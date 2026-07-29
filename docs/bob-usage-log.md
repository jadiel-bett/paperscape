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

## Sub-task 5 — Grounded Research-Map Prompt and ResearchMapService

**Status:** Completed  
**Branch:** `feat/research-map-service`  
**Implementation commit:** `8d9d12b`

### Objective

Implement the grounded research-map generation layer that transforms a validated `ExtractionResult` into a validated public `ResearchMap` through an injected `LLMProvider`.

The service needed to:

- Build a bounded prompt from selected paper chunks
- Treat paper content as untrusted source data
- Require structured JSON-only model output
- Ground the research question, findings, and limitations in source evidence
- Validate every evidence reference against chunks actually supplied to the model
- Prevent the model from controlling `paper_id` or the fixed disclaimer
- Retry model generation once when output is malformed or insufficiently grounded
- Remain independent of FastAPI, SQLite, watsonx SDK classes, jobs, and API routes
- Support deterministic offline evaluation without network access

### IBM Bob workflow

#### Planning

**Bob mode:** Plan

Bob reviewed:

- `AGENTS.md`
- `docs/product-spec.md`
- `docs/vertical-slice-plan.md`
- `docs/data-model.md`
- Paper and research-map Pydantic models
- The extraction service
- The `LLMProvider` interface
- Existing evaluation directories

Bob created:

- `docs/subtask-5-research-map-service-plan.md`

The plan covered:

- `ResearchMapService`
- Private model-response schemas
- Grounded prompt construction
- Context selection and truncation
- JSON parsing
- Evidence validation
- Confidence handling
- Corrective generation
- Offline evaluation fixtures
- Unit-test coverage

### Human review and plan corrections

The developer reviewed the initial plan and required several grounding and safety changes before implementation.

The final approved design required:

1. Evidence validation against only the chunks selected for the prompt, rather than the full extraction.
2. Individual greedy context selection instead of whole-section group selection.
3. Preservation of original chunk order using ordinal positions rather than lexical chunk-ID sorting.
4. Exclusion of references, bibliography, and acknowledgements from model context.
5. Sentinel-based prompt rendering using `__PAPER_CONTEXT_JSON__` instead of `str.format()`.
6. Internal evidence grounding for the research question and limitations, not only findings.
7. No source text, excerpts, raw model responses, or complete prompts in logs or exceptions.
8. Exact duplicate evidence rejection rather than silent mutation or deduplication.
9. Structured corrective issue codes instead of deriving correction instructions from exception text.
10. An eval runner that works from the repository root and performs no import-time execution.
11. Rejection of uncertain findings in the first vertical slice.

Bob updated the plan to include these decisions before implementation began.

### Implementation

**Bob mode:** Agent

Bob created:

- `backend/app/prompts/research_map.txt`
- `backend/app/services/research_map.py`
- `backend/tests/unit/test_research_map.py`
- `evals/fixtures/research_map_extraction.json`
- `evals/fixtures/research_map_model_response.json`
- `evals/expected/research_map_fixture.json`
- `evals/run_evals.py`

Bob also updated:

- `docs/subtask-5-research-map-service-plan.md`

### Service architecture

The implementation introduced:

- `ResearchMapService`
- `MapGenerationError`
- `_InternalResearchMap`
- `_InternalFinding`
- `_InternalGroundedStatement`
- `_InternalEvidence`
- Structured internal validation issue codes
- Deterministic context selection
- Grounded prompt construction
- Evidence validation
- One corrective model-generation attempt
- Conversion from internal grounded output to the public `ResearchMap`

The service depends only on:

- `ExtractionResult`
- Public research-map models
- The `LLMProvider` interface
- Standard Python and Pydantic utilities

It does not import or construct:

- FastAPI
- SQLite
- Settings
- `WatsonxProvider`
- IBM watsonx SDK classes
- HTTP clients
- Background jobs

### Grounded prompt template

The prompt template is stored in:

