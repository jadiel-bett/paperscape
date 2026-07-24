"""API tests for the papers endpoint (upload and research-map retrieval).

All tests use a test client with a fake extraction service and a real
temporary file-backed database.  No network, no watsonx, no real PDF files.
"""
from __future__ import annotations

import io
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import AppException, ServiceContainer, build_container
from app.main import create_app
from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap
from app.repositories import PersistenceError
from app.routers.papers import upload_paper

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_DISCLAIMER = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a temporary file-backed database."""
    db_file = tmp_path / "test_papers.db"
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_file}",
        cors_origins="http://localhost:3000",
        upload_max_bytes=20_971_520,
    )


@pytest.fixture
def fake_extraction_result() -> ExtractionResult:
    return ExtractionResult(
        paper_id="test-paper-id",
        filename="test.pdf",
        chunks=[
            Chunk(chunk_id="test-paper-id-p1-1", page=1, text="Introduction text.", section="Introduction"),
            Chunk(chunk_id="test-paper-id-p2-1", page=2, text="Results show significant improvement.", section="Results"),
        ],
    )


@pytest.fixture
def fake_research_map() -> ResearchMap:
    return ResearchMap(
        paper_id="test-paper-id",
        research_question="Test research question?",
        findings=[
            Finding(
                statement="Finding one",
                evidence=[Evidence(chunk_id="test-paper-id-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="high",
            ),
            Finding(
                statement="Finding two",
                evidence=[Evidence(chunk_id="test-paper-id-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="partial",
            ),
            Finding(
                statement="Finding three",
                evidence=[Evidence(chunk_id="test-paper-id-p2-1", page=2, excerpt="Results show significant improvement.")],
                confidence="high",
            ),
        ],
        limitations=["Small sample size."],
        disclaimer=_TEST_DISCLAIMER,
    )


@pytest.fixture
def fake_extraction_service(fake_extraction_result: ExtractionResult):
    svc = MagicMock()
    svc.extract.return_value = fake_extraction_result
    return svc


@pytest.fixture
def fake_uuid_factory() -> str:
    return "aaaa-bbbb-cccc-dddd"


@pytest.fixture
def container(
    settings: Settings,
    fake_extraction_service,
    fake_research_map: ResearchMap,
) -> ServiceContainer:
    """Build a container with fakes for API tests."""
    real = build_container(settings)
    # Replace extraction service with fake
    real.extraction_service = fake_extraction_service
    # Use a deterministic paper_id factory
    real.paper_id_factory = lambda: "test-paper-id"
    return real


@pytest.fixture
def client(settings: Settings, container: ServiceContainer) -> TestClient:
    """TestClient with the test container pre-injected."""
    app = create_app(settings, container=container)
    with TestClient(app) as c:
        yield c


def _make_pdf_bytes(content: str = "Fake PDF content for testing.") -> bytes:
    """Return bytes that look like a PDF (contains %PDF- signature)."""
    return b"%PDF-1.4\n" + content.encode("utf-8") + b"\n%%EOF"


class ClosableUpload:
    def __init__(self, data: bytes, *, filename: str | None = "test.pdf", content_type: str | None = "application/pdf") -> None:
        self.filename = filename
        self.content_type = content_type
        self._stream = io.BytesIO(data)
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


class TestUpload:
    VALID_PDF = _make_pdf_bytes()

    def test_valid_pdf_returns_201(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["paper_id"] == "test-paper-id"
        assert data["filename"] == "test.pdf"
        assert data["page_count"] == 2
        assert data["chunk_count"] == 2

    def test_paper_id_matches_persisted_extraction(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 201
        paper_id = resp.json()["paper_id"]
        stored = container.extraction_store.get(paper_id)
        assert stored is not None
        assert stored.paper_id == paper_id

    def test_filename_preserved(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("my-paper.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 201
        assert resp.json()["filename"] == "my-paper.pdf"

    def test_extraction_receives_bytes(
        self, client: TestClient, fake_extraction_service
    ) -> None:
        client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert fake_extraction_service.extract.called
        args, _ = fake_extraction_service.extract.call_args
        assert args[0] == self.VALID_PDF

    def test_extraction_is_persisted(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        stored = container.extraction_store.get("test-paper-id")
        assert stored is not None

    def test_empty_file_rejected_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_upload"

    def test_blank_filename_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("", self.VALID_PDF, "application/pdf")},
        )
        # FastAPI's form validation may return 422 for an empty filename before
        # the route handler runs, or 400 if the route handler catches it.
        assert resp.status_code in (400, 422)

    def test_unsupported_media_type_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.txt", b"text content", "text/plain")},
        )
        assert resp.status_code == 415
        assert resp.json()["detail"]["code"] == "unsupported_media_type"

    def test_oversized_upload_413(self, client: TestClient) -> None:
        # Create content larger than the default 20 MB limit
        large_content = b"A" * (20_971_521)
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("large.pdf", large_content, "application/pdf")},
        )
        assert resp.status_code == 413
        assert resp.json()["detail"]["code"] == "upload_too_large"

    def test_max_bytes_exactly_succeeds(
        self, client: TestClient, settings: Settings
    ) -> None:
        # Create content exactly at the limit
        # The PDF signature prefix and suffix are part of the total size
        prefix = b"%PDF-1.4\n"
        suffix = b"\n%%EOF"
        body_len = settings.upload_max_bytes - len(prefix) - len(suffix)
        exact_content = prefix + b"A" * body_len + suffix
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("exact.pdf", exact_content, "application/pdf")},
        )
        assert resp.status_code == 201

    def test_no_watsonx_constructed_for_upload(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        assert container.job_runner_factory is None
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 201

    def test_extraction_error_maps_to_422(
        self, client: TestClient, fake_extraction_service
    ) -> None:
        from app.services.extraction import ExtractionError

        fake_extraction_service.extract.side_effect = ExtractionError("No text")
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "extraction_failed"

    def test_text_absent_from_errors(
        self, client: TestClient, fake_extraction_service
    ) -> None:
        from app.services.extraction import ExtractionError

        fake_extraction_service.extract.side_effect = ExtractionError("No text")
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        error_body = str(resp.json())
        # Make sure no PDF bytes or chunk text leaked
        assert "%PDF-" not in error_body

    def test_multipart_content_type_not_confused(self, client: TestClient) -> None:
        """The endpoint checks UploadFile.content_type, not the multipart envelope."""
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        # Request-level content-type is multipart/form-data; the endpoint must
        # check file.content_type which is application/pdf
        assert resp.status_code == 201

    def test_non_pdf_signature_rejected(self, client: TestClient) -> None:
        """Content without %PDF- within first 1024 bytes is rejected."""
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("notapdf.pdf", b"Not a PDF at all!", "application/pdf")},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "upload_not_a_pdf"

    @pytest.mark.parametrize(
        ("filename", "content_type", "data", "status_code"),
        [
            (None, "application/pdf", VALID_PDF, 400),
            ("test.pdf", "text/plain", VALID_PDF, 415),
            ("empty.pdf", "application/pdf", b"", 400),
            ("large.pdf", "application/pdf", b"%PDF-" + b"x" * 16, 413),
        ],
    )
    def test_uploadfile_closed_on_validation_failure(
        self,
        settings: Settings,
        fake_extraction_service,
        filename: str | None,
        content_type: str,
        data: bytes,
        status_code: int,
    ) -> None:
        settings.upload_max_bytes = 10
        upload = ClosableUpload(
            data,
            filename=filename,
            content_type=content_type,
        )
        with pytest.raises(AppException) as exc_info:
            asyncio.run(
                upload_paper(
                    file=upload,  # type: ignore[arg-type]
                    settings=settings,
                    extraction_service=fake_extraction_service,
                    extraction_store=MagicMock(),
                    paper_id_factory=lambda: "valid-paper-id",
                )
            )
        assert exc_info.value.status_code == status_code
        assert upload.closed is True

    def test_uploadfile_closed_on_success(
        self, settings: Settings, fake_extraction_service, fake_extraction_result: ExtractionResult
    ) -> None:
        upload = ClosableUpload(self.VALID_PDF)
        fake_extraction_service.extract.return_value = fake_extraction_result
        asyncio.run(
            upload_paper(
                file=upload,  # type: ignore[arg-type]
                settings=settings,
                extraction_service=fake_extraction_service,
                extraction_store=MagicMock(),
                paper_id_factory=lambda: "valid-paper-id",
            )
        )
        assert upload.closed is True

    def test_uploadfile_closed_on_extraction_failure(
        self, settings: Settings, fake_extraction_service
    ) -> None:
        from app.services.extraction import ExtractionError

        fake_extraction_service.extract.side_effect = ExtractionError("private extraction detail")
        upload = ClosableUpload(self.VALID_PDF)
        with pytest.raises(AppException) as exc_info:
            asyncio.run(
                upload_paper(
                    file=upload,  # type: ignore[arg-type]
                    settings=settings,
                    extraction_service=fake_extraction_service,
                    extraction_store=MagicMock(),
                    paper_id_factory=lambda: "valid-paper-id",
                )
            )
        assert exc_info.value.status_code == 422
        assert upload.closed is True

    def test_uploadfile_closed_on_persistence_failure(
        self, settings: Settings, fake_extraction_service, fake_extraction_result: ExtractionResult
    ) -> None:
        store = MagicMock()
        store.save.side_effect = PersistenceError("private database detail")
        upload = ClosableUpload(self.VALID_PDF)
        fake_extraction_service.extract.return_value = fake_extraction_result
        with pytest.raises(AppException) as exc_info:
            asyncio.run(
                upload_paper(
                    file=upload,  # type: ignore[arg-type]
                    settings=settings,
                    extraction_service=fake_extraction_service,
                    extraction_store=store,
                    paper_id_factory=lambda: "valid-paper-id",
                )
            )
        assert exc_info.value.status_code == 500
        assert upload.closed is True
        assert "private database detail" not in str(exc_info.value)

    @pytest.mark.parametrize("bad_id", ["", "   ", "a" * 129, "bad/id", 123])
    def test_invalid_generated_paper_id_is_safe_500(
        self, client: TestClient, container: ServiceContainer, fake_extraction_service, bad_id: object
    ) -> None:
        container.paper_id_factory = lambda: bad_id  # type: ignore[return-value]
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 500
        assert resp.json()["detail"]["code"] == "internal_error"
        if str(bad_id):
            assert str(bad_id) not in str(resp.json())
        fake_extraction_service.extract.assert_not_called()

    def test_valid_generated_paper_id_is_preserved(
        self, client: TestClient, container: ServiceContainer, fake_extraction_service
    ) -> None:
        container.paper_id_factory = lambda: "Stable_ID-01"
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 201
        assert resp.json()["paper_id"] == "Stable_ID-01"
        args, _ = fake_extraction_service.extract.call_args
        assert args[2] == "Stable_ID-01"

    def test_persistence_error_maps_to_safe_500(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        container.extraction_store.save = MagicMock(
            side_effect=PersistenceError("private storage details")
        )
        resp = client.post(
            "/api/v1/papers",
            files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
        )
        assert resp.status_code == 500
        assert resp.json()["detail"]["code"] == "persistence_error"
        assert "private storage details" not in str(resp.json())

    def test_value_error_from_extraction_uses_curated_safe_message(
        self,
        client: TestClient,
        fake_extraction_service,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        sensitive = (
            r"C:\private\research\secret-paper.pdf "
            "API_KEY_SENTINEL PAPER_TEXT_SENTINEL"
        )
        fake_extraction_service.extract.side_effect = ValueError(sensitive)

        with caplog.at_level("DEBUG"):
            resp = client.post(
                "/api/v1/papers",
                files={"file": ("test.pdf", self.VALID_PDF, "application/pdf")},
            )

        assert resp.status_code == 422
        assert resp.json() == {
            "detail": {
                "code": "extraction_failed",
                "message": "The uploaded PDF could not be processed.",
            }
        }
        response_body = resp.text
        response_headers = str(resp.headers)
        log_text = caplog.text
        for sentinel in (
            r"C:\private\research\secret-paper.pdf",
            "API_KEY_SENTINEL",
            "PAPER_TEXT_SENTINEL",
        ):
            assert sentinel not in response_body
            assert sentinel not in response_headers
            assert sentinel not in log_text


# ---------------------------------------------------------------------------
# Research-map retrieval tests
# ---------------------------------------------------------------------------


class TestGetResearchMap:
    def test_latest_succeeded_job_returns_map(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        # Create an extraction
        container.extraction_store.save(
            ExtractionResult(
                paper_id="p-map-ret",
                filename="test.pdf",
                chunks=[Chunk(chunk_id="p-map-ret-p1-1", page=1, text="Text.")],
            )
        )
        # Create a succeeded job
        job = container.job_store.create("p-map-ret")
        container.job_store.mark_running(job.job_id)
        # Save a research map
        rm = ResearchMap(
            paper_id="p-map-ret",
            research_question="Q?",
            findings=[
                Finding(
                    statement="F1", evidence=[Evidence(chunk_id="p-map-ret-p1-1", page=1, excerpt="Text.")],
                    confidence="high",
                ),
                Finding(
                    statement="F2", evidence=[Evidence(chunk_id="p-map-ret-p1-1", page=1, excerpt="Text.")],
                    confidence="partial",
                ),
                Finding(
                    statement="F3", evidence=[Evidence(chunk_id="p-map-ret-p1-1", page=1, excerpt="Text.")],
                    confidence="high",
                ),
            ],
            limitations=["Limitation."],
            disclaimer=_TEST_DISCLAIMER,
        )
        container.research_map_store.save(rm)
        container.job_store.mark_succeeded(job.job_id)

        resp = client.get("/api/v1/papers/p-map-ret/research-map")
        assert resp.status_code == 200
        data = resp.json()
        assert data["research_question"] == "Q?"
        assert len(data["findings"]) == 3

    def test_no_job_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/papers/unknown-paper/research-map")
        assert resp.status_code == 404

    def test_succeeded_job_without_map_returns_404(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        job = container.job_store.create("p-no-map")
        container.job_store.mark_running(job.job_id)
        container.job_store.mark_succeeded(job.job_id)

        resp = client.get("/api/v1/papers/p-no-map/research-map")
        assert resp.status_code == 404

    def test_retrieval_performs_no_provider_construction(
        self, client: TestClient, container: ServiceContainer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider_factory = MagicMock(side_effect=AssertionError("provider must not be built"))
        container.job_runner_factory = provider_factory
        resp = client.get("/api/v1/papers/no-map/research-map")
        assert resp.status_code == 404
        provider_factory.assert_not_called()

    def test_latest_running_job_hides_map(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        # Extraction exists
        container.extraction_store.save(
            ExtractionResult(
                paper_id="p-running",
                filename="test.pdf",
                chunks=[Chunk(chunk_id="p-running-p1-1", page=1, text="Text.")],
            )
        )
        # Old succeeded job
        old_job = container.job_store.create("p-running")
        container.job_store.mark_running(old_job.job_id)
        container.job_store.mark_succeeded(old_job.job_id)
        # New running job
        new_job = container.job_store.create("p-running")
        container.job_store.mark_running(new_job.job_id)
        # Map exists
        rm = ResearchMap(
            paper_id="p-running",
            research_question="Q?",
            findings=[
                Finding(
                    statement="F1", evidence=[Evidence(chunk_id="p-running-p1-1", page=1, excerpt="Text.")],
                    confidence="high",
                ),
                Finding(
                    statement="F2", evidence=[Evidence(chunk_id="p-running-p1-1", page=1, excerpt="Text.")],
                    confidence="partial",
                ),
                Finding(
                    statement="F3", evidence=[Evidence(chunk_id="p-running-p1-1", page=1, excerpt="Text.")],
                    confidence="high",
                ),
            ],
            limitations=["Limitation."],
            disclaimer=_TEST_DISCLAIMER,
        )
        container.research_map_store.save(rm)

        resp = client.get("/api/v1/papers/p-running/research-map")
        assert resp.status_code == 404  # Latest job is running

    def test_latest_failed_job_hides_map(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        container.extraction_store.save(
            ExtractionResult(
                paper_id="p-failed",
                filename="test.pdf",
                chunks=[Chunk(chunk_id="p-failed-p1-1", page=1, text="Text.")],
            )
        )
        job = container.job_store.create("p-failed")
        container.job_store.mark_running(job.job_id)
        container.job_store.mark_failed(job.job_id, error_code="map_generation_failed")
        # Map exists (orphan)
        container.research_map_store.save(
            ResearchMap(
                paper_id="p-failed",
                research_question="Q?",
                findings=[
                    Finding(statement="F1", evidence=[Evidence(chunk_id="p-failed-p1-1", page=1, excerpt="Text.")], confidence="high"),
                    Finding(statement="F2", evidence=[Evidence(chunk_id="p-failed-p1-1", page=1, excerpt="Text.")], confidence="partial"),
                    Finding(statement="F3", evidence=[Evidence(chunk_id="p-failed-p1-1", page=1, excerpt="Text.")], confidence="high"),
                ],
                limitations=["Lim."],
                disclaimer=_TEST_DISCLAIMER,
            )
        )

        resp = client.get("/api/v1/papers/p-failed/research-map")
        assert resp.status_code == 404

    def test_disclaimer_unchanged(
        self, client: TestClient, container: ServiceContainer
    ) -> None:
        container.extraction_store.save(
            ExtractionResult(
                paper_id="p-disc",
                filename="test.pdf",
                chunks=[Chunk(chunk_id="p-disc-p1-1", page=1, text="Text.")],
            )
        )
        job = container.job_store.create("p-disc")
        container.job_store.mark_running(job.job_id)
        container.research_map_store.save(
            ResearchMap(
                paper_id="p-disc",
                research_question="Q?",
                findings=[
                    Finding(statement="F1", evidence=[Evidence(chunk_id="p-disc-p1-1", page=1, excerpt="Text.")], confidence="high"),
                    Finding(statement="F2", evidence=[Evidence(chunk_id="p-disc-p1-1", page=1, excerpt="Text.")], confidence="partial"),
                    Finding(statement="F3", evidence=[Evidence(chunk_id="p-disc-p1-1", page=1, excerpt="Text.")], confidence="high"),
                ],
                limitations=["Lim."],
                disclaimer=_TEST_DISCLAIMER,
            )
        )
        container.job_store.mark_succeeded(job.job_id)

        resp = client.get("/api/v1/papers/p-disc/research-map")
        assert resp.status_code == 200
        assert resp.json()["disclaimer"] == _TEST_DISCLAIMER