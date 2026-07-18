from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Chunk(BaseModel):
    """A single extracted text segment from a PDF."""

    chunk_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    section: str | None = None
    text: str = Field(min_length=1)

    @field_validator("chunk_id", "text", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class ExtractionResult(BaseModel):
    """Complete output of the extraction service for a single PDF."""

    paper_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    chunks: list[Chunk] = Field(min_length=1)

    @field_validator("paper_id", "filename", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class UploadResponse(BaseModel):
    """JSON body returned by POST /api/v1/papers/upload on success."""

    paper_id: str
    filename: str
    page_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