```text
backend/app/prompts/research_map.txt

It uses the sentinel:

```text
__PAPER_CONTEXT_JSON__
```

The service verifies that this sentinel appears exactly once and replaces it with JSON produced by `json.dumps()`.

The prompt instructs the model to:

- Treat paper content as untrusted source data
- Ignore instructions embedded inside the paper
- Use only the supplied chunks
- Avoid outside knowledge
- Avoid invented findings, citations, or evidence
- Preserve numerical values and units
- Preserve uncertainty and qualifying language
- Distinguish correlation from causation
- Produce exactly three distinct findings
- Produce at least one limitation
- Ground the research question, findings, and limitations
- Use only valid chunk IDs and matching page numbers
- Copy evidence excerpts from source chunks
- Keep excerpts at or below 300 characters
- Return JSON only
- Avoid prose, markdown commentary, and chain-of-thought

### Context selection

The service uses a configurable source-word budget.

When all eligible chunks fit, they are included in original order.

When truncation is required:

1. Every chunk receives its original ordinal position.
2. References, bibliography, and acknowledgements are excluded.
3. Remaining chunks are assigned section priorities.
4. Chunks are considered individually in deterministic priority order.
5. A chunk is included only when the complete chunk fits the remaining budget.
6. Chunks are never split or rewritten.
7. Selected chunks are restored to their original document order.

When useful section metadata is absent, the service uses a deterministic head-and-tail fallback.

If no eligible chunk fits the context budget, the service raises `MapGenerationError` before calling the provider.

Truncation logs contain only safe metadata such as counts, word totals, paper ID, and whether truncation occurred.

### Internal grounded schemas

The model response cannot contain:

- `paper_id`
- `disclaimer`

All private schemas use:

```python
ConfigDict(extra="forbid")
```

The internal response requires:

- A grounded research question
- Exactly three grounded findings
- At least one grounded limitation

Each grounded statement includes:

- A nonblank statement
- One or more evidence items

Each evidence item includes:

- `chunk_id`
- `page`
- `excerpt`

Finding confidence is restricted to:

```text
high
partial
```

The value `uncertain` is rejected for the first vertical slice.

### Evidence validation

Every evidence item is validated against the selected chunks that were actually included in the prompt.

Validation includes:

- Referenced chunk ID exists in the selected context
- Evidence page matches the source chunk page
- Excerpt is nonblank
- Excerpt length does not exceed 300 characters
- Excerpt exists within the source chunk after deterministic normalization
- Duplicate evidence is rejected
- Duplicate findings are rejected
- Research-question evidence is validated
- Finding evidence is validated
- Limitation evidence is validated

Text normalization uses:

1. Unicode NFKC normalization
2. Repeated-whitespace collapse
3. Leading and trailing whitespace removal

No fuzzy matching is used.

Exact duplicate evidence is identified using:

```text
chunk_id + page + normalized excerpt
```

Different excerpts from the same source chunk remain valid.

### Application-controlled fields

The final public map always receives:

```python
paper_id = ExtractionResult.paper_id
```

The disclaimer is always supplied by the application.

Internal evidence for the research question and limitations is validated before conversion, but omitted from the public object because the current public schema exposes them as strings.

The model cannot override either `paper_id` or the disclaimer.

### Parsing and response validation

The service accepts:

- Raw JSON
- One optional outer `json` markdown fence

The service rejects:

- Bare markdown fences
- Prose before the JSON object
- Prose after the JSON object
- Loose JSON substring recovery
- Unknown fields
- Missing fields
- Incorrect field types
- The wrong number of findings
- Empty limitations
- Empty evidence arrays
- Unsupported confidence values

Raw model output is never included in logs or public exception messages.

### Corrective generation

The service allows at most two generation calls:

1. Initial generation
2. One corrective generation

A corrective call can occur for structured output failures such as:

- Invalid JSON
- Invalid schema
- Wrong finding count
- Unknown chunk ID
- Page mismatch
- Excerpt not found
- Duplicate finding
- Duplicate evidence
- Missing limitation
- Unsupported confidence

The corrective prompt includes only:

- Safe structured issue codes
- The same bounded paper context
- Valid selected chunk IDs and pages
- An instruction to regenerate the complete JSON object

It does not include:

- Stack traces
- Raw exception messages
- Credentials
- Raw model responses
- Complete paper text outside the bounded context

Both provider calls use:

```text
temperature = 0.1
max_tokens = 1500
```

`LLMProviderError` propagates unchanged and never triggers a corrective generation.

### Evaluation baseline

Bob created a deterministic offline evaluation based on a synthetic study about drought-resistant maize varieties in Kenya.

The evaluation includes:

- An eight-chunk synthetic `ExtractionResult`
- A valid grounded model response
- An expected public `ResearchMap`
- A fake `LLMProvider`
- A repository-root executable evaluation script

The evaluation verifies:

- Prompt-to-service integration
- Internal response parsing
- Evidence grounding
- Public-model conversion
- Application-controlled `paper_id`
- Application-controlled disclaimer

The evaluation is a parsing and grounding regression baseline. It is not presented as a broad measure of model quality.

The runner:

- Makes no network calls
- Reads no `.env` file
- Performs no live watsonx inference
- Exits non-zero when output differs from the expected fixture

### Audit and verification

**Bob mode:** Ask

Bob audited the implementation for:

- Service boundaries
- Prompt safety
- Private schema strictness
- Context-selection behavior
- Grounding validation
- Corrective retry behavior
- Application-controlled fields
- Logging and exception safety
- Evaluation isolation
- Scope compliance

The developer independently verified the project using the backend virtual environment.

Commands run:

```powershell
python -m pip check
python -m pytest backend/tests --collect-only -q
python -m pytest backend/tests -v
python evals/run_evals.py
git diff --check
```

Verified results:

```text
225 tests collected
225 tests passed
0 failures
0 errors
5 warnings
Offline evaluation: PASS
```

The five warnings were third-party PyMuPDF/SWIG deprecation warnings:

```text
SwigPyPacked has no __module__ attribute
SwigPyObject has no __module__ attribute
swigvarlink has no __module__ attribute
```

These warnings originated from dependency internals rather than PaperScape code.

No network calls were made during the test suite or offline evaluation.

### Scope confirmation

The implementation did not add:

- `JobStore`
- Background-task execution
- API endpoints
- Upload handling
- SQLite persistence of extractions or maps
- Flutter UI
- Embeddings
- Vector databases
- LangChain
- Audience adaptation
- Visual abstracts
- Narration
- Multi-paper support
- Live watsonx tests in the default suite

### Bob contribution

IBM Bob was used to:

- Create the initial Sub-task 5 implementation plan
- Revise the plan after developer review
- Implement the grounded prompt template
- Implement `ResearchMapService`
- Create strict internal response schemas
- Implement deterministic context selection
- Implement parsing and evidence validation
- Implement corrective generation with safe issue codes
- Generate the unit-test suite
- Create the deterministic offline evaluation
- Audit the implementation
- Report validation results

### Human contribution

The developer:

- Defined the grounded research-map requirements
- Reviewed Bob's initial plan
- Required selected-context evidence validation
- Replaced group-level selection with individual greedy selection
- Required original ordinal ordering
- Required sentinel-based prompt rendering
- Required grounding for research questions and limitations
- Required strict source-text safety in logs and exceptions
- Required exact duplicate-evidence rejection
- Required structured corrective issue codes
- Required the root-executable offline evaluation
- Required rejection of uncertain findings
- Resolved the local Python environment issue
- Independently ran the complete test suite and offline evaluation
- Approved the final implementation

### Outcome

PaperScape gained a deterministic and evidence-grounded research-map generation layer.

The completed service:

- Converts validated extractions into public research maps
- Grounds the research question, findings, and limitations
- Validates evidence against the exact chunks supplied to the model
- Prevents unsupported citations
- Controls `paper_id` and disclaimer application-side
- Limits context deterministically
- Handles malformed model output with one corrective attempt
- Preserves provider-level error boundaries
- Supports complete offline testing and regression evaluation

The next phase is:

- SQLite `JobStore`
- Extraction persistence
- Research-map persistence
- Background job orchestration

## Sub-task 6 — SQLite JobStore and Artifact Persistence

**Status:** Completed  
**Branch:** `feat/job-store-persistence`  
**Implementation commit:** `<f7e499b>`

### Objective

Implement a synchronous SQLite persistence layer for:

- Job lifecycle records
- Extracted paper content
- Generated research maps

The persistence layer needed to:

- Use the existing SQLite schema
- Reconstruct validated Pydantic domain models
- Support atomic job-state transitions
- Prevent multiple workers from claiming the same pending job
- Support caller-managed transactions spanning multiple repositories
- Preserve extraction and research-map data across application restarts
- Report corrupt stored records safely
- Avoid logging paper content, evidence excerpts, prompts, responses, or credentials
- Remain independent of FastAPI, background tasks, PDF parsing, and watsonx inference

### IBM Bob workflow

#### Planning

**Bob mode:** Plan

Bob reviewed:

- `AGENTS.md`
- `docs/product-spec.md`
- `docs/vertical-slice-plan.md`
- `docs/data-model.md`
- `backend/app/database.py`
- `backend/app/config.py`
- Paper, research-map, and job models
- Extraction and research-map services
- Existing database tests

Bob created:

- `docs/subtask-6-job-store-persistence-plan.md`

The plan covered:

- Existing SQLite schema suitability
- Repository interfaces
- Shared persistence exceptions
- Connection ownership
- Transaction ownership
- Job lifecycle transitions
- Atomic compare-and-set SQL
- Pydantic serialization
- Corrupt-record handling
- Repository unit tests
- Cross-repository transaction tests

### Existing schema assessment

Bob inspected the existing tables:

```text
jobs
extractions
research_maps
```

The existing schema was determined to be sufficient for the vertical slice.

No database migration or schema redesign was required.

The tables already supported:

- Application-generated job IDs
- Indexed paper-to-job lookup
- Job status constraints
- One extraction per paper
- One research map per paper
- Serialized chunk data
- Serialized research-map data
- Nullable job failure codes

No ORM or migration framework was added.

### Human review and plan corrections

The developer reviewed the initial plan and required several changes before implementation.

The final approved design required:

1. Strict, non-idempotent job transitions.
2. A second worker attempting to claim an already-running job to receive `InvalidJobTransitionError`.
3. Support for `pending → failed` when scheduling or preflight work fails before execution begins.
4. Storage of safe machine-readable error codes only.
5. Complete separation between repository-owned and caller-owned transactions.
6. Injectable connection factories for all repositories.
7. One clock call during job creation so `created_at` and `updated_at` begin with the same value.
8. UTC-aware job timestamps.
9. Storage of only `list[Chunk]` in `extractions.chunks_json`.
10. Verification that a decoded research map's `paper_id` matches its database row.
11. Validation of all job IDs, paper IDs, generated IDs, and failure codes.
12. Deterministic active-job ordering.
13. Deterministic compare-and-set tests rather than timing-dependent threaded races.
14. Cross-repository transaction tests using one caller-owned SQLite connection.

Bob revised the plan before implementation.

### Implementation

**Bob mode:** Agent

Bob created:

- `backend/app/repositories/__init__.py`
- `backend/app/repositories/errors.py`
- `backend/app/repositories/job_store.py`
- `backend/app/repositories/extraction_store.py`
- `backend/app/repositories/research_map_store.py`
- `backend/tests/unit/test_job_store.py`
- `backend/tests/unit/test_extraction_store.py`
- `backend/tests/unit/test_research_map_store.py`
- `backend/tests/unit/test_repository_integration.py`

Bob modified:

- `backend/app/models/job.py`
- `docs/data-model.md`
- `docs/subtask-6-job-store-persistence-plan.md`

### Persistence exception hierarchy

The implementation introduced:

```text
PersistenceError
├── RecordNotFoundError
├── InvalidJobTransitionError
└── CorruptRecordError
```

The exceptions distinguish:

- General SQLite storage failures
- Missing records
- Invalid job-state transitions
- Stored records that cannot be reconstructed safely

Original SQLite, parsing, or Pydantic exceptions are preserved through exception chaining where appropriate.

Public exception messages do not include:

- Extracted paper text
- Evidence excerpts
- Stored JSON payloads
- Prompts
- Model responses
- Credentials
- Database connection strings

### JobStore

`JobStore` supports:

- Creating pending jobs
- Retrieving jobs
- Requiring existing jobs
- Finding the latest active job for a paper
- Checking whether a succeeded job exists
- Marking jobs as running
- Marking jobs as succeeded
- Marking jobs as failed

The job state machine is:

```text
pending ───────────────▶ running ───────────────▶ succeeded
   │                       │
   └───────────────────────┴────────────────────▶ failed
```

Allowed transitions:

```text
pending → running
pending → failed
running → succeeded
running → failed
```

Rejected transitions include:

```text
pending → succeeded
running → running
succeeded → succeeded
failed → failed
succeeded → failed
failed → succeeded
all other transitions from terminal states
```

Transitions are strict and non-idempotent.

### Atomic job claiming

Job transitions use compare-and-set SQL.

Example:

```sql
UPDATE jobs
SET status = ?, updated_at = ?
WHERE job_id = ?
  AND status = ?
