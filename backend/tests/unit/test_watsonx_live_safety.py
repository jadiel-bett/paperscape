"""Offline safety tests for the opt-in watsonx Tier A harness."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tests.live.test_watsonx_live import (
    _CANDIDATE_MODEL_ID,
    _build_authorized_provider,
)

_READY_ENV = {
    "WATSONX_LIVE_TEST": "1",
    "WATSONX_LIVE_ACK_CHARGES": "1",
    "WATSONX_API_KEY": "offline-dummy-key",
    "WATSONX_PROJECT_ID": "offline-dummy-project",
    "WATSONX_URL": "https://offline.invalid",
    "GRANITE_MODEL_ID": _CANDIDATE_MODEL_ID,
}


def _recording_loader(calls: list[str]) -> Callable[[], tuple[Any, Any]]:
    def _loader() -> tuple[Any, Any]:
        calls.append("factory_loader")
        raise AssertionError("application/SDK factories must not be loaded")

    return _loader


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"WATSONX_LIVE_TEST": "1"},
        {"WATSONX_LIVE_ACK_CHARGES": "1"},
    ],
    ids=["no-gates", "live-gate-only", "charge-ack-only"],
)
def test_missing_authorization_skips_before_factory_loading(
    environ: dict[str, str],
) -> None:
    calls: list[str] = []

    with pytest.raises(pytest.skip.Exception):
        _build_authorized_provider(
            environ,
            factory_loader=_recording_loader(calls),
        )

    assert calls == []


@pytest.mark.parametrize(
    ("missing_variable", "expected_code"),
    [
        ("WATSONX_API_KEY", "live_watsonx_readiness_missing:WATSONX_API_KEY"),
        (
            "WATSONX_PROJECT_ID",
            "live_watsonx_readiness_missing:WATSONX_PROJECT_ID",
        ),
        ("WATSONX_URL", "live_watsonx_readiness_missing:WATSONX_URL"),
        ("GRANITE_MODEL_ID", "live_watsonx_readiness_missing:GRANITE_MODEL_ID"),
    ],
)
def test_missing_readiness_fails_before_factory_loading(
    missing_variable: str,
    expected_code: str,
) -> None:
    environ = dict(_READY_ENV)
    environ.pop(missing_variable)
    calls: list[str] = []

    with pytest.raises(pytest.fail.Exception, match=expected_code):
        _build_authorized_provider(
            environ,
            factory_loader=_recording_loader(calls),
        )

    assert calls == []


def test_incorrect_candidate_fails_before_factory_loading() -> None:
    environ = {
        **_READY_ENV,
        "GRANITE_MODEL_ID": "ibm/not-the-approved-candidate",
    }
    calls: list[str] = []

    with pytest.raises(
        pytest.fail.Exception,
        match="live_watsonx_readiness_invalid:GRANITE_MODEL_ID",
    ):
        _build_authorized_provider(
            environ,
            factory_loader=_recording_loader(calls),
        )

    assert calls == []
