# Sub-task 6: SQLite JobStore and Extraction/Research-Map Persistence Plan

## 1. Objective

Implement a synchronous SQLite persistence layer for:

- Job lifecycle records (`JobStore`)
- Extraction persistence (`ExtractionStore`)
- Research-map persistence (`ResearchMapStore`)

The completed persistence layer must support the later asynchronous job orchestration and API phases without importing FastAPI, BackgroundTasks, watsonx SDK classes, or HTTP concepts.

---

## 2. Current Schema Assessment

### 2.1 Existing CREATE TABLE Statements

From `backend/app/database.py`:

**`jobs`:**
```sql
CREATE TABLE IF NOT EXISTS jobs (
    job_id     TEXT NOT NULL PRIMARY KEY,
    paper_id   TEXT NOT NULL,
    status     TEXT NOT NULL
               CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error      TEXT
)
CREATE INDEX IF NOT EXISTS idx_jobs_paper_id ON jobs (paper_id)
```

**`extractions`:**
```sql
CREATE TABLE IF NOT EXISTS extractions (
    paper_id    TEXT NOT NULL PRIMARY KEY,
    filename    TEXT NOT NULL,
    chunks_json TEXT NOT NULL
)
```

**`research_maps`:**
```sql
CREATE TABLE IF NOT EXISTS research_maps (
    paper_id TEXT NOT NULL PRIMARY KEY,
    map_json TEXT NOT NULL
)
```

### 2.2 Column Inventory

| Table | Columns | PK | FK | Timestamps | Indexes |
|---|---|---|---|---|---|
| `jobs` | `job_id`, `paper_id`, `status`, `created_at`, `updated_at`, `error` | `job_id` | None | `created_at`, `updated_at` (TEXT ISO-8601) | `idx_jobs_paper_id` |
| `extractions` | `paper_id`, `filename`, `chunks_json` | `paper_id` | None | None | None (PK only) |
| `research_maps` | `paper_id`, `map_json` | `paper_id` | None | None | None (PK only) |

### 2.3 Findings

- **No foreign keys** link `extractions` or `research_maps` to `jobs`. The schema uses `paper_id` as a loose logical link. No `papers` parent table exists.
- **Timestamps are stored as TEXT** using ISO-8601 strings — consistent with existing `init_db` usage.
- **`error` column is nullable** — non-NULL only for failed jobs.
- **Status CHECK constraint** enforced at the database layer.
- **Connection pattern** (`get_connection`): opens connection, sets `row_factory = sqlite3.Row`, enables `PRAGMA foreign_keys = ON`, enables WAL for file-backed databases. Caller-supplied connections never closed by callee.
- **Transaction pattern** (`init_db`): explicit `BEGIN`/`COMMIT`/`ROLLBACK`; caller-supplied connections remain open.

### 2.4 Schema Suitability

**The existing schema supports all required repository operations.** No schema changes are needed. The only deliberate gap is the absence of a `papers` table and corresponding foreign keys — this is acceptable for the MVP since `paper_id` is the natural primary key for both extractions and research maps.

### 2.5 Required Schema Modifications

None.

---

## 3. Files Created and Modified

### 3.1 New Files

| File | Purpose |
|---|---|
| `backend/app/repositories/__init__.py` | Package init; re-exports stores and errors |
| `backend/app/repositories/errors.py` | Shared persistence exception hierarchy |
| `backend/app/repositories/job_store.py` | `JobStore` — strict atomic job lifecycle |
| `backend/app/repositories/extraction_store.py` | `ExtractionStore` — extraction persistence |
| `backend/app/repositories/research_map_store.py` | `ResearchMapStore` — research-map persistence |
| `backend/tests/unit/test_job_store.py` | Unit tests for `JobStore` |
| `backend/tests/unit/test_extraction_store.py` | Unit tests for `ExtractionStore` |
| `backend/tests/unit/test_research_map_store.py` | Unit tests for `ResearchMapStore` |

### 3.2 Modified Files

| File | Change |
|---|---|
| `backend/app/models/job.py` | Add timezone-aware UTC validator for `created_at` and `updated_at` if not already enforced |
| `docs/data-model.md` | Document repository persistence contracts, serialization format, and the `error_code` pattern for failed jobs |

### 3.3 Files NOT Modified

