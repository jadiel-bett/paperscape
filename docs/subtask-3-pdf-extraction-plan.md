# Sub-task 3 — Docling-first, PyMuPDF-fallback PDF Extraction

## Top-Level Overview

**Goal:** Implement `ExtractionService.extract(pdf_bytes, filename, paper_id) -> ExtractionResult`
as a pure Python service with no HTTP/FastAPI dependencies. The service attempts Docling
first; if Docling is unavailable, raises an exception, or returns no usable chunks, it
transparently falls back to PyMuPDF. If both paths produce zero usable chunks, it raises
`ExtractionError`. A companion unit-test module covers every behavioural scenario using
mocks and programmatically generated PDF fixtures — no network calls, no Docling model
downloads.

**Scope:**
- `backend/app/services/extraction.py` — the service, adapters, and exceptions
- `backend/tests/unit/test_extraction.py` — all required tests
- `backend/requirements.txt` — two new pinned dependencies (`docling`, `pymupdf`)

**Out of scope:** file upload endpoint, MIME/size validation, database persistence, JobStore,
research-map generation, watsonx, OCR, table/figure interpretation beyond what Docling
provides naturally.

---

## Files Involved

| File | Action |
|---|---|
| `backend/app/services/extraction.py` | **Create** |
| `backend/tests/unit/test_extraction.py` | **Create** |
| `backend/requirements.txt` | **Modify** — add `docling` and `pymupdf` pins |

---

## Exception Hierarchy

All exceptions are defined at the top of `extraction.py`. No shared
`exceptions.py` module is created; that decision is deferred to a future
sub-task when other services need to share error types.

```
ExtractionError(RuntimeError)
  └── DoclingExtractionError   — Docling raised an error or is unavailable
```

Rules:
- Do **not** catch `BaseException`, `KeyboardInterrupt`, or `SystemExit`.
- When both backends fail, the PyMuPDF error is chained onto the primary
  `ExtractionError` via `raise ExtractionError(...) from pymupdf_error`.
  The Docling error is recorded in the message string so both causes are
  preserved without nesting a second live exception inside the primary.
- `DoclingExtractionError` wraps the root Docling cause so the fallback
  logic in `ExtractionService` can catch it by name and proceed.
- Error messages describe the failure mode without including any document text.

---

## Proposed Classes and Methods

### `ExtractionService`

The public entry point. Owns the fallback decision logic. Receives injectable
adapter instances so tests can substitute fakes without patching modules.

```
class ExtractionService:
    def __init__(
        self,
        docling_adapter: DoclingAdapter | None = None,
        pymupdf_adapter: PyMuPDFAdapter | None = None,
    ) -> None

    def extract(
        self,
        pdf_bytes: bytes,
        filename: str,
        paper_id: str,
    ) -> ExtractionResult
```

- When `docling_adapter` is `None`, a real `DoclingAdapter()` is instantiated
  internally (lazy default).
- When `pymupdf_adapter` is `None`, a real `PyMuPDFAdapter()` is instantiated
  internally (lazy default).
- Both adapters can be overridden independently; passing only one override
  leaves the other at its real default.

---

### `DoclingAdapter`

Encapsulates all Docling-specific import and conversion logic. The Docling
import is guarded inside `extract_chunks()` so the outer module never fails
to import even when `docling` is not installed.

```
class DoclingAdapter:
    def extract_chunks(
        self,
        pdf_bytes: bytes,
        paper_id: str,
    ) -> list[RawChunk]
```

**Input:** Docling receives the PDF via `DocumentStream` wrapping a
`io.BytesIO(pdf_bytes)` buffer. `DocumentStream` is Docling's standard
in-memory input type; no `tempfile` is used.

**Processing pipeline inside the adapter (in order):**

1. Import `docling` — wrap `ImportError` in `DoclingExtractionError`.
2. Convert via `DocumentConverter().convert(DocumentStream(...))`.
3. Walk the document's items in Docling's native reading order using
   `doc.iterate_items()` (or the equivalent API for the pinned version).
4. Apply the element allowlist (see below).
5. Track `current_section` via `SECTION_HEADER` elements.
6. For `TABLE` elements, serialise the table including its caption into
   one compact text block (see Table serialisation below).
