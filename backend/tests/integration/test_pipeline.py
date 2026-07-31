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
from app.repositories import (
    ExtractionStore,
    GenerationMode,
    JobStore,
    ResearchMapStore,
)
from app.services.extraction import ExtractionService
from app.services.extractive_research_map import ExtractiveResearchMapService
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
        pages = (
            "PaperScape test study.\n"
            "Research question: Does a structured research map preserve evidence?\n"
            "Results showed the prototype was associated with reliable selectable-text "
            "extraction from uploaded PDFs.",
            "Each finding was associated with retained chunk identifiers and one-based "
            "pages.\n"
            "This synthetic document has three pages and a small sample.",
            "Limitations were more likely to remain visible during expert review.",
        )
        for text in pages:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=11)
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

        def evidence_id_containing(required_phrase: str) -> str:
            """Select one unambiguous catalogue span by exact source phrase."""
            matches = [
                item["evidence_id"]
                for item in context
                if required_phrase.casefold() in item["text"].casefold()
            ]
            if not matches:
                raise AssertionError(
                    f"No evidence span contains fixture phrase {required_phrase!r}."
                )
            if len(matches) > 1:
                raise AssertionError(
                    f"Fixture phrase {required_phrase!r} matches multiple evidence spans: "
                    f"{matches!r}."
                )
            return matches[0]

        research_question_evidence_id = evidence_id_containing(
            "structured research map preserve evidence"
        )
        finding_evidence_ids = [
            [evidence_id_containing("selectable-text extraction")],
            [evidence_id_containing("chunk identifiers and one-based pages")],
            [evidence_id_containing("limitations were more likely")],
        ]
        limitation_evidence_id = evidence_id_containing(
            "synthetic document has three pages and a small sample"
        )

        def evidence(ids: list[str]) -> list[dict[str, Any]]:
            return [{"evidence_id": evidence_id} for evidence_id in ids]

        return json.dumps(
            {
                "research_question": {
                    "statement": "Does a structured research map preserve evidence?",
                    "evidence": evidence([research_question_evidence_id]),
                },
                "findings": [
                    {
                        "statement": (
                            "Results showed the prototype was associated with reliable "
                            "selectable-text extraction from uploaded PDFs."
                        ),
                        "evidence": evidence(finding_evidence_ids[0]),
                        "confidence": "high",
                    },
                    {
                        "statement": (
                            "Each finding was associated with retained chunk identifiers "
                            "and one-based pages."
                        ),
                        "evidence": evidence(finding_evidence_ids[1]),
                        "confidence": "partial",
                    },
                    {
                        "statement": (
                            "Limitations were more likely to remain visible during expert review."
                        ),
                        "evidence": evidence(finding_evidence_ids[2]),
                        "confidence": "high",
                    },
                ],
                "limitations": [
                    {
                        "statement": "The test document is synthetic and intentionally small.",
                        "evidence": evidence([limitation_evidence_id]),
                    }
                ],
            }
        )


class FailingProvider(LLMProvider):
    """Fake provider that fails through the real runner/provider-error path."""

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
        _extract_context(prompt)
        raise LLMProviderError("raw provider outage secret detail")


