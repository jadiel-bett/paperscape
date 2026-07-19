# Sub-task 4 — LLMProvider Interface and WatsonxProvider

## Top-Level Overview

This sub-task introduces the `LLMProvider` ABC and a concrete
`WatsonxProvider` implementation into
`backend/app/services/llm_provider.py`.  The module is the single point
of contact between PaperScape and the IBM watsonx.ai Python SDK.  All
other services type-hint against `LLMProvider`; none of them import the
SDK directly.

**Scope boundary:** this sub-task covers only the provider module and its
unit tests.  The research-map service (Sub-task 5), background jobs
(Sub-task 6), and API endpoints (Sub-task 7) are explicitly out of scope.

---

## Verified SDK Contract — ibm-watsonx-ai 1.5.14

> **Introspection complete.** All entries in this section are verified
> against the installed package.  The stub `backend/app/services/llm_provider.py`
> contains the full findings as an inline comment block.

### Imports (verified)

```python
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
```

`TextGenParameters` exists in `ibm_watsonx_ai.foundation_models.schema` but
is a dataclass with `None` defaults — not suitable as a constants namespace.
The correct constants namespace is **`GenTextParamsMetaNames`** from
`ibm_watsonx_ai.metanames`.

| Constant attribute     | Value (string key)   | Type    |
|------------------------|----------------------|---------|
| `GenParams.DECODING_METHOD` | `"decoding_method"` | `str` |
| `GenParams.MAX_NEW_TOKENS`  | `"max_new_tokens"`  | `int`  |
| `GenParams.TEMPERATURE`     | `"temperature"`     | `float`|

### `Credentials` construction (verified)

```python
credentials = Credentials(url=watsonx_url, api_key=api_key_str)
```

Kwargs `url=` and `api_key=` are accepted.

### `ModelInference` construction (verified)

```python
client = ModelInference(
    model_id=model_id,
    credentials=credentials,
    project_id=project_id,
    validate=False,    # skip model-list API fetch; tests and prod both use False
    max_retries=0,     # disable SDK-level retries (see retry section below)
)
```

The `Model` class is deprecated; `ModelInference` is the correct class.

`validate=True` (default) causes `ModelInference.__init__` to make a live
API call to fetch the supported model list.  Pass `validate=False` in the
factory to avoid this — the model ID is trusted from `Settings`.

### SDK-level retry system (verified — CRITICAL)

The `_post` method on `BaseModelInference` is decorated with
`@httpx_wrapper._with_retry()`.  By default this performs up to **10 retries**
on status codes `[429, 503, 504, 520]` with 0.5 s exponential backoff (max
8 s per attempt).

`max_retries` passed to `ModelInference.__init__` propagates through to
`BaseModelInference` and is read by `_get_max_retries()` inside `_with_retry`.
Setting `max_retries=0` **reliably disables** all SDK-level retries.

**Decision: keep retries in `WatsonxProvider`; disable SDK retries via
`max_retries=0`.**

- Provider owns: max 2 total attempts, injectable sleep, clear exception
  classification.
- SDK owns: nothing (disabled).
- Never enable both layers simultaneously.

### `generate_text` (verified)

```python
text = client.generate_text(prompt=prompt_str, params=params_dict)
# → str  (when prompt is a plain str and raw_response=False, the default)
```

Declared return type is `str | list[str | dict] | dict`.  When a plain
`str` prompt is passed without `raw_response=True`, the return value is
a `str`.  Guard with `isinstance(result, str)` before returning — raise
`LLMResponseError` on non-string output.

### Decoding parameters — explicit branching (verified)

Temperature does not apply to greedy decoding.  Use explicit branching:

```python
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

if temperature == 0.0:
    params = {
        GenParams.DECODING_METHOD: "greedy",
        GenParams.MAX_NEW_TOKENS: max_tokens,
    }
else:
    params = {
        GenParams.DECODING_METHOD: "sample",
        GenParams.MAX_NEW_TOKENS: max_tokens,
        GenParams.TEMPERATURE: temperature,
    }
```