7. For all other allowed element types, use the element's plain text.
8. Strip leading/trailing whitespace from every text block.
9. **Discard** elements whose text is empty or whitespace-only after stripping.
10. Verify every retained element has a reliable 1-based page number from
    Docling provenance; skip elements whose page cannot be determined.
11. Assign per-page 0-based `index` values (see Index assignment below).
12. Perform duplicate chunk-ID check (see Duplicate check below).
13. Return `list[RawChunk]` in reading order.

Any exception from Docling (excluding `ImportError`, which is handled in
step 1) is wrapped and re-raised as `DoclingExtractionError`.

---

### `PyMuPDFAdapter`

Encapsulates all PyMuPDF (`fitz`) logic. Always available as the fallback.

```
class PyMuPDFAdapter:
    def extract_chunks(
        self,
        pdf_bytes: bytes,
        paper_id: str,
    ) -> list[RawChunk]
```

- Opens `pdf_bytes` via `fitz.open(stream=pdf_bytes, filetype="pdf")`.
- Iterates pages in document order.
- Page number: `page.number + 1` (PyMuPDF is 0-based; +1 = 1-based).
- Calls `page.get_text("text")` for plain-text extraction in reading order.
- Treats the entire text from one page as a single `RawChunk`.
- Strips whitespace; discards the page if the result is empty.
- Sets `section=None` for all chunks — no structural analysis available.
- Assigns `index` values (see Index assignment below).
- Does **not** wrap exceptions; PyMuPDF errors propagate to `ExtractionService`.

---

### `RawChunk` (internal dataclass)

Internal transfer object between adapters and `ExtractionService`. Never
exported from the module as part of the public API.

```python
@dataclasses.dataclass
class RawChunk:
    page: int        # 1-based; guaranteed reliable
    index: int       # per-page 0-based; assigned after filtering
    text: str        # stripped; non-empty
    section: str | None
```

---

## Docling Element Allowlist

The adapter explicitly classifies every Docling `DocItemLabel` (or equivalent
enum) it encounters. Unknown labels are silently skipped.

### Emit as content chunks

| Docling label | Behaviour |
|---|---|
| `TITLE` | Emit text as chunk; also sets `current_section` |
| `TEXT` | Emit text as chunk |
| `PARAGRAPH` | Emit text as chunk |
| `LIST_ITEM` | Emit text as chunk |
| `CAPTION` | Emit text as chunk (image and figure captions — text only, no image) |
| `CODE` | Emit text as chunk |
| `FORMULA` | Emit text as chunk |
| `TABLE` | Serialise into one compact text chunk including its caption (see below) |

### Update section state only (not emitted as standalone chunks)

| Docling label | Behaviour |
|---|---|
| `SECTION_HEADER` | Updates `current_section` to this element's text; not emitted |

### Excluded entirely

| Docling label | Reason |
|---|---|
| `PICTURE` | Image content — not interpretable as text |
| `CHART` | Image content — not interpretable as text |
| `PAGE_HEADER` | Repeated boilerplate; not document content |
| `PAGE_FOOTER` | Repeated boilerplate; not document content |
| `DOCUMENT_INDEX` | Table-of-contents artefact; not substantive content |
| `REFERENCE` | Bibliography entry; outside primary content scope |
| `EMPTY_VALUE` | No content |
| `MARKER` | Structural marker; no text value |
| Form/checkbox elements | Interactive artefacts; no prose content |
| Any unrecognised label | Skipped silently |

### Table serialisation

When a `TABLE` element is encountered:
1. Extract the table's textual cell content row by row (tab-separated cells,
   newline-separated rows, or Docling's native `export_to_markdown()` if
   available for the pinned version — use the simplest stable API).
2. If the table has an associated `CAPTION` element, prepend it to the block
   as `"Caption: {caption_text}\n"`.
3. Strip the combined block; discard if empty after stripping.
4. Emit as one `RawChunk` using the table's page and the next available index.

### Figure and chart captions

`CAPTION` elements associated with `PICTURE` or `CHART` elements **are**
emitted as text chunks because the caption text is human-readable and
evidence-bearing. The image content itself is discarded.

---

## Index Assignment and Chunk ID Design

### Canonical chunk ID format

```
{paper_id}-p{page}-{index}
```

### Per-page, 1-based public index

The internal ``RawChunk.index`` is **per-page**, **0-based**, and resets to ``0``
at the start of each new page.  When constructing the public ``Chunk.chunk_id``
the value is shifted to **1-based** via ``index + 1``:

```
paper-123-p1-1   ← first chunk on page 1  (internal index 0)
paper-123-p1-2   ← second chunk on page 1 (internal index 1)
paper-123-p2-1   ← first chunk on page 2  (internal index 0)
paper-123-p2-2   ← second chunk on page 2 (internal index 1)
```

### When index is assigned

Index values are assigned **only after** the full processing pipeline has
been applied to every element on the page:

1. Reading-order normalisation (Docling native order, or page order for PyMuPDF)
2. Element filtering (allowlist applied)
3. Whitespace trimming
4. Removal of empty chunks

The surviving elements for a given page are then numbered `0, 1, 2, …` in the
order they remain after filtering. This means index values are stable and
contiguous; no gaps arise from discarded elements.

### Duplicate chunk-ID check

After all chunks have been assembled from the full document, `ExtractionService`
constructs a set of all `chunk_id` values and asserts its length equals the
number of chunks. If a duplicate is detected, `ExtractionError` is raised with
a message identifying the duplicate ID (but not any document text). This check
is the final guard before constructing `ExtractionResult`.

A duplicate can only arise from a programming error (e.g. the adapter returns
two elements with the same page and index). It cannot arise from normal input
variation when the pipeline above is followed correctly.

### One page can produce multiple chunks

Yes — Docling may identify multiple distinct text elements (paragraphs, list
items, table, formula) within a single page. PyMuPDF produces exactly one
chunk per page.

---

## Docling-to-Chunk Mapping

| Docling element property | `RawChunk` field | Notes |
|---|---|---|
| Provenance page number | `page` | 1-based from Docling; skip element if unavailable |
| Filtered, stripped text | `text` | Discard if empty after strip |
| `current_section` at time of emission | `section` | `None` until first `SECTION_HEADER` seen |
| Per-page counter after filtering | `index` | 0-based; resets each page |

---

## PyMuPDF-to-Chunk Mapping

| PyMuPDF value | `RawChunk` field | Notes |
|---|---|---|
| `page.number + 1` | `page` | Always reliable; PyMuPDF is 0-based |
| `page.get_text("text").strip()` | `text` | Discard page if blank after strip |
| Always `None` | `section` | No structural info available |
| `0` (always) | `index` | One chunk per page; per-page index is always 0 |

---

## Fallback Decision Logic

```
extract(pdf_bytes, filename, paper_id):

    docling_error: str | None = None

    1. Try docling_adapter.extract_chunks(pdf_bytes, paper_id)
       - On DoclingExtractionError as e:
           docling_error = str(e)
           → go to step 2
       - On success with zero chunks:
           docling_error = "Docling returned zero usable chunks"
           → go to step 2
       - On success with ≥ 1 chunk → go to step 3

    2. Try pymupdf_adapter.extract_chunks(pdf_bytes, paper_id)
       - On Exception as e:
           raise ExtractionError(
               f"Both extractors failed. Docling: {docling_error}. "
               f"PyMuPDF: {type(e).__name__}: {e}"
           ) from e
       - On success with zero chunks:
           raise ExtractionError(
               "PDF contains no selectable text"
           )
       - On success with ≥ 1 chunk → go to step 3

    3. Build list[Chunk] from list[RawChunk]:
       chunk_id = f"{paper_id}-p{raw.page}-{raw.index + 1}"  # 1-based public ID

    4. Duplicate chunk-ID check:
       ids = [c.chunk_id for c in chunks]
       if len(set(ids)) != len(ids):
           raise ExtractionError(f"Duplicate chunk ID detected: ...")

    5. Return ExtractionResult(
           paper_id=paper_id,
           filename=filename,
           chunks=chunks,
       )
```

Notes:
- The Docling error string in step 2 is captured from the exception message,
  which must never contain document text (enforced by `DoclingExtractionError`).
- Pydantic validation at step 5 enforces non-blank `text`, non-blank `chunk_id`,
  page ≥ 1, and `chunks` list `min_length=1` — these are the final invariant guards.

---

## Sub-Tasks

### Sub-task 3.1 — Exception classes

- **Intent:** Define the exception hierarchy before any logic is written so it
  can be imported cleanly by both the service and tests.
- **Expected Outcomes:**
  - `ExtractionError(RuntimeError)` exists in `extraction.py`.
  - `DoclingExtractionError(ExtractionError)` exists in `extraction.py`.
  - Both are importable from `app.services.extraction`.
