# Sub-task 8 — Flutter Web Vertical-Slice UI Plan

## 1. Objective

Implement the first usable PaperScape Flutter Web flow without changing backend
contracts:

1. Select one PDF from the browser.
2. Validate the selected file at the UI boundary.
3. Upload exact PDF bytes to the FastAPI backend.
4. Display extracted paper metadata.
5. Create or reuse a research-map background job.
6. Poll the job until it succeeds, fails, times out, is reset, or the controller
   is disposed.
7. Retrieve the persisted `ResearchMap` after a succeeded job.
8. Display the research question, exactly three findings, evidence excerpts,
   page provenance, limitations, and disclaimer.
9. Support retry and starting over after failures.

This sub-task is frontend-only implementation work. It must not change backend
contracts unless a verified frontend-blocking backend defect is found.

---

## 2. Corrected Repository Assessment

### 2.1 Actual Flutter application directory

The Flutter application is under:

```text
frontend/
```

### 2.2 Current Flutter and Dart SDK constraints

From `frontend/pubspec.yaml`:

```yaml
environment:
  sdk: ^3.5.4
```

From `frontend/pubspec.lock`:

```yaml
sdks:
  dart: ">=3.5.4 <4.0.0"
  flutter: ">=3.18.0-18.0.pre.54"
```

Observed local toolchain during planning:

```text
Flutter 3.24.5
Dart 3.5.4
```

### 2.3 Existing state-management approach

There is no package-based state-management approach. The current app is the
default counter app using local `StatefulWidget` state in `frontend/lib/main.dart`.

### 2.4 Existing HTTP client package

None.

### 2.5 Existing routing package

None.

### 2.6 Existing file-picker dependency

None.

### 2.7 Existing folder structure

Current frontend structure is minimal/default:

```text
frontend/
  lib/
    main.dart
  test/
    widget_test.dart
  web/
    favicon.png
    index.html
    manifest.json
    icons/
  analysis_options.yaml
  pubspec.yaml
  pubspec.lock
  README.md
```

### 2.8 Current app entry point

The entry point is `frontend/lib/main.dart`:

```dart
void main() {
  runApp(const MyApp());
}
```

The current `MyApp` is the default Flutter counter application.

### 2.9 Current theme and typography

The current theme is default Material 3 with a purple seed color:

```dart
ThemeData(
  colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
  useMaterial3: true,
)
```

No custom typography, spacing tokens, or design system exists.

### 2.10 Existing PaperScape branding or assets

No PaperScape-specific frontend branding or assets are present. The web metadata
still uses default Flutter project values such as `frontend` and
`A new Flutter project.`

### 2.11 Existing tests

There is one default widget test:

```text
frontend/test/widget_test.dart
```

It verifies the default counter increments. This test should be replaced by
PaperScape-specific widget/controller/model tests during implementation.

### 2.12 Confirmed Flutter Web readiness

Planning-time validation results:

```text
flutter analyze
Analyzing paperscape...
No issues found! (ran in 3.9s)
```

```text
flutter test
00:00 +0: loading c:/Projects/IBM Hackathon/PaperScape/paperscape/frontend/test/widget_test.dart
00:00 +0: Counter increments smoke test
00:01 +1: All tests passed!
```

```text
flutter build web
Compiling lib\main.dart for the Web...                             84.5s
√ Built build\web
```

Earlier failed command attempts were caused by Windows shell directory handling,
not by Flutter project defects.

---

## 3. Completed Backend Contracts to Consume

All backend endpoints are registered under `/api/v1`.

### 3.1 `POST /api/v1/papers`

Implemented in `backend/app/routers/papers.py`.

Request:

```text
multipart/form-data
field name: file
file media type: application/pdf
```

Success status: `201 Created`

Response model: `UploadResponse`

```json
{
  "paper_id": "uuid-or-generated-id",
  "filename": "paper.pdf",
  "page_count": 12,
  "chunk_count": 47
}
```

Frontend implication: the API client must call `/papers`, not the older planned
`/papers/upload` path, and must accept `201` as the successful upload status.

