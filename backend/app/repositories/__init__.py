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
from app.repositories.job_store import JobStore
from app.repositories.research_map_store import (
    GenerationMode,
    ResearchMapGenerationMetadata,
    ResearchMapStore,
)

__all__ = [
    "CorruptRecordError",
    "ExtractionStore",
    "GenerationMode",
    "InvalidJobTransitionError",
    "JobStore",
    "PersistenceError",
    "RecordNotFoundError",
    "ResearchMapStore",
    "ResearchMapGenerationMetadata",
]
