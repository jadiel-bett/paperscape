# PaperScape — Vertical Slice Plan

## Top-Level Overview

**Goal:** Deliver the smallest end-to-end working slice of PaperScape that proves
the full pipeline. A user uploads a selectable-text PDF through the Flutter Web
frontend. The backend extracts page-aware text, enqueues a background job to call
IBM Granite via watsonx.ai, and the frontend polls for completion before rendering
the structured research map. The map displays the research question, three key
findings, limitations, and source evidence (chunk IDs + page numbers).

**Scope:**
- Repository scaffolding (backend, frontend, Docker, docs)
- PDF upload endpoint
- Docling-first / PyMuPDF-fallback extraction service
- LLMProvider interface backed by watsonx.ai (IBM Granite)
- Research-map generation service
- Async job flow using FastAPI `BackgroundTasks` + SQLite job store
- Four FastAPI endpoints under `/api/v1/`: upload, start job, poll job, fetch result
- Flutter Web upload screen + polling progress screen + result screen
- pytest unit and integration tests for all service-layer code
- Docker Compose wiring

**Non-goals for this slice:**
- Audience selection or plain-language explainer generation
- Vector store / semantic search
- Authentication
- Celery, Redis, or any separate worker process
- Streaming responses

**Governing constraints (from AGENTS.md):**
- Services layer must be free of FastAPI/HTTP concepts.
- All watsonx access goes through `LLMProvider` interface.
- Page numbers and section metadata must flow through every layer.
- Every finding must carry source chunk IDs; no post-hoc citation generation.
- API keys never reach the Flutter application.
- Structured JSON responses only; no chain-of-thought.

---

## Sub-task 10 Status and Supersession Notes

This section records implementation status that supersedes parts of the original
historical vertical-slice plan below. The original descriptions are intentionally
left in place for traceability; use this section as the current source for these
items.

- **Sub-task 9 status:** The original Sub-task 9 scope (job creation, polling,
  failure handling, research-map retrieval, findings/evidence/limitations, and
  disclaimer display) was completed inside the expanded Sub-task 8 Flutter
  vertical slice. No separate Sub-task 9 implementation gap remains.
- **Current upload route:** Upload uses `POST /api/v1/papers`, not the older
  planned `POST /api/v1/papers/upload` route.
- **Current upload success status:** Upload returns `201 Created`, not the older
  planned `202 Accepted` status.
- **Current active-job behavior:** `POST /api/v1/papers/{paper_id}/research-map-jobs`
  is idempotent for active jobs. If a `pending` or `running` job already exists,
  the route returns `202 Accepted` with the existing active job instead of `409`.
- **Current frontend API setting:** Flutter Web uses the non-secret compile-time
  value `PAPERSCAPE_API_BASE_URL`; do not use the obsolete `BACKEND_URL` name.
  Changing this value requires rebuilding the Flutter Web app/image.
- **Canonical disclaimer:** Research maps display exactly:

  ```text
  This AI-generated explanation is grounded in the uploaded document but does not replace expert review.
  ```

- **Current frontend layout:** The implemented Flutter vertical slice lives under
  `frontend/lib/app` and `frontend/lib/features/research_map`, not the older
  `frontend/lib/api` and `frontend/lib/screens` sketch below.
- **Verified baseline before Sub-task 10 implementation:** The Sub-task 10 plan
  records the current verified baseline as 422 backend tests passing, 42 frontend
  tests passing, and the offline research-map evaluation passing. Sub-task 10
  verification reports the updated totals after Docker and integration-test work.
- **Sub-task 10 final verification baseline:** 424 backend tests were collected
  and all 424 passed, including both Sub-task 10 integration tests. All 42
  frontend tests passed, the offline ResearchMap evaluation passed, Flutter
  analyze passed, and the Flutter Web release build passed.
- **Docker ownership:** Production-like backend image, multi-stage Flutter Web
  image, unprivileged nginx runtime, two-service Compose topology, named SQLite
  volume, healthchecks, and Docker usage documentation are owned by Sub-task 10.

---

## Repository Structure