### 3.2 `POST /api/v1/papers/{paper_id}/research-map-jobs`

Success status: `202 Accepted`

Response model: `JobCreateResponse`

```json
{
  "job_id": "uuid-or-generated-id",
  "paper_id": "uuid-or-generated-id",
  "status": "pending"
}
```

Duplicate active-job behavior is intentionally idempotent: if a `pending` or
`running` job already exists for the paper, the endpoint returns `202` with the
existing active job. The frontend must not expect `409 Conflict` for duplicate
active jobs.

### 3.3 `GET /api/v1/jobs/{job_id}`

Success status: `200 OK`

Response model: `JobStatusResponse`

```json
{
  "job_id": "uuid-or-generated-id",
  "paper_id": "uuid-or-generated-id",
  "status": "pending",
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:15+00:00",
  "error": null
}
```

For failed jobs, `error` is a safe machine-readable code, not raw exception
text.

### 3.4 `GET /api/v1/papers/{paper_id}/research-map`

Success status: `200 OK`

Response model: `ResearchMap`

Retrieval requires the latest job for the paper to be `succeeded`. If the latest
job is not succeeded, or no map exists, the backend returns `404 map_not_found`.

Frontend implication: after polling reaches `succeeded`, fetch the map using the
same uploaded `paper_id`. Do not assume older completed maps remain visible
after a later failed regeneration.

### 3.5 `GET /api/v1/health`

Success response:

```json
{ "status": "ok" }
```

For Sub-task 8, the health endpoint should be optional and non-blocking.

---

## 4. Exact Backend Field Names

### 4.1 `UploadResponse`

Fields from `backend/app/models/paper.py`:

| Field | Type | Frontend validation |
|---|---|---|
| `paper_id` | string | required, nonblank |
| `filename` | string | required, nonblank |
| `page_count` | integer | required, `>= 0` |
| `chunk_count` | integer | required, `>= 0` |

### 4.2 `JobCreateResponse`

Fields from `backend/app/models/job.py`:

| Field | Type | Frontend validation |
|---|---|---|
| `job_id` | string | required, nonblank |
| `paper_id` | string | required, nonblank |
| `status` | `JobStatus` | required |

### 4.3 `JobStatusResponse`

Fields inherited from `Job`:

| Field | Type | Frontend validation |
|---|---|---|
| `job_id` | string | required, nonblank |
| `paper_id` | string | required, nonblank |
| `status` | `JobStatus` | required, unknown-safe enum parse |
| `created_at` | ISO-8601 string | parse as UTC-aware `DateTime` |
| `updated_at` | ISO-8601 string | parse as UTC-aware `DateTime` |
| `error` | string or null | safe error code only |

Valid backend statuses:

```text
pending
running
succeeded
failed
```

The Flutter model should include an `unknown` enum value for future-safe parsing
and convert unknown statuses into safe failure states rather than crashing.

### 4.4 `ResearchMap`

Fields from `backend/app/models/research_map.py`:

| Field | Type | Frontend validation |
|---|---|---|
| `paper_id` | string | required, nonblank |
| `research_question` | string | required, nonblank |
| `findings` | array | required, exactly 3 |
| `limitations` | array of string | required, at least 1 |
| `disclaimer` | string | required, nonblank |

`Finding` fields:

| Field | Type | Notes |
|---|---|---|
| `statement` | string | required, nonblank |
| `evidence` | array of `Evidence` | required, at least 1 |
| `confidence` | string enum | support `high`, `partial`, `uncertain` |

`Evidence` fields:

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | string | required, nonblank |
| `page` | integer | required, `>= 1` |
| `excerpt` | string | required, nonblank |

Although internal generation rules emphasize `high` and `partial`, the public
backend model permits `uncertain`; the frontend must parse and display it
safely.

---

## 5. Backend Error Shape and Frontend Mapping

Sub-task 7 implements a consistent error body:

```json
{
  "detail": {
    "code": "snake_case_code",
    "message": "Application-controlled message"
  }
}
```

The Flutter API client should map this into:

