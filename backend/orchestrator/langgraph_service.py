from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("orchestrator.langgraph")


async def handle_event(state: dict[str, Any]) -> None:
    """Run the LangGraph workflow for the incoming state."""
    logger.info(
        "langgraph_event_accepted",
        extra={
            "event": {
                "source": state.get("event_source"),
                "service": state.get("suspected_service"),
            }
        },
    )
    try:
        from backend.graph.workflow import run_workflow
    except ModuleNotFoundError as exc:
        logger.warning(
            "langgraph_unavailable",
            extra={"event": {"reason": str(exc), "action": "workflow skipped"}},
        )
        logs = state.setdefault("agent_logs", [])
        logs.append("Orchestrator workflow skipped: langgraph not installed")
        return

    result_state = await run_workflow(state)
    state.update(result_state)