```
paperscape/
├── AGENTS.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── data-model.md              # Canonical data shapes (written in Sub-task 1)
│   └── vertical-slice-plan.md     # This file
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py                # FastAPI app factory
│       ├── config.py              # Settings via pydantic-settings
│       ├── database.py            # SQLite connection + migrations (jobs table)
│       ├── models/                # Pydantic request/response models
│       │   ├── __init__.py
│       │   ├── paper.py           # Chunk, ExtractionResult, UploadResponse
│       │   ├── research_map.py    # Finding, ResearchMap
│       │   └── job.py             # Job, JobStatus, JobStatusResponse
│       ├── services/              # Pure business logic, no HTTP
│       │   ├── __init__.py
│       │   ├── extraction.py      # PDF → ExtractionResult
│       │   ├── llm_provider.py    # LLMProvider interface + WatsonxProvider
│       │   ├── research_map.py    # ExtractionResult → ResearchMap
│       │   └── job_store.py       # CRUD for jobs in SQLite
│       ├── prompts/
│       │   └── research_map.txt   # Prompt template for map generation
│       └── routers/
│           ├── __init__.py
│           ├── papers.py          # Upload + research-map-jobs + research-map endpoints
│           └── jobs.py            # GET /jobs/{job_id}
│
├── frontend/
│   ├── pubspec.yaml
│   └── lib/
│       ├── main.dart
│       ├── api/
│       │   └── papers_api.dart    # uploadPaper, startMapJob, pollJob, fetchMap
│       └── screens/
│           ├── upload_screen.dart # PDF picker + submit
│           ├── processing_screen.dart # Polling progress display
│           └── map_screen.dart    # Research map display
│
└── evals/
    ├── fixtures/                  # Static PDF text fixtures (no live backend)
    └── expected/                  # Expected JSON outputs for prompt regression
```

---

## API Contracts

All endpoints are prefixed with `/api/v1`.

---

### POST `/api/v1/papers/upload`

Accepts a multipart/form-data PDF. Runs extraction synchronously (fast, CPU-only)
and stores the `ExtractionResult` in SQLite. Returns immediately.

**Request:** `multipart/form-data`
- `file`: PDF binary (`application/pdf`)

**Response `202 Accepted`:**
```json
{
  "paper_id": "uuid-v4",
  "filename": "paper.pdf",
  "page_count": 12,
  "chunk_count": 47
}
```

**Error responses:**
- `400` — not a PDF, or PDF contains no selectable text
- `413` — file exceeds `UPLOAD_MAX_BYTES`
- `422` — validation error
- `500` — extraction failure

---

### POST `/api/v1/papers/{paper_id}/research-map-jobs`

Enqueues a background job to generate the research map for a previously uploaded
paper. Returns immediately with a `job_id` the client can poll.

**Request:** empty body (paper_id is in the path)

**Response `202 Accepted`:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "pending"
}
```

**Error responses:**
- `404` — `paper_id` not found
- `409` — a job for this paper is already `pending` or `running`
- `422` — validation error

---

### GET `/api/v1/jobs/{job_id}`

Returns the current status of a background job.

**Response `200 OK` — job in progress:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "pending | running",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "error": null
}
```

**Response `200 OK` — job succeeded:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "succeeded",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "error": null
}
```

**Response `200 OK` — job failed:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "failed",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "error": "Human-readable failure reason"
}
```

**Error responses:**
- `404` — `job_id` not found

---

### GET `/api/v1/papers/{paper_id}/research-map`

Returns the completed research map. Must only be called after the corresponding
job reaches `succeeded` status.

**Response `200 OK`:**
```json
{
  "paper_id": "uuid-v4",
  "research_question": "string",
  "findings": [
    {
      "statement": "string",
      "evidence": [
        { "chunk_id": "string", "page": 3, "excerpt": "string" }
      ],
      "confidence": "high | partial | uncertain"
    }
  ],
  "limitations": ["string"],
  "disclaimer": "This AI-generated explanation is grounded in the uploaded document but does not replace expert review."
}
```

**Error responses:**
- `404` — paper not found, or map not yet generated
- `409` — job exists but has not yet succeeded (client should keep polling)

---

### GET `/api/v1/health`

**Response `200 OK`:**
```json
{ "status": "ok" }
```

---

## Pydantic Models

### `backend/app/models/paper.py`

| Model | Fields | Notes |
|---|---|---|
| `Chunk` | `chunk_id: str`, `page: int`, `section: str \| None`, `text: str` | Page numbers 1-based |
| `ExtractionResult` | `paper_id: str`, `filename: str`, `chunks: list[Chunk]` | Output of extraction service |
| `UploadResponse` | `paper_id: str`, `filename: str`, `page_count: int`, `chunk_count: int` | API response for upload |

### `backend/app/models/research_map.py`

