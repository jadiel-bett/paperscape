from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

_log = logging.getLogger(__name__)


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and configure it for use in PaperScape.

    - Sets ``row_factory = sqlite3.Row`` so column values are accessible by name.
    - Enables ``PRAGMA foreign_keys = ON`` on every connection.
    - Enables WAL journal mode for file-backed databases; WAL is intentionally
      skipped for ``:memory:`` databases where it has no effect.

    The caller is responsible for closing the returned connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if db_path != ":memory:":
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        actual_mode = result[0] if result is not None else "unknown"
        if actual_mode != "wal":
            _log.warning(
                "SQLite WAL mode requested but current journal_mode is %r "
                "(db_path=%r). Write concurrency may be reduced.",
                actual_mode,
                db_path,
            )
    return conn


def init_db(
    db_path: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Initialise the database schema and reset any stale jobs.

    Creates the ``jobs``, ``extractions``, ``research_maps``, and
    ``research_map_metadata`` tables
    (idempotent — uses ``CREATE TABLE IF NOT EXISTS``).

    FastAPI ``BackgroundTasks`` are in-process and not durable.  Any jobs
    that were left in ``pending`` or ``running`` state by a previous process
    crash are reset to ``failed`` with ``error = 'server_restart'`` so the
    system never serves stale in-progress state.

    Transaction behaviour
    ---------------------
    All DDL and the stale-reset DML run inside a single explicit transaction
    that is committed on success or rolled back on any exception before the
    exception is re-raised.  SQLite supports transactional DDL so both schema
    changes and the stale-reset update are atomic.

    Connection ownership
    --------------------
    - If *conn* is ``None``, a new connection is opened internally and closed
      (after commit or rollback) before this function returns.
    - If a *conn* is supplied by the caller it is used as-is and is **never
      closed** here — ownership stays with the caller.  This supports test
      fixtures that share a single ``:memory:`` connection.
    """
    _owns_conn = conn is None
    if _owns_conn:
        conn = get_connection(db_path)

    try:
        conn.execute("BEGIN")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT NOT NULL PRIMARY KEY,
                paper_id   TEXT NOT NULL,
                status     TEXT NOT NULL
                           CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error      TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_jobs_paper_id ON jobs (paper_id)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extractions (
                paper_id    TEXT NOT NULL PRIMARY KEY,
                filename    TEXT NOT NULL,
                chunks_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_maps (
                paper_id TEXT NOT NULL PRIMARY KEY,
                map_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS creator_packs (
                pack_id  TEXT NOT NULL PRIMARY KEY,
                paper_id TEXT NOT NULL,
                audience TEXT NOT NULL,
                status   TEXT NOT NULL CHECK (status IN ('draft', 'approved')),
                pack_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_creator_packs_paper_id ON creator_packs (paper_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_map_metadata (
                paper_id        TEXT NOT NULL PRIMARY KEY,
                generation_mode TEXT NOT NULL
                                CHECK (
                                    generation_mode IN (
                                        'granite',
                                        'deterministic_extractive_fallback'
                                    )
                                ),
                fallback_reason TEXT
                                CHECK (
                                    fallback_reason IS NULL
                                    OR fallback_reason = 'llm_provider_error'
                                ),
                generated_at    TEXT NOT NULL,
                FOREIGN KEY (paper_id)
                    REFERENCES research_maps(paper_id) ON DELETE CASCADE
            )
            """
        )

        # Reset jobs that were pending or running when the previous process
        # died.  BackgroundTasks are not durable, so pending jobs cannot
        # safely survive an application restart.
        conn.execute(
            """
            UPDATE jobs
               SET status     = 'failed',
                    error      = 'server_restart',
                    updated_at = ?
             WHERE status IN ('pending', 'running')
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )

        conn.execute("COMMIT")
        _log.info("Database initialised at %r.", db_path)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        if _owns_conn:
            conn.close()
