"""Job lifecycle persistence.

Provides :class:`JobStore`, which manages the ``jobs`` SQLite table with
strict atomic transitions.  No FastAPI, HTTP, or watsonx imports exist
anywhere in this module.
"""
from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import ValidationError

from app.database import get_connection
from app.models.job import Job, JobStatus
from app.repositories.errors import (
    CorruptRecordError,
    InvalidJobTransitionError,
    PersistenceError,
    RecordNotFoundError,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Valid source-status values for each transition.  A set containing the
# *single* accepted source status, or all source statuses the transition
# accepts (``mark_failed`` accepts both pending and running).
_TRANSITION_SOURCES: dict[str, frozenset[JobStatus]] = {
    "running": frozenset({JobStatus.PENDING}),
    "succeeded": frozenset({JobStatus.RUNNING}),
    "failed": frozenset({JobStatus.PENDING, JobStatus.RUNNING}),
}

# ---------------------------------------------------------------------------
# Default helpers (injectable)
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------


def _validate_nonblank(value: str, name: str) -> str:
    """Strip *value* and return it; raise ``ValueError`` if blank."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}.")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be blank.")
    return stripped


def _validate_error_code(code: str) -> str:
    """Validate *code* matches ``^[a-z][a-z0-9_]{{0,63}}$``."""
    if not isinstance(code, str) or not _ERROR_CODE_PATTERN.match(code):
        raise ValueError(
            f"error_code must match pattern '^[a-z][a-z0-9_]{{0,63}}$'; got {code!r}."
        )
    return code


# ---------------------------------------------------------------------------
# Row → Job helper (safe conversion with CorruptRecordError)
# ---------------------------------------------------------------------------


def _row_to_job(row: sqlite3.Row) -> Job:
    """Convert a ``jobs`` row into a :class:`Job`.

    Raises
    ------
    CorruptRecordError
        If the stored ``status``, ``created_at``, or ``updated_at`` value
        cannot be parsed or does not pass model validation.
    """
    try:
        return Job(
            job_id=row["job_id"],
            paper_id=row["paper_id"],
            status=JobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error=row["error"],
        )
    except (ValueError, TypeError, ValidationError) as exc:
        raise CorruptRecordError(
            f"Stored job {row['job_id']!r} is corrupt."
        ) from exc


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------


class JobStore:
    """Persist and transition background-job records.

    Parameters
    ----------
    db_path:
        SQLite database path (``":memory:"`` or filesystem path).
    connection_factory:
        Callable that returns a new :class:`sqlite3.Connection` for *db_path*.
        Defaults to :func:`get_connection` from ``app.database``.
    clock:
        Callable that returns the current UTC :class:`datetime`.
        Called **once** per ``create()`` and once per transition.
    uuid_factory:
        Callable that returns a unique ``str`` identifier.
        Called once per ``create()``.
    """

    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], str] = _new_uuid,
    ) -> None:
        self._db_path = db_path
        self._connection_factory = connection_factory
        self._clock = clock
        self._uuid_factory = uuid_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Create a ``pending`` job for *paper_id*.

        The clock is called **once** — ``created_at`` and ``updated_at``
        share the same value.
        """
        paper_id = _validate_nonblank(paper_id, "paper_id")

        job_id = self._uuid_factory()
        if not isinstance(job_id, str) or not job_id.strip():
            raise PersistenceError("uuid_factory returned an empty or invalid identifier.")

        now = self._clock()
        created_at_str = now.isoformat()
        updated_at_str = now.isoformat()

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)
            conn.execute("BEGIN")

        try:
            conn.execute(
                """INSERT INTO jobs (job_id, paper_id, status, created_at, updated_at)
                   VALUES (?, ?, 'pending', ?, ?)""",
                (job_id, paper_id, created_at_str, updated_at_str),
            )

            if _owns:
                conn.execute("COMMIT")

            _log.debug("Created pending job %r for paper_id=%r.", job_id, paper_id)
            return Job(
                job_id=job_id,
                paper_id=paper_id,
                status=JobStatus.PENDING,
                created_at=now,
                updated_at=now,
                error=None,
            )
        except sqlite3.Error as exc:
            if _owns:
                conn.execute("ROLLBACK")
            raise PersistenceError(
                f"Failed to create job for paper_id={paper_id!r}."
            ) from exc
        except (ValueError, PersistenceError):
            if _owns:
                conn.execute("ROLLBACK")
            raise
        finally:
            if _owns:
                conn.close()

    def get(
        self,
        job_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job | None:
        """Return the job, or ``None`` if not found."""
        job_id = _validate_nonblank(job_id, "job_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return _row_to_job(row) if row is not None else None
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to retrieve job {job_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    def require(
        self,
        job_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Return the job, or raise :class:`RecordNotFoundError`."""
        job = self.get(job_id, conn=conn)
        if job is None:
            raise RecordNotFoundError(f"Job {job_id!r} not found.")
        return job

    def mark_running(
        self,
        job_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Atomically transition ``pending`` → ``running``.

        Raises
        ------
        RecordNotFoundError
            If *job_id* does not exist.
        InvalidJobTransitionError
            If the job is not in ``pending`` status.
        """
        return self._transition(job_id, JobStatus.RUNNING, conn=conn)

    def mark_succeeded(
        self,
        job_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Atomically transition ``running`` → ``succeeded``.

        Raises
        ------
        RecordNotFoundError
            If *job_id* does not exist.
        InvalidJobTransitionError
            If the job is not in ``running`` status.
        """
        return self._transition(job_id, JobStatus.SUCCEEDED, conn=conn)

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Atomically transition ``pending`` or ``running`` → ``failed``.

        Stores only the validated *error_code* in the ``error`` column.
        The *error_code* must match ``^[a-z][a-z0-9_]{{0,63}}$``.

        Raises
        ------
        ValueError
            If *error_code* is invalid.
        RecordNotFoundError
            If *job_id* does not exist.
        InvalidJobTransitionError
            If the job is already in a terminal state.
        """
        error_code = _validate_error_code(error_code)
        return self._transition(job_id, JobStatus.FAILED, error_code=error_code, conn=conn)

    def get_active_job_for_paper(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> Job | None:
        """Return the latest ``pending`` or ``running`` job for *paper_id*.

        Deterministic tie-break: ``ORDER BY created_at DESC, job_id DESC``.
        Returns ``None`` when no active job exists.

        .. note::
           The current schema does **not** enforce at most one active job per
           paper.  Orchestration code should call this method before creating
           a new job.
        """
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                """SELECT * FROM jobs
                   WHERE paper_id = ? AND status IN ('pending', 'running')
                   ORDER BY created_at DESC, job_id DESC
                   LIMIT 1""",
                (paper_id,),
            ).fetchone()
            return _row_to_job(row) if row is not None else None
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to query active job for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    def has_completed_job_for_paper(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Return ``True`` if a ``succeeded`` job exists for *paper_id*."""
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE paper_id = ? AND status = 'succeeded' LIMIT 1",
                (paper_id,),
            ).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to check completed job for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition(
        self,
        job_id: str,
        target: JobStatus,
        *,
        error_code: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> Job:
        """Perform an atomic status transition.  See public methods."""
        job_id = _validate_nonblank(job_id, "job_id")
        target_str = target.value

        valid_sources = _TRANSITION_SOURCES.get(target_str)
        if valid_sources is None:
            raise ValueError(f"Unknown target status {target_str!r}.")

        now = self._clock()
        updated_at_str = now.isoformat()

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)
            conn.execute("BEGIN")

        try:
            if target == JobStatus.FAILED:
                # pending or running → failed
                source_statuses = tuple(
                    s.value for s in sorted(valid_sources, key=lambda x: x.value)
                )
                placeholders = ", ".join("?" for _ in source_statuses)
                sql = (
                    f"UPDATE jobs SET status = 'failed', error = ?, updated_at = ? "
                    f"WHERE job_id = ? AND status IN ({placeholders})"
                )
                cursor = conn.execute(
                    sql, (error_code, updated_at_str, job_id, *source_statuses)
                )
            else:
                # Single-source transition: pending → running, running → succeeded
                source_str = next(iter(valid_sources)).value
                sql = (
                    f"UPDATE jobs SET status = ?, updated_at = ? "
                    f"WHERE job_id = ? AND status = ?"
                )
                cursor = conn.execute(sql, (target_str, updated_at_str, job_id, source_str))

            if cursor.rowcount == 1:
                if _owns:
                    conn.execute("COMMIT")

                # Re-read the updated row to build a complete Job.
                row = conn.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    # Should never happen after a successful UPDATE, but guard.
                    raise PersistenceError(
                        f"Job {job_id!r} disappeared after successful transition."
                    )
                result = _row_to_job(row)

                _log.info(
                    "Job %r transitioned → %s.", job_id, target_str,
                )
                return result

            # Zero rows affected → determine why.
            row = conn.execute(
                "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()

            if _owns:
                conn.execute("ROLLBACK")

            if row is None:
                raise RecordNotFoundError(f"Job {job_id!r} not found.")

            current_status = row["status"]
            raise InvalidJobTransitionError(
                f"Cannot transition job {job_id!r} from {current_status!r} "
                f"to {target_str!r}."
            )

        except (RecordNotFoundError, InvalidJobTransitionError, ValueError):
            # Do not wrap domain exceptions.
            if _owns:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise
        except sqlite3.Error as exc:
            if _owns:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            raise PersistenceError(
                f"Failed to transition job {job_id!r} to {target_str!r}."
            ) from exc
        finally:
            if _owns:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass