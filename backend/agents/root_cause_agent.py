from __future__ import annotations

import logging
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.root_cause_agent import RootCauseAgent as LegacyRootCauseAgent
from backend.agents.state import AgentState


logger = logging.getLogger("agents.root_cause")


@dataclass
class _QueuedRootCauseRequest:
    state: AgentState
    done: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: Exception | None = None


_root_cause_queue: queue.Queue[_QueuedRootCauseRequest] = queue.Queue()
_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None


def _queue_worker() -> None:
    while True:
        request = _root_cause_queue.get()
        try:
            agent = LegacyRootCauseAgent()
            output = agent.analyze(request.state)
            if isinstance(output, dict):
                print(f"[Pipeline] worker_received patch_present={bool(output.get('patch_generated'))}")
                output = _apply_patch_and_run_utils(output)
                request.result = output
            else:
                request.result = dict(request.state)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            request.error = exc
            logger.exception("root_cause_queue_worker_failed")
        finally:
            request.done.set()
            _root_cause_queue.task_done()


def _ensure_worker_running() -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_queue_worker, name="root-cause-queue-worker", daemon=True)
        _worker_thread.start()


def _apply_patch_and_run_utils(state: dict[str, Any]) -> dict[str, Any]:
    logs = state.setdefault("agent_logs", [])
    try:
        from utils.create_pr import create_pull_request
        from utils.git_push import push_changes
        from utils.patch_builder import generate_git_patch_from_text
        from utils.run_tests import run_tests
        from utils.slack_notify import send_slack_notification
    except Exception as exc:  # pragma: no cover - runtime env guard
        logs.append(f"[Pipeline] utils_import_failed: {type(exc).__name__}: {exc}")
        print(f"[Pipeline] utils_import_failed error={type(exc).__name__}: {exc}")
        return state

    patch = state.get("patch_generated")
    if not isinstance(patch, str) or not patch.strip():
        logs.append("[Pipeline] Skipped utils flow: no patch generated")
        print("[Pipeline] skipped reason=no_patch_generated")
        return state

    patch_file = Path.cwd() / "fix.patch"
    patch_file.write_text(patch, encoding="utf-8")
    logs.append(f"[Pipeline] fix.patch written at {patch_file}")
    print(f"[Pipeline] fix_patch_written path={patch_file}")

    apply_check = subprocess.run(["git", "apply", "--check", str(patch_file)], capture_output=True, text=True)
    if apply_check.returncode != 0:
        print("[Pipeline] git_apply_check_failed retrying_with_whitespace_flags=true")
        apply_check = subprocess.run(
            ["git", "apply", "--check", "--ignore-whitespace", "--ignore-space-change", str(patch_file)],
            capture_output=True,
            text=True,
        )
        if apply_check.returncode != 0:
            # Rebuild patch against current file content when payload old/new exists.
            file_path = str(state.get("file_path") or "").strip()
            old_code = state.get("old_code")
            new_code = state.get("new_code")
            rebuilt = False
            if file_path and isinstance(old_code, str) and isinstance(new_code, str):
                target = Path(file_path)
                if not target.exists():
                    target = Path.cwd() / file_path
                if target.exists():
                    current = target.read_text(encoding="utf-8", errors="ignore")
                    for old_variant in (old_code, old_code.replace("\r\n", "\n"), old_code.replace("\n", "\r\n")):
                        if old_variant and old_variant in current:
                            if "\r\n" in old_variant and "\r\n" not in new_code:
                                new_variant = new_code.replace("\n", "\r\n")
                            elif "\n" in old_variant and "\r\n" in new_code:
                                new_variant = new_code.replace("\r\n", "\n")
                            else:
                                new_variant = new_code
                            updated = current.replace(old_variant, new_variant, 1)
                            patch = generate_git_patch_from_text(file_path.replace("\\", "/"), current, updated)
                            if patch:
                                patch_file.write_text(patch, encoding="utf-8")
                                state["patch_generated"] = patch
                                rebuilt = True
                                print("[Pipeline] patch_rebuilt_from_current_file=true")
                                break
            if rebuilt:
                apply_check = subprocess.run(
                    ["git", "apply", "--check", "--ignore-whitespace", "--ignore-space-change", str(patch_file)],
                    capture_output=True,
                    text=True,
                )
                if apply_check.returncode == 0:
                    apply_cmd = ["git", "apply", "--ignore-whitespace", "--ignore-space-change", str(patch_file)]
                else:
                    print(f"[Pipeline] rebuilt_patch_apply_check_failed error={apply_check.stderr.strip() or apply_check.stdout.strip()}")

        if apply_check.returncode != 0:
            reverse_check = subprocess.run(
                ["git", "apply", "--reverse", "--check", "--ignore-whitespace", "--ignore-space-change", str(patch_file)],
                capture_output=True,
                text=True,
            )
            if reverse_check.returncode == 0:
                logs.append("[Pipeline] patch already applied; continuing pipeline")
                print("[Pipeline] patch_already_applied continuing=true")
                state["repo_fix_applied"] = True
            else:
                logs.append(f"[Pipeline] git apply --check failed: {apply_check.stderr.strip() or apply_check.stdout.strip()}")
                print(f"[Pipeline] git_apply_check_failed_final error={apply_check.stderr.strip() or apply_check.stdout.strip()}")
                send_slack_notification("Patch generated but git apply --check failed.")
                print("[Pipeline] slack_notify_sent type=apply_check_failed")
                state["slack_notified"] = True
                return state
        apply_cmd = ["git", "apply", "--ignore-whitespace", "--ignore-space-change", str(patch_file)]
    else:
        apply_cmd = ["git", "apply", str(patch_file)]

    if not state.get("repo_fix_applied"):
        apply_result = subprocess.run(apply_cmd, capture_output=True, text=True)
        if apply_result.returncode != 0:
            logs.append(f"[Pipeline] git apply failed: {apply_result.stderr.strip() or apply_result.stdout.strip()}")
            print(f"[Pipeline] git_apply_failed error={apply_result.stderr.strip() or apply_result.stdout.strip()}")
            send_slack_notification("Patch generated but git apply failed.")
            print("[Pipeline] slack_notify_sent type=apply_failed")
            state["slack_notified"] = True
            return state

        logs.append("[Pipeline] git apply succeeded")
        print("[Pipeline] git_apply_succeeded")
        state["repo_fix_applied"] = True

    test_result = run_tests()
    state["test_logs"] = test_result.get("logs")
    logs.append(f"[Pipeline] tests_success={bool(test_result.get('success'))}")
    print(f"[Pipeline] tests_completed success={bool(test_result.get('success'))}")
    if not test_result.get("success"):
        send_slack_notification("Automated fix attempted but tests are still failing.")
        print("[Pipeline] slack_notify_sent type=tests_failed")
        state["slack_notified"] = True
        return state

    try:
        print("[Pipeline] git_push_started")
        push_changes()
        state["pr_created"] = True
        print("[Pipeline] git_push_succeeded")
        print("[Pipeline] create_pr_started")
        pr_link = create_pull_request()
        state["pr_link"] = pr_link
        state["code_review_triggered"] = True
        logs.append(f"[Pipeline] PR created: {pr_link}")
        print(f"[Pipeline] create_pr_succeeded url={pr_link}")
        send_slack_notification(
            f"CI issue fixed automatically.\nRoot Cause: {state.get('root_cause')}\nPull Request: {pr_link}"
        )
        print("[Pipeline] slack_notify_sent type=success")
        state["slack_notified"] = True
    except Exception as exc:  # pragma: no cover - integration runtime guard
        logs.append(f"[Pipeline] PR flow failed: {type(exc).__name__}: {exc}")
        print(f"[Pipeline] pr_flow_failed error={type(exc).__name__}: {exc}")
        send_slack_notification("Patch applied and tests passed, but PR creation failed.")
        print("[Pipeline] slack_notify_sent type=pr_flow_failed")
        state["slack_notified"] = True

    return state


