from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from backend.agents.watchman.watchman_agent import WatchmanAgent


logger = logging.getLogger("watchman.routes")
router = APIRouter(tags=["watchman"])
watchman_agent = WatchmanAgent()


def _truncate(value: str, limit: int = 320) -> str:
    text = str(value or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _is_error_text(value: str | None) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return False
    keywords = ("fail", "error", "crash", "backoff", "oom", "timeout", "denied", "invalid")
    return any(keyword in text for keyword in keywords)


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
        commit_msg = _truncate(head_commit.get("message") or "n/a", 180)
        log = f"Push received on {ref} by {pusher}"
        log = f"{log} commit={commit_msg}"
        error = str(head_commit.get("message") or "push_event")
    elif github_event == "workflow_run":
        workflow_run = payload.get("workflow_run") or {}
        name = workflow_run.get("name", "workflow")
        status_text = workflow_run.get("status", "unknown")
        conclusion = workflow_run.get("conclusion", "unknown")
        html_url = workflow_run.get("html_url")
        branch = workflow_run.get("head_branch")
        head_sha = workflow_run.get("head_sha")
        log = (
            f"Workflow '{name}' failed: status={status_text} conclusion={conclusion} "
            f"branch={branch or 'unknown'} sha={(head_sha or 'unknown')[:12]} "
            f"url={html_url or 'n/a'}"
        )
        error = str(conclusion or status_text or "workflow_run_event")
    elif github_event == "check_suite":
        check_suite = payload.get("check_suite") or {}
        status_text = check_suite.get("status", "unknown")
        conclusion = check_suite.get("conclusion", "unknown")
        head_branch = check_suite.get("head_branch")
        head_sha = check_suite.get("head_sha")
        app_name = (check_suite.get("app") or {}).get("slug") or "unknown-app"
        log = (
            f"Check suite failed: app={app_name} status={status_text} conclusion={conclusion} "
            f"branch={head_branch or 'unknown'} sha={(head_sha or 'unknown')[:12]}"
        )
        error = str(conclusion or status_text or "check_suite_event")
    elif github_event == "check_run":
        check_run = payload.get("check_run") or {}
        name = check_run.get("name", "check_run")
        status_text = check_run.get("status", "unknown")
        conclusion = check_run.get("conclusion", "unknown")
        details_url = check_run.get("details_url")
        output = check_run.get("output") or {}
        summary = output.get("summary") or output.get("text") or ""
        summary_text = _truncate(summary, 220)
        log = (
            f"Check run '{name}' failed: status={status_text} conclusion={conclusion} "
            f"url={details_url or 'n/a'} summary={summary_text or 'n/a'}"
        )
        error = str(conclusion or status_text or summary_text or "check_run_event")
    else:
        action = payload.get("action")
        message = payload.get("message") or payload.get("log") or payload.get("error") or ""
        log = (
            f"GitHub event '{github_event}' action={action or 'n/a'} "
            f"message={_truncate(str(message), 220) or 'n/a'}"
        )
        error = str(message or action or github_event)

    return {
        "source": "github",
        "service": service,
        "log": log,
        "error": error,
        "file": file_path,
        "old_code": payload.get("old_code"),
        "new_code": payload.get("new_code"),
        "_raw_github_event": github_event,
    }


def _should_dispatch_github_event(raw_payload: dict[str, Any], github_event: str) -> bool:
    # Keep Watchman focused on actionable failure signals from CI/CD.
    if github_event == "workflow_run":
        workflow_run = raw_payload.get("workflow_run") or {}
        return workflow_run.get("status") == "completed" and workflow_run.get("conclusion") == "failure"

    if github_event == "check_suite":
        check_suite = raw_payload.get("check_suite") or {}
        return check_suite.get("status") == "completed" and check_suite.get("conclusion") == "failure"

    if github_event == "check_run":
        check_run = raw_payload.get("check_run") or {}
        return check_run.get("status") == "completed" and check_run.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}

    # For other GitHub events, dispatch only if payload text strongly looks like a failure.
    action = str(raw_payload.get("action") or "")
    message = str(raw_payload.get("message") or raw_payload.get("log") or raw_payload.get("error") or "")
    return _is_error_text(action) or _is_error_text(message)


