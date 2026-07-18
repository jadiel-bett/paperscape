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
    database, so all database tests that inspect tables created by ``init_db``
    must use this fixture so they share the same connection.
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


def test_jobs_status_check_constraint(conn: sqlite3.Connection) -> None:
    """The CHECK constraint on jobs.status must reject unknown values."""
    init_db(":memory:", conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO jobs (job_id, paper_id, status, created_at, updated_at)
            VALUES ('j1', 'p1', 'bogus', '2024-01-01T00:00:00', '2024-01-01T00:00:00')
            """
        )
        conn.commit()


def test_foreign_keys_enabled(conn: sqlite3.Connection) -> None:
    """foreign_keys pragma must be ON for every new connection."""
    c = get_connection(":memory:")
    try:
        result = c.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1, "PRAGMA foreign_keys should be ON (1)"
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Stale-job reset — all four statuses
# ---------------------------------------------------------------------------


def test_init_db_stale_reset_all_statuses(conn: sqlite3.Connection) -> None:
    """Only running jobs become failed; pending, succeeded, failed are unchanged."""
    init_db(":memory:", conn)

    _insert = (
        "INSERT INTO jobs (job_id, paper_id, status, created_at, updated_at) "
        "VALUES (?, 'p1', ?, '2024-01-01T00:00:00', '2024-01-01T00:00:00')"
    )
    conn.execute(_insert, ("j-running", "running"))
    conn.execute(_insert, ("j-pending", "pending"))
    conn.execute(_insert, ("j-succeeded", "succeeded"))
    conn.execute(_insert, ("j-failed", "failed"))
    conn.commit()

    # Simulate a server restart
    init_db(":memory:", conn)

    def _fetch(job_id: str):
        return conn.execute(
            "SELECT status, error, updated_at FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()

    running = _fetch("j-running")
    pending = _fetch("j-pending")
    succeeded = _fetch("j-succeeded")
    failed = _fetch("j-failed")

    # running → failed
    assert running["status"] == "failed"
    assert running["error"] == "server_restart"
    assert running["updated_at"] != "2024-01-01T00:00:00", (
        "updated_at must be refreshed for the reset job"
    )

    # all others unchanged
    assert pending["status"] == "pending"
    assert pending["updated_at"] == "2024-01-01T00:00:00"

    assert succeeded["status"] == "succeeded"
    assert succeeded["updated_at"] == "2024-01-01T00:00:00"

    assert failed["status"] == "failed"
    # error column of the pre-existing failed job should remain NULL (not overwritten)
    assert failed["error"] is None
    assert failed["updated_at"] == "2024-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Connection ownership: caller-supplied conn must never be closed
# ---------------------------------------------------------------------------


def test_init_db_does_not_close_caller_connection(conn: sqlite3.Connection) -> None:
    init_db(":memory:", conn)
    # If init_db had closed conn this execute would raise ProgrammingError
    result = conn.execute("SELECT 1 AS val").fetchone()
    assert result["val"] == 1


# ---------------------------------------------------------------------------
# get_connection — row factory and WAL
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


def test_wal_mode_set_for_file_database(tmp_path: pytest.TempPathFactory) -> None:
    """WAL journal mode must be active for file-backed databases."""
    db_file = tmp_path / "wal_test.db"  # type: ignore[operator]
    c = get_connection(str(db_file))
    try:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal", f"Expected WAL mode, got {mode!r}"
    finally:
        c.close()