- `backend/app/database.py` — schema, `get_connection`, and `init_db` are sufficient.
- `backend/app/models/paper.py`
- `backend/app/models/research_map.py`

---

## 4. Exception Hierarchy (`backend/app/repositories/errors.py`)

```python
class PersistenceError(RuntimeError):
    """Base persistence failure. Original exception chained as __cause__."""

class RecordNotFoundError(PersistenceError):
    """The requested persistence record does not exist."""

class InvalidJobTransitionError(PersistenceError):
    """The requested job status transition is not allowed."""

class CorruptRecordError(PersistenceError):
    """Stored JSON cannot be reconstructed as the expected model."""
```

**Safety rules:**
- Exception messages contain only IDs, status labels, type names, and error codes.
- No chunk text, evidence excerpts, complete JSON payloads, prompts, model responses, credentials, or connection strings.
- Original exception (`sqlite3.Error`, `json.JSONDecodeError`, `pydantic.ValidationError`) preserved as `__cause__`.
- Do **not** wrap existing domain exceptions (`RecordNotFoundError`, `InvalidJobTransitionError`, `CorruptRecordError`, `ValueError`). Only wrap `sqlite3.Error` and similar storage-layer failures.

---

## 5. Proposed Repository Interfaces

### 5.1 `JobStore`

```python
class JobStore:
    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], str] = _new_uuid,
    ) -> None: ...

    def create(self, paper_id: str) -> Job:
        """Create a job in 'pending' status. The clock is called once;
        created_at == updated_at."""

    def get(self, job_id: str) -> Job | None:
        """Return the job, or None if not found."""

    def require(self, job_id: str) -> Job:
        """Return the job, or raise RecordNotFoundError."""

    def mark_running(self, job_id: str) -> Job:
        """Atomically transition pending → running.
        Fails with InvalidJobTransitionError if the job is not pending."""

    def mark_succeeded(self, job_id: str) -> Job:
        """Atomically transition running → succeeded.
        Fails with InvalidJobTransitionError if the job is not running."""

    def mark_failed(
        self,
        job_id: str,
        *,
        error_code: str,
    ) -> Job:
        """Atomically transition pending or running → failed.
        Stores only a validated machine-readable error_code in jobs.error.
        Accepts pending (preflight failure) or running (execution failure).
        Fails with InvalidJobTransitionError if already terminal."""

    def get_active_job_for_paper(self, paper_id: str) -> Job | None:
        """Return the latest pending or running job, or None.
        Deterministic tie-break: ORDER BY created_at DESC, job_id DESC."""

    def has_completed_job_for_paper(self, paper_id: str) -> bool:
        """Return True if a succeeded job exists for this paper."""
```

**Design notes:**

- `paper_id`, `job_id`, `error_code` are validated as non-blank strings (and for `error_code`, against `^[a-z][a-z0-9_]{0,63}$`) before any SQL executes.
- `create()` calls `self._clock()` exactly once: `now = self._clock()` → `created_at = now; updated_at = now`.
- `uuid_factory` return value is validated: must be a non-blank `str`.
- `mark_failed` stores only `error_code` in the `error` column — no raw exception messages, model output, or content.
- `mark_failed` accepts source state `pending` (preflight/scheduling failure) or `running` (execution failure) via `WHERE status IN ('pending','running')`.
- `mark_succeeded` and `mark_running` use strict single-source-state `WHERE status = ?`.
- No `error_message` parameter — human-readable messages are mapped from codes at the API layer.
- No `conn=` parameter shown above for brevity; it is present on every public method — see Section 6.

### 5.2 `ExtractionStore`

```python
class ExtractionStore:
    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
    ) -> None: ...

    def save(self, extraction: ExtractionResult) -> None:
        """Atomic upsert. Stores paper_id, filename, and list[Chunk] JSON.
        The ExtractionResult is NOT duplicated inside chunks_json."""

    def get(self, paper_id: str) -> ExtractionResult | None: ...

    def require(self, paper_id: str) -> ExtractionResult: ...

    def exists(self, paper_id: str) -> bool: ...
```

**Serialization alignment with schema:**

The `extractions` table has columns `paper_id`, `filename`, `chunks_json`. The repository must **not** store the complete `ExtractionResult` as `chunks_json` (which would duplicate `paper_id` and `filename`). Instead:

**Write:**
```python
from pydantic import TypeAdapter

_CHUNKS_ADAPTER = TypeAdapter(list[Chunk])

# In save():
chunks_json = _CHUNKS_ADAPTER.dump_json(extraction.chunks).decode("utf-8")
conn.execute(
    "INSERT INTO extractions (paper_id, filename, chunks_json) VALUES (?, ?, ?) "
    "ON CONFLICT(paper_id) DO UPDATE SET filename=excluded.filename, chunks_json=excluded.chunks_json",
    (extraction.paper_id, extraction.filename, chunks_json),
)
```

**Read:**
```python
chunks = _CHUNKS_ADAPTER.validate_json(row["chunks_json"])
return ExtractionResult(
    paper_id=row["paper_id"],
    filename=row["filename"],
    chunks=chunks,
)
```

### 5.3 `ResearchMapStore`

```python
class ResearchMapStore:
    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
    ) -> None: ...

    def save(self, research_map: ResearchMap) -> None:
        """Atomic upsert. Stores the complete ResearchMap as map_json."""

    def get(self, paper_id: str) -> ResearchMap | None: ...

    def require(self, paper_id: str) -> ResearchMap: ...

    def exists(self, paper_id: str) -> bool: ...
```

**Paper ID integrity check on read:**

The complete `ResearchMap` is stored as JSON in `map_json`. On read, the repository must verify that the decoded model's `paper_id` equals the row's `paper_id`:

```python
research_map = ResearchMap.model_validate_json(row["map_json"])
if research_map.paper_id != row["paper_id"]:
    raise CorruptRecordError(
        f"Research map paper_id {research_map.paper_id!r} does not match "
        f"row paper_id {row['paper_id']!r}."
    )
return research_map
```

A mismatch indicates a storage corruption or bug and must raise `CorruptRecordError`.

---

## 6. Connection and Transaction Ownership

### 6.1 Pattern

Every public method on all three repositories accepts an optional keyword-only `conn` parameter:

```python
def create(
    self,
    paper_id: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> Job:
```

**Repository-owned connection (conn is None):**
1. Open connection via `self._connection_factory(self._db_path)`
2. Execute `BEGIN`
3. Perform operation
4. On success: `COMMIT`
5. On any exception: `ROLLBACK`
6. Always in `finally`: close the connection

**Caller-supplied connection (conn is not None):**
- Do **not** open a connection
- Do **not** execute `BEGIN`, `COMMIT`, or `ROLLBACK`
- Do **not** close the connection
- The caller owns all transaction and lifecycle responsibilities

### 6.2 Concrete Implementation Template

```python
def save(self, extraction: ExtractionResult, *, conn: sqlite3.Connection | None = None) -> None:
    _owns = conn is None
    if _owns:
        conn = self._connection_factory(self._db_path)
        conn.execute("BEGIN")

    try:
        _paper_id = _validate_nonblank(extraction.paper_id, "paper_id")
        chunks_json = _CHUNKS_ADAPTER.dump_json(extraction.chunks).decode("utf-8")
        conn.execute(
            """INSERT INTO extractions (paper_id, filename, chunks_json)
               VALUES (?, ?, ?)
               ON CONFLICT(paper_id) DO UPDATE SET
               filename=excluded.filename, chunks_json=excluded.chunks_json""",
            (_paper_id, extraction.filename, chunks_json),
        )

        if _owns:
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        if _owns:
            conn.execute("ROLLBACK")
        raise PersistenceError(
            f"Failed to save extraction for paper_id={extraction.paper_id!r}."
        ) from exc
    except (ValueError, PersistenceError):
        # Do not wrap; these are already domain exceptions.
        if _owns:
            conn.execute("ROLLBACK")
        raise
    finally:
        if _owns:
            conn.close()
```

### 6.3 Wrapping Rules

| Exception type | Wrapped as | Notes |
|---|---|---|
| `sqlite3.Error` (including `IntegrityError`, `OperationalError`) | `PersistenceError` with `__cause__` | Wrap all storage-layer failures |
| `json.JSONDecodeError` during read | `CorruptRecordError` with `__cause__` | Malformed stored JSON |
| `pydantic.ValidationError` during read | `CorruptRecordError` with `__cause__` | Schema-invalid stored JSON |
| `RecordNotFoundError` | **Not wrapped** | Already a domain exception |
| `InvalidJobTransitionError` | **Not wrapped** | Already a domain exception |
| `CorruptRecordError` | **Not wrapped** | Already a domain exception |
| `ValueError` | **Not wrapped** | Input validation failure |