| Model | Fields | Notes |
|---|---|---|
| `Evidence` | `chunk_id: str`, `page: int`, `excerpt: str` | excerpt ≤ 300 chars |
| `Finding` | `statement: str`, `evidence: list[Evidence]`, `confidence: Literal["high","partial","uncertain"]` | Exactly 3 findings required |
| `ResearchMap` | `paper_id: str`, `research_question: str`, `findings: list[Finding]`, `limitations: list[str]`, `disclaimer: str` | disclaimer is a hardcoded constant |

### `backend/app/models/job.py`

| Model | Fields | Notes |
|---|---|---|
| `JobStatus` | `Literal["pending","running","succeeded","failed"]` | Enum-like literal |
| `Job` | `job_id: str`, `paper_id: str`, `status: JobStatus`, `created_at: datetime`, `updated_at: datetime`, `error: str \| None` | Persisted to SQLite |
| `JobCreateResponse` | `job_id: str`, `paper_id: str`, `status: JobStatus` | Returned by POST research-map-jobs |
| `JobStatusResponse` | all `Job` fields | Returned by GET jobs/{job_id} |

### `backend/app/config.py`

| Setting | Env var | Default / Notes |
|---|---|---|
| `watsonx_api_key` | `WATSONX_API_KEY` | Required, never logged |
| `watsonx_url` | `WATSONX_URL` | e.g. `https://us-south.ml.cloud.ibm.com` |
| `watsonx_project_id` | `WATSONX_PROJECT_ID` | Required |
| `granite_model_id` | `GRANITE_MODEL_ID` | Default: `ibm/granite-13b-instruct-v2` |
| `upload_max_bytes` | `UPLOAD_MAX_BYTES` | Default: `20971520` (20 MB) |
| `cors_origins` | `CORS_ORIGINS` | Comma-separated list |
| `database_url` | `DATABASE_URL` | Default: `sqlite:///./paperscape.db` |

---

## Service Boundaries

### `extraction.py` — ExtractionService

**Responsibility:** Convert a raw PDF `bytes` object into an `ExtractionResult`.

**Interface:**
```
extract(pdf_bytes: bytes, filename: str, paper_id: str) -> ExtractionResult
```

**Strategy:**
1. Attempt Docling extraction (`DocumentConverter`). If successful and chunk
   count > 0, return result.
2. On `DoclingException` or zero chunks, fall back to PyMuPDF (`fitz.open`).
3. If both return zero chunks, raise `ExtractionError`.

**Rules:**
- No FastAPI imports. Accepts and returns pure Pydantic models.
- Chunk IDs are deterministic: `f"{paper_id}-p{page}-{index}"`.
- Section metadata from Docling heading labels; `None` for PyMuPDF fallback.

---

### `llm_provider.py` — LLMProvider Interface + WatsonxProvider

**Responsibility:** Isolate all watsonx.ai communication so services never
import the SDK directly.

**Interface (ABC):**
```
class LLMProvider(ABC):
    def generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str
```

**WatsonxProvider (concrete):**
- Constructed from a `Settings` object.
- Calls `ibm-watsonx-ai` SDK's `ModelInference.generate()`.
- Returns raw text string from the model response.
- Raises `LLMProviderError` on HTTP failure, timeout, or empty response.
- One exponential-backoff retry on transient failures.

**Rules:**
- No FastAPI imports.
- Credentials come from a `Settings` object passed at construction; not read
  from environment directly.

---

### `research_map.py` — ResearchMapService

**Responsibility:** Accept an `ExtractionResult`, build a prompt, call the LLM,
and parse the response into a validated `ResearchMap`.

**Interface:**
```
generate_map(extraction: ExtractionResult, provider: LLMProvider) -> ResearchMap
```

**Strategy:**
1. Truncate chunks to a 6000-word token-safe window (configurable). Include
   chunk IDs and page numbers in the prompt context.
2. Load prompt template from `backend/app/prompts/research_map.txt`.
3. Call `provider.generate()` with `max_tokens=1500`, `temperature=0.1`.
4. Parse response with `ResearchMap.model_validate_json()`.
5. Validate exactly 3 findings. On failure, retry once with a corrective prompt
   fragment. Raise `MapGenerationError` after two failures.
6. Append hardcoded disclaimer.

**Rules:**
- No FastAPI imports.
- Prompt template changes require a baseline update in `evals/expected/`.

---

### `job_store.py` — JobStore

**Responsibility:** Persist job records and `ResearchMap` results to SQLite so
they survive across background-task completion and are readable by subsequent
HTTP requests.

**Interface:**
```
create_job(paper_id: str) -> Job
get_job(job_id: str) -> Job | None
set_running(job_id: str) -> None
set_succeeded(job_id: str, result: ResearchMap) -> None
set_failed(job_id: str, error: str) -> None
get_result(paper_id: str) -> ResearchMap | None
get_active_job_for_paper(paper_id: str) -> Job | None
```

