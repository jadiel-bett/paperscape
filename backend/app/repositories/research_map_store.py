"""Research map persistence.

Provides :class:`ResearchMapStore`, which manages the ``research_maps`` SQLite
table.  No FastAPI, HTTP, or watsonx imports exist anywhere in this module.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from pydantic import ValidationError

from app.database import get_connection
from app.models.research_map import ResearchMap
from app.repositories.errors import CorruptRecordError, PersistenceError, RecordNotFoundError

_log = logging.getLogger(__name__)
_SAVEPOINT_NAME = "research_map_store_save"


class GenerationMode(str, Enum):
    """Internal label for the path that produced a persisted research map."""

    GRANITE = "granite"
    DETERMINISTIC_EXTRACTIVE_FALLBACK = "deterministic_extractive_fallback"


@dataclass(frozen=True)
class ResearchMapGenerationMetadata:
    """Internal persistence metadata; never part of public API schemas.

    ``generated_at`` is ``None`` only for a legacy ``research_maps`` row that
    predates the metadata table/feature. Such a row is treated as Granite
    output for backward compatibility.
    """

    paper_id: str
    generation_mode: GenerationMode
    fallback_reason: str | None
    generated_at: str | None

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
# ResearchMapStore
# ---------------------------------------------------------------------------


class ResearchMapStore:
    """Persist and retrieve :class:`ResearchMap` records.

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
        research_map: ResearchMap,
        *,
        generation_mode: GenerationMode = GenerationMode.GRANITE,
        fallback_reason: str | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Atomically save or replace a map and its internal metadata.

        The complete :class:`ResearchMap` is stored as JSON in ``map_json``.
        """
        _paper_id = _validate_nonblank(research_map.paper_id, "paper_id")
        self._validate_generation_metadata(generation_mode, fallback_reason)

        map_json = research_map.model_dump_json()
        generated_at = datetime.now(timezone.utc).isoformat()

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        _savepoint_active = False
        try:
            if _owns:
                conn.execute("BEGIN")
            else:
                # A caller-owned connection keeps control of the outer
                # transaction. If none exists yet, start one and deliberately
                # leave it open for the caller.
                if not conn.in_transaction:
                    conn.execute("BEGIN")
                conn.execute(f"SAVEPOINT {_SAVEPOINT_NAME}")
                _savepoint_active = True

            conn.execute(
                """INSERT INTO research_maps (paper_id, map_json)
                   VALUES (?, ?)
                   ON CONFLICT(paper_id) DO UPDATE SET
                       map_json = excluded.map_json""",
                (_paper_id, map_json),
            )
            conn.execute(
                """INSERT INTO research_map_metadata (
                       paper_id, generation_mode, fallback_reason, generated_at
                   )
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(paper_id) DO UPDATE SET
                       generation_mode = excluded.generation_mode,
                       fallback_reason = excluded.fallback_reason,
                       generated_at = excluded.generated_at""",
                (
                    _paper_id,
                    generation_mode.value,
                    fallback_reason,
                    generated_at,
                ),
            )

            if _owns:
                conn.execute("COMMIT")
            else:
                conn.execute(f"RELEASE SAVEPOINT {_SAVEPOINT_NAME}")
                _savepoint_active = False

            _log.debug("Saved research map for paper_id=%r.", _paper_id)
        except sqlite3.Error as exc:
            if _owns:
                conn.execute("ROLLBACK")
            elif _savepoint_active:
                self._rollback_savepoint(conn)
            raise PersistenceError(
                f"Failed to save research map for paper_id={_paper_id!r}."
            ) from exc
        except (ValueError, PersistenceError):
            if _owns:
                conn.execute("ROLLBACK")
            elif _savepoint_active:
                self._rollback_savepoint(conn)
            raise
        finally:
            if _owns:
                conn.close()

    def get(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ResearchMap | None:
        """Return the research map, or ``None`` if not found."""
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT * FROM research_maps WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if row is None:
                return None

            return self._row_to_research_map(row)
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to retrieve research map for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    def require(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ResearchMap:
        """Return the research map, or raise :class:`RecordNotFoundError`."""
        rm = self.get(paper_id, conn=conn)
        if rm is None:
            raise RecordNotFoundError(
                f"Research map for paper_id={paper_id!r} not found."
            )
        return rm

    def exists(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> bool:
        """Return ``True`` if a research map exists for *paper_id*."""
        paper_id = _validate_nonblank(paper_id, "paper_id")

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            row = conn.execute(
                "SELECT 1 FROM research_maps WHERE paper_id = ? LIMIT 1", (paper_id,)
            ).fetchone()
            return row is not None
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to check research map existence for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    def get_generation_metadata(
        self,
        paper_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ResearchMapGenerationMetadata | None:
        """Return internal generation metadata for an existing map.

        Legacy map rows without metadata are reported as Granite with a
        ``None`` timestamp. No generation metadata is exposed by API routes.
        """
        paper_id = _validate_nonblank(paper_id, "paper_id")
        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)

        try:
            map_row = conn.execute(
                "SELECT 1 FROM research_maps WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if map_row is None:
                return None

            row = conn.execute(
                """SELECT paper_id, generation_mode, fallback_reason, generated_at
                     FROM research_map_metadata
                    WHERE paper_id = ?""",
                (paper_id,),
            ).fetchone()
            if row is None:
                return ResearchMapGenerationMetadata(
                    paper_id=paper_id,
                    generation_mode=GenerationMode.GRANITE,
                    fallback_reason=None,
                    generated_at=None,
                )

            try:
                mode = GenerationMode(row["generation_mode"])
                self._validate_generation_metadata(mode, row["fallback_reason"])
                generated_at = row["generated_at"]
                parsed_at = datetime.fromisoformat(generated_at)
                if parsed_at.tzinfo is None:
                    raise ValueError("generated_at must include a timezone")
            except (TypeError, ValueError) as exc:
                raise CorruptRecordError(
                    f"Generation metadata for paper_id={paper_id!r} is corrupt."
                ) from exc

            return ResearchMapGenerationMetadata(
                paper_id=row["paper_id"],
                generation_mode=mode,
                fallback_reason=row["fallback_reason"],
                generated_at=generated_at,
            )
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"Failed to retrieve generation metadata for paper_id={paper_id!r}."
            ) from exc
        finally:
            if _owns:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rollback_savepoint(conn: sqlite3.Connection) -> None:
        """Undo this repository's writes without ending the caller transaction."""
        conn.execute(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT_NAME}")
        conn.execute(f"RELEASE SAVEPOINT {_SAVEPOINT_NAME}")

    @staticmethod
    def _validate_generation_metadata(
        generation_mode: GenerationMode,
        fallback_reason: str | None,
    ) -> None:
        if not isinstance(generation_mode, GenerationMode):
            raise ValueError("generation_mode must be a GenerationMode value.")
        if generation_mode is GenerationMode.GRANITE and fallback_reason is not None:
            raise ValueError("Granite generation requires fallback_reason=None.")
        if (
            generation_mode is GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK
            and fallback_reason != "llm_provider_error"
        ):
            raise ValueError(
                "Deterministic fallback generation requires "
                "fallback_reason='llm_provider_error'."
            )

    @staticmethod
    def _row_to_research_map(row: sqlite3.Row) -> ResearchMap:
        """Convert a ``research_maps`` row to a :class:`ResearchMap`.

        Raises
        ------
        CorruptRecordError
            If the stored ``map_json`` is malformed, schema-invalid, or the
            decoded ``paper_id`` does not match the row's ``paper_id``.
        """
        try:
            research_map = ResearchMap.model_validate_json(row["map_json"])
        except (json.JSONDecodeError, ValidationError) as exc:
            raise CorruptRecordError(
                f"Research map for paper_id={row['paper_id']!r} contains "
                f"corrupt map_json."
            ) from exc

        if research_map.paper_id != row["paper_id"]:
            raise CorruptRecordError(
                f"Research map paper_id {research_map.paper_id!r} does not match "
                f"row paper_id {row['paper_id']!r}."
            )

        return research_map
