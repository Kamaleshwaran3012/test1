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

        key = f"{namespace}/{pod_name}"
        previous_phase = self._status_cache.get(key)
        self._status_cache[key] = phase

        # Emit only first observation or actual phase transitions.
        if previous_phase is not None and previous_phase == phase:
            return None

        return {
            "source": "kubernetes",
            "service": pod_name,
            "log": f"Pod {namespace}/{pod_name} changed: {previous_phase or 'None'} -> {phase} ({event_type})",
            "error": phase,
            "_raw_kubernetes_event": {
                "namespace": namespace,
                "pod": pod_name,
                "event_type": event_type,
                "previous_phase": previous_phase,
                "current_phase": phase,
            },
        }
