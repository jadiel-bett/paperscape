from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import init_db
from app.dependencies import (
    ServiceContainer,
    app_exception_handler,
    AppException,
    build_container,
)
from app.routers import health_router, jobs_router, papers_router


def create_app(
    settings: Settings | None = None,
    *,
    container: ServiceContainer | None = None,
) -> FastAPI:
    """FastAPI application factory.

    Accepts an optional *settings* object and an optional pre-built
    *container* so tests can inject overrides without touching environment
    variables or the module-level cache.  When *container* is ``None`` a new
    container is built from *settings*.

    The container is attached to ``application.state.container`` **before**
    the lifespan runs so that the lifespan never overwrites a test-supplied
    container.
    """
    resolved_settings = settings or get_settings()
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[type-arg]
        init_db(resolved_settings.db_path)
        yield

    application = FastAPI(
        title="PaperScape API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Attach container before lifespan runs.
    application.state.container = resolved_container

    # Register exception handler for safe API error shape.
    application.add_exception_handler(AppException, app_exception_handler)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health_router, prefix="/api/v1")
    application.include_router(papers_router, prefix="/api/v1")
    application.include_router(jobs_router, prefix="/api/v1")

    return application


# Module-level instance for Uvicorn: uvicorn app.main:app
app = create_app()