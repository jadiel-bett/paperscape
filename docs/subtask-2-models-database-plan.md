# Sub-task 2 — Backend Pydantic Models, Settings, and SQLite Database Layer

## Top-Level Overview

**Goal:** Establish every shared data type and the persistence foundation that
all later sub-tasks (extraction, LLM, job store, routers) depend on.

**Scope:**
- Three Pydantic v2 model files (`paper.py`, `research_map.py`, `job.py`)
- Hardened `config.py` (pydantic-settings, DI-friendly, never logs secrets)
- `database.py` (SQLite schema init, WAL mode, stale-job reset)
- Unit tests covering validation, schema creation, and stale-job reset

**Non-goals:**
- No `JobStore` service (Sub-task 6)
- No extraction, LLM, or router code
- No schema migrations or versioning
- No changes to the product spec or vertical-slice plan

**Constraints:**
- Python 3.12 + Pydantic v2 syntax throughout
- `sqlite3` stdlib only — no ORM
- All watsonx credentials must be absent from test fixtures
- Tests must run without a `.env` file

**Canonical reference:** `docs/data-model.md` is the single source of truth
for all field names, types, and invariants. This plan implements those
definitions exactly.

**Design decisions (applied from user review):**
1. `watsonx_api_key` uses `SecretStr`; `watsonx_project_id` stays `str` (it is an identifier, not a credential).
2. `JobStatus` is a `StrEnum`, not a `Literal` alias.
3. `JobStatusResponse` inherits from `Job` rather than duplicating fields.
4. The "exactly 3 findings" invariant is enforced with `Field(min_length=3, max_length=3)` on `ResearchMap.findings`; no model validator is used.
5. Model validators are reserved for genuine cross-field invariants only.
6. `config.py` explicitly handles and tests both `sqlite:///./paperscape.db` and `sqlite:///:memory:` URL forms.
7. `db_path` validates the URL before stripping the prefix; it never silently produces a wrong path.
8. `init_db(db_path, conn=None)` closes connections it creates internally and never closes a caller-supplied connection.
9. The lifespan hook in `create_app()` uses the `settings` object that was passed into the factory, so test settings (including in-memory DB paths) are honoured.

---

## Implementation Order

Execute the sub-tasks in this sequence so each builds on stable foundations:

1. `models/paper.py`
2. `models/research_map.py`
3. `models/job.py`
4. `config.py` (harden existing file)
5. `database.py` (new file)
6. `main.py` (wire lifespan)
7. Tests

---

## Sub-Task 2.1 — `backend/app/models/paper.py`

### Intent
Define the three paper-domain Pydantic models that represent extracted PDF
content and the API upload response. These are the primary output types of the
extraction service and must be stable before any service layer is written.

### Expected Outcomes
- `paper.py` exists and imports cleanly with no runtime errors.
- `Chunk`, `ExtractionResult`, and `UploadResponse` are importable from
  `app.models.paper`.
- All field types, names, and constraints match `docs/data-model.md` exactly.
- Invalid field values are rejected by Pydantic validation.

### Todo List

1. Create `backend/app/models/paper.py`.

2. Define `Chunk` as a `BaseModel` with:
   - `chunk_id: str` — no default, required
   - `page: int` — must be ≥ 1 (`Field(ge=1)`)
   - `section: str | None = None`
   - `text: str` — no default, required

3. Define `ExtractionResult` as a `BaseModel` with:
   - `paper_id: str` — no default, required
   - `filename: str` — no default, required
   - `chunks: list[Chunk]` — no default, required

4. Define `UploadResponse` as a `BaseModel` with:
   - `paper_id: str`
   - `filename: str`
   - `page_count: int` — must be ≥ 0 (`Field(ge=0)`)
   - `chunk_count: int` — must be ≥ 0 (`Field(ge=0)`)

5. Add `from __future__ import annotations` at the top of the file.

6. `backend/app/models/__init__.py` — leave as-is (no forced re-exports needed).

