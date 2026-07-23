"""API tests for the jobs endpoint (job creation, polling, and lifecycle).

All tests use a test client with a test container, real temporary
file-backed database, and a FakeJobRunner.  No network, no watsonx.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import ServiceContainer, build_container
from app.main import create_app
from app.models.paper import Chunk, ExtractionResult


# ---------------------------------------------------------------------------
# FakeJobRunner — records scheduled jobs, never executes
# ---------------------------------------------------------------------------


class FakeJobRunner:
    """Records scheduled job IDs without executing anything."""

    def __init__(self) -> None:
        self.scheduled: list[str] = []

    def run(self, job_id: str) -> None:
        self.scheduled.append(job_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_file = tmp_path / "test_jobs.db"
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_file}",
        cors_origins="http://localhost:3000",
        upload_max_bytes=20_971_520,
    )


@pytest.fixture
def fake_job_runner() -> FakeJobRunner:
    return FakeJobRunner()


@pytest.fixture
def container(settings: Settings, fake_job_runner: FakeJobRunner) -> ServiceContainer:
    """Build a container with a FakeJobRunner and a real database."""
    real = build_container(settings)
    # Fake job runner (never executes real work)
    real.job_runner_factory = lambda: fake_job_runner  # type: ignore[return-value]
    # Use deterministic paper_id and job_id for testing
    real.paper_id_factory = lambda: "test-paper-id"
    return real


@pytest.fixture
def client(settings: Settings, container: ServiceContainer) -> TestClient:
    app = create_app(settings, container=container)
    with TestClient(app) as c:
        yield c


def _seed_extraction(
    container: ServiceContainer,
    paper_id: str = "test-paper-id",
) -> None:
    """Save an extraction for *paper_id* so job creation succeeds."""
    container.extraction_store.save(
        ExtractionResult(
            paper_id=paper_id,
            filename="test.pdf",
            chunks=[Chunk(chunk_id=f"{paper_id}-p1-1", page=1, text="Text.")],
        )
    )


# ---------------------------------------------------------------------------
# Job creation tests
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_existing_extraction_creates_pending_job(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container)
        resp = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert data["paper_id"] == "test-paper-id"

    def test_unknown_paper_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/papers/unknown-paper/research-map-jobs")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "paper_not_found"

    def test_runner_unavailable_returns_503(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        container.job_runner_factory = None
        _seed_extraction(container)
        resp = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp.status_code == 503
        assert resp.json()["detail"]["code"] == "generation_unavailable"

    def test_runner_unavailable_creates_no_job(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        container.job_runner_factory = None
        _seed_extraction(container)
        client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        job = container.job_store.get_latest_job_for_paper("test-paper-id")
        assert job is None

    def test_background_runner_scheduled_once(
        self, client: TestClient, container: ServiceContainer, fake_job_runner: FakeJobRunner
    ) -> None:
        _seed_extraction(container)
        client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert len(fake_job_runner.scheduled) == 1

    def test_duplicate_active_job_returns_existing(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container)
        resp1 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp1.status_code == 202
        resp2 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp2.status_code == 202
        # Both responses should have the same job_id
        assert resp1.json()["job_id"] == resp2.json()["job_id"]

    def test_duplicate_active_job_no_second_task(
        self, client: TestClient, container: ServiceContainer, fake_job_runner: FakeJobRunner
    ) -> None:
        _seed_extraction(container)
        client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        # Only one task should be scheduled
        assert len(fake_job_runner.scheduled) == 1

    def test_new_job_after_succeeded(
        self, client: TestClient, container: ServiceContainer, fake_job_runner: FakeJobRunner
    ) -> None:
        _seed_extraction(container)
        # Create first job and complete it
        resp1 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        job_id = resp1.json()["job_id"]
        container.job_store.mark_running(job_id)
        container.job_store.mark_succeeded(job_id)

        # Now create a new job — should succeed since latest job is succeeded
        resp2 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp2.status_code == 202
        assert resp2.json()["job_id"] != resp1.json()["job_id"]
        assert resp2.json()["status"] == "pending"

    def test_new_job_after_failed(
        self, client: TestClient, container: ServiceContainer, fake_job_runner: FakeJobRunner
    ) -> None:
        _seed_extraction(container)
        # Create first job and fail it
        resp1 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        job_id = resp1.json()["job_id"]
        container.job_store.mark_failed(job_id, error_code="map_generation_failed")

        # Now create a new job — should succeed since latest job is failed
        resp2 = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp2.status_code == 202
        assert resp2.json()["job_id"] != resp1.json()["job_id"]

    def test_no_model_inference_in_handler(
        self, client: TestClient, container: ServiceContainer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_extraction(container)
        # The handler should only schedule the lazy wrapper, not build the runner.
        factory = MagicMock(return_value=FakeJobRunner())
        container.job_runner_factory = factory
        # TestClient executes BackgroundTasks before returning. Replace the
        # wrapper so this test isolates handler scheduling from background work.
        monkeypatch.setattr("app.routers.papers.run_research_map_job", MagicMock())
        resp = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        assert resp.status_code == 202
        factory.assert_not_called()

    def test_no_raw_internal_error_exposed(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container)
        resp = client.post("/api/v1/papers/test-paper-id/research-map-jobs")
        body = resp.json()
        # Response should have only safe fields
        assert set(body.keys()) == {"job_id", "paper_id", "status"}

    def test_scheduling_failure_marks_job_failed(
        self, client: TestClient, container: ServiceContainer, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seed_extraction(container, "p-schedule-fail")

        def _raise(*_args, **_kwargs):
            raise RuntimeError("raw scheduler explosion")

        monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", _raise)
        resp = client.post("/api/v1/papers/p-schedule-fail/research-map-jobs")

        assert resp.status_code == 500
        assert resp.json()["detail"]["code"] == "task_scheduling_failed"
        body = str(resp.json())
        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "raw scheduler explosion" not in body
        assert "raw scheduler explosion" not in logs

        job = container.job_store.get_latest_job_for_paper("p-schedule-fail")
        assert job is not None
        assert job.status == "failed"
        assert job.error == "task_scheduling_failed"
        assert container.job_store.get_active_job_for_paper("p-schedule-fail") is None

    def test_concurrent_same_paper_requests_share_active_job(
        self, client: TestClient, container: ServiceContainer, fake_job_runner: FakeJobRunner
    ) -> None:
        _seed_extraction(container, "p-concurrent")

        barrier = threading.Barrier(2)

        def _post():
            barrier.wait(timeout=5)
            return client.post("/api/v1/papers/p-concurrent/research-map-jobs")

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: _post(), range(2)))

        assert {response.status_code for response in responses} == {202}
        job_ids = {response.json()["job_id"] for response in responses}
        assert len(job_ids) == 1
        assert len(fake_job_runner.scheduled) == 1
        active = container.job_store.get_active_job_for_paper("p-concurrent")
        assert active is not None
        assert active.job_id == next(iter(job_ids))

    def test_task_registration_occurs_after_lock_released(
        self, client: TestClient, container: ServiceContainer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_extraction(container, "p-lock-release")
        observed_unlocked = False

        original_add_task = __import__("starlette.background", fromlist=["BackgroundTasks"]).BackgroundTasks.add_task

        def _record_lock_state(self, *args, **kwargs):
            nonlocal observed_unlocked
            observed_unlocked = not container.job_creation_lock.locked()
            return original_add_task(self, *args, **kwargs)

        monkeypatch.setattr("starlette.background.BackgroundTasks.add_task", _record_lock_state)

        resp = client.post("/api/v1/papers/p-lock-release/research-map-jobs")

        assert resp.status_code == 202
        assert observed_unlocked is True

    def test_provider_construction_failure_is_safe(
        self, client: TestClient, container: ServiceContainer, caplog: pytest.LogCaptureFixture
    ) -> None:
        _seed_extraction(container, "p-provider-fail")
        container.job_runner_factory = MagicMock(
            side_effect=RuntimeError("credential/network secret")
        )

        resp = client.post("/api/v1/papers/p-provider-fail/research-map-jobs")

        assert resp.status_code == 202
        job = container.job_store.get_latest_job_for_paper("p-provider-fail")
        assert job is not None
        assert job.status == "failed"
        assert job.error == "llm_provider_error"
        body = str(resp.json())
        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "credential/network secret" not in body
        assert "credential/network secret" not in logs


# ---------------------------------------------------------------------------
# Job polling tests
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_pending_job_returned(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-pending")
        resp = client.post("/api/v1/papers/p-poll-pending/research-map-jobs")
        job_id = resp.json()["job_id"]

        poll = client.get(f"/api/v1/jobs/{job_id}")
        assert poll.status_code == 200
        assert poll.json()["status"] == "pending"

    def test_running_job_returned(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-running")
        resp = client.post("/api/v1/papers/p-poll-running/research-map-jobs")
        job_id = resp.json()["job_id"]
        container.job_store.mark_running(job_id)

        poll = client.get(f"/api/v1/jobs/{job_id}")
        assert poll.status_code == 200
        assert poll.json()["status"] == "running"

    def test_succeeded_job_returned(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-succ")
        resp = client.post("/api/v1/papers/p-poll-succ/research-map-jobs")
        job_id = resp.json()["job_id"]
        container.job_store.mark_running(job_id)
        container.job_store.mark_succeeded(job_id)

        poll = client.get(f"/api/v1/jobs/{job_id}")
        assert poll.status_code == 200
        assert poll.json()["status"] == "succeeded"
        assert poll.json()["error"] is None

    def test_failed_job_returns_safe_error_code(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-fail")
        resp = client.post("/api/v1/papers/p-poll-fail/research-map-jobs")
        job_id = resp.json()["job_id"]
        container.job_store.mark_failed(job_id, error_code="map_generation_failed")

        poll = client.get(f"/api/v1/jobs/{job_id}")
        assert poll.status_code == 200
        assert poll.json()["status"] == "failed"
        assert poll.json()["error"] == "map_generation_failed"

    def test_missing_job_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/jobs/nonexistent-job")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "job_not_found"

    def test_timestamps_serialize_correctly(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-ts")
        resp = client.post("/api/v1/papers/p-poll-ts/research-map-jobs")
        job_id = resp.json()["job_id"]

        poll = client.get(f"/api/v1/jobs/{job_id}")
        data = poll.json()
        # ISO-8601 with UTC offset — accept either Z or +00:00
        ts = data["created_at"]
        assert ts.endswith("+00:00") or ts.endswith("Z"), f"Unexpected timestamp format: {ts}"
        ts = data["updated_at"]
        assert ts.endswith("+00:00") or ts.endswith("Z"), f"Unexpected timestamp format: {ts}"

    def test_no_internal_database_values_leak(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        _seed_extraction(container, "p-poll-leak")
        resp = client.post("/api/v1/papers/p-poll-leak/research-map-jobs")
        job_id = resp.json()["job_id"]

        poll = client.get(f"/api/v1/jobs/{job_id}")
        body = poll.json()
        # Should only contain the fields from JobStatusResponse
        assert set(body.keys()) == {
            "job_id", "paper_id", "status",
            "created_at", "updated_at", "error",
        }