```

The affected row count is inspected.

When no row is updated:

1. The repository performs a safe lookup using the same connection.
2. A missing row produces `RecordNotFoundError`.
3. An existing row in the wrong state produces `InvalidJobTransitionError`.

An already-running job is never reported as successfully claimed by a second worker.

This prevents two workers from both believing that they own the same job.

### Safe failure codes

The `jobs.error` column stores only a validated machine-readable error code.

Accepted values follow a bounded pattern equivalent to:

```text
^[a-z][a-z0-9_]{0,63}$
```

Example codes include:

```text
server_restart
task_scheduling_failed
extraction_missing
map_generation_failed
llm_provider_error
persistence_error
```

The persistence layer does not store raw exception messages, provider responses, paper content, or prompts.

### UTC timestamp validation

The `Job` model was updated to require timezone-aware UTC timestamps.

The implementation rejects:

- Naive timestamps
- Non-UTC timestamps
- Malformed stored timestamp values

Job creation calls the injected clock once:

```python
now = clock()
created_at = now
updated_at = now
```

Each transition calls the clock once for its updated timestamp.

Tests use fixed clocks and do not depend on wall-clock timing.

### Corrupt job-row handling

Stored job rows are reconstructed through a protected conversion path.

The repository catches stored-data failures such as:

- Invalid job status values
- Invalid ISO-8601 timestamps
- Naive stored timestamps
- Non-UTC stored timestamps
- Pydantic validation failures
- Unexpected stored value types

These failures are converted into:

```text
CorruptRecordError
```

The original exception is preserved as `__cause__`.

Public errors identify only the affected job ID and do not expose the corrupt stored values.

### ExtractionStore

`ExtractionStore` supports:

- Saving or replacing an extraction
- Retrieving an extraction
- Requiring an existing extraction
- Checking whether an extraction exists

The table stores:

```text
paper_id
filename
chunks_json
```

Only the validated `list[Chunk]` is serialized into `chunks_json`.

The repository reconstructs an `ExtractionResult` using:

- `paper_id` from the database row
- `filename` from the database row
- Validated chunks decoded from `chunks_json`

This avoids duplicating the full `ExtractionResult` inside the JSON column.

Upserts use:

```sql
INSERT ... ON CONFLICT(paper_id) DO UPDATE
```

Repeated saves atomically replace the previous filename and chunk list.

### ResearchMapStore

`ResearchMapStore` supports:

- Saving or replacing a research map
- Retrieving a research map
- Requiring an existing map
- Checking whether a map exists

The complete validated `ResearchMap` is serialized into `map_json`.

When reading a map, the repository verifies:

```text
decoded ResearchMap.paper_id == database row paper_id
```

A mismatch raises `CorruptRecordError`.

All findings, evidence records, confidence values, limitations, and the fixed disclaimer survive round-trip persistence.

### Serialization

The repositories use Pydantic v2 serialization and validation.

Extraction chunks use a safe typed adapter for:

```text
list[Chunk]
```

Research maps use:

```python
research_map.model_dump_json()
ResearchMap.model_validate_json(...)
```

The implementation does not use:

- `pickle`
- `eval()`
- Unsafe object decoding
- Raw JSON string equality as a correctness check

Malformed or schema-invalid stored JSON raises `CorruptRecordError`.

### Connection ownership

All three repositories support:

- Repository-owned connections
- Caller-supplied connections

For repository-owned connections, the repository:

1. Opens the connection
2. Begins the transaction
3. Executes the operation
4. Commits on success
5. Rolls back on failure
6. Closes the connection

For caller-supplied connections, the repository does not:

- Begin a transaction
- Commit
- Roll back
- Close the connection

The caller owns the complete transaction lifecycle.

All repositories accept an injectable connection factory for testability.

### Cross-repository transactions

The implementation supports one caller-owned SQLite transaction spanning:

- `JobStore`
- `ExtractionStore`
- `ResearchMapStore`

Tests verify:

- A successful caller-managed commit persists all records
- A caller-managed rollback removes all records
- A repository error does not automatically roll back the caller's transaction
- A shared caller-owned connection remains open across all repositories
- Job, extraction, and research-map records survive closing and reopening the database
- Failed jobs and safe failure codes survive reopening

No transaction is kept open during PDF extraction or model inference.

### Logging and privacy

Repositories may log safe metadata such as:

- Operation name
- Job ID
- Paper ID
- Status transition
- Row count
- Failure category

Repositories do not log:

- Chunk text
- Evidence excerpts
- Extraction JSON
- Research-map JSON
- Prompts
- Model responses
- Credentials
- Database connection strings
- Raw exceptions that may contain sensitive content

### Initial audit

**Bob mode:** Ask

Bob audited:

- Repository boundaries
- Job transition safety
- Compare-and-set behavior
- Timestamp validation
- Error-code storage
- Connection ownership
- Transaction ownership
- Pydantic serialization
- Corrupt-data behavior
- Test isolation
- Cross-repository integration
- Logging safety
- Scope compliance

The initial audit identified two critical issues:

1. Cross-repository transaction tests had not been implemented.
2. Corrupt stored job timestamps or statuses could escape as raw `ValueError` or Pydantic errors rather than `CorruptRecordError`.

The audit also identified:

- Misleading blank-ID test names
- Missing explicit rollback-on-write-failure tests for extraction and research-map upserts
- Weak connection-closure assertions
- A weak repository-owned commit test

The implementation was not approved for commit until the critical findings were corrected.

### Audit corrections

**Bob mode:** Agent

Bob applied targeted corrections that:

- Added `backend/tests/unit/test_repository_integration.py`
- Added caller-managed commit tests
- Added caller-managed rollback tests
- Added reopen persistence tests
- Added shared-connection lifecycle tests
- Added repository-error-without-caller-rollback tests
- Wrapped corrupt job reconstruction failures as `CorruptRecordError`
- Added malformed timestamp tests
- Added naive timestamp tests
- Added non-UTC timestamp tests
- Added invalid stored-status tests
- Verified original exceptions are preserved as `__cause__`
- Renamed misleading blank-ID tests
- Added forced SQLite write-failure rollback tests
- Strengthened repository-owned commit verification
- Strengthened connection-closure tests using injected factories where practical

### Verification

The developer independently ran:

```powershell
python -m pip check
python -m pytest backend/tests --collect-only -q
python -m pytest backend/tests -v
git diff --check
```

Final verified results:

```text
Backend tests collected: 330
Backend tests passed: 330
Failures: 0
Errors: 0
Warnings: 5
pip check: PASS
git diff --check: PASS
```

Before the audit corrections, the verified suite contained:

```text
314 tests collected
314 tests passed
5 third-party warnings
```

The audit corrections added additional corruption, rollback, and cross-repository integration tests. The final post-correction total must be taken directly from pytest collection.

The warnings were third-party PyMuPDF/SWIG deprecation warnings and did not originate from PaperScape code.

### Scope confirmation

The implementation did not add:

- FastAPI routes
- Upload endpoints
- Background tasks
- Worker functions
- Job polling endpoints
- Automatic extraction execution
- Automatic research-map generation
- Live watsonx calls
- Flutter integration
- Celery
- Redis
- Alembic
- Authentication
- Multi-user ownership
- Job cancellation
- Progress percentages
- File storage
- Streaming

### Bob contribution

IBM Bob was used to:

- Inspect the existing SQLite schema
- Create the repository implementation plan
- Revise the state machine and transaction design
- Implement the persistence exception hierarchy
- Implement `JobStore`
- Implement `ExtractionStore`
- Implement `ResearchMapStore`
- Implement strict compare-and-set transitions
- Add UTC timestamp validation
- Add Pydantic serialization and reconstruction
- Generate repository unit tests
- Audit the implementation
- Identify missing transaction and corruption tests
- Apply targeted audit corrections
- Update persistence documentation
- Report verification results

### Human contribution

The developer:

- Defined the persistence-layer scope
- Reviewed Bob's initial plan
- Required strict non-idempotent job transitions
- Required `pending → failed`
- Required safe failure codes only
- Required caller-owned transaction semantics
- Required connection-factory injection
- Required UTC timestamp enforcement
- Required schema-aligned extraction serialization
- Required research-map paper-ID integrity checks
- Required deterministic job-claim tests
- Reviewed the initial implementation report
- Identified the test-count discrepancy
- Requested the Ask-mode audit
- Required all critical audit findings to be corrected
- Independently ran dependency checks and the full test suite
- Approved the final implementation

### Outcome

PaperScape gained a safe and testable SQLite persistence layer.

The completed repositories provide:

- Durable job lifecycle records
- Atomic job claims and transitions
- Prevention of duplicate worker claims
- Safe machine-readable failure codes
- Extraction round-trip persistence
- Research-map round-trip persistence
- Corrupt-record detection
- Explicit connection ownership
- Explicit transaction ownership
- Cross-repository caller-managed transactions
- Complete offline testing with temporary databases

The persistence layer is ready to support:

- Background job orchestration
- PDF upload endpoints
- Research-map job creation
- Job-status polling
- Research-map retrieval

## Sub-task 7 — Background Research-Map Orchestration and Vertical-Slice API

**Status:** Completed after audit corrections  
**Branch:** `feat/background-jobs-api`  
**Implementation commit:** `<2dafddc>`

### Objective

Implement the complete PaperScape backend vertical slice:

1. Upload one selectable-text PDF.
2. Extract page-aware chunks.
3. Persist the extraction.
4. Create an asynchronous research-map job.
5. Run grounded research-map generation through FastAPI background execution.
6. Persist the generated `ResearchMap`.
7. Poll the job status.
8. Retrieve the completed research map.

The implementation needed to integrate the existing:

- `ExtractionService`
- `LLMProvider`
- `WatsonxProvider`
- `ResearchMapService`
- `JobStore`
- `ExtractionStore`
- `ResearchMapStore`

Route handlers were required to orchestrate these components without duplicating extraction, grounding, inference, or persistence logic.

### IBM Bob workflow

#### Planning

**Bob mode:** Plan

Bob reviewed:

- `AGENTS.md`
- `docs/product-spec.md`
- `docs/vertical-slice-plan.md`
- `docs/data-model.md`
- `docs/bob-usage-log.md`
- The FastAPI application factory
- Settings and database initialization
- Paper, job, and research-map models
- Extraction, provider, and research-map services
- SQLite repositories
- Existing API and unit tests
- Environment configuration

Bob created:

- `docs/subtask-7-background-jobs-api-plan.md`

The plan covered:

- Endpoint contracts
- Multipart PDF validation
- Upload-size enforcement
- Paper-ID generation
- Application dependency injection
- Service-container construction
- Background job orchestration
- Job failure-code mapping
- Duplicate-job behavior
- Transaction boundaries
- Partial-failure recovery
- Startup stale-job recovery
- API error responses
- Offline API and runner tests

### Human review and plan corrections

The developer reviewed the first plan and required several architecture and safety corrections before implementation.

The final approved design required:

1. Reading only the uploaded file bytes from `UploadFile`.
2. Validating `file.content_type`, not the multipart request media type.
3. Reading at most `upload_max_bytes + 1`.
4. Closing `UploadFile` on every success and failure path.
5. Pinning `python-multipart`.
6. Returning HTTP 503 before job creation when generation capability is unavailable.
7. Preventing a duplicate runner from failing another runner's active job.
8. Using the `Job` returned by `mark_running()`.
9. Requiring the latest job—not any historical job—to be succeeded before serving a research map.
10. Protecting active-job lookup and creation with an in-process lock.
11. Resetting both pending and running jobs after process restart.
12. Supporting injection of a test `ServiceContainer` through `create_app()`.
13. Using temporary file-backed SQLite databases in tests.
14. Running synchronous extraction and persistence outside the async event loop.
15. Marking scheduling failures with `task_scheduling_failed`.
16. Avoiding unsupported claims about Starlette's multipart spooling behavior.
17. Keeping the usage-log update separate from the implementation commit.

Bob revised the implementation plan to incorporate these requirements.

### Implementation

**Bob mode:** Agent

Bob created:

- `backend/app/dependencies.py`
- `backend/app/services/research_map_job_runner.py`
- `backend/app/routers/papers.py`
- `backend/app/routers/jobs.py`
- `backend/tests/unit/test_research_map_job_runner.py`
- `backend/tests/unit/test_dependencies.py`
- `backend/tests/api/test_papers.py`
- `backend/tests/api/test_jobs.py`
- `docs/subtask-7-background-jobs-api-plan.md`

Bob modified:

- `backend/app/main.py`
- `backend/app/database.py`
- `backend/app/repositories/job_store.py`
- `backend/app/routers/__init__.py`
- `backend/requirements.txt`
- `backend/tests/unit/test_database.py`
- `backend/tests/unit/test_job_store.py`
- `backend/tests/api/test_health.py`
- `docs/data-model.md`

The watsonx settings already existed in `Settings`; they were not introduced by this sub-task.

### Endpoint implementation

The following routes were added under `/api/v1`.

#### Upload and extract a paper

```text
POST /api/v1/papers
```

Successful response:

```text
HTTP 201 Created
```

The endpoint:

1. Validates the uploaded filename.
2. Validates `UploadFile.content_type`.
3. Reads at most the configured limit plus one byte.
4. Rejects empty uploads.
5. Rejects oversized uploads.
6. Performs a lightweight PDF-signature check.
7. Generates and validates an application-owned paper ID.
8. Passes the exact uploaded bytes to `ExtractionService`.
9. Persists the resulting `ExtractionResult`.
10. Returns `UploadResponse`.

Paper IDs are not derived from filenames.

The endpoint uses `run_in_threadpool()` for blocking extraction and persistence work.

PaperScape does not deliberately persist or manage the uploaded PDF as a file. Starlette may internally spool multipart uploads.

#### Create a research-map job

```text
POST /api/v1/papers/{paper_id}/research-map-jobs
```

Successful response:

```text
HTTP 202 Accepted
```

The endpoint:

1. Validates the paper identifier.
2. Verifies that a persisted extraction exists.
3. Verifies that generation capability is configured.
4. Checks whether a pending or running job already exists.
5. Returns the existing active job for idempotent retries.
6. Creates a new pending job when no active job exists.
7. Registers background execution.
8. Returns `JobCreateResponse`.

A previous succeeded or failed job does not block explicit regeneration.

When no generation capability is available, the endpoint returns:

```text
HTTP 503
generation_unavailable
```

No pending job is created in this case.

#### Poll a job

```text
GET /api/v1/jobs/{job_id}
```

The endpoint returns:

- Pending jobs
- Running jobs
- Succeeded jobs
- Failed jobs with safe machine-readable error codes

Unknown jobs return HTTP 404.

Raw database, SDK, and domain exceptions are not exposed.

#### Retrieve a research map

```text
GET /api/v1/papers/{paper_id}/research-map
```

The endpoint returns a persisted `ResearchMap` only when:

1. The latest job for the paper exists.
2. The latest job status is `succeeded`.
3. A persisted research map exists.

A map is hidden when the latest job is:

- Pending
- Running
- Failed

This prevents an older succeeded job from exposing a map written by a newer failed or incomplete regeneration attempt.

Retrieval performs no model inference.

### Application service container

Bob implemented an explicit `ServiceContainer` attached to `app.state`.

The container provides:

- `Settings`
- `ExtractionService`
- `JobStore`
- `ExtractionStore`
- `ResearchMapStore`
- Paper-ID factory
- In-process job-creation lock
- Lazy job-runner factory

The application factory accepts an injected container:

```python
create_app(
    settings=None,
    *,
    container=None,
)
```

This enables API tests to construct a deterministic application with:

- Temporary SQLite storage
- Fake extraction services
- Fake background runners
- Fake model providers
- Deterministic identifiers
- No network access

The supplied container is attached before lifespan execution.

The lifespan initializes the database but does not replace a test-supplied container.

### Lazy watsonx construction

The initial implementation conditionally constructed `WatsonxProvider` while building the application container.

An Ask-mode audit demonstrated that the installed IBM SDK could attempt IAM authentication during provider construction, even when validation was expected to be disabled.

This caused importing `app.main` from the repository root to attempt a live request to:

```text
https://iam.cloud.ibm.com
```

Bob corrected this by making provider and runner construction genuinely lazy.

The final design does not construct `WatsonxProvider` during:

- `app.main` import
- `create_app()`
- Lifespan startup
- Health requests
- PDF uploads
- Job polling
- Research-map retrieval

Provider construction occurs only when a scheduled research-map job begins execution.

Where supported by the IBM SDK, the underlying inference constructor receives:

```python
validate=False
```

Lazy construction remains the primary import and network-safety boundary because SDK validation flags alone are not treated as a guarantee that every SDK version avoids authentication behavior.

### Background job orchestration

`ResearchMapJobRunner` is a synchronous orchestration service designed for FastAPI background execution.

Its successful sequence is:

```text
mark job running
→ load persisted extraction
→ generate grounded research map
→ persist research map
→ mark job succeeded
```

The runner uses the `Job` returned by:

```python
job_store.mark_running(job_id)
```

It does not perform an unnecessary second job lookup before loading the extraction.

### Safe job claiming

If `mark_running()` raises:

- `RecordNotFoundError`
- `InvalidJobTransitionError`

the runner logs safe metadata and returns.

It does not call `mark_failed()` after an unsuccessful claim.

This prevents a duplicate runner from changing another runner's legitimate running job to failed.

Only failures occurring after a successful claim may trigger best-effort failure handling.

### Failure-code mapping

The background runner maps failures to safe machine-readable codes.

```text
extraction_missing
map_generation_failed
llm_provider_error
persistence_error
unexpected_error
task_scheduling_failed
server_restart
```

The runner never persists:

- Raw exception messages
- SDK response bodies
- Credentials
- Paper content
- Evidence excerpts
- Prompt text
- Model output
- Stack traces

#### Extraction failure

A missing extraction produces:

```text
extraction_missing
```

#### Grounding failure

`MapGenerationError` produces:

```text
map_generation_failed
```

#### Provider failure

`LLMProviderError`, including provider-construction or credential failures during actual background execution, produces:

```text
llm_provider_error
```

#### Persistence failure

Repository failures produce:

```text
persistence_error
```

#### Unexpected failure

Unexpected exceptions produce:

```text
unexpected_error
```

### Scheduling failure

If background-task registration fails after a pending job has been created:

1. The endpoint attempts `pending → failed`.
2. The persisted error code is:

```text
task_scheduling_failed
```

3. The endpoint returns a safe HTTP 500 response.
4. The job is not left indefinitely pending.

### Duplicate-job protection

The endpoint uses an in-process lock around:

```text
active-job lookup
→ job creation
```

The lock is released before:

- Background-task registration
- Job execution
- Model generation
- Any long-running work

Concurrent requests for the same paper within one application process result in:

- One active job
- One background task
- Both requests receiving the same active job ID

This lock does not provide protection across multiple application processes. Distributed coordination was intentionally excluded from the hackathon MVP.

### Transaction boundaries

No SQLite transaction remains open during:

- PDF extraction
- Prompt construction
- Initial model generation
- Corrective generation
- Other watsonx inference

Repository operations use short, independent transactions.

The job-runner sequence is:

```text
mark_running transaction
→ extraction read
→ no database transaction during inference
→ research-map save transaction
→ mark_succeeded transaction
```

### Partial-failure recovery

A possible partial failure is:

```text
research map saved
→ mark_succeeded fails
```

The selected MVP policy is:

1. Leave the persisted map in SQLite.
2. Attempt to mark the job failed with `persistence_error`.
3. Hide the map because the latest job is not succeeded.
4. Allow a later regeneration request to overwrite the hidden map.
5. Use startup recovery if the job remains running.

This avoids holding a database transaction across model inference.

### Startup recovery

FastAPI `BackgroundTasks` are not durable across application restarts.

The database initialization process therefore converts stale jobs in either state:

```text
pending
running
```

to:

```text
status = failed
error = server_restart
```

Succeeded and failed jobs remain unchanged.

This prevents jobs from remaining permanently pending after a process exits before background execution begins.

### Upload validation

The upload endpoint validates:

- Nonblank filename
- File-level PDF media type
- Configured byte limit
- Empty uploads
- Lightweight PDF signature
- Generated paper identifier

Unsupported file media types return:

```text
HTTP 415
unsupported_media_type
```

Oversized uploads return:

```text
HTTP 413
upload_too_large
```

Extraction failures return a curated response rather than raw parser or validation text.

An extraction `ValueError` is mapped to a static application-controlled message such as:

```text
The uploaded PDF could not be processed.
```

The response does not contain:

- `str(exc)`
- Local file paths
- Filenames
- File bytes
- Extracted text
- Parser internals
- Library names
- Credentials
- Stack traces

`UploadFile.close()` is called through a complete route-level `finally` path, including:

- Success
- Blank filename
- Unsupported media type
- Empty upload
- Oversized upload
- Signature rejection
- Extraction failure
- Persistence failure
- Unexpected failure

### API error contract

API errors use a consistent safe structure:

```json
{
  "detail": {
    "code": "snake_case_code",
    "message": "Application-controlled message"
  }
}
```

Examples include:

```text
invalid_upload
unsupported_media_type
upload_too_large
extraction_failed
paper_not_found
job_not_found
map_not_found
generation_unavailable
task_scheduling_failed
persistence_error
internal_error
```

Raw domain, SQLite, SDK, validation, and parser errors are not included in API responses.

### First implementation audit

**Bob mode:** Ask

Bob audited:

- App-factory construction
- Dependency injection
- Provider lifecycle
- Multipart upload behavior
- File closure
- Upload-size enforcement
- Paper-ID generation
- Duplicate-job scheduling
- Scheduling failure
- Job-runner claim behavior
- Error-code mapping
- Transaction boundaries
- Startup recovery
- Partial-failure handling
- Map-retrieval eligibility
- Test isolation
- Scope compliance

The initial audit identified a critical problem:

> Importing `app.main` could instantiate `WatsonxProvider` and trigger live IBM IAM authentication when local watsonx credentials were present.

The audit also identified:

- Unsupported uploads returned HTTP 400 instead of 415.
- `UploadFile` was not closed on validation failures occurring before file reading.
- Generated paper IDs were not explicitly validated.
- Scheduling-failure behavior lacked direct tests.
- Concurrent duplicate-request protection lacked direct tests.
- Upload and retrieval tests were weaker than the plan.
- Implementation-report descriptions contained minor inaccuracies.

The implementation was not approved for commit.

### First audit correction pass

**Bob mode:** Agent

Bob applied corrections that:

- Deferred provider construction until background execution.
- Added import and network-safety regression tests.
- Changed unsupported file media type responses to HTTP 415.
- Added complete upload-file closure handling.
- Validated generated paper IDs.
- Added scheduling-failure tests.
- Added concurrent duplicate-request tests.
- Added task-lock scope tests.
- Strengthened upload boundary tests.
- Strengthened exact-byte extraction tests.
- Strengthened safe persistence-error tests.
- Strengthened retrieval eligibility tests.
- Added provenance and no-inference retrieval tests.
- Corrected implementation-report terminology.

### Second implementation audit

**Bob mode:** Ask

The second audit reported:

- No critical findings.
- Genuine lazy provider construction was in place.
- Importing `app.main` no longer created a provider or network request.
- Upload, scheduling, concurrency, runner claim, retrieval, and startup recovery behavior aligned with the approved architecture.

Two final issues remained:

1. The audit could not initially confirm that the actual IBM SDK constructor received `validate=False`.
2. Upload handling exposed `str(exc)` for an extraction `ValueError`.

The implementation remained unapproved until these were reconciled.

### Final audit correction pass

**Bob mode:** Agent

Bob traced the complete SDK construction path:

```text
job_runner_factory
→ WatsonxProvider
→ SDK client factory
→ IBM ModelInference constructor
```

Bob then either confirmed or added `validate=False` at the actual supported SDK constructor boundary and added a focused regression test.

Bob also replaced raw upload `ValueError` text with a curated static response and added a regression test containing sensitive sentinel values.

The test verified that the following did not appear in responses, headers, or logs:

```text
C:\private\research\secret-paper.pdf
API_KEY_SENTINEL
PAPER_TEXT_SENTINEL
```

### Verification

The developer and Bob ran verification from the repository root using the backend virtual environment.

Commands:

```powershell
backend\.venv\Scripts\python.exe -m pip check
backend\.venv\Scripts\python.exe -m pytest backend\tests --collect-only -q
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
git diff --check
```

Pre-final-correction verified results were:

```text
420 tests collected
420 tests passed
0 failures
0 errors
5 warnings
pip check: PASS
git diff --check: PASS
```

Final verified results:

```text
Backend tests collected: 421
Backend tests passed: 421
Failures: 0
Errors: 0
Warnings: 5
pip check: PASS
git diff --check: PASS
Import/network safety: PASS
Upload error sanitization: PASS
```

The warnings were third-party PyMuPDF/SWIG deprecation warnings involving:

```text
SwigPyPacked
SwigPyObject
swigvarlink
```

They did not originate from PaperScape code.

### Scope confirmation

The implementation did not add:

- Celery
- Redis
- Distributed workers
- Distributed locks
- Job cancellation
- Progress percentages
- WebSockets
- Server-sent events
- Authentication
- Multi-user ownership
- Original-PDF storage
- OCR
- Multi-paper comparison
- Audience adaptation
- Visual abstracts
- Narration
- Flutter UI
- Deployment infrastructure
- Live watsonx tests in the default suite

### Bob contribution

IBM Bob was used to:

- Inspect the existing FastAPI application structure
- Create the Sub-task 7 implementation plan
- Revise multipart and background-task architecture
- Implement the application service container
- Implement lazy provider and runner construction
- Implement paper upload and extraction endpoints
- Implement research-map job creation
- Implement job polling
- Implement research-map retrieval
- Implement the background job runner
- Implement safe failure-code mapping
- Implement startup recovery
- Add latest-job repository queries
- Add in-process duplicate-request locking
- Add safe API error handling
- Add multipart upload validation
- Add paper-ID validation
- Generate unit and API tests
- Audit the implementation
- Identify import-time IBM IAM behavior
- Apply import/network-safety corrections
- Strengthen concurrency and scheduling tests
- Reconcile `validate=False`
- Remove raw extraction exception text
- Report final verification results

### Human contribution

The developer:

- Defined the vertical-slice endpoint requirements
- Reviewed Bob's first plan
- Required correct multipart handling
- Required hard upload-size enforcement
- Required safe `UploadFile` closure
- Required HTTP 415 for unsupported media
- Required application-owned paper IDs
- Required 503 before creating unavailable generation jobs
- Required safe duplicate-runner claim behavior
- Required latest-job map eligibility
- Required an in-process job-creation lock
- Required pending-job startup recovery
- Required injectable application containers
- Required no database transaction during inference
- Required safe scheduling-failure handling
- Required separate implementation and usage-log commits
- Requested multiple Ask-mode audits
- Required import and network safety
- Required direct concurrency and scheduling tests
- Required `validate=False` reconciliation
- Required curated upload errors
- Independently reviewed test totals and audit findings
- Approved the completed vertical-slice backend

### Outcome

PaperScape gained a complete backend vertical slice.

The completed backend now supports:

- Safe multipart PDF upload
- Synchronous page-aware PDF extraction
- Durable extraction persistence
- Asynchronous research-map job creation
- Idempotent duplicate active-job handling
- Background grounded research-map generation
- Durable job lifecycle persistence
- Safe machine-readable failure codes
- Job-status polling
- Latest-job-gated research-map retrieval
- Startup recovery for non-durable background tasks
- Lazy watsonx construction
- Import and network-safe default behavior
- Complete offline API and orchestration testing

The backend vertical slice is ready to support the next phase:

- Flutter PDF upload
- Job-status polling
- Research-map presentation
- User-visible loading and failure states

---

## Sub-task 8 — Flutter Web Vertical Slice

**Status:** Completed
**Branch:** `feat/flutter-vertical-slice`
**Disclaimer alignment commit:** `<fe7fe31>`
**Flutter vertical slice commit:** `<1876d56>`

### Objective

Implement the Flutter Web vertical slice for PaperScape so a user can select a
PDF, upload it to the backend, create and poll a research-map job, and view the
grounded research map with findings, evidence, limitations, and the fixed
expert-review disclaimer.

The frontend needed to:

- Keep file picking behind a `PdfPicker` abstraction.
- Keep API calls behind `PaperScapeApiClient`.
- Use Flutter `ChangeNotifier` rather than adding a state-management framework.
- Avoid `dart:html` and direct browser APIs.
- Avoid exposing backend secrets or watsonx configuration.
- Upload PDFs as multipart form data with field name `file`.
- Encode paper and job identifiers as safe route path segments.
- Poll jobs safely with injectable timers and no real waits in tests.
- Reject stale async completions from older workflows.
- Render exactly three findings with confidence labels and selectable evidence.
- Render page provenance, chunk IDs, limitations, and the canonical disclaimer.

### Human decisions and review

The developer directed the Sub-task 8 scope and reviewed the plan, audits, and
correction passes.

Human decisions included:

- Approving the Flutter Web vertical-slice scope rather than adding unrelated
  frontend frameworks or backend behavior.
- Requiring `FilePicker` to remain behind `PdfPicker`.
- Requiring `ChangeNotifier` as the only state-management approach.
- Requiring API access through `PaperScapeApiClient`.
- Requiring direct `http_parser` declaration only for the multipart PDF part
  `Content-Type`.
- Requiring deterministic polling tests using an injectable `TimerFactory` and
  fake clock.
- Requiring stale-response protection for upload, job creation, polling, and
  map loading.
- Requiring operation-specific retry behavior rather than a generic restart.
- Requiring safe picker exception handling.
- Requiring responsive narrow-layout and full offline workflow coverage.
- Approving the canonical disclaimer alignment across product specification,
  backend model/service output, evaluation fixtures, and frontend validation.
- Explicitly approving the disclaimer alignment as a cross-layer contract
  correction rather than a frontend-only change.
- Directing that meaningful extra tests be preserved instead of reducing the
  suite to an arbitrary earlier count.

### Bob workflow

#### Planning

**Bob mode:** Plan

Bob performed Sub-task 8 planning in Plan mode and produced the Flutter vertical
slice plan:

- `docs/subtask-8-flutter-vertical-slice-plan.md`

The plan covered:

- Flutter application structure.
- Upload, job creation, polling, and research-map retrieval contracts.
- DTO parsing for upload, job, and research-map responses.
- Multipart upload behavior.
- Route-segment encoding behavior.
- Workflow state phases.
- Polling lifecycle safety.
- Responsive result rendering.
- Accessibility and privacy constraints.
- Offline test strategy.

#### Plan audit

**Bob mode:** Ask

Bob performed a plan audit in Ask mode before implementation. The audit checked
the proposed architecture against the product specification, data model,
backend API contracts, dependency constraints, privacy rules, and testability
requirements.

The plan audit emphasized:

- Keeping the frontend, document processing, retrieval, and inference concerns
  separated.
- Avoiding direct file-picker calls from widgets or controllers.
- Avoiding direct browser APIs and `dart:html`.
- Preserving page and chunk provenance in rendered output.
- Ensuring generated factual claims remained tied to backend evidence records.
- Avoiding live network calls, browser file dialogs, real polling waits, and
  watsonx credentials in Flutter tests.

#### Implementation

**Bob mode:** Agent

Bob implemented the Flutter Web vertical slice in Agent mode.

Bob-generated implementation included:

- Flutter app shell and local theme.
- Runtime app configuration for the backend API base URL.
- `SelectedPdf` domain object and validation helpers.
- `PdfPicker` abstraction and `FilePickerPdfPicker` adapter.
- Safe API exception and backend error-code mapping.
- DTOs for `UploadResponse`, `JobCreateResponse`, `JobStatusResponse`,
  `ResearchMap`, `Finding`, and `Evidence`.
- `PaperScapeApiClient` with multipart PDF upload and typed response decoding.
- `ResearchMapController` using `ChangeNotifier` and immutable state.
- Polling with an injectable `TimerFactory` and clock.
- Upload, job creation, polling, map loading, reset, dispose, and retry flows.
- Responsive UI for selection, processing, failures, and ready-state research
  maps.
- Selectable evidence excerpts with page and chunk provenance.

### Initial implementation and test-discovery findings

The initial Flutter implementation had only one smoke test. Later test
discovery confirmed that only two tests persisted in the relevant frontend test
tree at that point. This was insufficient for the release gate because the
workflow depended on multipart upload correctness, safe route construction,
polling lifecycle behavior, stale-response rejection, operation-specific retry,
and accessible rendering.

The developer directed Bob to expand the test suite rather than treat the smoke
coverage as adequate.

### Bob audit findings

**Bob mode:** Ask

Bob performed multiple release-gate audits and correction passes. Audit findings
included:

- The initial test coverage was far below the required behavior surface.
- API route tests mixed endpoint request assertions with an invalid response
  fixture, causing a research-map parse failure unrelated to route encoding.
- Several Completer-controlled tests accessed fake API completer collections
  before the controller had registered the async operation.
- The timeout retry path reused the original polling start timestamp and could
  immediately time out again.
- Picker/plugin exceptions were not converted into a curated safe state.
- Poll-overlap prevention needed an executable test that truly kept one poll
  unresolved while triggering another scheduled callback.
- Reset and dispose safety needed stronger in-flight completion coverage.
- Map-load retry and failed-job retry needed operation-specific proof.
- The canonical disclaimer value needed to remain identical across the product
  spec, backend, evaluation output, and frontend.

### Human-directed correction passes

**Bob mode:** Agent

The developer directed Bob through correction passes that repaired production
behavior and strengthened executable tests.

Corrections included:

- Multipart upload inspection proving:
  - HTTP method `POST`
  - multipart field name `file`
  - filename preservation
  - `application/pdf` media type
  - exact selected byte preservation
  - one file part
  - no JSON or base64 upload
  - no live network
- Safe route-segment encoding tests for UUIDs, spaces, slashes, query
  characters, fragments, percent input, and encoded-looking input.
- TimerFactory-based deterministic polling tests with no sleeps or real waits.
- Genuine poll-overlap prevention testing.
- Timeout retry behavior that reuses the same job ID and receives a fresh
  timeout window.
- Stale upload, job-creation, poll, and map response rejection.
- Reset safety covering selected PDF, byte reference, upload response, job ID,
  job status, map, error, generation invalidation, and in-flight completions.
- Dispose safety covering scheduled timers, timer callbacks, in-flight
  completions, listener notifications, and notify-after-dispose behavior.
- Operation-specific retry behavior:
  - failed upload retries the same selected PDF
  - failed job retry creates a new backend job for the same paper
  - polling transport retry continues the same job
  - map-load retry retrieves the same map without creating another generation
    job
- Safe picker exception handling that does not expose exception text, stack
  traces, browser paths, or plugin internals.
- Responsive narrow-layout widget testing with long wrapping evidence.
- Full offline workflow test from PDF selection through ready-state rendering.
- Canonical disclaimer alignment across product spec, backend public model,
  backend application-controlled service output, persistence/API tests,
  evaluation fixtures and expected output, frontend DTO validation, frontend
  tests, and rendered UI.

Flutter tests deliberately used no:

- Live network
- Browser file dialogs
- Real polling waits
- `Future.delayed` polling recursion
- watsonx credentials

### Final test expansion

The frontend test suite was expanded to 42 passing tests covering:

- API error sanitization.
- Multipart upload request inspection.
- Route-segment encoding safety.
- Upload, job, and research-map DTO parsing.
- Selected PDF validation.
- Workflow state transitions.
- Polling success, timeout, retry, and overlap behavior.
- Stale upload, job, poll, and map completions.
- Reset and dispose safety.
- Operation-specific retry behavior.
- Picker exception safety.
- Responsive UI rendering.
- Full offline workflow rendering.

### Verification

Final verification results:

```text
Backend tests: 422 passed, 5 existing warnings
Offline evaluation: PASS
Frontend tests: 42 passed
flutter analyze: PASS
flutter build web: PASS
git diff --check: PASS
```

The backend warnings were existing third-party PyMuPDF/SWIG deprecation warnings
and did not originate from PaperScape application code.

### Bob contribution

IBM Bob was used to:

- Create the Sub-task 8 Flutter vertical-slice plan.
- Audit the plan in Ask mode.
- Implement the Flutter Web vertical slice in Agent mode.
- Generate DTO, API-client, controller, widget, and workflow tests.
- Run multiple release-gate audits.
- Identify test-coverage gaps after initial smoke-test-only coverage.
- Identify malformed route-test fixtures.
- Identify incorrect asynchronous fake assumptions.
- Identify timeout retry behavior that did not rebase the timeout window.
- Implement production fixes.
- Repair deterministic Completer-controlled tests.
- Expand frontend tests to 42 passing tests.
- Run backend, frontend, evaluation, formatting, analysis, build, and diff
  verification commands.

### Human contribution

The developer:

- Defined the Sub-task 8 frontend acceptance criteria.
- Required the Bob Plan-mode implementation plan.
- Requested the Ask-mode plan audit.
- Reviewed the initial implementation and release-gate audit findings.
- Identified that the initial smoke-test coverage was inadequate.
- Directed Bob not to reduce tests to an arbitrary earlier count.
- Approved the canonical disclaimer alignment as a cross-layer contract fix.
- Directed multiple correction passes.
- Required tests to genuinely prove stale-response, polling, retry, reset, and
  dispose behavior.
- Required no live network, browser dialogs, real polling waits, or watsonx
  credentials in Flutter tests.
- Reviewed the final verification results.

### Outcome

PaperScape gained a tested Flutter Web vertical slice that connects to the
backend vertical slice without exposing credentials or backend internals.

The completed frontend now supports:

- PDF selection behind a domain picker abstraction.
- Safe client-side PDF validation.
- Multipart upload to the backend.
- Research-map job creation.
- Safe deterministic polling.
- Timeout, retry, reset, and dispose behavior.
- Stale-response rejection across all async workflow stages.
- Evidence-backed research-map presentation.
- Responsive narrow-layout rendering.
- Exact disclaimer validation and display.

The Flutter vertical slice is ready for commit after the recorded disclaimer
alignment and vertical-slice commits are assigned their final hashes.

## Sub-task 9 — Frontend Polling and Research Map Screens

**Status:** Completed as part of the expanded Sub-task 8 implementation  
**Separate implementation commit:** None  
**Primary implementation commit:** `1876d56` — `Add Flutter research map vertical slice`  
**Usage-log commit:** `627028d` — `Document Sub-task 8 Bob usage`  
**Merged through:** `74cefa3` — Merge of `feat/flutter-vertical-slice`

### Scope reconciliation

The original vertical-slice plan defined Sub-task 9 as the frontend work required to:

- create a research-map generation job;
- poll the job until completion;
- display pending, running, failed, and succeeded states;
- retrieve the persisted research map;
- render the research question;
- render exactly three findings;
- display confidence levels;
- display grounded evidence excerpts;
- display one-based page provenance and chunk IDs;
- display limitations;
- display the canonical AI disclaimer;
- expose appropriate retry and start-over actions.

During implementation, this scope was incorporated into an expanded Sub-task 8 so that the complete Flutter vertical slice could be built and verified as one coherent workflow.

No duplicate Sub-task 9 screen, controller, API client, polling service, or DTO layer was subsequently created.

### Bob usage

#### Plan mode

Bob was used to inspect the existing Flutter scaffold and design a bounded frontend architecture covering:

- compile-time backend configuration through `PAPERSCAPE_API_BASE_URL`;
- API DTOs aligned to the current FastAPI contracts;
- multipart PDF upload;
- research-map job creation;
- deterministic polling;
- job timeout handling;
- map retrieval;
- controller state transitions;
- operation-specific retry behavior;
- stale asynchronous-operation guards;
- responsive result presentation;
- deterministic controller and widget testing.

The plan separated responsibilities into:

- application configuration;
- API client and DTOs;
- PDF selection abstraction;
- controller/state workflow;
- presentation widgets;
- fake scheduler support for tests.

#### Agent mode

Bob implemented the Flutter Web vertical slice, including:

- `PaperScapeApiClient`;
- multipart upload using field name `file`;
- `PdfPicker` abstraction;
- `ResearchMapController`;
- deterministic `TimerFactory`;
- explicit workflow phases;
- job creation and polling;
- map retrieval;
- timeout and retry handling;
- stale upload/job/poll/map response protection;
- route-safe identifier encoding;
- picker exception handling;
- reset and disposal safety;
- responsive research-map presentation;
- selectable evidence excerpts;
- confidence indicators;
- page and chunk provenance;
- limitations;
- canonical disclaimer rendering.

The final frontend API contracts were:

- `POST /api/v1/papers`
- `POST /api/v1/papers/{paper_id}/research-map-jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/papers/{paper_id}/research-map`

The browser-visible backend configuration remained:

`PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1`

### Ask-mode audits and corrections

Bob Ask mode was used repeatedly to audit the implementation against the backend and product contracts.

The audits identified and helped correct:

- an outdated disclaimer value across frontend, backend, tests, documentation, and eval fixtures;
- timeout retry behavior that did not initially rebase the polling timeout window;
- missing or incomplete stale-operation coverage;
- missing retry-path coverage;
- route-encoding edge cases;
- picker exception handling;
- map-load retry semantics;
- reset and disposal behavior;
- duplicated or stale acceptance criteria from the original vertical-slice plan.

The canonical disclaimer was aligned across all layers to:

> This AI-generated explanation is grounded in the uploaded document but does not replace expert review.

### Verified behavior

The completed Sub-task 9 functionality proved:

- upload-to-map workflow;
- polling without overlapping requests;
- timeout followed by retry of the same job;
- failed-job retry through creation of a new job for the same paper;
- map-load retry without creating a new job;
- stale upload responses ignored;
- stale job responses ignored;
- stale polling responses ignored;
- stale map responses ignored;
- safe route construction for identifiers containing reserved characters;
- picker exceptions converted into safe UI errors;
- reset clears current state;
- disposed controllers perform no later notifications or API work;
- evidence remains selectable;
- provenance remains visible;
- the canonical disclaimer is enforced.

### Verification baseline at completion

- Backend tests: `422 passed`
- Frontend tests: `42 passed`
- `flutter analyze`: passed
- Flutter Web release build: passed
- Offline ResearchMap evaluation: passed
- `git diff --check`: passed

### Outcome

The original Sub-task 9 was fully completed inside the expanded Sub-task 8.

This was later documented explicitly in `docs/vertical-slice-plan.md` during Sub-task 10 so that the historical task definition remains visible without implying that duplicate frontend work is still pending.


---

## Sub-task 10 — Docker Compose and End-to-End Vertical-Slice Validation

**Status:** Implemented and runtime-validated  
**Plan document:** `docs/subtask-10-docker-compose-e2e-plan.md`  
**Plan commit:** `<659aac1>`  
**Implementation commit:** `<0f41eb5>`  
**Bob usage-log commit:** `<caef33d>`

### Objective

Sub-task 10 containerized and validated the existing PaperScape vertical slice:

selectable-text PDF  
→ Flutter Web upload  
→ FastAPI extraction  
→ persisted `ExtractionResult`  
→ research-map job creation  
→ background processing  
→ polling  
→ persisted `ResearchMap`  
→ Flutter result display

The implementation was intentionally limited to:

- one backend container;
- one frontend container;
- SQLite persistence through a named volume;
- FastAPI `BackgroundTasks`;
- an unprivileged nginx runtime;
- deterministic backend integration tests;
- credential-free Docker smoke validation;
- optional manual live-watsonx validation.

The task did not introduce Redis, Celery, PostgreSQL, a separate worker, authentication, OCR, Kubernetes, Terraform, CI/CD, cloud deployment, or production TLS.

### Bob usage

#### Plan mode

Bob inspected the repository and produced:

`docs/subtask-10-docker-compose-e2e-plan.md`

The plan covered:

- current Docker and Compose state;
- backend image design;
- Flutter Web multi-stage build;
- unprivileged nginx runtime;
- browser-visible API configuration;
- CORS;
- SQLite volume persistence;
- credential handling;
- deterministic integration testing;
- container smoke validation;
- browser walkthrough;
- acceptance-criteria reconciliation;
- implementation order;
- rollback strategy.

The original plan initially proposed several assumptions that were subsequently tightened through audit, including:

- Python runtime version;
- credential-free startup behavior;
- Granite configuration defaults;
- fake-provider test design;
- SQLite parent-directory ownership;
- nginx healthcheck tooling;
- exact Windows verification commands.

#### Ask-mode plan audit

Bob Ask mode audited the proposed plan against the current repository.

The audit confirmed:

- Python `3.12.10` was the established backend baseline;
- `python:3.12.10-slim-bookworm` existed;
- `ghcr.io/cirruslabs/flutter:3.24.5` existed;
- `nginxinc/nginx-unprivileged:1.27-alpine` existed;
- missing watsonx credentials were accepted by `Settings`;
- provider construction was lazy;
- credential-free job creation should return `generation_unavailable`;
- `sqlite:////data/paperscape.db` resolved to `/data/paperscape.db`;
- the integration test could use a fake `LLMProvider` with the real `ResearchMapService`;
- the selected failure path should persist `llm_provider_error`;
- failed map retrieval should return `map_not_found`.

