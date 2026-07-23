"""Paper upload, research-map job creation, and research-map retrieval routes.

All endpoints are registered under ``/api/v1/papers``.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from starlette.concurrency import run_in_threadpool

from app.dependencies import (
    AppException,
    ServiceContainer,
    get_container,
    get_extraction_service,
    get_extraction_store,
    get_job_creation_lock,
    get_job_runner_factory,
    get_job_store,
    get_paper_id_factory,
    get_research_map_store,
    get_settings,
    run_research_map_job,
)
from app.models.paper import UploadResponse
from app.models.job import JobCreateResponse, JobStatus
from app.repositories.errors import PersistenceError
from app.services.extraction import ExtractionError, ExtractionService

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.config import Settings
    from app.repositories import ExtractionStore, JobStore, ResearchMapStore
    from app.services.research_map_job_runner import ResearchMapJobRunner

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/papers", tags=["papers"])

# ---------------------------------------------------------------------------
# Shared upload helper
# ---------------------------------------------------------------------------

_UPLOAD_PDF_SIGNATURE = b"%PDF-"
_PAPER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


async def _read_upload_limited(
    file: UploadFile,
    *,
    max_bytes: int,
) -> bytes:
    """Read at most ``max_bytes + 1`` bytes from *file*.

    Raises
    ------
    AppException
        If the file is empty (400) or exceeds *max_bytes* (413).
    """
    data = await file.read(max_bytes + 1)
    if not data:
        raise AppException(
            400, "invalid_upload", "The uploaded file is empty."
        )
    if len(data) > max_bytes:
        raise AppException(
            413,
            "upload_too_large",
            f"The uploaded file exceeds the maximum allowed size "
            f"({max_bytes} bytes).",
        )
    return data


def _validate_generated_paper_id(value: object) -> str:
    """Validate an application-generated paper ID before extraction."""
    if not isinstance(value, str):
        raise AppException(
            500,
            "internal_error",
            "An internal identifier could not be generated. Please try again.",
        )
    if not _PAPER_ID_PATTERN.fullmatch(value):
        raise AppException(
            500,
            "internal_error",
            "An internal identifier could not be generated. Please try again.",
        )
    return value


# ---------------------------------------------------------------------------
# POST /api/v1/papers — Upload and extract
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def upload_paper(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
    extraction_service: ExtractionService = Depends(get_extraction_service),
    extraction_store: ExtractionStore = Depends(get_extraction_store),
    paper_id_factory: Callable[[], str] = Depends(get_paper_id_factory),
) -> UploadResponse:
    """Upload a PDF, extract text, and persist the extraction result."""
    try:
        # Validate filename.
        filename_raw = file.filename
        if filename_raw is None or not filename_raw.strip():
            raise AppException(
                400, "invalid_upload", "Uploaded file must have a non-blank filename."
            )
        filename = filename_raw.strip()

        # Validate file media type, not request-level multipart Content-Type.
        content_type_raw = file.content_type
        if content_type_raw is None or content_type_raw.strip().lower() != "application/pdf":
            raise AppException(
                415,
                "unsupported_media_type",
                "Only PDF files are accepted.",
            )

        # Read bytes with hard size limit.
        data = await _read_upload_limited(file, max_bytes=settings.upload_max_bytes)

        # Optional lightweight PDF signature check within first 1,024 bytes.
        if _UPLOAD_PDF_SIGNATURE not in data[:1024]:
            raise AppException(
                400,
                "upload_not_a_pdf",
                "The file does not appear to be a valid PDF.",
            )

        paper_id = _validate_generated_paper_id(paper_id_factory())

        # Extract (runs in thread pool to avoid blocking the async event loop).
        try:
            extraction = await run_in_threadpool(
                extraction_service.extract,
                data,
                filename,
                paper_id,
            )
        except ValueError as exc:
            raise AppException(
                422,
                "extraction_failed",
                "The uploaded PDF could not be processed.",
            ) from exc
        except ExtractionError as exc:
            raise AppException(
                422,
                "extraction_failed",
                "No selectable text could be extracted from the PDF.",
            ) from exc

        # Persist (runs in thread pool).
        try:
            await run_in_threadpool(extraction_store.save, extraction)
        except PersistenceError as exc:
            raise AppException(
                500, "persistence_error", "A storage error occurred. Please try again.",
            ) from exc

        return UploadResponse(
            paper_id=paper_id,
            filename=filename,
            page_count=len(set(c.page for c in extraction.chunks)),
            chunk_count=len(extraction.chunks),
        )
    finally:
        await file.close()


# ---------------------------------------------------------------------------
# POST /api/v1/papers/{paper_id}/research-map-jobs — Create job
# ---------------------------------------------------------------------------


@router.post("/{paper_id}/research-map-jobs", status_code=202)
async def create_research_map_job(
    paper_id: str,
    background_tasks: BackgroundTasks,
    container: ServiceContainer = Depends(get_container),
    extraction_store: ExtractionStore = Depends(get_extraction_store),
    job_store: JobStore = Depends(get_job_store),
    job_runner_factory: Callable[[], ResearchMapJobRunner] | None = Depends(get_job_runner_factory),
    job_creation_lock: threading.Lock = Depends(get_job_creation_lock),
) -> JobCreateResponse:
    """Create a background research-map generation job.

    Returns the existing active job (202) when one exists, or creates a new
    pending job.  Returns 503 when research-map generation is unavailable
    (no watsonx credentials configured).
    """
    # Validate paper_id and confirm extraction exists.
    paper_id = paper_id.strip()
    if not paper_id:
        raise AppException(
            400, "invalid_identifier", "Paper identifier must not be blank."
        )

    try:
        if not extraction_store.exists(paper_id):
            raise AppException(
                404,
                "paper_not_found",
                "No extracted paper was found for this identifier.",
            )
    except PersistenceError as exc:
        raise AppException(
            500, "persistence_error", "A storage error occurred. Please try again.",
        ) from exc

    # Check generation availability.
    if job_runner_factory is None:
        raise AppException(
            503,
            "generation_unavailable",
            "Research-map generation is not available. "
            "Check that watsonx credentials are configured.",
        )

    # Active-job lookup and creation are protected by an in-process lock.
    with job_creation_lock:
        try:
            active = job_store.get_active_job_for_paper(paper_id)
        except PersistenceError as exc:
            raise AppException(
                500,
                "persistence_error",
                "A storage error occurred. Please try again.",
            ) from exc

        if active is not None:
            # Return the existing active job (idempotent retry).
            return JobCreateResponse(
                job_id=active.job_id,
                paper_id=active.paper_id,
                status=active.status,
            )

        try:
            job = job_store.create(paper_id)
        except PersistenceError as exc:
            raise AppException(
                500,
                "persistence_error",
                "A storage error occurred. Please try again.",
            ) from exc

    # Lock is released before scheduling the background task.
    try:
        background_tasks.add_task(run_research_map_job, container, job.job_id)
    except Exception as exc:
        _log.error(
            "Failed to schedule background task for job %r: %s",
            job.job_id,
            type(exc).__name__,
        )
        # Best-effort mark job failed.
        try:
            job_store.mark_failed(job.job_id, error_code="task_scheduling_failed")
        except Exception as mark_exc:
            _log.error(
                "Failed to mark job %r as task_scheduling_failed: %s",
                job.job_id,
                type(mark_exc).__name__,
            )
        raise AppException(
            500,
            "task_scheduling_failed",
            "The background task could not be started. Please try again.",
        ) from exc

    return JobCreateResponse(
        job_id=job.job_id,
        paper_id=job.paper_id,
        status=JobStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/papers/{paper_id}/research-map — Retrieve research map
# ---------------------------------------------------------------------------


@router.get("/{paper_id}/research-map")
async def get_research_map(
    paper_id: str,
    job_store: JobStore = Depends(get_job_store),
    research_map_store: ResearchMapStore = Depends(get_research_map_store),
) -> object:
    """Return the completed research map for *paper_id*.

    Requires the **latest** job for the paper to be ``succeeded``.  Returns
    404 when no map is available (including when an orphaned map exists
    after a failed regeneration).
    """
    paper_id = paper_id.strip()
    if not paper_id:
        raise AppException(
            400, "invalid_identifier", "Paper identifier must not be blank."
        )

    # Check the latest job.
    try:
        latest = job_store.get_latest_job_for_paper(paper_id)
    except PersistenceError as exc:
        raise AppException(
            500, "persistence_error", "A storage error occurred. Please try again.",
        ) from exc

    if latest is None or latest.status != JobStatus.SUCCEEDED:
        raise AppException(
            404,
            "map_not_found",
            "No completed research map was found for this paper.",
        )

    # Retrieve the persisted map.
    try:
        research_map = research_map_store.get(paper_id)
    except PersistenceError as exc:
        raise AppException(
            500, "persistence_error", "A storage error occurred. Please try again.",
        ) from exc

    if research_map is None:
        raise AppException(
            404,
            "map_not_found",
            "No completed research map was found for this paper.",
        )

    return research_map