### Relevant Context
- Field definitions: `docs/data-model.md` § `backend/app/models/paper.py`
- Chunk ID format (`"{paper_id}-p{page}-{index}"`) is assigned by the
  extraction service, not validated here — no regex constraint needed.
- `page` is 1-based per spec; the `ge=1` constraint enforces this.
- `section` is `None` for the PyMuPDF fallback path; the field must be
  optional with a `None` default.

### Status
`[ ] pending`

---

## Sub-Task 2.2 — `backend/app/models/research_map.py`

### Intent
Define the three research-map-domain Pydantic models that represent the
structured AI output. The "exactly 3 findings" invariant is a single-field
length constraint on `ResearchMap.findings` and is expressed as
`Field(min_length=3, max_length=3)` — this is a field-level rule, not a
cross-field invariant, so no model validator is warranted.

### Expected Outcomes
- `research_map.py` exists and imports cleanly.
- `Evidence`, `Finding`, and `ResearchMap` are importable from
  `app.models.research_map`.
- `Evidence.excerpt` is rejected when it exceeds 300 characters.
- `ResearchMap` is rejected when `findings` does not contain exactly 3 items.
- `Finding.confidence` is rejected for any value outside the allowed literal set.
- `ResearchMap.disclaimer` defaults to the hardcoded constant.

### Todo List

1. Create `backend/app/models/research_map.py`.

2. Define `Evidence` as a `BaseModel` with:
   - `chunk_id: str`
   - `page: int` — `Field(ge=1)`
   - `excerpt: str` — `Field(max_length=300)`

3. Define `Finding` as a `BaseModel` with:
   - `statement: str`
   - `evidence: list[Evidence]` — `Field(min_length=1)`
   - `confidence: Literal["high", "partial", "uncertain"]`

4. Define `ResearchMap` as a `BaseModel` with:
   - `paper_id: str`
   - `research_question: str`
   - `findings: list[Finding]` — `Field(min_length=3, max_length=3)`
   - `limitations: list[str]`
   - `disclaimer: str = "This AI-generated explanation is grounded in the uploaded document but does not replace expert review."`

5. Do **not** add a model validator for finding count — the `Field` constraint
   above is sufficient and is the correct Pydantic v2 idiom for single-field
   length rules.

6. Import `Literal` from `typing`.

7. Add `from __future__ import annotations` at the top.

### Relevant Context
- Field definitions: `docs/data-model.md` § `backend/app/models/research_map.py`
- The exact disclaimer string is a product invariant:
  `"This AI-generated explanation is grounded in the uploaded document but does not replace expert review."`
- `evidence` minimum length of 1 is stated in `docs/data-model.md` § Invariants.
- `Literal` from `typing` is preferred over `enum.Enum` for the confidence
  field because it serializes cleanly to JSON strings without custom encoders,
  and confidence values are not shared across models.

### Status
`[ ] pending`

---

## Sub-Task 2.3 — `backend/app/models/job.py`

### Intent
Define the job-domain types. `JobStatus` is a `StrEnum` so that:
- Values compare equal to plain strings (`status == "pending"` works)
- SQLite stores and reads the value as plain text without conversion
- Pydantic v2 validates incoming strings against the enum members

`JobStatusResponse` inherits from `Job` so field definitions are not
duplicated; they can be separated later if their contracts actually diverge.

### Expected Outcomes
- `job.py` exists and imports cleanly.
- `JobStatus`, `Job`, `JobCreateResponse`, and `JobStatusResponse` are
  importable from `app.models.job`.
- `Job` fields match the SQLite `jobs` table columns exactly (enabling direct
  row-to-model mapping without transformation).
- `Job.error` is `None` by default.
- `Job.created_at` and `Job.updated_at` accept Python `datetime` objects.
- `JobStatus.PENDING == "pending"` evaluates to `True`.

### Todo List

1. Create `backend/app/models/job.py`.