```dart
class ApiException implements Exception {
  final int? statusCode;
  final String code;
  final String safeMessage;
}
```

The UI must not display raw HTTP response bodies, stack traces, HTML server
responses, database errors, SDK errors, local paths, uploaded PDF bytes, prompt
text, model output, or full research-map JSON.

### 5.1 Codes to handle

| Code | Suggested user-facing message |
|---|---|
| `invalid_upload` | Choose a non-empty PDF file and try again. |
| `unsupported_media_type` | PaperScape accepts PDF files only. |
| `upload_not_a_pdf` | The selected file does not appear to be a PDF. Choose a different file. |
| `upload_too_large` | The PDF is larger than the allowed upload limit. Choose a smaller file. |
| `extraction_failed` | PaperScape could not extract selectable text from this PDF. OCR is not supported in this version. |
| `invalid_identifier` | The paper or job identifier is invalid. Start over and try again. |
| `paper_not_found` | This uploaded paper could not be found. Start over and upload again. |
| `job_not_found` | This research-map job could not be found. Start over and try again. |
| `map_not_found` | The research map is not available yet. Try again after the job completes. |
| `generation_unavailable` | Research-map generation is unavailable. Check backend watsonx configuration, then retry. |
| `task_scheduling_failed` | PaperScape could not start the background job. Please try again. |
| `persistence_error` | A storage error occurred. Please try again. |
| `internal_error` | Something went wrong. Please try again. |
| `server_restart` | The server restarted before this job completed. Please retry generation. |
| `extraction_missing` | The extracted paper content is missing. Start over and upload again. |
| `map_generation_failed` | PaperScape could not generate a grounded research map for this paper. |
| `llm_provider_error` | The model service was unavailable. Please try again later. |
| `unexpected_error` | Something went wrong while generating the map. Please try again. |
| `invalid_job_state` | The job changed state unexpectedly. Please retry or start over. |

Unknown codes should use:

```text
Something went wrong. Please try again.
```

Technical details should be limited to debug-safe logs containing only phase,
HTTP status, safe code, `paper_id`, and `job_id`.

---

## 6. Package Decisions

No existing HTTP, router, file-picker, or state-management packages are present.

### 6.1 Proposed dependency additions for implementation

Do not add these until implementing Sub-task 8. This plan only records the
decision.

| Package | Type | Reason |
|---|---|---|
| `http` | runtime dependency | Small standard Dart HTTP client; supports multipart upload; adequate for current endpoints. |
| `file_picker` | runtime dependency | Supports Flutter Web, single-file PDF selection, and returning file bytes. |

No `dio` should be added if `http` is used. No router package should be added
for a single-screen vertical slice. No Riverpod, Bloc, Freezed, Retrofit, or
code generation should be added unless later requirements justify them.

### 6.2 HTTP caveat

Reliable upload progress and cancellation are limited with `http`. The UI should
show indeterminate upload/progress states instead of fake percentages. If
cancellation cannot be implemented cleanly with the chosen package, stale
workflow tokens must still prevent old async responses from overwriting newer
state.

---

## 7. Proposed Frontend Architecture

Use the smallest architecture consistent with the repository and product rules.

```text
frontend/lib/
  main.dart
  app/
    app.dart
    app_config.dart
    app_theme.dart
  features/
    research_map/
      data/
        api_exception.dart
        paperscape_api_client.dart
        dto/
          upload_response.dart
          job_response.dart
          research_map.dart
      domain/
        pdf_picker.dart
        selected_pdf.dart
      presentation/
        research_map_controller.dart
        research_map_state.dart
        research_map_screen.dart
        widgets/
          pdf_upload_panel.dart
          processing_panel.dart
          finding_card.dart
          evidence_block.dart
          limitations_panel.dart
          workflow_error_panel.dart
```

Tests should mirror the feature structure under `frontend/test/`.

This structure keeps API/data concerns, file selection, workflow state, and
widgets separate without introducing unnecessary framework abstractions.

---

## 8. API Base URL Configuration

Add one centralized configuration source:

```dart
const apiBaseUrl = String.fromEnvironment(
  'PAPERSCAPE_API_BASE_URL',
  defaultValue: 'http://localhost:8000/api/v1',
);
```

Implementation should normalize trailing slashes:

```text
http://localhost:8000/api/v1/ -> http://localhost:8000/api/v1
```

Route paths should be centralized in the API client, for example:

```text
POST /papers
POST /papers/{encodedPaperId}/research-map-jobs
GET  /jobs/{encodedJobId}
GET  /papers/{encodedPaperId}/research-map
GET  /health
```

Local execution example:

```powershell
flutter run -d chrome `
  --dart-define=PAPERSCAPE_API_BASE_URL=http://localhost:8000/api/v1
```

No secrets, watsonx credentials, backend internal configuration, prompts, or
SDK details belong in Flutter.

---

## 9. CORS and Local Browser Considerations

Current backend default CORS configuration from `backend/app/config.py`:

```text
http://localhost:3000,http://localhost:8080
```

`backend/app/main.py` configures:

```python
allow_origins=resolved_settings.cors_origins_list
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

Flutter Web development may use a random localhost port. The implementation
documentation should tell developers to either:

1. add the Flutter dev origin to backend `CORS_ORIGINS`, or
2. serve the built frontend from `http://localhost:8080`, or
3. run Flutter Web on a fixed allowed port if used by the local workflow.

Production deployments should use HTTPS for both frontend and backend. Avoid
mixed content by not calling an `http://` API from an `https://` frontend.

---

## 10. Domain Models

Implement hand-written typed Dart models. Avoid code generation.

### 10.1 Parsing rules

- Required fields must be present and have the expected type.
- Required strings should be trimmed and nonblank.
- Integer counts/pages must respect backend invariants.
- `ResearchMap.findings` must contain exactly three findings.
- Each finding must contain at least one evidence item.
- Unknown additive JSON fields should be ignored for compatibility.
- Missing or malformed required fields should throw safe parse exceptions.
- Timestamps should parse into UTC-aware `DateTime` values.
- Unknown job statuses should parse as `JobStatus.unknown` and become a safe
  workflow failure.
- Do not invent fields not returned by the backend.

### 10.2 Enums

`JobStatus`:

```text
pending
running
succeeded
failed
unknown
```

`FindingConfidence`:

```text
high
partial
uncertain
unknown
```

Unknown confidence values should render as a neutral “unknown support” label,
not crash the UI.

---

## 11. API Client Design

Create one `PaperScapeApiClient` responsible for:

- multipart PDF upload to `POST /papers`
- creating or retrieving an active research-map job
- polling job status
- retrieving the research map
- optional one-shot health check
- URL/path construction and identifier encoding
- HTTP timeout handling
- JSON decoding and model parsing
- safe exception mapping

Suggested interface:

```dart
abstract interface class PaperScapeApi {
  Future<UploadResponse> uploadPaper(SelectedPdf pdf);
  Future<JobCreateResponse> createResearchMapJob(String paperId);
  Future<JobStatusResponse> getJobStatus(String jobId);
  Future<ResearchMap> getResearchMap(String paperId);
  Future<bool> checkHealth();
}
```

Implementation rules:

- Use multipart field name `file`.
- Preserve the selected filename.
- Use `application/pdf` as the media type.
- Send only selected PDF bytes.
- Do not base64-encode the PDF.
- Do not log request bodies or response bodies.
- Use reasonable timeouts.
- Accept upload status `201` and job-create status `202`.
- Convert backend, timeout, network, non-JSON, malformed JSON, and parse errors
  into safe frontend exceptions.

---

## 12. File Selection and Client-Side Validation

The widget layer must not directly depend on the picker plugin.

### 12.1 Abstractions

```dart
abstract interface class PdfPicker {
  Future<SelectedPdf?> pickPdf();
}
```

```dart
class SelectedPdf {
  final String filename;
  final Uint8List bytes;
  final String? mimeType;

  int get sizeBytes => bytes.length;
}
```