- **Todo List:**
  1. Add `ExtractionError` and `DoclingExtractionError` at the top of
     `backend/app/services/extraction.py`.
- **Relevant Context:** Exception hierarchy section above.
- **Status:** [x] done

---

### Sub-task 3.2 — `RawChunk` dataclass and `PyMuPDFAdapter`

- **Intent:** Implement the always-available fallback adapter and the internal
  transfer object first so tests can be written and green before Docling is
  touched.
- **Expected Outcomes:**
  - `PyMuPDFAdapter.extract_chunks()` returns non-empty `RawChunk` list for a
    real PDF with selectable text.
  - Returns empty list for a PDF with no selectable text.
  - Page numbers are 1-based.
  - `section` is always `None`.
  - `index` is always `0` (one chunk per page).
- **Todo List:**
  1. Add `RawChunk` dataclass to `extraction.py`.
  2. Add `PyMuPDFAdapter` class with `extract_chunks()` method.
  3. Add `pymupdf==1.25.5` (or latest stable) to `requirements.txt`.
- **Relevant Context:** PyMuPDF-to-Chunk mapping table; Index assignment section.
- **Status:** [x] done

---

### Sub-task 3.3 — `DoclingAdapter`

- **Intent:** Implement the Docling adapter with element allowlist, section
  tracking, table serialisation, and per-page index assignment.
- **Expected Outcomes:**
  - `DoclingAdapter.extract_chunks()` returns `RawChunk` list with `section`
    populated where `SECTION_HEADER` elements are present.
  - Only allowlisted element types produce chunks.
  - `SECTION_HEADER` updates `current_section` but is not emitted as a chunk.
  - `TABLE` elements produce one compact text chunk including any caption.
  - `CAPTION` elements for images/figures are emitted; image content is not.
  - Elements without reliable page provenance are skipped.
  - `ImportError` raises `DoclingExtractionError`.
  - Any Docling internal exception raises `DoclingExtractionError`.
  - Index values are assigned after filtering (per-page, 0-based).
  - Docling is called via `DocumentStream` wrapping `io.BytesIO(pdf_bytes)`.
  - No `tempfile` usage.
- **Todo List:**
  1. Add `DoclingAdapter` class with `extract_chunks()` method.
  2. Implement element allowlist classification.
  3. Implement `current_section` tracking.
  4. Implement table serialisation logic.
  5. Guard Docling import with `try/except ImportError` inside the method.
  6. Add `docling==2.37.0` (or latest stable) to `requirements.txt`. Pin
     tightly; Docling's internal API has frequent breaking changes.
- **Relevant Context:** Docling element allowlist; Docling-to-Chunk mapping; Index assignment.
- **Status:** [x] done

---

### Sub-task 3.4 — `ExtractionService`

- **Intent:** Wire the two adapters together with fallback decision logic,
  duplicate-ID check, and produce a validated `ExtractionResult`.
- **Expected Outcomes:**
  - `ExtractionService.extract()` returns `ExtractionResult` with ≥ 1 chunk.
  - Docling failure (`DoclingExtractionError`) transparently triggers PyMuPDF fallback.
  - Zero Docling chunks triggers PyMuPDF fallback.
  - Both adapters failing raises `ExtractionError` with both error causes in the message.
  - Duplicate chunk IDs raise `ExtractionError`.
  - No files written to disk; no document text in logs.
- **Todo List:**
  1. Add `ExtractionService` class with `__init__` (injectable adapters) and
     `extract()` method.
  2. Implement fallback decision logic per the Fallback Decision Logic section.
  3. Build `list[Chunk]` from `list[RawChunk]` using the chunk ID formula.
  4. Implement duplicate chunk-ID check.
  5. Construct and return `ExtractionResult(paper_id, filename, chunks)`.
- **Relevant Context:** ExtractionService class; Fallback decision logic; Duplicate check.
- **Status:** [x] done

---

### Sub-task 3.5 — Unit tests

- **Intent:** Cover all specified test scenarios with deterministic, network-free
  tests using PyMuPDF to generate PDF fixtures programmatically.
- **Expected Outcomes:**
  - All 14 required test cases pass.
  - No network calls; no Docling model downloads.
  - Docling is mocked via injectable fake adapter (no `unittest.mock.patch` on
    module-level imports).
  - PDF fixtures are generated in-memory using PyMuPDF; no `fpdf2` dependency.
