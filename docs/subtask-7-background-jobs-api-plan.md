# Sub-task 7 — Background Research-Map Orchestration and Vertical-Slice FastAPI Endpoints

## 1. Current Route and App-Factory Assessment

### Existing state

> **Pre-implementation assessment:** This section records the state observed
> before Sub-task 7 implementation and is retained for audit context.

- **`backend/app/main.py`** — `create_app()` factory receives optional `Settings`, creates a `FastAPI` app with CORS middleware, a lifespan hook that calls `init_db()`, and registers only `health_router` at `/api/v1`. A module-level `app` instance is created for Uvicorn.
- **`backend/app/config.py`** — `Settings` model (pydantic-settings) with all required fields. `get_settings()` is cached with `@lru_cache(maxsize=1)`.
- **`backend/app/database.py`** — `init_db()` creates three tables, resets stale `pending` and `running` jobs to `failed`. `get_connection()` opens and configures SQLite connections.
- **`backend/app/routers/__init__.py`** — Exports the health, papers, and jobs routers.
- **`backend/app/routers/health.py`** — Single `GET /health` returning `{"status": "ok"}`.
- **`backend/tests/conftest.py`** — Session-scoped `test_settings` (temp file DB, `_env_file=None`), `test_app`, `test_client`.
- **`backend/tests/api/test_health.py`** — Health endpoint test exists.

### Gaps to fill

- No paper upload, job creation, job polling, or research-map retrieval endpoints exist.
- No dependency-injection layer exists — services/repositories are not wired.
- No `ResearchMapJobRunner` exists.
- No background-task orchestration exists.
- Router registration is minimal.
- Startup recovery only resets `running` jobs; must also reset `pending` jobs.
- No in-process concurrency protection for job creation.

---

## 2. Exact Files Created and Modified

### New files

| File | Purpose |
|---|---|
| `backend/app/services/research_map_job_runner.py` | Synchronous runner invoked by `BackgroundTasks` |
| `backend/app/dependencies.py` | Service container and FastAPI dependency callables |
| `backend/app/routers/papers.py` | Upload, create job, retrieve research-map endpoints |
| `backend/app/routers/jobs.py` | Poll job-status endpoint |
| `backend/tests/unit/test_research_map_job_runner.py` | Job-runner unit tests |
| `backend/tests/api/test_papers.py` | Upload and research-map endpoint tests |
| `backend/tests/api/test_jobs.py` | Job creation, polling, and retrieval tests |
| `docs/subtask-7-background-jobs-api-plan.md` | This plan |

### Modified files

| File | Change |
|---|---|
| `backend/app/main.py` | Accept optional `container` param; wire on `app.state` before lifespan; register new routers |
| `backend/app/database.py` | Reset both `pending` and `running` jobs to `failed` on startup |
| `backend/app/repositories/job_store.py` | Add `get_latest_job_for_paper()` method |
| `backend/app/config.py` | No changes required for vertical slice |
| `backend/app/routers/__init__.py` | Export router symbols |
| `backend/.env.example` | No changes required |
| `backend/requirements.txt` | Add `python-multipart` |
| `docs/data-model.md` | Add `UploadResponse` HTTP status change (201 vs 202), document error response shape, document latest-job retrieval requirement |
| `backend/app/models/paper.py` | `UploadResponse` page_count and chunk_count validation may need `Field(ge=0)` — already present |

### Excluded from implementation

- `docs/bob-usage-log.md` — Updated in a separate commit after implementation, with Sub-task 7 commit hash.

---

## 3. Endpoint Contracts

All endpoints are prefixed with `/api/v1`.

### 3.1 `POST /api/v1/papers` — Upload and extract paper

**Request:**
```
POST /api/v1/papers
Content-Type: multipart/form-data

file: <PDF binary>
```

**Response `201 Created`:**
```json
{
  "paper_id": "uuid-v4",
  "filename": "paper.pdf",
  "page_count": 12,
  "chunk_count": 47
}
```

**Error responses:**

| Status | Code | Condition |
|---|---|---|
| 400 | `invalid_upload` | Empty file or blank filename |
| 415 | `unsupported_media_type` | `file.content_type` is missing or not `application/pdf` |
| 400 | `upload_not_a_pdf` | PDF signature is not detected |
| 413 | `upload_too_large` | File exceeds `settings.upload_max_bytes` |
| 422 | `extraction_failed` | PDF has no selectable text or extraction cannot process it |
| 500 | `persistence_error` | Database write failure |

**Behavior sequence:**

