from __future__ import annotations

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A single extracted text segment from a PDF."""

    chunk_id: str
    page: int = Field(ge=1)
    section: str | None = None
    text: str


class ExtractionResult(BaseModel):
    """Complete output of the extraction service for a single PDF."""

    paper_id: str
    filename: str
    chunks: list[Chunk]


class UploadResponse(BaseModel):
    """JSON body returned by POST /api/v1/papers/upload on success."""

    paper_id: str
    filename: str
    page_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
