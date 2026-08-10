"""Cross-repository integration tests.

Exercises caller-managed transactions across :class:`JobStore`,
:class:`ExtractionStore`, and :class:`ResearchMapStore`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.database import init_db
from app.models.job import JobStatus
from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap
from app.repositories.errors import (
    CorruptRecordError,
    InvalidJobTransitionError,
    PersistenceError,
)
from app.repositories.extraction_store import ExtractionStore
from app.repositories.job_store import JobStore
from app.repositories.research_map_store import GenerationMode, ResearchMapStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "test_integration.db"
    init_db(str(path))
    return str(path)


@pytest.fixture
def job_store(db_path: str) -> JobStore:
    return JobStore(db_path)


@pytest.fixture
def extraction_store(db_path: str) -> ExtractionStore:
    return ExtractionStore(db_path)


@pytest.fixture
def research_map_store(db_path: str) -> ResearchMapStore:
    return ResearchMapStore(db_path)


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    return ExtractionResult(
        paper_id="paper-1",
        filename="integration.pdf",
        chunks=[Chunk(chunk_id="p1-p1-1", page=1, section=None, text="Integration test.")],
    )


@pytest.fixture
def sample_research_map() -> ResearchMap:
    return ResearchMap(
        paper_id="paper-1",
        research_question="Integration question?",
        findings=[
            Finding(
                statement="Find one.",
                evidence=[Evidence(chunk_id="p1-p1-1", page=1, excerpt="Integration test.")],
                confidence="high",
            ),
            Finding(
                statement="Find two.",
                evidence=[Evidence(chunk_id="p1-p1-1", page=1, excerpt="Integration test.")],
                confidence="partial",
            ),
            Finding(
                statement="Find three.",
                evidence=[Evidence(chunk_id="p1-p1-1", page=1, excerpt="Integration test.")],
                confidence="high",
            ),
        ],
        limitations=["One limitation."],
        disclaimer="This AI-generated explanation is grounded in the uploaded document but does not replace expert review.",
    )


# ---------------------------------------------------------------------------
# Test 1: Success flow survives reopen
# ---------------------------------------------------------------------------


def test_success_flow_survives_reopen(
    db_path: str,
    sample_extraction: ExtractionResult,
    sample_research_map: ResearchMap,
) -> None:
    """Full lifecycle: create job → save extraction → mark running → save map
    → mark succeeded → close → reopen → verify all three records."""
    store = JobStore(db_path)
    ext_store = ExtractionStore(db_path)
    map_store = ResearchMapStore(db_path)

    # Full lifecycle
    job = store.create("paper-1")
    ext_store.save(sample_extraction)
    job = store.mark_running(job.job_id)
    map_store.save(sample_research_map)
    job = store.mark_succeeded(job.job_id)
    assert job.status == JobStatus.SUCCEEDED

    # Close all connections by creating fresh stores (old ones release their
    # repository-owned connections automatically).

    # Reopen with fresh store instances
    fresh_job_store = JobStore(db_path)
    fresh_ext_store = ExtractionStore(db_path)
    fresh_map_store = ResearchMapStore(db_path)

    retrieved_job = fresh_job_store.get(job.job_id)
    assert retrieved_job is not None
    assert retrieved_job.status == JobStatus.SUCCEEDED

    retrieved_ext = fresh_ext_store.get("paper-1")
    assert retrieved_ext is not None
    assert retrieved_ext.filename == "integration.pdf"
    assert len(retrieved_ext.chunks) == 1

    retrieved_map = fresh_map_store.get("paper-1")
    assert retrieved_map is not None
    assert retrieved_map.research_question == "Integration question?"
    assert len(retrieved_map.findings) == 3


# ---------------------------------------------------------------------------
# Test 2: Failure flow survives reopen
# ---------------------------------------------------------------------------


def test_failure_flow_survives_reopen(db_path: str) -> None:
    """Create, fail, close, reopen — verify failed status persists."""
    store = JobStore(db_path)

    # pending → failed
    job = store.create("paper-2")
    store.mark_failed(job.job_id, error_code="map_generation_failed")

    # running → failed
    job_r = store.create("paper-3")
    store.mark_running(job_r.job_id)
    store.mark_failed(job_r.job_id, error_code="llm_provider_error")

    # Reopen
    fresh_store = JobStore(db_path)

    retrieved_a = fresh_store.get(job.job_id)
    assert retrieved_a is not None
    assert retrieved_a.status == JobStatus.FAILED
    assert retrieved_a.error == "map_generation_failed"

    retrieved_b = fresh_store.get(job_r.job_id)
    assert retrieved_b is not None
    assert retrieved_b.status == JobStatus.FAILED
    assert retrieved_b.error == "llm_provider_error"


# ---------------------------------------------------------------------------
# Test 3: Caller-managed commit
# ---------------------------------------------------------------------------


def test_caller_managed_commit_persists_all(
    db_path: str,
    sample_extraction: ExtractionResult,
    sample_research_map: ResearchMap,
) -> None:
    """One caller-managed transaction across all three stores;
    commit persists everything."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")

    try:
        store = JobStore(db_path)
        ext_store = ExtractionStore(db_path)
        map_store = ResearchMapStore(db_path)

        job = store.create("paper-1", conn=conn)
        ext_store.save(sample_extraction, conn=conn)
        store.mark_running(job.job_id, conn=conn)
        map_store.save(sample_research_map, conn=conn)
        store.mark_succeeded(job.job_id, conn=conn)

        # Verify still visible on this connection (not auto-committed)
        assert store.get(job.job_id, conn=conn).status == JobStatus.SUCCEEDED
        assert ext_store.get("paper-1", conn=conn) is not None
        assert map_store.get("paper-1", conn=conn) is not None

        # Key: confirm not yet visible on a fresh connection
        fresh = sqlite3.connect(db_path)
        fresh.row_factory = sqlite3.Row
        fresh.execute("PRAGMA foreign_keys = ON")
        assert fresh.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job.job_id,)).fetchone() is None
        fresh.close()

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # After commit, reopen fresh — everything persisted
    reopened = JobStore(db_path)
    assert reopened.get(job.job_id).status == JobStatus.SUCCEEDED
    assert ExtractionStore(db_path).get("paper-1") is not None
    assert ResearchMapStore(db_path).get("paper-1") is not None