2. Define `JobStatus` as a `StrEnum`:
   ```python
   class JobStatus(str, enum.Enum):
       PENDING   = "pending"
       RUNNING   = "running"
       SUCCEEDED = "succeeded"
       FAILED    = "failed"
   ```
   Import `enum` from the standard library.

3. Define `Job` as a `BaseModel` with:
   - `job_id: str`
   - `paper_id: str`
   - `status: JobStatus`
   - `created_at: datetime`
   - `updated_at: datetime`
   - `error: str | None = None`

4. Define `JobCreateResponse` as a `BaseModel` with:
   - `job_id: str`
   - `paper_id: str`
   - `status: JobStatus`

5. Define `JobStatusResponse` as a subclass of `Job`:
   ```python
   class JobStatusResponse(Job):
       pass
   ```
   This keeps all `Job` fields without duplication. Add a brief docstring
   noting that this is intentionally a pass-through today.

6. Import `datetime` from `datetime`.

7. Add `from __future__ import annotations` at the top.

### Relevant Context
- Field definitions: `docs/data-model.md` § `backend/app/models/job.py`
- Valid state transitions (`pending → running → succeeded | failed`) are
  enforced by the job store service (Sub-task 6), not by the model itself.
- `datetime` fields will be stored as ISO-8601 text in SQLite and
  reconstructed via `datetime.fromisoformat()` in the job store. The model
  accepts Python `datetime` objects; FastAPI serializes them to ISO strings.
- `StrEnum` means that when SQLite returns the string `"pending"`, Pydantic
  can coerce it directly into `JobStatus.PENDING` without a custom validator.
  This is the primary reason to prefer `StrEnum` over a plain `Literal` here.

### Status
`[ ] pending`

---

## Sub-Task 2.4 — `backend/app/config.py` (Harden existing file)

### Intent
Harden the existing `config.py` to:
- Protect `watsonx_api_key` from appearing in logs via `SecretStr`.
  `watsonx_project_id` stays `str` — it is a non-secret identifier.
- Validate `database_url` to accept only known-safe SQLite URL forms.
- Provide a `db_path` property that parses the URL correctly and validates
  the result rather than blindly stripping a prefix.
- Remain fully injectable via the `create_app()` factory (already satisfied).

No new environment variables are added — all are already documented in
`backend/.env.example`.

### Expected Outcomes
- `get_settings()` returns a `Settings` instance without reading `.env` when
  env vars are supplied directly (e.g., in tests via `Settings(...)`).
- `Settings.db_path` returns `":memory:"` for `"sqlite:///:memory:"`.
- `Settings.db_path` returns `"./paperscape.db"` for `"sqlite:///./paperscape.db"`.
- `Settings` raises `ValidationError` for any `database_url` that does not
  match a supported SQLite URL pattern.
- `repr(settings)` does not expose the `watsonx_api_key` value.
- Callers that need the raw API key call `settings.watsonx_api_key.get_secret_value()`.

### Todo List

1. Open `backend/app/config.py`.

2. Change `watsonx_api_key: str = ""` to `watsonx_api_key: SecretStr = SecretStr("")`.
   Import `SecretStr` from `pydantic`.
   Leave `watsonx_project_id: str = ""` unchanged.

3. Replace the free-form `database_url` field with a validated one.
   Add a `@field_validator("database_url", mode="after")` (or `mode="before"`)
   that enforces exactly two supported forms:
   - `"sqlite:///:memory:"` → valid
   - `"sqlite:///..."` where `...` is a non-empty relative or absolute path → valid
   - Anything else → raise `ValueError` with a clear message.

4. Add a `db_path` property that converts `database_url` to a plain path
   string by applying the following logic explicitly (not a blind strip):
   - If `database_url == "sqlite:///:memory:"` → return `":memory:"`
   - If `database_url.startswith("sqlite:///")` → strip `"sqlite:///"` prefix,
     assert the remainder is non-empty, return the remainder.
   - Otherwise → raise `ValueError` (this branch is unreachable after
     validation but guards against direct property access in tests).

