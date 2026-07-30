"""LLM provider interface and IBM watsonx.ai implementation.

Architecture rules
------------------
- No FastAPI, SQLite, or research-map imports anywhere in this module.
- No ``os.environ`` reads.  All credentials come from a ``Settings``
  object injected at construction time.
- The SDK client is never constructed at module import time.
- Complete prompt content is never written to logs.
- Credentials never appear in exception messages, ``repr`` output, or logs.

Verified SDK notes — ibm-watsonx-ai==1.5.14
--------------------------------------------
- ``ModelInference`` accepts ``validate=False`` to skip the construction-time
  model-list API call only.  APIClient construction and token acquisition can
  still perform network requests, so provider construction is network-active.
- ``max_retries=0`` disables the SDK's ``@_with_retry`` response-decorator
  layer.  It does not disable the separate ``RetryTransport``, which is pinned
  to three retries (up to four transport-loop iterations).
- ``ModelInference.chat()`` returns an untyped dictionary.  PaperScape must
  validate the assistant message before returning content to callers.
- ``GenChatParamsMetaNames`` provides ``max_completion_tokens`` and
  ``temperature``.  Chat does not accept the text-generation-only
  ``decoding_method`` or ``max_new_tokens`` fields.
- Credentials explicitly use ``verify=True``.  In this pinned SDK that
  preserves certificate verification and disables its unverified SSL fallback.
- Status codes are accessed via ``exc.response.status_code`` on
  ``ApiRequestFailure`` and its subclasses.  ``InvalidCredentialsError``
  descends from ``WMLClientError`` directly and has no ``.response``.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.config import Settings

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transient HTTP status codes — retry only on these explicit codes.
# ---------------------------------------------------------------------------

# Only these codes are considered transient.  All other HTTP status codes
# (including unknown 4xx/5xx like 418, 521) are non-transient to keep
# retry behaviour predictable and avoid retrying request-side errors.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset([408, 429, 500, 502, 503, 504, 520])

# Temperature range accepted by watsonx.ai
_MIN_TEMPERATURE: float = 0.0
_MAX_TEMPERATURE: float = 2.0

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class LLMProviderError(RuntimeError):
    """Base class for all failures that occur during or after LLM inference.

    Caller input errors (blank prompt, bad parameters) are raised as
    ``ValueError`` before this hierarchy is entered.
    """


class TransientLLMError(LLMProviderError):
    """A failure that is worth retrying: rate limit, timeout, 5xx transient."""


class NonTransientLLMError(LLMProviderError):
    """A failure that must not be retried: auth, bad request, config, 4xx."""


class LLMResponseError(LLMProviderError):
    """The provider returned no usable assistant text.

    Raised for a malformed Chat response, refusal, incomplete finish state, or
    empty/non-string assistant content.  Not retried because these indicate a
    response failure rather than a network failure.
    """


# ---------------------------------------------------------------------------
# LLMProvider abstract base class
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Interface for all LLM backends used in PaperScape.

    All services that need text generation type-hint against this class.
    No service imports the IBM watsonx.ai SDK directly.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate text from *prompt* and return the result as a plain string.

        Parameters
        ----------
        prompt:
            The complete prompt string.  Must not be blank.
        max_tokens:
            Maximum number of tokens to generate.  Must be at least 1.
        temperature:
            Sampling temperature in ``[0.0, 2.0]``.  ``0.0`` is the Chat API's
            closest greedy-equivalent setting; positive values enable sampling.

        Raises
        ------
        ValueError
            If *prompt* is blank, *max_tokens* < 1, or *temperature* is
            outside ``[0.0, 2.0]``.
        LLMResponseError
            If the Chat response is malformed, refused, incomplete, or has no
            usable assistant content.
        TransientLLMError
            On retryable network or server failures (after one retry).
        NonTransientLLMError
            On auth, permission, or invalid-request failures.
        LLMProviderError
            On other provider-level failures.
        """