The plan was corrected before implementation.

### Agent-mode implementation

Bob created:

- `backend/Dockerfile`
- `backend/.dockerignore`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/.dockerignore`
- `backend/tests/integration/test_pipeline.py`

Bob modified:

- `docker-compose.yml`
- `.env.example`
- `backend/.env.example`
- `frontend/README.md`
- `docs/vertical-slice-plan.md`

### Backend image

The backend image uses:

`python:3.12.10-slim-bookworm`

Recorded image digest:

`sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db`

The image:

- installs the pinned backend requirements;
- copies only the runtime application source;
- does not copy `.env`;
- does not copy the local virtual environment;
- creates the `paperscape` group and user;
- runs with UID/GID `10001:10001`;
- creates `/data`;
- runs Uvicorn with one worker;
- exposes port `8000`;
- uses no unnecessary system packages.

Runtime command:

`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1`

### Frontend image

The Flutter builder uses:

`ghcr.io/cirruslabs/flutter:3.24.5`

Recorded image digest:

`sha256:10e0449fb853a5826091cbea6ed215d260d76d37b11453149bead5b09b80fc64`

The image reported:

- Flutter `3.24.5`
- Dart `3.5.4`
- DevTools `2.37.3`

The runtime uses:

`nginxinc/nginx-unprivileged:1.27-alpine`

Recorded image digest:

`sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0`

The Flutter build receives only the non-secret compile-time value:

`PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1`

No watsonx credential, project ID, model configuration, or database value is passed into Flutter assets.

### Docker Compose topology

`docker-compose.yml` defines exactly two services:

- `backend`
- `frontend`

Backend behavior:

- host/container port: `8000:8000`;
- database URL: `sqlite:////data/paperscape.db`;
- persistent named volume mounted at `/data`;
- CORS origin: `http://localhost:8080`;
- Python-stdlib healthcheck on `/api/v1/health`;
- restart policy: `unless-stopped`.

