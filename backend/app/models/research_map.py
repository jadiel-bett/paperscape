from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

_DISCLAIMER = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)


class Evidence(BaseModel):
    """A single piece of source evidence linking a finding to a chunk."""

    chunk_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=300)

    @field_validator("chunk_id", "excerpt", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class Finding(BaseModel):
    """One of three key findings extracted from the paper."""

    statement: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Literal["high", "partial", "uncertain"]

    @field_validator("statement", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class ResearchMap(BaseModel):
    """Complete structured output of the research-map generation service."""

    paper_id: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    findings: list[Finding] = Field(min_length=3, max_length=3)
    limitations: list[str] = Field(min_length=1)
    disclaimer: Literal[
        "This AI-generated explanation is grounded in the uploaded document but does not replace expert review."
    ] = _DISCLAIMER

    @field_validator("paper_id", "research_question", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v