`FilePickerPdfPicker` should wrap `file_picker` and return `null` when the user
cancels selection.

### 12.2 UI-boundary validation

Validate before upload:

- file exists / selection returned a result
- filename is nonblank
- extension is `.pdf`, case-insensitive
- MIME type is compatible when supplied
- bytes are available
- file is not empty
- file does not exceed the configured client-side limit

The backend remains authoritative. The UI must not claim that extension or MIME
checks prove the file is safe.

Do not store the file in browser local storage, IndexedDB, shared preferences,
or logs. Clear PDF bytes on reset and dispose where practical.

---

## 13. Workflow State Machine

Use one `ResearchMapController` with an immutable `ResearchMapState` and a phase
enum. Because there is no existing framework, use `ChangeNotifier` from Flutter
instead of adding Riverpod or Bloc.

Recommended phases:

```text
idle
selectingFile
fileSelected
uploading
uploadSucceeded
creatingJob
polling
loadingMap
ready
failed
```

State fields:

- `phase`
- selected file metadata
- selected file bytes only while needed
- upload response
- job ID
- current job status
- research map
- safe user-facing error
- retry type / retry capability
- action-in-progress boolean
- workflow generation token

Required behavior:

- Duplicate button taps do not start duplicate requests.
- New file selection clears previous results.
- Starting over cancels polling.
- Disposing cancels timers and prevents later state writes.
- Failed upload can be retried.
- Failed job can start a new backend job for the same uploaded paper.
- Completed workflow can reset for another paper.
- Stale responses from older workflows cannot overwrite newer state.

Use a monotonically increasing workflow token/request generation ID to reject
stale async completions.

---

## 14. Job Creation Behavior

After upload succeeds:

1. Store and display the `UploadResponse` metadata.
2. Use `uploadResponse.paperId` to call `POST /papers/{paper_id}/research-map-jobs`.
3. Treat any successful `202` as the job to poll, whether newly created or an
   existing active job.
4. Begin polling the returned `job_id`.
5. Do not call the model directly from Flutter.
6. Do not create a second job while one request is already in progress.

When backend returns `generation_unavailable`, show a clear safe message and a
retry option after backend configuration is fixed.

---

## 15. Polling Implementation

Use a bounded, lifecycle-safe polling scheduler abstraction.

Recommended behavior:

1. Poll immediately after receiving the job ID.
2. Poll every 1.5–2 seconds while status is `pending` or `running`.
3. Stop when status is `succeeded`, `failed`, `unknown`, reset, timeout, or
   dispose.
4. Prevent overlapping poll requests with an `_isPollingRequestInFlight` guard.
5. Stop after a configurable timeout, such as two minutes.
6. Show a safe timeout message with retry/start-over actions.
7. Do not use uncancellable `Future.delayed()` recursion.

Use an injectable scheduler/timer factory for tests so tests do not wait in real
time.

### 15.1 Success path

When status becomes `succeeded`:

1. Stop polling.
2. Transition to `loadingMap`.
3. Call `GET /papers/{paper_id}/research-map`.
4. Transition to `ready` only after successful decoding.

### 15.2 Failure path

When status becomes `failed`:

1. Stop polling.
2. Read only `JobStatusResponse.error` as a safe code.
3. Map the code to a user-facing explanation.
4. Offer retry generation or start over.

---

## 16. Presentation Plan

Implement one responsive vertical-slice screen.

### 16.1 Header

- PaperScape name
- Short value statement, for example:
  `Upload a paper. Build an evidence-backed research map.`
- Optional non-blocking backend health indicator only if it remains simple.

### 16.2 Upload panel

- Select-PDF button as the primary interaction.
- Optional drag-and-drop affordance only if supported without making it the only
  upload path.
- Selected filename.
- Human-readable file size.
- Replace-file action.
- Upload/generate button.
- Client-side validation feedback.

### 16.3 Paper metadata panel

After successful upload, display:

- filename
- page count
- chunk count
- paper ID as secondary metadata if useful for debugging/demo traceability

### 16.4 Processing panel

