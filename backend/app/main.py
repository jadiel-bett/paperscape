from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import init_db
from app.routers.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory.

    Accepts an optional *settings* object so tests can inject overrides
    without touching environment variables or the module-level cache.
    The lifespan hook closes over the resolved *settings* instance so that
    test-supplied settings (including in-memory database paths) are always
    honoured.
    """
    if settings is None:
        settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[type-arg]
        init_db(settings.db_path)
        yield

    application = FastAPI(
        title="PaperScape API",
        version="0.1.0",
        lifespan=lifespan,
    )

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