# ---------------------------------------------------------------------------
# Test 4: Caller-managed rollback
# ---------------------------------------------------------------------------


def test_caller_managed_rollback_removes_all(
    db_path: str,
    sample_extraction: ExtractionResult,
    sample_research_map: ResearchMap,
) -> None:
    """Caller-managed transaction rolled back — nothing persists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")

    store = JobStore(db_path)
    ext_store = ExtractionStore(db_path)
    map_store = ResearchMapStore(db_path)

    job = store.create("paper-rb", conn=conn)
    ext_store.save(sample_extraction, conn=conn)
    map_store.save(sample_research_map, conn=conn)

    # They are visible on this connection
    assert store.get(job.job_id, conn=conn) is not None
    assert ext_store.get("paper-1", conn=conn) is not None
    assert map_store.get("paper-1", conn=conn) is not None

    # Roll back
    conn.execute("ROLLBACK")
    conn.close()

    # Reopen — nothing should persist
    reopened = JobStore(db_path)
    assert reopened.get(job.job_id) is None
    assert ExtractionStore(db_path).get("paper-1") is None
    assert ResearchMapStore(db_path).get("paper-1") is None


# ---------------------------------------------------------------------------
# Test 5: Repository error does not roll back caller transaction
# ---------------------------------------------------------------------------


def test_repository_error_does_not_roll_back_caller_transaction(db_path: str) -> None:
    """A controlled repository failure (invalid transition) leaves the caller
    transaction open and prior writes visible."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")

    store = JobStore(db_path)

    # Successful write
    job = store.create("paper-err", conn=conn)
    assert store.get(job.job_id, conn=conn).status == JobStatus.PENDING

    # Mark running successfully
    store.mark_running(job.job_id, conn=conn)
    assert store.get(job.job_id, conn=conn).status == JobStatus.RUNNING

    # The caller's transaction should still be open
    assert conn.in_transaction

    # Cause a controlled repository failure: mark_running on an already-running job
    with pytest.raises(InvalidJobTransitionError):
        store.mark_running(job.job_id, conn=conn)

    # The caller's transaction must NOT have been rolled back by the repository
    assert conn.in_transaction, (
        "Repository must not roll back a caller-owned transaction"
    )

    # Prior writes are still visible on this connection
    row = conn.execute(
        "SELECT status FROM jobs WHERE job_id = ?", (job.job_id,)
    ).fetchone()
    assert row["status"] == "running"

    # Perform another valid write to prove the transaction is still usable
    job2 = store.create("paper-err-2", conn=conn)
    assert store.get(job2.job_id, conn=conn).status == JobStatus.PENDING

    # Roll back the caller's transaction
    conn.execute("ROLLBACK")
    conn.close()

    # Verify nothing persisted
    reopened = JobStore(db_path)
    assert reopened.get(job.job_id) is None
    assert reopened.get(job2.job_id) is None