Show stage-specific progress text:

```text
Uploading paper
Extracting selectable text
Creating research-map job
Generating grounded findings
Loading research map
```

Use a spinner or step indicator. Do not show fake model percentages.

### 16.5 Research-map result

Display:

- research question
- exactly three finding cards
- confidence badge for each finding
- one or more evidence blocks per finding
- page numbers
- chunk identifiers as secondary metadata
- limitations
- disclaimer

Evidence must remain visibly associated with its finding. Do not hide page
provenance.

### 16.6 Failure state

Display:

- short safe explanation
- retry action when appropriate
- start-over action
- no raw technical details

---

## 17. Responsive Design

Support at minimum:

- desktop browser
- tablet-width browser
- narrow mobile-width browser

Implementation guidelines:

- centered max-width content on desktop
- single-column layout on narrow screens
- finding cards stack vertically
- evidence excerpts wrap without horizontal overflow
- buttons remain reachable and readable
- avoid fixed pixel layouts that assume one monitor size

Use Material 3 defaults and a small PaperScape palette derived from a local
`app_theme.dart`; do not add a large design-system dependency.

---

## 18. Accessibility Plan

- Keyboard-accessible buttons.
- Visible focus states from Material widgets.
- Semantic labels for file selection and upload controls.
- Status text exposed to assistive technologies where practical.
- Sufficient contrast.
- Text alternatives for nondecorative icons.
- Error messages visually and semantically associated with relevant controls.
- No meaning conveyed by color alone.
- Selectable evidence text where practical.
- Practical minimum tap targets.
- Drag-and-drop must never be the only upload mechanism.

---

## 19. Health Behavior Decision

The health endpoint exists, but it should not increase vertical-slice complexity.

Recommended Sub-task 8 decision: omit continuous health behavior. If included,
make it a single startup check or manual retry only:

- do not block file selection indefinitely
- do not poll health continuously
- do not expose backend internals
- keep health separate from job polling

---

## 20. Testing Abstractions

Inject these dependencies:

- API client (`PaperScapeApi`)
- PDF picker (`PdfPicker`)
- polling scheduler/timer
- clock or timeout source
- optional cancellation handle if supported later

Tests must not:

- open a browser file dialog
- make network calls
- access a live backend
- use real timers/sleeps
- read real PDFs unless a tiny committed fixture is deliberately added
- depend on watsonx credentials

---

## 21. Model and API-Client Test Matrix

Cover at minimum:

- `UploadResponse` parses valid JSON.
- Missing required upload field fails safely.
- `JobCreateResponse` parses pending job.
- `JobStatusResponse` parses `pending`, `running`, `succeeded`, and `failed`.
- Failed-job error code parses.
- Unknown job status is handled safely.
- Timestamps parse as UTC-aware `DateTime` values.
- `ResearchMap` parses exactly three findings.
- Multiple evidence items parse.
- Page and chunk provenance parse.
- Confidence values `high`, `partial`, and `uncertain` parse.
- Unknown confidence is handled safely.
- Limitations parse.
- Disclaimer parses.
- Backend error shape parses.
- Malformed JSON produces safe parsing error.
- Upload sends multipart field `file`.
- Upload preserves filename.
- Upload sends exact bytes.
- Upload uses PDF media type.
- Upload expects `201` success.
- Job creation expects `202` success.
- Job routes use encoded identifiers.
- Timeout maps to safe frontend exception.
- Non-JSON server error maps to generic safe error.
- Raw response body is not exposed.

---

## 22. Workflow-Controller Test Matrix

Cover at minimum:

- Initial state is `idle`.
- PDF selection succeeds.
- Selection cancellation returns to safe state.
- Invalid file rejected before upload.
- Empty file rejected.
- Oversized file rejected.
- Upload begins once.
- Duplicate upload taps ignored.
- Upload success stores paper metadata.
- Job creation receives uploaded paper ID.
- Existing active job response begins polling.
- Pending status continues polling.
- Running status continues polling.
- Succeeded status stops polling and loads map.
- Failed status stops polling.
- Unknown status stops with safe failure.
- Timeout stops polling.
- Reset stops polling.
- Dispose stops polling.
- Poll requests never overlap.
- Retrieval failure produces safe failure state.
- Retry after upload failure.
- Retry after failed job.
- Start-over clears previous PDF bytes and research map.
- Stale earlier response cannot overwrite a newer workflow.
- Safe error mapping for known backend codes.
- Generic error mapping for unknown codes.