For PaperScape's research-map call (`temperature=0.1`), this uses
low-temperature sampling.

### SDK exception hierarchy (verified)

```python
from ibm_watsonx_ai.wml_client_error import (
    WMLClientError,           # base for all SDK errors
    ApiRequestFailure,        # HTTP errors; exc.response.status_code → int
    AuthenticationError,      # subclass of ApiRequestFailure (auth failures)
    InvalidCredentialsError,  # subclass of WMLClientError (config failures)
)
```

MROs:
- `AuthenticationError → ApiRequestFailure → WMLClientError → Exception`
- `InvalidCredentialsError → WMLClientError → Exception`

**Status code access:** `exc.response.status_code` (structured field on
`ApiRequestFailure` and its subclasses).  Do **not** parse message strings.
For `WMLClientError` subclasses without a `.response` attribute (e.g.
`InvalidCredentialsError`), treat as non-transient.

### HTTP status code classification (verified)

| Status code | Classification | Notes                                     |
|-------------|----------------|-------------------------------------------|
| 408         | Transient      | Request timeout                           |
| 429         | Transient      | Rate limit (also in SDK default list)     |
| 500         | Transient      | Internal server error                     |
| 502         | Transient      | Bad gateway                               |
| 503         | Transient      | Service unavailable (SDK default)         |
| 504         | Transient      | Gateway timeout (SDK default)             |
| 520         | Transient      | Cloudflare / unknown (SDK default)        |
| 400         | Non-transient  | Invalid request parameters                |
| 401         | Non-transient  | Unauthorized (`AuthenticationError`)      |
| 403         | Non-transient  | Forbidden                                 |
| 404         | Non-transient  | Model not found (`MissingFoundationModel`)|
| 409         | Non-transient  | Conflict                                  |
| 422         | Non-transient  | Unprocessable entity                      |
| no `.response` | Non-transient | `InvalidCredentialsError`, config errors |
| unknown int | Transient      | Treat unknown codes as transient; document|

Network timeouts and connection resets (no `.response` attribute on
exception): treat as transient.

---

## Architecture

### Module: `backend/app/services/llm_provider.py`

The module is structured in five sections:

1. **Exception classes** — `LLMProviderError`, `TransientLLMError`,
   `NonTransientLLMError`, `LLMResponseError`
2. **`LLMProvider` ABC** — defines the public contract
3. **`_SdkClientFactory`** — thin injectable factory for `ModelInference`
4. **`WatsonxProvider`** — concrete implementation
5. **Module-level docstring** stating no FastAPI, SQLite, or research-map
   imports are allowed

#### Architecture rules (matching `extraction.py` precedent)

- No FastAPI, SQLite, or research-map imports.
- No direct `os.environ` reads.
- Credentials come exclusively from the `Settings` object passed to
  `__init__`.
- The SDK client is never constructed at module import time.
- Complete prompts are never written to logs.
- Credentials never appear in exception messages, `repr` output, or logs.

---

## Sub-Tasks

---

### Sub-task 4.1 — Pin SDK dependency and introspection gate

**Intent:** Add `ibm-watsonx-ai==1.5.14` to `requirements.txt`, install
it, and record the real installed API before any provider code is written.
This is the gating step — implementation of 4.2–4.7 must not begin until
the introspection results are documented.

**Expected Outcomes:**
- `backend/requirements.txt` contains `ibm-watsonx-ai==1.5.14`.
- Introspection results are recorded in a comment block at the top of
  `llm_provider.py` (created as a stub) covering all points below.

**Introspection findings (recorded):**
- `Credentials(url=..., api_key=...)` ✓
- `ModelInference(model_id, credentials, project_id, validate=False, max_retries=0)` ✓
- `generate_text(prompt: str, params: dict)` exists; returns `str | list | dict` ✓
- Params namespace: `from ibm_watsonx_ai.metanames import GenTextParamsMetaNames`
  — keys `DECODING_METHOD`, `MAX_NEW_TOKENS`, `TEMPERATURE` verified ✓
