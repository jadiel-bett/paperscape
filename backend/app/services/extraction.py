"""PDF extraction service.

Provides :class:`ExtractionService`, which attempts Docling extraction first
and falls back to PyMuPDF when Docling is unavailable or produces no chunks.

Architecture notes
------------------
- No FastAPI, SQLite, or watsonx imports anywhere in this module.
- Extraction is stateless; the caller is responsible for persistence.
- ``DoclingAdapter`` and ``PyMuPDFAdapter`` are injectable via
  ``ExtractionService.__init__`` so unit tests can substitute fakes without
  patching module-level imports.
- Docling is imported inside ``DoclingAdapter.extract_chunks()`` so the module
  loads successfully even when ``docling`` is not installed.
- One page can produce multiple chunks when Docling identifies several
  structural elements (paragraphs, list items, tables, etc.) on that page.
- Chunk indexes are **per-page** and **0-based** internally (in ``RawChunk``),
  but the public ``chunk_id`` converts them to **1-based** via
  ``f"{{paper_id}}-p{{page}}-{{index + 1}}"``.  The ``page`` component already
  encodes the page number in the chunk ID, so per-page uniqueness is sufficient.
- Duplicate chunk IDs (which can only arise from an adapter programming error)
  are detected by ``ExtractionService`` before constructing the result.
- No file is ever written to disk; Docling receives a ``DocumentStream``
  wrapping a ``BytesIO`` buffer.
- Complete document text is never written to logs.
"""
from __future__ import annotations

import dataclasses
import io
import logging
from collections import defaultdict

from app.models.paper import Chunk, ExtractionResult

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExtractionError(RuntimeError):
    """Raised when no usable text can be extracted from the PDF."""


class DoclingExtractionError(ExtractionError):
    """Raised when Docling is unavailable or fails during extraction.

    ``ExtractionService`` catches this by name and falls back to PyMuPDF.
    The message must never contain document text.
    """


# ---------------------------------------------------------------------------
# Internal transfer object
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class RawChunk:
    """Internal transfer object produced by adapters.

    ``page``   — 1-based page number; guaranteed reliable.
    ``index``  — per-page 0-based position; assigned after filtering.
                 The public chunk ID converts this to 1-based via index + 1.
    ``text``   — stripped, non-empty text.
    ``section``— nearest enclosing section heading, or ``None``.
    """

    page: int
    index: int
    text: str
    section: str | None


# ---------------------------------------------------------------------------
# Docling element allowlist
# ---------------------------------------------------------------------------

# Labels whose text content is emitted as a chunk.
_EMIT_LABELS: frozenset[str] = frozenset(
    [
        "title",
        "text",
        "paragraph",
        "list_item",
        "caption",
        "code",
        "formula",
        # TABLE is handled separately via export_to_markdown.
    ]
)

# Labels that update current_section but are not emitted as standalone chunks.
_SECTION_LABELS: frozenset[str] = frozenset(["section_header"])

# TABLE label string — handled as a special case.
_TABLE_LABEL: str = "table"


# ---------------------------------------------------------------------------
# DoclingAdapter
# ---------------------------------------------------------------------------