---

## 23. Widget Test Matrix

### Idle and selection

- Upload screen renders.
- Select-PDF button is visible.
- Selected filename and size render.
- Invalid-file message renders.
- Generate button disabled without a valid file.
- Generate button enabled with a valid file.

### Processing

- Uploading state renders.
- Job creation state renders.
- Pending/running state renders.
- Duplicate action controls are disabled.
- No fake percentage is shown.

### Results

- Research question renders.
- Exactly three finding cards render.
- Finding statements render.
- Confidence labels render.
- Evidence excerpts render.
- Page provenance renders.
- Chunk identifiers render as secondary metadata.
- Limitations render.
- Disclaimer renders.
- Long excerpts do not overflow at narrow width.

### Failures

- Safe upload failure renders.
- Safe job failure renders.
- Retry action renders.
- Start-over action renders.
- Raw exception text is absent.

### Accessibility

- Upload control has a semantic label.
- Main actions are keyboard-focusable.
- Status changes expose suitable semantics where implemented.

---

## 24. Optional Integration-Style Widget Test

Use:

- fake PDF picker
- fake API client
- fake polling scheduler

Simulate:

```text
select file
→ upload succeeds
→ job creation returns pending job
→ job is pending
→ job becomes running
→ job succeeds
→ research map loads
```

Verify final research-map UI. No live backend, browser dialog, real timer, or
watsonx credential is used.

---

## 25. Logging and Privacy

Debug-safe logs may include:

- workflow phase
- HTTP status
- safe API error code
- paper ID
- job ID

Do not log:

- PDF bytes
- extracted paper text
- evidence excerpts
- full research-map JSON
- raw HTTP response bodies
- credentials
- local browser file paths
- prompts or model output
- stack traces in user-visible text

Production UI errors must remain generic and safe.

---

## 26. Exact Files Proposed for Implementation

### 26.1 Create

```text
frontend/lib/app/app.dart
frontend/lib/app/app_config.dart
frontend/lib/app/app_theme.dart
frontend/lib/features/research_map/data/api_exception.dart
frontend/lib/features/research_map/data/paperscape_api_client.dart
frontend/lib/features/research_map/data/dto/upload_response.dart
frontend/lib/features/research_map/data/dto/job_response.dart
frontend/lib/features/research_map/data/dto/research_map.dart
frontend/lib/features/research_map/domain/pdf_picker.dart
frontend/lib/features/research_map/domain/selected_pdf.dart
frontend/lib/features/research_map/presentation/research_map_controller.dart
frontend/lib/features/research_map/presentation/research_map_state.dart
frontend/lib/features/research_map/presentation/research_map_screen.dart
frontend/lib/features/research_map/presentation/widgets/pdf_upload_panel.dart
frontend/lib/features/research_map/presentation/widgets/processing_panel.dart
frontend/lib/features/research_map/presentation/widgets/finding_card.dart
frontend/lib/features/research_map/presentation/widgets/evidence_block.dart
frontend/lib/features/research_map/presentation/widgets/limitations_panel.dart
frontend/lib/features/research_map/presentation/widgets/workflow_error_panel.dart
```

### 26.2 Modify

```text
frontend/lib/main.dart
frontend/test/widget_test.dart
frontend/web/index.html
frontend/web/manifest.json
frontend/README.md
```

Expected modifications:

- replace default counter app with PaperScape app bootstrap
- replace default counter test with PaperScape tests
- update web title/description from default Flutter values
- document local frontend/backend execution and CORS notes

### 26.3 Dependency modifications during implementation

When implementation begins, modify only frontend package files as needed:

```text
frontend/pubspec.yaml
frontend/pubspec.lock
```

Add only:

- `http`
- `file_picker`

This plan document does not modify dependencies.

---

## 27. Scope Exclusions

Do not implement in Sub-task 8:

- authentication
- user accounts
- saved project history
- original PDF persistence
- OCR
- scanned-PDF support
- multi-paper comparison
- audience selection
- audience-specific summaries
- visual abstracts
- narration scripts
- audio generation
- content editing
- export
- citation graphs
- embeddings
- vector databases
- WebSockets
- server-sent events
- push notifications
- offline job processing
- backend changes unrelated to a verified frontend blocker
- deployment infrastructure

---

## 28. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Flutter dev server origin not allowed by backend CORS | Document `CORS_ORIGINS` update or serve frontend on `localhost:8080`. |
| Upload progress unavailable with `http` | Show indeterminate upload/progress states; do not fake percentages. |
| Duplicate clicks create duplicate requests | Controller action-in-progress guards and workflow phase checks. |
| Stale async completions overwrite newer workflow | Monotonic workflow token checked after every await. |
| Polling overlaps or runs forever | In-flight guard, injectable timer, timeout, reset/dispose cancellation. |
| Backend returns active existing job | Treat any `202` job response as the job to poll. |
| Unknown backend error/status appears | Unknown-safe enums and generic safe user messages. |
| Large excerpts overflow UI | Wrap text, constrain max width, test narrow layouts. |
| Sensitive data leaks via logs/errors | Log only phase/status/safe codes/IDs; never log bytes, text, raw bodies, prompts, or model output. |

---

## 29. Acceptance Checklist

- [ ] A user can select one PDF in Flutter Web.
- [ ] Invalid files are rejected with safe feedback.
- [ ] Exact PDF bytes are uploaded as multipart field `file`.
- [ ] Upload uses `POST /api/v1/papers` and accepts `201 Created`.
- [ ] Upload success displays paper metadata.
- [ ] A research-map job can be created via `POST /papers/{paper_id}/research-map-jobs`.
- [ ] Existing active jobs returned as `202` are handled correctly.
- [ ] Job polling is cancellable and non-overlapping.
- [ ] Polling stops on success, failure, reset, timeout, and dispose.
- [ ] A succeeded job loads the persisted research map.
- [ ] A failed job displays a safe user-facing error.
- [ ] The UI renders the research question.
- [ ] The UI renders exactly three findings.
- [ ] Confidence labels render for `high`, `partial`, and `uncertain`.
- [ ] Evidence excerpts and page provenance are visible.
- [ ] Limitations and disclaimer are visible.
- [ ] No raw backend errors or response bodies are displayed.
- [ ] No PDF bytes or paper content are logged.
- [ ] No real backend is required for frontend tests.
- [ ] No real timers or sleeps are used in tests.
- [ ] Existing Flutter tests are replaced or updated and continue to pass.
- [ ] `flutter analyze` passes.
- [ ] `flutter test` passes.
- [ ] `flutter build web` succeeds.
- [ ] `git diff --check` passes.

---

## 30. Short Summary

- **Existing frontend readiness:** Flutter Web scaffold exists, analyzes, tests,
  and builds successfully, but it is still the default counter app with no
  PaperScape UI, HTTP client, file picker, routing, or state-management package.
- **Selected state-management approach:** `ChangeNotifier` controller plus
  immutable state and phase enum; no Riverpod/Bloc.
- **Selected HTTP/file-picker packages:** add `http` and `file_picker` during
  implementation; do not add `dio` or another picker.
- **Workflow state design:** one explicit state machine covering selection,
  upload, job creation, polling, map loading, ready, and failed phases, protected
  by duplicate-action guards and workflow tokens.
- **Polling strategy:** immediate poll, then every 1.5–2 seconds for
  `pending`/`running`, bounded by timeout, cancellable on reset/dispose, no
  overlapping requests.
- **Estimated test groups:** model/API-client tests, controller tests, widget
  tests, and one optional integration-style widget test using fakes.