---

## 7. Job Transition State Machine (Strict)

### 7.1 Allowed Transitions

```
┌──────────┐  mark_running()   ┌──────────┐  mark_succeeded()  ┌───────────┐
│ pending   │──────────────────▶│ running   │──────────────────▶│ succeeded  │
└────┬─────┘                   └────┬─────┘                   └───────────┘
     │                              │
     │  mark_failed()               │  mark_failed()
     └──────────────────────────────┴─────────────────────────▶┌──────────┐
                                                               │  failed   │
                                                               └──────────┘
```

### 7.2 Atomic Compare-and-Set SQL

Every transition uses a single `UPDATE` with a `WHERE` clause:

**`mark_running`:**
```sql
UPDATE jobs SET status = 'running', updated_at = ?
WHERE job_id = ? AND status = 'pending'
```

**`mark_succeeded`:**
```sql
UPDATE jobs SET status = 'succeeded', updated_at = ?
WHERE job_id = ? AND status = 'running'
```

**`mark_failed`:**
```sql
UPDATE jobs SET status = 'failed', error = ?, updated_at = ?
WHERE job_id = ? AND status IN ('pending', 'running')
```

### 7.3 Zero-Row Handling

After any transition where `cursor.rowcount == 0`:

1. Query current row using the **same connection**: `SELECT status FROM jobs WHERE job_id = ?`
2. If no row: raise `RecordNotFoundError`
3. Otherwise: raise `InvalidJobTransitionError` with a message like `"Cannot transition job {job_id!r} from {current_status} to {desired_status}."`

**There is no idempotent path.** A second `mark_running` on an already-running job raises `InvalidJobTransitionError`. This is essential to prevent two workers from both believing they claimed the same job.

### 7.4 Transition Matrix

| From | To | Allowed? | Notes |
|---|---|---|---|
| pending | running | ✅ | `mark_running()` — exactly once |
| pending | failed | ✅ | `mark_failed()` — preflight/scheduling failure |
| running | succeeded | ✅ | `mark_succeeded()` |
| running | failed | ✅ | `mark_failed()` — execution failure |
| running | running | ❌ | `InvalidJobTransitionError` — prevents double-claim |
| succeeded | succeeded | ❌ | `InvalidJobTransitionError` |
| failed | failed | ❌ | `InvalidJobTransitionError` |
| pending | succeeded | ❌ | `InvalidJobTransitionError` |
| succeeded | * | ❌ | `InvalidJobTransitionError` |
| failed | * | ❌ | `InvalidJobTransitionError` |

---

## 8. Error Code Specification

### 8.1 Stored Format

The `jobs.error` column stores only machine-readable error codes matching:

```
^[a-z][a-z0-9_]{0,63}$
```

Examples:
- `server_restart`
- `extraction_missing`
- `map_generation_failed`
- `llm_provider_error`
- `persistence_error`
- `task_scheduling_failed`

### 8.2 Validation

Before any SQL execution:

```python
import re

_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

def _validate_error_code(code: str) -> str:
    if not isinstance(code, str) or not _ERROR_CODE_RE.match(code):
        raise ValueError(
            f"error_code must match pattern '^[a-z][a-z0-9_]{{0,63}}$'; got {code!r}."
        )
    return code
```

### 8.3 What is NOT Stored

- Raw exception messages
- Stack traces
- Source text
- Chunk content
- Model prompts or responses
- Provider response bodies
- Credentials
- Connection strings

Human-readable messages for API responses are mapped from codes at the router/API layer, not in the repository.

---

## 9. Clock and UUID Injection

### 9.1 Defaults

```python
from datetime import datetime, timezone

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _new_uuid() -> str:
    return str(uuid.uuid4())
```

### 9.2 Injection Points

```python
class JobStore:
    def __init__(
        self,
        db_path: str,
        *,
        connection_factory: Callable[[str], sqlite3.Connection] = get_connection,
        clock: Callable[[], datetime] = _utc_now,
        uuid_factory: Callable[[], str] = _new_uuid,
    ) -> None:
```

- `connection_factory` matches the signature of `get_connection` from `app.database`.
- `clock` is called once during `create()` and once per transition.
- `uuid_factory` is called once during `create()`.