- `max_retries=0` reliably disables SDK retries (default is 10) ✓
- `validate=False` required to skip live model-list API fetch ✓
- Exception: `ApiRequestFailure.response.status_code` is the structured field ✓
- `AuthenticationError → ApiRequestFailure → WMLClientError` ✓
- `InvalidCredentialsError → WMLClientError` (no `.response`) → non-transient ✓

**Relevant Context:** `backend/requirements.txt`

**Status:** [x] done

---

### Sub-task 4.2 — Define exception hierarchy

**Intent:** Establish a controlled error taxonomy so callers catch
`LLMProviderError` without coupling to SDK internals.

**Expected Outcomes:**
- Four exception classes exist in `llm_provider.py`.
- `LLMProviderError` is the base for all provider failures during or after
  inference.
- `TransientLLMError` signals a failure worth retrying (HTTP 4xx/5xx
  transient set, network issues).
- `NonTransientLLMError` signals an SDK-level failure that must not be
  retried (auth, bad config, permission, conflict).
- `LLMResponseError` signals that the provider returned no usable text
  (non-string type, empty, or whitespace-only output).
- Exception messages never contain the API key string.
- Caller input errors (`ValueError`) are **not** modelled as provider
  exceptions — they are raised directly as `ValueError`.

**Exception class design:**

```
LLMProviderError(RuntimeError)
├── TransientLLMError        # rate-limit, timeout, 5xx transient
├── NonTransientLLMError     # auth, bad request, config, 4xx non-transient
└── LLMResponseError         # non-string, empty, or whitespace-only output
```

**Trigger mapping:**

| Condition                                      | Exception raised           |
|------------------------------------------------|----------------------------|
| Blank / whitespace-only prompt                 | `ValueError`               |
| `max_tokens < 1`                               | `ValueError`               |
| `temperature` outside `[0.0, 2.0]`             | `ValueError`               |
| HTTP 408 / 429 / 500 / 502 / 503 / 504 / 520  | `TransientLLMError`        |
| HTTP 400 / 401 / 403 / 404 / 409 / 422         | `NonTransientLLMError`     |
| `generate_text` returns non-`str`              | `LLMResponseError`         |
| `generate_text` returns empty / whitespace str | `LLMResponseError`         |
| Unknown exception from SDK                     | `TransientLLMError`        |

**Credential-safety rule:** when wrapping an SDK exception into
`LLMProviderError`, the message must contain only the exception type name
and, if available, the HTTP status code.  The original exception is
chained as `__cause__`.

**Todo List:**
1. Write the four exception classes with docstrings.
2. Verify that `repr(exc)` for each class does not include the API key.

**Relevant Context:** `extraction.py` exception section (lines 43-53);
Sub-task 4.1 introspection results for SDK exception fields

**Status:** [ ] pending

---

### Sub-task 4.3 — Write `LLMProvider` ABC

**Intent:** Define the public interface all services depend on.

**Expected Outcomes:**
- `LLMProvider` is an `ABC` with one abstract method `generate`.
- Method signature: `generate(self, prompt: str, *, max_tokens: int, temperature: float) -> str`
- No concrete logic in the ABC.
- Importable as a type annotation without the SDK being present.

**Todo List:**
1. Import `ABC` and `abstractmethod` from `abc`.
2. Define `LLMProvider(ABC)` with the `generate` abstract method.

**Relevant Context:** `docs/vertical-slice-plan.md` lines 305–309

**Status:** [ ] pending

---

### Sub-task 4.4 — Write `_SdkClientFactory` and constructor

**Intent:** Isolate SDK construction behind an injectable factory so
unit tests can substitute a fake `ModelInference` without patching
module-level imports — matching the `DoclingAdapter` / `PyMuPDFAdapter`
injection pattern from `ExtractionService`.

