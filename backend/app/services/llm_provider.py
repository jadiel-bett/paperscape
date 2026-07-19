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
  model-list API call.  Invalid model IDs are detected on the first generation
  call instead.  Pass ``validate=False`` so the provider can be constructed
  without a live network connection (required for tests and startup latency).
- ``max_retries=0`` disables the SDK's built-in ``@_with_retry`` decorator,
  which would otherwise perform up to 10 retries on [429, 503, 504, 520].
  The provider owns all retry logic instead.
- ``generate_text()`` is declared as returning ``str | list[str | dict] | dict``
  so runtime type validation is required before returning.
- ``GenTextParamsMetaNames`` (not the ``TextGenParameters`` dataclass) is the
  correct constants namespace for building the params dict.
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
    """The provider returned no usable generated text.

    Raised for non-string output, empty output, or whitespace-only output.
    Not retried — these indicate a content failure, not a network failure.
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
            Sampling temperature in ``[0.0, 2.0]``.  Use ``0.0`` for
            greedy (deterministic) decoding; positive values for sampling.

        Raises
        ------
        ValueError
            If *prompt* is blank, *max_tokens* < 1, or *temperature* is
            outside ``[0.0, 2.0]``.
        LLMResponseError
            If the model returns empty, whitespace-only, or non-string output.
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

    ``validate=False`` is always passed to avoid a live model-list API call
    at construction time.  ``max_retries=0`` disables SDK-level retries so
    ``WatsonxProvider`` is the sole retry owner.
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
            validate=False,   # skip construction-time model-list fetch
            max_retries=0,    # provider owns all retries
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
    At most two total attempts.  A transient failure on the first attempt
    triggers ``_sleep(1.0)`` then a second attempt.  A second transient
    failure raises ``TransientLLMError``.  Non-transient failures and
    response errors raise immediately without retrying.
    SDK-level retries are disabled (``max_retries=0``).
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
        """Call ``generate_text``, classify exceptions, validate the result."""
        try:
            result = self._client.generate_text(prompt=prompt, params=params)
        except Exception as exc:
            raise _classify_exception(exc) from exc

        if not isinstance(result, str):
            raise LLMResponseError(
                f"generate_text returned unexpected type: {type(result).__name__}"
            )
        stripped = result.strip()
        if not stripped:
            raise LLMResponseError("generate_text returned empty generated text")
        return stripped


# ---------------------------------------------------------------------------
# Generation params builder
# ---------------------------------------------------------------------------


def _build_params(*, max_tokens: int, temperature: float) -> dict:
    """Return the SDK generation params dict for the given arguments.

    Temperature is omitted from the params dict when greedy decoding is used
    because IBM documents that temperature does not apply to greedy decoding.
    """
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

    if temperature == 0.0:
        return {
            GenParams.DECODING_METHOD: "greedy",
            GenParams.MAX_NEW_TOKENS: max_tokens,
        }
    return {
        GenParams.DECODING_METHOD: "sample",
        GenParams.MAX_NEW_TOKENS: max_tokens,
        GenParams.TEMPERATURE: temperature,
    }


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
