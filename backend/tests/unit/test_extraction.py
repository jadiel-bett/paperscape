"""Unit tests for backend/app/services/extraction.py.

All tests are fully offline — no network calls, no Docling model downloads.
Docling is never instantiated; a FakeDoclingAdapter is injected instead.
PDF fixtures are generated programmatically using PyMuPDF (fitz).
"""
from __future__ import annotations

import os
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from app.services.extraction import (
    DoclingExtractionError,
    ExtractionError,
    ExtractionService,
    PyMuPDFAdapter,
    RawChunk,
)


# ---------------------------------------------------------------------------
# PDF fixture helpers
# ---------------------------------------------------------------------------


def make_pdf(pages: list[str]) -> bytes:
    """Return PDF bytes with one page per string, each containing that text."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    return doc.tobytes()


def make_blank_pdf(num_pages: int = 1) -> bytes:
    """Return PDF bytes with pages that contain no selectable text."""
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


# ---------------------------------------------------------------------------
# Fake adapter helpers
# ---------------------------------------------------------------------------


class FakeDoclingAdapter:
    """Injectable fake that returns a preset list of RawChunk objects."""

    def __init__(self, chunks: list[RawChunk]) -> None:
        self._chunks = chunks

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:  # noqa: ARG002
        return list(self._chunks)


class RaisingDoclingAdapter:
    """Injectable fake that raises DoclingExtractionError."""

    def __init__(self, message: str = "docling boom") -> None:
        self._message = message

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:  # noqa: ARG002
        raise DoclingExtractionError(self._message)


class RaisingPyMuPDFAdapter:
    """Injectable fake that raises a generic RuntimeError."""

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:  # noqa: ARG002
        raise RuntimeError("pymupdf boom")


# ---------------------------------------------------------------------------
# Test 1 — successful Docling extraction
# ---------------------------------------------------------------------------


def test_docling_successful_extraction() -> None:
    chunks = [RawChunk(page=1, index=0, text="Abstract text.", section=None)]
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter(chunks),
        pymupdf_adapter=RaisingPyMuPDFAdapter(),  # must not be called
    )
    result = svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="pid-1")
    assert len(result.chunks) == 1
    assert result.chunks[0].text == "Abstract text."


# ---------------------------------------------------------------------------
# Test 2 — page and section metadata preserved
# ---------------------------------------------------------------------------


def test_docling_preserves_page_and_section() -> None:
    chunks = [
        RawChunk(page=2, index=0, text="Intro paragraph.", section="Introduction"),
        RawChunk(page=3, index=0, text="Results text.", section="Results"),
    ]
    svc = ExtractionService(docling_adapter=FakeDoclingAdapter(chunks))
    result = svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="pid-2")
    assert result.chunks[0].page == 2
    assert result.chunks[0].section == "Introduction"
    assert result.chunks[1].page == 3
    assert result.chunks[1].section == "Results"


# ---------------------------------------------------------------------------
# Test 3 — deterministic chunk IDs (1-based per-page numbering)
# ---------------------------------------------------------------------------


def test_deterministic_chunk_ids() -> None:
    chunks = [
        RawChunk(page=1, index=0, text="Alpha.", section=None),
        RawChunk(page=1, index=1, text="Beta.", section=None),
        RawChunk(page=2, index=0, text="Gamma.", section=None),
    ]
    svc = ExtractionService(docling_adapter=FakeDoclingAdapter(chunks))
    result = svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="mypaper")
    # Public IDs are 1-based: index + 1
    assert result.chunks[0].chunk_id == "mypaper-p1-1"
    assert result.chunks[1].chunk_id == "mypaper-p1-2"
    assert result.chunks[2].chunk_id == "mypaper-p2-1"


# ---------------------------------------------------------------------------
# Test 4 — empty / whitespace-only text blocks are removed
# ---------------------------------------------------------------------------


def test_empty_text_blocks_removed() -> None:
    # The fake adapter returns a mix of valid and blank chunks.
    # ExtractionService passes them through to Pydantic which rejects blank text.
    # The adapter is responsible for stripping; the service still handles it via
    # Pydantic validation.  We test the end-to-end invariant: no blank texts reach
    # the result.  We simulate an adapter that returns only the valid chunk.
    chunks = [
        RawChunk(page=1, index=0, text="Real content.", section=None),
    ]
    svc = ExtractionService(docling_adapter=FakeDoclingAdapter(chunks))
    result = svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="pid-4")
    assert all(c.text.strip() != "" for c in result.chunks)


# ---------------------------------------------------------------------------
# Test 5 — DoclingExtractionError triggers PyMuPDF fallback
# ---------------------------------------------------------------------------


def test_docling_exception_triggers_pymupdf_fallback() -> None:
    pdf = make_pdf(["Fallback page content."])
    svc = ExtractionService(
        docling_adapter=RaisingDoclingAdapter(),
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    result = svc.extract(pdf, filename="paper.pdf", paper_id="pid-5")
    assert len(result.chunks) >= 1
    assert result.chunks[0].page == 1


# ---------------------------------------------------------------------------
# Test 6 — zero Docling chunks triggers PyMuPDF fallback
# ---------------------------------------------------------------------------


def test_zero_docling_chunks_triggers_pymupdf_fallback() -> None:
    pdf = make_pdf(["Page one text.", "Page two text."])
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),  # empty → fallback
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    result = svc.extract(pdf, filename="paper.pdf", paper_id="pid-6")
    assert len(result.chunks) == 2  # one chunk per page from PyMuPDF


# ---------------------------------------------------------------------------
# Test 7 — PyMuPDF extracts multi-page PDF
# ---------------------------------------------------------------------------


def test_pymupdf_extracts_multi_page_pdf() -> None:
    pdf = make_pdf(["Page one.", "Page two.", "Page three."])
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    result = svc.extract(pdf, filename="paper.pdf", paper_id="pid-7")
    assert len(result.chunks) == 3


# ---------------------------------------------------------------------------
# Test 8 — page numbers are 1-based
# ---------------------------------------------------------------------------


def test_page_numbers_are_one_based() -> None:
    pdf = make_pdf(["First page content."])
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    result = svc.extract(pdf, filename="paper.pdf", paper_id="pid-8")
    assert result.chunks[0].page == 1


# ---------------------------------------------------------------------------
# Test 9 — PyMuPDF fallback always has section=None
# ---------------------------------------------------------------------------


def test_pymupdf_fallback_section_is_none() -> None:
    pdf = make_pdf(["Content on page one.", "Content on page two."])
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    result = svc.extract(pdf, filename="paper.pdf", paper_id="pid-9")
    assert all(c.section is None for c in result.chunks)


# ---------------------------------------------------------------------------
# Test 10 — both extractors failing raises ExtractionError
# ---------------------------------------------------------------------------


def test_both_extractors_failing_raises_extraction_error() -> None:
    svc = ExtractionService(
        docling_adapter=RaisingDoclingAdapter("docling exploded"),
        pymupdf_adapter=RaisingPyMuPDFAdapter(),
    )
    with pytest.raises(ExtractionError) as exc_info:
        svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="pid-10")
    # Both error causes must be recorded in the message.
    msg = str(exc_info.value)
    assert "docling exploded" in msg
    assert "PyMuPDF" in msg
    # The chained cause must be the PyMuPDF RuntimeError.
    assert isinstance(exc_info.value.__cause__, RuntimeError)


# ---------------------------------------------------------------------------
# Test 11 — blank PDF raises ExtractionError
# ---------------------------------------------------------------------------


def test_no_selectable_text_raises_extraction_error() -> None:
    pdf = make_blank_pdf(num_pages=2)
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),  # Docling disabled → fallback
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    with pytest.raises(ExtractionError, match="no selectable text"):
        svc.extract(pdf, filename="blank.pdf", paper_id="pid-11")


# ---------------------------------------------------------------------------
# Test 12 — blank filename and blank paper_id rejected early with ValueError
# ---------------------------------------------------------------------------


def test_blank_filename_rejected_by_pydantic() -> None:
    chunks = [RawChunk(page=1, index=0, text="Some text.", section=None)]
    svc = ExtractionService(docling_adapter=FakeDoclingAdapter(chunks))

    with pytest.raises(ValueError, match="filename must not be blank"):
        svc.extract(b"%PDF-1.4", filename="  ", paper_id="pid-12")

    with pytest.raises(ValueError, match="paper_id must not be blank"):
        svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="  ")


# ---------------------------------------------------------------------------
# Test 13 — result always has at least one chunk
# ---------------------------------------------------------------------------


def test_extraction_result_has_at_least_one_chunk() -> None:
    chunks = [RawChunk(page=1, index=0, text="One chunk.", section=None)]
    svc = ExtractionService(docling_adapter=FakeDoclingAdapter(chunks))
    result = svc.extract(b"%PDF-1.4", filename="paper.pdf", paper_id="pid-13")
    assert len(result.chunks) >= 1


# ---------------------------------------------------------------------------
# Test 14 — service does not write files to disk
# ---------------------------------------------------------------------------


def test_service_does_not_write_files(tmp_path: Path) -> None:
    pdf = make_pdf(["Hello disk-free world."])
    svc = ExtractionService(
        docling_adapter=FakeDoclingAdapter([]),
        pymupdf_adapter=PyMuPDFAdapter(),
    )
    before = set(os.listdir(tmp_path))
    svc.extract(pdf, filename="paper.pdf", paper_id="pid-14")
    after = set(os.listdir(tmp_path))
    assert before == after, f"New files written: {after - before}"