### 9.3 Clock Call Count

- **`create()`:** 1 call — `now = self._clock()`; `created_at = now; updated_at = now`
- **`mark_running()`:** 1 call — sets `updated_at`
- **`mark_succeeded()`:** 1 call — sets `updated_at`
- **`mark_failed()`:** 1 call — sets `updated_at`

### 9.4 UUID Validation

The return value of `uuid_factory` is validated before SQL:

```python
job_id = self._uuid_factory()
if not isinstance(job_id, str) or not job_id.strip():
    raise PersistenceError("uuid_factory returned an empty or invalid identifier.")
```

---

## 10. Timestamp Timezone Awareness

### 10.1 Current Model Gap

The `Job` model uses plain `datetime` — not `AwareDatetime`. This means naive datetimes could theoretically be accepted by Pydantic validation.

### 10.2 Required Fix

Add a field validator (or use `AwareDatetime`) to enforce:

```python
from datetime import datetime, timezone

@field_validator("created_at", "updated_at", mode="after")
@classmethod
def _require_utc_aware(cls, v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware.")
    if v.utcoffset() != timezone.utcoffset():
        raise ValueError("Timestamp must be UTC.")
    return v
```

This ensures that:
- Naive datetimes are rejected during `Job.model_validate()` → triggers `CorruptRecordError` in the repository.
- Non-UTC datetimes (e.g., `+03:00`) are rejected.
- The repository itself always produces UTC-aware timestamps via `datetime.now(timezone.utc)`.

### 10.3 Application

This validator is added **only to `Job`** (not to other models). The `JobStatusResponse` inherits from `Job` and gets it automatically.

---

## 11. Serialization Strategy

### 11.1 ExtractionStore

- **Write:** `TypeAdapter(list[Chunk]).dump_json(chunks).decode("utf-8")` into `chunks_json`
- **Read:** `TypeAdapter(list[Chunk]).validate_json(row["chunks_json"])` → construct `ExtractionResult` from row columns
- `paper_id` and `filename` come from row columns, **not** from JSON
- No duplication of identifiers

### 11.2 ResearchMapStore

- **Write:** `ResearchMap.model_dump_json()` into `map_json`
- **Read:** `ResearchMap.model_validate_json(row["map_json"])` → verify `map.paper_id == row["paper_id"]`
- Complete object stored; paper_id mismatch raises `CorruptRecordError`

### 11.3 JobStore

- Timestamps: `dt.isoformat()` — produces UTC ISO-8601 format
- Status: `JobStatus` enum serializes to bare string via `StrEnum`
- `error`: stored as plain TEXT (the validated `error_code` string)

### 11.4 General Rules

- UTF-8 safe — SQLite TEXT handles Unicode natively
- No `pickle`, `eval()`, or custom unsafe encoding
- No raw JSON string equality in tests — compare reconstructed Pydantic models via `==`
- Compact JSON (no indentation) for storage

---

## 12. Input Validation

All identifiers and codes must pass validation before reaching SQL:

| Parameter | Validation | Error on failure |
|---|---|---|
| `paper_id` | Non-blank `str` (stripped) | `ValueError` |
| `job_id` | Non-blank `str` (stripped) | `ValueError` |
| `error_code` | Matches `^[a-z][a-z0-9_]{0,63}$` | `ValueError` |
| `uuid_factory` return | Non-blank `str` | `PersistenceError` |

A helper:

```python
def _validate_nonblank(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank.")
    return value.strip()
```

---

## 13. Active Job Retrieval

### 13.1 Query

```sql
SELECT * FROM jobs
WHERE paper_id = ?
  AND status IN ('pending', 'running')
ORDER BY created_at DESC, job_id DESC
LIMIT 1
```

### 13.2 Deterministic Tie-Break

The secondary sort on `job_id DESC` ensures deterministic results when two jobs have identical `created_at` values (e.g., from a fixed test clock).

### 13.3 No Database-Level Uniqueness

The current schema does **not** enforce at most one active job per paper. This is acceptable for the single-process MVP: orchestration code checks `get_active_job_for_paper()` before creating a new job. A partial unique index on `(paper_id) WHERE status IN ('pending','running')` can be added later if needed.

---

## 14. Logging and Privacy Rules

### 14.1 Allowed in Logs

