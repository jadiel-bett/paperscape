# IBM Bob Usage Log

This document records how IBM Bob was used as the primary development tool while building PaperScape.

It distinguishes between:

* Work planned or implemented using IBM Bob
* Decisions made by the developer
* Audits and corrections performed after implementation
* Tests and manual verification
* Resulting Git commits

This log was introduced after completion of Sub-task 3. Entries for project setup, Sub-task 1, and Sub-task 2 were reconstructed from the project plans, Git history, Bob reports, audits, and test results.

No credentials, `.env` contents, private papers, or confidential prompts are included.

---

## Project Initialization and Product Planning

**Status:** Completed
**Branch:** `main`
**Commit:** `<e688676>`

### Objective

Establish the product definition, repository rules, architecture boundaries, and first end-to-end development plan for PaperScape.

PaperScape is an AI-powered research communication studio that turns dense research PDFs into audience-specific, evidence-backed explainer packs.

### IBM Bob workflow

IBM Bob was used to:

* Initialize the repository using `/init`
* Generate project instruction files
* Review the proposed product architecture
* Create the first vertical-slice implementation plan
* Help structure the product specification
* Define implementation phases and acceptance criteria

### Artifacts created

* `AGENTS.md`
* `.bobignore`
* `.gitignore`
* `docs/product-spec.md`
* `docs/vertical-slice-plan.md`

### Key product decisions

The developer established that the first working vertical slice would:

1. Upload one selectable-text PDF
2. Extract page-aware content
3. Generate a structured research map
4. Run Granite inference through an asynchronous job
5. Poll job status from the frontend
6. Display three findings, limitations, and source evidence

The following were deliberately deferred:

* Authentication
* OCR
* Automatic video generation
* Multi-paper comparison
* Collaboration
* Redis and Celery
* Advanced chart and figure interpretation

### Human contribution

The developer:

* Selected PaperScape as the hackathon concept
* Defined the target users and core problem
* Chose Flutter Web and FastAPI
* Chose watsonx.ai and IBM Granite for runtime AI
* Required evidence-linked output
* Approved asynchronous polling instead of blocking model requests
* Reviewed and committed the product specification and vertical-slice plan

### Outcome

The project began with a documented scope, architecture, development workflow, and definition of done.

---

## Sub-task 1 — Repository Scaffold and Data Model Documentation

**Status:** Completed
**Branch:** `feat/project-scaffold`
**Implementation commit:** `<74e8110>`

### Objective

Create a minimal, runnable PaperScape repository with backend and frontend scaffolding, environment templates, documentation, tests, and a health endpoint.

### IBM Bob workflow

#### Planning and implementation

**Bob mode:** Agent

Bob reviewed:

* `AGENTS.md`
* `docs/product-spec.md`
* `docs/vertical-slice-plan.md`

Bob created the initial project structure, including:

* FastAPI backend package
* Flutter Web project
* Environment-variable templates
* Docker Compose stub
* Data-model documentation
* Evaluation directories
* Health endpoint
* Backend health tests

### Files and structures created

Backend:

* `backend/app/main.py`
* `backend/app/config.py`
* `backend/app/routers/health.py`
* Backend package directories
* Backend test directories
* `backend/requirements.txt`
* `backend/.env.example`

Frontend:

* Flutter Web project under `frontend/`

Documentation and configuration:

* `docs/data-model.md`
* Root `.env.example`
* `docker-compose.yml`
* `evals/fixtures/.gitkeep`
* `evals/expected/.gitkeep`

### Initial validation

Bob ran:

```powershell
python -m pytest backend/tests -v
flutter analyze
flutter build web
```

Initial results:

* Backend health tests passed
* Flutter analysis found no issues
* Flutter Web built successfully

### Bob audit

**Bob mode:** Ask

Bob audited the scaffold for:

* Missing files
* Incorrect dependencies
* Secret exposure
* Data-model inconsistencies
* Git-ignore problems
* App-factory testability
* Docker Compose validity
* Generated files that should not be tracked

