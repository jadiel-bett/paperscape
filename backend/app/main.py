from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory.

    Accepts an optional *settings* object so tests can inject overrides
    without touching environment variables or the module-level cache.
    """
    if settings is None:
        settings = get_settings()

    application = FastAPI(title="PaperScape API", version="0.1.0")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router, prefix="/api/v1")

    return application


# Module-level instance for Uvicorn: uvicorn app.main:app
app = create_app()