# ---------------------------------------------------------------------------
# SDK client factory — injectable for tests
# ---------------------------------------------------------------------------


class _SdkClientFactory:
    """Constructs a ``ModelInference`` instance from verified credentials.

    Separated from ``WatsonxProvider`` so unit tests can substitute a
    ``FakeSdkClientFactory`` without patching module-level imports.

    ``validate=False`` skips model-spec validation only; APIClient construction
    can still authenticate over the network. ``max_retries=0`` disables the
    SDK response-decorator retry layer but not its separate RetryTransport.
    """

    def build(
        self,
        *,
        model_id: str,
        credentials: object,
        project_id: str,
    ) -> object:
        from ibm_watsonx_ai.foundation_models import ModelInference

        return ModelInference(
            model_id=model_id,
            credentials=credentials,
            project_id=project_id,
            validate=False,  # skip model-spec validation only
            max_retries=0,  # disable response-decorator retries only
        )


# ---------------------------------------------------------------------------
# WatsonxProvider
# ---------------------------------------------------------------------------


class WatsonxProvider(LLMProvider):
    """Concrete ``LLMProvider`` backed by IBM watsonx.ai.

    Construction
    ------------
    Pass a ``Settings`` instance (from ``app.config``).  Credentials are
    read from ``settings`` only; the raw API key is unwrapped once to build
    ``Credentials`` and is not stored on this object afterwards.

    Retry behaviour
    ---------------
    At most two provider-level Chat invocations.  A transient failure on the
    first invocation triggers ``_sleep(1.0)`` then a second invocation.  A
    second transient failure raises ``TransientLLMError``.  Non-transient
    failures and response errors raise immediately without a provider retry.
    The pinned SDK's separate RetryTransport remains active even though
    response-decorator retries are disabled with ``max_retries=0``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: _SdkClientFactory | None = None,
        _sleep: Callable[[float], None] | None = None,
    ) -> None:
        from ibm_watsonx_ai import Credentials

        factory = client_factory or _SdkClientFactory()
        self._sleep = _sleep if _sleep is not None else time.sleep

        credentials = Credentials(
            url=settings.watsonx_url,
            api_key=settings.watsonx_api_key.get_secret_value(),
            verify=True,
            # raw key used only here; not stored as an attribute
        )
        self._client = factory.build(
            model_id=settings.granite_model_id,
            credentials=credentials,
            project_id=settings.watsonx_project_id,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Generate text.  See ``LLMProvider.generate`` for the full contract."""
        # --- caller input validation (raises ValueError, not provider errors) ---
        if not prompt.strip():
            raise ValueError("prompt must not be blank")
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if not (_MIN_TEMPERATURE <= temperature <= _MAX_TEMPERATURE):
            raise ValueError(
                f"temperature must be between {_MIN_TEMPERATURE} and {_MAX_TEMPERATURE}"
            )

        params = _build_params(max_tokens=max_tokens, temperature=temperature)

        _log.debug(
            "generate called: prompt_len=%d, max_tokens=%d, temperature=%s",
            len(prompt),
            max_tokens,
            temperature,
        )

        # --- attempt 1 ---
        try:
            return self._call_sdk(prompt, params)
        except TransientLLMError:
            pass  # fall through to retry

        # --- retry after transient failure ---
        self._sleep(1.0)

        try:
            return self._call_sdk(prompt, params)
        except TransientLLMError as exc:
            raise TransientLLMError(
                f"Transient failure persisted after retry: {type(exc).__name__}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_sdk(self, prompt: str, params: dict) -> str:
        """Call Chat, classify SDK exceptions, and validate assistant content."""
        messages = [{"role": "user", "content": prompt}]
        try:
            result = self._client.chat(messages=messages, params=params)
        except Exception as exc:
            raise _classify_exception(exc) from exc

        return _extract_chat_content(result)


# ---------------------------------------------------------------------------
# Generation params builder
# ---------------------------------------------------------------------------


def _build_params(*, max_tokens: int, temperature: float) -> dict:
    """Return the pinned SDK Chat parameters for the public provider inputs."""
    from ibm_watsonx_ai.metanames import GenChatParamsMetaNames as GenParams

    return {
        GenParams.MAX_COMPLETION_TOKENS: max_tokens,
        GenParams.TEMPERATURE: temperature,
    }


def _extract_chat_content(response: object) -> str:
    """Return validated assistant content without exposing raw response values."""
    if not isinstance(response, dict):
        raise LLMResponseError("chat_response_not_object")

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("chat_response_choices_invalid")

    choice = choices[0]
    if not isinstance(choice, dict):
        raise LLMResponseError("chat_response_choice_invalid")

    message = choice.get("message")
    if not isinstance(message, dict):
        raise LLMResponseError("chat_response_message_invalid")
    if message.get("role") != "assistant":
        raise LLMResponseError("chat_response_role_invalid")

    if choice.get("refusal") or message.get("refusal"):
        raise LLMResponseError("chat_response_refused")

    if "content" not in message:
        raise LLMResponseError("chat_response_content_missing")
    content = message["content"]
    if not isinstance(content, str):
        raise LLMResponseError("chat_response_content_not_string")

    stripped = content.strip()
    if not stripped:
        raise LLMResponseError("chat_response_content_empty")

    finish_reason = choice.get("finish_reason")
    if not isinstance(finish_reason, str):
        raise LLMResponseError("chat_response_finish_reason_invalid")
    if finish_reason != "stop":
        raise LLMResponseError("chat_response_finish_not_stop")

    return stripped


# ---------------------------------------------------------------------------
# Exception classifier
# ---------------------------------------------------------------------------


def _classify_exception(exc: Exception) -> LLMProviderError:
    """Map an SDK exception to a provider exception.

    Classification uses only structured SDK fields:
    - ``exc.response.status_code`` on ``ApiRequestFailure`` subclasses.
    - Absence of ``.response`` (e.g. ``InvalidCredentialsError``) → non-transient.
    - Known network exceptions (``httpx.ConnectError``, ``httpx.TimeoutException``,
      ``requests.exceptions.ConnectionError``, ``requests.exceptions.Timeout``)
      → transient.

    The message exposed to callers contains only the exception class name and,
    where available, the HTTP status code.  The original exception is always
    preserved via exception chaining.  Prompt text, credentials, and response
    bodies are never included in the public message.
    """
    # --- network / timeout exceptions (transient) ---
    exc_type = type(exc).__name__
    try:
        import httpx as _httpx

        if isinstance(exc, (_httpx.ConnectError, _httpx.TimeoutException)):
            return TransientLLMError(f"Network error: {exc_type}")
    except ImportError:
        pass

    try:
        import requests as _requests

        if isinstance(exc, (_requests.exceptions.ConnectionError, _requests.exceptions.Timeout)):
            return TransientLLMError(f"Network error: {exc_type}")
    except ImportError:
        pass

    # --- SDK exceptions with a structured status code ---
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status: int = exc.response.status_code
        if status in _TRANSIENT_STATUS_CODES:
            return TransientLLMError(f"Transient HTTP {status}: {exc_type}")
        # All other status codes (including unknown 4xx/5xx like 418, 521)
        # are non-transient — only the explicit allowlist triggers retry.
        return NonTransientLLMError(f"Non-transient HTTP {status}: {exc_type}")

    # --- SDK exceptions without a response (config/credential failures) ---
    try:
        from ibm_watsonx_ai.wml_client_error import WMLClientError

        if isinstance(exc, WMLClientError):
            return NonTransientLLMError(f"SDK configuration error: {exc_type}")
    except ImportError:
        pass

    # --- ValueError from the SDK (e.g. invalid params) ---
    if isinstance(exc, ValueError):
        return NonTransientLLMError(f"Invalid request: {exc_type}")

    # --- unknown exceptions — conservative: non-transient to avoid blind retries ---
    return NonTransientLLMError(f"Unexpected error: {exc_type}")