**Expected Outcomes:**
- `_SdkClientFactory` has a single method `build(model_id, credentials,
  project_id) -> ModelInference` (or equivalent duck-typed object).
- `WatsonxProvider.__init__` accepts `settings: Settings` and an optional
  `client_factory: _SdkClientFactory | None`.
- When `client_factory` is `None`, a real `_SdkClientFactory` is used.
- The `ModelInference` instance is constructed in `__init__` — not at
  module import time.
- `settings.watsonx_api_key.get_secret_value()` is called exactly once,
  inside `__init__`, to unwrap the key before passing it to `Credentials`.
- After construction, the raw key string is not stored as an attribute.
- SDK-level retries are disabled via `max_retries=0` (verified in Sub-task 4.1).

**SDK construction sequence in `__init__`:**

```python
credentials = Credentials(
    url=settings.watsonx_url,
    api_key=settings.watsonx_api_key.get_secret_value(),
)
self._client = client_factory.build(
    model_id=settings.granite_model_id,
    credentials=credentials,
    project_id=settings.watsonx_project_id,
)
```

**`_SdkClientFactory.build()` passes `validate=False` and `max_retries=0`**
(verified in Sub-task 4.1): `validate=False` skips the live model-list
API fetch; `max_retries=0` disables SDK-level retries so the provider loop
is the only active retry layer.

**Testability:**
- Tests inject a `FakeSdkClientFactory` returning a `FakeModelInference`.
- No real SDK construction or credential validation in tests.
- The factory pattern means tests never patch `ibm_watsonx_ai.*`.

**Todo List:**
1. Write `_SdkClientFactory` with `build()` method.
2. Write `WatsonxProvider.__init__` accepting `settings`, optional
   `client_factory`, and optional `_sleep`.
3. Confirm raw key is not stored as a member after `__init__`.

**Relevant Context:** `ExtractionService.__init__` (extraction.py lines 295–301);
`Settings` config.py lines 26–31; Sub-task 4.1 introspection (retry params)

**Status:** [ ] pending

---

### Sub-task 4.5 — Implement `generate` with input validation

**Intent:** Implement the core `generate` method with caller-input guards
that raise `ValueError` before any network call is made, explicit decoding
parameter branching, and strict output type checking.

**Expected Outcomes:**
- Blank / whitespace-only `prompt` raises `ValueError("prompt must not be blank")`.
- `max_tokens < 1` raises `ValueError("max_tokens must be at least 1")`.
- `temperature` outside `[0.0, 2.0]` raises `ValueError("temperature must be between 0.0 and 2.0")`.
- SDK is never called when any of the above guards fire.
- When `temperature == 0.0`, the params dict contains `DECODING_METHOD: "greedy"`
  and `MAX_NEW_TOKENS: max_tokens`; `temperature` key is **omitted**.
- When `temperature > 0.0`, the params dict contains `DECODING_METHOD: "sample"`,
  `MAX_NEW_TOKENS: max_tokens`, and `TEMPERATURE: temperature`.
- `generate_text` is called with the prompt string and the params dict.
- If the return value is not an instance of `str`, raises `LLMResponseError`.
- If the return value (after `.strip()`) is empty, raises `LLMResponseError`.
- Otherwise, returns the stripped string.

**Params construction (using verified alias `GenParams`):**

```python
if temperature == 0.0:
    params = {
        GenParams.DECODING_METHOD: "greedy",
        GenParams.MAX_NEW_TOKENS: max_tokens,
    }
else:
    params = {
        GenParams.DECODING_METHOD: "sample",
        GenParams.MAX_NEW_TOKENS: max_tokens,
        GenParams.TEMPERATURE: temperature,
    }
```

**Logging rule:** do not log the prompt content; log only metadata at
DEBUG level:
```
_log.debug("generate called: prompt_len=%d, max_tokens=%d, temperature=%s", ...)
```

