# Sub-task 11A — Watsonx Chat API migration

## Status and boundary

This plan is the approved specification for migrating the internal
`WatsonxProvider` implementation from the deprecated text-generation API to the
pinned watsonx Chat API.

The application-facing contract remains:

```python
generate(prompt: str, *, max_tokens: int, temperature: float) -> str
```

This migration does not change the application model default, prompts,
ResearchMap limits, frontend, Compose, database, job orchestration, SDK version,
or live-test authorization gates. It does not add Tier B or the live evaluator.

## Recorded Tier A evidence

The first Tier A connectivity test used:

- Frankfurt (`eu-de`);
- explicit candidate model `ibm/granite-4-h-small`;
- `ModelInference.generate_text`;
- the harmless readiness instruction;
- a 32-token output limit;
- temperature zero.

IAM authentication, `WatsonxProvider` construction, and `ModelInference`
construction succeeded. The text-generation request did not raise an HTTP access
error. The pinned SDK warned that `decoding_method` was ignored and that
`/ml/v1/text/generation` is deprecated. `generate_text` returned an empty string,
PaperScape raised `LLMResponseError`, and Tier A failed.

The one-invocation paid approval recorded by Jadiel Bett on 2026-07-30 was
consumed by that run. It does not authorize another paid call.

No credential, project ID, IAM token, prompt, generated content, or raw SDK
response is recorded.

## Current and target flows

```text
Current:
ResearchMapService
  → LLMProvider.generate(...)
  → WatsonxProvider
  → ModelInference.generate_text(...)
  → str

Target:
ResearchMapService
  → unchanged LLMProvider.generate(...)
  → WatsonxProvider
  → ModelInference.chat(messages=[one user message], params=...)
  → strict assistant-response validation
  → str
```

No automatic fallback to `generate_text` or another model is permitted.

## Pinned SDK findings

The implementation is based on the installed `ibm-watsonx-ai==1.5.14` source.
Its synchronous Chat signature is:

```python
ModelInference.chat(
    messages: list[dict],
    params: dict | TextChatParameters | None = None,
    tools: list | None = None,
    tool_choice: dict | None = None,
    tool_choice_option: Literal["none", "auto", "required"] | None = None,
    context: str | None = None,
    crypto: dict | Crypto | None = None,
) -> dict
```

Verified details:

- The SDK validates `messages` as a list but does not deeply validate each
  message.
- A supported text message is `{"role": "user", "content": prompt}`.
- Chat uses `/ml/v1/text/chat`, the same `APIClient`, `_post` response
  decorator, and `RetryTransport` as text generation.
- Chat returns an untyped dictionary. Assistant content is located at
  `choices[0]["message"]["content"]`; `finish_reason` is on the choice.
- `TextChatParameters` and `GenChatParamsMetaNames` include `temperature`,
  `max_tokens`, `max_completion_tokens`, and `response_format`.
- Chat has no `decoding_method`; `max_new_tokens` is a text-generation field.
- `response_format` supports JSON object and JSON Schema forms.
- Non-success responses are handled through the existing SDK response handling
  and expose structured status through SDK request failures where available.
- `max_retries=0` disables the `_with_retry` response-decorator layer for Chat,
  but not the separate HTTPX `RetryTransport`.

The pinned source is authoritative. IBM Granite 4 guidance corroborates using
`max_completion_tokens` and temperature zero:
<https://www.ibm.com/granite/docs/models/granite>.

The watsonx Chat documentation corroborates the assistant response shape:
<https://www.ibm.com/docs/en/watsonx/saas?topic=code-chat>.

## Request translation

The exact existing prompt is preserved as one user message:

```python
[{"role": "user", "content": prompt}]
```

Parameter mapping:

| Public input | Chat parameter |
|---|---|
| `max_tokens` | `max_completion_tokens` |
| `temperature` | `temperature`, including `0.0` |

Temperature zero is the Chat API's closest greedy-equivalent setting. It is not
documented as a guarantee of bit-for-bit reproducibility.

The provider must not send `decoding_method`, `max_new_tokens`,
`response_format`, tools, tool choices, context, crypto, or streaming options.
JSON response format is not forced globally because the provider also supports
non-JSON prompts such as Tier A. The existing ResearchMap prompt, Pydantic
validation, grounding validation, and corrective call continue to enforce the
structured result.

## Response parsing contract

The provider validates, in order:

1. The response is a dictionary.
2. `choices` is a non-empty list.
3. The first choice is a dictionary.
4. `message` is a dictionary.
5. `message.role` is exactly `assistant`.
6. Neither the choice nor message contains a truthy refusal.
7. `message.content` exists and is a string.
8. Content is non-empty after stripping whitespace.
9. `finish_reason` is a string equal to `stop`.

Missing or malformed fields, refusal, `length`, `tool_calls`, and unknown finish
states raise `LLMResponseError`. Truncated content is never returned as valid
ResearchMap JSON.

Errors use fixed sanitized codes and never interpolate response values, raw
responses, prompt content, generated content, response bodies, or exception
text. Response validation failures are not retried by the provider.

A valid assistant string that later fails ResearchMap JSON or schema validation
remains eligible for the service's existing corrective call. A structurally
invalid Chat response fails at the provider boundary.

## TLS and retry model

`WatsonxProvider` constructs `Credentials` with `verify=True`.

In the pinned SDK, an explicit verification value causes
`allow_ssl_fallback=False`. Certificate errors therefore fail safely instead of
triggering the SDK's extra unverified raw request. `verify=False`, certificate
error suppression, environment-based weakening of verification, and installed
site-packages patches are prohibited.

`validate=False` skips model-spec validation only. `APIClient` construction and
token acquisition remain network-active.