Frontend behavior:

- host/container port: `8080:8080`;
- depends on a healthy backend;
- builds with `PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1`;
- healthcheck uses `/health`;
- restart policy: `unless-stopped`.

The browser calls `localhost:8000`, not the Compose service hostname, because the Flutter application executes in the user's browser.

### Compose credential handling

The root Compose configuration uses:

- `COMPOSE_WATSONX_API_KEY`
- `COMPOSE_WATSONX_PROJECT_ID`

These are mapped into the backend container as:

- `WATSONX_API_KEY`
- `WATSONX_PROJECT_ID`

This was introduced after `docker compose config` revealed that an existing root `.env` contained stale direct-development placeholder values under the normal `WATSONX_*` names.

The Compose-specific names prevent stale placeholder credentials from being forwarded accidentally.

Direct backend development continues to use the normal variables documented in `backend/.env.example`.

Compose does not currently expose a root `GRANITE_MODEL_ID` override and relies on the backend application's configured default.

### Integration test implementation

`backend/tests/integration/test_pipeline.py` adds two tests.

The test pipeline uses:

- a programmatically generated selectable-text PDF;
- temporary file-backed SQLite;
- real FastAPI routes;
- real `ExtractionService`;
- real `ExtractionStore`;
- real `JobStore`;
- real `ResearchMapStore`;
- real `ResearchMapService`;
- real `ResearchMapJobRunner`;
- real `run_research_map_job` background adapter;
- fake `LLMProvider` only;
- no network;
- no watsonx credentials;
- no sleeps;
- no committed binary fixture.