**Storage:**
- Single SQLite file (`paperscape.db`) at the path set by `DATABASE_URL`.
- Two tables: `jobs` (status metadata) and `research_maps` (serialised JSON
  result, keyed by `paper_id`).
- Schema created on app startup via a lightweight migration in `database.py`.
- The `ExtractionResult` is also persisted in a third table `extractions` so
  the background task can retrieve it without the HTTP request context.

**Rules:**
- No FastAPI imports. Pure Python + `sqlite3` (stdlib; no ORM required for
  this slice).

---

## Background Job Flow

```
POST /api/v1/papers/{paper_id}/research-map-jobs
  │
  ├── Validates paper_id exists in DB
  ├── Checks no active job already exists (409 guard)
  ├── Creates Job record (status=pending) in SQLite via JobStore
  ├── Registers _run_map_job(job_id, paper_id) with BackgroundTasks
  └── Returns 202 { job_id, paper_id, status="pending" }

BackgroundTasks._run_map_job(job_id, paper_id):
  ├── job_store.set_running(job_id)
  ├── extraction = job_store.get_extraction(paper_id)
  ├── result = research_map_service.generate_map(extraction, provider)
  │     ├── On success → job_store.set_succeeded(job_id, result)
  │     └── On MapGenerationError / LLMProviderError
  │           └── job_store.set_failed(job_id, error_message)
  └── (returns; BackgroundTasks handles thread lifecycle)

GET /api/v1/jobs/{job_id}        ← polled every 1-2 s by frontend
  └── Returns current Job record from SQLite

GET /api/v1/papers/{paper_id}/research-map
  ├── If no succeeded job → 409
  └── Returns ResearchMap JSON from SQLite
```

---

## Implementation Phases

### Phase 1 — Repository Scaffold & Data Model
Stand up the project skeleton: directory tree, `data-model.md`, `.env.example`
files, docker-compose stub, and `evals/` directories.

### Phase 2 — Backend: Models, Config, and Database Layer
Define all Pydantic models, `Settings`, and the SQLite schema
(`jobs`, `extractions`, `research_maps` tables). No services yet.

### Phase 3 — Backend: Extraction Service
Docling-first / PyMuPDF-fallback extraction; `ExtractionError`; unit tests.

### Phase 4 — Backend: LLM Provider Interface and WatsonxProvider
`LLMProvider` ABC, `WatsonxProvider` with retry; `LLMProviderError`; unit tests.

### Phase 5 — Backend: Research Map Service and Prompt Template
`ResearchMapService`, `research_map.txt` prompt, `MapGenerationError`, eval
baseline; unit tests.

### Phase 6 — Backend: JobStore Service
`JobStore` with full CRUD over SQLite; unit tests against an in-memory
`:memory:` SQLite database.

### Phase 7 — Backend: FastAPI Routers, BackgroundTasks, and Docker
Wire all services into the four endpoints, register background task runner,
write `Dockerfile`; API tests using `TestClient` with overridden dependencies.

### Phase 8 — Frontend: Flutter Scaffold and Upload Screen
Flutter Web project, PDF file picker, `POST /api/v1/papers/upload`, loading
states, error handling.

### Phase 9 — Frontend: Polling and Map Screens
`POST /api/v1/papers/{id}/research-map-jobs`, poll `GET /api/v1/jobs/{job_id}`
every 1.5 s, transition to map screen on `succeeded`, display failure message
on `failed`.

### Phase 10 — Docker Compose and End-to-End Validation
Complete `docker-compose.yml`, nginx frontend container, integration test,
acceptance criteria walkthrough.

### Phase 11 — Eval Baseline
Capture expected `ResearchMap` JSON in `evals/expected/`. Document eval rerun
procedure.

---

## Testing Strategy

### Unit Tests (`backend/tests/unit/`)

| Test file | What it covers |
|---|---|
| `test_models.py` | Pydantic validation edge cases for all models including `JobStatus` transitions |
| `test_extraction.py` | Docling path with fixture PDF; PyMuPDF fallback; `ExtractionError` on zero-text |
| `test_llm_provider.py` | `WatsonxProvider` with mocked SDK; retry on transient error; `LLMProviderError` |
| `test_research_map.py` | Happy path with mock provider; `MapGenerationError` on bad JSON; `MapGenerationError` on wrong finding count; truncation logic |
| `test_job_store.py` | `create_job`; `set_running`; `set_succeeded` with result; `set_failed`; `get_active_job_for_paper` deduplication guard — all against in-memory SQLite |