1. Receive `UploadFile` from FastAPI form parameter.
2. Validate `file.filename` is non-blank (reject with `invalid_upload`).
3. Validate `file.content_type` is `application/pdf` (reject with `unsupported_media_type` and HTTP 415). Do **not** check the request-level multipart `Content-Type`.
4. Read at most `max_bytes + 1` bytes via `await file.read(max_bytes + 1)`.
5. If `len(data) == 0` → reject with `invalid_upload`.
6. If `len(data) > max_bytes` → reject with `upload_too_large`.
7. Optionally check for `%PDF-` within the first 1,024 bytes as a lightweight validation signal. If absent, reject with `upload_not_a_pdf`.
8. Generate `paper_id` via the injected UUID factory.
9. Run extraction in the thread pool: `extraction = await run_in_threadpool(extraction_service.extract, data, filename, paper_id)`.
10. Persist the `ExtractionResult` in the thread pool: `await run_in_threadpool(extraction_store.save, extraction)`.
11. Close the `UploadFile` in a `finally` block.
12. Return `UploadResponse` with HTTP 201.

**Storage guarantee:** PaperScape does not deliberately persist or manage the original PDF as a file. Do not write a brittle test asserting Starlette never uses a spooled temporary file internally.

### 3.2 `POST /api/v1/papers/{paper_id}/research-map-jobs` — Create research-map job

**Response `202 Accepted`:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "pending"
}
```

**Decision — Duplicate active job behavior:**

The endpoint returns **HTTP 202 with the existing active job** when an active (`pending` or `running`) job already exists for the paper. This provides idempotent client retry behavior.

A previously succeeded or failed latest job does **not** block a new job — the client can always request regeneration or retry.

**In-process concurrency protection:**

Active-job lookup and job creation are protected by a single `threading.Lock` stored in the service container:

```python
with container.job_creation_lock:
    active = job_store.get_active_job_for_paper(paper_id)
    if active is not None:
        return active
    job = job_store.create(paper_id)
```

The lock covers only database checks and creation. It is **not** held during `BackgroundTasks.add_task()` or inference. This protects against concurrent API requests inside one process but does **not** provide cross-process safety.

**Generation-unavailable guard:**

When the service container has no `job_runner_factory` (because watsonx credentials are unavailable), the endpoint returns **HTTP 503** immediately:

```json
{
  "detail": {
    "code": "generation_unavailable",
    "message": "Research-map generation is not available. Check that watsonx credentials are configured."
  }
}
```

No job is created, no `BackgroundTask` is scheduled.

**Behavior sequence:**

1. Validate `paper_id` format.
2. Confirm extraction exists via `ExtractionStore.exists()` → 404 if not.
3. Check that `container.job_runner_factory is not None` → 503 if not available.
4. With `job_creation_lock`: look up active job via `get_active_job_for_paper`. If one exists, return it with 202. Otherwise, create a new pending job.
5. Attempt `background_tasks.add_task(run_research_map_job, container, job.job_id)`.
6. If `add_task` unexpectedly fails, attempt `job_store.mark_failed(job_id, error_code="task_scheduling_failed")` and return HTTP 500. Do not leave the job pending.

**Error responses:**

| Status | Code | Condition |
|---|---|---|
| 404 | `paper_not_found` | No extraction exists for `paper_id` |
| 503 | `generation_unavailable` | No `job_runner_factory` configured (watsonx missing) |
| 500 | `task_scheduling_failed` | `BackgroundTasks.add_task()` fails |

### 3.3 `GET /api/v1/jobs/{job_id}` — Poll job status

**Response `200 OK`:**
```json
{
  "job_id": "uuid-v4",
  "paper_id": "uuid-v4",
  "status": "pending|running|succeeded|failed",
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:15+00:00",
  "error": null
}
```

For failed jobs, `error` contains the safe machine-readable code (e.g., `"map_generation_failed"`).

**Error responses:**

| Status | Code | Condition |
|---|---|---|
| 404 | `job_not_found` | No job exists for `job_id` |

### 3.4 `GET /api/v1/papers/{paper_id}/research-map` — Retrieve research map

**Response `200 OK`:** Full `ResearchMap` JSON as defined in the data model.

**Behavior:**

Retrieval requires that the **latest** job for the paper is `succeeded`. A `JobStore.get_latest_job_for_paper()` method is added:

```python
def get_latest_job_for_paper(
    self, paper_id: str, *, conn: sqlite3.Connection | None = None
) -> Job | None:
```

Uses deterministic ordering: `ORDER BY created_at DESC, job_id DESC LIMIT 1`.

**Retrieval logic:**

```
latest = job_store.get_latest_job_for_paper(paper_id)
latest is None              → 404
latest.status != succeeded  → 404
map = research_map_store.get(paper_id)
map is None                 → 404
return map                  → 200
```

This prevents exposing an orphaned map after a failed regeneration attempt overwrote the map but could not mark the job as succeeded. An older succeeded job is not sufficient; only the latest job's status matters.

---

## 4. Application Service-Container Design

### Approach: `ServiceContainer` dataclass, injectable into `create_app()`

```python
@dataclass
class ServiceContainer:
    settings: Settings
    extraction_service: ExtractionService
    job_store: JobStore
    extraction_store: ExtractionStore
    research_map_store: ResearchMapStore
    paper_id_factory: Callable[[], str]
    job_runner_factory: Callable[[], ResearchMapJobRunner] | None
    job_creation_lock: threading.Lock