- **Todo List:**
  1. Add a `make_pdf(pages: list[str]) -> bytes` helper using
     `fitz.open()` + `page.insert_text()` + `doc.tobytes()`.
  2. Add a `make_blank_pdf(num_pages: int = 1) -> bytes` helper producing
     pages with no text content.
  3. Add a `FakeDoclingAdapter` class with a `chunks` attribute; its
     `extract_chunks()` returns the preset list.
  4. Write all 14 test cases listed in the Test Strategy section.
  5. Confirm no `pytest.ini` or `conftest.py` changes are needed.
- **Relevant Context:** Test strategy section; existing `test_models.py` style.
- **Status:** [x] done

---

## Test Strategy

All tests live in `backend/tests/unit/test_extraction.py`.

### PDF Fixture Helpers (module-level functions)

```
make_pdf(pages: list[str]) -> bytes
    Uses fitz.open(), inserts one string per page as selectable text,
    returns doc.tobytes(). Pure PyMuPDF; no network; no Docling.

make_blank_pdf(num_pages: int = 1) -> bytes
    Uses fitz.open(), adds pages with no inserted text, returns doc.tobytes().
    Simulates a scanned-image PDF with no selectable text.
```

### Mock Strategy for Docling

Rather than patching Docling's module-level import, tests use the injectable
adapter constructor:

```python
class FakeDoclingAdapter:
    def __init__(self, chunks: list[RawChunk]) -> None:
        self._chunks = chunks

    def extract_chunks(self, pdf_bytes: bytes, paper_id: str) -> list[RawChunk]:
        return list(self._chunks)
```

Tests construct `ExtractionService(docling_adapter=FakeDoclingAdapter([...]), ...)`.
The real `DoclingAdapter` is never instantiated in unit tests.

### Required Test Cases

| # | Test name | What is verified |
|---|---|---|
| 1 | `test_docling_successful_extraction` | Fake Docling adapter returns chunks → `ExtractionResult` contains those chunks |
| 2 | `test_docling_preserves_page_and_section` | Chunks carry correct `page` numbers and `section` labels from fake adapter |
| 3 | `test_deterministic_chunk_ids` | Chunk IDs match `{paper_id}-p{page}-{index}` formula exactly |
| 4 | `test_empty_text_blocks_removed` | `RawChunk` with whitespace-only text passed from fake adapter is not included in result |
| 5 | `test_docling_exception_triggers_pymupdf_fallback` | Fake adapter raises `DoclingExtractionError` → PyMuPDF path used, result returned |
| 6 | `test_zero_docling_chunks_triggers_pymupdf_fallback` | Fake adapter returns `[]` → PyMuPDF path used with a real multi-page PDF |
| 7 | `test_pymupdf_extracts_multi_page_pdf` | `make_pdf(["page one", "page two", "page three"])` → 3 chunks, one per page |
| 8 | `test_page_numbers_are_one_based` | First chunk from a `make_pdf()` result has `page == 1` |
| 9 | `test_pymupdf_fallback_section_is_none` | All chunks produced via PyMuPDF path have `section is None` |
| 10 | `test_both_extractors_failing_raises_extraction_error` | Fake Docling raises `DoclingExtractionError`; fake PyMuPDF raises `RuntimeError` → `ExtractionError` raised |
| 11 | `test_no_selectable_text_raises_extraction_error` | `make_blank_pdf()` with Docling disabled → `ExtractionError` raised |
| 12 | `test_blank_filename_rejected_by_pydantic` | Blank `filename` (`""` or `"  "`) causes `ValidationError` before a result is returned |
| 13 | `test_extraction_result_has_at_least_one_chunk` | Successful call always yields `len(result.chunks) >= 1` |
| 14 | `test_service_does_not_write_files` | After `extract()` call, `tmp_path` contains no new files |

### Test for blank `paper_id`

Blank `paper_id` is rejected by the `ExtractionResult` Pydantic validator —
the same `_strip_and_require_nonblank` validator that covers `filename`. A
companion assertion alongside test #12 confirms this without a separate test.

---

## Dependency Changes

Add to `backend/requirements.txt`:

```
docling==2.37.0
pymupdf==1.25.5
```