**Todo List:**
1. Add `ValueError` guards at the start of `generate`.
2. Build the params dict with the correct branching logic.
3. Call `generate_text` and capture the result.
4. Check `isinstance(output, str)` before stripping.
5. Check stripped result is non-empty before returning.

**Relevant Context:** Sub-task 4.2 (error taxonomy), Sub-task 4.4 (client),
Sub-task 4.1 (verified GenParams attribute names)

**Status:** [ ] pending

---

### Sub-task 4.6 — Implement retry behaviour

**Intent:** Wrap the SDK call with a single retry for transient failures,
with short backoff, injectable sleep, and a `_classify_exception` helper
that maps SDK exceptions to provider exceptions using structured fields only.

**Expected Outcomes:**
- At most **two** total attempts (one initial + one retry).
- Retry happens only for `TransientLLMError`.
- `NonTransientLLMError` and `LLMResponseError` are raised immediately
  without a second attempt.
- Backoff between attempts: `_sleep(1.0)`.
- Sleep function is injectable via `__init__` parameter
  `_sleep: Callable[[float], None] | None = None`; defaults to
  `time.sleep`.
- After two transient failures, raises `LLMProviderError` (or
  `TransientLLMError`) with the second exception chained as `__cause__`.
- After a transient failure followed by success, returns the text.
- Tests inject `_sleep=lambda _: None` to avoid real delays.

**Retry sequence:**

```
attempt 1
  → success                      → return text
  → TransientLLMError            → _sleep(1.0) → attempt 2
      → success                  → return text
      → any LLMProviderError     → re-raise (chained)
  → NonTransientLLMError         → re-raise immediately
  → LLMResponseError             → re-raise immediately
  → ValueError                   → re-raise immediately (not caught here)
```

**`_classify_exception` helper:**

```python
def _classify_exception(exc: Exception) -> LLMProviderError:
    """Map an SDK exception to a provider exception.

    Uses exc.response.status_code (ApiRequestFailure and subclasses).
    For WMLClientError without .response (e.g. InvalidCredentialsError),
    treats as non-transient.  Does not parse message strings.
    """
```

SDK-to-provider mapping:

```
SDK raises                              → Provider exception
──────────────────────────────────────────────────────────────────
HTTP 408/429/500/502/503/504/520        TransientLLMError(type_name, status)
HTTP 400/401/403/404/409/422            NonTransientLLMError(type_name, status)
WMLClientError without .response        NonTransientLLMError(type_name)
network timeout / connection reset      TransientLLMError(type_name)
ValueError from SDK                     NonTransientLLMError(type_name)
unknown / unclassifiable                TransientLLMError(type_name)  [documented]
```

Messages contain only the exception type name and status code.  The raw
exception is always chained as `__cause__`.

**SDK retry interaction:** `max_retries=0` is set at construction
(verified in Sub-task 4.1) — this provider retry loop is the only active
layer.

**Todo List:**
1. Write `_classify_exception` using `hasattr(exc, "response")` guard
   and `exc.response.status_code` (verified in Sub-task 4.1).
2. Extract the raw SDK call into `_call_sdk(prompt, params)` which calls
   `generate_text` and raises appropriate provider exceptions.
3. Implement the retry loop in `generate`.
4. Ensure the original exception is always chained as `__cause__`.

**Relevant Context:** Sub-task 4.1 (verified: `exc.response.status_code`,
`InvalidCredentialsError` has no `.response`); Sub-task 4.2; Sub-task 4.5

**Status:** [ ] pending

---

### Sub-task 4.7 — Write unit tests

**Intent:** Provide comprehensive test coverage for all specified
behaviours using a fully mocked SDK client — no network calls, no real
credentials, no `.env` dependency.

**Expected Outcomes:** all test cases below pass with `pytest`.

**File:** `backend/tests/unit/test_llm_provider.py`

#### Test fixture design

- `FakeModelInference` — a plain class with a `generate_text` method
  whose return value is configurable.  Tracks call count and the arguments
  (prompt, params) it was called with.  Can be configured to raise an
  exception on a specific call.
