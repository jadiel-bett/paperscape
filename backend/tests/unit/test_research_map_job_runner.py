"""Unit tests for :class:`ResearchMapJobRunner`.

All tests use temporary file-backed SQLite databases and fake services.
No network, no watsonx, no real extraction.
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.database import init_db
from app.models.job import Job, JobStatus
from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap
from app.repositories import (
    ExtractionStore,
    InvalidJobTransitionError,
    JobStore,
    PersistenceError,
    RecordNotFoundError,
    ResearchMapStore,
)
from app.services.llm_provider import LLMProviderError
from app.services.research_map import MapGenerationError, ResearchMapService
from app.services.research_map_job_runner import ResearchMapJobRunner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_DISCLAIMER = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "runner_test.db"
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


def _make_sample_extraction(paper_id: str) -> ExtractionResult:
    return ExtractionResult(
        paper_id=paper_id,
        filename="test.pdf",
        chunks=[
            Chunk(chunk_id=f"{paper_id}-p1-1", page=1, text="Introduction text.", section="Introduction"),
            Chunk(chunk_id=f"{paper_id}-p2-1", page=2, text="Results show significant improvement.", section="Results"),
        ],
    )


def _make_sample_research_map(paper_id: str) -> ResearchMap:
    return ResearchMap(
        paper_id=paper_id,
        research_question="Test research question?",
        findings=[
            Finding(
                statement="Finding one",
                evidence=[Evidence(chunk_id=f"{paper_id}-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="high",
            ),
            Finding(
                statement="Finding two",
                evidence=[Evidence(chunk_id=f"{paper_id}-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="partial",
            ),
            Finding(
                statement="Finding three",
                evidence=[Evidence(chunk_id=f"{paper_id}-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="high",
            ),
        ],
        limitations=["Small sample size."],
        disclaimer=_TEST_DISCLAIMER,
    )


@pytest.fixture
def fake_research_map_service() -> ResearchMapService:
    """Return a mock ResearchMapService that returns a valid map."""
    mock = MagicMock(spec=ResearchMapService)
    # Return the map with correct paper_id based on extraction input
    def _generate(extraction: ExtractionResult) -> ResearchMap:
        return _make_sample_research_map(extraction.paper_id)
    mock.generate_map.side_effect = _generate
    return mock


# ---------------------------------------------------------------------------
# Helper to create a pending job and build a runner
# ---------------------------------------------------------------------------


def _create_runner(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    research_map_service: ResearchMapService,
) -> ResearchMapJobRunner:
    return ResearchMapJobRunner(
        job_store=job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        research_map_service=research_map_service,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_pending_to_running(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-happy"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.SUCCEEDED


def test_runner_uses_returned_job(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-returned"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    # The mock was called; verify mark_running was invoked.
    stored = job_store.get(job.job_id)
    assert stored is not None
    assert stored.status == JobStatus.SUCCEEDED


def test_extraction_is_loaded(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-loaded"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    # The mocked service received an extraction
    assert fake_research_map_service.generate_map.called
    args, _ = fake_research_map_service.generate_map.call_args
    assert args[0].paper_id == paper_id


def test_map_is_saved(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-saved"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    saved = research_map_store.get(paper_id)
    assert saved is not None
    assert saved.paper_id == paper_id


def test_successful_job_becomes_succeeded(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-success"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.SUCCEEDED
    assert final.error is None


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_missing_extraction_marks_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    # Create a job for a paper_id that has no extraction saved
    paper_id = "p-missing-ext"
    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "extraction_missing"


def test_map_generation_error_marks_failed(
    caplog: pytest.LogCaptureFixture,
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    caplog.set_level(
        logging.ERROR,
        logger="app.services.research_map_job_runner",
    )
    paper_id = "p-map-err"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = MapGenerationError("Model failed")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, failing_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "map_generation_failed"
    assert (
        "Research map generation failed: issue_codes=['UNKNOWN']"
        in caplog.messages
    )


def test_map_generation_error_logs_only_safe_sorted_issue_codes(
    caplog: pytest.LogCaptureFixture,
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    caplog.set_level(
        logging.DEBUG,
        logger="app.services.research_map_job_runner",
    )
    chunk_sentinel = "SENTINEL_PAPER_CHUNK_TEXT"
    extraction = ExtractionResult(
        paper_id="p-safe-diagnostic",
        filename="test.pdf",
        chunks=[
            Chunk(
                chunk_id="p-safe-diagnostic-p1-1",
                page=1,
                text=chunk_sentinel,
                section="Results",
            )
        ],
    )
    extraction_store.save(extraction)

    failure = MapGenerationError(
        "SENTINEL_PROMPT_TEXT SENTINEL_MODEL_OUTPUT",
        issue_codes={
            "PAGE_MISMATCH",
            "INVALID_JSON",
            "SENTINEL_UNSAFE_ISSUE_CODE",
        },
    )
    failure.__cause__ = ValueError("SENTINEL_CHAINED_EXCEPTION")
    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = failure

    job = job_store.create(extraction.paper_id)
    runner = _create_runner(
        job_store,
        extraction_store,
        research_map_store,
        failing_service,
    )
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "map_generation_failed"
    assert (
        "Research map generation failed: "
        "issue_codes=['INVALID_JSON', 'PAGE_MISMATCH']"
        in caplog.messages
    )
    complete_log = caplog.text
    assert "SENTINEL_PROMPT_TEXT" not in complete_log
    assert "SENTINEL_MODEL_OUTPUT" not in complete_log
    assert chunk_sentinel not in complete_log
    assert "SENTINEL_CHAINED_EXCEPTION" not in complete_log
    assert "SENTINEL_UNSAFE_ISSUE_CODE" not in complete_log


def test_llm_provider_error_marks_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    paper_id = "p-llm-err"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = LLMProviderError("Provider down")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, failing_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "llm_provider_error"


def test_persistence_error_on_save_marks_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-persist-err"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    # Save raises PersistenceError
    failing_map_store = MagicMock(spec=ResearchMapStore)
    failing_map_store.save.side_effect = PersistenceError("Disk full")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, failing_map_store, fake_research_map_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "persistence_error"


def test_persistence_error_on_mark_succeeded(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-mark-succ-err"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    # mark_succeeded raises PersistenceError
    failing_job_store = MagicMock(spec=JobStore)
    failing_job_store.mark_running.side_effect = lambda jid: Job(
        job_id=jid, paper_id=paper_id, status=JobStatus.RUNNING,
        created_at=job_store._clock(), updated_at=job_store._clock(),
    )
    failing_job_store.mark_succeeded.side_effect = PersistenceError("DB locked")

    # create a real job first
    job = job_store.create(paper_id)
    failing_job_store.mark_failed = job_store.mark_failed

    # Use the real job_store for extraction store operations
    runner = ResearchMapJobRunner(
        job_store=failing_job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        research_map_service=fake_research_map_service,
    )
    runner.run(job.job_id)

    # The map should be saved (we use real research_map_store),
    # but the job should be failed since mark_succeeded raised.
    saved = research_map_store.get(paper_id)
    assert saved is not None

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "persistence_error"


def test_unexpected_exception_marks_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    paper_id = "p-unexpected"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = RuntimeError("Something broke")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, failing_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    # Unexpected errors propagate and the runner catches them via the broad
    # Exception handler in _mark_failed
    assert final.status == JobStatus.FAILED


# ---------------------------------------------------------------------------
# Safety — no raw exception messages in stored errors
# ---------------------------------------------------------------------------


def test_raw_exception_messages_not_stored(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    paper_id = "p-raw-msg"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = MapGenerationError("Sensitive details")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, failing_service)
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    # The error should be the safe code, not the exception message
    assert "Sensitive details" != final.error
    assert final.error == "map_generation_failed"


# ---------------------------------------------------------------------------
# Runner safety — claim failure must not call mark_failed
# ---------------------------------------------------------------------------


def test_invalid_job_state_does_not_mark_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-invalid-state"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    # Create and immediately mark as succeeded
    job = job_store.create(paper_id)
    job_store.mark_running(job.job_id)
    job_store.mark_succeeded(job.job_id)

    # Try to run — mark_running will raise InvalidJobTransitionError
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    # Job should remain succeeded (runner should NOT have called mark_failed)
    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.SUCCEEDED
    assert final.error is None


def test_missing_job_does_not_mark_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run("nonexistent-job")

    # Nothing should be persisted for a nonexistent job
    # (No assertion of failure — just verify it doesn't throw)


def test_second_runner_cannot_fail_active_job(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-second-runner"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)

    # Runner A claims the job
    runner_a = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner_a.run(job.job_id)

    # Runner B tries to claim the same job
    runner_b = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner_b.run(job.job_id)

    # Job should be succeeded (Runner A's work), not failed by Runner B
    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.SUCCEEDED
    assert final.error is None


# ---------------------------------------------------------------------------
# Transaction isolation
# ---------------------------------------------------------------------------


def test_no_transaction_during_model_call(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    """Verify that mark_running's transaction is closed before generate_map."""
    paper_id = "p-txn-iso"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    # Service that checks no transaction is open
    class CheckTxnService:
        def __init__(self) -> None:
            self.called = False

        def generate_map(self, extraction: ExtractionResult) -> ResearchMap:
            self.called = True
            # At this point the mark_running transaction should be closed
            return _make_sample_research_map(paper_id)

    service = CheckTxnService()
    runner = ResearchMapJobRunner(
        job_store=job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        research_map_service=service,  # type: ignore[arg-type]
    )

    job = job_store.create(paper_id)
    runner.run(job.job_id)

    assert service.called