Version notes:
- `docling` is pinned tightly because its element model and `DocumentConverter`
  API change frequently between minor versions. The `DocItemLabel` enum values
  and `iterate_items()` / `DocumentStream` interfaces must be verified against
  the pinned version before implementation.
- `pymupdf` is the `PyMuPDF` package, imported as `fitz`. Pin to a known-stable
  release. As of June 2025, `1.25.x` is the current stable series.
- Do **not** add `fpdf2` or any other PDF-generation library; PyMuPDF generates
  minimal test PDFs programmatically.

---

## Architecture Constraints

1. **No FastAPI imports** in `extraction.py` or its adapters.
2. **No database imports** — extraction is stateless; persistence is the caller's
   responsibility.
3. **No watsonx imports.**
4. **No `BaseException` catch** — only named exception types.
5. **No `tempfile` usage** — Docling conversion uses `DocumentStream` with
   `io.BytesIO(pdf_bytes)`. There is no fallback to temporary files.
6. **No complete paper text in log output** — log metadata only (page count,
   chunk count, parser used). Never log extracted text.
7. **Preserve both adapter errors** — when both backends fail, the Docling error
   string is included in the `ExtractionError` message and the PyMuPDF error is
   the chained cause. Neither message may contain document content.
8. **Pydantic models from `paper.py` are used as-is** — no modifications to
   existing models are required or permitted for this sub-task.
9. **Exceptions stay in `extraction.py`** — no shared `exceptions.py` until
   another service explicitly needs to import `ExtractionError`.

---

## Risks and Fallbacks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `DocumentStream` is not available or has a different import path in the pinned Docling version | Medium | Verify at implementation time; adapt import path; document in code comment |
| Docling `DocItemLabel` enum values differ from those listed in the allowlist | High | Pin version tightly; verify each label name against the installed package before writing the adapter |
| `iterate_items()` API differs between Docling versions | High | Pin version; check the actual method name and signature for `docling==2.37.0` at implementation time |
| PyMuPDF `get_text("text")` returns inconsistent reading order on complex layouts | Low | Acceptable for fallback path; note in docstring |
| Docling ML model downloads during unit tests | Low | Real `DoclingAdapter` never instantiated in unit tests; fake adapter used instead |
| `fitz` name conflicts with a different PyPI package also named `fitz` | Low | Install via `pymupdf`; import as `import fitz` |
| Per-page index collision if adapter emits two elements with same page and index | Low | Duplicate-ID check in `ExtractionService` catches this; raises `ExtractionError` |

---

## Acceptance Criteria

- [ ] `ExtractionService.extract(pdf_bytes, filename, paper_id)` returns a valid
      `ExtractionResult` for any PDF with selectable text.
- [ ] Docling failure (`DoclingExtractionError` or zero chunks) silently falls
      back to PyMuPDF.
- [ ] `ExtractionError` is raised when both parsers produce zero usable chunks.
- [ ] `ExtractionError` is raised when a duplicate chunk ID is detected.
- [ ] All chunk IDs match `{paper_id}-p{page}-{index}` with per-page, 0-based index.
- [ ] Index values are assigned only after reading-order normalisation, element
      filtering, whitespace trimming, and removal of empty chunks.
- [ ] Page numbers are 1-based in all returned chunks.
- [ ] Docling chunks carry `section` labels derived from `SECTION_HEADER` elements;
      `SECTION_HEADER` elements themselves are not emitted as chunks.
- [ ] Only allowlisted Docling element types produce chunks; all others are silently
      discarded.
- [ ] `TABLE` elements produce one compact text chunk including their caption.
- [ ] `CAPTION` elements for images/figures are emitted; image content is not.
- [ ] Elements without reliable page provenance are skipped without error.
- [ ] PyMuPDF chunks always have `section=None`.
- [ ] Empty and whitespace-only text blocks never appear in returned chunks.
- [ ] No `tempfile` usage anywhere in `extraction.py`.
- [ ] No files are written to disk during extraction (verified by test #14).
- [ ] Both adapter errors are preserved when both backends fail; no document text
      appears in any error message or log line.
- [ ] No FastAPI, SQLite, or watsonx imports exist in `extraction.py`.
- [ ] All 14 unit tests pass without network access or Docling model downloads.
- [ ] `docling` and `pymupdf` are pinned in `requirements.txt`.
- [ ] `ExtractionResult` is never returned with zero chunks.