The happy path proves:

- PDF upload returns `201`;
- extraction is persisted;
- job creation returns `202`;
- FastAPI schedules the real background adapter;
- the real runner completes;
- job status becomes `succeeded`;
- the persisted map can be retrieved;
- exactly three findings are returned;
- each finding has grounded evidence;
- evidence references real extracted chunk IDs, pages, and excerpts;
- pages are one-based;
- limitations are non-empty;
- the canonical disclaimer is exact;
- the fake provider is called exactly once;
- no corrective generation retry occurs.

The failure path proves:

- the fake provider raises `LLMProviderError`;
- the real route-scheduled adapter executes;
- job status becomes `failed`;
- the safe persisted/public error is `llm_provider_error`;
- the raw provider message is not exposed;
- map retrieval returns `404`;
- the safe response code is `map_not_found`.

### Deterministic PDF generation

The integration test generates the PDF in memory using PyMuPDF.

The helper uses fixed:

- content;
- page dimensions;
- text coordinates;
- metadata;
- serialization settings;
- document-ID behavior.

Two independent calls return identical bytes.

Recorded SHA-256:

`03290709491d45c886992dd2f8bcd7135682bae107e8031a834a122b5f3593bf`

The PDF retains:

- a valid `%PDF-` header;
- selectable text;
- at least one page;
- at least one extraction chunk.