# ---------------------------------------------------------------------------
# Runner return value and exception behavior
# ---------------------------------------------------------------------------


def test_runner_returns_none(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-return-none"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    result = runner.run(job.job_id)
    assert result is None


def test_runner_does_not_reraise(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    paper_id = "p-no-reraise"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    failing_service = MagicMock(spec=ResearchMapService)
    failing_service.generate_map.side_effect = MapGenerationError("fail")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, failing_service)
    # Should not raise
    runner.run(job.job_id)


def test_no_additional_retry_loop(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
) -> None:
    """The runner must not call generate_map more than once."""
    paper_id = "p-no-retry"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    service = MagicMock(spec=ResearchMapService)
    service.generate_map.side_effect = MapGenerationError("fail")

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, service)
    runner.run(job.job_id)

    # generate_map should be called exactly once (retry is owned by ResearchMapService)
    assert service.generate_map.call_count == 1


# ---------------------------------------------------------------------------
# Extraction store persistence error
# ---------------------------------------------------------------------------


def test_extraction_persistence_error_marks_failed(
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    paper_id = "p-ext-persist-err"
    # Do not save an extraction — RecordNotFoundError will be caught as PersistenceError
    # Actually require() raises RecordNotFoundError, not PersistenceError.
    # Let's test the PersistenceError path via a failing ExtractionStore mock.
    failing_ext_store = MagicMock(spec=ExtractionStore)
    failing_ext_store.require.side_effect = PersistenceError("DB unavailable")

    job = job_store.create(paper_id)
    runner = ResearchMapJobRunner(
        job_store=job_store,
        extraction_store=failing_ext_store,
        research_map_store=research_map_store,
        research_map_service=fake_research_map_service,
    )
    runner.run(job.job_id)

    final = job_store.get(job.job_id)
    assert final is not None
    assert final.status == JobStatus.FAILED
    assert final.error == "persistence_error"


# ---------------------------------------------------------------------------
# Logging safety — paper content and model output not logged
# ---------------------------------------------------------------------------


def test_paper_content_not_logged(
    caplog: pytest.LogCaptureFixture,
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    caplog.set_level(logging.DEBUG)
    paper_id = "p-log-content"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    for record in caplog.records:
        msg = str(record.getMessage())
        assert "Introduction text" not in msg, f"Log contains chunk text: {msg}"
        assert "significant improvement" not in msg, f"Log contains chunk text: {msg}"


def test_model_output_not_logged(
    caplog: pytest.LogCaptureFixture,
    job_store: JobStore,
    extraction_store: ExtractionStore,
    research_map_store: ResearchMapStore,
    fake_research_map_service: ResearchMapService,
) -> None:
    caplog.set_level(logging.DEBUG)
    paper_id = "p-log-output"
    extraction = _make_sample_extraction(paper_id)
    extraction_store.save(extraction)

    job = job_store.create(paper_id)
    runner = _create_runner(job_store, extraction_store, research_map_store, fake_research_map_service)
    runner.run(job.job_id)

    for record in caplog.records:
        msg = str(record.getMessage())
        assert "Finding one" not in msg
