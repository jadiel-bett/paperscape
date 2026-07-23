"""Unit tests for backend/app/services/llm_provider.py.

All tests are fully offline — no network calls, no IBM SDK requests, no .env
reads.  The SDK client is never instantiated; a FakeSdkClientFactory and
FakeModelInference are injected instead.  All tests pass _sleep=lambda _: None
so no real sleep occurs.
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services.llm_provider import (
    LLMProvider,
    LLMProviderError,
    LLMResponseError,
    NonTransientLLMError,
    TransientLLMError,
    WatsonxProvider,
    _SdkClientFactory,
    _build_params,
    _classify_exception,
)

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------

_API_KEY = "test-key-do-not-log-xyzzy"
_URL = "https://test.example.com"
_PROJECT_ID = "proj-abc-123"
_MODEL_ID = "ibm/granite-test-v1"
_PROMPT = "Summarise this paper."
_GENERATED = "This paper studies X using Y."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_settings() -> Settings:
    """Return a Settings instance with safe dummy values and no .env reads."""
    return Settings(
        _env_file=None,
        watsonx_api_key=_API_KEY,
        watsonx_url=_URL,
        watsonx_project_id=_PROJECT_ID,
        granite_model_id=_MODEL_ID,
    )


class FakeModelInference:
    """Minimal fake that records calls and returns a configurable value."""

    def __init__(self, return_value: Any = _GENERATED, side_effects: list | None = None) -> None:
        """
        Parameters
        ----------
        return_value:
            Returned on every call when *side_effects* is exhausted or absent.
        side_effects:
            If provided, consumed left-to-right.  Each entry is either a
            return value or an exception instance/class to raise.
        """
        self._return_value = return_value
        self._side_effects: list = list(side_effects) if side_effects else []
        self.call_count: int = 0
        self.calls: list[dict] = []  # each call's kwargs

    def generate_text(self, *, prompt: str, params: dict, **_kwargs: Any) -> Any:
        self.call_count += 1
        self.calls.append({"prompt": prompt, "params": dict(params)})
        if self._side_effects:
            effect = self._side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            if isinstance(effect, type) and issubclass(effect, BaseException):
                raise effect()
            return effect
        return self._return_value


class FakeSdkClientFactory:
    """Injectable factory that returns a pre-built FakeModelInference."""

    def __init__(self, client: FakeModelInference) -> None:
        self.client = client
        self.build_kwargs: dict = {}

    def build(self, *, model_id: str, credentials: Any, project_id: str) -> FakeModelInference:
        self.build_kwargs = {
            "model_id": model_id,
            "credentials": credentials,
            "project_id": project_id,
        }
        return self.client


def make_provider(
    client: FakeModelInference | None = None,
    settings: Settings | None = None,
    sleep_calls: list | None = None,
) -> tuple[WatsonxProvider, FakeSdkClientFactory, list]:
    """Build a WatsonxProvider with fake collaborators.

    Returns (provider, factory, sleep_log) where sleep_log accumulates the
    float values passed to the injected sleep callable.
    """
    if client is None:
        client = FakeModelInference()
    factory = FakeSdkClientFactory(client)
    if settings is None:
        settings = make_settings()

    recorded: list = [] if sleep_calls is None else sleep_calls

    def _fake_sleep(secs: float) -> None:
        recorded.append(secs)

    provider = WatsonxProvider(settings, client_factory=factory, _sleep=_fake_sleep)
    return provider, factory, recorded


# ---------------------------------------------------------------------------
# Section 1 — Abstract base class
# ---------------------------------------------------------------------------


def test_llm_provider_is_abstract() -> None:
    """LLMProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]


def test_llm_provider_subclass_must_implement_generate() -> None:
    """A concrete subclass that skips generate() also cannot be instantiated."""

    class Incomplete(LLMProvider):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Section 2 — Construction and credential handling
# ---------------------------------------------------------------------------


def test_correct_model_id_passed_to_factory() -> None:
    _, factory, _ = make_provider()
    assert factory.build_kwargs["model_id"] == _MODEL_ID


def test_correct_project_id_passed_to_factory() -> None:
    _, factory, _ = make_provider()
    assert factory.build_kwargs["project_id"] == _PROJECT_ID


def test_correct_url_in_credentials() -> None:
    """The Credentials object forwarded to the factory carries the correct URL."""
    _, factory, _ = make_provider()
    creds = factory.build_kwargs["credentials"]
    assert creds.url == _URL