### API Tests (`backend/tests/api/`)

| Test file | What it covers |
|---|---|
| `test_papers_router.py` | `POST /upload` happy path; 400 on non-PDF; 413 on oversized file; 400 on image-only PDF |
| `test_jobs_router.py` | `POST /research-map-jobs` 202 with job_id; 404 on unknown paper_id; 409 on duplicate active job; `GET /jobs/{job_id}` for pending / running / succeeded / failed; `GET /research-map` 200 after success; 409 if job not yet succeeded; 404 if no map |

### Integration Test (`backend/tests/integration/`)

| Test file | What it covers |
|---|---|
| `test_pipeline.py` | Upload fixture PDF → start map job → poll until status `succeeded` (watsonx mocked) → fetch research map → assert all acceptance criteria fields present |

### Eval Pipeline (`evals/`)

| File | Purpose |
|---|---|
| `evals/run_evals.py` | Runs extraction + map generation against fixture PDFs, diffs output against `evals/expected/*.json` |
| `evals/fixtures/` | Static fixture PDFs; no live backend required |
| `evals/expected/` | Committed expected JSON; updated deliberately after prompt changes |

**Testing rules:**
- All service-layer tests use dependency injection; no env vars or live network.
- `JobStore` tests use `sqlite3` in-memory (`:memory:`) — no file on disk.
- API tests use `TestClient` with FastAPI dependency overrides.
- Live watsonx calls gated behind `WATSONX_LIVE_TEST=1`; never run in default CI.
- Background task execution in API tests is run synchronously by calling the
  task function directly after the response, not through the real async runner.

---

## Security Considerations

| Risk | Mitigation |
|---|---|
| API key exposure | Keys in `.env`, never logged, never serialised into any response, never forwarded to frontend |
| Malicious PDF | Validate `Content-Type: application/pdf`; enforce `UPLOAD_MAX_BYTES` before reading bytes; wrap Docling/PyMuPDF parse in try/except |
| Prompt injection | Wrap paper content in explicit `<PAPER_CONTENT>` delimiters in the prompt; model instructed to treat content as data only |
| Secret leakage via Docker | `Dockerfile` must not `COPY .env`; secrets injected at runtime via `env_file` in Compose |
| CORS | `CORSMiddleware` allows only `CORS_ORIGINS` env-configured list; default blocks all cross-origin |
| SQLite path traversal | `DATABASE_URL` validated in `config.py` to allow only a relative file path or `:memory:`; no user-supplied path |
| Stale failed jobs | Failed jobs remain in DB for audit; a simple `updated_at` timestamp lets operators identify and clean up old records |

---

## Risks and Fallback Approaches

| Risk | Likelihood | Fallback |
|---|---|---|
| Docling fails to install in Docker due to native deps | Medium | `EXTRACTION_BACKEND=pymupdf` env flag bypasses Docling entirely |
| Granite returns malformed JSON | Medium | One retry with corrective prompt fragment; `MapGenerationError` and job `failed` after two attempts |
| watsonx credentials wrong at startup | Low | `config.py` validates required fields; app fails to start with descriptive error |
| BackgroundTasks thread crash leaves job in `running` state | Low | On startup, `database.py` migration resets any `running` jobs to `failed` with error `"server_restart"` |
| Flutter polling hammers backend | Low | 1.5 s polling interval with exponential back-off after 5 consecutive non-terminal responses |
| Flutter web file picker platform quirks | Low | Use `file_picker` package (stable web support); tested in Chrome |
| PDF has no extractable text (scanned) | Medium | Return `400` "PDF contains no selectable text; OCR not supported in this version" |
| Token window exceeded for large PDFs | Medium | Truncate to first 6000 words; log warning with `paper_id` and actual count |
| Rate limiting on watsonx free tier | Low | Exponential backoff with one retry in `WatsonxProvider`; surface `LLMProviderError` → job `failed` |
| SQLite write contention | Very Low | Single-worker uvicorn in dev; `check_same_thread=False` + WAL mode for Docker |

---

## Acceptance Criteria

The vertical slice is complete when ALL of the following are true:

1. **Upload:** A user can select and upload a selectable-text PDF through
   Flutter Web. The upload returns a `paper_id` and `chunk_count` without error.

2. **Extraction:** The backend extracts at least one text chunk per page,
   preserving the page number, for a typical academic PDF.