def _build_container(
    settings: Settings,
    provider: LLMProvider,
) -> ServiceContainer:
    job_store = JobStore(settings.db_path)
    extraction_store = ExtractionStore(settings.db_path)
    research_map_store = ResearchMapStore(settings.db_path)
    extractive_fallback_factory = ExtractiveResearchMapService

    def runner_factory() -> ResearchMapJobRunner:
        return ResearchMapJobRunner(
            job_store=job_store,
            extraction_store=extraction_store,
            research_map_store=research_map_store,
            research_map_service=ResearchMapService(provider),
            extractive_fallback_factory=extractive_fallback_factory,
        )

    return ServiceContainer(
        settings=settings,
        extraction_service=ExtractionService(),
        job_store=job_store,
        extraction_store=extraction_store,
        research_map_store=research_map_store,
        extractive_fallback_factory=extractive_fallback_factory,
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
        finding_evidence_sets: list[frozenset[tuple[str, int, str]]] = []
        expected_anchors = [
            "selectable-text extraction",
            "chunk identifiers and one-based pages",
            "limitations were more likely",
        ]
        for finding, expected_anchor in zip(
            research_map["findings"], expected_anchors, strict=True
        ):
            assert finding["confidence"] in {"high", "partial"}
            assert finding["evidence"]
            finding_evidence_sets.append(
                frozenset(
                    (
                        evidence["chunk_id"],
                        evidence["page"],
                        evidence["excerpt"],
                    )
                    for evidence in finding["evidence"]
                )
            )
            assert any(
                expected_anchor.casefold() in evidence["excerpt"].casefold()
                for evidence in finding["evidence"]
            )
            for evidence in finding["evidence"]:
                assert evidence["chunk_id"] in real_chunk_ids
                assert evidence["page"] >= 1
                assert evidence["excerpt"]

        assert len(set(finding_evidence_sets)) == 3

        persisted_map = container.research_map_store.get(upload_data["paper_id"])
        assert persisted_map is not None
        assert persisted_map.paper_id == upload_data["paper_id"]
        assert len(persisted_map.findings) == 3


def test_pipeline_provider_failure_is_safe(tmp_path: Path) -> None:
    provider = FailingProvider()
    client, container = _make_client(tmp_path, provider)
    pdf_bytes = _make_selectable_pdf()

    with client:
        upload_data, job_data = _upload_and_create_job(client, pdf_bytes)

        status = client.get(f"/api/v1/jobs/{job_data['job_id']}")
        assert status.status_code == 200
        status_data = status.json()
        assert status_data["job_id"] == job_data["job_id"]
        assert status_data["paper_id"] == upload_data["paper_id"]
        assert status_data["status"] == JobStatus.SUCCEEDED
        assert status_data["error"] is None
        assert "raw provider outage secret detail" not in status.text
        assert "map_generation_failed" not in status.text
        assert provider.call_count == 1

        persisted_job = container.job_store.get(job_data["job_id"])
        assert persisted_job is not None
        assert persisted_job.status == JobStatus.SUCCEEDED
        assert persisted_job.error is None
        assert persisted_job.error != "raw provider outage secret detail"

        map_response = client.get(
            f"/api/v1/papers/{upload_data['paper_id']}/research-map"
        )
        assert map_response.status_code == 200
        public_map = map_response.json()
        assert set(public_map) == {
            "paper_id",
            "research_question",
            "findings",
            "limitations",
            "disclaimer",
        }
        assert len(public_map["findings"]) == 3
        extraction = container.extraction_store.require(upload_data["paper_id"])
        chunks = {chunk.chunk_id: chunk for chunk in extraction.chunks}
        for finding in public_map["findings"]:
            assert finding["confidence"] == "partial"
            assert len(finding["evidence"]) == 1
            evidence = finding["evidence"][0]
            assert evidence["excerpt"] == finding["statement"]
            assert evidence["chunk_id"] in chunks
            assert evidence["excerpt"] in " ".join(
                chunks[evidence["chunk_id"]].text.split()
            )

        metadata = container.research_map_store.get_generation_metadata(
            upload_data["paper_id"]
        )
        assert metadata is not None
        assert (
            metadata.generation_mode
            is GenerationMode.DETERMINISTIC_EXTRACTIVE_FALLBACK
        )
        assert metadata.fallback_reason == "llm_provider_error"


def test_pipeline_provider_and_fallback_failure_remains_safe(tmp_path: Path) -> None:
    provider = FailingProvider()
    client, container = _make_client(tmp_path, provider)
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text(
            (72, 72),
            "This document contains background text but no eligible reported findings.",
            fontsize=11,
        )
        pdf_bytes = doc.tobytes(no_new_id=True)
    finally:
        doc.close()

    with client:
        upload_data, job_data = _upload_and_create_job(client, pdf_bytes)
        status = client.get(f"/api/v1/jobs/{job_data['job_id']}")

        assert status.status_code == 200
        assert status.json()["status"] == JobStatus.FAILED
        assert status.json()["error"] == "llm_provider_error"
        assert "raw provider outage secret detail" not in status.text
        assert provider.call_count == 1
        assert container.research_map_store.get(upload_data["paper_id"]) is None
