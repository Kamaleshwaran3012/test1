from __future__ import annotations

import logging
from typing import Any

from backend.orchestrator import langgraph_service


logger = logging.getLogger("orchestrator.router")


async def handle_event(state: dict[str, Any]) -> None:
    """Entry point for Watchman -> Orchestrator dispatch."""
    logger.info(
        "orchestrator_event_received",
        extra={
            "event": {
                "source": state.get("event_source"),
                "service": state.get("suspected_service"),
                "timestamp": state.get("timestamp"),
            }
        },
    )

    handler = getattr(langgraph_service, "handle_event", None)
    if handler is None:
        logger.info("orchestrator_noop", extra={"event": {"reason": "langgraph_service.handle_event missing"}})
        return

    result = handler(state)
    if hasattr(result, "__await__"):
        await result
