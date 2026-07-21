from __future__ import annotations

import enum
from datetime import datetime, timezone, timedelta

from pydantic import BaseModel, field_validator


class JobStatus(enum.StrEnum):
    """Valid states for a background processing job.

    Transitions: pending → running → succeeded
                                    ↘ failed

    Implemented as ``enum.StrEnum`` (Python 3.11+) so that values compare
    equal to plain strings and serialise to bare strings in JSON without a
    custom encoder.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(BaseModel):
    """Persisted job record stored in the jobs SQLite table."""

    job_id: str
    paper_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: str | None = None

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def _require_utc_aware(cls, v: datetime) -> datetime:
        """Reject naive or non-UTC timestamps.

        The repository always writes ``datetime.now(timezone.utc)``, so
        any loaded timestamp that is naive or has a non-zero UTC offset
        indicates a storage or programming error.
        """
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware.")
        if v.utcoffset() != timedelta():
            raise ValueError("Timestamp must be UTC.")
        return v


class JobCreateResponse(BaseModel):
    """JSON body returned by POST /api/v1/papers/{paper_id}/research-map-jobs."""

    job_id: str
    paper_id: str
    status: JobStatus


class JobStatusResponse(Job):
    """JSON body returned by GET /api/v1/jobs/{job_id}.

    Inherits all fields from Job. The two models are intentionally kept as
    one today; they can be separated if their API contracts diverge.
    """

    pass
