from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from backend.agents.state import AgentState

try:
    from langchain.output_parsers import ResponseSchema, StructuredOutputParser  # type: ignore

    HAS_STRUCTURED_OUTPUT_PARSER = True
except ModuleNotFoundError:
    HAS_STRUCTURED_OUTPUT_PARSER = False

    @dataclass
    class ResponseSchema:  # pragma: no cover - simple compatibility shim
        name: str
        description: str


logger = logging.getLogger("watchman")


class NormalizedEvent(BaseModel):
    event_source: str = Field(description="Alert source, normalized to lowercase")
    service_name: str = Field(description="Service/application name")
    error_log: str = Field(description="Most useful error log message")
    file_path: str | None = Field(default=None, description="Path to related file if present")


class WatchmanAgent:
    """Receives, validates, normalizes, and forwards incoming DevOps events."""

    SUPPORTED_SOURCES = {"github", "kubernetes", "aws", "docker", "grafana"}
    REQUIRED_FIELDS = {"source", "service", "log"}

    def __init__(self, repo_root: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

    async def receive_event(self, payload: dict[str, Any]) -> None:
        """Validate quickly, then process in background so HTTP can return immediately."""
        self.validate_event(payload)
        task = asyncio.create_task(self._process_event(payload))
        task.add_done_callback(self._log_background_task_result)

    @staticmethod
    def _log_background_task_result(task: asyncio.Task[Any]) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("watchman_background_process_failed")

    def validate_event(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")

        missing = [field for field in self.REQUIRED_FIELDS if not payload.get(field)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")

        source = str(payload["source"]).strip().lower()
        if source not in self.SUPPORTED_SOURCES:
            supported = ", ".join(sorted(self.SUPPORTED_SOURCES))
            raise ValueError(f"Unsupported source '{source}'. Supported sources: {supported}")

    async def parse_event_with_langchain(self, payload: dict[str, Any]) -> dict[str, str | None]:
        parser: Any
        if HAS_STRUCTURED_OUTPUT_PARSER:
            response_schemas = [
                ResponseSchema(name="event_source", description="Alert source, normalized to lowercase"),
                ResponseSchema(name="service_name", description="Service/application name"),
                ResponseSchema(name="error_log", description="Most useful error log message"),
                ResponseSchema(name="file_path", description="Path to related file if present, else null"),
            ]
            parser = StructuredOutputParser.from_response_schemas(response_schemas)
        else:
            parser = PydanticOutputParser(pydantic_object=NormalizedEvent)

        prompt = PromptTemplate(
            template=(
                "You normalize DevOps webhook events.\n"
                "Return only structured output.\n\n"
                "{format_instructions}\n\n"
                "Incoming event JSON:\n{payload_json}"
            ),
            input_variables=["payload_json"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )

        normalized_input = {
            "event_source": str(payload.get("source", "")).strip().lower(),
            "service_name": str(payload.get("service", "")).strip(),
            "error_log": str(payload.get("log") or payload.get("error") or "").strip(),
            "file_path": str(payload.get("file")).strip() if payload.get("file") else None,
        }

        _ = prompt.format(payload_json=json.dumps(payload, ensure_ascii=True))
        result = parser.parse(json.dumps(normalized_input, ensure_ascii=True))
        if isinstance(result, BaseModel):
            result_data = result.model_dump()
        else:
            result_data = dict(result)

        return {
            "event_source": str(result_data.get("event_source", "")).strip().lower(),
            "service_name": str(result_data.get("service_name", "")).strip(),
            "error_log": str(result_data.get("error_log", "")).strip(),
            "file_path": str(result_data.get("file_path")).strip() if result_data.get("file_path") else None,
        }

    def initialize_state(self, parsed_event: dict[str, str | None]) -> AgentState:
        file_path = parsed_event.get("file_path")
        file_contents = self._load_file(file_path)
        files_context = {file_path: file_contents} if file_path and file_contents is not None else {}

        return {
            "error_log": parsed_event.get("error_log"),
            "detected_errors": [parsed_event.get("error_log", "")] if parsed_event.get("error_log") else [],
            "current_error": parsed_event.get("error_log"),
            "files_context": files_context,
            "event_source": parsed_event.get("event_source"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suspected_service": parsed_event.get("service_name"),
            "error_type": None,
            "diagnosis_type": None,
            "file_path": file_path,
            "line_number": None,
            "fix_description": None,
            "replacement_code": None,
            "root_cause": None,
            "confidence_score": None,
            "patch_generated": None,
            "pr_title": None,
            "pr_description": None,
            "iteration_count": 0,
            "processed_errors": [],
            "agent_logs": [],
        }

    def log_event(self, state: dict[str, Any]) -> None:
        for message in state.get("agent_logs", []):
            logger.info(
                "watchman_event_log",
                extra={
                    "event": {
                        "source": state.get("event_source"),
                        "service": state.get("suspected_service"),
                        "message": message,
                        "timestamp": state.get("timestamp"),
                    }
                },
            )

    async def dispatch_to_orchestrator(self, state: dict[str, Any]) -> None:
        print("[Watchman] dispatch_start")
        try:
            from backend.orchestrator import router as orchestrator_router  # type: ignore

            handler = getattr(orchestrator_router, "handle_event", None)
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    await handler(state)
                else:
                    handler(state)
                print("[Watchman] dispatch_via=orchestrator.router")
                return
        except Exception:
            logger.exception("watchman_dispatch_router_failed")

        try:
            from backend.orchestrator import langgraph_service  # type: ignore

            handler = getattr(langgraph_service, "handle_event", None)
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    await handler(state)
                else:
                    handler(state)
                print("[Watchman] dispatch_via=orchestrator.langgraph_service")
                return
        except Exception:
            logger.exception("watchman_dispatch_langgraph_failed")

        # Fallback 1: call workflow directly when router/service wiring is unavailable.
        try:
            from backend.graph.workflow import run_workflow  # type: ignore

            result_state = await run_workflow(state)
            if isinstance(result_state, dict):
                state.update(result_state)
            logger.warning("watchman_dispatch_fallback_workflow")
            print("[Watchman] dispatch_via=fallback.workflow")
            return
        except Exception:
            logger.exception("watchman_dispatch_fallback_workflow_failed")

        # Fallback 2: ensure triage still runs even without full graph.
        try:
            from backend.agents import triage_agent as triage_module  # type: ignore

            handler = getattr(triage_module, "handle_event", None) or getattr(triage_module, "run", None)
            if handler:
                result = handler(state)
                if hasattr(result, "__await__"):
                    result = await result
                if isinstance(result, dict):
                    state.update(result)
                logger.warning("watchman_dispatch_fallback_triage_only")
                print("[Watchman] dispatch_via=fallback.triage")
                return
        except Exception:
            logger.exception("watchman_dispatch_fallback_triage_failed")

        logger.warning("watchman_dispatch_skipped", extra={"event": {"reason": "No orchestrator/triage handler found"}})
        print("[Watchman] dispatch_via=skipped")

    async def _process_event(self, payload: dict[str, Any]) -> None:
        parsed_event = await self.parse_event_with_langchain(payload)
        state = self.initialize_state(parsed_event)

        state["agent_logs"].append(f"Watchman received event from {parsed_event.get('event_source')}")
        state["agent_logs"].append("Event normalized using LangChain")
        state["agent_logs"].append(f"Service {parsed_event.get('service_name')} detected")
        state["agent_logs"].append("Global state initialized")
        normalized_error_log = state.get("error_log")
        logger.info(
            "watchman_normalized_error_log",
            extra={
                "event": {
                    "source": state.get("event_source"),
                    "service": state.get("suspected_service"),
                    "error_log": normalized_error_log,
                }
            },
        )
        print(f"[Watchman] normalized_error_log_for_pathologist={normalized_error_log}")

        await self.dispatch_to_orchestrator(state)
        state["agent_logs"].append("Event dispatched to orchestrator")
        self.log_event(state)

    def _load_file(self, file_path: str | None) -> str | None:
        if not file_path:
            return None

        candidate = (self.repo_root / file_path).resolve()
        try:
            if not str(candidate).startswith(str(self.repo_root.resolve())):
                return None
            if candidate.exists() and candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except Exception:
            logger.exception("watchman_file_load_failed", extra={"event": {"file_path": file_path}})
        return None