5. Update `get_settings()` docstring to note it is designed for
   `Depends(get_settings)` in FastAPI routes; direct calls should be
   confined to `create_app()` and tests that supply explicit overrides.

6. Preserve all existing fields and the `cors_origins_list` property exactly.

### Relevant Context
- Current implementation: `backend/app/config.py`
- `.env.example` variables: `backend/.env.example`
- `create_app()` in `backend/app/main.py` accepts `Settings | None` — this
  contract must not change.
- No existing callers read `watsonx_api_key` as a string yet; the `SecretStr`
  change has zero downstream impact at this stage.
- The `db_path` property is consumed by the lifespan hook in `main.py`
  (Sub-task 2.6) and by test fixtures that construct `Settings` directly.

### Status
`[ ] pending`

---

## Sub-Task 2.5 — `backend/app/database.py`

### Intent
Create the SQLite connection factory and schema initialization module.
This module is the only place in the codebase that issues `CREATE TABLE`
statements and knows the physical column layout of the three persistence tables.
It also performs the stale-job reset on startup.

**Connection ownership rule (critical):** `init_db` creates a connection when
none is supplied and closes it before returning. When the caller supplies a
connection (always the case in tests using `:memory:`), `init_db` uses it and
never closes it. This keeps the ownership contract unambiguous.

No `JobStore` CRUD logic lives here — that belongs in Sub-task 6.

### Expected Outcomes
- `backend/app/database.py` exists and imports cleanly.
- `init_db(":memory:", conn)` on a shared connection creates all three tables.
- Calling `init_db` twice on the same connection is idempotent.
- After `init_db`, any rows with `status = 'running'` are set to `'failed'`.
- `get_connection(db_path)` returns a connection with `row_factory = sqlite3.Row`.
- File-based connections have `journal_mode = WAL`.
- `:memory:` connections do not have WAL set (and the journal mode is `"memory"`).

### Todo List

1. Create `backend/app/database.py` with `from __future__ import annotations`.

2. Implement `get_connection(db_path: str) -> sqlite3.Connection`:
   - `conn = sqlite3.connect(db_path)`
   - `conn.row_factory = sqlite3.Row`
   - `if db_path != ":memory:": conn.execute("PRAGMA journal_mode=WAL")`
   - Return `conn`.
   - Do not store the connection as a module-level singleton.

3. Implement `init_db(db_path: str, conn: sqlite3.Connection | None = None) -> None`:

   a. Connection ownership:
      ```python
      _owns_conn = conn is None
      if _owns_conn:
          conn = get_connection(db_path)
      ```

   b. Create the **`jobs`** table:
      ```sql
      CREATE TABLE IF NOT EXISTS jobs (
          job_id     TEXT NOT NULL PRIMARY KEY,
          paper_id   TEXT NOT NULL,
          status     TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          error      TEXT
      )
      ```
      Create index:
      ```sql
      CREATE INDEX IF NOT EXISTS idx_jobs_paper_id ON jobs (paper_id)
      ```

   c. Create the **`extractions`** table:
      ```sql
      CREATE TABLE IF NOT EXISTS extractions (
          paper_id    TEXT NOT NULL PRIMARY KEY,
          filename    TEXT NOT NULL,
          chunks_json TEXT NOT NULL
      )
      ```

   d. Create the **`research_maps`** table:
      ```sql
      CREATE TABLE IF NOT EXISTS research_maps (
          paper_id TEXT NOT NULL PRIMARY KEY,
          map_json TEXT NOT NULL
      )
      ```

   e. Reset stale running jobs:
      ```sql
      UPDATE jobs
         SET status     = 'failed',
             error      = 'Reset by server restart',
             updated_at = ?
       WHERE status = 'running'
      ```
      Pass `datetime.utcnow().isoformat()` as the parameter value.

   f. Commit:
      ```python
      conn.commit()
      ```

   g. Close only if owned:
      ```python
      if _owns_conn:
          conn.close()
      ```

