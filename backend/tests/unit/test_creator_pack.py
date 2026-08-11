from app.models.creator_pack import AudienceType, CreatorPackStatus
from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap
from app.services.creator_pack import CreatorPackService


def _research_map() -> ResearchMap:
    return ResearchMap(
        paper_id="paper-1",
        research_question="What changed?",
        findings=[
            Finding(statement="Finding one", evidence=[Evidence(chunk_id="c1", page=1, excerpt="Finding one")], confidence="high"),
            Finding(statement="Finding two", evidence=[Evidence(chunk_id="c2", page=2, excerpt="Finding two")], confidence="partial"),
            Finding(statement="Finding three", evidence=[Evidence(chunk_id="c3", page=3, excerpt="Finding three")], confidence="uncertain"),
        ],
        limitations=["Small sample"],
    )


def test_creator_pack_is_derived_from_map_and_mints_evidence_ids():
    pack = CreatorPackService().generate(_research_map(), AudienceType.HIGH_SCHOOL)
    assert pack.status is CreatorPackStatus.DRAFT
    assert "paper-1:f0:e0" in pack.evidence_cards[0].evidence_ids
    assert "Small sample" in pack.narration_script
    assert pack.disclaimer.startswith("This AI-generated explanation")

