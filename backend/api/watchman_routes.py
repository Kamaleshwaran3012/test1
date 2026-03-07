from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from backend.agents.watchman.watchman_agent import WatchmanAgent


logger = logging.getLogger("watchman.routes")
router = APIRouter(prefix="/watchman", tags=["watchman"])
watchman_agent = WatchmanAgent()


def _adapt_github_payload(payload: dict[str, Any], github_event: str) -> dict[str, Any]:
    repository = payload.get("repository") or {}
    service = repository.get("name") or repository.get("full_name") or "github-repository"
    log = f"GitHub event: {github_event}"
    error = github_event
    file_path = None

    if github_event == "push":
        ref = payload.get("ref", "unknown-ref")
        pusher = (payload.get("pusher") or {}).get("name", "unknown-user")
        head_commit = payload.get("head_commit") or {}
        modified = head_commit.get("modified") or head_commit.get("added") or []
        file_path = modified[0] if modified else None
        log = f"Push received on {ref} by {pusher}"
        error = "push_event"
    elif github_event == "workflow_run":
        workflow_run = payload.get("workflow_run") or {}
        name = workflow_run.get("name", "workflow")
        status_text = workflow_run.get("status", "unknown")
        conclusion = workflow_run.get("conclusion", "unknown")
        log = f"Workflow '{name}' status={status_text} conclusion={conclusion}"
        error = conclusion or "workflow_run_event"
    elif github_event == "check_suite":
        check_suite = payload.get("check_suite") or {}
        status_text = check_suite.get("status", "unknown")
        conclusion = check_suite.get("conclusion", "unknown")
        log = f"Check suite status={status_text} conclusion={conclusion}"
        error = conclusion or "check_suite_event"

    return {
        "source": "github",
        "service": service,
        "log": log,
        "error": error,
        "file": file_path,
        "_raw_github_event": github_event,
    }


@router.post("/event", status_code=status.HTTP_200_OK)
async def receive_watchman_event(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    event_payload = dict(payload)
    github_event = request.headers.get("X-GitHub-Event")
    if github_event and "source" not in event_payload:
        event_payload = _adapt_github_payload(event_payload, github_event)

    try:
        await watchman_agent.receive_event(event_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("watchman_route_failed", extra={"event": {"source": event_payload.get("source")}})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to receive event",
        ) from exc

    return {"status": "ok", "message": "Event accepted"}
