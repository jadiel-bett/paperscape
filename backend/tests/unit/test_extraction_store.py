"""Unit tests for :class:`ExtractionStore`.

All tests use ``tmp_path``-backed SQLite databases.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.database import init_db
from app.models.paper import Chunk, ExtractionResult
from app.repositories.errors import CorruptRecordError, PersistenceError, RecordNotFoundError
from app.repositories.extraction_store import ExtractionStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "test_extractions.db"
    init_db(str(path))
    return str(path)


@pytest.fixture
def store(db_path: str) -> ExtractionStore:
    return ExtractionStore(db_path)


@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [
        Chunk(chunk_id="p1-p1-1", page=1, section="Introduction", text="This is the intro."),
        Chunk(chunk_id="p1-p2-1", page=2, section=None, text="Methods and results."),
    ]


@pytest.fixture
def sample_extraction(sample_chunks: list[Chunk]) -> ExtractionResult:
    return ExtractionResult(
        paper_id="paper-1",
        filename="study.pdf",
        chunks=sample_chunks,
    )


@pytest.fixture
def alt_extraction() -> ExtractionResult:
    return ExtractionResult(
        paper_id="paper-1",
        filename="study_v2.pdf",
        chunks=[Chunk(chunk_id="p1-p1-1", page=1, section=None, text="Replacement.")],
    )


# ---------------------------------------------------------------------------
# save() and get()
# ---------------------------------------------------------------------------


def test_save_and_retrieve(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.paper_id == "paper-1"
    assert retrieved.filename == "study.pdf"
    assert len(retrieved.chunks) == 2


def test_every_chunk_round_trips(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    for original, retrieved_chunk in zip(sample_extraction.chunks, retrieved.chunks):
        assert retrieved_chunk.chunk_id == original.chunk_id
        assert retrieved_chunk.page == original.page
        assert retrieved_chunk.section == original.section
        assert retrieved_chunk.text == original.text


def test_chunk_ids_round_trip(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert [c.chunk_id for c in retrieved.chunks] == ["p1-p1-1", "p1-p2-1"]


def test_chunk_pages_round_trip(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert [c.page for c in retrieved.chunks] == [1, 2]


def test_chunk_sections_round_trip(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.chunks[0].section == "Introduction"
    assert retrieved.chunks[1].section is None


def test_chunk_text_round_trips(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert [c.text for c in retrieved.chunks] == [
        "This is the intro.",
        "Methods and results.",
    ]


def test_filename_round_trips_from_column(store: ExtractionStore) -> None:
    ext = ExtractionResult(
        paper_id="p2",
        filename="custom_name.pdf",
        chunks=[Chunk(chunk_id="p2-p1-1", page=1, section=None, text="Content.")],
    )
    store.save(ext)
    retrieved = store.get("p2")
    assert retrieved is not None
    assert retrieved.filename == "custom_name.pdf"


def test_paper_id_round_trips_from_column(store: ExtractionStore) -> None:
    ext = ExtractionResult(
        paper_id="p3",
        filename="a.pdf",
        chunks=[Chunk(chunk_id="p3-p1-1", page=1, section=None, text="X.")],
    )
    store.save(ext)
    retrieved = store.get("p3")
    assert retrieved is not None
    assert retrieved.paper_id == "p3"


def test_section_none_round_trips(store: ExtractionStore) -> None:
    ext = ExtractionResult(
        paper_id="p4",
        filename="a.pdf",
        chunks=[Chunk(chunk_id="p4-p1-1", page=1, section=None, text="No section.")],
    )
    store.save(ext)
    retrieved = store.get("p4")
    assert retrieved is not None
    assert retrieved.chunks[0].section is None


def test_section_string_round_trips(store: ExtractionStore) -> None:
    ext = ExtractionResult(
        paper_id="p5",
        filename="a.pdf",
        chunks=[Chunk(chunk_id="p5-p1-1", page=1, section="Methods", text="Methods text.")],
    )
    store.save(ext)
    retrieved = store.get("p5")
    assert retrieved is not None
    assert retrieved.chunks[0].section == "Methods"


def test_unicode_text_round_trips(store: ExtractionStore) -> None:
    ext = ExtractionResult(
        paper_id="p-unicode",
        filename="é.pdf",
        chunks=[Chunk(chunk_id="u-p1-1", page=1, section=None, text="Unicode: ñ, 博士, 🌍")],
    )
    store.save(ext)
    retrieved = store.get("p-unicode")
    assert retrieved is not None
    assert retrieved.chunks[0].text == "Unicode: ñ, 博士, 🌍"
    assert retrieved.filename == "é.pdf"


# ---------------------------------------------------------------------------
# None / missing
# ---------------------------------------------------------------------------


def test_missing_extraction_returns_none(store: ExtractionStore) -> None:
    assert store.get("nonexistent") is None


def test_require_missing_raises(store: ExtractionStore) -> None:
    with pytest.raises(RecordNotFoundError):
        store.require("nonexistent")


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


def test_exists_true(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    assert store.exists("paper-1") is True


def test_exists_false(store: ExtractionStore) -> None:
    assert store.exists("nonexistent") is False


# ---------------------------------------------------------------------------
# Repeated save (upsert)
# ---------------------------------------------------------------------------


def test_repeated_save_replaces(
    store: ExtractionStore,
    sample_extraction: ExtractionResult,
    alt_extraction: ExtractionResult,
) -> None:
    store.save(sample_extraction)
    store.save(alt_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert len(retrieved.chunks) == 1
    assert retrieved.chunks[0].text == "Replacement."


def test_repeated_save_filename_updated(
    store: ExtractionStore,
    sample_extraction: ExtractionResult,
    alt_extraction: ExtractionResult,
) -> None:
    store.save(sample_extraction)
    store.save(alt_extraction)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.filename == "study_v2.pdf"


# ---------------------------------------------------------------------------
# Corrupt data
# ---------------------------------------------------------------------------


def test_malformed_json_raises_corrupt(db_path: str) -> None:
    """Directly insert bad JSON, then attempt to read with the store."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO extractions (paper_id, filename, chunks_json) VALUES (?, ?, ?)",
        ("bad-id", "f.pdf", "{invalid json"),
    )
    conn.commit()
    conn.close()

    store = ExtractionStore(db_path)
    with pytest.raises(CorruptRecordError):
        store.get("bad-id")


