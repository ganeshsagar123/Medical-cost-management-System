from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import advisor, analytics, auth, datasets, forecasts, health, insights, recommendations, scenarios
from app.core.config import get_settings
from app.db.init_db import initialize_database

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Healthcare financial and operational analytics foundation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(datasets.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(forecasts.router, prefix="/api/v1")
app.include_router(insights.router, prefix="/api/v1")
app.include_router(recommendations.router, prefix="/api/v1")
app.include_router(scenarios.router, prefix="/api/v1")
app.include_router(advisor.router, prefix="/api/v1")

frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        target_file = frontend_dist / full_path
        if full_path and target_file.exists() and target_file.is_file():
            return FileResponse(target_file)
        return FileResponse(frontend_dist / "index.html")
