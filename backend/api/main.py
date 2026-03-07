from fastapi import FastAPI

from backend.api.watchman_routes import router as watchman_router
from backend.api.watchman_routes import watchman_agent
from backend.tools.k8s_pod_watcher import K8sPodWatcher


app = FastAPI(title="Neoverse Backend API")
app.include_router(watchman_router)

pod_watcher = K8sPodWatcher(callback=watchman_agent.receive_event)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def start_background_watchers() -> None:
    await pod_watcher.start()


@app.on_event("shutdown")
async def stop_background_watchers() -> None:
    await pod_watcher.stop()
