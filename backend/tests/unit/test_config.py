from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings

# ---------------------------------------------------------------------------
# Helper — construct Settings without reading any .env file
# ---------------------------------------------------------------------------

_BASE = {
    "watsonx_url": "https://us-south.ml.cloud.ibm.com",
    "watsonx_project_id": "proj-test",
    "cors_origins": "http://localhost:3000",
}


def _settings(**overrides: object) -> Settings:
    """Construct a Settings instance without reading ``.env``.

    Uses ``_env_file=None`` so the developer's local credentials are never
    loaded and tests remain fully isolated.
    """
    kwargs = {**_BASE, **overrides}
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# db_path — supported URL forms
# ---------------------------------------------------------------------------


def test_db_path_memory() -> None:
    s = _settings(database_url="sqlite:///:memory:")
    assert s.db_path == ":memory:"


def test_db_path_relative_file() -> None:
    s = _settings(database_url="sqlite:///./paperscape.db")
    assert s.db_path == "./paperscape.db"


def test_db_path_absolute_unix_path() -> None:
    s = _settings(database_url="sqlite:////tmp/test.db")
    assert s.db_path == "/tmp/test.db"


def test_db_path_windows_absolute_path() -> None:
    """Windows-style absolute paths must be handled correctly."""
    s = _settings(database_url="sqlite:///C:/data/paperscape.db")
    assert s.db_path == "C:/data/paperscape.db"


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
# SecretStr masking — repr, model_dump, model_dump_json
# ---------------------------------------------------------------------------


def test_secret_key_not_in_repr() -> None:
    s = _settings(watsonx_api_key="super-secret-value")
    assert "super-secret-value" not in repr(s)


def test_secret_key_not_in_model_dump_json_mode() -> None:
    """model_dump(mode='json') must not expose the raw API key value."""
    s = _settings(watsonx_api_key="super-secret-value")
    dumped = s.model_dump(mode="json")
    key_value = dumped.get("watsonx_api_key")
    # Pydantic v2 serialises SecretStr as "**********" in JSON mode
    assert key_value != "super-secret-value", (
        f"watsonx_api_key leaked in model_dump(mode='json'): {key_value!r}"
    )


def test_secret_key_not_in_model_dump_json_string() -> None:
    """model_dump_json() must not expose the raw API key value."""
    s = _settings(watsonx_api_key="super-secret-value")
    json_str = s.model_dump_json()
    assert "super-secret-value" not in json_str, (
        "watsonx_api_key leaked in model_dump_json() output"
    )


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
    assert s.watsonx_project_id == "proj-123"
    assert isinstance(s.watsonx_project_id, str)
    assert not isinstance(s.watsonx_project_id, SecretStr)


# ---------------------------------------------------------------------------
# cors_origins_list property (preserved from original config)
# ---------------------------------------------------------------------------


def test_cors_origins_list() -> None:
    s = _settings(cors_origins="http://localhost:3000, http://localhost:8080")
    assert s.cors_origins_list == ["http://localhost:3000", "http://localhost:8080"]
