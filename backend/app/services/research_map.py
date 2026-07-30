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
from collections.abc import Iterable
from dataclasses import dataclass
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
_DISCLAIMER: str = (
    "This AI-generated explanation is grounded in the uploaded document but "
    "does not replace expert review."
)
_CONTEXT_SENTINEL: str = "__PAPER_CONTEXT_JSON__"
_MAX_EVIDENCE_SPAN_CHARS: int = 300

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
# Issue codes for corrective retry
# ---------------------------------------------------------------------------


class _IssueCode:
    INVALID_JSON = "INVALID_JSON"
    INVALID_SCHEMA = "INVALID_SCHEMA"
    WRONG_FINDING_COUNT = "WRONG_FINDING_COUNT"
    UNKNOWN_EVIDENCE_ID = "UNKNOWN_EVIDENCE_ID"
    DUPLICATE_FINDING = "DUPLICATE_FINDING"
    DUPLICATE_EVIDENCE = "DUPLICATE_EVIDENCE"
    MISSING_LIMITATION = "MISSING_LIMITATION"
    UNCERTAIN_CONFIDENCE = "UNCERTAIN_CONFIDENCE"


_SAFE_ISSUE_CODES: frozenset[str] = frozenset(
    {
        _IssueCode.INVALID_JSON,
        _IssueCode.INVALID_SCHEMA,
        _IssueCode.WRONG_FINDING_COUNT,
        _IssueCode.UNKNOWN_EVIDENCE_ID,
        _IssueCode.DUPLICATE_FINDING,
        _IssueCode.DUPLICATE_EVIDENCE,
        _IssueCode.MISSING_LIMITATION,
        _IssueCode.UNCERTAIN_CONFIDENCE,
    }
)


def _safe_issue_codes(issue_codes: Iterable[str]) -> frozenset[str]:
    """Return only fixed, non-sensitive ResearchMap validation issue codes."""
    return frozenset(issue_codes) & _SAFE_ISSUE_CODES


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MapGenerationError(RuntimeError):
    """The model did not produce a valid grounded research map."""

    def __init__(
        self,
        message: str,
        *,
        issue_codes: Iterable[str] | None = None,
    ) -> None:
        super().__init__(message)
        self._issue_codes = _safe_issue_codes(issue_codes or ())

    @property
    def issue_codes(self) -> frozenset[str]:
        """Return the safe validation issue codes carried by this error."""
        return self._issue_codes


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


@dataclass(frozen=True, slots=True)
class _EvidenceSpan:
    """Backend-owned source span exposed to the model by an opaque ID."""

    evidence_id: str
    chunk_id: str
    page: int
    section: str | None
    text: str


class _InternalEvidenceReference(BaseModel):
    """A model-returned reference to a backend-owned evidence span."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)

    @field_validator("evidence_id", mode="before")
    @classmethod
    def _require_nonblank(cls, v: object) -> object:
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("Field must not be blank or whitespace-only.")
        return v


class _InternalGroundedStatement(BaseModel):
    """A statement that must carry at least one piece of supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1)
    evidence: list[_InternalEvidenceReference] = Field(min_length=1)

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
    evidence: list[_InternalEvidenceReference] = Field(min_length=1)
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


def _split_evidence_text(text: str) -> list[str]:
    """Split source text into deterministic exact spans of at most 300 chars."""
    if not text.strip():
        return []

    if len(text.strip()) <= _MAX_EVIDENCE_SPAN_CHARS:
        return [text.strip()]

    spans: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        while start < text_length and text[start].isspace():
            start += 1
        if start >= text_length:
            break

        limit = min(start + _MAX_EVIDENCE_SPAN_CHARS, text_length)
        end = limit

        if limit < text_length:
            paragraph_break = text.rfind("\n\n", start + 1, limit + 1)
            if paragraph_break > start:
                end = paragraph_break
            else:
                sentence_ends = list(
                    re.finditer(r"[.!?](?=\s|$)", text[start:limit])
                )
                if sentence_ends:
                    end = start + sentence_ends[-1].end()
                else:
                    whitespace_break = max(
                        text.rfind(" ", start + 1, limit + 1),
                        text.rfind("\n", start + 1, limit + 1),
                        text.rfind("\t", start + 1, limit + 1),
                    )
                    if whitespace_break > start:
                        end = whitespace_break

        span = text[start:end].strip()
        if span:
            spans.append(span)
        start = end

    return spans


