import logging
from typing import Any

from backend.agents.gemini_client import (
    DEFAULT_LLM_MODEL,
    GeminiQuotaExceededError,
    invoke_text,
    parse_json_dict,
)
from backend.agents.state import AgentState
from backend.prompts.triage_prompt import TRIAGE_SYSTEM_PROMPT


logger = logging.getLogger("agents.triage")


def _render_triage_prompt(state: AgentState) -> str:
    prompt = TRIAGE_SYSTEM_PROMPT
    prompt = prompt.replace("{current_error}", str(state.get("current_error", "")))
    prompt = prompt.replace("{error_log}", str(state.get("error_log", "")))
    prompt = prompt.replace("{event_source}", str(state.get("event_source", "")))
    return prompt


def _heuristic_fallback(state: AgentState) -> dict[str, str]:
    error_log = str(state.get("error_log", "")).lower()
    source = str(state.get("event_source", "")).lower()

    if source == "kubernetes" or "pod " in error_log or "kube-" in error_log:
        return {"error_type": "infra", "suspected_service": "kubernetes"}
    if any(token in error_log for token in ("build", "ci", "docker build", "github actions", "pip install", "npm install")):
        return {"error_type": "build", "suspected_service": "github-actions"}
    return {"error_type": "runtime", "suspected_service": "unknown"}


def _normalize_error_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"infra", "build", "runtime"}:
        return normalized
    return "runtime"


def _deterministic_triage(state: AgentState) -> dict[str, str] | None:
    source = str(state.get("event_source", "")).lower()
    error_log = str(state.get("error_log", "")).lower()
    suspected_service = str(state.get("suspected_service", "")).lower()
    combined = " ".join((error_log, suspected_service))

    infra_tokens = (
        "kubernetes",
        "pod ",
        "crashloopbackoff",
        "imagepullbackoff",
        "errimagepull",
        "oomkilled",
        "createcontainerconfigerror",
        "etcd",
        "coredns",
        "node notready",
        "failedscheduling",
    )
    build_tokens = (
        "github actions",
        "workflow",
        "check suite",
        "check run",
        "ci",
        "docker build",
        "build failed",
        "pip install",
        "npm install",
        "pnpm install",
        "poetry install",
        "compilation failed",
        "docker login",
        "requested access to the resource is denied",
        "unauthorized",
        "authentication required",
        "pull access denied",
        "repository does not exist",
        "manifest unknown",
        "insufficient_scope",
        "errimagepull",
        "imagepullbackoff",
    )
    runtime_tokens = (
        "traceback",
        "exception",
        "runtimeerror",
        "typeerror",
        "valueerror",
        "keyerror",
        "nullpointer",
        "segmentation fault",
        "500 internal server error",
    )

    if any(token in combined for token in runtime_tokens):
        return {"error_type": "runtime", "suspected_service": state.get("suspected_service") or "application-runtime"}
    if any(token in combined for token in build_tokens):
        return {"error_type": "build", "suspected_service": state.get("suspected_service") or "github-actions"}
    if any(token in combined for token in infra_tokens):
        return {"error_type": "infra", "suspected_service": state.get("suspected_service") or "kubernetes"}
    if source == "kubernetes":
        return {"error_type": "infra", "suspected_service": state.get("suspected_service") or "kubernetes"}
    if source == "github":
        return {"error_type": "build", "suspected_service": state.get("suspected_service") or "github-actions"}

    return None


def triage_agent(state: AgentState) -> dict[str, Any]:
    print("[Triage] entered")
    prompt = _render_triage_prompt(state)
    deterministic = _deterministic_triage(state)

    if deterministic:
        result = deterministic
    else:
        try:
            response_text = invoke_text(prompt, model=DEFAULT_LLM_MODEL, temperature=0)
            result = parse_json_dict(response_text)
        except GeminiQuotaExceededError:
            logger.warning("triage_llm_quota_exhausted_using_heuristic")
            result = _heuristic_fallback(state)
        except Exception:
            logger.exception("triage_llm_fallback")
            result = _heuristic_fallback(state)

    result["error_type"] = _normalize_error_type(result.get("error_type"))
    if not result.get("suspected_service"):
        result["suspected_service"] = state.get("suspected_service") or "unknown"

    print(
        f"[Triage] classified error_type={result.get('error_type')} "
        f"suspected_service={result.get('suspected_service')}"
    )
    return {
        "error_type": result.get("error_type"),
        "suspected_service": result.get("suspected_service"),
        "agent_logs": [f"Triage classified error as {result.get('error_type')}"]
    }


def handle_event(state: AgentState) -> dict[str, Any]:
    """LangGraph-compatible entrypoint used by orchestrator workflow."""
    return triage_agent(state)


def run(state: AgentState) -> dict[str, Any]:
    """Compatibility alias for generic orchestrator discovery."""
    return triage_agent(state)
