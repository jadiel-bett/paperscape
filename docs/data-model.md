# PaperScape — Canonical Data Model

This document is the single source of truth for all data shapes used across
the PaperScape backend. Every Pydantic model in `backend/app/models/` must
match the definitions below. API responses and inter-service contracts are
derived directly from these shapes.

---

## `backend/app/models/paper.py`

### `Chunk`

Represents a single extracted text segment from a PDF.

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | `str` | Deterministic: `"{paper_id}-p{page}-{index}"` |
| `page` | `int` | 1-based page number |
| `section` | `str \| None` | Heading label from Docling; `None` for PyMuPDF fallback |
| `text` | `str` | Extracted text content of the chunk |

---

### `ExtractionResult`

The complete output of the extraction service for a single PDF.

| Field | Type | Notes |
|---|---|---|
| `paper_id` | `str` | UUID v4, assigned at upload time; must be non-blank |
| `filename` | `str` | Original uploaded filename; must be non-blank |
| `chunks` | `list[Chunk]` | All extracted chunks, ordered by page then position; must contain at least one chunk |

---

### `UploadResponse`

The JSON body returned by `POST /api/v1/papers/upload` on success (`202 Accepted`).

| Field | Type | Notes |
|---|---|---|
| `paper_id` | `str` | UUID v4 |
| `filename` | `str` | Original filename |
| `page_count` | `int` | Total number of pages in the PDF |
| `chunk_count` | `int` | Total number of chunks extracted |

---

## `backend/app/models/research_map.py`

### `Evidence`

A single piece of source evidence linking a finding statement to a chunk.

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | `str` | References a `Chunk.chunk_id` in the same paper |
| `page` | `int` | 1-based page number of the source chunk |
| `excerpt` | `str` | Verbatim or near-verbatim excerpt; ≤ 300 characters |

---

### `Finding`

One of three key findings extracted from the paper by the research-map service.

| Field | Type | Notes |
|---|---|---|
| `statement` | `str` | Plain-language statement of the finding |
| `evidence` | `list[Evidence]` | One or more evidence records supporting the statement |
| `confidence` | `Literal["high", "partial", "uncertain"]` | Confidence level assigned by the model |

Validation rule: a `ResearchMap` must contain **exactly 3** `Finding` records.

---

### `ResearchMap`

The complete structured output of the research-map generation service.

| Field | Type | Notes |
|---|---|---|
| `paper_id` | `str` | UUID v4 of the source paper |
| `research_question` | `str` | The central research question identified by the model |
| `findings` | `list[Finding]` | Exactly 3 findings |
| `limitations` | `list[str]` | Limitations identified in the paper; must contain at least one item |
| `disclaimer` | `Literal["This map does not replace expert review."]` | Fixed constant; any other value is rejected at validation |

---

## `backend/app/models/job.py`

### `JobStatus`

A `StrEnum` (Python 3.11+ `enum.StrEnum`) representing all valid job states.
Values are plain lowercase strings that compare equal to string literals
(`JobStatus.PENDING == "pending"`).

```python
class JobStatus(enum.StrEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
```

Valid transitions:

```
pending → running → succeeded
                  ↘ failed
```

---

### `Job`

The persisted job record stored in the `jobs` SQLite table.

| Field | Type | Notes |
|---|---|---|
| `job_id` | `str` | UUID v4 |
| `paper_id` | `str` | UUID v4 of the paper this job processes |
| `status` | `JobStatus` | Current state of the job |
| `created_at` | `datetime` | UTC timestamp when the job was created |
| `updated_at` | `datetime` | UTC timestamp of the last status change |
| `error` | `str \| None` | Human-readable failure reason; `None` when not failed |

---

### `JobCreateResponse`

The JSON body returned by `POST /api/v1/papers/{paper_id}/research-map-jobs`
on success (`202 Accepted`).

| Field | Type | Notes |
|---|---|---|
| `job_id` | `str` | UUID v4 of the newly created job |
| `paper_id` | `str` | UUID v4 of the paper |
| `status` | `JobStatus` | Always `"pending"` at creation time |

---

### `JobStatusResponse`

The JSON body returned by `GET /api/v1/jobs/{job_id}`.
Contains all fields from `Job`.

| Field | Type | Notes |
|---|---|---|
| `job_id` | `str` | UUID v4 |
| `paper_id` | `str` | UUID v4 |
| `status` | `JobStatus` | Current state |
| `created_at` | `datetime` | UTC creation timestamp |
| `updated_at` | `datetime` | UTC last-update timestamp |
| `error` | `str \| None` | Failure reason, or `null` |

---

## Invariants

- All `paper_id` and `job_id` values are UUID v4 strings.
- All `datetime` values are UTC ISO-8601 strings in API responses.
- `chunk_id` format is deterministic: `"{paper_id}-p{page}-{index}"`.
- `Evidence.excerpt` must not exceed 300 characters.
- `ResearchMap.findings` must contain exactly 3 items.
- `ResearchMap.limitations` must contain at least one item.
- `ResearchMap.disclaimer` is a fixed `Literal` constant: `"This map does not replace expert review."` — any other value is rejected by Pydantic validation.
- Every `Finding` must have at least one `Evidence` record.
- Required string fields (`chunk_id`, `text`, `paper_id`, `filename`, `statement`, `chunk_id`, `excerpt`, `research_question`) must be non-blank; whitespace-only values are rejected and leading/trailing whitespace is stripped.
- `ExtractionResult.chunks` must contain at least one `Chunk`.
- `Job.error` is non-null only when `status == "failed"`.
- `JobStatus` transitions are one-way: a succeeded or failed job cannot be moved back to pending or running.
- The `jobs` table enforces `CHECK (status IN ('pending', 'running', 'succeeded', 'failed'))` at the database layer.

---

## Relationships

```
ExtractionResult 1 ──── * Chunk
       │
       │ (paper_id)
       ▼
      Job * ──── 1 paper_id
       │
       │ (on success)
       ▼
  ResearchMap 1 ──── 3 Finding
                           │
                           └── 1..* Evidence  (chunk_id → Chunk)
```
