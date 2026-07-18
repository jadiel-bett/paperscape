from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Settings instance pointing at a temporary file-backed SQLite database.

    A temporary file (not ``:memory:``) is used so that tests that open
    separate connections to the same database (e.g. lifespan + request
    handler) all share the same on-disk database.  The file is placed in a
    pytest-managed temp directory and is cleaned up automatically after the
    session.

    ``_env_file=None`` prevents pydantic-settings from reading the repository
    ``.env`` file so that tests are fully isolated from the developer's
    local credentials.
    """
    db_file = tmp_path_factory.mktemp("db") / "test_paperscape.db"
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{db_file}",
        cors_origins="http://localhost:3000",
    )


@pytest.fixture(scope="session")
def test_app(test_settings: Settings):
    """FastAPI application instance initialised with test settings."""
    return create_app(test_settings)


@pytest.fixture(scope="session")
def test_client(test_app) -> TestClient:
    """HTTP test client whose lifespan runs against the test database."""
    with TestClient(test_app) as client:
        yield client
