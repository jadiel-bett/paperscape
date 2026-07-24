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

The JSON body returned by `POST /api/v1/papers` on success (`201 Created`).

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
| `disclaimer` | `Literal["This AI-generated explanation is grounded in the uploaded document but does not replace expert review."]` | Fixed constant; any other value is rejected at validation |

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
- `ResearchMap.disclaimer` is a fixed `Literal` constant: `"This AI-generated explanation is grounded in the uploaded document but does not replace expert review."` — any other value is rejected by Pydantic validation.
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

---

## Persistence Layer (Repositories)

The persistence layer lives in `backend/app/repositories/`. Each store manages a
single SQLite table and provides atomic, testable data access.

### Exception hierarchy

| Exception | Base | Raised when |
|---|---|---|
| `PersistenceError` | `RuntimeError` | A storage-layer operation fails (`sqlite3.Error` chained as `__cause__`) |
| `RecordNotFoundError` | `PersistenceError` | A requested ID has no matching row |
| `InvalidJobTransitionError` | `PersistenceError` | A job-status transition is not allowed by the state machine |
| `CorruptRecordError` | `PersistenceError` | Stored JSON cannot be deserialised into the expected Pydantic model |

### Connection ownership

Every public method on all three stores accepts an optional keyword-only
`conn: sqlite3.Connection | None = None` parameter.

- **Repository-owned** (``conn is None``): the store opens a connection via its
  injected ``connection_factory``, executes ``BEGIN``, performs the operation,
  and on success ``COMMIT``. On any exception it ``ROLLBACK``. The connection is
  **always closed** in a ``finally`` block.
- **Caller-supplied** (``conn is not None``): the store does **not** open,
  ``BEGIN``, ``COMMIT``, ``ROLLBACK``, or close the connection. The caller owns
  the full transaction lifecycle.

### Serialization rules

| Table | Column(s) | Serialization |
|---|---|---|
| `extractions` | `paper_id`, `filename` | Stored directly in row columns; **not** duplicated inside JSON |
| `extractions` | `chunks_json` | ``TypeAdapter(list[Chunk]).dump_json(chunks).decode("utf-8")`` — stores only the chunk list |
| `research_maps` | `map_json` | ``ResearchMap.model_dump_json()`` — stores the complete object |
| `research_maps` | `paper_id` | Verified on read: decoded ``ResearchMap.paper_id`` must match the row key; mismatch raises `CorruptRecordError` |
| `jobs` | `created_at`, `updated_at` | ``datetime.now(timezone.utc).isoformat()`` — validated as UTC-aware by the ``Job`` model |
| `jobs` | `error` | Stores only a validated machine-readable error code |
| `jobs` | `status` | ``JobStatus`` enum serialises to bare string via ``StrEnum`` |

### Error code pattern

The ``jobs.error`` column stores only short machine-readable codes matching:

```
^[a-z][a-z0-9_]{0,63}$
```

Examples: ``server_restart``, ``extraction_missing``, ``map_generation_failed``,
``llm_provider_error``, ``persistence_error``, ``task_scheduling_failed``,
``unexpected_error``, ``invalid_job_state``.

Human-readable messages are mapped from codes at the API/router layer, never in
the repository.

### Job transition state machine (strict)

```
pending ──▶ running ──▶ succeeded
   │           │
   └───────────┴──────▶ failed
```

Each transition is atomic ``UPDATE ... WHERE status = ?`` (single source) or
``WHERE status IN ('pending','running')`` (``mark_failed``).  Zero-row updates
first query the current status: absent rows raise ``RecordNotFoundError``;
wrong status raises ``InvalidJobTransitionError``.

There is **no idempotent path** — double-claim detection rejects ``running → running``.

---

## Repository interfaces

### `JobStore`

```python
class JobStore:
    def create(self, paper_id: str, *, conn=None) -> Job: ...
    def get(self, job_id: str, *, conn=None) -> Job | None: ...
    def require(self, job_id: str, *, conn=None) -> Job: ...
    def mark_running(self, job_id: str, *, conn=None) -> Job: ...
    def mark_succeeded(self, job_id: str, *, conn=None) -> Job: ...
    def mark_failed(self, job_id: str, *, error_code: str, conn=None) -> Job: ...
    def get_active_job_for_paper(self, paper_id: str, *, conn=None) -> Job | None: ...
    def has_completed_job_for_paper(self, paper_id: str, *, conn=None) -> bool: ...
    def get_latest_job_for_paper(self, paper_id: str, *, conn=None) -> Job | None: ...
```

### `ExtractionStore`

```python
class ExtractionStore:
    def save(self, extraction: ExtractionResult, *, conn=None) -> None: ...
    def get(self, paper_id: str, *, conn=None) -> ExtractionResult | None: ...
    def require(self, paper_id: str, *, conn=None) -> ExtractionResult: ...
    def exists(self, paper_id: str, *, conn=None) -> bool: ...
```

### `ResearchMapStore`

```python
class ResearchMapStore:
    def save(self, research_map: ResearchMap, *, conn=None) -> None: ...
    def get(self, paper_id: str, *, conn=None) -> ResearchMap | None: ...
    def require(self, paper_id: str, *, conn=None) -> ResearchMap: ...
    def exists(self, paper_id: str, *, conn=None) -> bool: ...
```
