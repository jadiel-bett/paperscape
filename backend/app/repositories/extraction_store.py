"""Extraction persistence.

Provides :class:`ExtractionStore`, which manages the ``extractions`` SQLite
table.  No FastAPI, HTTP, or watsonx imports exist anywhere in this module.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable

from pydantic import TypeAdapter, ValidationError

from app.database import get_connection
from app.models.paper import Chunk, ExtractionResult
from app.repositories.errors import CorruptRecordError, PersistenceError, RecordNotFoundError

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Serialization adapter — stores only list[Chunk] in chunks_json
# ---------------------------------------------------------------------------

_CHUNKS_ADAPTER: TypeAdapter[list[Chunk]] = TypeAdapter(list[Chunk])

# ---------------------------------------------------------------------------
# Input validation helper
# ---------------------------------------------------------------------------


def _validate_nonblank(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}.")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be blank.")
    return stripped


# ---------------------------------------------------------------------------
# ExtractionStore
# ---------------------------------------------------------------------------


class ExtractionStore:
    """Persist and retrieve :class:`ExtractionResult` records.

    Parameters
    ----------
    db_path:
        SQLite database path (``":memory:"`` or filesystem path).
    connection_factory:
        Callable that returns a new :class:`sqlite3.Connection` for *db_path*.
        Defaults to :func:`get_connection` from ``app.database``.
    """

    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
    ) -> None:
        self._db_path = db_path
        self._connection_factory = connection_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        extraction: ExtractionResult,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Atomically save or replace the extraction for its ``paper_id``.

        Only the chunk list is stored in ``chunks_json``.  The ``paper_id``
        and ``filename`` come from the row columns, **not** from the JSON.
        """
        _paper_id = _validate_nonblank(extraction.paper_id, "paper_id")

        chunks_json = _CHUNKS_ADAPTER.dump_json(extraction.chunks).decode("utf-8")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)
            conn.execute("BEGIN")

        try:
            conn.execute(
                """INSERT INTO extractions (paper_id, filename, chunks_json)
                   VALUES (?, ?, ?)
                   ON CONFLICT(paper_id) DO UPDATE SET
                       filename = excluded.filename,
                       chunks_json = excluded.chunks_json""",
                (_paper_id, extraction.filename, chunks_json),
            )

            if _owns:
                conn.execute("COMMIT")

            _log.debug("Saved extraction for paper_id=%r.", _paper_id)
        except sqlite3.Error as exc:
            if _owns:
                conn.execute("ROLLBACK")
            raise PersistenceError(
                f"Failed to save extraction for paper_id={_paper_id!r}."
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
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ExtractionResult | None:
        """Return the extraction, or ``None`` if not found."""
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT * FROM extractions WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                return None

            return self._row_to_extraction(row)
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to retrieve extraction for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    def require(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ExtractionResult:
        """Return the extraction, or raise :class:`RecordNotFoundError`."""
        extraction = self.get(paper_id, conn=conn)
        if extraction is None:
            raise RecordNotFoundError(f"Extraction for paper_id={paper_id!r} not found.")
        return extraction

    def exists(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Return ``True`` if an extraction exists for *paper_id*."""
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT 1 FROM extractions WHERE paper_id = ? LIMIT 1", (paper_id,)
            ).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to check extraction existence for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_extraction(row: sqlite3.Row) -> ExtractionResult:
        """Convert an ``extractions`` row to an :class:`ExtractionResult`.

        Raises
        ------
        CorruptRecordError
            If the stored ``chunks_json`` is malformed or does not deserialise
            to a valid ``list[Chunk]``.
        """
        try:
            chunks = _CHUNKS_ADAPTER.validate_json(row["chunks_json"])
        except (json.JSONDecodeError, ValidationError) as exc:
            raise CorruptRecordError(
                f"Extraction for paper_id={row['paper_id']!r} contains "
                f"corrupt chunks_json."
            ) from exc

        return ExtractionResult(
            paper_id=row["paper_id"],
            filename=row["filename"],
            chunks=chunks,
        )