4. Add `from __future__ import annotations` and import `sqlite3` and
   `datetime` at the top.

### Relevant Context
- `jobs` table columns must match `Job` model fields exactly to allow direct
  row → model hydration in the job store (Sub-task 6).
- `extractions.chunks_json` stores `ExtractionResult.chunks` serialized as
  JSON. `paper_id` and `filename` are separate columns for indexed lookup.
- `research_maps.map_json` stores the full `ResearchMap` as JSON.
- WAL is skipped for `:memory:` — it is not meaningful there and would
  produce a noisy warning in test output.
- The stale-job reset runs synchronously inside `init_db`, before the first
  request is served.

### Status
`[ ] pending`

---

## Sub-Task 2.6 — `backend/app/main.py` (Wire lifespan)

### Intent
Add a FastAPI lifespan context manager to `create_app()` that calls
`init_db(settings.db_path)` on startup. The `settings` object used must be
the one passed into the factory — this ensures that a test calling
`create_app(test_settings)` with an in-memory DB path initializes that
database, not the production one.

### Expected Outcomes
- The app starts up cleanly and `init_db` is called before the first request.
- The health endpoint continues to return `{"status": "ok"}`.
- A test that creates the app with `Settings(database_url="sqlite:///:memory:")`
  gets a fully initialized in-memory schema, not an error.

### Todo List

1. Open `backend/app/main.py`.

2. Add imports at the top:
   ```python
   from contextlib import asynccontextmanager
   from app.database import init_db
   ```

3. Inside `create_app()`, define the lifespan using the `settings` local variable
   (which is already resolved before this point):
   ```python
   @asynccontextmanager
   async def lifespan(_app: FastAPI):
       init_db(settings.db_path)
       yield
   ```
   The `settings` reference inside `lifespan` closes over the resolved
   `settings` local, so injected test settings are always used.

4. Pass `lifespan=lifespan` to the `FastAPI(...)` constructor.

5. Keep the CORS middleware and health router registration unchanged.

6. The module-level `app = create_app()` at the bottom is unchanged.

### Relevant Context
- Current `main.py`: `backend/app/main.py`
- FastAPI 0.139.0 fully supports the `lifespan` parameter.
- The `@app.on_event("startup")` decorator is deprecated in this version;
  the lifespan context manager is the correct approach.
- The lifespan is defined inside `create_app()` so it captures `settings`
  by closure — this is the key mechanism that makes test injection work.

### Status
`[ ] pending`

---

## Sub-Task 2.7 — Tests

### Intent
Provide fast, hermetic tests for all new code. Tests must not read `.env`,
must not contact watsonx, and must not require a filesystem database path.
All database tests use a shared `:memory:` connection.

### Expected Outcomes
- `backend/tests/unit/test_models.py` covers all Pydantic validation rules.
- `backend/tests/unit/test_database.py` covers schema creation and stale-job reset.
- All new tests pass alongside the existing `test_health.py`.
- No test reads from `.env` or any external service.

### Todo List

#### `backend/tests/unit/test_models.py`

1. Create the file with `from __future__ import annotations`.

2. **`Chunk` tests:**
   - Valid construction succeeds.
   - `page=0` raises `ValidationError`.
   - `section=None` is accepted.
   - Missing `chunk_id` raises `ValidationError`.

3. **`ExtractionResult` tests:**
   - Valid construction with a list of `Chunk` objects succeeds.
   - Empty `chunks` list is accepted (count enforcement is the service layer's
     responsibility).

4. **`UploadResponse` tests:**
   - `page_count=0` and `chunk_count=0` are accepted.
   - `page_count=-1` raises `ValidationError`.

5. **`Evidence` tests:**
   - `excerpt` of exactly 300 characters is accepted.
   - `excerpt` of 301 characters raises `ValidationError`.
   - `page=0` raises `ValidationError`.