def test_api_key_unwrapped_into_credentials() -> None:
    """The raw API key is passed to Credentials, not the SecretStr wrapper."""
    _, factory, _ = make_provider()
    creds = factory.build_kwargs["credentials"]
    # Credentials stores the key; we verify it matches the unwrapped value.
    assert creds.api_key == _API_KEY


def test_raw_key_not_retained_on_provider() -> None:
    """The raw API key string is not stored as any attribute on WatsonxProvider."""
    provider, _, _ = make_provider()
    for attr_value in vars(provider).values():
        assert attr_value != _API_KEY, (
            f"Raw API key found in provider attribute: {attr_value!r}"
        )


def test_validate_false_passed_to_real_factory() -> None:
    """_SdkClientFactory.build() passes validate=False to ModelInference.

    We verify this by inspecting the real factory's build() call via a mock
    ModelInference constructor — no live SDK connection is made.
    """
    import inspect

    from ibm_watsonx_ai.foundation_models import ModelInference

    assert "validate" in inspect.signature(ModelInference).parameters

    mock_mi_cls = MagicMock(return_value=MagicMock())
    real_factory = _SdkClientFactory()

    import ibm_watsonx_ai.foundation_models as _fm_mod  # noqa: PLC0415

    original_cls = _fm_mod.ModelInference
    _fm_mod.ModelInference = mock_mi_cls  # type: ignore[attr-defined]
    try:
        from ibm_watsonx_ai import Credentials

        real_factory.build(
            model_id=_MODEL_ID,
            credentials=Credentials(url=_URL, api_key=_API_KEY),
            project_id=_PROJECT_ID,
        )
        _, kwargs = mock_mi_cls.call_args
        assert kwargs.get("validate") is False
    finally:
        _fm_mod.ModelInference = original_cls  # type: ignore[attr-defined]


def test_max_retries_zero_passed_to_real_factory() -> None:
    """_SdkClientFactory.build() passes max_retries=0 to ModelInference."""
    mock_mi_cls = MagicMock(return_value=MagicMock())
    real_factory = _SdkClientFactory()

    import ibm_watsonx_ai.foundation_models as _fm_mod  # noqa: PLC0415

    original_cls = _fm_mod.ModelInference
    _fm_mod.ModelInference = mock_mi_cls  # type: ignore[attr-defined]
    try:
        from ibm_watsonx_ai import Credentials

        real_factory.build(
            model_id=_MODEL_ID,
            credentials=Credentials(url=_URL, api_key=_API_KEY),
            project_id=_PROJECT_ID,
        )
        _, kwargs = mock_mi_cls.call_args
        assert kwargs.get("max_retries") == 0
    finally:
        _fm_mod.ModelInference = original_cls  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Section 3 — Successful generation
# ---------------------------------------------------------------------------


def test_generate_returns_text() -> None:
    provider, _, _ = make_provider()
    result = provider.generate(_PROMPT, max_tokens=200, temperature=0.1)
    assert result == _GENERATED


def test_prompt_passed_to_client() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.calls[0]["prompt"] == _PROMPT


def test_max_tokens_maps_to_max_new_tokens() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=512, temperature=0.0)
    params = client.calls[0]["params"]
    assert params["max_new_tokens"] == 512


def test_output_whitespace_stripped() -> None:
    client = FakeModelInference(return_value="  answer  \n")
    provider, _, _ = make_provider(client=client)
    result = provider.generate(_PROMPT, max_tokens=50, temperature=0.0)
    assert result == "answer"


# ---------------------------------------------------------------------------
# Section 4 — Generation parameters
# ---------------------------------------------------------------------------


def test_temperature_zero_uses_greedy() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.calls[0]["params"]["decoding_method"] == "greedy"


def test_temperature_zero_omits_temperature_key() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert "temperature" not in client.calls[0]["params"]


def test_positive_temperature_uses_sample() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.1)
    assert client.calls[0]["params"]["decoding_method"] == "sample"


def test_positive_temperature_includes_temperature_key() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.7)
    assert client.calls[0]["params"]["temperature"] == pytest.approx(0.7)


def test_build_params_greedy_no_temperature() -> None:
    params = _build_params(max_tokens=100, temperature=0.0)
    assert params["decoding_method"] == "greedy"
    assert params["max_new_tokens"] == 100
    assert "temperature" not in params