- Operation name
- `job_id`
- `paper_id`
- Status transition (from/to)
- `error_code`
- Row counts
- Success/failure category

### 14.2 Prohibited in Logs

- Chunk text
- Evidence excerpts
- Complete extraction JSON
- Complete research-map JSON
- Prompts
- Model responses
- API keys
- Database connection strings
- `error_code` validation failures with full code dump (use `repr` only for short codes)

### 14.3 Pattern

```python
_log = logging.getLogger(__name__)

_log.debug("Creating pending job for paper_id=%r.", paper_id)
_log.info("Job %r transitioned pending → running.", job_id)
_log.error("Failed to save extraction for paper_id=%r.", paper_id, exc_info=True)
```

The `exc_info=True` on error logs provides traceback context without needing to format the exception message inline.

---

## 15. Unit-Test Matrix

All tests use `tmp_path`-backed SQLite databases. Each test file calls `init_db` explicitly before use. No real `paperscape.db` is accessed.

### 15.1 `test_job_store.py`

| # | Test | Category |
|---|---|---|
| 1 | `test_create_pending_job` | Core CRUD |
| 2 | `test_create_job_has_correct_fields` | Core CRUD |
| 3 | `test_created_at_equals_updated_at_on_create` | Timestamps |
| 4 | `test_custom_uuid_factory_is_used` | Dependency injection |
| 5 | `test_custom_clock_is_used` | Dependency injection |
| 6 | `test_clock_called_once_during_create` | Timestamps |
| 7 | `test_timestamps_are_utc_aware` | Timestamps |
| 8 | `test_timestamps_are_utc_specifically` | Timestamps |
| 9 | `test_get_existing_job` | Core CRUD |
| 10 | `test_get_missing_job_returns_none` | Core CRUD |
| 11 | `test_require_existing_job` | Core CRUD |
| 12 | `test_require_missing_job_raises` | Error handling |
| 13 | `test_mark_running_from_pending_succeeds` | Transition: allowed |
| 14 | `test_mark_succeeded_from_running_succeeds` | Transition: allowed |
| 15 | `test_mark_failed_from_running_succeeds` | Transition: allowed |
| 16 | `test_mark_failed_from_pending_succeeds` | Transition: allowed (preflight) |
| 17 | `test_mark_failed_stores_error_code` | Error codes |
| 18 | `test_mark_failed_error_code_stored_exactly` | Error codes |
| 19 | `test_mark_succeeded_from_pending_rejected` | Transition: rejected |
| 20 | `test_mark_running_from_succeeded_rejected` | Transition: rejected |
| 21 | `test_mark_running_from_failed_rejected` | Transition: rejected |
| 22 | `test_mark_succeeded_from_failed_rejected` | Transition: rejected |
| 23 | `test_mark_failed_from_succeeded_rejected` | Transition: rejected |
| 24 | `test_mark_failed_from_failed_rejected` | Transition: rejected |
| 25 | `test_repeated_mark_running_rejected` | Transition: no idempotent claim |
| 26 | `test_repeated_mark_succeeded_rejected` | Transition: no idempotent re-apply |
| 27 | `test_repeated_mark_failed_rejected` | Transition: no idempotent re-apply |
| 28 | `test_missing_transition_target_raises` | Error handling |
| 29 | `test_second_worker_cannot_claim_already_running_job` | Concurrency: deterministic CAS |
| 30 | `test_transition_uses_atomic_compare_and_set` | Concurrency |
| 31 | `test_error_code_must_match_pattern` | Input validation |
| 32 | `test_blank_error_code_rejected` | Input validation |
| 33 | `test_blank_paper_id_rejected` | Input validation |
| 34 | `test_blank_job_id_rejected` | Input validation |
| 35 | `test_uuid_factory_returns_blank_rejected` | Input validation |
| 36 | `test_get_active_job_for_paper_returns_pending` | Active job lookup |
| 37 | `test_get_active_job_for_paper_returns_running` | Active job lookup |
| 38 | `test_get_active_job_for_paper_none_when_all_succeeded` | Active job lookup |
| 39 | `test_get_active_job_for_paper_none_when_all_failed` | Active job lookup |
| 40 | `test_get_active_job_for_paper_none_when_no_jobs` | Active job lookup |
| 41 | `test_get_active_job_returns_deterministic_tie_break` | Active job lookup |
| 42 | `test_has_completed_job_for_paper_true` | Completion check |
| 43 | `test_has_completed_job_for_paper_false` | Completion check |
| 44 | `test_status_constraint_enforced` | Schema enforcement |
| 45 | `test_nonexistent_job_id_returns_none` | Core CRUD |
| 46 | `test_no_source_content_or_ids_in_exception_messages` | Safety |
| 47 | `test_repository_owned_connection_closed` | Connection ownership |
| 48 | `test_caller_owned_connection_remains_open` | Connection ownership |
| 49 | `test_repository_owned_write_commits` | Transaction behavior |
| 50 | `test_repository_owned_write_rolls_back_on_failure` | Transaction behavior |