### Audit findings and corrections

The review identified:

* Unused Python imports
* Duplicate `.gitignore` entries
* Missing trailing newline in `.gitignore`
* Settings being resolved too early
* Need for reproducible dependency versions
* Need to confirm `httpx2` compatibility
* Need to verify all documented data models

The audit incorrectly described the data-model count as nine, but listed all ten required items:

1. `Chunk`
2. `ExtractionResult`
3. `UploadResponse`
4. `Evidence`
5. `Finding`
6. `ResearchMap`
7. `JobStatus`
8. `Job`
9. `JobCreateResponse`
10. `JobStatusResponse`

The documentation itself was complete.

Bob applied the approved corrections:

* Removed unused imports
* Cleaned `.gitignore`
* Added virtual-environment ignore coverage
* Refactored FastAPI setup into a testable `create_app()` factory
* Pinned tested direct dependencies
* Preserved `httpx2` compatibility with the installed FastAPI and Starlette versions

### Human verification

The developer created a clean review virtual environment and ran:

```powershell
python -m pip install -r backend/requirements.txt
python -m pip check
python -m pytest backend/tests -v
docker compose config
```

Verified versions included:

* FastAPI `0.139.0`
* Starlette `1.3.1`
* Pydantic `2.13.4`
* HTTPX2 `2.7.0`

The developer also confirmed:

* The health endpoint returned `{"status":"ok"}`
* Dependencies installed cleanly from `requirements.txt`
* `.env` and virtual environments were ignored
* No secrets were committed

### Bob contribution

IBM Bob was used to:

* Scaffold the repository
* Generate the backend and frontend foundations
* Create the health endpoint and tests
* Write data-model documentation
* Audit the implementation
* Apply approved corrections
* Run tests and builds

### Human contribution

The developer:

* Defined the scaffold scope
* Reviewed Bob’s implementation
* Corrected the audit’s model-count error
* Verified dependency installation in a clean environment
* Validated Docker Compose configuration
* Approved the implementation for commit

### Outcome

PaperScape had a clean, reproducible, runnable foundation with a tested FastAPI backend and Flutter Web frontend.

---

## Sub-task 2 — Pydantic Models and SQLite Database Schema

**Status:** Completed
**Branch:** `feat/models-and-database`
**Implementation commit:** `<79151ff>`

### Objective

Implement PaperScape’s canonical data contracts, secure settings model, SQLite schema, startup initialization, and isolated tests.

### IBM Bob workflow

#### Planning

**Bob mode:** Plan

Bob created:

* `docs/subtask-2-models-database-plan.md`

The plan covered:

* Paper and chunk models
* Research-map models
* Job models
* Settings validation
* SQLite connection management
* Schema initialization
* Stale job recovery
* Unit-test strategy

### Human architectural decisions

The developer reviewed the plan and required:

* `SecretStr` for `watsonx_api_key`
* Plain `str` for `watsonx_project_id`
* `StrEnum` for `JobStatus`
* Exactly three findings enforced with `Field`
* `JobStatusResponse` inheriting from `Job`
* Explicit SQLite URL validation
* Caller-owned database connections remaining open
* FastAPI lifespan integration
* No ORM
* No premature JobStore implementation

### Implementation

**Bob mode:** Agent

Bob created:

* `backend/app/models/paper.py`
* `backend/app/models/research_map.py`
* `backend/app/models/job.py`
* `backend/app/database.py`
* `backend/tests/unit/test_models.py`
* `backend/tests/unit/test_database.py`
* `backend/tests/unit/test_config.py`

Bob modified:

* `backend/app/config.py`
* `backend/app/main.py`
* `docs/data-model.md`

### Implemented behavior

The implementation added:

* Validated paper, chunk, evidence, finding, research-map, and job models
* Nonblank string validation
* Minimum-one-chunk enforcement
* Exactly-three-findings enforcement
* Minimum-one-limitation enforcement
* Fixed expert-review disclaimer
* `JobStatus` as `StrEnum`
* Secret masking for the watsonx API key
* SQLite URL validation
* SQLite schema initialization
* `jobs`, `extractions`, and `research_maps` tables
* Valid job-status database constraint
* Foreign-key enforcement
* WAL mode for file-backed databases
* Stale `running` jobs reset to `failed`
* Explicit transaction commit and rollback
* FastAPI lifespan database initialization

### Bob audit

**Bob mode:** Ask

Bob audited:

* Model invariants
* Empty-string behavior
* Secret serialization
* SQLite transactions
* Connection ownership
* WAL behavior
* Foreign-key setup
* Test isolation
* Real database side effects
* Stale-job reset coverage
* Scope expansion

### Audit findings and corrections

The audit found:

* API tests could initialize the default database
* Rollback behavior needed to be explicit
* The jobs table lacked a status constraint
* Foreign-key enforcement was missing
* Empty limitations were accepted
* Required strings accepted blanks
* Empty extraction chunks were accepted
* The fixed disclaimer could be overridden
* Tests needed broader stale-job coverage
* Test settings needed to ignore `.env`
* File-backed WAL behavior needed testing

The audit also claimed `SecretStr` could leak through `model_dump(mode="json")`. The developer checked this against Pydantic `2.13.4` and determined that the value remained masked by default. A regression test was added rather than introducing an unnecessary custom serializer.

### Corrections applied

Bob added:

* `backend/tests/conftest.py`
* Injected temporary file-backed test settings
* TestClient lifespan isolation
* Explicit database rollback
* Job-status database constraint
* Foreign-key pragma
* WAL verification
* Expanded stale-job tests
* Nonblank field validation
* Minimum extraction-chunk validation
* Minimum limitation validation
* Fixed disclaimer enforcement
* `StrEnum`
* UTF-8 environment-file encoding
* Secret masking tests
* Windows SQLite URL tests
* Updated data-model documentation

### Verification

Bob reported:

```text
72 collected
72 passed
0 warnings
```

The developer verified:

```powershell
python -m pip check
python -m pytest backend/tests -v
git diff --check
```

The implementation confirmed:

* No real `paperscape.db` file was created during tests
* Caller-supplied database connections remained open
* Internally created connections were closed
* `running` jobs were reset correctly
* Other job statuses remained unchanged
* The health endpoint still worked
* No watsonx credentials were required for tests

### Bob contribution

IBM Bob was used to:

* Plan the data-model and database phase
* Implement the models and SQLite schema
* Generate validation and database tests
* Audit security and lifecycle behavior
* Apply approved corrections
* Update technical documentation

### Human contribution

The developer:

* Chose final model and settings semantics
* Required `SecretStr`, `StrEnum`, lifespan integration, and transaction safety
* Evaluated audit findings
* Rejected the incorrect SecretStr leak conclusion
* Required test isolation from the real database
* Approved the final implementation

### Outcome

PaperScape gained a secure, validated, testable domain model and persistent SQLite foundation suitable for later job execution and research-map storage.

---

## Sub-task 3 — Page-Aware PDF Extraction

**Status:** Completed
**Branch:** `feat/pdf-extraction`
**Implementation commit:** `<6235eb9>`

### Objective

Implement a PDF extraction service that converts selectable-text research PDFs into validated, page-aware chunks.

The service needed to:

* Use Docling as the primary parser
* Fall back to PyMuPDF
* Preserve page provenance
* Preserve section metadata where available
* Produce deterministic chunk IDs
* Avoid writing uploaded PDFs to disk
* Remain independent of FastAPI, SQLite, and watsonx.ai

### IBM Bob workflow

#### Planning

**Bob mode:** Plan

Bob created:

* `docs/subtask-3-pdf-extraction-plan.md`

The plan defined:

* `ExtractionService`
* `DoclingAdapter`
* `PyMuPDFAdapter`
* Internal `RawChunk`
* Fallback behavior
* Chunk-ID generation
* Content-type filtering
* Offline test strategy
* Acceptance criteria

### Human architectural decisions

The developer reviewed the plan and required:

* One-based public chunk indexes that reset on each page
* `DocumentStream` with `BytesIO`
* No temporary files
* Injectable adapters
* Explicit Docling content filtering
* Section headers treated as metadata
* Table text included as one compact chunk
* Figure captions retained
* Image content not interpreted
* Reliable page provenance
* Extraction-specific exceptions kept in `extraction.py`

### Implementation

**Bob mode:** Agent

Bob created:

* `backend/app/services/extraction.py`
* `backend/tests/unit/test_extraction.py`

Bob modified:

* `backend/requirements.txt`
* `docs/subtask-3-pdf-extraction-plan.md`

The implementation included:

* `ExtractionError`
* `DoclingExtractionError`
* Internal `RawChunk`
* Injectable parser adapters
* Docling-first extraction
* PyMuPDF fallback
* In-memory PDF processing
* Section tracking
* Deterministic chunk IDs
* Duplicate-ID detection
* Input validation
* Offline unit tests

### Bob audit

**Bob mode:** Ask

The audit examined:

* Public extraction contracts
* Docling item types
* Page provenance
* Chunk identifiers
* Fallback behavior
* Error handling
* Resource cleanup
* Input validation
* Test isolation
* Dependency pinning

The initial audit raised concerns about:

* Whether allowlisted Docling labels inherited from `TextItem`
* Blank identifiers being validated too late
* Public chunk indexes starting at zero
* Duplicate-ID implementation clarity
* Test type annotations

### Human review of findings

The developer determined that:

* Recursively emitting `GroupItem` content could duplicate child text
* The installed Docling class hierarchy should be verified directly
* Public identifiers must be one-based
* Invalid inputs should fail before Docling is invoked

### Corrections

**Bob mode:** Agent

Bob:

* Added early input validation
* Changed public IDs to one-based per-page numbering
* Tightened exception assertions
* Replaced side-effect duplicate detection with an explicit loop
* Corrected the `tmp_path` annotation
* Updated the plan and ID examples
* Documented Docling inheritance verification

### Real Docling verification

The installed version was:

```text
docling==2.37.0
```

The following classes were verified to inherit from `TextItem`:

* `ListItem`
* `SectionHeaderItem`
* `CodeItem`
* `FormulaItem`

A real two-page PDF produced:

```text
smoke-1-p1-1  page=1  section=None  text='Introduction'
smoke-1-p1-2  page=1  section=None  text='This is the introduction paragraph.'
smoke-1-p2-1  page=2  section=None  text='Methods'
smoke-1-p2-2  page=2  section=None  text='First step'
smoke-1-p2-3  page=2  section=None  text='Second step'
smoke-1-p2-4  page=2  section=None  text='Table 1: Results summary'
```

The smoke test confirmed:

* Docling processed the PDF
* PyMuPDF fallback was not used
* Page numbers were one-based
* Public chunk IDs were one-based
* No temporary PDF was written

### Verification

Results:

```text
Extraction tests: 14 passed
Complete backend suite: 86 passed
Failures: 0
```

Commands included:

```powershell
python -m pip check
python -m pytest backend/tests -v
git diff --check
```

Additional confirmations:

* No network calls in default unit tests
* No real Docling initialization in default tests
* No FastAPI, SQLite, HTTP, or watsonx imports in the extraction service
* No later-phase functionality was added

### Bob contribution

IBM Bob was used to:

* Create the extraction implementation plan
* Implement the parser architecture
* Generate unit tests
* Audit the implementation
* Apply approved fixes
* Update documentation
* Summarize validation results

### Human contribution

The developer:

* Set the extraction and grounding requirements
* Reviewed Bob’s plan
* Chose final chunk-ID semantics
* Corrected audit assumptions
* Verified Docling’s real class hierarchy
* Ran the real Docling smoke test
* Reviewed all test results
* Approved the final implementation

### Outcome

PaperScape gained a tested, page-aware extraction layer that supports Docling-first processing, PyMuPDF fallback, deterministic provenance, and offline unit testing.

---

## Current Project State

Completed:

* Product definition
* Vertical-slice architecture
* Repository scaffold
* Flutter Web foundation
* FastAPI foundation
* Pydantic data contracts
* SQLite schema and lifecycle
* Page-aware PDF extraction
* Docling and PyMuPDF integration

Next planned phase:

* `LLMProvider`
* `WatsonxProvider`
* IBM Granite inference integration

## Sub-task 4 — IBM watsonx.ai and Granite Provider

**Status:** Completed
**Branch:** `feat/watsonx-provider`
**Implementation commit:** `<d56333a>`

### Objective

Implement a secure and testable model-provider abstraction that allows PaperScape to call IBM Granite through watsonx.ai without coupling the rest of the application to the IBM SDK.

The provider needed to:

* Expose a small `LLMProvider` interface
* Use IBM `ModelInference`
* Load model and project configuration from injected settings
* Protect the IBM Cloud API key
* Validate generation inputs
* Return only usable generated text
* Retry only recognized transient failures
* Prevent duplicate retry behavior between PaperScape and the IBM SDK
* Remain independent of FastAPI, SQLite, jobs, and research-map logic
* Support complete offline unit testing

### IBM Bob workflow

#### 1. Planning

**Bob mode:** Plan

Bob reviewed:

* `AGENTS.md`
* `docs/product-spec.md`
* `docs/vertical-slice-plan.md`
* `docs/data-model.md`
* `backend/app/config.py`
* Existing service architecture
* Current backend dependencies

Bob created:

* `docs/subtask-4-watsonx-provider-plan.md`

The plan divided the work into:

1. IBM SDK installation and introspection
2. Provider exception hierarchy
3. `LLMProvider` abstract interface
4. watsonx SDK client factory
5. `WatsonxProvider`
6. Input and response validation
7. Retry behavior
8. Offline unit tests

### SDK documentation and introspection gate

The IBM watsonx.ai SDK was not installed when planning began.

Bob was instructed to:

* Review official IBM SDK documentation
* Search the repository for existing watsonx assumptions
* Compare public documentation with the project specification
* Install a pinned SDK version
* Inspect the actual installed Python signatures before implementation

The project pinned:

```text
ibm-watsonx-ai==1.5.14
```

Bob installed the package and inspected the installed SDK before writing the provider.

The following details were verified:

* `Credentials` is imported from `ibm_watsonx_ai`
* `ModelInference` is imported from `ibm_watsonx_ai.foundation_models`
* Generation parameter constants are imported from:

```python
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames
```

* `ModelInference` accepts:

  * `model_id`
  * `credentials`
  * `project_id`
  * `validate`
  * `max_retries`
* `validate=False` prevents a model-list request during client construction
* `max_retries=0` disables SDK-owned retry behavior
* `generate_text()` can declare return values other than `str`, so runtime response validation is required
* Structured SDK request failures can expose an HTTP status through `exc.response.status_code`
* Credential errors do not always expose a response object

### Human architectural decisions

The developer reviewed the Bob-generated plan and required:

* `generate_text()` rather than `generate()` because the project provider returns a string
* Synchronous `generate()` because inference runs inside a background job
* Caller input errors to raise `ValueError`
* Model response errors to use a separate `LLMResponseError`
* Greedy decoding when `temperature == 0`
* Sample decoding when `temperature > 0`
* The IBM SDK retry system to be disabled
* PaperScape to own a maximum of one retry
* Retry behavior based on an explicit status-code allowlist
* Unknown HTTP status codes to default to non-transient
* No exception classification based on parsing arbitrary error strings
* An injectable SDK client factory
* An injectable sleep function
* No network access in the default test suite