6. **`Finding` tests:**
   - Valid `confidence` values (`"high"`, `"partial"`, `"uncertain"`) are
     accepted.
   - An invalid `confidence` value raises `ValidationError`.
   - Empty `evidence` list raises `ValidationError`.

7. **`ResearchMap` tests:**
   - Exactly 3 findings is accepted.
   - 2 findings raises `ValidationError`.
   - 4 findings raises `ValidationError`.
   - Default `disclaimer` equals `"This AI-generated explanation is grounded in the uploaded document but does not replace expert review."`.
   - Custom `disclaimer` value is accepted.

8. **`JobStatus` tests:**
   - `JobStatus.PENDING == "pending"` evaluates to `True` (StrEnum behaviour).
   - `Job` constructed with `status=JobStatus.PENDING` succeeds.
   - `Job` constructed with `status="pending"` (plain string) is coerced to
     `JobStatus.PENDING` by Pydantic.
   - `Job` with `status="invalid"` raises `ValidationError`.

9. **`Job` tests:**
   - `error=None` is the default.
   - `created_at` and `updated_at` accept `datetime` objects.

10. **`JobCreateResponse` and `JobStatusResponse` tests:**
    - Both construct without errors from valid data.
    - `JobStatusResponse` has all fields from `Job` (inheritance confirmed
      by checking `JobStatusResponse.model_fields` keys).

#### `backend/tests/unit/test_database.py`

All database tests work through a single pytest fixture that creates a shared
in-memory connection:

```python
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()
```

1. Create the file with `from __future__ import annotations` and import
   `sqlite3`, `pytest`, `init_db`, and `get_connection` from `app.database`.

2. **`test_init_db_creates_tables(conn)`:**
   - Call `init_db(":memory:", conn)`.
   - Query `sqlite_master WHERE type='table'`.
   - Assert tables `jobs`, `extractions`, `research_maps` all exist.

3. **`test_init_db_creates_paper_id_index(conn)`:**
   - Call `init_db(":memory:", conn)`.
   - Query `sqlite_master WHERE type='index' AND name='idx_jobs_paper_id'`.
   - Assert the index exists.

4. **`test_init_db_is_idempotent(conn)`:**
   - Call `init_db(":memory:", conn)` twice.
   - Assert no exception is raised and all three tables still exist.

5. **`test_init_db_resets_stale_running_jobs(conn)`:**
   - Call `init_db(":memory:", conn)` to create the schema.
   - Insert a `running` job row and a `pending` job row into `jobs`.
   - Call `init_db(":memory:", conn)` a second time (simulates restart).
   - Assert the `running` row now has `status = 'failed'` and `error` is
     not null.
   - Assert the `pending` row is unchanged.

6. **`test_init_db_does_not_close_caller_connection(conn)`:**
   - Call `init_db(":memory:", conn)`.
   - After the call, execute `SELECT 1` on `conn` — it must not raise.
   - This confirms that `init_db` honoured the ownership contract.

7. **`test_get_connection_sets_row_factory`:**
   - Call `get_connection(":memory:")`.
   - Execute `SELECT 1 AS val`.
   - Assert `row["val"] == 1`.
   - Close the connection.

8. **`test_wal_mode_not_set_for_memory`:**
   - Call `get_connection(":memory:")`.
   - Execute `PRAGMA journal_mode`.
   - Assert the result is `"memory"` (not `"wal"`).
   - Close the connection.

#### `backend/tests/unit/test_config.py`

1. Create the file with `from __future__ import annotations`.

2. **`test_db_path_memory`:**
   - Construct `Settings(database_url="sqlite:///:memory:", ...)`.
   - Assert `settings.db_path == ":memory:"`.

3. **`test_db_path_relative_file`:**
   - Construct `Settings(database_url="sqlite:///./paperscape.db", ...)`.
   - Assert `settings.db_path == "./paperscape.db"`.

