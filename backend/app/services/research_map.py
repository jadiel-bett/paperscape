"""Research-map generation service.

Transforms a validated :class:`ExtractionResult` into a grounded
:class:`ResearchMap` through an injected :class:`LLMProvider`.

Architecture rules
------------------
- No FastAPI, SQLite, HTTP, or watsonx SDK imports anywhere in this module.
- The service depends only on the ``LLMProvider`` ABC — never on a concrete
  provider.
- The service does not read environment variables or access configuration.
- Evidence is validated against the selected (bounded) chunk set only.
- Paper text, model output, and prompt content are never included in
  exception messages or logs.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap
from app.services.llm_provider import LLMProvider, LLMProviderError

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_MAP_TEMPERATURE: float = 0.1
_MAP_MAX_TOKENS: int = 1500
_DISCLAIMER: str = "This map does not replace expert review."
_CONTEXT_SENTINEL: str = "__PAPER_CONTEXT_JSON__"

# Section-priority configuration.
# Keys are lower-cased section keywords; values are the priority rank
# (lower rank = higher priority).
_HIGH_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {"abstract", "results", "findings", "discussion", "conclusion", "limitations"}
)
_MEDIUM_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {"methods", "methodology", "materials"}
)
_LOW_SECTION_KEYWORDS: frozenset[str] = frozenset({"introduction", "background"})
_EXCLUDED_SECTION_KEYWORDS: frozenset[str] = frozenset(
    {"references", "bibliography", "acknowledgements"}
)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MapGenerationError(RuntimeError):
    """The model did not produce a valid grounded research map."""


# ---------------------------------------------------------------------------
# Issue codes for corrective retry
# ---------------------------------------------------------------------------


class _IssueCode:
    INVALID_JSON = "INVALID_JSON"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    WRONG_FINDING_COUNT = "WRONG_FINDING_COUNT"
    UNKNOWN_CHUNK_ID = "UNKNOWN_CHUNK_ID"
    PAGE_MISMATCH = "PAGE_MISMATCH"
    EXCERPT_NOT_FOUND = "EXCERPT_NOT_FOUND"
    DUPLICATE_FINDING = "DUPLICATE_FINDING"
    DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
    MISSING_LIMITATION = "MISSING_LIMITATION"
    UNCERTAIN_CONFIDENCE = "UNCERTAIN_CONFIDENCE"


# ---------------------------------------------------------------------------
# Unicode normalisation
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    """NFKC-normalize, collapse whitespace, and strip *text*."""
    nfkc = unicodedata.normalize("NFKC", text)
    collapsed = re.sub(r"\s+", " ", nfkc)
    return collapsed.strip()


# ---------------------------------------------------------------------------
# Internal grounded schemas (private)
# ---------------------------------------------------------------------------


class _InternalEvidence(BaseModel):
    """A single evidence record as returned by the model."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=1, max_length=300)

    @field_validator("chunk_id", "excerpt", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class _InternalGroundedStatement(BaseModel):
    """A statement that must carry at least one piece of supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    evidence: list[_InternalEvidence] = Field(min_length=1)

    @field_validator("statement", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class _InternalFinding(BaseModel):
    """A finding with evidence and confidence (no uncertain)."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    evidence: list[_InternalEvidence] = Field(min_length=1)
    confidence: str = Field(...)  # validated post-Pydantic for "high" | "partial"

    @field_validator("statement", mode="before")
    @classmethod
    def _strip_and_require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v

    @field_validator("confidence", mode="after")
    @classmethod
    def _validate_confidence(cls, v: str) -> str:
        if v not in ("high", "partial"):
            raise ValueError(
                'confidence must be "high" or "partial"; got {v!r}'
            )
        return v


class _InternalResearchMap(BaseModel):
    """Complete model output — no paper_id or disclaimer (controlled by service)."""

    model_config = ConfigDict(extra="forbid")

    research_question: _InternalGroundedStatement
    findings: list[_InternalFinding] = Field(min_length=3, max_length=3)
    limitations: list[_InternalGroundedStatement] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Context selection helpers
# ---------------------------------------------------------------------------


def _section_priority(section: str | None) -> int:
    """Return a priority rank for a chunk section (lower = higher priority).

    Priority groups:
        1 — High (abstract, results, findings, discussion, conclusion, limitations)
        2 — Medium (methods, methodology, materials)
        3 — Low (introduction, background)
        4 — No section or no keyword matched
    """
    if section is None:
        return 4
    section_lower = section.lower()
    # Check high priority first (most important content).
    for kw in _HIGH_SECTION_KEYWORDS:
        if kw in section_lower:
            return 1
    for kw in _MEDIUM_SECTION_KEYWORDS:
        if kw in section_lower:
            return 2
    for kw in _LOW_SECTION_KEYWORDS:
        if kw in section_lower:
            return 3
    return 4


def _is_excluded_section(section: str | None) -> bool:
    """Return ``True`` if *section* indicates boilerplate content to exclude."""
    if section is None:
        return False
    section_lower = section.lower()
    for kw in _EXCLUDED_SECTION_KEYWORDS:
        if kw in section_lower:
            return True
    return False


def _word_count(text: str) -> int:
    """Return the number of whitespace-delimited tokens in *text*."""
    return len(text.split())


# ---------------------------------------------------------------------------
# ResearchMapService
# ---------------------------------------------------------------------------


class ResearchMapService:
    """Transform an :class:`ExtractionResult` into a grounded :class:`ResearchMap`.

    Parameters
    ----------
    provider:
        The LLM provider to call for generation.
    prompt_template:
        Optional prompt template.  When ``None``, the template is loaded from
        ``backend/app/prompts/research_map.txt`` on first use.
    max_context_words:
        Maximum number of source words to include in the prompt context.
        Must be at least 1.
    """

    _PROMPT_PATH = Path(__file__).resolve().parents[2] / "app" / "prompts" / "research_map.txt"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        prompt_template: str | None = None,
        max_context_words: int = 6000,
    ) -> None:
        if max_context_words < 1:
            raise ValueError("max_context_words must be at least 1")

        self._provider = provider
        self._max_context_words = max_context_words

        if prompt_template is not None:
            self._raw_template: str = prompt_template
        else:
            self._raw_template = self._PROMPT_PATH.read_text(encoding="utf-8")

        if self._raw_template.count(_CONTEXT_SENTINEL) != 1:
            raise ValueError(
                f"Prompt template must contain exactly one {_CONTEXT_SENTINEL!r} sentinel. "
                f"Found {self._raw_template.count(_CONTEXT_SENTINEL)}."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_map(
        self,
        extraction: ExtractionResult,
    ) -> ResearchMap:
        """Transform an :class:`ExtractionResult` into a grounded :class:`ResearchMap`.

        Raises
        ------
        LLMProviderError
            Provider-level failures propagate unchanged.
        MapGenerationError
            Model output, parsing, schema, or grounding failure.
        """
        # Step 1 — select bounded source chunks.
        selected = self._select_chunks(extraction)

        # Step 2 — build the initial grounded prompt.
        base_prompt = self._build_prompt(selected)

        # Step 3 — first generation attempt.
        issue_codes: set[str] = set()
        try:
            response = self._provider.generate(
                base_prompt,
                max_tokens=_MAP_MAX_TOKENS,
                temperature=_MAP_TEMPERATURE,
            )
            parsed, issues = self._parse_and_validate(response, selected)
            if not issues:
                return self._to_public_map(parsed, extraction.paper_id)
            issue_codes = issues
        except MapGenerationError as exc:
            # Collect issue codes from the exception for retry.
            if hasattr(exc, "_issue_codes"):
                issue_codes = exc._issue_codes  # type: ignore[attr-defined]
            if not issue_codes:
                raise  # Re-raise if no codes were captured.
        except LLMProviderError:
            # Provider failures propagate unchanged — no corrective retry.
            raise

        # Step 4 — corrective retry.
        corrective_prompt = self._build_corrective_prompt(
            base_prompt, issue_codes, selected
        )
        try:
            response = self._provider.generate(
                corrective_prompt,
                max_tokens=_MAP_MAX_TOKENS,
                temperature=_MAP_TEMPERATURE,
            )
            parsed, remaining_issues = self._parse_and_validate(response, selected)
            if remaining_issues:
                raise MapGenerationError(
                    "Research map generation failed after corrective retry."
                )
            return self._to_public_map(parsed, extraction.paper_id)
        except MapGenerationError as exc:
            raise MapGenerationError(
                "Research map generation failed after corrective retry."
            ) from exc

    # ------------------------------------------------------------------
    # Context selection
    # ------------------------------------------------------------------

    def _select_chunks(self, extraction: ExtractionResult) -> list[Chunk]:
        """Select and return a bounded subset of *extraction.chunks*.

        Raises ``MapGenerationError`` when no eligible chunk exists or no
        single chunk fits the budget.
        """
        chunks = extraction.chunks
        if not chunks:
            raise MapGenerationError(
                "Cannot build a research map from an empty extraction."
            )

        # Record original ordinal positions.
        indexed = [(idx, c) for idx, c in enumerate(chunks)]

        # Exclude boilerplate sections.
        eligible = [
            (idx, c) for idx, c in indexed if not _is_excluded_section(c.section)
        ]

        if not eligible:
            raise MapGenerationError(
                "All chunks were excluded as boilerplate (references, "
                "bibliography, or acknowledgements)."
            )

        # Check whether section metadata is useful.
        has_useful_sections = any(
            c.section is not None and not _is_excluded_section(c.section)
            for _, c in eligible
        )

        if has_useful_sections:
            # Priority-based greedy selection.
            sorted_eligible = sorted(
                eligible,
                key=lambda pair: (_section_priority(pair[1].section), pair[0]),
            )
        else:
            # Head-and-tail fallback: alternate from front and back.
            sorted_eligible = _head_and_tail_sort(eligible)

        # Greedily select individual chunks.
        selected_indices: list[int] = []
        running_words = 0

        for orig_idx, chunk in sorted_eligible:
            wc = _word_count(chunk.text)
            if wc == 0:
                _log.debug("Skipping empty-text chunk at original index %d.", orig_idx)
                continue
            if running_words + wc <= self._max_context_words:
                selected_indices.append(orig_idx)
                running_words += wc
            else:
                # Chunk does not fit — continue to next (it may be smaller).
                _log.debug(
                    "Chunk at original index %d (%d words) exceeds remaining budget "
                    "(%d/%d words used); skipping.",
                    orig_idx,
                    wc,
                    running_words,
                    self._max_context_words,
                )

        if not selected_indices:
            raise MapGenerationError(
                "No single chunk fits within the configured context budget "
                f"({self._max_context_words} words)."
            )

        # Restore original document order.
        selected_indices.sort()
        result = [chunks[i] for i in selected_indices]

        _log.debug(
            "Context selection: paper_id=%s, total=%d, excluded=%d, "
            "selected=%d, selected_words=%d, budget_exceeded=%s",
            extraction.paper_id,
            len(chunks),
            len(chunks) - len(eligible),
            len(result),
            running_words,
            running_words > self._max_context_words,
        )
        return result

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(self, selected_chunks: list[Chunk]) -> str:
        """Build the full prompt string for the given *selected_chunks*."""
        serialized = json.dumps(
            [
                {
                    "chunk_id": c.chunk_id,
                    "page": c.page,
                    "section": c.section,
                    "text": c.text,
                }
                for c in selected_chunks
            ],
            ensure_ascii=False,
        )
        return self._raw_template.replace(_CONTEXT_SENTINEL, serialized)

    # ------------------------------------------------------------------
    # Corrective prompt building
    # ------------------------------------------------------------------

    def _build_corrective_prompt(
        self,
        original_prompt: str,
        issue_codes: set[str],
        selected_chunks: list[Chunk],
    ) -> str:
        """Build a corrective prompt with safe issue codes and valid chunks."""
        valid_chunks_json = json.dumps(
            [
                {"chunk_id": c.chunk_id, "page": c.page}
                for c in selected_chunks
            ],
            ensure_ascii=False,
        )
        codes_list = ", ".join(sorted(issue_codes))
        correction_section = (
            "\n\nCORRECTION REQUIRED\n"
            "The previous response contained the following issues:\n"
            f"{codes_list}\n\n"
            "Valid chunk IDs and pages:\n"
            f"{valid_chunks_json}\n\n"
            "Regenerate the complete JSON research map. "
            "Return ONLY valid JSON. No markdown fences, prose, or commentary."
        )
        return original_prompt + correction_section

    # ------------------------------------------------------------------
    # Parsing and validation
    # ------------------------------------------------------------------

    def _parse_and_validate(
        self,
        raw: str,
        selected_chunks: list[Chunk],
    ) -> tuple[_InternalResearchMap, set[str]]:
        """Parse *raw* model output and validate it.

        Returns
        -------
        Tuple of ``(parsed_internal_map, set_of_issue_codes)``.
        When ``issues`` is empty the map is fully valid.
        """
        issues: set[str] = set()

        # --- Step 1: parse JSON ---
        trimmed = raw.strip()

        # Optional fence removal.
        if trimmed.startswith("```json\n"):
            # Remove opening fence.
            trimmed = trimmed[len("```json\n"):]
            if trimmed.endswith("```"):
                trimmed = trimmed[:-3].strip()
            # If the fence was on the same line, also handle that.
        elif trimmed.startswith("```json"):
            trimmed = trimmed[len("```json"):]
            if trimmed.endswith("```"):
                trimmed = trimmed[:-3].strip()
        elif trimmed.startswith("```") and not trimmed.startswith("```json"):
            # Plain ``` without json marker -> reject.
            issues.add(_IssueCode.INVALID_JSON)
            exc = MapGenerationError("Model output uses unmarked code fences.")
            exc._issue_codes = issues  # type: ignore[attr-defined]
            raise exc

        if not (trimmed.startswith("{") and trimmed.endswith("}")):
            issues.add(_IssueCode.INVALID_JSON)
            exc = MapGenerationError("Model output does not contain a JSON object.")
            exc._issue_codes = issues
            raise exc

        try:
            obj: dict[str, Any] = json.loads(trimmed)
        except json.JSONDecodeError:
            issues.add(_IssueCode.INVALID_JSON)
            exc = MapGenerationError("Model output contains malformed JSON.")
            exc._issue_codes = issues
            raise exc

        # --- Step 2: Pydantic validation ---
        try:
            parsed = _InternalResearchMap.model_validate(obj)
        except Exception:
            issues.add(_IssueCode.INVALID_SCHEMA)
            exc = MapGenerationError(
                "Model output does not conform to the expected schema."
            )
            exc._issue_codes = issues
            raise exc

        # --- Step 3: specific schema post-checks ---
        if len(parsed.findings) != 3:
            issues.add(_IssueCode.WRONG_FINDING_COUNT)

        if not parsed.limitations:
            issues.add(_IssueCode.MISSING_LIMITATION)

        # Confidence already validated by Pydantic on _InternalFinding,
        # but check for unexpected values.
        for finding in parsed.findings:
            if finding.confidence not in ("high", "partial"):
                issues.add(_IssueCode.UNCERTAIN_CONFIDENCE)

        # --- Step 4: evidence grounding ---
        grounding_issues = self._validate_evidence(parsed, selected_chunks)
        issues.update(grounding_issues)

        return parsed, issues

    # ------------------------------------------------------------------
    # Evidence grounding validation
    # ------------------------------------------------------------------

    def _validate_evidence(
        self,
        internal_map: _InternalResearchMap,
        selected_chunks: list[Chunk],
    ) -> set[str]:
        """Validate all evidence against the selected chunks.

        Returns a set of issue codes; an empty set means all evidence is valid.
        """
        issues: set[str] = set()

        selected_lookup: dict[str, Chunk] = {
            c.chunk_id: c for c in selected_chunks
        }

        all_grounded: list[tuple[str, list[_InternalEvidence], str]] = [
            ("research_question", internal_map.research_question.evidence, ""),
        ]
        for idx, finding in enumerate(internal_map.findings):
            all_grounded.append((f"finding[{idx}]", finding.evidence, finding.statement))
        for idx, lim in enumerate(internal_map.limitations):
            all_grounded.append((f"limitation[{idx}]", lim.evidence, lim.statement))

        # Check findings distinctness.
        finding_statements_normalized = [
            _normalize_text(f.statement).casefold() for f in internal_map.findings
        ]
        if len(set(finding_statements_normalized)) != len(finding_statements_normalized):
            issues.add(_IssueCode.DUPLICATE_FINDING)

        for label, evidence_list, owner_text in all_grounded:
            seen_evidence_keys: set[tuple[str, int, str]] = set()

            for ev_idx, ev in enumerate(evidence_list):
                # chunk_id exists in selected_lookup.
                if ev.chunk_id not in selected_lookup:
                    issues.add(_IssueCode.UNKNOWN_CHUNK_ID)
                    continue

                source_chunk = selected_lookup[ev.chunk_id]

                # page match.
                if ev.page != source_chunk.page:
                    issues.add(_IssueCode.PAGE_MISMATCH)
                    continue

                # excerpt containment.
                norm_excerpt = _normalize_text(ev.excerpt)
                norm_source = _normalize_text(source_chunk.text)
                if norm_excerpt not in norm_source:
                    issues.add(_IssueCode.EXCERPT_NOT_FOUND)
                    continue

                # exact duplicate evidence within this grounded statement.
                ev_key = (ev.chunk_id, ev.page, norm_excerpt)
                if ev_key in seen_evidence_keys:
                    issues.add(_IssueCode.DUPLICATE_EVIDENCE)
                else:
                    seen_evidence_keys.add(ev_key)

        # Check evidence presence for all grounded statements.
        if not internal_map.research_question.evidence:
            issues.add(_IssueCode.INVALID_SCHEMA)

        for finding in internal_map.findings:
            if not finding.evidence:
                issues.add(_IssueCode.INVALID_SCHEMA)

        for lim in internal_map.limitations:
            if not lim.evidence:
                issues.add(_IssueCode.INVALID_SCHEMA)

        return issues

    # ------------------------------------------------------------------
    # Conversion to public ResearchMap
    # ------------------------------------------------------------------

    def _to_public_map(
        self,
        internal: _InternalResearchMap,
        paper_id: str,
    ) -> ResearchMap:
        """Convert an internal draft to the public :class:`ResearchMap`."""
        return ResearchMap(
            paper_id=paper_id,
            research_question=internal.research_question.statement,
            findings=[
                Finding(
                    statement=f.statement,
                    evidence=[
                        Evidence(
                            chunk_id=e.chunk_id,
                            page=e.page,
                            excerpt=e.excerpt,
                        )
                        for e in f.evidence
                    ],
                    confidence=f.confidence,
                )
                for f in internal.findings
            ],
            limitations=[item.statement for item in internal.limitations],
            disclaimer=_DISCLAIMER,
        )


# ---------------------------------------------------------------------------
# Head-and-tail sorting
# ---------------------------------------------------------------------------


def _head_and_tail_sort(
    pairs: list[tuple[int, Chunk]],
) -> list[tuple[int, Chunk]]:
    """Return a list alternating between front and back elements.

    Example for ``[a, b, c, d, e]`` → ``[a, e, b, d, c]``.
    This ensures both early and late content is prioritised when no
    section metadata is available.
    """
    n = len(pairs)
    result: list[tuple[int, Chunk]] = []
    left = 0
    right = n - 1
    toggle = True
    while left <= right:
        if toggle:
            result.append(pairs[left])
            left += 1
        else:
            result.append(pairs[right])
            right -= 1
        toggle = not toggle
    return result