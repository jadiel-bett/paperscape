"""Persistence for reviewed creator packs."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from pydantic import ValidationError

from app.database import get_connection
from app.models.creator_pack import CreatorPack
from app.repositories.errors import CorruptRecordError, PersistenceError


class CreatorPackStore:
    def __init__(self, db_path: str, *, connection_factory: Callable[[str], sqlite3.Connection] = get_connection) -> None:
        self._db_path = db_path
        self._connection_factory = connection_factory

    def save(self, pack: CreatorPack, *, conn: sqlite3.Connection | None = None) -> None:
        owns = conn is None
        if owns:
            conn = self._connection_factory(self._db_path)
            conn.execute("BEGIN")
        try:
            conn.execute(
                """INSERT INTO creator_packs (pack_id, paper_id, audience, status, pack_json)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(pack_id) DO UPDATE SET status=excluded.status, pack_json=excluded.pack_json""",
                (pack.pack_id, pack.paper_id, pack.audience.value, pack.status.value, pack.model_dump_json()),
            )
            if owns:
                conn.execute("COMMIT")
        except sqlite3.Error as exc:
            if owns:
                conn.execute("ROLLBACK")
            raise PersistenceError("Failed to save creator pack.") from exc
        finally:
            if owns:
                conn.close()

    def get(self, pack_id: str, *, conn: sqlite3.Connection | None = None) -> CreatorPack | None:
        owns = conn is None
        if owns:
            conn = self._connection_factory(self._db_path)
        try:
            row = conn.execute("SELECT pack_json FROM creator_packs WHERE pack_id = ?", (pack_id,)).fetchone()
            if row is None:
                return None
            try:
                return CreatorPack.model_validate_json(row["pack_json"])
            except (ValueError, ValidationError) as exc:
                raise CorruptRecordError("Creator pack record is corrupt.") from exc
        except sqlite3.Error as exc:
            raise PersistenceError("Failed to retrieve creator pack.") from exc
        finally:
            if owns:
                conn.close()

    def list_for_paper(self, paper_id: str, *, conn: sqlite3.Connection | None = None) -> list[CreatorPack]:
        owns = conn is None
        if owns:
            conn = self._connection_factory(self._db_path)
        try:
            rows = conn.execute("SELECT pack_json FROM creator_packs WHERE paper_id = ? ORDER BY pack_id", (paper_id,)).fetchall()
            result = []
            for row in rows:
                try:
                    result.append(CreatorPack.model_validate_json(row["pack_json"]))
                except (ValueError, ValidationError) as exc:
                    raise CorruptRecordError("Creator pack record is corrupt.") from exc
            return result
        except sqlite3.Error as exc:
            raise PersistenceError("Failed to list creator packs.") from exc
        finally:
            if owns:
                conn.close()