3. **Job Start:** `POST /api/v1/papers/{paper_id}/research-map-jobs` returns
   `202` with a `job_id` and `status: "pending"` immediately (no blocking wait).

4. **Job Polling:** `GET /api/v1/jobs/{job_id}` correctly reflects
   `pending → running → succeeded` (or `failed`) as the background task
   progresses.

5. **Research Map Result:** After the job reaches `succeeded`,
   `GET /api/v1/papers/{paper_id}/research-map` returns a valid `ResearchMap`
   containing:
   - A non-empty `research_question`
   - Exactly 3 `findings`, each with ≥ 1 `evidence` item (with `chunk_id`,
     `page`, `excerpt`)
   - ≥ 1 `limitations` string
   - The hardcoded `disclaimer`

6. **Failure Handling:** When the LLM call fails, the job transitions to
   `failed` with a non-empty `error` string, and the frontend displays a
   user-readable error state.

7. **Duplicate Guard:** A second `POST /research-map-jobs` for the same
   `paper_id` while a job is `pending` or `running` returns `409`.

8. **Frontend Flow:** The Flutter frontend transitions through Upload →
   Processing (polling with progress indicator) → Map display (all five
   elements rendered) or Error screen — without layout overflow at 1280×800.

9. **Tests pass:** `pytest backend/tests/` passes with zero failures, covering
   extraction, LLM provider, research-map service, job store, and all router
   endpoints.

10. **No secrets in code:** No API key or credential appears in any committed
    file. `.env.example` documents all required variables with descriptions.

11. **Docker Compose up:** `docker compose up` starts both services. Frontend
    reachable at `http://localhost:8080`; backend at `http://localhost:8000/api/v1/health`.

12. **Eval baseline committed:** At least one fixture PDF and its expected
    `ResearchMap` JSON exist in `evals/`.

---

## Sub-Tasks

### Sub-task 1 — Repository Scaffold & Data Model Doc
- **Intent:** Create the directory tree, canonical `docs/data-model.md`, and
  all placeholder files so every subsequent sub-task has a home.
- **Expected Outcomes:**
  - Directory tree matches the Repository Structure section exactly.
  - `docs/data-model.md` documents all models: `Chunk`, `ExtractionResult`,
    `UploadResponse`, `Evidence`, `Finding`, `ResearchMap`, `Job`,
    `JobStatus`, `JobCreateResponse`, `JobStatusResponse`.
  - Root `.env.example` and `backend/.env.example` list every required env var
    with a one-line description.
  - `docker-compose.yml` stub contains `backend` and `frontend` service stubs.
  - `evals/fixtures/` and `evals/expected/` exist with `.gitkeep`.
- **Todo List:**
  1. Create `docs/data-model.md`.
  2. Create root `.env.example` with all `WATSONX_*`, `DATABASE_URL`,
     `UPLOAD_MAX_BYTES`, `CORS_ORIGINS` vars.
  3. Create `backend/.env.example` (same content, scoped to backend).
  4. Create stub `docker-compose.yml`.
  5. Create all `__init__.py` and empty module stubs under `backend/app/`.
  6. Create `evals/fixtures/` and `evals/expected/` with `.gitkeep`.
  7. Create Flutter project skeleton under `frontend/` with `pubspec.yaml`.
- **Relevant Context:** Repository Structure section; Pydantic Models section.
- **Status:** [ ] pending

---

### Sub-task 2 — Backend: Pydantic Models, Config, and Database Layer
- **Intent:** Define exact data contracts for all layers and set up the SQLite
  schema before any service code is written.
- **Expected Outcomes:**
  - `backend/app/models/paper.py` defines `Chunk`, `ExtractionResult`,
    `UploadResponse`.
  - `backend/app/models/research_map.py` defines `Evidence`, `Finding`,
    `ResearchMap`.
  - `backend/app/models/job.py` defines `JobStatus`, `Job`,
    `JobCreateResponse`, `JobStatusResponse`.
  - `backend/app/config.py` loads all settings from env vars via
    `pydantic-settings`; fails fast on missing required vars.
  - `backend/app/database.py` creates the three tables (`jobs`, `extractions`,
    `research_maps`) on first call; resets stale `running` jobs to `failed`
    on startup.
  - `test_models.py` passes all validation edge cases.
- **Todo List:**
  1. Write `backend/app/models/paper.py`.
  2. Write `backend/app/models/research_map.py`.
  3. Write `backend/app/models/job.py`.
  4. Write `backend/app/config.py`.
  5. Write `backend/app/database.py` with `init_db()` and schema SQL.
  6. Write `backend/tests/unit/test_models.py`.
  7. Add `pydantic`, `pydantic-settings` to `requirements.txt`.
