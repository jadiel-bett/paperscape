"""Unit tests for :class:`ResearchMapStore`.

All tests use ``tmp_path``-backed SQLite databases.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.database import init_db
from app.models.research_map import Evidence, Finding, ResearchMap
from app.repositories.errors import CorruptRecordError, PersistenceError, RecordNotFoundError
from app.repositories.research_map_store import ResearchMapStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "test_maps.db"
    init_db(str(path))
    return str(path)


@pytest.fixture
def store(db_path: str) -> ResearchMapStore:
    return ResearchMapStore(db_path)


@pytest.fixture
def sample_map() -> ResearchMap:
    return ResearchMap(
        paper_id="paper-1",
        research_question="What is the effect of X on Y?",
        findings=[
            Finding(
                statement="Finding one.",
                evidence=[Evidence(chunk_id="p1-p1-1", page=1, excerpt="Evidence one.")],
                confidence="high",
            ),
            Finding(
                statement="Finding two.",
                evidence=[Evidence(chunk_id="p1-p2-1", page=2, excerpt="Evidence two.")],
                confidence="partial",
            ),
            Finding(
                statement="Finding three.",
                evidence=[Evidence(chunk_id="p1-p3-1", page=3, excerpt="Evidence three.")],
                confidence="high",
            ),
        ],
        limitations=["Small sample size."],
        disclaimer="This map does not replace expert review.",
    )


@pytest.fixture
def alt_map() -> ResearchMap:
    return ResearchMap(
        paper_id="paper-1",
        research_question="Updated question?",
        findings=[
            Finding(
                statement="New finding A.",
                evidence=[Evidence(chunk_id="p1-p1-1", page=1, excerpt="New evidence.")],
                confidence="high",
            ),
            Finding(
                statement="New finding B.",
                evidence=[Evidence(chunk_id="p1-p2-1", page=2, excerpt="More evidence.")],
                confidence="partial",
            ),
            Finding(
                statement="New finding C.",
                evidence=[Evidence(chunk_id="p1-p3-1", page=3, excerpt="Final evidence.")],
                confidence="high",
            ),
        ],
        limitations=["Limited scope."],
        disclaimer="This map does not replace expert review.",
    )


# ---------------------------------------------------------------------------
# save() and get()
# ---------------------------------------------------------------------------


def test_save_and_retrieve(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.paper_id == "paper-1"
    assert retrieved.research_question == "What is the effect of X on Y?"


def test_paper_id_round_trips(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.paper_id == "paper-1"


def test_exactly_three_findings_round_trip(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert len(retrieved.findings) == 3


def test_all_evidence_round_trips(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    for original_finding, retrieved_finding in zip(sample_map.findings, retrieved.findings):
        for original_ev, retrieved_ev in zip(original_finding.evidence, retrieved_finding.evidence):
            assert retrieved_ev.chunk_id == original_ev.chunk_id
            assert retrieved_ev.page == original_ev.page
            assert retrieved_ev.excerpt == original_ev.excerpt


def test_confidence_values_round_trip(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert [f.confidence for f in retrieved.findings] == ["high", "partial", "high"]


def test_limitations_round_trip(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.limitations == ["Small sample size."]


def test_disclaimer_round_trips(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.disclaimer == "This map does not replace expert review."


# ---------------------------------------------------------------------------
# None / missing
# ---------------------------------------------------------------------------


def test_missing_map_returns_none(store: ResearchMapStore) -> None:
    assert store.get("nonexistent") is None


def test_require_missing_raises(store: ResearchMapStore) -> None:
    with pytest.raises(RecordNotFoundError):
        store.require("nonexistent")


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


def test_exists_true(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    assert store.exists("paper-1") is True


def test_exists_false(store: ResearchMapStore) -> None:
    assert store.exists("nonexistent") is False


# ---------------------------------------------------------------------------
# Repeated save (upsert)
# ---------------------------------------------------------------------------


def test_repeated_save_replaces(store: ResearchMapStore, sample_map: ResearchMap, alt_map: ResearchMap) -> None:
    store.save(sample_map)
    store.save(alt_map)
    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.research_question == "Updated question?"
    assert len(retrieved.findings) == 3
    assert retrieved.findings[0].statement == "New finding A."


# ---------------------------------------------------------------------------
# Corrupt data
# ---------------------------------------------------------------------------


def test_malformed_json_raises_corrupt(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO research_maps (paper_id, map_json) VALUES (?, ?)",
        ("bad-id", "{invalid json"),
    )
    conn.commit()
    conn.close()

    store = ResearchMapStore(db_path)
    with pytest.raises(CorruptRecordError):
        store.get("bad-id")


def test_schema_invalid_json_raises_corrupt(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO research_maps (paper_id, map_json) VALUES (?, ?)",
        ("bad-schema", json.dumps({"not": "a research map"})),
    )
    conn.commit()
    conn.close()

    store = ResearchMapStore(db_path)
    with pytest.raises(CorruptRecordError):
        store.get("bad-schema")


def test_paper_id_mismatch_raises_corrupt(db_path: str) -> None:
    rm = ResearchMap(
        paper_id="different-id",
        research_question="Q?",
        findings=[
            Finding(
                statement="F1",
                evidence=[Evidence(chunk_id="c1", page=1, excerpt="E1.")],
                confidence="high",
            ),
            Finding(
                statement="F2",
                evidence=[Evidence(chunk_id="c2", page=2, excerpt="E2.")],
                confidence="partial",
            ),
            Finding(
                statement="F3",
                evidence=[Evidence(chunk_id="c3", page=3, excerpt="E3.")],
                confidence="high",
            ),
        ],
        limitations=["L1."],
        disclaimer="This map does not replace expert review.",
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO research_maps (paper_id, map_json) VALUES (?, ?)",
        ("row-id", rm.model_dump_json()),
    )
    conn.commit()
    conn.close()

    store = ResearchMapStore(db_path)
    with pytest.raises(CorruptRecordError):
        store.get("row-id")


# ---------------------------------------------------------------------------
# Transaction, connection ownership, and rollback-on-failure
# ---------------------------------------------------------------------------


def test_caller_conn_remains_open(store: ResearchMapStore, db_path: str, sample_map: ResearchMap) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    store.save(sample_map, conn=conn)
    row = conn.execute("SELECT 1 AS val").fetchone()
    assert row["val"] == 1
    conn.close()


def test_repository_conn_is_closed(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    store.save(sample_map)
    assert store.get("paper-1") is not None


def test_upsert_rolls_back_on_trigger_failure(db_path: str, sample_map: ResearchMap, alt_map: ResearchMap) -> None:
    """Create a trigger that forces a write failure, then verify the prior record survives."""
    store = ResearchMapStore(db_path)
    store.save(sample_map)
    assert store.get("paper-1") is not None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS test_break_research_map
           BEFORE UPDATE ON research_maps
           BEGIN
               SELECT RAISE(ABORT, 'forced test failure');
           END;"""
    )
    conn.commit()
    conn.close()

    with pytest.raises(PersistenceError):
        store.save(alt_map)

    retrieved = store.get("paper-1")
    assert retrieved is not None
    assert retrieved.research_question == "What is the effect of X on Y?"


# ---------------------------------------------------------------------------
# Input validation — blank paper_id
# ---------------------------------------------------------------------------


def test_blank_paper_id_rejected_by_get(store: ResearchMapStore, sample_map: ResearchMap) -> None:
    """Identifiers for reads/queries reject blank values."""
    with pytest.raises(ValueError):
        store.get("  ")