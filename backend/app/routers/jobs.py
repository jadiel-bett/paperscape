"""Job status polling route.

Registered under ``/api/v1/jobs``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import AppException, get_job_store
from app.models.job import JobStatusResponse
from app.repositories.errors import PersistenceError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    job_store=Depends(get_job_store),
) -> JobStatusResponse:
    """Return the current status of a background job."""
    job_id = job_id.strip()
    if not job_id:
        raise AppException(
            400, "invalid_identifier", "Job identifier must not be blank."
        )

    try:
        job = job_store.get(job_id)
    except PersistenceError as exc:
        raise AppException(
            500, "persistence_error", "A storage error occurred. Please try again.",
        ) from exc

    if job is None:
        raise AppException(
            404,
            "job_not_found",
            "No job was found for this identifier.",
        )

    return JobStatusResponse(
        job_id=job.job_id,
        paper_id=job.paper_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
    )