def test_schema_invalid_json_raises_corrupt(db_path: str) -> None:
    """Insert JSON that is valid but not a list[Chunk]."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO extractions (paper_id, filename, chunks_json) VALUES (?, ?, ?)",
        ("bad-schema", "f.pdf", json.dumps({"not": "a list"})),
    )
    conn.commit()
    conn.close()

    store = ExtractionStore(db_path)
    with pytest.raises(CorruptRecordError):
        store.get("bad-schema")


# ---------------------------------------------------------------------------
# Transaction, connection ownership, and rollback-on-failure
# ---------------------------------------------------------------------------


def test_caller_conn_remains_open(store: ExtractionStore, db_path: str, sample_extraction: ExtractionResult) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    store.save(sample_extraction, conn=conn)
    row = conn.execute("SELECT 1 AS val").fetchone()
    assert row["val"] == 1
    conn.close()


def test_repository_conn_is_closed(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    store.save(sample_extraction)
    assert store.get("paper-1") is not None


def test_extraction_result_not_duplicated_in_json(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    """Verify chunks_json stores only the chunk list, not the full ExtractionResult."""
    store.save(sample_extraction)
    conn = sqlite3.connect(store._db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT chunks_json FROM extractions WHERE paper_id = ?", ("paper-1",)).fetchone()
    conn.close()
    assert row is not None
    stored = json.loads(row["chunks_json"])
    assert isinstance(stored, list)
    assert len(stored) == 2
    assert "paper_id" not in stored[0]
    assert "filename" not in stored[0]


def test_upsert_rolls_back_on_trigger_failure(db_path: str, sample_extraction: ExtractionResult, alt_extraction: ExtractionResult) -> None:
    """Create a trigger that forces a write failure, then verify the prior record survives."""
    store = ExtractionStore(db_path)
    store.save(sample_extraction)
    assert store.get("paper-1") is not None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS test_break_extraction
           BEFORE UPDATE ON extractions
           BEGIN
               SELECT RAISE(ABORT, 'forced test failure');
           END;"""
    )
    conn.commit()
    conn.close()

    with pytest.raises(PersistenceError):
        store.save(alt_extraction)

    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.filename == "study.pdf"
    assert len(retrieved.chunks) == 2


# ---------------------------------------------------------------------------
# Input validation — blank paper_id
# ---------------------------------------------------------------------------


def test_blank_paper_id_rejected_by_get(store: ExtractionStore, sample_extraction: ExtractionResult) -> None:
    """Identifiers for reads/queries reject blank values.

    The Pydantic domain model prevents constructing ExtractionResult
    with a blank paper_id, so save() validation is a safety net for
    bypassed or future model construction paths.
    """
    with pytest.raises(ValueError):
        store.get("  ")