# ---------------------------------------------------------------------------
# Test 6: Shared connection remains open
# ---------------------------------------------------------------------------


def test_shared_connection_remains_open(
    db_path: str,
    sample_extraction: ExtractionResult,
    sample_research_map: ResearchMap,
) -> None:
    """One connection passed through all three stores remains usable."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    store = JobStore(db_path)
    ext_store = ExtractionStore(db_path)
    map_store = ResearchMapStore(db_path)

    # All operations use the same caller-owned connection
    job = store.create("paper-shared", conn=conn)
    ext_store.save(sample_extraction, conn=conn)
    store.mark_running(job.job_id, conn=conn)
    map_store.save(sample_research_map, conn=conn)
    store.mark_succeeded(job.job_id, conn=conn)

    # Connection is still usable
    row = conn.execute("SELECT 1 AS val").fetchone()
    assert row["val"] == 1

    # Commit from the caller
    conn.commit()

    # Verify through a new connection that data persisted
    reopened_job = JobStore(db_path)
    retrieved = reopened_job.get(job.job_id)
    assert retrieved is not None
    assert retrieved.status == JobStatus.SUCCEEDED

    conn.close()


def test_metadata_table_is_created(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name = 'research_map_metadata'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert "generation_mode" in row[0]
    assert "fallback_reason" in row[0]
    assert "ON DELETE CASCADE" in row[0]


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (GenerationMode.GRANITE, "llm_provider_error"),
        (GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK, None),
        (GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK, "other"),
        ("granite", None),
    ],
)
def test_invalid_generation_metadata_is_rejected_before_persistence(
    research_map_store: ResearchMapStore,
    sample_research_map: ResearchMap,
    mode: object,
    reason: str | None,
) -> None:
    with pytest.raises(ValueError):
        research_map_store.save(
            sample_research_map,
            generation_mode=mode,  # type: ignore[arg-type]
            fallback_reason=reason,
        )

    assert research_map_store.get(sample_research_map.paper_id) is None


def test_granite_and_fallback_metadata_round_trip_and_replace(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    store.save(sample_research_map)
    granite = store.get_generation_metadata(sample_research_map.paper_id)

    assert granite is not None
    assert granite.generation_mode is GenerationMode.GRANITE
    assert granite.fallback_reason is None
    assert granite.generated_at is not None

    replacement = sample_research_map.model_copy(
        update={"research_question": "Replacement question?"}
    )
    store.save(
        replacement,
        generation_mode=GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK,
        fallback_reason="llm_provider_error",
    )
    reopened = ResearchMapStore(db_path)
    persisted = reopened.require(sample_research_map.paper_id)
    fallback = reopened.get_generation_metadata(sample_research_map.paper_id)

    assert persisted.research_question == "Replacement question?"
    assert fallback is not None
    assert (
        fallback.generation_mode
        is GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK
    )
    assert fallback.fallback_reason == "llm_provider_error"
    assert fallback.generated_at is not None


def test_legacy_map_without_metadata_is_treated_as_granite(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO research_maps (paper_id, map_json) VALUES (?, ?)",
            (
                sample_research_map.paper_id,
                sample_research_map.model_dump_json(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    metadata = store.get_generation_metadata(sample_research_map.paper_id)

    assert metadata is not None
    assert metadata.generation_mode is GenerationMode.GRANITE
    assert metadata.fallback_reason is None
    assert metadata.generated_at is None
    assert store.get_generation_metadata("missing-paper") is None


def test_malformed_metadata_raises_corrupt_record(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    store.save(sample_research_map)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE research_map_metadata SET generated_at = 'not-a-timestamp' "
            "WHERE paper_id = ?",
            (sample_research_map.paper_id,),
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(CorruptRecordError):
        store.get_generation_metadata(sample_research_map.paper_id)


def test_metadata_failure_rolls_back_map_and_metadata_together(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    store.save(sample_research_map)
    original_metadata = store.get_generation_metadata(sample_research_map.paper_id)
    replacement = sample_research_map.model_copy(
        update={"research_question": "Must be rolled back?"}
    )
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TRIGGER fail_metadata_update
            BEFORE UPDATE ON research_map_metadata
            BEGIN
                SELECT RAISE(ABORT, 'forced metadata failure');
            END
            """
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(PersistenceError):
        store.save(
            replacement,
            generation_mode=GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK,
            fallback_reason="llm_provider_error",
        )

    assert store.require(sample_research_map.paper_id) == sample_research_map
    assert store.get_generation_metadata(sample_research_map.paper_id) == original_metadata