def test_build_params_sample_includes_temperature() -> None:
    params = _build_params(max_tokens=50, temperature=0.5)
    assert params["decoding_method"] == "sample"
    assert params["max_new_tokens"] == 50
    assert params["temperature"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Section 5 — Input validation (ValueError, not provider errors)
# ---------------------------------------------------------------------------


def test_blank_prompt_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError, match="prompt must not be blank"):
        provider.generate("", max_tokens=100, temperature=0.0)


def test_whitespace_prompt_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError, match="prompt must not be blank"):
        provider.generate("   \n\t  ", max_tokens=100, temperature=0.0)


def test_blank_prompt_does_not_call_client() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    with pytest.raises(ValueError):
        provider.generate("", max_tokens=100, temperature=0.0)
    assert client.call_count == 0


def test_max_tokens_zero_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError, match="max_tokens must be at least 1"):
        provider.generate(_PROMPT, max_tokens=0, temperature=0.0)


def test_max_tokens_negative_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError):
        provider.generate(_PROMPT, max_tokens=-1, temperature=0.0)


def test_max_tokens_below_one_does_not_call_client() -> None:
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client)
    with pytest.raises(ValueError):
        provider.generate(_PROMPT, max_tokens=0, temperature=0.0)
    assert client.call_count == 0


def test_temperature_below_zero_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError, match="temperature must be between"):
        provider.generate(_PROMPT, max_tokens=100, temperature=-0.1)


def test_temperature_above_two_raises_value_error() -> None:
    provider, _, _ = make_provider()
    with pytest.raises(ValueError, match="temperature must be between"):
        provider.generate(_PROMPT, max_tokens=100, temperature=2.1)


def test_temperature_boundary_zero_accepted() -> None:
    provider, _, _ = make_provider()
    result = provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert result == _GENERATED


def test_temperature_boundary_two_accepted() -> None:
    provider, _, _ = make_provider()
    result = provider.generate(_PROMPT, max_tokens=100, temperature=2.0)
    assert result == _GENERATED


# ---------------------------------------------------------------------------
# Section 6 — Response validation
# ---------------------------------------------------------------------------


def test_non_string_output_raises_llm_response_error() -> None:
    client = FakeModelInference(return_value=None)
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)


def test_dict_output_raises_llm_response_error() -> None:
    client = FakeModelInference(return_value={"results": [{"generated_text": "x"}]})
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)


def test_list_output_raises_llm_response_error() -> None:
    client = FakeModelInference(return_value=["text"])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)


def test_empty_string_output_raises_llm_response_error() -> None:
    client = FakeModelInference(return_value="")
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)


def test_whitespace_only_output_raises_llm_response_error() -> None:
    client = FakeModelInference(return_value="   \n\t  ")
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)


def test_response_error_is_not_retried() -> None:
    """LLMResponseError must not trigger a retry — client called exactly once."""
    client = FakeModelInference(return_value="")
    provider, _, _ = make_provider(client=client)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 1


# ---------------------------------------------------------------------------
# Section 7 — Exception classification
# ---------------------------------------------------------------------------


def _make_api_failure(status: int) -> Exception:
    """Return a minimal ApiRequestFailure-like exception with a status code."""
    exc = Exception("sdk error")
    response = MagicMock()
    response.status_code = status
    exc.response = response  # type: ignore[attr-defined]
    return exc


def test_classify_transient_429() -> None:
    exc = _make_api_failure(429)
    result = _classify_exception(exc)
    assert isinstance(result, TransientLLMError)


def test_classify_transient_500() -> None:
    result = _classify_exception(_make_api_failure(500))
    assert isinstance(result, TransientLLMError)


def test_classify_transient_503() -> None:
    result = _classify_exception(_make_api_failure(503))
    assert isinstance(result, TransientLLMError)


def test_classify_transient_408() -> None:
    result = _classify_exception(_make_api_failure(408))
    assert isinstance(result, TransientLLMError)


def test_classify_transient_502() -> None:
    result = _classify_exception(_make_api_failure(502))
    assert isinstance(result, TransientLLMError)


def test_classify_transient_504() -> None:
    result = _classify_exception(_make_api_failure(504))
    assert isinstance(result, TransientLLMError)


def test_classify_transient_520() -> None:
    result = _classify_exception(_make_api_failure(520))
    assert isinstance(result, TransientLLMError)


def test_classify_non_transient_401() -> None:
    result = _classify_exception(_make_api_failure(401))
    assert isinstance(result, NonTransientLLMError)


def test_classify_non_transient_403() -> None:
    result = _classify_exception(_make_api_failure(403))
    assert isinstance(result, NonTransientLLMError)


