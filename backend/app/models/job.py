from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel


class JobStatus(str, enum.Enum):
    """Valid states for a background processing job.

    Transitions: pending → running → succeeded
                                   ↘ failed
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