### Static audits and corrections

Bob Ask mode identified and helped correct:

- incomplete SQLite ignore patterns;
- lack of an explicit successful-provider call-count assertion;
- ambiguous Compose credential naming documentation;
- a no-op replacement of `run_research_map_job` in the initial integration test;
- nondeterministic PDF serialization;
- inaccurate root Compose documentation for `GRANITE_MODEL_ID`;
- missing Sub-task 10 test-baseline documentation.

The final integration tests no longer patch:

- `run_research_map_job`;
- `BackgroundTasks.add_task`;
- `ResearchMapJobRunner.run`;
- `ResearchMapService.generate`;
- repository methods.

No manual `runner.run()` call occurs after the job-creation request.

### nginx runtime issue and correction

The first frontend container build succeeded, but the container repeatedly exited with:

`unknown directive "8,}\.(js|css|png|jpg|jpeg|gif|svg|woff2?)$"`

The issue was traced to an unquoted nginx regular-expression location containing the `{8,}` quantifier.

Original form:

`location ~* ^/(assets|canvaskit)/.+\.[0-9a-f]{8,}\.(...)$`

Corrected form:

`location ~* "^/(assets|canvaskit)/.+\.[0-9a-f]{8,}\.(...)$"`

After correction:

- `nginx -t` passed;
- the frontend container became healthy;
- restart count remained `0`;
- `/health` returned `ok`;
- `/` returned HTTP `200`;
- `index.html` returned `Cache-Control: no-store`.

