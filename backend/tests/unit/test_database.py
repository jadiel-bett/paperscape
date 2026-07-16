from __future__ import annotations

import sqlite3

import pytest

from app.database import get_connection, init_db


# ---------------------------------------------------------------------------
# Fixture: shared in-memory connection
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Provide a single in-memory SQLite connection for the duration of a test.

    Each call to ``sqlite3.connect(':memory:')`` creates an isolated
    database, so all database tests must share this fixture to see the
    tables created by ``init_db``.
    """
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


def test_init_db_creates_tables(conn: sqlite3.Connection) -> None:
    init_db(":memory:", conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    assert "jobs" in table_names
    assert "extractions" in table_names
    assert "research_maps" in table_names


def test_init_db_creates_paper_id_index(conn: sqlite3.Connection) -> None:
    init_db(":memory:", conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_jobs_paper_id'"
    ).fetchall()
    assert len(rows) == 1


def test_init_db_is_idempotent(conn: sqlite3.Connection) -> None:
    init_db(":memory:", conn)
    init_db(":memory:", conn)  # should not raise
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    assert {"jobs", "extractions", "research_maps"} <= table_names


# ---------------------------------------------------------------------------
# Stale-job reset
# ---------------------------------------------------------------------------


def test_init_db_resets_stale_running_jobs(conn: sqlite3.Connection) -> None:
    # Create schema on first call
    init_db(":memory:", conn)

    # Insert a running job and a pending job
    conn.execute(
        """
        INSERT INTO jobs (job_id, paper_id, status, created_at, updated_at)
        VALUES ('j-running', 'p1', 'running', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """
    )
    conn.execute(
        """
        INSERT INTO jobs (job_id, paper_id, status, created_at, updated_at)
        VALUES ('j-pending', 'p1', 'pending', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
        """
    )
    conn.commit()

    # Simulate a server restart by calling init_db again
    init_db(":memory:", conn)

    running = conn.execute(
        "SELECT status, error FROM jobs WHERE job_id = 'j-running'"
    ).fetchone()
    pending = conn.execute(
        "SELECT status FROM jobs WHERE job_id = 'j-pending'"
    ).fetchone()

    assert running["status"] == "failed"
    assert running["error"] is not None
    assert pending["status"] == "pending"


# ---------------------------------------------------------------------------
# Connection ownership: caller-supplied conn must never be closed
# ---------------------------------------------------------------------------


def test_init_db_does_not_close_caller_connection(conn: sqlite3.Connection) -> None:
    init_db(":memory:", conn)
    # If init_db had closed conn this execute would raise ProgrammingError
    result = conn.execute("SELECT 1 AS val").fetchone()
    assert result["val"] == 1


# ---------------------------------------------------------------------------
# get_connection
# ---------------------------------------------------------------------------


def test_get_connection_sets_row_factory() -> None:
    c = get_connection(":memory:")
    try:
        row = c.execute("SELECT 1 AS val").fetchone()
        assert row["val"] == 1
    finally:
        c.close()


def test_wal_mode_not_set_for_memory() -> None:
    c = get_connection(":memory:")
    try:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "memory"
    finally:
        c.close()
