"""Application service container and FastAPI dependency injection.

Provides the :class:`ServiceContainer` dataclass and FastAPI ``Depends``
callables so that route handlers never construct services or repositories
directly.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.repositories import CreatorPackStore, ExtractionStore, JobStore, ResearchMapStore
from app.models.provider import (
    ModelCapability,
    ModelReference,
    ProviderType,
    TaskPolicy,
    TaskType,
)
from app.services.creator_pack import CreatorPackService
from app.services.extraction import ExtractionService
from app.services.extractive_research_map import ExtractiveResearchMapService
from app.services.llm_provider import WatsonxProvider
from app.services.provider_adapters import OpenAIAdapter, OpenAICompatibleAdapter
from app.services.provider_ports import ModelRouter, ProviderRegistry
from app.services.research_map import ResearchMapService
from app.services.research_map_job_runner import (
    ExtractiveFallbackFactory,
    ResearchMapJobRunner,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared API error shape
# ---------------------------------------------------------------------------


class AppException(Exception):
    """A safe, structured HTTP error with a machine-readable code and
    a human-readable message.

    Raised from route handlers and caught by a registered exception handler
    that produces ``{"detail": {"code": ..., "message": ...}}``.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    """FastAPI exception handler for :class:`AppException`."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


# ---------------------------------------------------------------------------
# Service container
# ---------------------------------------------------------------------------


@dataclass
class ServiceContainer:
    """Holds all application services, repositories, and factories.

    Constructed once by :func:`build_container` and attached to
    ``app.state.container`` during ``create_app()``.

    Tests may construct a :class:`ServiceContainer` directly with fakes
    and pass it via ``create_app(settings, container=...)``.
    """

    settings: Settings
    extraction_service: ExtractionService
    job_store: JobStore
    extraction_store: ExtractionStore
    research_map_store: ResearchMapStore
    extractive_fallback_factory: ExtractiveFallbackFactory
    paper_id_factory: Callable[[], str]
    job_runner_factory: Callable[[], ResearchMapJobRunner] | None
    creator_pack_store: CreatorPackStore | None = None
    creator_pack_service: CreatorPackService | None = None
    job_creation_lock: threading.Lock = field(default_factory=threading.Lock)


# ---------------------------------------------------------------------------
# Container builder
# ---------------------------------------------------------------------------


def build_container(settings: Settings) -> ServiceContainer:
    """Build a fully wired :class:`ServiceContainer` from *settings*.

    - ``ExtractionService``, ``JobStore``, ``ExtractionStore``,
      ``ResearchMapStore`` are **always** constructed.
    - ``WatsonxProvider`` is **not** constructed here.  The container stores a
      lazy ``job_runner_factory`` so app import, startup, health checks,
      uploads, polling, and map retrieval never contact IBM.
    - Missing credentials leave ``job_runner_factory=None`` and the
      research-map job endpoint returns 503 before creating a job.
    """
    extraction_service = ExtractionService()
    job_store = JobStore(settings.db_path)
    extraction_store = ExtractionStore(settings.db_path)
    research_map_store = ResearchMapStore(settings.db_path)
    creator_pack_store = CreatorPackStore(settings.db_path)
    creator_pack_service = CreatorPackService()
    extractive_fallback_factory: ExtractiveFallbackFactory = ExtractiveResearchMapService

    job_runner_factory: Callable[[], ResearchMapJobRunner] | None = None

    def _build_provider():
        """Choose a configured managed/BYOK route without leaking credentials."""
        adapters = []
        if settings.default_provider in {"managed", "watsonx"} and settings.watsonx_api_key.get_secret_value():
            adapters.append(WatsonxProvider(settings))
        if settings.default_provider in {"managed", "openai"} and settings.openai_api_key.get_secret_value():
            adapters.append(OpenAIAdapter(
                api_key=settings.openai_api_key.get_secret_value(),
                model_id=settings.openai_model_id,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ))
        if settings.default_provider in {"compatible", "byok"} and settings.compatible_api_key.get_secret_value() and settings.compatible_base_url:
            adapters.append(OpenAICompatibleAdapter(
                api_key=settings.compatible_api_key.get_secret_value(),
                model_id=settings.compatible_model_id,
                base_url=settings.compatible_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
            ))
        if not adapters:
            return None
        preferred = []
        if settings.default_provider in {"managed", "watsonx"}:
            preferred.append(ModelReference(provider_type=ProviderType.WATSONX, model_id=settings.granite_model_id))
        if settings.default_provider in {"managed", "openai"}:
            preferred.append(ModelReference(provider_type=ProviderType.OPENAI, model_id=settings.openai_model_id))
        if settings.default_provider in {"compatible", "byok"}:
            preferred.append(ModelReference(provider_type=ProviderType.OPENAI_COMPATIBLE, model_id=settings.compatible_model_id))
        return ModelRouter(ProviderRegistry(tuple(adapters))).route(
            TaskPolicy(
                task=TaskType.RESEARCH_MAP,
                required_capabilities={ModelCapability.STRUCTURED_OUTPUT},
                preferred_models=preferred,
            )
        )

    if (
        settings.watsonx_api_key.get_secret_value()
        or settings.openai_api_key.get_secret_value()
        or (settings.compatible_api_key.get_secret_value() and settings.compatible_base_url)
    ):
        def _build_job_runner() -> ResearchMapJobRunner:
            llm_provider = _build_provider()
            if llm_provider is None:
                raise RuntimeError("No configured provider route")
            research_map_service = ResearchMapService(llm_provider)
            return ResearchMapJobRunner(
                job_store=job_store,
                extraction_store=extraction_store,
                research_map_store=research_map_store,
                research_map_service=research_map_service,
                extractive_fallback_factory=extractive_fallback_factory,
            )

        job_runner_factory = _build_job_runner
    else:
        _log.info(
            "WATSONX_API_KEY is empty. "
            "Research-map generation will be unavailable (503)."
        )

    return ServiceContainer(
        settings=settings,
        extraction_service=extraction_service,
        job_store=job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        extractive_fallback_factory=extractive_fallback_factory,
        paper_id_factory=lambda: str(uuid.uuid4()),
        job_runner_factory=job_runner_factory,
        creator_pack_store=creator_pack_store,
        creator_pack_service=creator_pack_service,
    )


def run_research_map_job(container: ServiceContainer, job_id: str) -> None:
    """Construct and run a research-map job runner lazily.

    This function is safe to schedule with FastAPI ``BackgroundTasks``.  It is
    the first place where ``WatsonxProvider`` may be constructed.  Provider or
    SDK construction failures are converted to the safe persisted
    ``llm_provider_error`` code without leaking raw exception details.
    """
    if container.job_runner_factory is None:
        _log.error("Job %r cannot run because generation is unavailable.", job_id)
        try:
            container.job_store.mark_failed(job_id, error_code="llm_provider_error")
        except Exception as exc:
            _log.error(
                "Failed to mark job %r after unavailable generation: %s",
                job_id,
                type(exc).__name__,
            )
        return

    try:
        runner = container.job_runner_factory()
    except Exception as exc:
        _log.error(
            "Failed to construct research-map runner for job %r: %s",
            job_id,
            type(exc).__name__,
        )
        try:
            container.job_store.mark_failed(job_id, error_code="llm_provider_error")
        except Exception as mark_exc:
            _log.error(
                "Failed to mark job %r after provider construction failure: %s",
                job_id,
                type(mark_exc).__name__,
            )
        return

    runner.run(job_id)


# ---------------------------------------------------------------------------
# FastAPI dependency callables
# ---------------------------------------------------------------------------


def get_settings(request: Request) -> Settings:
    return request.app.state.container.settings


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_extraction_service(request: Request) -> ExtractionService:
    return request.app.state.container.extraction_service


def get_job_store(request: Request) -> JobStore:
    return request.app.state.container.job_store


def get_extraction_store(request: Request) -> ExtractionStore:
    return request.app.state.container.extraction_store


def get_research_map_store(request: Request) -> ResearchMapStore:
    return request.app.state.container.research_map_store


def get_job_runner_factory(request: Request) -> Callable[[], ResearchMapJobRunner] | None:
    return request.app.state.container.job_runner_factory


def get_job_creation_lock(request: Request) -> threading.Lock:
    return request.app.state.container.job_creation_lock


def get_paper_id_factory(request: Request) -> Callable[[], str]:
    return request.app.state.container.paper_id_factory


def get_creator_pack_store(request: Request) -> CreatorPackStore:
    store = request.app.state.container.creator_pack_store
    if store is None:
        raise RuntimeError("Creator pack storage is not configured")
    return store


def get_creator_pack_service(request: Request) -> CreatorPackService:
    service = request.app.state.container.creator_pack_service
    if service is None:
        raise RuntimeError("Creator pack service is not configured")
    return service