The nginx entrypoint message stating that it could not modify `default.conf` was determined to be harmless because the supplied configuration did not require the entrypoint's IPv6 rewrite.

### Docker runtime validation

Docker runtime validation confirmed:

- Docker Desktop Linux engine available;
- backend image built;
- frontend image built;
- backend container healthy;
- frontend container healthy;
- frontend restart count `0`;
- backend runs as UID/GID `10001:10001`;
- `/data` is writable;
- database path is `/data/paperscape.db`;
- SQLite journal mode is `wal`;
- backend health returns `{"status":"ok"}`;
- frontend health returns `ok`;
- frontend root returns HTTP `200`;
- nginx serves `index.html` with `Cache-Control: no-store`;
- no native-library import failure occurred;
- no SQLite permission error occurred;
- no credential was printed in logs.

### Credential-free smoke validation

A synthetic selectable-text PDF was uploaded to the containerized backend.

Result:

- HTTP status: `201 Created`
- filename: `paperscape-smoke.pdf`
- page count: `1`
- chunk count: `1`

A research-map generation request was then submitted without watsonx credentials.

Result:

- HTTP status: `503 Service Unavailable`
- response code: `generation_unavailable`
- jobs before request: `0`
- jobs after request: `0`

This confirmed that:

- application startup does not require watsonx credentials;
- upload and extraction remain available;
- provider construction remains unavailable safely;
- no pending job is created when generation cannot be configured.

### CORS validation

A browser-style preflight request from:

`http://localhost:8080`

returned:

- HTTP `200`;
- `Access-Control-Allow-Origin: http://localhost:8080`;
- `Access-Control-Allow-Credentials: true`;
- the expected allowed HTTP methods.

### SQLite volume persistence

Before normal Compose shutdown:

- extraction count: `1`

After:

- `docker compose down`
- `docker compose up -d --wait`

the extraction count remained:

- `1`

Both services returned healthy after recreation.

`docker compose down -v` was not used, so the named SQLite volume was preserved.

### Final verification baseline

Backend:

- `pip check`: passed
- tests collected: `424`
- tests passed: `424`
- Sub-task 10 integration tests: `2 passed`
- offline ResearchMap evaluation: passed

Frontend:

- `flutter pub get`: passed
- formatting check: passed
- `flutter analyze`: passed
- Flutter tests: `42 passed`
- Flutter Web release build: passed

Docker:

- `docker compose config`: passed
- backend image build: passed
- frontend image build: passed
- backend healthcheck: passed
- frontend healthcheck: passed
- nginx configuration test: passed
- credential-free smoke test: passed
- CORS test: passed
- named-volume persistence test: passed

Repository:

- `git diff --check`: passed
- no temporary smoke files remained
- no real credentials were present
- no production backend or Flutter application source was modified

### Bob contribution

Bob was used for:

- repository inspection;
- implementation planning;
- Dockerfile and Compose implementation;
- integration-test implementation;
- documentation updates;
- static code audits;
- environment-contract audits;
- security and secret-handling audits;
- integration-test realism audits;
- nginx failure diagnosis;
- targeted release-gate corrections;
- final verification planning.

The iterative Plan → Agent → Ask → Agent workflow was especially useful for catching issues that ordinary unit tests did not expose, including:

- browser-visible versus container-visible API URLs;
- stale credential interpolation;
- nginx regex parsing;
- fake-provider test realism;
- background-task adapter coverage;
- deterministic fixture generation;
- SQLite volume ownership;
- safe credential-free behavior.

### Human validation and decisions

Manual human actions remained necessary for:

- starting Docker Desktop;
- executing Docker pull/build/run commands;
- reviewing container logs;
- running the browser-facing smoke requests;
- verifying CORS headers;
- checking volume persistence;
- approving the Compose-specific credential naming;
- deciding not to introduce a production runtime fake-provider mode;
- confirming the nginx entrypoint warning was non-blocking;
- approving final commit boundaries.

### Outcome

Sub-task 10 produced a reproducible two-container local environment and a deterministic backend integration suite that validates the complete research-map pipeline without live watsonx access.

Successful map generation remains available as an optional manual test when valid backend-only watsonx credentials are supplied.

The default automated and credential-free workflows remain network-independent and safe.