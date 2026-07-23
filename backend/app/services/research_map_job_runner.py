"""Synchronous research-map job runner invoked by FastAPI BackgroundTasks.

Orchestrates the end-to-end execution of a research-map generation job:
claim the job via atomic transition, load the extraction, generate the map,
persist the result, and mark the job succeeded.  All operational failures
are captured as safe error codes.
"""
from __future__ import annotations

import logging

from app.repositories import (
    ExtractionStore,
    InvalidJobTransitionError,
    JobStore,
    PersistenceError,
    RecordNotFoundError,
    ResearchMapStore,
)
from app.services.llm_provider import LLMProviderError
from app.services.research_map import MapGenerationError, ResearchMapService

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error codes (all match ^[a-z][a-z0-9_]{0,63}$)
# ---------------------------------------------------------------------------

_EXTRACTION_MISSING = "extraction_missing"
_MAP_GENERATION_FAILED = "map_generation_failed"
_LLM_PROVIDER_ERROR = "llm_provider_error"
_PERSISTENCE_ERROR = "persistence_error"
_UNEXPECTED_ERROR = "unexpected_error"


# ---------------------------------------------------------------------------
# ResearchMapJobRunner
# ---------------------------------------------------------------------------


class ResearchMapJobRunner:
    """Synchronous job runner for research-map generation.

    Designed to be passed to ``BackgroundTasks.add_task()``.  All expected
    operational failures are caught and persisted as safe error codes.  The
    ``run()`` method never re-raises an expected failure.

    Parameters
    ----------
    job_store:
        Repository for job lifecycle transitions.
    extraction_store:
        Repository for persisted extraction results.
    research_map_store:
        Repository for persisted research maps.
    research_map_service:
        Service that transforms an ``ExtractionResult`` into a ``ResearchMap``
        via an injected ``LLMProvider``.
    """

    def __init__(
        self,
        *,
        job_store: JobStore,
        extraction_store: ExtractionStore,
        research_map_store: ResearchMapStore,
        research_map_service: ResearchMapService,
    ) -> None:
        self._job_store = job_store
        self._extraction_store = extraction_store
        self._research_map_store = research_map_store
        self._research_map_service = research_map_service

    def run(self, job_id: str) -> None:
        """Execute the research-map generation job.

        Never raises expected failures.  Catches operational failures,
        persists a safe error code, and returns ``None``.
        """
        _log.debug("Job runner starting for job_id=%r.", job_id)

        # ---- Step 1: claim the job (pending → running) ----
        try:
            job = self._job_store.mark_running(job_id)
        except RecordNotFoundError:
            _log.warning("Job %r not found; cannot claim.", job_id)
            return
        except InvalidJobTransitionError:
            _log.warning(
                "Job %r is not pending; another worker may have claimed it.",
                job_id,
            )
            return

        # ---- Step 2: load the persisted extraction ----
        try:
            extraction = self._extraction_store.require(job.paper_id)
        except RecordNotFoundError:
            _log.error("Extraction for paper_id=%r not found.", job.paper_id)
            self._mark_failed(job_id, _EXTRACTION_MISSING)
            return
        except PersistenceError as exc:
            _log.error(
                "Persistence error loading extraction for paper_id=%r: %s",
                job.paper_id,
                type(exc).__name__,
            )
            self._mark_failed(job_id, _PERSISTENCE_ERROR)
            return

        # ---- Step 3: generate the research map (no transaction open) ----
        try:
            research_map = self._research_map_service.generate_map(extraction)
        except MapGenerationError:
            _log.error(
                "Map generation failed for paper_id=%r.", job.paper_id,
            )
            self._mark_failed(job_id, _MAP_GENERATION_FAILED)
            return
        except LLMProviderError:
            _log.error(
                "LLM provider error for paper_id=%r.", job.paper_id,
            )
            self._mark_failed(job_id, _LLM_PROVIDER_ERROR)
            return
        except Exception as exc:
            _log.error(
                "Unexpected error during map generation for paper_id=%r: %s",
                job.paper_id,
                type(exc).__name__,
            )
            self._mark_failed(job_id, _UNEXPECTED_ERROR)
            return

        # ---- Step 4: persist the research map ----
        try:
            self._research_map_store.save(research_map)
        except PersistenceError as exc:
            _log.error(
                "Persistence error saving research map for paper_id=%r: %s",
                job.paper_id,
                type(exc).__name__,
            )
            self._mark_failed(job_id, _PERSISTENCE_ERROR)
            return

        # ---- Step 5: mark the job succeeded ----
        try:
            self._job_store.mark_succeeded(job_id)
        except (RecordNotFoundError, InvalidJobTransitionError, PersistenceError) as exc:
            _log.error(
                "Failed to mark job %r succeeded after map save: %s",
                job_id,
                type(exc).__name__,
            )
            # The map is persisted, but we cannot mark the job succeeded.
            # Best-effort mark_failed so the retrieval logic (latest job check)
            # hides this orphaned map.
            self._mark_failed(job_id, _PERSISTENCE_ERROR)
            return

        _log.info("Job %r completed successfully.", job_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mark_failed(self, job_id: str, error_code: str) -> None:
        """Best-effort attempt to mark *job_id* as failed.

        Failures during this call are logged but never re-raised.
        """
        try:
            self._job_store.mark_failed(job_id, error_code=error_code)
            _log.info("Job %r marked failed with code=%r.", job_id, error_code)
        except (RecordNotFoundError, InvalidJobTransitionError):
            # Job may already be in a terminal state — that is fine.
            _log.debug(
                "Could not mark job %r failed (already terminal): code=%r.",
                job_id,
                error_code,
            )
        except PersistenceError as exc:
            _log.error(
                "Persistence error marking job %r failed: %s",
                job_id,
                type(exc).__name__,
            )