def _build_evidence_catalogue(selected_chunks: list[Chunk]) -> list[_EvidenceSpan]:
    """Build stable backend-owned evidence spans in selected-document order."""
    catalogue: list[_EvidenceSpan] = []
    for chunk in selected_chunks:
        for text in _split_evidence_text(chunk.text):
            catalogue.append(
                _EvidenceSpan(
                    evidence_id=f"E{len(catalogue) + 1:04d}",
                    chunk_id=chunk.chunk_id,
                    page=chunk.page,
                    section=chunk.section,
                    text=text,
                )
            )
    return catalogue


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
        evidence_catalogue = _build_evidence_catalogue(selected)

        # Step 2 — build the initial grounded prompt.
        base_prompt = self._build_prompt(evidence_catalogue)

        # Step 3 — first generation attempt.
        issue_codes: set[str] = set()
        try:
            response = self._provider.generate(
                base_prompt,
                max_tokens=_MAP_MAX_TOKENS,
                temperature=_MAP_TEMPERATURE,
            )
            parsed, issues = self._parse_and_validate(response, evidence_catalogue)
            if not issues:
                return self._to_public_map(
                    parsed, extraction.paper_id, evidence_catalogue
                )
            issue_codes = set(_safe_issue_codes(issues))
        except MapGenerationError as exc:
            issue_codes = set(exc.issue_codes)
            _log.warning(
                "Research map validation failed: attempt=1 issue_codes=%s",
                sorted(issue_codes) or ["UNKNOWN"],
            )
            if not issue_codes:
                raise  # Re-raise if no codes were captured.
        except LLMProviderError:
            # Provider failures propagate unchanged — no corrective retry.
            raise
        else:
            _log.warning(
                "Research map validation failed: attempt=1 issue_codes=%s",
                sorted(issue_codes) or ["UNKNOWN"],
            )

        # Step 4 — corrective retry.
        corrective_prompt = self._build_corrective_prompt(
            base_prompt, issue_codes, evidence_catalogue
        )
        try:
            response = self._provider.generate(
                corrective_prompt,
                max_tokens=_MAP_MAX_TOKENS,
                temperature=_MAP_TEMPERATURE,
            )
            parsed, remaining_issues = self._parse_and_validate(
                response, evidence_catalogue
            )
            if remaining_issues:
                final_error = MapGenerationError(
                    "Research map generation failed after corrective retry.",
                    issue_codes=remaining_issues,
                )
            else:
                return self._to_public_map(
                    parsed, extraction.paper_id, evidence_catalogue
                )
        except MapGenerationError as exc:
            final_error = MapGenerationError(
                "Research map generation failed after corrective retry.",
                issue_codes=exc.issue_codes,
            )
            _log.warning(
                "Research map validation failed: attempt=2 issue_codes=%s",
                sorted(final_error.issue_codes) or ["UNKNOWN"],
            )
            raise final_error from exc

        _log.warning(
            "Research map validation failed: attempt=2 issue_codes=%s",
            sorted(final_error.issue_codes) or ["UNKNOWN"],
        )
        raise final_error

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

    def _build_prompt(self, evidence_catalogue: list[_EvidenceSpan]) -> str:
        """Build the full prompt string for the backend evidence catalogue."""
        serialized = json.dumps(
            [
                {
                    "evidence_id": span.evidence_id,
                    "chunk_id": span.chunk_id,
                    "page": span.page,
                    "section": span.section,
                    "text": span.text,
                }
                for span in evidence_catalogue
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
        evidence_catalogue: list[_EvidenceSpan],
    ) -> str:
        """Build a corrective prompt with safe issue codes and evidence IDs."""
        valid_evidence_ids = json.dumps(
            [span.evidence_id for span in evidence_catalogue]
        )
        codes_list = ", ".join(sorted(issue_codes))
        correction_section = (
            "\n\nCORRECTION REQUIRED\n"
            "The previous response contained the following issues:\n"
            f"{codes_list}\n\n"
            "Valid evidence IDs:\n"
            f"{valid_evidence_ids}\n\n"
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
        evidence_catalogue: list[_EvidenceSpan],
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
            raise MapGenerationError(
                "Model output uses unmarked code fences.",
                issue_codes=issues,
            )

        if not (trimmed.startswith("{") and trimmed.endswith("}")):
            issues.add(_IssueCode.INVALID_JSON)
            raise MapGenerationError(
                "Model output does not contain a JSON object.",
                issue_codes=issues,
            )

        try:
            obj: dict[str, Any] = json.loads(trimmed)
        except json.JSONDecodeError:
            issues.add(_IssueCode.INVALID_JSON)
            raise MapGenerationError(
                "Model output contains malformed JSON.",
                issue_codes=issues,
            )

        # --- Step 2: Pydantic validation ---
        try:
            parsed = _InternalResearchMap.model_validate(obj)
        except Exception:
            issues.add(_IssueCode.INVALID_SCHEMA)
            raise MapGenerationError(
                "Model output does not conform to the expected schema.",
                issue_codes=issues,
            )

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
        grounding_issues = self._validate_evidence(parsed, evidence_catalogue)
        issues.update(grounding_issues)

        return parsed, issues

    # ------------------------------------------------------------------
    # Evidence grounding validation
    # ------------------------------------------------------------------

    def _validate_evidence(
        self,
        internal_map: _InternalResearchMap,
        evidence_catalogue: list[_EvidenceSpan],
    ) -> set[str]:
        """Validate all model-returned references against the catalogue.

        Returns a set of issue codes; an empty set means all evidence is valid.
        """
        issues: set[str] = set()

        evidence_lookup: dict[str, _EvidenceSpan] = {
            span.evidence_id: span for span in evidence_catalogue
        }

        all_grounded: list[
            tuple[str, list[_InternalEvidenceReference], str]
        ] = [
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

        for _label, evidence_list, _owner_text in all_grounded:
            seen_evidence_ids: set[str] = set()

            for evidence in evidence_list:
                if evidence.evidence_id not in evidence_lookup:
                    issues.add(_IssueCode.UNKNOWN_EVIDENCE_ID)
                    continue

                if evidence.evidence_id in seen_evidence_ids:
                    issues.add(_IssueCode.DUPLICATE_EVIDENCE)
                else:
                    seen_evidence_ids.add(evidence.evidence_id)

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
        evidence_catalogue: list[_EvidenceSpan],
    ) -> ResearchMap:
        """Convert an internal draft to the public :class:`ResearchMap`."""
        evidence_lookup = {
            span.evidence_id: span for span in evidence_catalogue
        }
        return ResearchMap(
            paper_id=paper_id,
            research_question=internal.research_question.statement,
            findings=[
                Finding(
                    statement=f.statement,
                    evidence=[
                        Evidence(
                            chunk_id=evidence_lookup[e.evidence_id].chunk_id,
                            page=evidence_lookup[e.evidence_id].page,
                            excerpt=evidence_lookup[e.evidence_id].text,
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
