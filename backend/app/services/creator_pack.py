"""Deterministic creator-pack generation from validated research-map records."""
from __future__ import annotations

from app.models.creator_pack import (
    AudienceType,
    CreatorPack,
    EvidenceCard,
    GlossaryEntry,
    ResolvedEvidence,
    VisualAbstractBlock,
)
from app.models.research_map import ResearchMap


_AUDIENCE_GUIDANCE = {
    AudienceType.GENERAL_PUBLIC: "in clear everyday language",
    AudienceType.HIGH_SCHOOL: "using simple language and briefly explaining technical terms",
    AudienceType.UNDERGRADUATE: "using introductory scientific language while preserving uncertainty",
}


class CreatorPackService:
    """Build a safe first draft without re-interpreting the paper.

    This deliberately uses only verified map statements and evidence. A later
    model-backed adaptation can replace the prose builder while retaining the
    same input/output contract and validators.
    """

    def generate(self, research_map: ResearchMap, audience: AudienceType) -> CreatorPack:
        guidance = _AUDIENCE_GUIDANCE[audience]
        cards = [
            EvidenceCard(
                finding_index=index,
                statement=finding.statement,
                # Mint stable backend evidence IDs; the source chunk IDs stay
                # private to the resolver and are never authored by a model.
                evidence_ids=[f"{research_map.paper_id}:f{index}:e{evidence_index}" for evidence_index, _ in enumerate(finding.evidence)],
                confidence=finding.confidence,
                evidence=[
                    ResolvedEvidence(
                        evidence_id=f"{research_map.paper_id}:f{index}:e{evidence_index}",
                        chunk_id=evidence.chunk_id,
                        page=evidence.page,
                        excerpt=evidence.excerpt,
                    )
                    for evidence_index, evidence in enumerate(finding.evidence)
                ],
            )
            for index, finding in enumerate(research_map.findings)
        ]
        findings_text = " ".join(f.statement for f in research_map.findings)
        summary = (
            f"This research asks: {research_map.research_question}. "
            f"The key findings are {guidance}: {findings_text}"
        )
        script = (
            f"In this paper, researchers asked: {research_map.research_question}. "
            f"Here is what they found: {findings_text} "
            f"Important limitations include: {'; '.join(research_map.limitations)}"
        )
        blocks = [
            VisualAbstractBlock(label="Research question", text=research_map.research_question),
            VisualAbstractBlock(
                label="Key findings",
                text=findings_text,
                evidence_ids=[
                    f"{research_map.paper_id}:f{finding_index}:e{evidence_index}"
                    for finding_index, finding in enumerate(research_map.findings)
                    for evidence_index, _ in enumerate(finding.evidence)
                ],
            ),
            VisualAbstractBlock(label="Limitations", text="; ".join(research_map.limitations)),
        ]
        return CreatorPack(
            paper_id=research_map.paper_id,
            audience=audience,
            title=f"Research explainer: {research_map.research_question}",
            summary=summary,
            narration_script=script,
            visual_abstract=blocks,
            evidence_cards=cards,
            glossary=[],
            limitations=research_map.limitations,
            disclaimer=research_map.disclaimer,
        )
