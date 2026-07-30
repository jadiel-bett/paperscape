"""HTTP-level integration tests for the PaperScape backend pipeline.

These tests exercise real FastAPI routes, real PDF extraction, real repositories,
the real research-map service, and the real job runner.  The only fake is the
``LLMProvider`` so tests never require watsonx credentials or live network calls.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

import fitz
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import ServiceContainer
from app.main import create_app
from app.models.job import JobStatus
from app.repositories import ExtractionStore, JobStore, ResearchMapStore
from app.services.extraction import ExtractionService
from app.services.llm_provider import LLMProvider, LLMProviderError
from app.services.research_map import ResearchMapService
from app.services.research_map_job_runner import ResearchMapJobRunner

_DISCLAIMER = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)


def _make_selectable_pdf() -> bytes:
    """Return a tiny deterministic selectable-text PDF generated with PyMuPDF."""
    doc = fitz.open()
    try:
        doc.set_metadata(
            {
                "title": "PaperScape deterministic integration fixture",
                "author": "PaperScape",
                "subject": "Synthetic selectable-text research paper",
                "keywords": "paperscape,integration,test",
                "creator": "PaperScape",
                "producer": "PyMuPDF",
                "creationDate": "D:20250101000000+00'00'",
                "modDate": "D:20250101000000+00'00'",
            }
        )
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            "PaperScape test study\n"
            "Research question: Does a structured research map preserve evidence?\n"
            "Finding one: The prototype extracts selectable text from uploaded PDFs.\n"
            "Finding two: Each finding keeps chunk identifiers and one-based pages.\n"
            "Finding three: Limitations remain visible for expert review.\n"
            "Limitation: This synthetic document has one page and a small sample.",
            fontsize=11,
        )
        return doc.tobytes(no_new_id=True)
    finally:
        doc.close()


def _extract_context(prompt: str) -> list[dict[str, Any]]:
    """Extract the serialized paper-context JSON embedded in the real prompt."""
    match = re.search(
        r"<PAPER_CONTENT>\s*(\[.*?\])\s*</PAPER_CONTENT>",
        prompt,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("Prompt did not contain serialized paper context JSON")
    context = json.loads(match.group(1))
    assert isinstance(context, list)
    assert context
    return context


class DeterministicProvider(LLMProvider):
    """Fake provider returning valid evidence-ID JSON from the real catalogue."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        self.call_count += 1
        assert max_tokens > 0
        assert 0.0 <= temperature <= 2.0
        context = _extract_context(prompt)
        evidence_ids = [item["evidence_id"] for item in context]
        assert len(evidence_ids) >= 2
        if len(evidence_ids) >= 3:
            finding_evidence_ids = [
                [evidence_ids[0]],
                [evidence_ids[1]],
                [evidence_ids[2]],
            ]
        else:
            finding_evidence_ids = [
                [evidence_ids[0]],
                [evidence_ids[1]],
                evidence_ids,
            ]

        def evidence(ids: list[str]) -> list[dict[str, Any]]:
            return [{"evidence_id": evidence_id} for evidence_id in ids]

        return json.dumps(
            {
                "research_question": {
                    "statement": "Does a structured research map preserve evidence?",
                    "evidence": evidence([evidence_ids[0]]),
                },
                "findings": [
                    {
                        "statement": "The prototype extracts selectable text from uploaded PDFs.",
                        "evidence": evidence(finding_evidence_ids[0]),
                        "confidence": "high",
                    },
                    {
                        "statement": "Findings keep chunk identifiers and one-based page provenance.",
                        "evidence": evidence(finding_evidence_ids[1]),
                        "confidence": "partial",
                    },
                    {
                        "statement": "Limitations remain visible for expert review.",
                        "evidence": evidence(finding_evidence_ids[2]),
                        "confidence": "high",
                    },
                ],
                "limitations": [
                    {
                        "statement": "The test document is synthetic and intentionally small.",
                        "evidence": evidence([evidence_ids[0]]),
                    }
                ],
            }
        )


class FailingProvider(LLMProvider):
    """Fake provider that fails through the real runner/provider-error path."""

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        _extract_context(prompt)
        raise LLMProviderError("raw provider outage secret detail")


def _build_container(
    settings: Settings,
    provider: LLMProvider,
) -> ServiceContainer:
    job_store = JobStore(settings.db_path)
    extraction_store = ExtractionStore(settings.db_path)
    research_map_store = ResearchMapStore(settings.db_path)

    def runner_factory() -> ResearchMapJobRunner:
        return ResearchMapJobRunner(
            job_store=job_store,
            extraction_store=extraction_store,
            research_map_store=research_map_store,
            research_map_service=ResearchMapService(provider),
        )

    return ServiceContainer(
        settings=settings,
        extraction_service=ExtractionService(),
        job_store=job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        paper_id_factory=lambda: "11111111-1111-4111-8111-111111111111",
        job_runner_factory=runner_factory,
        job_creation_lock=threading.Lock(),
    )


