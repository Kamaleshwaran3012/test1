from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

from kubernetes import client, config, watch


logger = logging.getLogger("k8s.pod_watcher")


PodEventCallback = Callable[[dict[str, Any]], asyncio.Future[Any] | Any]


class K8sPodWatcher:
    """Watch Kubernetes pod changes and emit normalized events."""

    def __init__(self, callback: PodEventCallback) -> None:
        self._callback = callback
        self._task: asyncio.Task[None] | None = None
        self._stop_event = threading.Event()
        self._status_cache: dict[str, str] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(asyncio.to_thread(self._run_watch, loop))
        logger.info("k8s_pod_watcher_started")

    async def stop(self) -> None:
        if not self._task:
            return

        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("k8s_pod_watcher_stopped")

    def _load_config(self) -> bool:
        try:
            config.load_incluster_config()
            logger.info("k8s_config_loaded_incluster")
            return True
        except Exception:
            pass

        try:
            config.load_kube_config()
            logger.info("k8s_config_loaded_local")
            return True
        except Exception as exc:
            logger.warning("k8s_watcher_disabled_no_config", extra={"event": {"error": str(exc)}})
            return False

    def _run_watch(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self._load_config():
            return

        api = client.CoreV1Api()
        pod_watch = watch.Watch()

        while not self._stop_event.is_set():
            try:
                stream = pod_watch.stream(api.list_pod_for_all_namespaces, timeout_seconds=30)
                for event in stream:
                    if self._stop_event.is_set():
                        pod_watch.stop()
                        break

                    normalized = self._normalize_pod_event(event)
                    if not normalized:
                        continue

                    future = asyncio.run_coroutine_threadsafe(self._dispatch(normalized), loop)
                    try:
                        future.result(timeout=10)
                    except Exception:
                        logger.exception("k8s_watcher_dispatch_failed")
            except Exception:
                logger.exception("k8s_watcher_stream_error")

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        result = self._callback(payload)
        if asyncio.iscoroutine(result):
            await result

    def _normalize_pod_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        event_type = str(event.get("type") or "UNKNOWN")
        pod_obj = event.get("object")
        if pod_obj is None:
            return None

        metadata = getattr(pod_obj, "metadata", None)
        status = getattr(pod_obj, "status", None)
        pod_name = getattr(metadata, "name", None) or "unknown-pod"
        namespace = getattr(metadata, "namespace", None) or "default"
        phase = getattr(status, "phase", None) or "Unknown"

        failure_detail = self._extract_failure_detail(status)
        # Emit only actionable error states.
        if not failure_detail and phase not in {"Failed", "Unknown"}:
            return None

        signature = f"{phase}|{failure_detail or ''}"
        key = f"{namespace}/{pod_name}"
        previous_signature = self._status_cache.get(key)
        self._status_cache[key] = signature
        if previous_signature == signature:
            return None

        previous_phase = previous_signature.split("|", 1)[0] if previous_signature else None
        error_reason = failure_detail.split(":", 1)[0] if failure_detail else phase
        log_message = (
            f"Pod {namespace}/{pod_name} error: {failure_detail} (phase={phase}, event={event_type})"
            if failure_detail
            else f"Pod {namespace}/{pod_name} entered phase {phase} ({event_type})"
        )
        return {
            "source": "kubernetes",
            "service": pod_name,
            "log": log_message,
            "error": error_reason,
            "_raw_kubernetes_event": {
                "namespace": namespace,
                "pod": pod_name,
                "event_type": event_type,
                "previous_phase": previous_phase,
                "current_phase": phase,
                "failure_detail": failure_detail,
            },
        }

    def _extract_failure_detail(self, status: Any) -> str | None:
        if status is None:
            return None

        container_statuses = list(getattr(status, "init_container_statuses", None) or [])
        container_statuses.extend(getattr(status, "container_statuses", None) or [])

        waiting_error_reasons = {
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "ErrImagePull",
            "CreateContainerConfigError",
            "CreateContainerError",
            "RunContainerError",
            "InvalidImageName",
            "OOMKilled",
        }

        for container in container_statuses:
            name = getattr(container, "name", "container")
            state = getattr(container, "state", None)
            waiting = getattr(state, "waiting", None)
            if waiting is not None:
                reason = str(getattr(waiting, "reason", "") or "").strip()
                message = str(getattr(waiting, "message", "") or "").strip()
                if reason in waiting_error_reasons or "backoff" in reason.lower() or "error" in reason.lower():
                    suffix = f": {message}" if message else ""
                    return f"{reason or 'WaitingError'} in {name}{suffix}"

            terminated = getattr(state, "terminated", None)
            if terminated is not None:
                reason = str(getattr(terminated, "reason", "") or "").strip() or "Terminated"
                message = str(getattr(terminated, "message", "") or "").strip()
                exit_code = getattr(terminated, "exit_code", None)
                if exit_code not in (None, 0) or reason.lower() not in {"completed"}:
                    exit_part = f" (exit_code={exit_code})" if exit_code is not None else ""
                    msg_part = f": {message}" if message else ""
                    return f"{reason} in {name}{exit_part}{msg_part}"

        conditions = getattr(status, "conditions", None) or []
        for condition in conditions:
            condition_type = str(getattr(condition, "type", "") or "").strip()
            condition_status = str(getattr(condition, "status", "") or "").strip()
            reason = str(getattr(condition, "reason", "") or "").strip()
            message = str(getattr(condition, "message", "") or "").strip()
            if condition_type == "Ready" and condition_status == "False" and (reason or message):
                msg_part = f": {message}" if message else ""
                return f"{reason or 'NotReady'}{msg_part}"

        return None