- **Relevant Context:** Pydantic Models section; JobStore — Storage description.
- **Status:** [ ] pending

---

### Sub-task 3 — Backend: Extraction Service
- **Intent:** Implement Docling-first / PyMuPDF-fallback extraction as a pure
  service with no HTTP dependencies.
- **Expected Outcomes:**
  - `ExtractionService.extract()` returns an `ExtractionResult` with ≥ 1 chunk
    per page for a typical PDF.
  - Docling failure triggers transparent PyMuPDF fallback.
  - Zero-text PDF raises `ExtractionError`.
  - `test_extraction.py` passes all three scenarios.
- **Todo List:**
  1. Write `backend/app/services/extraction.py` with Docling and PyMuPDF paths.
  2. Define `ExtractionError` in a shared `exceptions.py` or inline.
  3. Add `docling`, `pymupdf` to `requirements.txt`.
  4. Write `backend/tests/unit/test_extraction.py` using a programmatically
     generated small PDF fixture (e.g. via `fpdf2`).
  5. Verify chunk IDs follow `{paper_id}-p{page}-{index}`.
- **Relevant Context:** Service Boundaries — ExtractionService section.
- **Status:** [ ] pending

---

### Sub-task 4 — Backend: LLM Provider Interface and WatsonxProvider
- **Intent:** Build the `LLMProvider` ABC and `WatsonxProvider` so all other
  services type-hint against the interface, not the SDK.
- **Expected Outcomes:**
  - `LLMProvider` ABC is importable as a type.
  - `WatsonxProvider.generate()` calls the SDK with correct params and returns
    a string.
  - Transient SDK failure triggers one retry; persistent failure raises
    `LLMProviderError`.
  - `test_llm_provider.py` passes with mocked `ModelInference`.
- **Todo List:**
  1. Write `backend/app/services/llm_provider.py`.
  2. Add `ibm-watsonx-ai` to `requirements.txt`.
  3. Write `backend/tests/unit/test_llm_provider.py`.
  4. Confirm no env vars read directly inside the provider.
- **Relevant Context:** Service Boundaries — LLMProvider section.
- **Status:** [ ] pending

---

### Sub-task 5 — Backend: Research Map Service and Prompt Template
- **Intent:** Implement map generation as a pure service and establish the
  eval baseline.
- **Expected Outcomes:**
  - `ResearchMapService.generate_map()` returns a valid `ResearchMap` given a
    mock provider returning well-formed JSON.
  - `MapGenerationError` raised on bad JSON or wrong finding count, after one
    retry.
  - `test_research_map.py` passes all scenarios.
  - `evals/expected/research_map_fixture.json` committed.
- **Todo List:**
  1. Write `backend/app/prompts/research_map.txt` with `<PAPER_CONTENT>`
     delimiters and JSON schema instructions.
  2. Write `backend/app/services/research_map.py`.
  3. Define `MapGenerationError`.
  4. Write `backend/tests/unit/test_research_map.py`.
  5. Write `evals/run_evals.py`.
  6. Commit `evals/expected/research_map_fixture.json`.
- **Relevant Context:** Service Boundaries — ResearchMapService; AI rules in
  AGENTS.md.
- **Status:** [ ] pending

---

### Sub-task 6 — Backend: JobStore Service
- **Intent:** Implement the persistence layer for job state and results so
  background tasks and HTTP handlers share a reliable store.
- **Expected Outcomes:**
  - All `JobStore` methods work correctly against an in-memory SQLite DB.
  - `get_active_job_for_paper` returns the existing job when one is
    `pending`/`running`, enabling the `409` guard.
  - `test_job_store.py` passes all CRUD scenarios.
- **Todo List:**
  1. Write `backend/app/services/job_store.py` using stdlib `sqlite3`.
  2. Write `backend/tests/unit/test_job_store.py` with an in-memory fixture DB.
  3. Test `set_succeeded` persists `ResearchMap` JSON and `get_result` retrieves
     it correctly.
  4. Test stale-job cleanup at startup (running → failed on restart).
- **Relevant Context:** Service Boundaries — JobStore section; Background Job
  Flow section.
- **Status:** [ ] pending

---

### Sub-task 7 — Backend: FastAPI Routers, BackgroundTasks, and Dockerfile
- **Intent:** Wire all services into the four API endpoints and package the
  backend in Docker.