`max_retries=0` disables only the `_with_retry` response-decorator retry layer.
The pinned `RetryTransport` still uses:

- `retries=3`;
- up to four transport-loop iterations;
- status force list `401, 500, 502, 503, 504, 520, 521, 524`.

The existing provider-owned retry remains limited to one retry for its explicit
transient classification. This migration does not broaden classification of
exhausted SDK `ExceptionGroup` failures. ResearchMap's corrective call remains
separate and applies only after valid text fails JSON/schema validation.

Conservative theoretical raw inference bounds with verified TLS and no SSL
fallback are:

| Scope | Raw inference transport requests |
|---|---:|
| One Chat invocation | 4 |
| Tier A, including one provider retry | 8 |
| Tier B, including one corrective provider call | 16 |

Authentication and provider-construction requests are additional. These bounds
are not observed counts, guaranteed inference-service arrivals, approved paid
ceilings, or necessarily billable requests. Unobservable attempts must be
reported as unknown, never zero.

## Expected files

Migration files:

- `docs/subtask-11a-watsonx-chat-api-migration-plan.md`
- `backend/app/services/llm_provider.py`
- `backend/tests/unit/test_llm_provider.py`
- `docs/subtask-11-live-watsonx-validation-plan.md`
- `docs/vertical-slice-plan.md`
- `docs/bob-usage-log.md`

The Tier A live test does not require a behavioral change because it calls the
unchanged provider interface. Its `provider_connectivity` name, gates,
readiness checks, prompt, and 32-token limit remain unchanged.

## Test matrix

Offline provider tests cover:

- factory model, project, `validate=False`, and `max_retries=0`;
- explicit `Credentials.verify is True`;
- the exact one-user-message request;
- `max_completion_tokens`;
- zero and positive temperature;
- absence of text-generation-only and global response-format fields;
- valid assistant content and whitespace stripping;
- every structural response failure and finish/refusal state;
- no retry for response validation;
- exactly one provider retry for direct transient failures with identical
  messages and parameters;
- no retry for non-transient failures;
- no prompt, credential, refusal, generated content, or raw response exposure;
- existing caller validation and exception classification.

Existing fake-provider ResearchMap and integration tests remain unchanged.
Malformed valid text still receives one corrective service call; provider errors
do not.

Required offline commands:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_llm_provider.py -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_research_map.py -q
backend\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_pipeline.py -q
backend\.venv\Scripts\python.exe -m pytest backend\tests --collect-only -q
backend\.venv\Scripts\python.exe -m pytest backend\tests -q -rs
backend\.venv\Scripts\python.exe evals\run_evals.py
backend\.venv\Scripts\python.exe -m pip check

Push-Location frontend
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test --reporter expanded
flutter build web --release
Pop-Location

git diff --check
git status --short
git diff --stat
```

No verification command sets live flags, constructs a real provider, reads
credentials, or makes a network request.

## Implementation order and rollback

1. Commit this plan as the approved specification.
2. Correct provider SDK comments and enable explicit TLS verification.
3. Replace text-generation request and parameters with Chat translation.
4. Add strict assistant response parsing.
5. Replace text-specific unit fakes and tests.
6. Run focused and full offline gates.
7. Update historical/live-validation documentation with verified results.
8. Audit the final diff and retry/cost statements.
9. Keep paid Tier A blocked pending a new explicit decision.

Before live validation, rollback is a revert of this bounded provider, test, and
documentation change. Rollback must not add a deprecated API fallback, model
fallback, insecure TLS setting, or site-packages patch.

If migrated Tier A fails, record only sanitized evidence, do not rerun
automatically, do not promote the default, and do not begin Tier B.

## Acceptance criteria

- Production `WatsonxProvider` no longer calls `generate_text`.
- `LLMProvider.generate` and all service/job interfaces remain unchanged.
- Exact Chat translation and strict response parsing are proved offline.
- TLS certificate verification is explicit and SSL fallback is disabled.
- Retry documentation and the 8/16 inference bounds match pinned source.
- All backend, evaluation, frontend, dependency, collection, and diff gates pass.
- The application default remains `ibm/granite-13b-instruct-v2`.
- No prompt, frontend, Compose, database, job, Tier B, evaluator, SDK-version,
  or installed-package change is included.

## Post-migration Tier A

Paid Tier A remains blocked until:

1. The migration diff is independently audited.
2. All offline gates pass.
3. A new decision explicitly accepts up to eight theoretical raw inference
   requests plus additional authentication/construction traffic.
4. Lite-plan quota and Frankfurt availability are reconfirmed.

The future run must use the explicit
`GRANITE_MODEL_ID=ibm/granite-4-h-small` process override, both live gates, only
the `provider_connectivity` selector, the harmless prompt, and the 32-token
limit. It reports sanitized pass/fail information only and is not rerun after
failure without review.

Only after migrated Tier A succeeds may a separate bounded change promote the
default, update its assertion and documentation, and rerun all offline gates.
Tier B remains separately blocked until that promotion succeeds.

## Implementation verification

Recorded on 30 July 2026 with both live-test gates absent:

- provider unit tests: 94 passed;
- ResearchMap unit tests: 67 passed;
- integration pipeline tests: 2 passed;
- complete backend collection: 454 tests;
- complete backend suite: 453 passed and 1 skipped;
- the only skip was gated Tier A before provider construction;
- offline ResearchMap evaluation: passed;
- `pip check`: passed;
- frontend formatting: 23 files checked, 0 changed;
- Flutter analysis: no issues;
- Flutter tests: 42 passed;
- Flutter Web release build: passed.

No live watsonx call occurred. No live-test environment variable was set, no
real `WatsonxProvider` was constructed, and no credential file was inspected.