4. **`test_db_path_rejects_non_sqlite_url`:**
   - Constructing `Settings(database_url="postgresql://localhost/db", ...)`
     raises `ValidationError`.

5. **`test_db_path_rejects_empty_path`:**
   - Constructing `Settings(database_url="sqlite:///", ...)` raises
     `ValidationError` or returns a path that is clearly invalid (the
     validator should reject an empty remainder).

6. **`test_secret_key_not_in_repr`:**
   - Construct `Settings(watsonx_api_key="super-secret", ...)`.
   - Assert `"super-secret"` does not appear in `repr(settings)`.

7. **`test_project_id_is_plain_str`:**
   - Construct `Settings(watsonx_project_id="proj-123", ...)`.
   - Assert `settings.watsonx_project_id == "proj-123"` (plain string, no
     `.get_secret_value()` needed).

All `Settings` constructions in these tests must pass all required fields as
keyword arguments (no `.env` file dependency). Minimal required kwargs:
`watsonx_api_key`, `watsonx_url`, `watsonx_project_id`, `database_url`.

### Relevant Context
- Existing test pattern: `backend/tests/api/test_health.py` — uses
  `TestClient`; unit tests here are plain `pytest` functions with no HTTP
  client.
- `pytest.raises(ValidationError)` is the standard pattern; import
  `ValidationError` from `pydantic`.
- The `test_init_db_resets_stale_running_jobs` test is the most important
  database test — it guards the product-spec requirement that crashed jobs
  never stay in `running` state after a restart.

### Status
`[ ] pending`

---

## Acceptance Criteria

All of the following must be true before Sub-task 2 is considered complete:

1. **Models importable:** `from app.models.paper import Chunk, ExtractionResult, UploadResponse` succeeds.
2. **Models importable:** `from app.models.research_map import Evidence, Finding, ResearchMap` succeeds.
3. **Models importable:** `from app.models.job import JobStatus, Job, JobCreateResponse, JobStatusResponse` succeeds.
4. **Validation enforced:** `ResearchMap` with 2 or 4 findings raises `ValidationError`.
5. **Validation enforced:** `Evidence` with `excerpt` > 300 chars raises `ValidationError`.
6. **Validation enforced:** `Chunk` with `page=0` raises `ValidationError`.
7. **Validation enforced:** `Finding` with empty `evidence` list raises `ValidationError`.
8. **StrEnum works:** `JobStatus.PENDING == "pending"` is `True`; `Job(status="pending", ...)` coerces without error.
9. **Config hardened:** `Settings` with a non-`sqlite:` `database_url` raises `ValidationError`.
10. **Config hardened:** `repr(settings)` does not expose the `watsonx_api_key` value.
11. **Config hardened:** `settings.db_path == ":memory:"` for `"sqlite:///:memory:"`.
12. **Config hardened:** `settings.db_path == "./paperscape.db"` for `"sqlite:///./paperscape.db"`.
13. **Config hardened:** `watsonx_project_id` is a plain `str`, not `SecretStr`.
14. **Schema created:** `init_db` creates all three tables and the `idx_jobs_paper_id` index on a fresh connection.
15. **Schema idempotent:** Calling `init_db` twice does not raise an error.
16. **Stale reset:** After `init_db` on a DB that has `running` jobs, those jobs are `failed`.
17. **Connection ownership:** After `init_db(":memory:", conn)`, `conn` is still open and usable.
18. **WAL mode:** `get_connection("./some.db")` sets `journal_mode = WAL`.
19. **No WAL for memory:** `get_connection(":memory:")` results in `journal_mode = memory`.
20. **Lifespan wired:** `create_app(settings)` uses `settings.db_path` for `init_db`, not the module-level cached settings.
21. **Health endpoint unchanged:** `GET /api/v1/health` returns `{"status": "ok"}`.
22. **Tests pass:** `pytest backend/tests/` exits 0 with no failures or errors.
23. **No secrets in tests:** No test file references `WATSONX_API_KEY` or reads `.env`.