def test_caller_owned_map_save_releases_savepoint_but_keeps_outer_transaction(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")
    try:
        store.save(sample_research_map, conn=conn)

        assert conn.in_transaction
        assert store.require(sample_research_map.paper_id, conn=conn) == sample_research_map
        metadata = store.get_generation_metadata(
            sample_research_map.paper_id,
            conn=conn,
        )
        assert metadata is not None
        assert metadata.generation_mode is GenerationMode.GRANITE

        fresh = sqlite3.connect(db_path)
        try:
            assert fresh.execute(
                "SELECT 1 FROM research_maps WHERE paper_id = ?",
                (sample_research_map.paper_id,),
            ).fetchone() is None
        finally:
            fresh.close()
    finally:
        conn.rollback()
        conn.close()


def test_caller_owned_metadata_failure_rolls_back_only_repository_savepoint(
    db_path: str,
    sample_research_map: ResearchMap,
) -> None:
    store = ResearchMapStore(db_path)
    job_store = JobStore(db_path)
    store.save(sample_research_map)
    original_metadata = store.get_generation_metadata(sample_research_map.paper_id)
    replacement = sample_research_map.model_copy(
        update={"research_question": "Partial replacement must not persist?"}
    )

    trigger_conn = sqlite3.connect(db_path)
    try:
        trigger_conn.execute(
            """
            CREATE TRIGGER fail_caller_metadata_update
            BEFORE UPDATE ON research_map_metadata
            BEGIN
                SELECT RAISE(ABORT, 'forced caller metadata failure');
            END
            """
        )
        trigger_conn.commit()
    finally:
        trigger_conn.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("BEGIN")
    try:
        before_job = job_store.create("unrelated-before-savepoint", conn=conn)

        with pytest.raises(PersistenceError):
            store.save(
                replacement,
                generation_mode=GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK,
                fallback_reason="llm_provider_error",
                conn=conn,
            )

        assert conn.in_transaction
        assert store.require(sample_research_map.paper_id, conn=conn) == sample_research_map
        assert (
            store.get_generation_metadata(sample_research_map.paper_id, conn=conn)
            == original_metadata
        )
        assert job_store.require(before_job.job_id, conn=conn) == before_job

        after_job = job_store.create("unrelated-after-savepoint", conn=conn)
        assert job_store.require(after_job.job_id, conn=conn) == after_job
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()

    reopened = ResearchMapStore(db_path)
    assert reopened.require(sample_research_map.paper_id) == sample_research_map
    assert (
        reopened.get_generation_metadata(sample_research_map.paper_id)
        == original_metadata
    )
    assert JobStore(db_path).require(before_job.job_id) == before_job
    assert JobStore(db_path).require(after_job.job_id) == after_job
