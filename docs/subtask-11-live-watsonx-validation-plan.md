# Sub-task 11 — Live watsonx/Granite Validation and Demo-Paper Baseline

## 1. Objective

Validate the existing PaperScape vertical slice against a real watsonx.ai
project and an available IBM Granite model without broadening the product scope.

The validation must prove:

```text
WatsonxProvider connectivity
→ real ResearchMapService generation
→ current JSON and grounding validation
→ full Flutter Web / Compose workflow
→ persisted, evidence-backed ResearchMap
```

This task remains limited to live-provider validation, a three-paper manual
evaluation baseline, security and cost controls, and the documentation needed to
repeat the validation safely.

It does not add audience adaptation, explainer packs, narration, visual
abstracts, editing/regeneration, export, authentication, OCR, Redis, Celery,
PostgreSQL, vector search, deployment, or CI execution of paid tests.

## 2. Current-state assessment

The repository currently has the following recorded, verified baseline:

- 424 backend tests passed.
- 42 frontend tests passed.
- The deterministic offline ResearchMap evaluation passed.
- Backend and frontend Docker images built successfully.
- Both Compose services became healthy.
- Credential-free upload and extraction passed.
- Credential-free job creation returned safe HTTP `503
  generation_unavailable` without creating a job.
- SQLite WAL mode and named-volume persistence passed.
- CORS from `http://localhost:8080` passed.
- Successful generation is proven only with fake `LLMProvider`
  implementations.
- No successful real watsonx browser workflow has been recorded.

The offline Phase 11 eval-baseline requirement is therefore already satisfied.
The missing proof is real provider compatibility and a successful end-to-end
live workflow.

### 2.1 Current provider behavior

The current implementation uses:

- `ibm-watsonx-ai==1.5.14`;
- `ModelInference`;
- the Chat API through `ModelInference.chat`;
- `validate=False`;
- `max_retries=0`;
- explicit `Credentials(verify=True)`;
- a provider-owned maximum of two attempts for explicitly transient failures;
- `max_tokens=1500` and `temperature=0.1` for ResearchMap generation;
- at most one ResearchMap corrective generation call.

`WatsonxProvider` is not constructed during module import, application startup,
health checks, upload, polling, or map retrieval. A non-empty API key enables a
lazy job-runner factory. Provider construction first occurs when the background
job executes.

Pinned `ibm-watsonx-ai==1.5.14` source inspection establishes that:

- PaperScape defers the SDK import until `WatsonxProvider` construction;
- `WatsonxProvider` construction immediately creates `ModelInference`;
- `ModelInference` creates `APIClient`;
- `APIClient` obtains an authentication token during initialization;
- provider construction can therefore perform network authentication;
- `validate=False` skips model-spec validation only;
- `validate=False` does not make provider construction network-free;
- `max_retries=0` disables the SDK's `_with_retry` response decorator;
- the pinned SDK separately creates a `RetryTransport`;
- `RetryTransport` is configured with `retries=3`;
- that transport retries statuses including `401`, `500`, `502`, `503`, `504`,
  `520`, `521`, and `524`;
- explicit `verify=True` disables the pinned transport's unverified SSL
  fallback while preserving certificate verification.

The inaccurate provider comments about network-free construction and sole retry
ownership were corrected as part of Sub-task 11A.

### 2.1.1 First Tier A result and Chat migration

The first Tier A run used the explicit `ibm/granite-4-h-small` candidate in
Frankfurt through `ModelInference.generate_text`. IAM authentication and
provider/SDK client construction succeeded. The request did not raise an HTTP
access error, but the SDK warned that `decoding_method` was ignored and that the
text-generation endpoint is deprecated. The SDK returned an empty string and
PaperScape raised `LLMResponseError`.

That Tier A run failed and consumed the one-invocation approval recorded by
Jadiel Bett on 30 July 2026. It did not authorize a rerun.

Sub-task 11A therefore migrated the provider internally to
`ModelInference.chat` while preserving `LLMProvider.generate(...) -> str`. The
exact existing prompt is sent as one user message, `max_tokens` maps to
`max_completion_tokens`, temperature is passed exactly, and assistant content
is strictly validated. At migration time the application model default remained
unchanged; after the migrated Tier A pass, Stage 2 promoted the compatible
Granite 4 model.

Offline verification after the migration collected 454 backend tests: 453
passed and the gated Tier A test was the only skip. Provider tests (94),
ResearchMap tests (67), integration tests (2), the offline evaluation,
dependency check, frontend format/analysis, 42 Flutter tests, and the Flutter
Web release build passed. No live call occurred.

### 2.2 Current configuration

Direct backend configuration uses:

| Setting | Current behavior |
|---|---|
| `WATSONX_API_KEY` | Empty by default; a non-empty value enables job creation. |
| `WATSONX_PROJECT_ID` | Empty by default; required for successful project-scoped inference. |
| `WATSONX_URL` | The application currently defaults to `https://us-south.ml.cloud.ibm.com`; Frankfurt live validation must explicitly override it with `https://eu-de.ml.cloud.ibm.com`. |
| `GRANITE_MODEL_ID` | Defaults to `ibm/granite-4-h-small`. |

Compose reads backend-only credentials from:

- `COMPOSE_WATSONX_API_KEY`
- `COMPOSE_WATSONX_PROJECT_ID`

and maps them into the backend container as:

- `WATSONX_API_KEY`
- `WATSONX_PROJECT_ID`

Compose forwards `WATSONX_URL` and currently relies on the application's model
default. No watsonx setting is exposed to Flutter.

Watsonx credentials remain backend-only. Missing credentials are supported
during ordinary startup, health checks, upload, and extraction; generation
remains unavailable until they are configured. Frankfurt live validation uses
`https://eu-de.ml.cloud.ibm.com`. Live tests remain skipped unless both
`WATSONX_LIVE_TEST=1` and `WATSONX_LIVE_ACK_CHARGES=1` are explicitly supplied.

### 2.3 IBM model and API lifecycle facts

The following facts were verified during planning on **29 July 2026**:

1. `ibm/granite-13b-instruct-v2` was withdrawn on 15 October 2025 and is not a
   usable live baseline.
2. `ibm/granite-4-h-small` is currently listed for provided pay-per-token
   inference in Frankfurt and is the candidate Granite model for this
   validation.
3. The watsonx.ai text-generation API is deprecated and scheduled for removal
   on 14 March 2027.
4. Current Granite 4 documentation emphasizes Chat API use. The presence of the
   `generate_text` method in the installed SDK is not proof that the candidate
   model supports the existing application path.

Official IBM sources:

- [Foundation model lifecycle](https://www.ibm.com/docs/en/watsonx/saas?topic=model-foundation-lifecycle)
  — retrieved 29 July 2026.
- [Supported foundation models in watsonx.ai](https://www.ibm.com/docs/en/watsonx/saas?topic=solutions-supported-foundation-models)
  — retrieved 29 July 2026.
- [Regional availability of services and features](https://www.ibm.com/docs/en/watsonx/saas?topic=services-regional-availability-features)
  — retrieved 29 July 2026.
- [What's new for watsonx as a Service](https://www.ibm.com/docs/en/watsonx/saas?topic=watsonx-whats-new)
  — retrieved 29 July 2026.
- [watsonx.ai Runtime service plans](https://www.ibm.com/docs/en/watsonx/saas?topic=cloud-watsonxai-runtime-plans)
  — retrieved 29 July 2026.

Model availability remains region-, project-, entitlement-, and API-specific.
The documentation above identifies a candidate; Tier A is the compatibility
proof.

## 3. Model migration order

Do not change the application default before live compatibility is proven.

Use this mandatory sequence:

1. Leave `Settings.granite_model_id` unchanged.
2. Set an explicit process-environment override for Tier A:

   ```text
   GRANITE_MODEL_ID=ibm/granite-4-h-small
   ```

3. Prove that the existing pinned SDK, `ModelInference` construction, Chat API,
   credentials, project, endpoint, Chat parameters, and candidate model work
   together.
4. Only after Tier A succeeds, promote the application default to:

   ```text
   ibm/granite-4-h-small
   ```

5. Update the config unit assertion and affected documentation in the same
   bounded implementation.
6. Rerun the complete backend suite, frontend gates, and offline evaluation
   after the default change.
7. Proceed to Tier B only after those offline gates pass.

If Tier A shows that the candidate model cannot use the migrated Chat path, stop
and record the blocker. Do not automatically:

- choose another model;
- switch regions;
- upgrade the SDK;
- change the `LLMProvider` interface;
- change `ResearchMapService`;
- change the prompt;
- weaken schema or grounding validation.

Any of those actions requires an explicit, separately documented
provider-migration decision.

## 4. Credential, region, and service readiness

### 4.1 Selected Frankfurt deployment baseline

PaperScape selects Frankfurt for this validation:

| Item | Selected value |
|---|---|
| Region | Frankfurt |
| IBM region code | `eu-de` |
| API endpoint | `https://eu-de.ml.cloud.ibm.com` |
| watsonx.ai Runtime plan | Lite |

The PaperScape project and its associated watsonx.ai Runtime must both be
created in Frankfurt. A Runtime created in another region does not satisfy this
baseline even if it belongs to the same IBM Cloud account.

`ibm/granite-4-h-small` is currently listed for provided pay-per-token inference
in Frankfurt. This listing is necessary but not sufficient: Tier A must still
prove PaperScape project entitlement and migrated Chat compatibility through the
Frankfurt endpoint.

Actual latency from Kenya must be measured during validation rather than
assumed from geographic proximity or region labels.

Dallas remains a fallback only if a verified Frankfurt-specific compatibility
blocker occurs. A failed call must be classified and recorded; it must not
automatically trigger a region switch. Any move to Dallas requires a separate,
explicit decision supported by evidence that the blocker is specific to
Frankfurt.

### 4.2 Required live configuration

A successful live run requires:

- a non-empty watsonx API key;
- a non-empty project ID;
- a PaperScape project created in Frankfurt (`eu-de`);
- `WATSONX_URL=https://eu-de.ml.cloud.ibm.com`;
- an associated and usable Lite-plan watsonx.ai Runtime created in Frankfurt;
- permission to perform project-scoped foundation-model inference;
- project entitlement to the candidate model through Frankfurt;
- available quota and billing authorization.

Do not infer a project's region from the UUID. Confirm the region manually in
the IBM Cloud or watsonx project UI.

### 4.3 Safe readiness checklist

Before any paid test:

1. Confirm `WATSONX_LIVE_TEST` is exactly `1`.
2. Confirm `WATSONX_LIVE_ACK_CHARGES` is exactly `1`.
3. Confirm `WATSONX_API_KEY` is present without inspecting or displaying it.
4. Confirm `WATSONX_PROJECT_ID` is present.
5. Confirm the PaperScape project was created in Frankfurt (`eu-de`).
6. Confirm `WATSONX_URL` is explicitly supplied as
   `https://eu-de.ml.cloud.ibm.com`.
7. Confirm a Lite-plan watsonx.ai Runtime created in Frankfurt is associated
   with the project.
8. Confirm the candidate model appears in Resource Hub or Prompt Lab for that
   project.
9. Confirm the account has suitable project inference permissions.
10. Review the current account plan, remaining quota, rate limit, and billing
    authorization.
11. Confirm `GRANITE_MODEL_ID` is explicitly supplied and is exactly
    `ibm/granite-4-h-small` for Tier A.
12. Confirm the Git worktree contains no credential changes.

Readiness output may contain only:

- boolean presence/readiness flags;
- endpoint hostname or documented regional identifier;
- candidate model ID;
- SDK version;
- sanitized test-gate state.

It must not contain:

- API-key value;
- API-key length;
- API-key prefix or suffix;
- API-key hash;
- bearer or IAM tokens;
- credential object representations;
- provider/client representations;
- resolved Compose configuration containing secrets.

Do not run output-producing `docker compose config` after credentials are
present. Use `docker compose config --quiet`.

### 4.4 Validation timing

Configuration is not fully validated at startup:

- an empty API key leaves generation unavailable and returns a safe `503`;
- a non-empty API key enables the job endpoint;
- project, credential, endpoint, and model failures can occur later during
  provider construction or inference;
- provider-construction failure is converted to the safe persisted
  `llm_provider_error` code.

## 5. Live test opt-in and default behavior

Use this live-test module across two implementation stages:

```text
backend/tests/live/test_watsonx_live.py
```

Stage 1 adds only `test_watsonx_provider_connectivity`. Stage 2 adds
`test_live_research_map_service` only after Tier A succeeds, the default is
promoted, and offline regressions pass.

Both gates are mandatory:

```text
WATSONX_LIVE_TEST=1
WATSONX_LIVE_ACK_CHARGES=1
```

When either gate is absent, all live tests must skip before:

- constructing `Settings`;
- importing or constructing `WatsonxProvider`;
- importing the watsonx SDK;
- constructing `ModelInference` or `APIClient`;
- requesting an IAM token;
- making any network request.

When both gates are enabled:

- missing `WATSONX_API_KEY` must fail readiness;
- missing `WATSONX_PROJECT_ID` must fail readiness;
- missing `WATSONX_URL` must fail readiness;
- missing `GRANITE_MODEL_ID` must fail readiness;
- a candidate model other than `ibm/granite-4-h-small` must fail Tier A
  readiness;
- every readiness failure must occur before provider construction;
- output may reveal only the missing variable name or a sanitized readiness
  code;
- incomplete configuration must fail, not skip, because a configured paid run
  must not appear successful through skips.

Live tests must construct configuration with:

```python
Settings(_env_file=None)
```

This allows explicitly supplied process-environment variables while preventing
implicit reads of repository `.env` files.

At module collection time, do not instantiate `Settings`, read repository
`.env` files, import or construct `WatsonxProvider`, import or construct the SDK
client, instantiate `ModelInference` or `APIClient`, request an IAM token, or
make a network call. Settings, provider, SDK client, and fixture construction
must occur inside gated fixtures or test functions after authorization and
readiness checks.

Add:

```text
backend/tests/unit/test_watsonx_live_safety.py
```

Offline tests must prove:

- no gates: skip and zero `Settings` or provider construction;
- only `WATSONX_LIVE_TEST=1`: skip and zero construction;
- only `WATSONX_LIVE_ACK_CHARGES=1`: skip and zero construction;
- both gates set but API key missing: fail before construction;
- both gates set but project ID missing: fail before construction;
- explicit candidate model missing or incorrect: fail before construction.

Do not preserve an estimated collection total. Implementation can add two live
tests, live-gate safety tests, evaluator authorization tests, and manifest
validation tests. Record actual collected, passed, and skipped totals.

The default-test invariant is:

- all 424 existing tests continue passing;
- new live tests skip by default;
- safety tests pass offline;
- ordinary pytest makes zero network calls;
- ordinary pytest performs no paid provider or client construction.

## 6. Retry ownership, accounting, and cost ceilings

### 6.1 Verified retry layers

Keep these metrics separate:

- `research_map_service_calls`;
- `provider_generate_calls`;
- `corrective_retry_count`;
- `provider_transient_retry_count`;
- `sdk_retry_loop_iterations`;
- `sdk_raw_transport_request_count`;
- `sdk_transport_retry_count`;
- `ssl_fallback_request_count`;
- `authentication_request_count`, where observable.

The pinned SDK has two distinct retry mechanisms:

1. `max_retries=0` disables the `_with_retry` response decorator.
2. The SDK separately creates a `RetryTransport` with `retries=3` for statuses
   including `401`, `500`, `502`, `503`, `504`, `520`, `521`, and `524`.

`RetryTransport` runs up to `retries + 1` retry-loop iterations. With
`retries=3`, this means up to four loop iterations and four raw inference
transport requests per Chat invocation.

Sub-task 11A explicitly constructs credentials with `verify=True`. In the pinned
SDK this preserves certificate verification and makes SSL fallback ineligible.
A certificate error therefore fails safely and cannot add an unverified raw
request.

PaperScape's `WatsonxProvider` may invoke `chat` twice because it owns one
transient retry. `ResearchMapService` may call the provider twice because it owns
one corrective generation call.

### 6.2 Theoretical upper bounds after the Chat migration

Per `chat` invocation:

- up to four SDK retry-loop iterations;
- up to four raw inference transport requests;
- no SSL-fallback request.

Tier A:

- exactly one provider service call;
- up to two `chat` invocations because PaperScape owns one transient
  retry;
- up to eight SDK retry-loop iterations;
- up to eight raw inference transport requests;
- authentication and provider-construction requests are additional.

Tier B:

- up to two ResearchMap service calls because the service owns one corrective
  generation call;
- up to two provider `chat` invocations per service call;
- up to sixteen SDK retry-loop iterations;
- up to sixteen raw inference transport requests;
- authentication and provider-construction requests are additional.

These are conservative theoretical bounds in the current pinned path, not
approved paid-call ceilings. A TLS failure may not reach the inference service
and is therefore not necessarily a billable inference. Tier A execution must not
proceed merely because the live harness exists.

Before another Tier A execution, explicitly approve the migrated Chat path.

**Decision A — bounded SDK-client construction**

Implement and test a bounded SDK-client construction strategy that addresses:

- `RetryTransport` retries;
- SSL fallback;
- authentication requests;
- accurate attempt accounting.

Decision A must preserve normal TLS certificate validation. Explicitly
prohibited approaches are:

- disabling TLS verification;
- setting `verify=False` merely to bound attempts;
- suppressing certificate errors;
- patching installed site-packages;
- silently replacing the SDK transport;
- reducing security controls for cost predictability.

The bounded strategy must:

- preserve normal TLS certificate validation;
- use supported SDK/client configuration or a reviewed application-owned client
  factory;
- have offline tests;
- avoid logging prompts, responses, credentials, or tokens;
- produce measurable request ceilings;
- receive explicit approval before paid execution.

**Decision B — accept the pinned Chat ceiling**

Explicitly accept the pinned SDK's transport retry risk, document the theoretical
eight-raw-request Tier A bound plus additional authentication/construction
requests, review quota and billing, and approve the cost risk before executing
Tier A.

The previous Decision B approved one text-generation Tier A invocation with a
ten-request bound. That invocation was executed, failed, and consumed the
approval. It does not authorize the migrated Chat Tier A.

Do not patch installed site-packages or weaken TLS verification.

### 6.3 Observability requirements

Do not call a metric automatic unless the harness can observe it without
recording prompts, responses, credentials, or sensitive client state.

- `research_map_service_calls` are observable.
- `provider_generate_calls` are observable.
- `corrective_retry_count` is observable.
- `provider_transient_retry_count` is observable through approved provider
  instrumentation.
- `sdk_retry_loop_iterations` require approved transport instrumentation.
- `sdk_raw_transport_request_count` requires approved transport
  instrumentation.
- `sdk_transport_retry_count` requires approved transport instrumentation.
- `ssl_fallback_request_count` requires approved transport instrumentation.
- `authentication_request_count` may require separate approved instrumentation.
- An unobserved SDK request count must be reported as unknown, never zero.

Instrumentation must not change production retry behavior, generate additional
billable calls, or record prompts, raw responses, credentials, tokens, or
provider/client representations.

The three-paper evaluator must run papers serially. Exactly three papers are
required for acceptance; five is an optional expansion and hard cap. It must
stop on credential, project, endpoint, model-access, or retry-accounting
failures.

## Migrated Chat Tier A Paid-Run Decision

**Decision date:** 2026-07-30  
**Approved by:** Jadiel Bett  
**Status:** Approved for one invocation

### Decision

Approve one manually initiated Tier A connectivity test through the migrated
watsonx Chat API.

### Controls

- Run only `test_watsonx_provider_connectivity`.
- Select it explicitly with `-k provider_connectivity`.
- Use `ibm/granite-4-h-small` through a process-environment override.
- Use the Frankfurt `eu-de` endpoint.
- Limit output to 32 completion tokens.
- Do not rerun automatically or manually after failure without review.
- Tier B remains separately blocked.
- TLS certificate verification is explicitly enabled.
- SSL fallback is disabled.
- No installed SDK files are modified.
- The Lite-plan quota and model availability have been reviewed.

### Known theoretical bound

- Up to four raw inference requests per Chat invocation.
- `WatsonxProvider` may make two Chat invocations through its one transient
  retry.
- Tier A therefore has a theoretical maximum of eight raw inference requests.
- Authentication and provider-construction requests are additional.
- These are theoretical transport bounds and are not assumed to represent
  billable inference calls.

### Authorization boundary

This approval authorizes exactly one migrated Chat Tier A invocation.

It does not authorize:

- Tier B;
- the three-paper evaluator;
- repeated Tier A attempts;
- model-default promotion;
- prompt changes;
- SDK upgrades;
- disabling TLS verification;
- switching models or regions automatically.

This approval is consumed when the Tier A command is executed, regardless of
whether the test passes or fails.

### Execution record

- Executed on: 2026-07-30
- Outcome: passed
- Model: `ibm/granite-4-h-small`
- Region: Frankfurt (`eu-de`)
- Provider path: `ModelInference.chat`
- Output limit: 32 completion tokens
- Test selection: `-k provider_connectivity`
- Warnings: none
- Automatic or manual rerun performed: no
- Approval status: consumed
- Credentials or generated content recorded: no

### Tier A conclusion

The migrated watsonx Chat API path is compatible with the PaperScape provider
for the Frankfurt project and the explicitly selected
`ibm/granite-4-h-small` model.

This result authorizes the next bounded implementation stage:

- promote `ibm/granite-4-h-small` to the application default;
- update the corresponding configuration assertion and documentation;
- run all offline regression gates;
- add the separately gated Tier B ResearchMap validation;
- add the live evaluator and its authorization safeguards.

It does not authorize a Tier B paid call. Tier B requires a separate explicit
approval after its implementation and audit.

## 7. Validation tiers

### 7.1 Tier A — provider connectivity smoke

Purpose: prove that the current provider path can invoke the explicitly selected
candidate without modifying application data.

The migrated Chat Tier A passed once on 30 July 2026. Its paid-run approval was
consumed, and any rerun requires a separate explicit approval.

Required behavior:

1. Verify both authorization gates before application or SDK imports.
2. Verify all required live variables and the exact candidate before provider
   construction.
3. Set `GRANITE_MODEL_ID=ibm/granite-4-h-small` explicitly in the process
   environment.
4. Construct `Settings(_env_file=None)`.
5. Construct the real `WatsonxProvider`.
6. Submit one harmless prompt unrelated to application or paper data.
7. Use `max_tokens=32` and `temperature=0`, which the current provider maps to
   `max_completion_tokens=32` and `temperature=0` exactly.
8. Assert that a non-empty string is returned.
9. Record only sanitized, actually observable metrics.

Tier A must prove:

- credentials authenticate;
- the Frankfurt project and `https://eu-de.ml.cloud.ibm.com` endpoint work
  together;
- the PaperScape project is entitled to access the candidate model in
  Frankfurt;
- the installed SDK can construct the client;
- `ModelInference.chat` works with the candidate model;
- the migrated Chat parameter shape is accepted;
- strict assistant response parsing returns a usable string;
- retry ceilings are respected;
- no secret is logged.

Sanitized Tier A metrics:

- SDK version;
- candidate model ID;
- endpoint hostname;
- provider construction outcome;
- elapsed construction time;
- elapsed inference time;
- provider-generate call count;
- provider transient-retry count, if instrumented;
- SDK retry-loop iterations only if approved transport instrumentation makes
  them observable;
- raw transport-request count only if approved transport instrumentation makes
  it observable;
- SDK transport-retry count only if approved transport instrumentation makes it
  observable;
- SSL-fallback request count only if approved transport instrumentation makes it
  observable;
- authentication-request count, if observable;
- output character count;
- final pass/fail code.

Unknown loop-iteration, raw-request, SSL-fallback, SDK retry, or authentication
counts must be reported as unknown rather than zero. The approved Section 6
decision defines the paid request ceiling.

Do not store the prompt or generated text. Tier A must not write application
records, SQLite rows, or result files.

### 7.2 Tier B — service-level live ResearchMap validation

Purpose: validate the real model against the existing ResearchMap prompt,
schemas, context selection, and grounding rules.

Use:

- the existing synthetic `evals/fixtures/research_map_extraction.json`;
- the current `backend/app/prompts/research_map.txt`;
- the real `ResearchMapService`;
- the real `WatsonxProvider`;
- the same explicitly selected candidate model;
- in-memory results by default.

Verify automatically:

- the real prompt template is used;
- model output parses as JSON;
- the internal schema validates;
- exactly three findings exist;
- every required grounded statement has evidence;
- chunk IDs reference selected fixture chunks;
- evidence pages match the referenced chunks;
- excerpts occur within normalized chunk text;
- findings are distinct;
- limitations exist;
- confidence is `high` or `partial`;
- the public disclaimer is canonical;
- observable service, corrective, provider transient, retry-loop, raw-request,
  SSL-fallback, SDK retry, and authentication counts stay within the separately
  approved Section 6 ceilings.

If the first output is invalid, record the safe issue-code set and allow the
existing single corrective call. Do not store the invalid raw output.

Tier B fails if:

- a provider/access error occurs;
- an observable attempt exceeds the approved retry ceiling;
- a required attempt metric is unavailable under the approved instrumentation
  decision;
- the second response remains invalid;
- any evidence reference fails grounding;
- the output cannot support exactly three findings and at least one limitation.

### 7.3 Tier C — full Compose/browser workflow

Purpose: prove the user-facing vertical slice with one approved primary paper.

Flow:

```text
Flutter Web
→ PDF upload
→ extraction
→ job creation
→ real WatsonxProvider
→ polling
→ persisted ResearchMap
→ browser display
```

Credentials remain backend-only. The candidate model must already have passed
Tier A, been promoted to the application default, and passed all post-change
offline gates before Tier C.

Persistence after restart is verified through the backend research-map endpoint
using the recorded paper ID. The current frontend has no paper-history or
automatic restoration feature, so Tier C must not claim automatic frontend
history restoration.

## Tier C ResearchMap Diagnostic Rerun Decision

**Approved by:** Jadiel Bett  
**Date:** 2026-07-30  
**Status:** Approved for one invocation

Approve one additional ResearchMap job using the already persisted extraction.

Purpose:

- identify only the safe validation issue codes produced by the initial and
  corrective model outputs.

Controls:

- no PDF re-upload;
- one job-creation request;
- no prompt change;
- no weakened validation;
- no raw model output logging;
- no source-text or excerpt logging;
- no automatic or manual rerun after failure without review;
- the existing single corrective generation call remains the only bounded
  application retry.

This approval is consumed when the job is submitted, whether it passes or
fails.

## 8. Demo-paper selection and three-paper baseline

### 8.1 Required set

Task acceptance requires exactly three approved papers:

- one primary demo paper;
- two supporting papers;
- at least two subject areas across the set.

Up to five papers may be used as an optional expansion. Five is the hard safety
cap, not a mandatory target.

Preferred subject areas:

- agriculture;
- public health;
- climate;
- education;
- accessible technology.

### 8.2 Selection criteria

Every paper must be:

- open access;
- permitted for the intended demo and evaluation use;
- backed by a source URL and licence-evidence URL;
- selectable text rather than image-only pages;
- modest in file size;
- structured reliably enough for current extraction;
- based on a clear research question;
- able to support at least three defensible findings;
- explicit about at least one limitation;
- understandable to non-specialist judges;
- free of sensitive personal data;
- not dependent on complex figures for its central findings.

The primary paper is approved only after:

1. licence and excerpt-use evidence are reviewed;
2. dry extraction returns valid page-aware chunks;
3. the central question, at least three findings, and a limitation can be
   manually located in extracted text;
4. important evidence can be understood without interpreting a complex figure;
5. the paper is suitable for a short live demonstration.

### 8.3 Manifest fields

Use this exact top-level shape before rights-approved papers are added:

```json
{
  "schema_version": 1,
  "papers": []
}
```

Each paper object must contain:

- paper ID;
- title;
- authors;
- source URL;
- licence;
- licence-evidence URL;
- retrieval date;
- local filename;
- subject area;
- primary-demo flag;
- expected high-level findings;
- known limitations;
- selection rationale.

The JSON field names are:

```text
paper_id
title
authors
source_url
licence
licence_evidence_url
retrieved_on
local_filename
subject_area
acceptance
primary_demo
expected_high_level_findings
known_limitations
selection_rationale
rights_review.status
rights_review.excerpt_use_reviewed
```

Manifest validation must require:

- exactly three papers with `acceptance=true`;
- exactly one accepted paper with `primary_demo=true`;
- at least two subject areas across accepted papers;
- no more than five total papers;
- unique paper IDs, local filenames, and source URLs;
- non-blank licence and licence-evidence URL values;
- basename-only local filenames;
- no absolute local paths, path separators, or `..`;
- every resolved local file path remains below `evals/live/papers`;
- no real paper entry before `rights_review.status` is `approved` and
  `rights_review.excerpt_use_reviewed` is true;
- no secrets or machine-specific absolute paths.

The primary demo paper is one of the three acceptance papers. Up to two
non-acceptance papers may be added only as the optional five-paper expansion.

Do not commit PDFs. Local paper files belong under an ignored
`evals/live/papers` path.

Open access does not automatically authorize unrestricted redistribution or
excerpt reuse. Licence and excerpt-use evidence must be reviewed separately.

## 9. Live evaluator and result-storage policy

### 9.1 Evaluation execution

`evals/run_live_eval.py` will process the three-paper set serially through:

- real `ExtractionService`;
- temporary file-backed SQLite;
- real extraction, job, and ResearchMap stores;
- real `ResearchMapJobRunner`;
- real `ResearchMapService`;
- real `WatsonxProvider`.

The evaluator defaults to one paper for the first paid run. Expansion to all
three requires the first paper to complete successfully. Expansion beyond three
requires explicit operator intent and can never exceed five.

The evaluator is a Stage 2 addition and must independently require all three
authorizations:

```text
WATSONX_LIVE_TEST=1
WATSONX_LIVE_ACK_CHARGES=1
--ack-charges
```

When any authorization is absent, it must abort before `Settings` construction,
provider or SDK import/construction, PDF extraction, database creation, or any
network request. It must reject limits above five, process papers serially, and
stop the batch on access or configuration failure.

### 9.2 Storage controls

By default:

- complete live ResearchMap output remains in memory;
- no result JSON or Markdown is written;
- no raw SDK response is stored;
- no prompt is stored;
- no failed raw model output is stored.

When local output is explicitly requested:

- write only below ignored `evals/live/results/private`;
- do not commit automatically;
- include validated ResearchMap output only, never raw SDK envelopes;
- exclude prompts, credentials, bearer tokens, project identifiers where not
  needed, and provider/client representations.

Committed scorecards contain only sanitized metrics and human-review scores. A
generated map containing source excerpts may be committed only after the paper
licence and excerpt policy have been reviewed.

Use these local paths:

```text
evals/live/papers/
evals/live/results/private/
```

Plan `evals/live/.gitignore` exactly as:

```gitignore
papers/**
!papers/.gitkeep

results/private/**
!results/private/.gitkeep

*.tmp
```

Complete maps, generated JSON, generated Markdown, prompts, raw SDK output, and
private reviewer material belong only under `results/private`. Sanitized
schemas, examples, and approved scorecards may be committed outside
`results/private`. Do not use broad rules such as `results/*.json` or
`results/*.md`.

## 10. Evaluation scorecard

For each paper, record:

| Metric | Method |
|---|---|
| Extraction page count | Automatic |
| Extraction chunk count | Automatic |
| Final job status | Automatic |
| ResearchMap service calls | Automatic |
| Provider generate calls | Automatic |
| Corrective retries | Automatic |
| Provider transient retries | Automatic only with injected sleep or approved provider instrumentation |
| SDK retry-loop iterations | Automatic only with approved SDK transport instrumentation/configuration |
| Raw inference transport requests | Automatic only with approved SDK transport instrumentation/configuration |
| SDK transport retries | Automatic only with approved SDK transport instrumentation/configuration |
| SSL-fallback requests | Automatic only with approved SDK transport instrumentation/configuration |
| Authentication requests | Record only where separately observable |
| Provider construction time | Automatic |
| Generation elapsed time | Automatic |
| Total processing time | Automatic |
| JSON/schema validity | Automatic |
| Exactly-three-findings validity | Automatic |
| Evidence chunk-ID validity | Automatic |
| Evidence page validity | Automatic |
| Normalized excerpt validity | Automatic |
| Limitation presence | Automatic |
| Canonical disclaimer | Automatic |
| Confidence distribution | Automatic |
| UI rendering success | Human review |
| Claim support against cited excerpts | Human review |
| Numerical fidelity | Human review |
| Important-limitation recall | Human review |
| Unsupported-claim count | Human review |
| Visible failure or warning | Human review |
| Reviewer notes | Human review |

An unobservable attempt or retry count is recorded as `unknown`, not zero.
Scorecards must identify the approved instrumentation/configuration used for
every non-public metric.

Manual reviewers assess whether claims are supported by the uploaded paper.
They do not claim that PaperScape or the review establishes scientific
correctness.

Numerical review must compare:

- values;
- units;
- signs and directions;
- denominators;
- ranges;
- percentages;
- statistical qualifiers;
- correlation/causation wording;
- uncertainty language.

Limitation recall requires comparison with the paper's important stated
limitations. Automatic presence of one limitation is necessary but not
sufficient for manual recall success.

## 11. Failure-path validation

Use real paid calls only for the successful compatibility and generation paths.
Use existing offline tests or documented simulations for wasteful or unsafe
failures.

| Failure | Validation policy | Expected application outcome |
|---|---|---|
| Missing API key | Existing credential-free API/Compose test | `503 generation_unavailable`, no job created |
| Empty project ID with non-empty API key | Existing dependency/job-runner behavior plus offline test | Job creation is permitted; provider construction later fails; job persists `llm_provider_error` |
| Invalid API key | Mocked SDK classification; do not deliberately call live | Non-transient provider failure |
| Wrong project ID | Mocked provider-construction failure; do not deliberately call live | `llm_provider_error` |
| Inaccessible/unknown model | Mocked 4xx classification unless encountered naturally | Non-transient `llm_provider_error` |
| Quota/rate limit | Mocked 429 behavior unless encountered naturally | PaperScape may perform one provider retry; pinned transport behavior is accounted separately |
| SDK transport status | Pinned-source inspection and approved instrumentation | `RetryTransport` may retry `401`, `500`, `502`, `503`, `504`, `520`, `521`, and `524` |
| Timeout/network failure | Existing mocked timeout coverage plus pinned transport review | Recognized errors may receive one provider retry; SDK transport behavior can add attempts |
| Exhausted `RemoteProtocolError` | Pinned-source inspection and offline classification test | May emerge through `ExceptionGroup`; current PaperScape classification can treat the group as non-transient |
| Malformed JSON | Existing ResearchMap tests and optional natural Tier B observation | One corrective call |
| Invalid evidence | Existing grounding tests and optional natural Tier B observation | One corrective call |
| Corrective exhaustion | Existing mocked service/job-runner tests | `map_generation_failed` |

Never consume quota merely to demonstrate an already covered error path.

Keep the safe application codes separated by layer:

- `generation_unavailable`: request rejected before job creation when generation
  is disabled by a missing API key;
- `llm_provider_error`: provider construction or inference failure persisted on
  a job;
- `map_generation_failed`: JSON, schema, or grounding failure after the
  corrective generation call.

## 12. Browser acceptance walkthrough

1. Confirm Tier A and Tier B passed.
2. Confirm the application default was promoted only after Tier A.
3. Confirm post-promotion backend, frontend, and offline gates passed.
4. Put valid backend-only Compose credentials in ignored root `.env`.
5. Run `docker compose config --quiet`.
6. Start Compose with `docker compose up -d --build --wait`.
7. Confirm both health endpoints.
8. Open `http://localhost:8080`.
9. Upload the approved primary demo PDF.
10. Confirm filename, page count, and chunk count.
11. Start research-map generation.
12. Observe pending/running states where they are visible.
13. Confirm successful completion.
14. Confirm a non-empty research question.
15. Confirm exactly three findings.
16. Inspect evidence excerpts.
17. Confirm one-based page numbers and real chunk IDs.
18. Confirm confidence labels.
19. Confirm limitations.
20. Confirm the canonical disclaimer.
21. Confirm no browser console errors.
22. Confirm no secret or backend-only watsonx configuration appears in network
    responses or frontend assets.
23. Record total processing time and visible warnings.
24. Stop Compose without deleting the volume.
25. Restart Compose.
26. Retrieve the persisted ResearchMap through the backend endpoint using the
    recorded paper ID.
27. Record that persistence succeeded without claiming frontend history
    restoration.

Screenshots must show only the application UI and approved paper content. Do not
capture terminals, environment configuration, tokens, project settings, or
browser request headers.

## 13. Prompt and baseline-change policy

Do not edit the prompt merely to make one live paper pass.

Classify each failure first as:

- extraction;
- context selection;
- credential or project access;
- endpoint/region mismatch;
- model access;
- SDK/API incompatibility;
- malformed JSON;
- schema validation;
- grounding validation;
- latency;
- prompt quality.

Prompt changes are outside the initial Sub-task 11 implementation. If later
approved, they require:

- focused ResearchMap unit tests;
- offline evaluation review;
- deliberate expected-baseline handling;
- before/after live results on the same papers;
- preserved evidence-grounding requirements;
- no weakening of exactly-three-findings, limitation, disclaimer, or evidence
  invariants.

The text-generation API deprecation must be recorded as a migration risk. It
does not authorize an automatic Chat API migration during this task.

## 14. Exact expected files

### 14.1 Stage 1 — pre-Tier-A harness implementation

```text
docs/subtask-11-live-watsonx-validation-plan.md
docs/demo-paper-selection.md
backend/tests/live/__init__.py
backend/tests/live/test_watsonx_live.py          # Tier A only
backend/tests/unit/test_watsonx_live_safety.py
evals/live/README.md
evals/live/paper_manifest.json
evals/live/.gitignore
```

This planning step creates only the first file.

Stage 1 is approved only for safe authorization helpers, offline gate tests, the
Tier A-only live test, the manifest schema, ignore rules, and paper-selection
documentation. Do not create `evals/run_live_eval.py` and do not add Tier B in
Stage 1.

Before Tier A, do not change:

```text
backend/app/config.py
backend/tests/unit/test_config.py
backend/app/services/llm_provider.py
.env.example
backend/.env.example
docs/data-model.md
docs/vertical-slice-plan.md
frontend/README.md
docs/bob-usage-log.md
docker-compose.yml
backend/app/prompts/research_map.txt
frontend/lib/
LLMProvider interface
job orchestration
runtime infrastructure
```

### 14.2 Stage 2 — only after Tier A succeeds

Permitted Stage 2 additions and changes are:

```text
backend/tests/live/test_watsonx_live.py          # add Tier B
evals/run_live_eval.py
evaluator safety tests
backend/app/config.py
backend/tests/unit/test_config.py
backend/app/services/llm_provider.py             # verified documentation correction only
.env.example
backend/.env.example
docs/data-model.md
docs/vertical-slice-plan.md
frontend/README.md
docs/bob-usage-log.md
```

Stage 2 may add the Tier B live test and evaluator, promote the model default,
update the config assertion, and update environment examples and affected
documentation. The provider documentation correction and Chat migration were
completed separately in Sub-task 11A. Run all offline regressions after Stage 2
changes and before executing Tier B.

The deadline-bounded Stage 2 implementation promotes the default and adds only
`test_live_research_map_service`. The Tier B harness is implemented but has not
been executed. It requires a separate paid-run decision. The three-paper
evaluator remains deferred and is not part of this bounded change. Successful
Tier B remains a prerequisite for the real Compose/browser workflow.

Sub-task 11A must also fix stale wording in `docs/vertical-slice-plan.md` that
said:

- the provider calls `ModelInference.generate`;
- required watsonx credentials are validated at startup.

### 14.3 Explicitly unchanged

Do not modify:

```text
docker-compose.yml
backend/app/prompts/research_map.txt
frontend/lib/
LLMProvider interface
job orchestration
runtime infrastructure
```

unless a verified blocker receives a separately documented decision.

## Tier B Paid-Run Decision

**Decision date:** 2026-07-30  
**Approved by:** Jadiel Bett  
**Status:** Approved for one Tier B invocation

### Decision

Approve one manually initiated service-level ResearchMap validation using the
real watsonx Chat provider and the existing synthetic extraction fixture.

### Controls

- Run only `test_live_research_map_service`.
- Select it explicitly with `-k research_map_service`.
- Use `ibm/granite-4-h-small`.
- Use the Frankfurt `eu-de` endpoint.
- Keep TLS certificate verification enabled.
- Do not rerun after failure without review.
- Do not print or persist generated model output.
- Do not begin the browser workflow unless Tier B succeeds.
- Do not run a three-paper evaluator.
- Do not modify installed SDK files.

### Known theoretical bound

- `ResearchMapService` may make two provider calls through its one corrective
  retry.
- `WatsonxProvider` may make two Chat invocations for each provider call through
  its transient retry.
- The SDK may make up to four raw inference requests per Chat invocation.
- Tier B therefore has a theoretical maximum of sixteen raw inference requests.
- Authentication and provider-construction traffic is additional.
- These are theoretical transport bounds and are not assumed to represent
  billable inference calls.

### Authorization boundary

This approval authorizes exactly one Tier B invocation.

It does not authorize:

- Tier A reruns;
- repeated Tier B attempts;
- the three-paper evaluator;
- the full browser workflow;
- model or region switching;
- prompt changes;
- weakened validation.

The approval is consumed when the Tier B command executes, whether it passes or
fails.

### Execution record

- Executed on: 2026-07-30
- Outcome: passed
- Test: `test_live_research_map_service`
- Selection: `-k research_map_service`
- Model: `ibm/granite-4-h-small`
- Region: Frankfurt (`eu-de`)
- Result: `1 passed, 1 deselected`
- Execution time: `11.60s`
- Automatic or manual rerun: no
- Generated ResearchMap persisted or printed: no
- Credentials, project identifiers, prompts, and raw responses recorded: no
- Approval status: consumed

### Tier B conclusion

The real watsonx Chat provider successfully generated a ResearchMap that passed
the existing PaperScape schema and evidence-grounding validation against the
controlled extraction fixture.

This authorizes preparation of one manually controlled Tier C browser workflow
using an approved open-access PDF. It does not authorize repeated Tier B calls,
the three-paper evaluator, or unrelated paid model testing.

## 15. Verification commands

### 15.1 Default offline gates

From the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pip check
backend\.venv\Scripts\python.exe -m pytest backend\tests --collect-only -q
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe evals\run_evals.py

Push-Location frontend
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test --reporter expanded
Pop-Location

git diff --check
git status --short
```

After live tests are added, ordinary pytest must report the actual collected,
passed, and skipped totals. All existing tests must continue passing, the two
live tests must skip by default, and no network call may occur.

### 15.2 Explicit Tier A and Tier B gates

Provision `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` in the current process by a
private method that does not echo them. Then set only the non-secret controls:

```powershell
$env:WATSONX_LIVE_TEST = '1'
$env:WATSONX_LIVE_ACK_CHARGES = '1'
$env:WATSONX_URL = 'https://eu-de.ml.cloud.ibm.com'
$env:GRANITE_MODEL_ID = 'ibm/granite-4-h-small'

backend\.venv\Scripts\python.exe -m pytest `
  backend\tests\live\test_watsonx_live.py `
  -k provider_connectivity -q -rs
```

This command selects Tier A only. During Stage 1 the file contains no Tier B
test. Do not execute Tier A until the Section 6 RetryTransport and paid-attempt
decision is explicitly approved.

Only after Tier A succeeds, the model default is promoted, and every offline
gate passes, run Tier B alone:

```powershell
backend\.venv\Scripts\python.exe -m pytest `
  backend\tests\live\test_watsonx_live.py `
  -k research_map_service -q -rs
```

The Tier A command must never collect or execute Tier B as an active paid test.
Explicit pytest markers may supplement `-k`, but the documented command must
select exactly one tier.

After testing, clear all live variables, including the secret and project ID,
without printing their values.

### 15.3 Evaluator

Start with one paper:

```powershell
backend\.venv\Scripts\python.exe evals\run_live_eval.py `
  --manifest evals\live\paper_manifest.json `
  --limit 1 `
  --ack-charges
```

The evaluator must also verify both environment authorization gates
independently. It aborts before Settings, provider/SDK construction, extraction,
database creation, or networking when either gate or `--ack-charges` is absent.
It defaults to one paper, rejects values above five, processes serially, and
stops on access or configuration failure. Expand to exactly three only after the
first paper succeeds.

### 15.4 Compose/browser tier

```powershell
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-WebRequest http://localhost:8080/health
```

After the browser walkthrough:

```powershell
docker compose down
docker compose up -d --wait
docker compose ps
```

Verify the persisted map through the backend endpoint, then:

```powershell
docker compose down
```

Do not use `docker compose down -v` during validation.

## 16. Costs, quota, and security safeguards

### 16.1 Cost controls

- Require both live opt-in gates.
- Require `--ack-charges` independently for the evaluator.
- Require explicit candidate-model override for Tier A.
- Use a 32-token Tier A output ceiling.
- Preserve the current 1500-token ResearchMap ceiling.
- Reconfirm the Section 6 `RetryTransport`, authentication, and
  attempt-accounting decision before another Tier A execution.
- Treat eight raw inference transport requests for Tier A and sixteen for Tier B,
  excluding authentication/construction requests, as conservative theoretical
  bounds rather than approved paid ceilings.
- Count service calls, retry-loop iterations, raw transport requests, transport
  retries, SSL-fallback requests, and authentication requests only where
  approved instrumentation makes each count observable.
- Report unobservable request and attempt counts as unknown, never zero.
- Abort when an approved, observable ceiling is exceeded.
- Under Decision A, preserve normal TLS certificate validation; never use
  `verify=False`, suppressed certificate errors, or reduced security controls to
  make cost predictable.
- Run papers serially.
- Default the evaluator to one paper.
- Require exactly three papers for acceptance.
- Cap optional expansion at five.
- Stop immediately on access/configuration failures.
- Review current plan, quota, rate limit, and billing authorization first.
- Never run live tests in ordinary pytest or CI.

### 16.2 Security controls

- Keep credentials only in process environment or ignored local `.env`.
- Never commit credentials.
- Never pass watsonx values to Flutter.
- Never print secret presence details beyond a boolean.
- Never store prompts or raw SDK responses.
- Never serialize provider/client objects.
- Persist only safe application error codes.
- Use `docker compose config --quiet` with configured credentials.
- Scan logs in memory and report only pass/fail; do not print a matching secret
  line.
- Inspect browser responses and compiled assets for backend-only variable names
  and values.
- Keep local PDFs and live outputs ignored.
- Review licence and excerpt policy before committing generated map content.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| A withdrawn model is used accidentally | The application default was promoted to `ibm/granite-4-h-small` only after migrated Tier A succeeded. |
| Candidate model lacks migrated Chat compatibility | Stop and require a new provider decision. |
| Candidate model is unavailable to the project | Confirm Resource Hub/Prompt Lab access, then stop on Tier A failure. |
| Frankfurt project, Runtime, and endpoint regions differ | Create both the project and Lite Runtime in Frankfurt and use `https://eu-de.ml.cloud.ibm.com`; do not infer region from UUID. |
| A Frankfurt call fails | Classify and verify whether the blocker is Frankfurt-specific; do not automatically switch regions. Dallas requires a separate, evidence-backed fallback decision. |
| Kenya latency is assumed rather than measured | Record actual construction, inference, and workflow latency from Kenya during the approved live validation. |
| SDK performs construction requests | Pinned source confirms authentication during construction; gate every import/construction path and instrument authentication separately where approved. |
| Hidden SDK transport retries increase requests | Four retry-loop iterations can produce four raw inference requests per Chat invocation; Tier A and Tier B conservative bounds are eight and sixteen respectively, excluding authentication/construction requests. Any further paid run requires a separate decision. |
| Cost bounding weakens TLS security | Credentials explicitly use `verify=True`; never use `verify=False`, suppress certificate errors, patch site-packages, silently replace transport, or reduce security controls. |
| JSON or grounding fails | Allow the existing single corrective call; do not weaken validation. |
| One paper drives prompt overfitting | Classify failures first and require multi-paper evidence before prompt work. |
| UI polling reaches its two-minute timeout | Record the visible failure; do not silently change timeouts. |
| Generated excerpts create redistribution concerns | Keep output local until licence and excerpt policy review. |
| Secrets appear in diagnostics | Emit booleans and sanitized codes only; never print raw matches. |
| Deprecated text-generation API is removed later | Sub-task 11A removes the production dependency; preserve the recorded 14 March 2027 lifecycle evidence. |

## 18. Rollback strategy

Before Tier A succeeds, rollback consists only of removing the live-test and
evaluation harness changes. The application default remains unchanged.

After Tier A succeeds and the default is promoted:

- revert the model-default/config documentation change if the post-promotion
  offline gates fail;
- record that reverting restores a known-withdrawn default and therefore
  disables a usable live baseline;
- do not silently substitute another model;
- do not delete the Compose volume during rollback;
- remove local ignored PDFs and result files only when explicitly intended;
- preserve sanitized scorecards and blocker documentation needed for audit.

No external rollback can undo consumed inference quota. Cost gates and bounded
attempts are therefore mandatory before execution.

## 19. Implementation order

1. Commit this plan as the only planning artifact.
2. Implement only the Stage 1 authorization helpers, offline gate tests, Tier
   A-only test, manifest schema, ignore rules, and paper-selection documentation.
3. Verify ordinary collection and pytest execution skip Tier A before Settings
   or provider construction and perform zero network calls.
4. Record actual collected, passed, and skipped totals.
5. Audit Sub-task 11A, pass all offline gates, and explicitly approve the
   migrated Chat Decision B from Section 6. The new decision must accept the
   conservative eight-request Tier A bound plus additional authentication and
   construction traffic.
6. Confirm credentials, the Frankfurt project, the Frankfurt Lite Runtime
   association, the `eu-de` endpoint, model visibility, project entitlement,
   permission, quota, billing readiness, and the approved attempt ceiling
   without printing secrets.
7. Only then run Tier A alone with the explicit Granite 4 environment override.
8. If Tier A fails, record the blocker and stop.
9. If Tier A succeeds, begin Stage 2: update the application model default,
   config assertion, verified provider documentation, environment examples, and
   affected documentation as one bounded change.
10. Add Tier B, `evals/run_live_eval.py`, and their offline safety tests.
11. Run all offline backend, frontend, evaluator, manifest, and evaluation gates.
12. Run Tier B alone with the synthetic `ExtractionResult` fixture.
13. If Tier B fails, classify the failure and stop before prompt changes.
14. Select and document exactly three rights-approved acceptance papers across
    at least two subjects.
15. Run the evaluator on one paper with both gates and `--ack-charges`.
16. Expand to all three only after the first succeeds.
17. Complete human scorecards.
18. Run Tier C with the approved primary paper.
19. Verify backend persistence after restart.
20. Perform secret, log, browser, and repository-hygiene checks.
21. Record actual test totals, measured latency from Kenya, observable
    retry-loop iterations, raw requests, SSL-fallback requests, authentication
    requests, unknown unobservable counts, model/API risks, and final acceptance
    status.

## 20. Acceptance criteria

Sub-task 11 is complete only when:

- Stage 1 remained limited to authorization helpers, offline gate tests, the
  Tier A-only test, manifest/ignore scaffolding, and paper-selection
  documentation.
- The migrated provider explicitly preserved TLS certificate verification and
  disabled the pinned SDK's unverified SSL fallback.
- A new Chat-path Decision B explicitly accepted the conservative
  eight-raw-request Tier A bound, additional authentication/construction
  traffic, and associated quota/billing risk before another paid execution.
- Tier A succeeds with `ibm/granite-4-h-small` supplied as an explicit process
  override.
- The PaperScape project and associated Lite-plan watsonx.ai Runtime were both
  created in Frankfurt (`eu-de`) and validation used
  `https://eu-de.ml.cloud.ibm.com`.
- The pinned SDK, `ModelInference`, Chat API, project, endpoint, migrated
  parameters, and candidate model are proven compatible together.
- Tier A proves project entitlement and Chat compatibility in
  Frankfurt.
- The application default is promoted only after Tier A succeeds.
- All existing backend tests continue passing after the promotion.
- New live tests skip by default and make zero network calls during ordinary
  pytest.
- Both enabled gates with incomplete readiness fail before provider
  construction rather than skip.
- Tier B succeeds with the current prompt, schema, and grounding validation.
- One approved primary paper completes the full Compose/browser Tier C workflow.
- Exactly three papers have completed manual scorecards across at least two
  subject areas.
- Every successful ResearchMap contains exactly three findings, evidence,
  limitations, and the canonical disclaimer.
- Evidence can be traced to real chunks, pages, and source excerpts.
- ResearchMap service calls, provider generate calls, corrective retries, and
  observable provider retries, SDK retry-loop iterations, raw transport
  requests, SDK transport retries, SSL-fallback requests, and authentication
  requests are recorded.
- Unobservable SDK, SSL-fallback, or authentication request counts are recorded
  as unknown, never zero.
- The conservative theoretical raw-request bounds are recorded as eight for
  Tier A and sixteen for Tier B, excluding authentication/provider-construction
  requests; they are not represented as approved paid-call ceilings.
- Actual latency from Kenya and final job status are recorded.
- Dallas is used only after a verified Frankfurt-specific compatibility blocker
  and a separate explicit fallback decision; no failed call automatically
  switches regions.
- No credentials appear in Git, Flutter, logs, screenshots, stored outputs, or
  captured diagnostics.
- Frontend tests and analysis pass.
- The offline ResearchMap evaluation passes.
- Paper rights evidence and retrieval metadata are documented.
- Complete live maps remain uncommitted unless licence and excerpt policy are
  approved.
- The evaluator independently requires both live gates and `--ack-charges`.
- The completed Chat migration and the text-generation API's 14 March 2027
  removal date are recorded.
- Failures remain safe and readable.

## 21. Final status

1. The offline eval-baseline requirement is already satisfied.
2. Migrated Chat Tier A passed once in Frankfurt with
   `ibm/granite-4-h-small`; its approval is consumed.
3. The application now defaults to `ibm/granite-4-h-small`.
4. The separately gated Tier B harness is implemented but has not been
   executed.
5. Tier B requires a separate paid-run decision, and a successful Tier B remains
   a prerequisite for the real Compose/browser workflow.
6. Provider construction performs network authentication in the pinned SDK.
7. The migrated provider explicitly enables certificate verification, disabling
    the pinned SDK's unverified SSL fallback.
8. Sub-task 11A replaces the deprecated production text-generation request with
    `ModelInference.chat` while preserving the public provider interface.
9. Any further paid live run requires a separate explicit retry,
   authentication, attempt-accounting, and cost-control decision.
10. The current conservative theoretical bounds are eight raw inference
    transport requests for Tier A and sixteen for Tier B, excluding
    authentication and provider-construction requests.
11. TLS certificate verification may not be weakened.
12. Frankfurt (`eu-de`) is selected with
     `https://eu-de.ml.cloud.ibm.com`; the PaperScape project and associated
     Lite-plan Runtime must both be created there.
13. Credential readiness, project entitlement, candidate-model access, and Chat
     compatibility remain live prerequisites.
14. Actual latency from Kenya must be measured rather than assumed.
15. Dallas is a fallback only for a verified Frankfurt-specific compatibility
     blocker, and a failed call must never switch regions automatically.
16. Audience adaptation begins only after Tier A, Tier B, Tier C, and the
     three-paper scorecard succeed.

## 22. Tier C diagnostic preparation

The approved real nine-page selectable-text PDF extracted successfully with
`page_count=9` and `chunk_count=148`. The first real background ResearchMap job
then failed safely with `map_generation_failed`; the exact schema or grounding
validation causes were not observable.

Deadline-bounded diagnostics now preserve and log only allowlisted, sorted
ResearchMap validation issue-code names for the initial and corrective attempts.
The job runner records the same safe codes while continuing to persist only
`map_generation_failed`. No prompt or validation rule changed, and no paid
diagnostic rerun has occurred.

## 23. Tier C evidence-normalization preparation

The safe diagnostics established that the first real generation attempt failed
only `EXCERPT_NOT_FOUND`, while its corrective attempt failed
`INVALID_SCHEMA`. A conservative evidence-containment normalization was added
for harmless PDF and text-serialization representation differences only.

Chunk ID and page matching remain exact, and normalized excerpts must remain
contiguous substrings of their referenced source chunks. No fuzzy, semantic, or
paraphrase matching was introduced. No paid diagnostic rerun occurred during
implementation.

### Boundary-integrity correction

A follow-up audit found that bare substring containment could accept truncated
evidence beginning after a sign or qualifier, ending before a percentage or
unit, or stopping within a number, apostrophe/hyphen-joined word, or confidence
interval. Deterministic boundary guards now reject those cases while retaining
exact contiguous normalized matching and the established long-excerpt behavior.
No fuzzy or semantic similarity was introduced, and no paid rerun occurred.

## 24. Tier C deterministic evidence-span preparation

Conservative normalization did not resolve the real `EXCERPT_NOT_FOUND`
result, and the corrective attempt again returned `INVALID_SCHEMA`. That
failure path is now removed from model control.
After bounded chunk selection, the backend deterministically creates exact
source spans of at most 300 characters in document order and assigns stable
opaque IDs (`E0001`, `E0002`, ...). The model returns only those IDs; the backend
resolves each valid ID to the original chunk ID, page, and exact span text when
constructing the unchanged public `ResearchMap`.

Unknown or case-mismatched IDs fail with the safe allowlisted
`UNKNOWN_EVIDENCE_ID` diagnostic. The corrective attempt lists only valid
evidence IDs. The former evidence-normalization and substring-boundary path is
no longer active; no fuzzy, semantic, normalized, or model-authored excerpt
matching remains. Prompt safety rules, model settings, provider behavior,
corrective retry count, and public schemas/API responses are unchanged. No paid
or live rerun occurred during implementation.

## 25. Tier C claim-to-evidence specificity preparation

The first real evidence-ID ResearchMap job succeeded operationally, but manual
semantic review rejected the result. All three findings reused one generic
association span while introducing subgroup thresholds, individual outcomes,
and an exception that the selected evidence did not directly support.

Two deterministic validation safeguards were added. Distinct findings may no
longer reuse the same complete evidence-ID set, and digit-based quantities,
comparators, ranges, percentages, confidence intervals, and quantitative number
words from zero through twenty must occur in the finding's selected exact
evidence spans under conservative surface normalization. Only safe
`DUPLICATE_FINDING_EVIDENCE` and `UNSUPPORTED_CLAIM_DETAIL` issue codes are
logged.

This is a bounded factual-detail safeguard, not a complete natural-language
entailment system. It does not prove ordinary non-numeric paraphrases or broader
semantic support. Deterministic spans, backend-owned public provenance, prompt
safety, provider behavior, model settings, and the single corrective retry are
unchanged. No live or paid call occurred during implementation.

### Specificity-guard audit corrections

The first specificity implementation was not committed. A read-only audit found
that whitespace-normalized concatenation could synthesize a critical expression
across two evidence spans, repeated unknown IDs could cascade into a misleading
duplicate-set diagnostic, and standalone quantitative number words in explicit
count contexts were missed.

All three findings were corrected. Every critical expression must now occur
wholly within one selected span; findings with unresolved evidence IDs are
excluded from duplicate-set and specificity checks; and terminal number words
from zero through twenty are recognized only behind bounded quantitative cues
such as total, count, number, quantity, amount, or sample size plus an allowed
copula. Label contexts such as section, group, category, model, and version stay
excluded. The guard remains lexical and bounded rather than full semantic
entailment. No live or paid call occurred.

## 26. Numeric-token boundary remediation

The second read-only audit found numeric-subtoken false positives: word-only
boundaries accepted `5%` inside `0.5%` and bare `5` inside decimals, signed
values, percentages, suffix-plus thresholds, larger integers, and ratios.
The matcher now uses quantitative-token-aware continuation boundaries covering
digits, letters, decimal and numeric separators, signs, comparators, percent
signs, range punctuation, and slash/colon ratios. Regressions cover those
negative cases plus exact bare, percentage, suffix-plus, signed, comparator,
range, decimal, and confidence-interval matches. No prompt, extraction,
public API, or provider behavior changed, and no live call occurred.

## 27. Issue-specific conservative specificity retry

The next real PDF run confirmed the specificity guard was functioning: both the
initial response and the existing generic corrective response were rejected
with `UNSUPPORTED_CLAIM_DETAIL` because their quantitative details did not occur
wholly within any cited individual span. The generic correction was therefore
insufficient for this failure mode.

The existing single corrective attempt now adds an issue-specific conservative
qualitative fallback when that code is present. It requests three concise
qualitative associations, distinct complete evidence-ID sets, exact-ID use, and
evidence-level terminology while preferring removal of unsupported numeric,
threshold, ratio, outcome, and exception detail. Validation was not weakened,
the initial prompt and one-retry limit remain unchanged, and no live or paid
call occurred during implementation.

## 28. Bounded lexical claim-support guard

The recorded conservative retry succeeded operationally, but manual review
accepted only the first finding and rejected the second and third. Exact
provenance and numeric-detail validation were insufficient for those
nonnumeric claims, which introduced outcomes not meaningfully named by their
cited evidence.

Resolved findings now require at least one contiguous two-token lexical anchor
within one individual cited span. The private normalizer applies only Unicode
NFKC, case folding, punctuation-to-boundary handling, and whitespace
normalization. A small domain-agnostic stop/boilerplate set excludes generic
relation wording, and overlap made up only of terms already in the research
question (such as `social media use` or `sleep patterns`) is insufficient.

`INSUFFICIENT_LEXICAL_SUPPORT` is a safe diagnostic. Its corrective guidance
requires direct evidence terminology, a different span when the current span
does not name the outcome, and concise findings; it does not include failed
output, missing phrases, or source text. No stemming, lemmatization, synonym,
fuzzy, embedding, reordering, or semantic matching was introduced. Existing
unknown-ID isolation, duplicate-set, numeric-detail, and individual-span
validation remain independent, including combined diagnostics. Public models,
provenance, APIs, provider-call bounds, and retry count are unchanged. No live
call occurred for this implementation.

## 29. Deterministic integration fixture lexical-support remediation

The complete deterministic suite exposed a stale happy-path fixture: its fake
provider assumed positional evidence IDs and the three finding selections
collided under the existing duplicate-set validation after lexical support was
enabled. Production lexical validation was not weakened.

The fake provider now selects opaque evidence IDs by unambiguous source phrases
from the real evidence catalogue, including `extracts selectable text`,
`chunk identifiers and one-based pages`, and `limitations remain visible`. The
one-page selectable PDF fixture was padded with deterministic sentence
boundaries so those phrases resolve to distinct evidence spans. The happy path
now succeeds in one provider call, with public assertions for real chunk
provenance, distinct finding evidence sets, and the expected lexical anchors.
No live call occurred.

## 30. Unconditional final corrective-response contract

The latest real job failed its first attempt with
`DUPLICATE_FINDING_EVIDENCE` and `UNSUPPORTED_CLAIM_DETAIL`. Its corrective
response fixed those issues but introduced unsupported qualitative findings,
so attempt two failed `INSUFFICIENT_LEXICAL_SUPPORT` and the job ended with
`map_generation_failed`. Because lexical guidance was conditional on the
first-attempt codes, issue-specific guidance alone was insufficient under the
existing two-call ceiling.

Every corrective prompt now carries a compact complete grounding contract. It
requires exact valid IDs, distinct complete evidence sets, concise
association-language findings, an outcome-naming exact lexical anchor from one
cited span, individual-span support for complete numeric expressions, and
removal of uncertain detail. Existing issue-specific guidance remains as
additional emphasis and composes with the universal contract. Validators, the
initial prompt, public provenance, and provider-call bounds are unchanged. No
live or paid call occurred during this implementation.

## 31. Provider-failure-only deterministic extractive fallback

Earlier real runs proved the Granite integration and its corrective validation
path. Monthly watsonx token availability later became unreliable, so
PaperScape now preserves demo continuity with a narrowly scoped deterministic
fallback. Granite remains the primary path. The fallback runs only when
`ResearchMapService` raises `LLMProviderError`; it does not run for
model-validation failures, `MapGenerationError`, extraction or persistence
errors, invalid requests, or unexpected exceptions.

The fallback is extractive rather than semantic synthesis. It selects exactly
three complete, eligible, sufficiently diverse source sentences from distinct
extracted chunks, preserves their normalized wording and real page/chunk
provenance, and assigns partial confidence. It never paraphrases or pads an
insufficient result. When three safe findings cannot be selected, the existing
public `llm_provider_error` failure remains in effect and no map is persisted.

Generation mode and the safe fallback reason are stored atomically in the
internal `research_map_metadata` table. Legacy map rows without metadata are
read internally as Granite output. The public `ResearchMap` shape is unchanged,
and the fallback is not exposed as model synthesis.

Demo note: PaperScape uses Granite first. When the AI provider is unavailable,
it can degrade safely to an internally labelled deterministic extractive map
rather than fabricating unsupported claims.

No live, network, paid, or watsonx call occurred during this implementation.

## 32. Final deterministic-fallback audit remediation

The final read-only audit found four issues: caller-owned saves could retain a
partial map update after metadata failure, punctuation-only sentence splitting
mishandled abbreviations and headings, method rejection depended too heavily on
section metadata, and the fallback service was constructed eagerly.

Caller-owned map saves now use a repository-local SQLite savepoint. A metadata
failure rolls back both repository writes while preserving unrelated outer
transaction work and leaving the caller in control of commit or rollback. The
sentence scanner now preserves line boundaries while discarding standalone
headings, protects explicit abbreviations and personal initials, recognizes
terminal punctuation followed by closing quotes or brackets, and continues to
preserve decimals and quantitative expressions. Bounded procedural patterns
reject method-only sentences even without section metadata while retaining
result sentences that mention adjusted models or analyses.

Dependency wiring now injects a zero-argument fallback factory. Construction
occurs exactly once inside the `LLMProviderError` branch and never during
container creation, health requests, Granite success, or `MapGenerationError`.
Activation boundaries, public schemas, evidence requirements, diversity,
failure codes, Granite prompts, and validators remain unchanged. No live,
network, paid, or watsonx call occurred during remediation.

The final commit-readiness audit also identified uppercase proper-noun
continuations after `U.S.`, `U.K.`, and `vs.` as an abbreviation boundary that
could leave an eligible trailing fragment. Those abbreviations now remain
internal when body text follows, with scanner- and service-level regressions
covering finding-cue continuations. End-of-block and closing-punctuation uses
remain terminal.

A follow-up audit caught the inverse ambiguity: treating every uppercase token
after those abbreviations as a continuation could join two source sentences.
Because an arbitrary uppercase token cannot reliably distinguish a proper-noun
continuation from a new sentence without external linguistic inference, the
scanner now treats the boundary as ambiguous by default, independently of the
finding eligibility rules. The ambiguous span is excluded rather than split or
joined. Only narrow structurally incomplete prefixes such as `The U.S.` before
`Department`, `The U.K.` before `Biobank`, and `Treatment vs.` before `Control`
remain protected. Clear end-of-block terminals remain eligible. Regressions
cover long and short preceding sentences followed by `Results`, `Findings`,
`Researchers`, `Participants`, and a proper-name sentence starter.

The final two audit findings were remediated without changing activation or
persistence boundaries. Passive `measured`, `assessed`, `evaluated`, `fitted`,
`fit`, `trained`, `collected`, and `recorded` constructions followed by
`using`, `with`, or `by` could escape the object-dependent method filter; a
bounded high-confidence passive-procedure rule now rejects them independently
of section metadata or recognized method objects. Generic title-case heading
detection could also discard wrapped result text. Finding-cue-bearing,
procedural, and continuation-ending title-case lines are now retained as body
text, while known headings, standalone title labels, and all-caps headings are
still removed. No live, network, paid, or watsonx call occurred.

A real deterministic fallback run succeeded with three acceptable findings,
but manual review found that the paper title was incorrectly selected as a
limitation because `cross-sectional` qualified alone. Limitation selection now
separates bounded direct limitation claims from contextual design terms.
`Cross-sectional`, self-report, observational, retrospective, and convenience
sample wording requires explicit limitation framing or consequence language in
the same complete sentence. Title/subtitle wording and bare design labels are
rejected; when no true limitation is present, the existing transparent fixed
limitation is returned. No live, network, paid, or watsonx call occurred during
this remediation.

The final limitation-selection audit found three remaining precision gaps.
Subject-independent `interpreted with caution` and `interpreted cautiously`
phrases now qualify through one bounded, case-insensitive pattern. The
limitation-only `Because ...` completeness exception now requires a finite
subordinate clause and a complete, allowlisted consequence predicate rather
than accepting a trailing noun fragment. A separate limitation-title check
rejects short cue-bearing title-style noun phrases without relying on wrapped
body-line heading detection, while retaining complete title-cased limitation
claims. Finding selection, source ordering, exact-source preservation, public
schemas, activation boundaries, and persistence behavior are unchanged. No
live, network, paid, or watsonx call occurred during this remediation.