- **Expected Outcomes:**
  - All four endpoints (`/upload`, `/research-map-jobs`, `/jobs/{id}`,
    `/research-map`) respond correctly per the API Contracts section.
  - `409` returned on duplicate active job.
  - Background task function (`_run_map_job`) is unit-testable by calling it
    directly with a test DB.
  - `docker build` succeeds; container responds to `/api/v1/health`.
  - `test_papers_router.py` and `test_jobs_router.py` pass.
- **Todo List:**
  1. Write `backend/app/routers/papers.py` (upload, research-map-jobs,
     research-map endpoints).
  2. Write `backend/app/routers/jobs.py` (job status endpoint).
  3. Write `backend/app/main.py` (app factory, CORS, router registration,
     `init_db()` on startup).
  4. Wire `ExtractionService`, `ResearchMapService`, `JobStore`, and
     `LLMProvider` via FastAPI dependency injection.
  5. Write `backend/tests/api/test_papers_router.py`.
  6. Write `backend/tests/api/test_jobs_router.py`.
  7. Write `backend/Dockerfile` (python:3.11-slim, non-root user, no .env copy).
- **Relevant Context:** API Contracts; Background Job Flow; Security —
  Dockerfile; Risks — BackgroundTasks crash.
- **Status:** [ ] pending

---

### Sub-task 8 — Frontend: Flutter Scaffold and Upload Screen
- **Intent:** Create the minimal Flutter Web project and the upload screen with
  file picker and error handling.
- **Expected Outcomes:**
  - `flutter build web` succeeds.
  - User can pick a PDF, see the filename, and click Upload.
  - Loading indicator shown during upload.
  - On success, navigates to Processing screen with `paper_id`.
  - On error (400, 413, 500), shows a user-readable message.
- **Todo List:**
  1. Create Flutter project: `flutter create frontend --platforms web`.
  2. Add `file_picker`, `http` to `pubspec.yaml`.
  3. Write `frontend/lib/api/papers_api.dart` with `uploadPaper()`.
  4. Write `frontend/lib/screens/upload_screen.dart`.
  5. Set backend URL via `--dart-define=BACKEND_URL=http://localhost:8000`.
- **Relevant Context:** API Contracts — POST /upload; Security — no API keys.
- **Status:** [ ] pending

---

### Sub-task 9 — Frontend: Polling and Research Map Screens
- **Intent:** Implement the async polling loop and the research map display.
- **Expected Outcomes:**
  - After upload, `POST /research-map-jobs` is called automatically.
  - Processing screen polls `GET /jobs/{job_id}` every 1.5 s, showing
    `pending`, `running` states.
  - On `succeeded`, navigates to Map screen and calls `GET /research-map`.
  - On `failed`, shows the `error` field as a user-readable message with a
    Retry button.
  - Map screen renders: research question, 3 findings with evidence + page
    numbers + confidence badge, limitations list, disclaimer — no overflow at
    1280×800.
- **Todo List:**
  1. Add `startMapJob()`, `pollJob()`, `fetchResearchMap()` to `papers_api.dart`.
  2. Write `frontend/lib/screens/processing_screen.dart` with polling timer.
  3. Write `frontend/lib/screens/map_screen.dart` with all five display sections.
  4. Implement confidence badge widget (colour-coded: high=green, partial=amber,
     uncertain=red).
  5. Wire navigation: Upload → Processing → Map (or Error).
- **Relevant Context:** API Contracts — jobs and research-map endpoints;
  Acceptance Criteria items 3–6, 8.
- **Status:** [ ] pending

---

### Sub-task 10 — Docker Compose and End-to-End Validation
- **Intent:** Wire the full stack in Docker Compose and verify every acceptance
  criterion.
- **Expected Outcomes:**
  - `docker compose up` starts `backend` and `frontend` without error.
  - Frontend at `http://localhost:8080`; backend health at
    `http://localhost:8000/api/v1/health`.
  - Integration test `test_pipeline.py` passes end-to-end with mocked watsonx.
  - All 12 acceptance criteria verified.
- **Todo List:**
  1. Complete `docker-compose.yml` with build contexts, port mappings, `env_file`
     references, and `healthcheck` directives.
  2. Write `frontend/Dockerfile` (Flutter web build → nginx).
  3. Write `backend/tests/integration/test_pipeline.py`.
  4. Walk through all 12 acceptance criteria and confirm each is met.
  5. Commit `evals/fixtures/` fixture PDF and `evals/expected/` baseline JSON.
- **Relevant Context:** Acceptance Criteria; Risks — SQLite WAL mode for Docker.
- **Status:** [ ] pending
