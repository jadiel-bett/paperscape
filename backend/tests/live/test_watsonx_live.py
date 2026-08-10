"""Opt-in Tier A and Tier B validation for the real watsonx provider.

This module is safe to collect during ordinary pytest runs. Application and SDK
objects are imported and constructed only after both paid-test gates and all
sanitized readiness checks pass.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path
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
_RESEARCH_MAP_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "evals"
    / "fixtures"
    / "research_map_extraction.json"
)
_CANONICAL_DISCLAIMER = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)


class _CountingProvider:
    """Count public provider calls while delegating them unchanged."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.provider_generate_calls = 0

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        self.provider_generate_calls += 1
        return self._delegate.generate(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", normalized).strip()


def _tier_b_error_category(exc: Exception, *, phase: str) -> str:
    """Return a sanitized PaperScape category without inspecting error text."""
    if phase == "provider_construction":
        return "llm_provider_error"

    error_name = type(exc).__name__
    if error_name in {
        "LLMProviderError",
        "LLMResponseError",
        "NonTransientLLMError",
        "TransientLLMError",
    }:
        return "llm_provider_error"
    if error_name == "MapGenerationError":
        return "map_generation_error"
    if error_name in {"JSONDecodeError", "ValidationError", "OSError"}:
        return "fixture_validation_error"
    if error_name == "AssertionError":
        return "research_map_validation_error"
    return "unexpected_error"


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


def test_live_research_map_service(
    record_property: Callable[[str, object], None],
) -> None:
    """Tier B: validate the real service against the synthetic extraction."""
    _require_live_authorization(os.environ)
    _require_live_readiness(os.environ)

    provider_generate_calls = 0
    corrective_retry_count = 0
    generation_started_at: float | None = None
    elapsed_generation_seconds = 0.0
    failure_phase = "fixture_validation"

    try:
        from app.models.paper import ExtractionResult
        from app.services.research_map import ResearchMapService

        extraction_data = json.loads(
            _RESEARCH_MAP_FIXTURE.read_text(encoding="utf-8")
        )
        extraction = ExtractionResult.model_validate(extraction_data)
        chunk_lookup = {chunk.chunk_id: chunk for chunk in extraction.chunks}

        failure_phase = "provider_construction"
        provider = _build_authorized_provider(os.environ)
        counting_provider = _CountingProvider(provider)
        service = ResearchMapService(provider=counting_provider)

        failure_phase = "research_map_generation"
        generation_started_at = time.perf_counter()
        result = service.generate_map(extraction)
        elapsed_generation_seconds = time.perf_counter() - generation_started_at
        provider_generate_calls = counting_provider.provider_generate_calls
        corrective_retry_count = max(provider_generate_calls - 1, 0)

        assert result.research_question.strip()
        assert len(result.findings) == 3

        normalized_findings = [
            _normalize_text(finding.statement).casefold()
            for finding in result.findings
        ]
        assert len(set(normalized_findings)) == len(normalized_findings)

        for finding in result.findings:
            assert finding.confidence in {"high", "partial"}
            assert finding.evidence
            for evidence in finding.evidence:
                assert evidence.chunk_id in chunk_lookup
                referenced_chunk = chunk_lookup[evidence.chunk_id]
                assert evidence.page >= 1
                assert evidence.page == referenced_chunk.page
                normalized_excerpt = _normalize_text(evidence.excerpt)
                assert normalized_excerpt
                assert normalized_excerpt in _normalize_text(referenced_chunk.text)

        assert result.limitations
        assert all(limitation.strip() for limitation in result.limitations)
        assert result.disclaimer == _CANONICAL_DISCLAIMER
        assert provider_generate_calls in {1, 2}
        assert provider_generate_calls <= 2
        assert corrective_retry_count in {0, 1}
    except Exception as exc:
        if generation_started_at is not None:
            elapsed_generation_seconds = (
                time.perf_counter() - generation_started_at
            )
        if "counting_provider" in locals():
            provider_generate_calls = counting_provider.provider_generate_calls
            corrective_retry_count = max(provider_generate_calls - 1, 0)

        record_property("provider_generate_calls", provider_generate_calls)
        record_property("corrective_retry_count", corrective_retry_count)
        record_property(
            "elapsed_generation_seconds",
            round(elapsed_generation_seconds, 3),
        )
        safe_failure = (
            f"tier_b_failure:exception={type(exc).__name__};"
            f"category={_tier_b_error_category(exc, phase=failure_phase)};"
            f"provider_generate_calls={provider_generate_calls};"
            f"elapsed_generation_seconds={elapsed_generation_seconds:.3f}"
        )
        raise pytest.fail.Exception(safe_failure, pytrace=False) from None

    record_property("provider_generate_calls", provider_generate_calls)
    record_property("corrective_retry_count", corrective_retry_count)
    record_property(
        "elapsed_generation_seconds",
        round(elapsed_generation_seconds, 3),
    )
