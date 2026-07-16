from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and configure it for use in PaperScape.

    Sets ``row_factory = sqlite3.Row`` so that column values can be
    accessed by name.  Enables WAL journal mode for file-based databases;
    WAL is skipped for ``:memory:`` databases where it has no effect.

    The caller is responsible for closing the returned connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(
    db_path: str,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Initialise the database schema and reset any stale running jobs.

    Creates the ``jobs``, ``extractions``, and ``research_maps`` tables
    (idempotent — uses ``CREATE TABLE IF NOT EXISTS``).

    Any jobs that were left in ``running`` state by a previous process
    crash are reset to ``failed`` so the system never serves stale state.

    Connection ownership
    --------------------
    - If *conn* is ``None``, a new connection is opened internally and
      closed before this function returns.
    - If a *conn* is supplied by the caller it is used as-is and is
      **never closed** here — ownership stays with the caller.  This
      supports test fixtures that share a single ``:memory:`` connection.
    """
    _owns_conn = conn is None
    if _owns_conn:
        conn = get_connection(db_path)

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT NOT NULL PRIMARY KEY,
                paper_id   TEXT NOT NULL,
                status     TEXT NOT NULL,
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

        # Reset jobs that were running when the previous process died.
        conn.execute(
            """
            UPDATE jobs
               SET status     = 'failed',
                   error      = 'Reset by server restart',
                   updated_at = ?
             WHERE status = 'running'
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )

        conn.commit()
    finally:
        if _owns_conn:
            conn.close()