def _make_client(
    tmp_path: Path,
    provider: LLMProvider,
) -> tuple[TestClient, ServiceContainer]:
    db_path = tmp_path / "pipeline.db"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_path}",
        cors_origins="http://localhost:8080",
    )
    container = _build_container(settings, provider)
    app = create_app(settings, container=container)
    return TestClient(app), container


def _upload_and_create_job(
    client: TestClient,
    pdf_bytes: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    upload = client.post(
        "/api/v1/papers",
        files={"file": ("pipeline.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    upload_data = upload.json()

    create_job = client.post(
        f"/api/v1/papers/{upload_data['paper_id']}/research-map-jobs"
    )
    assert create_job.status_code == 202
    return upload_data, create_job.json()


def test_pipeline_generates_and_persists_research_map(tmp_path: Path) -> None:
    provider = DeterministicProvider()
    client, container = _make_client(tmp_path, provider)
    pdf_bytes = _make_selectable_pdf()
    assert pdf_bytes == _make_selectable_pdf()
    assert pdf_bytes.startswith(b"%PDF-")

    with client:
        upload_data, job_data = _upload_and_create_job(client, pdf_bytes)

        assert upload_data["paper_id"] == "11111111-1111-4111-8111-111111111111"
        assert upload_data["filename"] == "pipeline.pdf"
        assert upload_data["page_count"] >= 1
        assert upload_data["chunk_count"] >= 1
        assert job_data["paper_id"] == upload_data["paper_id"]
        assert job_data["status"] == JobStatus.PENDING

        persisted_extraction = container.extraction_store.get(upload_data["paper_id"])
        assert persisted_extraction is not None
        assert persisted_extraction.filename == "pipeline.pdf"
        assert persisted_extraction.chunks

        status = client.get(f"/api/v1/jobs/{job_data['job_id']}")
        assert status.status_code == 200
        status_data = status.json()
        assert status_data["status"] == JobStatus.SUCCEEDED
        assert status_data["error"] is None
        assert provider.call_count == 1

        map_response = client.get(
            f"/api/v1/papers/{upload_data['paper_id']}/research-map"
        )
        assert map_response.status_code == 200
        research_map = map_response.json()

        assert research_map["paper_id"] == upload_data["paper_id"]
        assert research_map["research_question"]
        assert len(research_map["findings"]) == 3
        assert research_map["limitations"]
        assert research_map["disclaimer"] == _DISCLAIMER

        real_chunk_ids = {chunk.chunk_id for chunk in persisted_extraction.chunks}
        for finding in research_map["findings"]:
            assert finding["confidence"] in {"high", "partial"}
            assert finding["evidence"]
            for evidence in finding["evidence"]:
                assert evidence["chunk_id"] in real_chunk_ids
                assert evidence["page"] >= 1
                assert evidence["excerpt"]

        persisted_map = container.research_map_store.get(upload_data["paper_id"])
        assert persisted_map is not None
        assert persisted_map.paper_id == upload_data["paper_id"]
        assert len(persisted_map.findings) == 3


def test_pipeline_provider_failure_is_safe(tmp_path: Path) -> None:
    client, container = _make_client(tmp_path, FailingProvider())
    pdf_bytes = _make_selectable_pdf()

    with client:
        upload_data, job_data = _upload_and_create_job(client, pdf_bytes)

        status = client.get(f"/api/v1/jobs/{job_data['job_id']}")
        assert status.status_code == 200
        status_data = status.json()
        assert status_data["job_id"] == job_data["job_id"]
        assert status_data["paper_id"] == upload_data["paper_id"]
        assert status_data["status"] == JobStatus.FAILED
        assert status_data["error"] == "llm_provider_error"
        assert "raw provider outage secret detail" not in status.text
        assert "map_generation_failed" not in status.text

        persisted_job = container.job_store.get(job_data["job_id"])
        assert persisted_job is not None
        assert persisted_job.status == JobStatus.FAILED
        assert persisted_job.error == "llm_provider_error"
        assert persisted_job.error != "raw provider outage secret detail"

        map_response = client.get(
            f"/api/v1/papers/{upload_data['paper_id']}/research-map"
        )
        assert map_response.status_code == 404
        assert map_response.json()["detail"]["code"] == "map_not_found"
