from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

# ---------------------------------------------------------------------------
# Minimal kwargs accepted by Settings without reading .env
# ---------------------------------------------------------------------------

_BASE = {
    "watsonx_url": "https://us-south.ml.cloud.ibm.com",
    "watsonx_project_id": "proj-test",
    "cors_origins": "http://localhost:3000",
}


def _settings(**overrides: object) -> Settings:
    """Construct a Settings instance with test-safe defaults."""
    kwargs = {**_BASE, **overrides}
    return Settings.model_validate(kwargs)


# ---------------------------------------------------------------------------
# db_path — supported URL forms
# ---------------------------------------------------------------------------


def test_db_path_memory() -> None:
    s = _settings(database_url="sqlite:///:memory:")
    assert s.db_path == ":memory:"


def test_db_path_relative_file() -> None:
    s = _settings(database_url="sqlite:///./paperscape.db")
    assert s.db_path == "./paperscape.db"


def test_db_path_absolute_path() -> None:
    s = _settings(database_url="sqlite:////tmp/test.db")
    assert s.db_path == "/tmp/test.db"


# ---------------------------------------------------------------------------
# db_path — rejected URL forms
# ---------------------------------------------------------------------------


def test_db_path_rejects_non_sqlite_url() -> None:
    with pytest.raises(ValidationError):
        _settings(database_url="postgresql://localhost/db")


def test_db_path_rejects_http_url() -> None:
    with pytest.raises(ValidationError):
        _settings(database_url="http://example.com/db")


def test_db_path_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        _settings(database_url="sqlite:///")


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------


def test_secret_key_not_in_repr() -> None:
    s = _settings(watsonx_api_key="super-secret-value")
    assert "super-secret-value" not in repr(s)


def test_secret_key_accessible_via_get_secret_value() -> None:
    s = _settings(watsonx_api_key="my-key")
    assert s.watsonx_api_key.get_secret_value() == "my-key"


def test_watsonx_api_key_is_secret_str() -> None:
    s = _settings(watsonx_api_key="k")
    assert isinstance(s.watsonx_api_key, SecretStr)


# ---------------------------------------------------------------------------
# project_id is plain str (not SecretStr)
# ---------------------------------------------------------------------------


def test_project_id_is_plain_str() -> None:
    s = _settings(watsonx_project_id="proj-123")
    # Must be directly accessible as a plain string — no .get_secret_value()
    assert s.watsonx_project_id == "proj-123"
    assert isinstance(s.watsonx_project_id, str)
    assert not isinstance(s.watsonx_project_id, SecretStr)


# ---------------------------------------------------------------------------
# cors_origins_list property (preserved from original config)
# ---------------------------------------------------------------------------


def test_cors_origins_list() -> None:
    s = _settings(cors_origins="http://localhost:3000, http://localhost:8080")
    assert s.cors_origins_list == ["http://localhost:3000", "http://localhost:8080"]
