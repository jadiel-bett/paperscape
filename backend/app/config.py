from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Intended for use with FastAPI's ``Depends(get_settings)``.  Direct
    instantiation is supported for tests — pass ``_env_file=None`` to
    prevent pydantic-settings from reading any ``.env`` file:

        Settings(_env_file=None, database_url="sqlite:///:memory:", ...)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # watsonx.ai credentials
    # watsonx_api_key is a secret — repr and JSON serialisation show "**********"
    watsonx_api_key: SecretStr = SecretStr("")
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    # watsonx_project_id is a non-secret identifier — kept as plain str
    watsonx_project_id: str = ""
    granite_model_id: str = "ibm/granite-4-h-small"

    # Provider-neutral launch routes. OpenAI-compatible credentials are used
    # only by the backend and are never serialized to the Flutter client.
    openai_api_key: SecretStr = SecretStr("")
    openai_model_id: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    compatible_api_key: SecretStr = SecretStr("")
    compatible_model_id: str = ""
    compatible_base_url: str = ""
    default_provider: str = "managed"
    provider_timeout_seconds: float = 60.0

    # Upload
    upload_max_bytes: int = 20_971_520  # 20 MB

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # Database — must be a SQLite URL
    database_url: str = "sqlite:///./paperscape.db"

    @field_validator("database_url", mode="after")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        """Accept only SQLite URLs in the two supported forms:

        - ``sqlite:///:memory:``
        - ``sqlite:///`` followed by a non-empty path (relative or absolute,
          including Windows-style paths such as ``sqlite:///C:/data/app.db``)
        """
        if v == "sqlite:///:memory:":
            return v
        if v.startswith("sqlite:///"):
            remainder = v[len("sqlite:///"):]
            if not remainder:
                raise ValueError(
                    "database_url 'sqlite:///' has an empty path. "
                    "Use 'sqlite:///:memory:' for an in-memory database "
                    "or 'sqlite:///./paperscape.db' for a file."
                )
            return v
        raise ValueError(
            f"Unsupported database_url {v!r}. "
            "Only SQLite URLs are accepted (e.g. 'sqlite:///./paperscape.db')."
        )

    @property
    def db_path(self) -> str:
        """Return the plain filesystem path (or ':memory:') from database_url.

        Examples
        --------
        ``"sqlite:///:memory:"``            → ``":memory:"``
        ``"sqlite:///./paperscape.db"``     → ``"./paperscape.db"``
        ``"sqlite:///C:/data/app.db"``      → ``"C:/data/app.db"``

        Raises ``ValueError`` for malformed URLs that somehow bypass the
        field validator — this branch is unreachable in normal operation.
        """
        if self.database_url == "sqlite:///:memory:":
            return ":memory:"
        if self.database_url.startswith("sqlite:///"):
            path = self.database_url[len("sqlite:///"):]
            if not path:
                raise ValueError(
                    "database_url has an empty path after 'sqlite:///'."
                )
            return path
        raise ValueError(
            f"Cannot extract db_path from unsupported database_url: {self.database_url!r}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance.

    Designed for ``Depends(get_settings)`` in FastAPI routes.  Direct calls
    should be confined to ``create_app()`` and tests that supply explicit
    overrides via ``Settings(_env_file=None, ...)``.
    """
    return Settings()