def test_classify_non_transient_400() -> None:
    result = _classify_exception(_make_api_failure(400))
    assert isinstance(result, NonTransientLLMError)


def test_classify_non_transient_404() -> None:
    result = _classify_exception(_make_api_failure(404))
    assert isinstance(result, NonTransientLLMError)


def test_classify_non_transient_409() -> None:
    result = _classify_exception(_make_api_failure(409))
    assert isinstance(result, NonTransientLLMError)


def test_classify_non_transient_422() -> None:
    result = _classify_exception(_make_api_failure(422))
    assert isinstance(result, NonTransientLLMError)


def test_classify_unknown_status_code_is_non_transient() -> None:
    """Unknown HTTP status codes are non-transient — only the explicit
    allowlist (408, 429, 500, 502, 503, 504, 520) triggers retry."""
    result = _classify_exception(_make_api_failure(418))
    assert isinstance(result, NonTransientLLMError)
    result = _classify_exception(_make_api_failure(521))
    assert isinstance(result, NonTransientLLMError)
    result = _classify_exception(_make_api_failure(503))
    assert isinstance(result, TransientLLMError)


def test_classify_invalid_credentials_error() -> None:
    """InvalidCredentialsError (no .response) is classified as non-transient."""
    from ibm_watsonx_ai.wml_client_error import InvalidCredentialsError

    exc = InvalidCredentialsError("invalid api key")
    result = _classify_exception(exc)
    assert isinstance(result, NonTransientLLMError)


def test_classify_wml_client_error_no_response() -> None:
    """WMLClientError without a .response attribute is non-transient."""
    from ibm_watsonx_ai.wml_client_error import WMLClientError

    exc = WMLClientError("config problem")
    result = _classify_exception(exc)
    assert isinstance(result, NonTransientLLMError)


def test_classify_value_error() -> None:
    result = _classify_exception(ValueError("bad param"))
    assert isinstance(result, NonTransientLLMError)


def test_classify_httpx_connect_error() -> None:
    import httpx

    exc = httpx.ConnectError("connection refused")
    result = _classify_exception(exc)
    assert isinstance(result, TransientLLMError)


def test_classify_httpx_timeout() -> None:
    import httpx

    exc = httpx.TimeoutException("timed out")
    result = _classify_exception(exc)
    assert isinstance(result, TransientLLMError)


def test_classify_unknown_exception_is_non_transient() -> None:
    """Unknown exceptions without recognised fields are non-transient
    (conservative: don't retry blindly)."""
    result = _classify_exception(RuntimeError("unexpected"))
    assert isinstance(result, NonTransientLLMError)


# ---------------------------------------------------------------------------
# Section 8 — Retry behaviour
# ---------------------------------------------------------------------------


def _make_fake_transient() -> TransientLLMError:
    """Return a TransientLLMError with a fake response for chaining tests."""
    return TransientLLMError("Transient HTTP 429: FakeError")


def test_transient_failure_retries_exactly_once() -> None:
    transient = _make_api_failure(429)
    client = FakeModelInference(side_effects=[transient, _GENERATED])
    provider, _, _ = make_provider(client=client)
    result = provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert result == _GENERATED
    assert client.call_count == 2


def test_successful_retry_returns_text() -> None:
    transient = _make_api_failure(503)
    client = FakeModelInference(side_effects=[transient, "retry result"])
    provider, _, _ = make_provider(client=client)
    result = provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert result == "retry result"