### 15.2 `test_extraction_store.py`

| # | Test | Category |
|---|---|---|
| 1 | `test_save_and_retrieve` | Core CRUD |
| 2 | `test_every_chunk_round_trips` | Data integrity |
| 3 | `test_chunk_ids_round_trip` | Data integrity |
| 4 | `test_chunk_pages_round_trip` | Data integrity |
| 5 | `test_chunk_sections_round_trip` | Data integrity |
| 6 | `test_chunk_text_round_trips` | Data integrity |
| 7 | `test_filename_round_trips_from_column` | Data integrity |
| 8 | `test_paper_id_round_trips_from_column` | Data integrity |
| 9 | `test_section_none_round_trips` | Data integrity |
| 10 | `test_section_string_round_trips` | Data integrity |
| 11 | `test_unicode_text_round_trips` | Data integrity |
| 12 | `test_missing_extraction_returns_none` | Core CRUD |
| 13 | `test_require_missing_raises` | Error handling |
| 14 | `test_exists_true` | Core CRUD |
| 15 | `test_exists_false` | Core CRUD |
| 16 | `test_repeated_save_replaces` | Upsert behavior |
| 17 | `test_repeated_save_filename_updated` | Upsert behavior |
| 18 | `test_malformed_json_raises_corrupt` | Error handling |
| 19 | `test_schema_invalid_json_raises_corrupt` | Error handling |
| 20 | `test_failed_write_rolls_back` | Transaction behavior |
| 21 | `test_caller_conn_remains_open` | Connection ownership |
| 22 | `test_repository_conn_is_closed` | Connection ownership |
| 23 | `test_blank_paper_id_rejected` | Input validation |
| 24 | `test_no_extraction_text_in_logs_or_errors` | Safety |
| 25 | `test_upsert_is_atomic` | Transaction behavior |
| 26 | `test_extraction_result_not_duplicated_in_json` | Data integrity |

### 15.3 `test_research_map_store.py`

| # | Test | Category |
|---|---|---|
| 1 | `test_save_and_retrieve` | Core CRUD |
| 2 | `test_paper_id_round_trips` | Data integrity |
| 3 | `test_exactly_three_findings_round_trip` | Data integrity |
| 4 | `test_all_evidence_round_trips` | Data integrity |
| 5 | `test_confidence_values_round_trip` | Data integrity |
| 6 | `test_limitations_round_trip` | Data integrity |
| 7 | `test_disclaimer_round_trips` | Data integrity |
| 8 | `test_missing_map_returns_none` | Core CRUD |
| 9 | `test_require_missing_raises` | Error handling |
| 10 | `test_exists_true` | Core CRUD |
| 11 | `test_exists_false` | Core CRUD |
| 12 | `test_repeated_save_replaces` | Upsert behavior |
| 13 | `test_malformed_json_raises_corrupt` | Error handling |
| 14 | `test_schema_invalid_json_raises_corrupt` | Error handling |
| 15 | `test_paper_id_mismatch_raises_corrupt` | Data integrity |
| 16 | `test_failed_write_rolls_back` | Transaction behavior |
| 17 | `test_caller_conn_remains_open` | Connection ownership |
| 18 | `test_repository_conn_is_closed` | Connection ownership |
| 19 | `test_blank_paper_id_rejected` | Input validation |
| 20 | `test_no_evidence_excerpt_in_logs_or_errors` | Safety |
| 21 | `test_upsert_is_atomic` | Transaction behavior |

### 15.4 Cross-Repository Transaction Tests

These tests exercise the caller-managed transaction pattern across all three repositories using a shared connection.