def root_cause_agent(state: AgentState) -> dict[str, Any]:
    print("[RootCause] entered")
    print(f"[RootCause] input_file_path={state.get('file_path')}")
    _ensure_worker_running()

    logs = state.setdefault("agent_logs", [])
    pending_before = _root_cause_queue.qsize()
    logs.append(f"Root cause request queued (pending_before={pending_before})")

    request = _QueuedRootCauseRequest(state=state)
    _root_cause_queue.put(request)
    request.done.wait()

    if request.error is not None:
        error_message = f"{type(request.error).__name__}: {request.error}"
        logs.append(f"Root cause queue worker failed; request skipped ({error_message})")
        print(f"[RootCause] failed error={error_message}")
        return {"agent_logs": logs}

    result = request.result if isinstance(request.result, dict) else {"agent_logs": logs}
    patch_generated = bool((result or {}).get("patch_generated"))
    logs.append("Root cause request completed from queue")
    if not patch_generated:
        last_reason = ""
        result_logs = (result or {}).get("agent_logs", [])
        if isinstance(result_logs, list):
            surgeon_logs = [msg for msg in result_logs if isinstance(msg, str) and "[SurgeonAgent]" in msg]
            if surgeon_logs:
                last_reason = surgeon_logs[-1]
        if last_reason:
            print(f"[RootCause] completed patch_generated={patch_generated} reason={last_reason}")
        else:
            print(f"[RootCause] completed patch_generated={patch_generated}")
    else:
        print(f"[RootCause] completed patch_generated={patch_generated}")

    return result


def handle_event(state: AgentState) -> dict[str, Any]:
    return root_cause_agent(state)


def run(state: AgentState) -> dict[str, Any]:
    return root_cause_agent(state)