- `FakeSdkClientFactory` — a factory that returns a pre-built
  `FakeModelInference` instance and records its `build()` arguments
  (model_id, url from credentials, project_id).
- `make_settings()` — returns
  `Settings(_env_file=None, watsonx_api_key="test-key-do-not-log", watsonx_url="https://test.example.com", watsonx_project_id="proj-123", granite_model_id="ibm/granite-test")`
  with safe dummy values.  Never reads environment variables.
- All tests pass `_sleep=lambda _: None` to eliminate real delays.

#### Test list

| #  | Test name                                        | Behaviour verified                                                     |
|----|--------------------------------------------------|------------------------------------------------------------------------|
| 1  | `test_generate_returns_text`                     | Happy path: returns generated string                                   |
| 2  | `test_correct_model_id_passed_to_factory`        | `model_id` matches `settings.granite_model_id`                         |
| 3  | `test_correct_project_id_passed_to_factory`      | `project_id` matches `settings.watsonx_project_id`                     |
| 4  | `test_correct_url_passed_to_factory`             | `url` in `Credentials` matches `settings.watsonx_url`                  |
| 5  | `test_greedy_params_when_temperature_zero`       | `temperature==0.0` → `"greedy"` decoding, `temperature` key absent     |
| 6  | `test_sample_params_when_temperature_nonzero`    | `temperature==0.1` → `"sample"` decoding, `temperature` key present    |
| 7  | `test_max_new_tokens_propagated`                 | `max_tokens` value appears as `max_new_tokens` in params               |
| 8  | `test_secret_unwrapped_only_at_construction`     | `SecretStr.get_secret_value()` called once; raw key not on provider    |
| 9  | `test_sdk_retries_disabled`                      | `FakeSdkClientFactory.build()` receives `max_retries=0` (if supported) |
| 10 | `test_blank_prompt_raises_value_error`           | Blank prompt raises `ValueError`; SDK not called                       |
| 11 | `test_whitespace_prompt_raises_value_error`      | Whitespace-only prompt raises `ValueError`; SDK not called             |
| 12 | `test_invalid_max_tokens_raises_value_error`     | `max_tokens=0` raises `ValueError`; SDK not called                     |
| 13 | `test_invalid_temperature_low_raises_value_error`| `temperature=-0.1` raises `ValueError`; SDK not called                 |
| 14 | `test_invalid_temperature_high_raises_value_error`| `temperature=2.1` raises `ValueError`; SDK not called                 |
| 15 | `test_non_string_output_raises_llm_response_error` | SDK returns `None` → `LLMResponseError` raised                       |
| 16 | `test_empty_output_raises_llm_response_error`    | SDK returns `""` → `LLMResponseError` raised                          |
| 17 | `test_whitespace_output_raises_llm_response_error` | SDK returns `"   \n"` → `LLMResponseError` raised                   |
| 18 | `test_llm_response_error_not_retried`            | `LLMResponseError` path: SDK called exactly once                       |
| 19 | `test_transient_failure_retries_exactly_once`    | Transient failure on attempt 1: SDK called twice total                 |
| 20 | `test_successful_retry_returns_text`             | Transient failure then success: text from attempt 2 returned           |
| 21 | `test_persistent_transient_failure_raises`       | Two consecutive transient failures → `LLMProviderError` raised         |
| 22 | `test_non_transient_failure_not_retried`         | Non-transient SDK error: SDK called exactly once                       |
| 23 | `test_sleep_called_on_transient_retry`           | Injected sleep called exactly once on transient retry                  |
| 24 | `test_sleep_not_called_on_non_transient`         | Injected sleep never called on non-transient failure                   |
| 25 | `test_no_double_retry`                           | Max total calls is 2 regardless of transient failure count             |
| 26 | `test_credentials_not_in_exception_string`       | `LLMProviderError` message does not contain the API key string         |
| 27 | `test_credentials_not_in_provider_repr`          | `repr(provider)` does not contain the API key string                   |