def test_persistent_transient_failure_raises_after_two_attempts() -> None:
    t1 = _make_api_failure(429)
    t2 = _make_api_failure(429)
    client = FakeModelInference(side_effects=[t1, t2])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(TransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 2


def test_no_double_retry_max_two_attempts() -> None:
    """Even if many transient failures occur, the loop caps at exactly 2 calls."""
    failures = [_make_api_failure(503)] * 5
    client = FakeModelInference(side_effects=failures)
    provider, _, _ = make_provider(client=client)
    with pytest.raises((TransientLLMError, LLMProviderError)):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 2


def test_unknown_http_status_not_retried() -> None:
    """An unknown HTTP status code (418) is non-transient and must not be
    retried — the SDK should be called exactly once."""
    fail = _make_api_failure(418)
    client = FakeModelInference(side_effects=[fail])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(NonTransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 1


def test_non_transient_http_error_not_retried() -> None:
    fail = _make_api_failure(401)
    client = FakeModelInference(side_effects=[fail])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(NonTransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 1


def test_invalid_credentials_error_not_retried() -> None:
    from ibm_watsonx_ai.wml_client_error import InvalidCredentialsError

    client = FakeModelInference(side_effects=[InvalidCredentialsError("invalid api key")])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(NonTransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 1


def test_unknown_exception_not_retried() -> None:
    client = FakeModelInference(side_effects=[RuntimeError("unexpected")])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(NonTransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert client.call_count == 1


def test_sleep_called_exactly_once_on_transient_retry() -> None:
    transient = _make_api_failure(429)
    client = FakeModelInference(side_effects=[transient, _GENERATED])
    sleep_log: list = []
    provider, _, _ = make_provider(client=client, sleep_calls=sleep_log)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert sleep_log == [1.0]


def test_sleep_not_called_on_success() -> None:
    sleep_log: list = []
    client = FakeModelInference()
    provider, _, _ = make_provider(client=client, sleep_calls=sleep_log)
    provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert sleep_log == []


def test_sleep_not_called_on_non_transient_failure() -> None:
    fail = _make_api_failure(403)
    sleep_log: list = []
    client = FakeModelInference(side_effects=[fail])
    provider, _, _ = make_provider(client=client, sleep_calls=sleep_log)
    with pytest.raises(NonTransientLLMError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert sleep_log == []


def test_sleep_not_called_on_response_error() -> None:
    sleep_log: list = []
    client = FakeModelInference(return_value="")
    provider, _, _ = make_provider(client=client, sleep_calls=sleep_log)
    with pytest.raises(LLMResponseError):
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert sleep_log == []


def test_original_exception_chained_on_persistent_transient() -> None:
    t1 = _make_api_failure(503)
    t2 = _make_api_failure(503)
    client = FakeModelInference(side_effects=[t1, t2])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(TransientLLMError) as exc_info:
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# Section 9 — Credential and prompt safety
# ---------------------------------------------------------------------------


def test_api_key_not_in_exception_message() -> None:
    fail = _make_api_failure(429)
    fail.response.status_code = 429
    t1 = _make_api_failure(429)
    t2 = _make_api_failure(429)
    client = FakeModelInference(side_effects=[t1, t2])
    provider, _, _ = make_provider(client=client)
    with pytest.raises(TransientLLMError) as exc_info:
        provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
    assert _API_KEY not in str(exc_info.value)
    assert _API_KEY not in repr(exc_info.value)


def test_api_key_not_in_provider_repr() -> None:
    provider, _, _ = make_provider()
    assert _API_KEY not in repr(provider)


def test_api_key_not_in_any_provider_attribute_repr() -> None:
    provider, _, _ = make_provider()
    for attr_val in vars(provider).values():
        assert _API_KEY not in repr(attr_val)


def test_prompt_not_in_exception_message(caplog: pytest.LogCaptureFixture) -> None:
    """Prompt text must not appear in exception messages or log output."""
    secret_prompt = "SECRET_PROMPT_CONTENT_12345"
    fail = _make_api_failure(401)
    client = FakeModelInference(side_effects=[fail])
    provider, _, _ = make_provider(client=client)
    with caplog.at_level(logging.DEBUG, logger="app.services.llm_provider"):
        with pytest.raises(NonTransientLLMError) as exc_info:
            provider.generate(secret_prompt, max_tokens=100, temperature=0.0)
    assert secret_prompt not in str(exc_info.value)
    assert secret_prompt not in repr(exc_info.value)
    # The prompt text must not have been emitted at any log level.
    assert secret_prompt not in caplog.text


def test_no_real_sleep_occurs() -> None:
    """Confirm the injected no-op sleep is used, not time.sleep."""
    import time as _time

    original_sleep = _time.sleep
    sleep_called = []

    def _guard_sleep(secs: float) -> None:  # pragma: no cover
        sleep_called.append(secs)
        raise AssertionError("time.sleep was called — injected sleep should be used")

    _time.sleep = _guard_sleep  # type: ignore[assignment]
    try:
        transient = _make_api_failure(429)
        client = FakeModelInference(side_effects=[transient, _GENERATED])
        sleep_log: list = []
        provider, _, _ = make_provider(client=client, sleep_calls=sleep_log)
        result = provider.generate(_PROMPT, max_tokens=100, temperature=0.0)
        assert result == _GENERATED
        assert sleep_log == [1.0]
    finally:
        _time.sleep = original_sleep  # type: ignore[assignment]
