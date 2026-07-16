from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # watsonx.ai credentials (required at runtime; validated elsewhere)
    watsonx_api_key: str = ""
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_project_id: str = ""
    granite_model_id: str = "ibm/granite-13b-instruct-v2"

    # Upload
    upload_max_bytes: int = 20_971_520  # 20 MB

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # Database
    database_url: str = "sqlite:///./paperscape.db"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
