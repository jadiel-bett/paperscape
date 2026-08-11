"""Audience-facing creator-pack contracts derived from an approved research map."""
from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AudienceType(StrEnum):
    GENERAL_PUBLIC = "general_public"
    HIGH_SCHOOL = "high_school"
    UNDERGRADUATE = "undergraduate"


class CreatorPackStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class EvidenceCard(BaseModel):
    finding_index: int = Field(ge=0)
    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: str = Field(min_length=1)
    evidence: list["ResolvedEvidence"] = Field(default_factory=list)


class ResolvedEvidence(BaseModel):
    """Backend-resolved source record; never supplied by a model."""

    evidence_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=300)


class VisualAbstractBlock(BaseModel):
    label: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class GlossaryEntry(BaseModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)


class CreatorPack(BaseModel):
    pack_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    paper_id: str = Field(min_length=1)
    audience: AudienceType
    status: CreatorPackStatus = CreatorPackStatus.DRAFT
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    narration_script: str = Field(min_length=1)
    visual_abstract: list[VisualAbstractBlock] = Field(min_length=1)
    evidence_cards: list[EvidenceCard] = Field(min_length=1)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
    disclaimer: str = Field(min_length=1)

    @field_validator("paper_id", "title", "summary", "narration_script", "disclaimer", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Field must not be blank")
        return value


class CreatorPackCreateRequest(BaseModel):
    audience: AudienceType


class CreatorPackUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    narration_script: str | None = None
    visual_abstract: list[VisualAbstractBlock] | None = None
    glossary: list[GlossaryEntry] | None = None


class CreatorPackApprovalRequest(BaseModel):
    approved: bool