```

### Construction rules

1. `ExtractionService`, `JobStore`, `ExtractionStore`, `ResearchMapStore` are **always** constructed.
2. `WatsonxProvider` is **not** constructed while building the container. When credentials are missing, `job_runner_factory` is `None`; when credentials are present, it is a factory that constructs `WatsonxProvider`, `ResearchMapService`, and `ResearchMapJobRunner` only when a background task executes.
3. Strategy name: **genuine lazy construction**. Container construction, app import, lifespan startup, health, upload, polling, and retrieval make no provider or network call. Provider-construction failures are handled by the background wrapper as `llm_provider_error`.
4. `paper_id_factory` defaults to `lambda: str(uuid.uuid4())`.
5. `job_creation_lock` is always constructed as `threading.Lock()`.

### App factory changes

```python
def create_app(
    settings: Settings | None = None,
    *,
    container: ServiceContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_container = container or build_container(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db(resolved_settings.db_path)
        yield

    application = FastAPI(title="PaperScape API", version="0.1.0", lifespan=lifespan)
    application.state.container = resolved_container
    application.add_middleware(CORSMiddleware, ...)
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(papers_router, prefix="/api/v1")
    application.include_router(jobs_router, prefix="/api/v1")
    return application
```

The container is attached to `application.state` **before** lifespan runs. Tests can pass a `container` argument and the lifespan will not overwrite it.

---

## 5. Dependency-Injection Strategy

### FastAPI dependency functions

Each dependency function reads `request.app.state.container` and returns the required service:

```python
def get_settings(request: Request) -> Settings:
    return request.app.state.container.settings

def get_extraction_service(request: Request) -> ExtractionService:
    return request.app.state.container.extraction_service

def get_job_store(request: Request) -> JobStore:
    return request.app.state.container.job_store

def get_job_runner_factory(request: Request) -> Callable[[], ResearchMapJobRunner] | None:
    return request.app.state.container.job_runner_factory

def get_job_creation_lock(request: Request) -> threading.Lock:
    return request.app.state.container.job_creation_lock
```

### Consistent error shape

A reusable error helper produces a consistent error body:

```python
class AppException(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message

# Registered exception handler:
@app.exception_handler(AppException)
def handle_app_exception(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
```

All route handlers raise `AppException` with safe, curated messages.

---

## 6. ResearchMapJobRunner Interface

### Design

A synchronous class invoked by `BackgroundTasks.add_task()`. The runner owns orchestration: claim job, load extraction, call service, persist map, transition job.

```python
class ResearchMapJobRunner:
    def __init__(
        self,
        *,
        job_store: JobStore,
        extraction_store: ExtractionStore,
        research_map_store: ResearchMapStore,
        research_map_service: ResearchMapService,
    ) -> None:
        ...

    def run(self, job_id: str) -> None:
        """Execute the job synchronously. Never leaves an expected failure unhandled."""
```

### Execution sequence

```
1. Attempt to claim:
   try:
       job = job_store.mark_running(job_id)
   except (RecordNotFoundError, InvalidJobTransitionError):
       # Another runner claimed it, or job vanished.
       # Log safe metadata only. Do NOT call mark_failed.
       return

2. extraction = extraction_store.require(job.paper_id)
3. research_map = research_map_service.generate_map(extraction)
4. research_map_store.save(research_map)
5. job_store.mark_succeeded(job.job_id)
```

Use the `Job` returned by `mark_running()` for the `paper_id` — do not re-read the job from the store unless necessary.

### Failure handling

| Failure point | Caught exception | Error code | Action |
|---|---|---|---|
| `mark_running` fails | `RecordNotFoundError` / `InvalidJobTransitionError` | — | Log safe metadata, `return`. **Never call `mark_failed`.** A second runner must never change another runner's active `running` job to `failed`. |
| Extraction not found | `RecordNotFoundError` | `extraction_missing` | Best-effort `mark_failed` |
| Map generation fails | `MapGenerationError` | `map_generation_failed` | Best-effort `mark_failed` |
| LLM provider fails | `LLMProviderError` | `llm_provider_error` | Best-effort `mark_failed` |
| Research map save fails | `PersistenceError` | `persistence_error` | Best-effort `mark_failed` |
| `mark_succeeded` fails | `PersistenceError` / `InvalidJobTransitionError` | `persistence_error` | Best-effort `mark_failed` |
| Unexpected exception | Any `Exception` | `unexpected_error` | Best-effort `mark_failed` |

A best-effort `mark_failed` may itself fail (e.g., the job is already in a terminal state). That failure is logged but **not** re-raised.

### Safety constraints

- No paper text, evidence excerpts, prompts, model responses, credentials, or stack traces in persisted error codes or log messages.
- Log only `job_id`, `paper_id`, error codes, and exception type names.
- Never re-raise expected failures from `run()`.

---

## 7. Failure-Code Mapping

All codes match the pattern `^[a-z][a-z0-9_]{0,63}$` validated by `JobStore.mark_failed()`.

| Code | Raised when |
|---|---|
| `server_restart` | Startup stale-job recovery (both `pending` and `running` jobs) |
| `task_scheduling_failed` | `BackgroundTasks.add_task()` fails after job creation |
| `extraction_missing` | Extraction not found by job runner |
| `map_generation_failed` | `ResearchMapService` raises `MapGenerationError` |
| `llm_provider_error` | `LLMProvider` raises `LLMProviderError` |
| `persistence_error` | Any `PersistenceError` from repositories |
| `invalid_job_state` | (Reserved; not used in runner since `mark_running` failure just returns) |
| `unexpected_error` | Unclassified exception in runner |

---

## 8. Transaction Boundaries

### Rule

No SQLite transaction remains open during:
- PDF extraction (`ExtractionService.extract()`)
- Prompt construction
- Model inference (`LLMProvider.generate()`)
- Corrective model generation

### Per-operation transactions

Every repository call that uses a repository-owned connection opens and closes its own short transaction:

```
Upload handler:
  extraction_store.save()          ← own transaction

Job creation handler:
  extraction_store.exists()        ← own read
  (inside lock)
    job_store.get_active_job_for_paper()  ← own read
    job_store.create()             ← own transaction
  (end lock)
  BackgroundTasks.add_task()       ← in-process registration

Job runner:
  job_store.mark_running()         ← own transaction
  extraction_store.require()       ← own read
  [model inference — NO transaction]
  research_map_store.save()        ← own transaction
  job_store.mark_succeeded()       ← own transaction
```

### Partial-failure recovery policy

**Scenario:** `research_map_store.save()` succeeds but `job_store.mark_succeeded()` fails.

**Policy for MVP:**
1. The map remains persisted in `research_maps`.
2. The runner attempts `job_store.mark_failed(job.job_id, error_code="persistence_error")`.
3. If `mark_failed` also fails, the job may remain `running`. Startup stale-job recovery (`init_db`) resets `running` → `failed` with `server_restart`.
4. `GET /research-map` requires the **latest** job to be `succeeded`, so the orphaned map is not served.
5. The user retries, creating a new job. The new job regenerates and overwrites the orphaned map via upsert.
6. If the old failed regeneration's latest job was `succeeded` but was overwritten by a failed regeneration, the orphaned map remains hidden because the latest job is `failed`.

---

## 9. Duplicate-Job Behavior

### Decision: Idempotent 202 for existing active job

`POST /api/v1/papers/{paper_id}/research-map-jobs`:

1. If a job in `pending` or `running` already exists → return that job with HTTP 202. No duplicate `BackgroundTask`.
2. If the latest job is `succeeded` or `failed` → create a new pending job.

### In-process lock

A single `threading.Lock` protects the active-job lookup and creation sequence:

```python
with container.job_creation_lock:
    active = job_store.get_active_job_for_paper(paper_id)
    if active is not None:
        return active
    job = job_store.create(paper_id)
```

The lock is never held during `BackgroundTasks.add_task()` or inference. This protects concurrent requests inside one Uvicorn process but does not provide cross-process safety.

---

## 10. Upload-Reading Algorithm

### Correct multipart handling

FastAPI's `UploadFile` is injected directly via the route parameter. The route is `async def` and uses `run_in_threadpool` for blocking work.

```python
async def _read_upload_limited(
    file: UploadFile,
    *,
    max_bytes: int,
) -> bytes:
    """Read at most max_bytes + 1 bytes from the uploaded file.

    Raises
    ------
    ValueError
        If the file is empty or exceeds max_bytes.
    """
    try:
        data = await file.read(max_bytes + 1)
        if not data:
            raise ValueError("Uploaded file is empty.")
        if len(data) > max_bytes:
            raise ValueError(
                f"Uploaded file exceeds {max_bytes} byte limit."
            )
        return data
    finally:
        await file.close()
```

### Validation sequence

1. Receive `file: UploadFile` as a FastAPI form parameter.
2. Validate `file.filename` is non-blank → raise `AppException(400, "invalid_upload", ...)`.
3. Validate `file.content_type` === `"application/pdf"` → raise `AppException(400, "upload_not_a_pdf", ...)`.
4. Optionally check first 1,024 bytes for `%PDF-` → raise `AppException(400, "upload_not_a_pdf", ...)`.
5. Call `_read_upload_limited(file, max_bytes=settings.upload_max_bytes)`.
6. Validate `data` is non-empty (redundant with helper but safe).
7. Generate `paper_id`.
8. Run extraction: `await run_in_threadpool(extraction_service.extract, data, filename, paper_id)`.
9. Persist: `await run_in_threadpool(extraction_store.save, extraction)`.
10. Return 201.

---

## 11. API Error Shape

### Consistent error format

```json
{
  "detail": {
    "code": "paper_not_found",
    "message": "No extracted paper was found for this identifier."
  }
}
```

### Implementation

A reusable `AppException` class and a single exception handler produce this shape for all routes:

```python
class AppException(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
```

### Error codes reference

| HTTP Status | Code | Message |
|---|---|---|
| 400 | `invalid_upload` | The uploaded file is empty or not a valid PDF. |
| 400 | `upload_not_a_pdf` | The file is not a PDF document. |
| 400 | `invalid_identifier` | The provided identifier is malformed. |
| 404 | `paper_not_found` | No extracted paper was found for this identifier. |
| 404 | `job_not_found` | No job was found for this identifier. |
| 404 | `map_not_found` | No completed research map was found for this paper. |
| 413 | `upload_too_large` | The uploaded file exceeds the maximum allowed size. |
| 422 | `extraction_failed` | The uploaded PDF could not be processed. |
| 500 | `persistence_error` | A storage error occurred. Please try again. |
| 500 | `task_scheduling_failed` | The background task could not be started. Please try again. |
| 500 | `internal_error` | An unexpected error occurred. |
| 503 | `generation_unavailable` | Research-map generation is not available. Check that watsonx credentials are configured. |

### Safety rules

- Never expose raw exception messages, SQLite errors, SDK errors, prompt text, paper text, model output, API keys, file bytes, or local paths.
- `detail.code` is always a safe machine-readable string.
- `detail.message` is always a curated human-readable string.

---

## 12. Credential Behavior

### Genuine lazy provider construction

`WatsonxProvider` is constructed only inside the background `job_runner_factory`, after a research-map job has been scheduled. No provider is built during import, app creation, lifespan startup, health checks, upload, job polling, or research-map retrieval. The SDK factory supplies `validate=False` to `ibm_watsonx_ai.foundation_models.ModelInference` where supported, but lazy construction remains the primary no-network safety boundary because `validate=False` alone must not be treated as a guarantee that every SDK version avoids authentication activity during construction.

When credentials are unavailable:
- `job_runner_factory = None`
- `POST /api/v1/papers/{id}/research-map-jobs` returns 503 `generation_unavailable`.
- All other endpoints (health, upload, polling, retrieval) work without credentials.

---

## 13. Background-Task Behavior in Tests

### Starlette TestClient behavior

With `TestClient` and the installed Starlette 1.3.1, `BackgroundTasks` added via `background_tasks.add_task()` are executed synchronously after the response is sent but before the test client context manager exits.

### Test strategy

1. **Endpoint scheduling tests:** Inject a factory that returns a `FakeJobRunner` recording scheduled job IDs. Do not rely on model/provider construction in the request handler.
2. **Job-runner unit tests:** Instantiate `ResearchMapJobRunner` directly with fakes/stubs, call `run()`, assert state transitions and persistence. No FastAPI, no HTTP, no `BackgroundTasks`.
3. **End-to-end API tests:** Set `container.job_runner_factory` to a factory returning a `FakeJobRunner`, or to a factory returning a real `ResearchMapJobRunner` wired to a fake `ResearchMapService`.

### FakeJobRunner for endpoint scheduling tests

```python
class FakeJobRunner:
    def __init__(self):
        self.scheduled: list[str] = []

    def run(self, job_id: str) -> None:
        self.scheduled.append(job_id)
```

---

## 14. Startup Recovery

### Current behavior (Sub-task 6)

`init_db()` resets only `running` jobs to `failed` with `error = 'server_restart'`.

### Required change

Both `pending` and `running` jobs must be reset to `failed` on startup:

```sql
UPDATE jobs
SET status = 'failed', error = 'server_restart', updated_at = ?
WHERE status IN ('pending', 'running')
```

**Rationale:** FastAPI `BackgroundTasks` are in-process and not durable. A server shutdown after committing a `pending` job but before starting the background task leaves a `pending` job that will never execute. Starting a new process cannot assume ownership of the old process's pending work.

**Safety:** This is safe for the planned single-process deployment because startup happens before the application accepts new requests.

Update `backend/tests/unit/test_database.py` to cover both `pending` and `running` reset.

---

## 15. Test Isolation Requirements

All new tests must:

- Use temporary **file-backed** SQLite databases (via `tmp_path`) for any test where multiple repository-owned connections are opened (e.g., job-runner tests, API tests). Do **not** use `:memory:` for these cases because each standard `:memory:` connection has its own independent database.
- Use `test_settings` fixture or `tmp_path`-based `Settings` as appropriate.
- Inject `FakeLLMProvider` or `FakeResearchMapService` for any test path that could trigger model inference.
- Never access `os.environ` or read `.env` files.
- Never make network calls.
- Never use `time.sleep()` — inject a fake sleep that records calls.
- Close all database connections and file handles.

### Fake service implementations needed

| Fake | Used in |
|---|---|
| `FakeExtractionService` | Upload endpoint tests |
| `FakeLLMProvider` | Job runner unit tests, E2E API tests |
| `FakeResearchMapService` | Job runner unit tests (alternative to FakeLLMProvider) |
| `FakeJobRunner` | Job creation endpoint scheduling tests |
| `FakeUUIDFactory` | Deterministic `paper_id` generation |

### Test database strategy

- **Runner tests** (`test_research_map_job_runner.py`): Use `tmp_path / "job_runner.db"` with explicit `init_db()` call. One shared file-backed database per test.
- **API tests** (`test_papers.py`, `test_jobs.py`): Use the existing `test_settings` fixture which already creates a temporary file-backed database.

---

## 16. Unit-Test Matrix — `test_research_map_job_runner.py`

All tests use `tmp_path`-backed file SQLite and fake extraction/map services. No network, no watsonx, no sleeps.

| # | Test | Assertion |
|---|---|---|
| 1 | `test_pending_to_running` | Job transitions `pending` → `running` |
| 2 | `test_uses_returned_job` | Runner uses the `Job` returned by `mark_running()` |
| 3 | `test_extraction_is_loaded` | `extraction_store.require()` called with correct `paper_id` |
| 4 | `test_service_receives_extraction` | `ResearchMapService.generate_map()` receives the persisted `ExtractionResult` |
| 5 | `test_map_is_saved` | `research_map_store.save()` called with generated `ResearchMap` |
| 6 | `test_successful_job_becomes_succeeded` | Job.status == `succeeded` |
| 7 | `test_missing_extraction_marks_failed` | `RecordNotFoundError` → `extraction_missing` |
| 8 | `test_map_generation_error_marks_failed` | `MapGenerationError` → `map_generation_failed` |
| 9 | `test_llm_provider_error_marks_failed` | `LLMProviderError` → `llm_provider_error` |
| 10 | `test_persistence_error_on_save_marks_failed` | `PersistenceError` during `save()` → `persistence_error` |
| 11 | `test_persistence_error_on_mark_succeeded` | Map saved, `mark_succeeded` raises → `persistence_error` |
| 12 | `test_unexpected_exception_marks_failed` | Random `RuntimeError` → `unexpected_error` |
| 13 | `test_raw_exception_messages_not_stored` | `job.error` contains safe code, not exception message |
| 14 | `test_paper_content_not_logged` | Log does not contain chunk text |
| 15 | `test_model_output_not_logged` | Log does not contain model response |
| 16 | `test_invalid_job_state_does_not_mark_failed` | `mark_running` raises `InvalidJobTransitionError` → log and return, never call `mark_failed` |
| 17 | `test_missing_job_does_not_mark_failed` | `mark_running` raises `RecordNotFoundError` → log and return, never call `mark_failed` |
| 18 | `test_second_runner_cannot_fail_active_job` | Runner A succeeds `mark_running`, Runner B receives `InvalidJobTransitionError` and returns, Runner A's job remains `running` |
| 19 | `test_no_transaction_during_model_call` | Verify transaction is closed before `generate_map()` |
| 20 | `test_runner_returns_none` | `run()` returns `None` for all paths |
| 21 | `test_runner_does_not_reraise` | Expected exceptions never propagate out of `run()` |
| 22 | `test_no_additional_retry_loop` | `generate_map()` called at most once |

---

## 17. API-Test Matrix — `test_papers.py`

### Upload tests

| # | Test | Assertion |
|---|---|---|
| 1 | `test_valid_pdf_returns_201` | Status 201, `UploadResponse` fields |
| 2 | `test_paper_id_matches_persisted_extraction` | Returned `paper_id` exists in `ExtractionStore` |
| 3 | `test_filename_preserved` | `UploadResponse.filename` matches |
| 4 | `test_extraction_receives_bytes` | Fake extraction service received exact bytes |
| 5 | `test_extraction_is_persisted` | `ExtractionStore.save()` called |
| 6 | `test_only_file_bytes_reach_extraction` | No multipart envelope bytes in extraction input |
| 7 | `test_empty_file_rejected_400` | Zero-byte upload → 400 |
| 8 | `test_blank_filename_rejected_400` | Whitespace filename → 400 |
| 9 | `test_unsupported_media_type_rejected` | `file.content_type` is `text/plain` → 415 (`unsupported_media_type`) |
| 10 | `test_multipart_content_type_not_confused` | Request is `multipart/form-data` but `UploadFile.content_type` is checked → correct behaviour |
| 11 | `test_oversized_upload_413` | File exceeds `upload_max_bytes` → 413 |
| 12 | `test_max_bytes_exactly_succeeds` | File at `max_bytes` → 201 |
| 13 | `test_max_bytes_plus_one_fails` | File at `max_bytes + 1` → 413 |
| 14 | `test_uploadfile_closed_on_success` | `UploadFile.close()` called |
| 15 | `test_uploadfile_closed_on_failure` | `UploadFile.close()` called after size rejection |
| 16 | `test_watsonx_not_constructed_for_upload` | No `LLMProvider` constructed during upload |
| 17 | `test_extraction_error_maps_to_422` | `ExtractionError` → 422 |
| 18 | `test_persistence_error_maps_to_500` | `PersistenceError` → 500 |
| 19 | `test_file_bytes_absent_from_errors` | Error body does not contain PDF bytes |
| 20 | `test_text_absent_from_errors` | Error body does not contain chunk text |

### Research-map retrieval tests

| # | Test | Assertion |
|---|---|---|
| 21 | `test_latest_succeeded_job_returns_map` | Latest job is `succeeded`, map exists → 200 |
| 22 | `test_no_job_returns_404` | No jobs exist → 404 |
| 23 | `test_no_map_returns_404` | Latest job is `succeeded` but no map → 404 |
| 24 | `test_latest_running_job_hides_map` | Latest job is `running` → 404 (even if older succeeded job exists) |
| 25 | `test_latest_failed_job_hides_map` | Latest job is `failed` → 404 (orphan map after failed regen) |
| 26 | `test_orphan_map_after_failed_regen` | Latest job `failed`, map exists → 404 |
| 27 | `test_retrieval_performs_no_inference` | `LLMProvider.generate()` never called |
| 28 | `test_disclaimer_unchanged` | `disclaimer` == `"This map does not replace expert review."` |
| 29 | `test_evidence_round_trip` | Evidence `chunk_id`, `page`, `excerpt` match |
| 30 | `test_persistence_error_maps_to_500` | `PersistenceError` during retrieval → 500 |

---

## 18. API-Test Matrix — `test_jobs.py`

### Job creation tests

| # | Test | Assertion |
|---|---|---|
| 1 | `test_existing_extraction_creates_pending_job` | POST returns 202 with pending job |
| 2 | `test_unknown_paper_returns_404` | Bad `paper_id` → 404 |
| 3 | `test_runner_unavailable_returns_503` | Container has `job_runner=None` → 503 |
| 4 | `test_runner_unavailable_creates_no_job` | 503 response, no job stored |
| 5 | `test_background_runner_scheduled_once` | `FakeJobRunner.scheduled` contains one entry |
| 6 | `test_duplicate_active_job_returns_existing` | Second POST with active job → 202, same `job_id` |
| 7 | `test_duplicate_active_job_no_second_task` | `FakeJobRunner.scheduled` still has one entry |
| 8 | `test_new_job_after_succeeded` | Latest job `succeeded`, new POST creates fresh `pending` job |
| 9 | `test_new_job_after_failed` | Latest job `failed`, new POST creates fresh `pending` job |
| 10 | `test_concurrent_requests_create_one_job` | Two simultaneous requests create one `pending` job and schedule one task |
| 11 | `test_in_process_lock_held_during_check_and_create` | Lock protects `get_active_job_for_paper` + `create` |
| 12 | `test_in_process_lock_not_held_during_task_registration` | Lock released before `BackgroundTasks.add_task()` |
| 13 | `test_persistence_error_safe` | PersistenceError → 500 with safe code |
| 14 | `test_no_model_inference_in_handler` | `LLMProvider.generate()` never called |
| 15 | `test_no_raw_internal_error_exposed` | Error body has only `detail.code` and `detail.message` |

### Job polling tests

| # | Test | Assertion |
|---|---|---|
| 16 | `test_pending_job_returned` | GET returns status `"pending"` |
| 17 | `test_running_job_returned` | GET returns status `"running"` |
| 18 | `test_succeeded_job_returned` | GET returns status `"succeeded"` |
| 19 | `test_failed_job_returns_safe_error_code` | GET returns error code, not raw exception |
| 20 | `test_missing_job_returns_404` | Unknown `job_id` → 404 |
| 21 | `test_timestamps_serialize_correctly` | ISO-8601 with UTC offset |
| 22 | `test_no_internal_database_values_leak` | Response contains only `JobStatusResponse` fields |

### Startup recovery tests (in `test_database.py`)

| # | Test | Assertion |
|---|---|---|
| 23 | `test_pending_jobs_reset_on_startup` | `pending` jobs → `failed` with `server_restart` |
| 24 | `test_running_jobs_reset_on_startup` | `running` jobs → `failed` with `server_restart` |
| 25 | `test_other_jobs_unchanged_on_startup` | `succeeded` and `failed` jobs remain unchanged |

---

## 19. Router Registration and Tags

### Papers router (`backend/app/routers/papers.py`)

```python
router = APIRouter(prefix="/papers", tags=["papers"])
```

Endpoints:
- `POST /` → upload
- `POST /{paper_id}/research-map-jobs`
- `GET /{paper_id}/research-map`

### Jobs router (`backend/app/routers/jobs.py`)

```python
router = APIRouter(prefix="/jobs", tags=["jobs"])
```

Endpoint:
- `GET /{job_id}`

### Main.py registration

```python
from app.routers.papers import router as papers_router
from app.routers.jobs import router as jobs_router

application.include_router(papers_router, prefix="/api/v1")
application.include_router(jobs_router, prefix="/api/v1")
```

Full URL paths:
- `POST /api/v1/papers`
- `POST /api/v1/papers/{paper_id}/research-map-jobs`
- `GET /api/v1/papers/{paper_id}/research-map`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/health` (existing, unchanged)

---

## 20. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Starlette TestClient background task timing | Low | Use `FakeJobRunner` for scheduling tests; separate runner unit tests |
| Check-then-create race for active jobs | Low (single-process) | In-process `threading.Lock`; document multi-process limitation |
| Orphaned map after partial failure | Low | Latest-job check hides orphaned map; stale recovery resets `running` |
| `create_app()` called without watsonx creds but job endpoint called | Medium | 503 `generation_unavailable` returned before job creation |
| `BackgroundTasks.add_task()` fails after job creation | Very low | Best-effort `mark_failed` with `task_scheduling_failed` |
| PDF signature false positive | Low | Optional check within first 1,024 bytes; not required at byte zero |
| `UploadFile` not closed on error path | Medium | `try/finally` around the complete upload handler |
| Standard `:memory:` SQLite breaks cross-connection tests | Medium | Use `tmp_path` file-backed databases for runner and API tests |

---

## 21. Acceptance Checklist

- [ ] `POST /api/v1/papers` with valid PDF returns 201 with `UploadResponse`.
- [ ] Upload endpoint checks `UploadFile.content_type`, not request-level `Content-Type`.
- [ ] Upload reads at most `max_bytes + 1` from `UploadFile`.
- [ ] Empty upload returns 400; oversized upload returns 413; invalid media type returns 415.
- [ ] `UploadFile` is closed in `finally` on success and every failure path.
- [ ] PDF extraction and persistence run in thread pool, not on the async event loop.
- [ ] `POST /api/v1/papers/{paper_id}/research-map-jobs` returns 202 with job_id.
- [ ] Missing `job_runner_factory` returns 503 `generation_unavailable` and creates no job.
- [ ] Duplicate active-job request returns existing job with 202; no duplicate `BackgroundTask`.
- [ ] In-process `threading.Lock` protects active-job lookup and creation.
- [ ] Job runner claims job via `mark_running()`; failure to claim (wrong state, missing job) logs and returns without `mark_failed`.
- [ ] Second runner cannot change another runner's active job to `failed`.
- [ ] Job runner persists the `ResearchMap` via `ResearchMapStore`.
- [ ] Job runner transitions: `pending` → `running` → `succeeded` (or `failed` on error).
- [ ] `GET /api/v1/jobs/{job_id}` returns current job status.
- [ ] `GET /api/v1/papers/{paper_id}/research-map` returns map (200) only when latest job is `succeeded`.
- [ ] Orphaned map after failed regeneration remains hidden (latest job is not `succeeded`).
- [ ] Old `succeeded` job does not expose new orphaned map after failed regeneration.
- [ ] `pending` and `running` jobs are reset to `failed` on startup (`server_restart`).
- [ ] `BackgroundTasks.add_task()` failure marks job `failed` with `task_scheduling_failed`.
- [ ] No route handler duplicates extraction, grounding, provider, or repository logic.
- [ ] No SQLite transaction remains open during model inference.
- [ ] No real watsonx credentials required for default tests.
- [ ] No network calls in default tests.
- [ ] `GET /api/v1/health` still returns 200.
- [ ] All backend tests pass.
- [ ] `git diff --check` passes.
- [ ] `JobStore.get_latest_job_for_paper()` is added and tested.
- [ ] `python-multipart` is pinned in `backend/requirements.txt`.

---

## 22. Summary of Key Decisions

### Proposed endpoint behavior

| Endpoint | Method | Status | Notes |
|---|---|---|---|
| `/api/v1/papers` | POST | 201 | Synchronous extraction via thread pool; resource created |
| `/api/v1/papers/{id}/research-map-jobs` | POST | 202 or 503 | Async job; 503 when generation unavailable; idempotent for active jobs |
| `/api/v1/jobs/{job_id}` | GET | 200 | Poll current status |
| `/api/v1/papers/{id}/research-map` | GET | 200 or 404 | Requires latest job is succeeded |

### Duplicate-job decision

**Idempotent 202** — return the existing active job rather than 409. In-process `threading.Lock` protects the lookup and creation sequence.

### Provider-construction strategy

**Genuinely lazy** — `WatsonxProvider` is built only by the background `job_runner_factory` after job scheduling. Missing credentials result in `job_runner_factory=None`; job creation returns 503 when generation is unavailable. Provider-construction failures are persisted as `llm_provider_error` by the background wrapper.

### Partial-failure recovery policy

**Map-is-persisted, latest-job check required.** The map is saved first, then the job is marked succeeded. If `mark_succeeded` fails, orphaned map is hidden because retrieval requires the latest job to be succeeded.

### Runner claim safety

If `mark_running()` fails (wrong state or missing job), the runner logs safe metadata and returns. It never calls `mark_failed` for a job it did not successfully claim.

### Estimated test groups

1. `test_research_map_job_runner.py` — ~22 unit tests
2. `test_papers.py` — ~30 API tests (20 upload + 10 retrieval)
3. `test_jobs.py` — ~22 API tests (15 creation + 7 polling)
4. `test_database.py` — ~3 additional startup recovery tests
5. Existing suite — 330 tests (must continue to pass)

Total new tests: ~77.
Estimated total: ~407 tests.