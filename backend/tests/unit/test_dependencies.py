"""Tests for safe application dependency construction."""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.database import init_db
from app.dependencies import ServiceContainer, build_container, run_research_map_job
from app.models.job import JobStatus
from app.repositories import JobStore


def _settings(tmp_path: Path, *, api_key: str = "", project_id: str = "") -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'dependencies.db'}",
        watsonx_api_key=api_key,
        watsonx_project_id=project_id,
    )


def test_nonempty_credentials_do_not_construct_provider_or_call_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = MagicMock(side_effect=AssertionError("provider must be lazy"))
    monkeypatch.setattr("app.dependencies.WatsonxProvider", provider)

    container = build_container(_settings(tmp_path, api_key="configured", project_id="project"))

    assert container.job_runner_factory is not None
    provider.assert_not_called()


def test_importing_main_with_credentials_does_not_construct_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = MagicMock(side_effect=AssertionError("provider must be lazy"))
    monkeypatch.setattr("app.dependencies.WatsonxProvider", provider)
    monkeypatch.setattr(
        "app.main.get_settings",
        lambda: _settings(tmp_path, api_key="configured", project_id="project"),
    )

    import app.main as main

    importlib.reload(main)

    provider.assert_not_called()


def test_provider_construction_failure_marks_pending_job_failed(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, api_key="configured", project_id="project")
    init_db(settings.db_path)
    base = build_container(settings)
    job_store = base.job_store
    job = job_store.create("paper-provider-failure")
    factory = MagicMock(side_effect=RuntimeError("credential and network details"))
    container = ServiceContainer(
        settings=settings,
        extraction_service=base.extraction_service,
        job_store=job_store,
        extraction_store=base.extraction_store,
        research_map_store=base.research_map_store,
        paper_id_factory=base.paper_id_factory,
        job_runner_factory=factory,
    )

    run_research_map_job(container, job.job_id)

    stored = job_store.get(job.job_id)
    assert stored is not None
    assert stored.status == JobStatus.FAILED
    assert stored.error == "llm_provider_error"
    factory.assert_called_once()


def test_provider_factory_is_only_background_runner_construction_site(
    tmp_path: Path,
) -> None:
    container = build_container(_settings(tmp_path, api_key="configured", project_id="project"))
    assert container.job_runner_factory is not None
    assert isinstance(container.job_store, JobStore)
    assert container.job_runner_factory.__name__ == "_build_job_runner"