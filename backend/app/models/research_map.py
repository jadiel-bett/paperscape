from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A single piece of source evidence linking a finding to a chunk."""

    chunk_id: str
    page: int = Field(ge=1)
    excerpt: str = Field(max_length=300)


class Finding(BaseModel):
    """One of three key findings extracted from the paper."""

    statement: str
    evidence: list[Evidence] = Field(min_length=1)
    confidence: Literal["high", "partial", "uncertain"]


class ResearchMap(BaseModel):
    """Complete structured output of the research-map generation service."""

    paper_id: str
    research_question: str
    findings: list[Finding] = Field(min_length=3, max_length=3)
    limitations: list[str]
    disclaimer: str = "This map does not replace expert review."