### 2. Implementation

**Bob mode:** Agent

Bob created:

* `backend/app/services/llm_provider.py`
* `backend/tests/unit/test_llm_provider.py`

Bob modified:

* `backend/requirements.txt`
* `docs/subtask-4-watsonx-provider-plan.md`

### Provider architecture

The implementation introduced:

```text
LLMProviderError
├── TransientLLMError
├── NonTransientLLMError
└── LLMResponseError
```

It also introduced:

* `LLMProvider` abstract base class
* `WatsonxProvider`
* An injectable watsonx SDK client factory
* Injectable sleep behavior for retry tests
* Structured exception classification
* Runtime output validation

The public interface is:

```python
def generate(
    self,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    ...
```

### SDK client construction

`WatsonxProvider` constructs the IBM SDK client using:

```text
model_id     = settings.granite_model_id
project_id   = settings.watsonx_project_id
credentials  = Credentials(
    url=settings.watsonx_url,
    api_key=settings.watsonx_api_key.get_secret_value(),
)
validate     = False
max_retries  = 0
```

The raw API key is unwrapped only during credential construction and is not stored as a provider attribute.

The provider does not:

* Read environment variables directly
* Store the plaintext API key
* Log complete prompts
* Log credentials
* Expose SDK response bodies in public exceptions
* Validate the selected model during construction

Using `validate=False` means an invalid Granite model ID is detected during the first generation request rather than provider startup.

### Input validation

The provider rejects invalid caller input before invoking the SDK.

It raises `ValueError` for:

* Blank or whitespace-only prompts
* `max_tokens` below `1`
* Temperature below `0.0`
* Temperature above `2.0`

### Generation parameters

For `temperature == 0.0`, the provider uses:

```text
decoding_method = greedy
max_new_tokens  = max_tokens
```

The temperature parameter is omitted.

For `temperature > 0.0`, the provider uses:

```text
decoding_method = sample
max_new_tokens  = max_tokens
temperature     = supplied temperature
```

The implementation uses `GenTextParamsMetaNames` constants rather than hardcoded parameter-key assumptions.

### Response validation

The provider accepts only a string result from `generate_text()`.

It raises `LLMResponseError` when the SDK returns:

* A non-string value
* An empty string
* A whitespace-only string

Valid generated text is stripped before being returned.

Response-validation failures are never retried.

### Retry behavior

PaperScape owns the retry loop.

The IBM SDK retry system is disabled with:

```text
max_retries=0
```

The provider makes at most:

```text
2 total inference attempts
```

The sequence is:

1. Perform the first request.
2. If the failure is recognized as transient, wait using the injected sleep function.
3. Retry once.
4. If the second request fails, raise `TransientLLMError`.
5. Do not retry non-transient or response-validation errors.

The retry delay is:

```text
1.0 second
```

Default tests inject a fake sleep function, so no real delays occur.

### Exception classification

Recognized transient HTTP statuses are:

```text
408
429
500
502
503
504
520
```

Recognized transient network failures include verified timeout and connection-error types.

Examples of non-transient failures include:

```text
400
401
403
404
409
422
```

The following are also non-transient:

* Invalid credentials
* Invalid caller inputs
* SDK `ValueError`
* Unknown exceptions
* Unknown HTTP status codes not in the transient allowlist
* Invalid model output

Unknown statuses such as `418` and `521` are not retried.

Classification uses structured exception fields where available. It does not search arbitrary exception strings for status codes.

### Credential and prompt safety

The implementation was designed so that:

* The plaintext API key is not retained by `WatsonxProvider`
* Secrets do not appear in `repr`
* Secrets do not appear in public exception messages
* Prompts do not appear in public exception messages
* Prompts and credentials are not written to logs
* Raw SDK response content is not exposed through provider errors
* Tests use fake credentials and never read the project `.env`

