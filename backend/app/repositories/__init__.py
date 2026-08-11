"""Persistence repositories for PaperScape.

Each repository manages a single SQLite table and provides atomic,
testable data access.  All methods accept an optional ``conn`` parameter
for caller-managed transactions.
"""
from app.repositories.errors import (
    CorruptRecordError,
    InvalidJobTransitionError,
    PersistenceError,
    RecordNotFoundError,
)
from app.repositories.extraction_store import ExtractionStore
from app.repositories.creator_pack_store import CreatorPackStore
from app.repositories.job_store import JobStore
from app.repositories.research_map_store import (
    GenerationMode,
    ResearchMapGenerationMetadata,
    ResearchMapStore,
)

__all__ = [
    "CorruptRecordError",
    "CreatorPackStore",
    "ExtractionStore",
    "GenerationMode",
    "InvalidJobTransitionError",
    "JobStore",
    "PersistenceError",
    "RecordNotFoundError",
    "ResearchMapStore",
    "ResearchMapGenerationMetadata",
]
