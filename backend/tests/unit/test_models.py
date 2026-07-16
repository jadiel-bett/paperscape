from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.job import Job, JobCreateResponse, JobStatus, JobStatusResponse
from app.models.paper import Chunk, ExtractionResult, UploadResponse
from app.models.research_map import Evidence, Finding, ResearchMap

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_EVIDENCE = Evidence(chunk_id="p1-p1-0", page=1, excerpt="Some text.")
_VALID_FINDING = Finding(
    statement="Finding one.",
    evidence=[_VALID_EVIDENCE],
    confidence="high",
)
_THREE_FINDINGS = [_VALID_FINDING, _VALID_FINDING, _VALID_FINDING]
_NOW = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------


def test_chunk_valid() -> None:
    c = Chunk(chunk_id="abc-p1-0", page=1, text="Hello world")
    assert c.chunk_id == "abc-p1-0"
    assert c.section is None


def test_chunk_page_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        Chunk(chunk_id="x", page=0, text="t")


def test_chunk_page_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        Chunk(chunk_id="x", page=-1, text="t")


def test_chunk_section_none_accepted() -> None:
    c = Chunk(chunk_id="x", page=1, text="t", section=None)
    assert c.section is None


def test_chunk_missing_chunk_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Chunk(page=1, text="t")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------


def test_extraction_result_valid() -> None:
    chunk = Chunk(chunk_id="p-p1-0", page=1, text="body")
    er = ExtractionResult(paper_id="pid", filename="paper.pdf", chunks=[chunk])
    assert len(er.chunks) == 1


def test_extraction_result_empty_chunks_accepted() -> None:
    er = ExtractionResult(paper_id="pid", filename="paper.pdf", chunks=[])
    assert er.chunks == []


# ---------------------------------------------------------------------------
# UploadResponse
# ---------------------------------------------------------------------------


def test_upload_response_zero_counts_accepted() -> None:
    r = UploadResponse(paper_id="p", filename="f.pdf", page_count=0, chunk_count=0)
    assert r.page_count == 0


def test_upload_response_negative_page_count_rejected() -> None:
    with pytest.raises(ValidationError):
        UploadResponse(paper_id="p", filename="f.pdf", page_count=-1, chunk_count=0)


def test_upload_response_negative_chunk_count_rejected() -> None:
    with pytest.raises(ValidationError):
        UploadResponse(paper_id="p", filename="f.pdf", page_count=1, chunk_count=-1)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_valid() -> None:
    e = Evidence(chunk_id="c", page=1, excerpt="text")
    assert e.excerpt == "text"


def test_evidence_excerpt_exactly_300_accepted() -> None:
    Evidence(chunk_id="c", page=1, excerpt="x" * 300)


def test_evidence_excerpt_301_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(chunk_id="c", page=1, excerpt="x" * 301)


def test_evidence_page_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(chunk_id="c", page=0, excerpt="text")


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


def test_finding_valid_confidence_values() -> None:
    for conf in ("high", "partial", "uncertain"):
        f = Finding(statement="s", evidence=[_VALID_EVIDENCE], confidence=conf)  # type: ignore[arg-type]
        assert f.confidence == conf


def test_finding_invalid_confidence_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(statement="s", evidence=[_VALID_EVIDENCE], confidence="unknown")  # type: ignore[arg-type]


def test_finding_empty_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(statement="s", evidence=[], confidence="high")


# ---------------------------------------------------------------------------
# ResearchMap
# ---------------------------------------------------------------------------


def test_research_map_three_findings_accepted() -> None:
    m = ResearchMap(
        paper_id="p",
        research_question="q",
        findings=_THREE_FINDINGS,
        limitations=["l1"],
    )
    assert len(m.findings) == 3


def test_research_map_two_findings_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchMap(
            paper_id="p",
            research_question="q",
            findings=[_VALID_FINDING, _VALID_FINDING],
            limitations=[],
        )


def test_research_map_four_findings_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchMap(
            paper_id="p",
            research_question="q",
            findings=[_VALID_FINDING] * 4,
            limitations=[],
        )


def test_research_map_default_disclaimer() -> None:
    m = ResearchMap(
        paper_id="p",
        research_question="q",
        findings=_THREE_FINDINGS,
        limitations=[],
    )
    assert m.disclaimer == "This map does not replace expert review."


def test_research_map_custom_disclaimer_accepted() -> None:
    m = ResearchMap(
        paper_id="p",
        research_question="q",
        findings=_THREE_FINDINGS,
        limitations=[],
        disclaimer="Custom note.",
    )
    assert m.disclaimer == "Custom note."


# ---------------------------------------------------------------------------
# JobStatus (StrEnum)
# ---------------------------------------------------------------------------


def test_job_status_str_equality() -> None:
    assert JobStatus.PENDING == "pending"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.SUCCEEDED == "succeeded"
    assert JobStatus.FAILED == "failed"


def test_job_with_enum_member() -> None:
    j = Job(
        job_id="j1",
        paper_id="p1",
        status=JobStatus.PENDING,
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert j.status == JobStatus.PENDING


def test_job_with_plain_string_coerced() -> None:
    j = Job(
        job_id="j1",
        paper_id="p1",
        status="pending",  # type: ignore[arg-type]
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert j.status == JobStatus.PENDING


def test_job_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Job(
            job_id="j1",
            paper_id="p1",
            status="invalid",  # type: ignore[arg-type]
            created_at=_NOW,
            updated_at=_NOW,
        )


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


def test_job_error_defaults_to_none() -> None:
    j = Job(
        job_id="j1",
        paper_id="p1",
        status=JobStatus.PENDING,
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert j.error is None


def test_job_accepts_datetime_fields() -> None:
    now = datetime.now(timezone.utc)
    j = Job(
        job_id="j1",
        paper_id="p1",
        status=JobStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )
    assert j.created_at == now


# ---------------------------------------------------------------------------
# JobCreateResponse
# ---------------------------------------------------------------------------


def test_job_create_response_valid() -> None:
    r = JobCreateResponse(job_id="j1", paper_id="p1", status=JobStatus.PENDING)
    assert r.status == JobStatus.PENDING


# ---------------------------------------------------------------------------
# JobStatusResponse
# ---------------------------------------------------------------------------


def test_job_status_response_valid() -> None:
    r = JobStatusResponse(
        job_id="j1",
        paper_id="p1",
        status=JobStatus.SUCCEEDED,
        created_at=_NOW,
        updated_at=_NOW,
    )
    assert r.job_id == "j1"


def test_job_status_response_has_all_job_fields() -> None:
    """JobStatusResponse inherits all fields from Job."""
    job_fields = set(Job.model_fields.keys())
    response_fields = set(JobStatusResponse.model_fields.keys())
    assert job_fields == response_fields
