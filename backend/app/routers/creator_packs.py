"""Creator-pack generation and human approval routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.dependencies import (
    AppException,
    get_creator_pack_service,
    get_creator_pack_store,
    get_job_store,
    get_research_map_store,
)
from app.models.creator_pack import (
    CreatorPackApprovalRequest,
    CreatorPackCreateRequest,
    CreatorPackUpdateRequest,
    CreatorPackStatus,
)
from app.models.job import JobStatus
from app.repositories import CreatorPackStore, JobStore, ResearchMapStore
from app.repositories.errors import PersistenceError
from app.services.creator_pack import CreatorPackService

router = APIRouter(prefix="/papers", tags=["creator-packs"])


def _require_completed_map(paper_id: str, job_store: JobStore, research_map_store: ResearchMapStore):
    paper_id = paper_id.strip()
    if not paper_id:
        raise AppException(400, "invalid_identifier", "Paper identifier must not be blank.")
    try:
        latest = job_store.get_latest_job_for_paper(paper_id)
        research_map = research_map_store.get(paper_id)
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc
    if latest is None or latest.status != JobStatus.SUCCEEDED or research_map is None:
        raise AppException(404, "map_not_found", "A completed research map is required first.")
    return research_map


@router.post("/{paper_id}/creator-packs", status_code=201)
def create_creator_pack(
    paper_id: str,
    request: CreatorPackCreateRequest,
    job_store: JobStore = Depends(get_job_store),
    research_map_store: ResearchMapStore = Depends(get_research_map_store),
    service: CreatorPackService = Depends(get_creator_pack_service),
    store: CreatorPackStore = Depends(get_creator_pack_store),
):
    research_map = _require_completed_map(paper_id, job_store, research_map_store)
    pack = service.generate(research_map, request.audience)
    try:
        store.save(pack)
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc
    return pack


@router.get("/{paper_id}/creator-packs")
def list_creator_packs(
    paper_id: str,
    store: CreatorPackStore = Depends(get_creator_pack_store),
):
    try:
        return store.list_for_paper(paper_id.strip())
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc


@router.post("/{paper_id}/creator-packs/{pack_id}/approve")
def approve_creator_pack(
    paper_id: str,
    pack_id: str,
    request: CreatorPackApprovalRequest,
    store: CreatorPackStore = Depends(get_creator_pack_store),
):
    try:
        pack = store.get(pack_id.strip())
        if pack is None or pack.paper_id != paper_id.strip():
            raise AppException(404, "pack_not_found", "Creator pack was not found.")
        pack.status = CreatorPackStatus.APPROVED if request.approved else CreatorPackStatus.DRAFT
        store.save(pack)
        return pack
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc


@router.patch("/{paper_id}/creator-packs/{pack_id}")
def update_creator_pack(
    paper_id: str,
    pack_id: str,
    request: CreatorPackUpdateRequest,
    store: CreatorPackStore = Depends(get_creator_pack_store),
):
    try:
        pack = store.get(pack_id.strip())
        if pack is None or pack.paper_id != paper_id.strip():
            raise AppException(404, "pack_not_found", "Creator pack was not found.")
        if pack.status == CreatorPackStatus.APPROVED:
            raise AppException(409, "pack_locked", "Approved creator packs are locked; duplicate the pack to edit it.")
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(pack, field, value)
        store.save(pack)
        return pack
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc


@router.get("/{paper_id}/creator-packs/{pack_id}/export", response_class=PlainTextResponse)
def export_creator_pack(
    paper_id: str,
    pack_id: str,
    store: CreatorPackStore = Depends(get_creator_pack_store),
):
    try:
        pack = store.get(pack_id.strip())
        if pack is None or pack.paper_id != paper_id.strip():
            raise AppException(404, "pack_not_found", "Creator pack was not found.")
        if pack.status != CreatorPackStatus.APPROVED:
            raise AppException(409, "pack_not_approved", "Approve the creator pack before exporting it.")
        cards = "\n".join(f"- {card.statement} ({card.confidence})" for card in pack.evidence_cards)
        visual = "\n".join(f"### {block.label}\n{block.text}" for block in pack.visual_abstract)
        return f"# {pack.title}\n\n{pack.summary}\n\n## Evidence cards\n{cards}\n\n## Narration script\n{pack.narration_script}\n\n## Visual abstract\n{visual}\n\n## Limitations\n" + "\n".join(f"- {item}" for item in pack.limitations) + f"\n\n{pack.disclaimer}\n"
    except PersistenceError as exc:
        raise AppException(500, "persistence_error", "A storage error occurred. Please try again.") from exc
