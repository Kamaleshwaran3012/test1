from fastapi import FastAPI

from backend.api.watchman_routes import router as watchman_router


app = FastAPI(title="Neoverse Backend API")
app.include_router(watchman_router)