class DoclingAdapter:
    """Wraps Docling PDF conversion.

    Docling is imported lazily inside :meth:`extract_chunks` so this module
    loads even when ``docling`` is not installed.  Any failure from Docling
    is wrapped in :exc:`DoclingExtractionError`.

    Input
    -----
    The PDF is fed to Docling as a ``DocumentStream(name=..., stream=BytesIO(pdf_bytes))``.
    No temporary files are created.

    Element processing pipeline
    ---------------------------
    For each page the adapter:

    1. Collects items from ``doc.iterate_items()`` that are ``DocItem`` instances.
    2. Applies the element allowlist.
    3. Tracks ``current_section`` via ``SECTION_HEADER`` items.
    4. Serialises ``TABLE`` items via ``export_to_markdown`` + ``caption_text``.
    5. Strips whitespace; discards empty blocks.
    6. Skips items whose Docling provenance does not carry a valid page number.
    7. Assigns per-page 0-based indexes **after** all filtering.

    .. note::
       The ``isinstance(item, TextItem)`` guard used below has been verified
       against the pinned ``docling==2.37.0`` (via ``docling-core==2.87.1``):

       - ``ListItem``          is ``TextItem``  (MRO: ListItem → TextItem → …)
       - ``SectionHeaderItem`` is ``TextItem``  (MRO: SectionHeaderItem → TextItem → …)
       - ``CodeItem``          is ``TextItem``  (MRO: CodeItem → FloatingItem → TextItem → …)
       - ``FormulaItem``       is ``TextItem``  (MRO: FormulaItem → TextItem → …)

       ``GroupItem`` is **not** a ``TextItem`` and is intentionally excluded.
       ``PARAGRAPH`` and ``TEXT`` labels appear on ``TextItem`` instances at
       runtime (verified via smoke test).  If this is ever changed by a Docling
       upgrade the allowlist logic must be re-verified.
    """

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:  # noqa: ARG002
        try:
            from docling.datamodel.base_models import ConversionStatus
            from docling.datamodel.base_models import DocumentStream as DoclingStream
            from docling.document_converter import DocumentConverter
            from docling_core.types.doc.document import DocItem, TableItem, TextItem
        except ImportError as exc:
            raise DoclingExtractionError(
                f"Docling is not installed or cannot be imported: {type(exc).__name__}"
            ) from exc

        try:
            stream = DoclingStream(name=paper_id, stream=io.BytesIO(pdf_bytes))
            result = DocumentConverter().convert(stream)
        except Exception as exc:
            raise DoclingExtractionError(
                f"Docling conversion failed: {type(exc).__name__}"
            ) from exc

        if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
            raise DoclingExtractionError(
                f"Docling conversion status: {result.status.value}"
            )

        doc = result.document

        # Group raw text blocks by page number before assigning indexes.
        # Each entry: (text, section_at_time_of_emission)
        by_page: dict[int, list[tuple[str, str | None]]] = defaultdict(list)
        current_section: str | None = None

        try:
            for item, _level in doc.iterate_items():
                if not isinstance(item, DocItem):
                    continue

                label_value: str = item.label.value  # DocItemLabel enum → str

                # Resolve page number from provenance.
                if not item.prov:
                    continue
                page_no: int = item.prov[0].page_no  # 1-based per Docling spec
                if not isinstance(page_no, int) or page_no < 1:
                    continue

                if label_value in _SECTION_LABELS:
                    # Update section state; do not emit a chunk.
                    if isinstance(item, TextItem):
                        txt = item.text.strip()
                        if txt:
                            current_section = txt
                    continue

                if label_value in _EMIT_LABELS:
                    # Verified against docling==2.37.0: all allowlisted labels
                    # whose type is constrained here appear as TextItem subclasses
                    # at runtime (see class docstring for MRO verification).
                    if isinstance(item, TextItem):
                        txt = item.text.strip()
                        if txt:
                            by_page[page_no].append((txt, current_section))
                    continue

                if label_value == _TABLE_LABEL:
                    if isinstance(item, TableItem):
                        parts: list[str] = []
                        cap = item.caption_text(doc).strip()
                        if cap:
                            parts.append(f"Caption: {cap}")
                        md = item.export_to_markdown(doc).strip()
                        if md:
                            parts.append(md)
                        combined = "\n".join(parts).strip()
                        if combined:
                            by_page[page_no].append((combined, current_section))
                    continue

                # All other labels (PICTURE, CHART, PAGE_HEADER, etc.) are
                # silently skipped.

        except Exception as exc:
            raise DoclingExtractionError(
                f"Error iterating Docling document items: {type(exc).__name__}"
            ) from exc

        # Assign per-page 0-based indexes after all filtering is complete.
        chunks: list[RawChunk] = []
        for page_no in sorted(by_page.keys()):
            for idx, (text, section) in enumerate(by_page[page_no]):
                chunks.append(RawChunk(page=page_no, index=idx, text=text, section=section))

        return chunks


# ---------------------------------------------------------------------------
# PyMuPDFAdapter
# ---------------------------------------------------------------------------


class PyMuPDFAdapter:
    """Wraps PyMuPDF (``fitz``) PDF text extraction.

    Produces one :class:`RawChunk` per page that contains selectable text.
    All chunks have ``section=None`` — PyMuPDF provides no structural metadata.
    ``index`` is always ``0`` because there is exactly one chunk per page.
    The public chunk ID converts this to 1-based via ``index + 1``.

    Reading order follows PyMuPDF's default ``"text"`` extraction mode, which
    uses the page's content stream order.  This may be imperfect on complex
    multi-column layouts but is acceptable for the fallback path.

    Exceptions from ``fitz`` propagate unwrapped to :class:`ExtractionService`,
    which converts them to :exc:`ExtractionError`.
    """

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:  # noqa: ARG002
        import fitz  # PyMuPDF — always available (listed in requirements.txt)

        chunks: list[RawChunk] = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text = page.get_text("text").strip()
                if not text:
                    continue
                # page.number is 0-based; add 1 for 1-based page number.
                chunks.append(
                    RawChunk(
                        page=page.number + 1,
                        index=0,
                        text=text,
                        section=None,
                    )
                )
        return chunks


