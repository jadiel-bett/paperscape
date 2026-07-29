"""Opt-in Tier A connectivity validation for the real watsonx provider.

This module is safe to collect during ordinary pytest runs. Application and SDK
objects are imported and constructed only after both paid-test gates and all
sanitized readiness checks pass.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

import pytest

_LIVE_TEST_GATE = "WATSONX_LIVE_TEST"
_CHARGE_ACK_GATE = "WATSONX_LIVE_ACK_CHARGES"
_CANDIDATE_MODEL_ID = "ibm/granite-4-h-small"
_REQUIRED_LIVE_VARIABLES = (
    "WATSONX_API_KEY",
    "WATSONX_PROJECT_ID",
    "WATSONX_URL",
    "GRANITE_MODEL_ID",
)


def _require_live_authorization(environ: Mapping[str, str]) -> None:
    """Skip unless both explicit paid-test authorization gates equal ``1``."""
    if (
        environ.get(_LIVE_TEST_GATE) != "1"
        or environ.get(_CHARGE_ACK_GATE) != "1"
    ):
        pytest.skip(
            "live_watsonx_not_authorized: both paid-test gates must equal 1",
            allow_module_level=False,
        )


def _require_live_readiness(environ: Mapping[str, str]) -> None:
    """Fail with sanitized codes when authorized live configuration is absent."""
    for variable_name in _REQUIRED_LIVE_VARIABLES:
        value = environ.get(variable_name)
        if value is None or not value.strip():
            pytest.fail(
                f"live_watsonx_readiness_missing:{variable_name}",
                pytrace=False,
            )

    if environ["GRANITE_MODEL_ID"].strip() != _CANDIDATE_MODEL_ID:
        pytest.fail(
            "live_watsonx_readiness_invalid:GRANITE_MODEL_ID",
            pytrace=False,
        )


def _load_live_factories() -> tuple[Callable[..., Any], Callable[..., Any]]:
    """Import application and SDK-backed types only after readiness passes."""
    from app.config import Settings
    from app.services.llm_provider import WatsonxProvider

    return Settings, WatsonxProvider


def _build_authorized_provider(
    environ: Mapping[str, str],
    *,
    factory_loader: Callable[
        [], tuple[Callable[..., Any], Callable[..., Any]]
    ] = _load_live_factories,
) -> Any:
    """Authorize, validate, then construct the explicitly selected provider."""
    _require_live_authorization(environ)
    _require_live_readiness(environ)

    settings_factory, provider_factory = factory_loader()
    settings = settings_factory(_env_file=None)

    if settings.granite_model_id != _CANDIDATE_MODEL_ID:
        pytest.fail(
            "live_watsonx_readiness_settings_mismatch:GRANITE_MODEL_ID",
            pytrace=False,
        )

    return provider_factory(settings)


@pytest.fixture
def live_provider() -> Any:
    """Return a real provider only after authorization and readiness checks."""
    return _build_authorized_provider(os.environ)


def test_watsonx_provider_connectivity(live_provider: Any) -> None:
    """Tier A: verify the current provider returns a non-empty string."""
    result = live_provider.generate(
        "Reply with the single word READY.",
        max_tokens=32,
        temperature=0,
    )

    assert isinstance(result, str)
    assert result.strip()