### 3. Audit

**Bob mode:** Ask

Bob audited the implementation against:

* Project rules
* Product requirements
* The Sub-task 4 plan
* The installed IBM SDK behavior
* Credential-safety requirements
* Retry constraints
* Test-isolation requirements

The review checked:

* Abstract-provider behavior
* SDK construction arguments
* Credential unwrapping
* Decoding parameters
* Input validation
* Response validation
* Exception classification
* Retry ownership
* Maximum request count
* Secret and prompt exposure
* Network isolation
* Scope boundaries

### Audit findings and corrections

The implementation report initially contained inconsistent test totals. The developer required Bob to rerun pytest collection and report exact per-file and total counts.

The initial implementation also classified unrecognized structured HTTP statuses as transient. The developer rejected this behavior because retries must be limited to explicitly recognized temporary failures.

Bob corrected the implementation so that:

* Only explicitly allowlisted statuses are retried
* Unknown status codes raise immediately as non-transient failures
* `418` is not retried
* `521` is not retried
* Known transient failures retry once
* At most two SDK calls are possible
* Reported test totals come directly from pytest collection

### 4. Tests and validation

The provider test suite covers:

* Abstract base-class behavior
* Correct watsonx URL
* Correct model ID
* Correct project ID
* API-key unwrapping
* No plaintext-key retention
* `validate=False`
* `max_retries=0`
* Prompt propagation
* Token parameter mapping
* Greedy decoding
* Sample decoding
* Temperature omission for greedy decoding
* Temperature inclusion for sampling
* Invalid prompt handling
* Invalid token limits
* Invalid temperatures
* Empty output
* Whitespace output
* Non-string output
* Transient retry behavior
* Successful retry
* Persistent transient failure
* Non-transient HTTP failure
* Invalid credentials
* Unknown failures
* Unknown status codes
* Sleep behavior
* Maximum request count
* Secret safety
* Prompt safety
* No real network calls

Final verification commands:

```powershell
python -m pip check
python -m pytest backend/tests --collect-only -q
python -m pytest backend/tests -v
git diff --check
```

Final results:

```text
LLM provider tests: <LLM_PROVIDER_TEST_COUNT> passed
Complete backend suite: <TOTAL_BACKEND_TEST_COUNT> passed
Failures: 0
Warnings: <WARNING_COUNT>
```

Any warnings were reviewed to confirm whether they originated from project code or third-party dependencies.

### Scope confirmation

The implementation did not add:

* Research-map generation
* Research-map prompts
* Background jobs
* API routes
* Database persistence
* Streaming responses
* LangChain
* Audience adaptation
* Live watsonx calls in the default test suite

### Bob contribution

IBM Bob was used to:

* Research the official IBM SDK contract
* Compare documentation with project requirements
* Install and inspect the pinned SDK
* Create the provider implementation plan
* Implement the provider and exception hierarchy
* Generate the offline unit-test suite
* Audit retry, security, and response behavior
* Apply approved corrections
* Run and summarize verification commands
* Update the technical plan

### Human contribution

The developer:

* Defined the provider boundaries
* Required IBM Granite and watsonx.ai integration
* Required actual SDK introspection before implementation
* Selected `generate_text()`
* Required one retry owner
* Defined explicit transient statuses
* Required unknown statuses to fail without retry
* Required credential and prompt safety
* Reviewed the implementation report
* Identified inconsistent test totals
* Required targeted audit corrections
* Approved the final implementation

### Outcome

PaperScape gained a secure, testable IBM watsonx.ai provider that can call Granite through a stable application-level interface.

The implementation provides:

* Controlled IBM SDK construction
* Safe credential handling
* Deterministic generation parameters
* Explicit response validation
* Predictable retry behavior
* Complete offline unit testing

The provider is ready to support the next phase:

* Grounded research-map prompt construction
* `ResearchMapService`
* Structured Granite output parsing
* Claim-to-evidence validation
