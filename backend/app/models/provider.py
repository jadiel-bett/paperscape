"""Provider-neutral contracts used by routing and inference adapters.

These models intentionally contain no SDK-specific types.  They are safe to
persist as run provenance and are also suitable for API responses after
redacting secret references.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr, field_validator


class ProviderType(StrEnum):
    WATSONX = "watsonx"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"


class ModelCapability(StrEnum):
    TEXT_GENERATION = "text_generation"
    STRUCTURED_OUTPUT = "structured_output"
    PDF_INPUT = "pdf_input"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    IMAGE_GENERATION = "image_generation"
    SPEECH_SYNTHESIS = "speech_synthesis"
    TOOL_CALLING = "tool_calling"


class TaskType(StrEnum):
    RESEARCH_MAP = "research_map"
    AUDIENCE_ADAPTATION = "audience_adaptation"
    CREATOR_PACK = "creator_pack"


class PrivacyMode(StrEnum):
    MANAGED = "managed"
    BYOK = "byok"
    PRIVATE = "private"


class ProviderConnection(BaseModel):
    id: UUID
    workspace_id: UUID
    provider_type: ProviderType
    display_name: str = Field(min_length=1)
    secret_reference: str | None = None
    base_url: str | None = None
    region: str | None = None
    project_reference: str | None = None
    enabled: bool = True


class ModelDescriptor(BaseModel):
    provider_connection_id: UUID | None = None
    provider_type: ProviderType
    model_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    capabilities: set[ModelCapability] = Field(min_length=1)
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    supports_json_schema: bool = False
    supports_pdf: bool = False
    supports_vision: bool = False
    supports_streaming: bool = False
    data_regions: list[str] = Field(default_factory=list)
    license_id: str | None = None
    lifecycle_status: str = "active"


class ModelReference(BaseModel):
    provider_type: ProviderType
    model_id: str = Field(min_length=1)


class TaskPolicy(BaseModel):
    task: TaskType
    required_capabilities: set[ModelCapability] = Field(default_factory=set)
    preferred_models: list[ModelReference] = Field(default_factory=list)
    fallback_models: list[ModelReference] = Field(default_factory=list)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)
    max_latency_seconds: int | None = Field(default=None, ge=1)
    privacy_mode: PrivacyMode = PrivacyMode.MANAGED
    allowed_providers: set[ProviderType] | None = None
    allow_cross_provider_fallback: bool = False


class StructuredGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    json_schema: dict[str, Any] | None = None
    max_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0, le=2)

    @field_validator("prompt")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class TextGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0, le=2)

    @field_validator("prompt")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class GenerationProvenance(BaseModel):
    provider_type: ProviderType
    model_id: str
    adapter_version: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: Decimal | None = Field(default=None, ge=0)
    fallback_used: bool = False


class GenerationResult(BaseModel):
    content: str = Field(min_length=1)
    provenance: GenerationProvenance