def _adapt_kubernetes_payload(payload: dict[str, Any]) -> dict[str, Any]:
    involved_object = payload.get("involvedObject") or {}
    service_name = (
        payload.get("service")
        or involved_object.get("name")
        or involved_object.get("kind")
        or payload.get("reportingComponent")
        or "kubernetes-cluster"
    )
    reason = payload.get("reason") or payload.get("type") or "kubernetes_event"
    message = payload.get("message") or payload.get("log") or "Kubernetes change received"
    log = f"{reason}: {message}" if reason and message else str(message)

    return {
        "source": "kubernetes",
        "service": str(service_name),
        "log": str(log),
        "error": str(reason),
        "file": payload.get("file"),
    }


def _should_dispatch_kubernetes_event(raw_payload: dict[str, Any]) -> bool:
    event_type = str(raw_payload.get("type", "") or "").strip().lower()
    reason = str(raw_payload.get("reason", "") or "").strip()
    message = str(raw_payload.get("message") or raw_payload.get("log") or "").strip()

    if event_type == "warning":
        return True
    if _is_error_text(reason) or _is_error_text(message):
        return True

    return False


async def _dispatch_event(payload: dict[str, Any]) -> dict[str, str]:
    try:
        await watchman_agent.receive_event(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("watchman_route_failed", extra={"event": {"source": payload.get("source")}})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to receive event",
        ) from exc

    return {"status": "ok", "message": "Event accepted"}


@router.post("/webhook/github", status_code=status.HTTP_200_OK)
async def github_webhook(payload: dict[str, Any], request: Request) -> dict[str, str]:
    github_event = request.headers.get("X-GitHub-Event", "unknown")
    event_payload = _adapt_github_payload(payload, github_event)
    print(
        f"[Watchman] github_event_received type={github_event} "
        f"service={event_payload.get('service')}"
    )
    print(f"[Watchman] github_event_log={event_payload.get('log')}")
    logger.info(
        "watchman_github_event_received",
        extra={
            "event": {
                "github_event": github_event,
                "service": event_payload.get("service"),
                "log": event_payload.get("log"),
            }
        },
    )

    if not _should_dispatch_github_event(payload, github_event):
        print("[Watchman] github_event_dispatch=ignored reason=No failure signal detected")
        logger.info(
            "watchman_github_event_ignored",
            extra={
                "event": {
                    "github_event": github_event,
                    "reason": "No failure signal detected",
                    "service": event_payload.get("service"),
                }
            },
        )
        return {"status": "ok", "message": f"GitHub event ignored: {github_event}"}

    print("[Watchman] github_event_dispatch=forwarded")
    return await _dispatch_event(event_payload)


@router.post("/webhook/kubernetes", status_code=status.HTTP_200_OK)
async def kubernetes_webhook(payload: dict[str, Any]) -> dict[str, str]:
    if not _should_dispatch_kubernetes_event(payload):
        return {"status": "ok", "message": "Kubernetes event ignored: non-error"}

    event_payload = _adapt_kubernetes_payload(payload)
    return await _dispatch_event(event_payload)


@router.post("/watchman/event", status_code=status.HTTP_200_OK)
async def receive_watchman_event(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    raw_payload = dict(payload)
    event_payload = dict(raw_payload)
    github_event = request.headers.get("X-GitHub-Event")
    if github_event and "source" not in event_payload:
        event_payload = _adapt_github_payload(raw_payload, github_event)
        print(
            f"[Watchman] github_event_received type={github_event} "
            f"service={event_payload.get('service')}"
        )
        print(f"[Watchman] github_event_log={event_payload.get('log')}")
        if not _should_dispatch_github_event(raw_payload, github_event):
            print("[Watchman] github_event_dispatch=ignored reason=No failure signal detected")
            logger.info(
                "watchman_github_event_ignored",
                extra={"event": {"github_event": github_event}},
            )
            return {"status": "ok", "message": f"GitHub event ignored: {github_event}"}
        print("[Watchman] github_event_dispatch=forwarded")
    elif str(event_payload.get("source", "")).strip().lower() == "github":
        inferred_event = str(event_payload.get("_raw_github_event") or event_payload.get("event") or "direct")
        print(
            f"[Watchman] github_event_received type={inferred_event} "
            f"service={event_payload.get('service')}"
        )
        print(f"[Watchman] github_event_log={event_payload.get('log')}")
        print("[Watchman] github_event_dispatch=forwarded")

    return await _dispatch_event(event_payload)
