"""Research map persistence.

Provides :class:`ResearchMapStore`, which manages the ``research_maps`` SQLite
table.  No FastAPI, HTTP, or watsonx imports exist anywhere in this module.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable

from pydantic import ValidationError

from app.database import get_connection
from app.models.research_map import ResearchMap
from app.repositories.errors import CorruptRecordError, PersistenceError, RecordNotFoundError

_log = logging.getLogger(__name__)

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
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Atomically save or replace the research map for its ``paper_id``.

        The complete :class:`ResearchMap` is stored as JSON in ``map_json``.
        """
        _paper_id = _validate_nonblank(research_map.paper_id, "paper_id")

        map_json = research_map.model_dump_json()

        _owns = conn is None
        if _owns:
            conn = self._connection_factory(self._db_path)
            conn.execute("BEGIN")

        try:
            conn.execute(
                """INSERT INTO research_maps (paper_id, map_json)
                   VALUES (?, ?)
                   ON CONFLICT(paper_id) DO UPDATE SET
                       map_json = excluded.map_json""",
                (_paper_id, map_json),
            )

            if _owns:
                conn.execute("COMMIT")

            _log.debug("Saved research map for paper_id=%r.", _paper_id)
        except sqlite3.Error as exc:
            if _owns:
                conn.execute("ROLLBACK")
            raise PersistenceError(
                f"Failed to save research map for paper_id={_paper_id!r}."
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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