> **Note on test 9 (`test_sdk_retries_disabled`):** if Sub-task 4.1
> establishes that `max_retries` is not accepted by `ModelInference` in
> 1.5.14, this test is updated to assert that the provider retry loop
> is present and the SDK factory does not receive a `max_retries` kwarg.
> Document the outcome in the test's docstring.

#### Credential safety assertion pattern

```python
KEY = "test-key-do-not-log"
# ... trigger failure ...
assert KEY not in str(exc_info.value)
assert KEY not in repr(exc_info.value)
```

**Todo List:**
1. Write `FakeModelInference` with configurable return, side-effect, and
   call tracking.
2. Write `FakeSdkClientFactory` with build-argument recording.
3. Write `make_settings()` helper using `Settings(_env_file=None, ...)`.
4. Write all 27 test cases.
5. Run `pytest backend/tests/unit/test_llm_provider.py -v` and confirm
   all 27 pass.
6. Run `pytest backend/tests/` to confirm pre-existing tests still pass.

**Relevant Context:** `test_extraction.py` for the fake-adapter pattern;
`conftest.py` for `Settings(_env_file=None, ...)` pattern

**Status:** [ ] pending

---

## Dependency Changes

| File | Change |
|------|--------|
| `backend/requirements.txt` | Add `ibm-watsonx-ai==1.5.14` |

No other files are modified by this sub-task.

---

## SDK API Gaps and Risks

All gating risks from Sub-task 4.1 have been resolved by introspection.
Remaining risks:

| Risk | Mitigation |
|------|------------|
| `generate_text` returns non-`str` for certain inputs | `isinstance(result, str)` guard + `LLMResponseError`; verified return type in introspection |
| `validate=False` skips model existence check | Acceptable: model ID is controlled via `Settings`; fail fast at first real call |
| SDK retry defaults change in a patch release | `max_retries=0` overrides the default regardless of what the default is |
| `ApiRequestFailure` 404 raises `MissingFoundationModel` instead | `MissingFoundationModel` is a `WMLClientError`; has no `.response` → caught by the `hasattr(exc, "response")` guard as non-transient |
| ibm-watsonx-ai updated beyond 1.5.14 | Pin is locked; upgrade must re-run introspection and update this plan |

---

## Acceptance Criteria

- [x] `backend/requirements.txt` contains `ibm-watsonx-ai==1.5.14`.
- [x] Sub-task 4.1 introspection results are recorded in `llm_provider.py`.
- [ ] `backend/app/services/llm_provider.py` contains `LLMProvider`,
      `WatsonxProvider`, `LLMProviderError`, `TransientLLMError`,
      `NonTransientLLMError`, `LLMResponseError`.
- [ ] `LLMProvider` is importable as an ABC without the SDK installed.
- [ ] `WatsonxProvider` constructs `ModelInference` from injected
      `Settings`; never reads environment variables directly.
- [ ] `SecretStr.get_secret_value()` is called once, in `__init__`, and
      the raw string is not stored as a member.
- [ ] Blank prompt, `max_tokens < 1`, and out-of-range temperature raise
      `ValueError` before any SDK call.
- [ ] `temperature == 0.0` produces greedy params with no temperature key.
- [ ] `temperature > 0.0` produces sample params with temperature key.
- [ ] Only one retry layer is active (provider loop or SDK — not both).
- [ ] Transient SDK failures retry exactly once with injected sleep.
- [ ] Non-transient failures are raised immediately without retry.
- [ ] `LLMResponseError` is raised for non-string, empty, or
      whitespace-only output, and is not retried.
- [ ] The API key never appears in exception messages, `repr()`, or logs.
- [ ] No FastAPI, SQLite, or research-map imports in the module.
- [ ] All 27 unit tests in `test_llm_provider.py` pass.
- [ ] Pre-existing tests (`pytest backend/tests/`) continue to pass.