# ---------------------------------------------------------------------------
# ExtractionService
# ---------------------------------------------------------------------------


class ExtractionService:
    """Docling-first, PyMuPDF-fallback PDF extraction service.

    Adapters are injectable so unit tests can substitute fakes without
    patching module-level imports.  When an adapter argument is ``None`` the
    corresponding real adapter is instantiated lazily on first use.
    """

    def __init__(
        self,
        docling_adapter: DoclingAdapter | None = None,
        pymupdf_adapter: PyMuPDFAdapter | None = None,
    ) -> None:
        self._docling: DoclingAdapter = docling_adapter or DoclingAdapter()
        self._pymupdf: PyMuPDFAdapter = pymupdf_adapter or PyMuPDFAdapter()

    def extract(
        self,
        pdf_bytes: bytes,
        filename: str,
        paper_id: str,
    ) -> ExtractionResult:
        """Extract text from *pdf_bytes* and return a validated :class:`ExtractionResult`.

        Raises
        ------
        ValueError
            If *pdf_bytes* is empty, or *filename* or *paper_id* are blank or
            whitespace-only.  Validation happens *before* any adapter invocation
            to avoid unnecessary expensive extraction work.
        ExtractionError
            When neither backend produces usable text, or when a duplicate
            chunk ID is detected (which indicates an adapter programming error).
        """
        # --- Early input validation (before any adapter invocation) ---
        if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
            raise ValueError("pdf_bytes must not be empty.")

        filename_stripped = filename.strip()
        if not filename_stripped:
            raise ValueError("filename must not be blank.")

        paper_id_stripped = paper_id.strip()
        if not paper_id_stripped:
            raise ValueError("paper_id must not be blank.")

        raw_chunks: list[RawChunk]
        docling_error: str | None = None

        # --- Step 1: attempt Docling ---
        try:
            raw_chunks = self._docling.extract_chunks(pdf_bytes, paper_id)
            if not raw_chunks:
                docling_error = "Docling returned zero usable chunks"
                _log.debug("Docling produced no chunks; falling back to PyMuPDF.")
                raw_chunks = self._pymupdf_extract(pdf_bytes, paper_id, docling_error)
            else:
                _log.debug(
                    "Docling extracted %d chunks from paper_id=%r.",
                    len(raw_chunks),
                    paper_id,
                )
        except DoclingExtractionError as exc:
            docling_error = str(exc)
            _log.debug(
                "Docling failed (%s); falling back to PyMuPDF.",
                type(exc).__name__,
            )
            raw_chunks = self._pymupdf_extract(pdf_bytes, paper_id, docling_error)

        # --- Step 2: build Chunk list from RawChunk list ---
        # Public chunk IDs use 1-based per-page numbering.
        # RawChunk.index is 0-based internally; we convert here.
        chunks: list[Chunk] = [
            Chunk(
                chunk_id=f"{paper_id}-p{r.page}-{r.index + 1}",
                page=r.page,
                section=r.section,
                text=r.text,
            )
            for r in raw_chunks
        ]

        # --- Step 3: duplicate chunk-ID guard ---
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            seen: set[str] = set()
            duplicates: set[str] = set()
            for chunk_id in ids:
                if chunk_id in seen:
                    duplicates.add(chunk_id)
                else:
                    seen.add(chunk_id)
            raise ExtractionError(
                f"Duplicate chunk ID(s) detected: {list(duplicates)[:5]!r}. "
                "This is an adapter programming error."
            )

        _log.info(
            "Extraction complete: paper_id=%r, chunks=%d.",
            paper_id,
            len(chunks),
        )
        return ExtractionResult(
            paper_id=paper_id_stripped,
            filename=filename_stripped,
            chunks=chunks,
        )

    def _pymupdf_extract(
        self,
        pdf_bytes: bytes,
        paper_id: str,
        docling_error: str | None,
    ) -> list[RawChunk]:
        """Call the PyMuPDF adapter and raise :exc:`ExtractionError` on failure."""
        try:
            raw = self._pymupdf.extract_chunks(pdf_bytes, paper_id)
        except Exception as exc:
            msg = (
                f"Both extractors failed. "
                f"Docling: {docling_error or 'not attempted'}. "
                f"PyMuPDF: {type(exc).__name__}."
            )
            raise ExtractionError(msg) from exc

        if not raw:
            raise ExtractionError("PDF contains no selectable text.")
        _log.debug("PyMuPDF extracted %d chunks.", len(raw))
        return raw