| # | Scenario | Category |
|---|---|---|
| 1 | `test_success_flow_create_extract_mark_running_map_succeed` | Integration |
| 2 | `test_failure_flow_then_reopen` | Integration |
| 3 | `test_caller_commit_persists_all_repository_writes` | Transaction behavior |
| 4 | `test_caller_rollback_removes_all_repository_writes` | Transaction behavior |
| 5 | `test_repository_does_not_rollback_caller_transaction` | Transaction behavior |
| 6 | `test_caller_conn_stays_open_across_multiple_repositories` | Connection ownership |

### 15.5 Two-Connection Concurrency Test (Deterministic)

The primary concurrency correctness test uses two configured connections, not threads:

| # | Scenario |
|---|---|
| 1 | Create pending job → Connection A calls `mark_running()` successfully → Connection B calls `mark_running()` → raises `InvalidJobTransitionError` → final status is `running` with B's call rejected |

This proves CAS behavior without thread-scheduling flakiness.

---

## 16. Test Isolation Rules

- `tmp_path`-backed SQLite databases only
- `init_db` called explicitly in each test fixture
- No `.env` reads
- No default `paperscape.db`
- No network calls
- No real sleeps
- No live watsonx credentials
- Connections reliably closed
- Deterministic on Windows

---

## 17. Scope Exclusions

- FastAPI routes, BackgroundTasks, HTTP concepts
- Worker functions, job polling endpoints
- Automatic extraction or research-map execution
- Live watsonx calls
- Flutter integration
- Celery, Redis, Alembic
- Authentication, multi-user ownership
- Cleanup scheduling, job cancellation, progress percentages
- Job queues, streaming, file storage
- Version history for repeated saves
- Partial unique index for active-job enforcement
- Cross-table foreign keys

---

## 18. Acceptance Criteria

1. `JobStore` persists and reconstructs current `Job` models via Pydantic.
2. All job transitions are strict and atomic — no idempotent "already at target" paths.
3. Only one caller can successfully transition `pending → running`.
4. Invalid transitions raise `InvalidJobTransitionError`.
5. `pending → failed` is allowed (preflight failure support).
6. Only validated machine-readable `error_code` values are stored in `jobs.error`.
7. `ExtractionResult` round-trips through SQLite with all chunk fields intact.
8. `chunks_json` stores only `list[Chunk]`, not the complete `ExtractionResult`.
9. `ResearchMap` round-trips through SQLite; `paper_id` mismatch on read raises `CorruptRecordError`.
10. Corrupt stored JSON is reported safely via `CorruptRecordError`.
11. Upserts are atomic (`INSERT ... ON CONFLICT`).
12. Repository-owned connections are opened, transacted, committed/rolled back, and closed.
13. Caller-supplied connections are used without BEGIN/COMMIT/ROLLBACK/close.
14. Transactions roll back on failure; caller-managed rollback removes cross-repository writes.
15. No paper or evidence content appears in logs or exception messages.
16. No raw exception text, model output, or provider details in `error` column.
17. All tests use temporary SQLite databases only.
18. No FastAPI, BackgroundTasks, HTTP, or watsonx SDK imports in repository modules.
19. `pytest backend/tests/` passes with zero failures.
20. `git diff --check` passes.
21. Timestamps are UTC-aware and validated through the `Job` model.

---

## 19. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `Job` model accepts naive datetimes | High (current state) | Add `@field_validator` for UTC awareness; repository always writes `datetime.now(timezone.utc)` |
| `TypeAdapter` not available in Pydantic version | Low | `TypeAdapter` available since Pydantic 2.0; pinned version is 2.13.4 |
| Two pending jobs with same timestamps cause non-deterministic `get_active_job_for_paper` | Low | Secondary sort on `job_id DESC` guarantees deterministic ordering |
| No database enforcement of one-active-job-per-paper | Low | MVP orchestration checks before creation; single-process design; partial unique index reserved for later |
| Duplicate `job_id` from UUID factory | Very Low | UUID v4 collision negligible; `UNIQUE` constraint on `job_id` catches it as `PersistenceError` |
| Large extraction JSON within SQLite TEXT limit | Low | Typical extraction < 10 MB; SQLite TEXT max ~1 GB |
| Threaded concurrency test flaky on Windows | Medium | Primary correctness test uses deterministic two-connection CAS; threaded test optional |