"""Deterministic, extractive ResearchMap fallback.

This module deliberately has no provider, network, filesystem, environment,
randomness, or clock dependencies. Findings are complete normalized source
sentences selected by fixed lexical rules.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.paper import Chunk, ExtractionResult
from app.models.research_map import Evidence, Finding, ResearchMap

_RESEARCH_QUESTION = "What findings are explicitly reported in the uploaded document?"
_FALLBACK_LIMITATION = (
    "This deterministic extractive fallback presents selected source sentences "
    "without model-generated interpretation."
)

_FINDING_CUES = (
    "associated with",
    "association between",
    "more likely",
    "less likely",
    "higher",
    "lower",
    "increased",
    "decreased",
    "relationship between",
    "results indicate",
    "results showed",
    "findings indicate",
    "was observed",
    "were observed",
    "difference between",
    "odds of",
    "compared with",
    "compared to",
)
_STRONG_CUES = ("associated with", "more likely", "less likely")
_LIMITATION_CUES = (
    "limitation",
    "limitations",
    "cross-sectional",
    "self-report",
    "self-reported",
    "cannot establish",
    "cannot determine",
    "may not generalise",
    "may not generalize",
    "residual confounding",
    "selection bias",
)
_CAUSAL_CUES = (
    "caused",
    "causes",
    "leads to",
    "resulted in",
    "proves that",
    "responsible for",
)
_CAUSAL_DESIGN_CUES = (
    "randomized",
    "randomised",
    "randomized controlled",
    "randomised controlled",
    "causal study",
    "causal design",
)
_METHOD_SECTION_RE = re.compile(
    r"\b(?:methods?|materials and methods|methodology|procedures?|references?|"
    r"bibliography|table of contents|acknowledg(?:e)?ments?)\b",
    re.IGNORECASE,
)
_NAVIGATION_RE = re.compile(
    r"\b(?:table of contents|supplementary material|click here|download|"
    r"previous page|next page)\b",
    re.IGNORECASE,
)
_CAPTION_RE = re.compile(r"^(?:figure|fig\.?|table|box)\s+\w+", re.IGNORECASE)
_COPYRIGHT_RE = re.compile(
    r"(?:©|\bcopyright\b|\ball rights reserved\b|\blicen[cs]ed under\b)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^(?:[-*•▪◦‣]|\(?[a-z0-9]{1,3}[.)]\s)", re.IGNORECASE)
_TRUNCATED_START_RE = re.compile(
    r"^(?:\.{2,}|…|(?:and|or|but|because|which|that|whereas)\b)",
    re.IGNORECASE,
)
_ALPHABETIC_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SUBSTANTIVE_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "these",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)
_DIVERSITY_THRESHOLD = 0.75
_CLOSING_CHARACTERS = "'\"’”)]}"
_OPENING_CHARACTERS = "'\"‘“([{"
_EXPLICIT_HEADINGS = frozenset(
    {
        "abstract",
        "background",
        "conclusion",
        "conclusions",
        "discussion",
        "findings",
        "introduction",
        "limitations",
        "methodology",
        "methods",
        "results",
    }
)
_ABBREVIATIONS = frozenset(
    {
        "u.s.",
        "u.k.",
        "e.g.",
        "i.e.",
        "dr.",
        "mr.",
        "mrs.",
        "ms.",
        "prof.",
        "fig.",
        "no.",
        "vs.",
    }
)
_ALWAYS_NONTERMINAL_ABBREVIATIONS = frozenset(
    {"e.g.", "i.e.", "dr.", "mr.", "mrs.", "ms.", "prof.", "fig.", "no."}
)
_UPPERCASE_CONTINUATION_ABBREVIATIONS = frozenset({"u.s.", "u.k.", "vs."})
_PERIOD_PROTECTED = "protected"
_PERIOD_TERMINAL = "terminal"
_PERIOD_AMBIGUOUS = "ambiguous"
_METHOD_ONLY_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwe (?:used|fitted|fit|trained|evaluated|measured|assessed)\b",
        r"\bdata were collected\b",
        r"\bparticipants were recruited\b",
        r"\b(?:was|were) analy[sz]ed using\b",
        r"\busing cross[- ]validation\b",
        r"\bthe (?:(?:linear|logistic) )?model was compared with\b",
        r"\bmodels were compared using\b",
        r"\b(?:logistic|linear) regression was used\b",
        r"\brandom effects model was fitted\b",
        r"\b(?:questionnaire|survey) was administered\b",
    )
)
_PROCEDURAL_ACTION_RE = re.compile(
    r"\b(?:was|were) (?:used|fitted|fit|trained|evaluated|measured|assessed|"
    r"administered|collected)\b",
    re.IGNORECASE,
)
_PASSIVE_PROCEDURE_RE = re.compile(
    r"\b(?:was|were)\s+"
    r"(?:measured|assessed|evaluated|fitted|fit|trained|collected|recorded)\s+"
    r"(?:using|with|by)\b",
    re.IGNORECASE,
)
_METHOD_OBJECT_RE = re.compile(
    r"\b(?:models?|regressions?|algorithms?|classifiers?|cross[- ]validation|"
    r"questionnaires?|surveys?|protocols?|recruitment|measurements?|"
    r"data collection)\b",
    re.IGNORECASE,
)
_WRAPPED_LINE_END_RE = re.compile(
    r"\b(?:associated with|more likely|less likely|compared with|compared to|"
    r"relationship between|difference between|using|with|by|to|of|and|or|between)\s*$",
    re.IGNORECASE,
)


class ExtractiveFallbackError(RuntimeError):
    """The source does not contain three safe, distinct extractive findings."""


@dataclass(frozen=True)
class _Candidate:
    sentence: str
    chunk: Chunk
    chunk_index: int
    sentence_index: int
    score: int


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(
        rf"(?<!\w){re.escape(phrase)}(?!\w)",
        text,
        flags=re.IGNORECASE,
    ) is not None


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _is_probable_wrapped_body_line(line: str) -> bool:
    """Keep title-case lines that contain sentence or continuation evidence."""
    if _contains_any(line, _FINDING_CUES):
        return True
    if _PASSIVE_PROCEDURE_RE.search(line) or _PROCEDURAL_ACTION_RE.search(line):
        return True
    if any(pattern.search(line) for pattern in _METHOD_ONLY_PATTERNS):
        return True
    return _WRAPPED_LINE_END_RE.search(line) is not None


def _is_heading_line(line: str) -> bool:
    """Conservatively identify a standalone heading before lines are joined."""
    heading_key = line.rstrip(":").strip().casefold()
    if heading_key in _EXPLICIT_HEADINGS:
        return True
    if line.rstrip(_CLOSING_CHARACTERS).endswith((".", "?", "!")):
        return False
    words = _ALPHABETIC_TOKEN_RE.findall(line)
    if not words or len(words) > 6 or len(line) > 80:
        return False
    if any(character.isalpha() for character in line) and line == line.upper():
        return True
    if _is_probable_wrapped_body_line(line):
        return False
    connector_words = {"and", "for", "in", "of", "on", "the", "to", "with"}
    substantive = [word for word in words if word.casefold() not in connector_words]
    return bool(substantive) and all(word[:1].isupper() for word in substantive)


def _body_blocks(text: str) -> list[str]:
    """Normalize wrapped body lines without joining across headings/paragraphs."""
    normalized = unicodedata.normalize("NFKC", text)
    blocks: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        if current_lines:
            blocks.append(" ".join(current_lines))
            current_lines.clear()

    for raw_line in normalized.splitlines() or [normalized]:
        line = " ".join(raw_line.split())
        if not line or _is_heading_line(line):
            flush()
            continue
        current_lines.append(line)
    flush()
    return blocks


def _is_clear_uppercase_abbreviation_continuation(candidate: str, token: str) -> bool:
    """Recognize only narrow prefixes that cannot stand as source sentences."""
    normalized = _normalize(candidate).lstrip(_OPENING_CHARACTERS + " ").casefold()
    if token in {"u.s.", "u.k."}:
        return normalized in {token, f"the {token}"}
    if token == "vs.":
        words = _ALPHABETIC_TOKEN_RE.findall(normalized)
        return len(words) == 2 and words[-1] == "vs"
    return False


def _classify_period(text: str, index: int, sentence_start: int) -> str:
    """Classify a period as protected, terminal, or unsafe to disambiguate."""
    previous = text[index - 1] if index > 0 else ""
    following = text[index + 1] if index + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return _PERIOD_PROTECTED
    if previous.isalpha() and following.isalpha():
        return _PERIOD_PROTECTED

    token_start = index
    while token_start > 0 and (
        text[token_start - 1].isalpha() or text[token_start - 1] == "."
    ):
        token_start -= 1
    token = text[token_start : index + 1].casefold()
    is_et_al = re.search(r"\bet\s+al\.$", text[: index + 1], re.IGNORECASE)
    if token in _ALWAYS_NONTERMINAL_ABBREVIATIONS:
        return _PERIOD_PROTECTED
    if token in _ABBREVIATIONS or is_et_al:
        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if token in _UPPERCASE_CONTINUATION_ABBREVIATIONS:
            # These abbreviations commonly modify an uppercase proper noun
            # (for example, "The U.S. Department" or "Treatment vs. Control").
            # Outside narrow structurally incomplete prefixes, an uppercase
            # next token is inherently ambiguous without external linguistic
            # inference. Fail closed rather than use finding-eligibility rules
            # to guess whether the preceding text is a sentence.
            if next_index >= len(text) or text[next_index] in _CLOSING_CHARACTERS:
                return _PERIOD_TERMINAL
            candidate = text[sentence_start : index + 1].strip()
            if text[next_index].isupper() and not _is_clear_uppercase_abbreviation_continuation(
                candidate,
                token,
            ):
                return _PERIOD_AMBIGUOUS
            return _PERIOD_PROTECTED
        # A contextual abbreviation followed by lowercase continuation text is
        # internal. At end-of-block or before a new uppercase sentence it can
        # still serve as genuine terminal punctuation.
        if next_index < len(text) and not text[next_index].isupper():
            return _PERIOD_PROTECTED
        return _PERIOD_TERMINAL

    # A single-letter personal initial is protected only when followed by an
    # uppercase name/initial, so ordinary sentence-final periods still split.
    if len(token) == 2 and token[0].isalpha():
        next_index = index + 1
        while next_index < len(text) and text[next_index].isspace():
            next_index += 1
        if next_index < len(text) and text[next_index].isupper():
            return _PERIOD_PROTECTED
    return _PERIOD_TERMINAL


def _scan_block(block: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    index = 0
    discard_current_span = False
    while index < len(block):
        character = block[index]
        if character not in ".?!":
            index += 1
            continue
        if character == ".":
            period_kind = _classify_period(block, index, start)
            if period_kind == _PERIOD_PROTECTED:
                index += 1
                continue
            if period_kind == _PERIOD_AMBIGUOUS:
                discard_current_span = True
                index += 1
                continue

        boundary_end = index + 1
        while boundary_end < len(block) and block[boundary_end] in _CLOSING_CHARACTERS:
            boundary_end += 1
        if boundary_end < len(block) and not block[boundary_end].isspace():
            index += 1
            continue

        sentence = block[start:boundary_end].strip()
        if sentence and not discard_current_span:
            sentences.append(sentence)
        start = boundary_end
        discard_current_span = False
        while start < len(block) and block[start].isspace():
            start += 1
        index = start
    return sentences


def _split_sentences(text: str) -> list[str]:
    """Return deterministic normalized source sentences in stable order."""
    return [sentence for block in _body_blocks(text) for sentence in _scan_block(block)]


def _is_complete_source_sentence(sentence: str) -> bool:
    terminal_core = sentence.rstrip(_CLOSING_CHARACTERS)
    if not terminal_core or terminal_core[-1] not in ".?!":
        return False
    if len(sentence) > 300:
        return False
    if len(_ALPHABETIC_TOKEN_RE.findall(sentence)) < 6:
        return False
    if terminal_core.endswith(("...", "…")):
        return False
    if _TRUNCATED_START_RE.search(sentence):
        return False
    if _BULLET_RE.search(sentence):
        return False
    if _CAPTION_RE.search(sentence):
        return False
    if _COPYRIGHT_RE.search(sentence):
        return False
    if _NAVIGATION_RE.search(sentence):
        return False
    visible_start = sentence.lstrip(_OPENING_CHARACTERS + " ")
    if visible_start and visible_start[0].isalpha() and visible_start[0].islower():
        return False
    words = _ALPHABETIC_TOKEN_RE.findall(sentence)
    if words and sum(word[:1].isupper() for word in words) / len(words) > 0.8:
        return False
    return True


def _is_method_only(sentence: str) -> bool:
    if _PASSIVE_PROCEDURE_RE.search(sentence):
        return True
    if any(pattern.search(sentence) for pattern in _METHOD_ONLY_PATTERNS):
        return True
    return bool(
        _PROCEDURAL_ACTION_RE.search(sentence) and _METHOD_OBJECT_RE.search(sentence)
    )


def _is_finding_candidate(sentence: str, chunk: Chunk) -> bool:
    if not _is_complete_source_sentence(sentence):
        return False
    if chunk.section and _METHOD_SECTION_RE.search(_normalize(chunk.section)):
        return False
    if _is_method_only(sentence):
        return False
    if not _contains_any(sentence, _FINDING_CUES):
        return False
    if _contains_any(sentence, _CAUSAL_CUES) and not _contains_any(
        sentence, _CAUSAL_DESIGN_CUES
    ):
        return False
    return True


def _score(sentence: str, section: str | None) -> int:
    score = 0
    normalized_section = _normalize(section or "")
    if re.search(r"\b(?:results?|findings?)\b", normalized_section, re.IGNORECASE):
        score += 40
    elif re.search(
        r"\b(?:conclusions?|abstract)\b", normalized_section, re.IGNORECASE
    ):
        score += 20
    if _contains_any(sentence, _STRONG_CUES):
        score += 10
    if 50 <= len(sentence) <= 240:
        score += 5
    return score


def _substantive_tokens(sentence: str) -> frozenset[str]:
    return frozenset(
        token
        for token in (
            raw.casefold() for raw in _SUBSTANTIVE_TOKEN_RE.findall(sentence)
        )
        if token not in _STOPWORDS
    )


def _jaccard(left: str, right: str) -> float:
    left_tokens = _substantive_tokens(left)
    right_tokens = _substantive_tokens(right)
    union = left_tokens | right_tokens
    if not union:
        return 1.0
    return len(left_tokens & right_tokens) / len(union)


class ExtractiveResearchMapService:
    """Build a ResearchMap solely from exact sentences in extracted chunks."""

    def generate(self, extraction: ExtractionResult) -> ResearchMap:
        candidates: list[_Candidate] = []
        limitation: str | None = None

        for chunk_index, chunk in enumerate(extraction.chunks):
            normalized_chunk = _normalize(chunk.text)
            for sentence_index, sentence in enumerate(_split_sentences(chunk.text)):
                # This invariant makes the extractive guarantee explicit.
                if sentence not in normalized_chunk:
                    continue
                if (
                    limitation is None
                    and _is_complete_source_sentence(sentence)
                    and _contains_any(sentence, _LIMITATION_CUES)
                ):
                    limitation = sentence
                if _is_finding_candidate(sentence, chunk):
                    candidates.append(
                        _Candidate(
                            sentence=sentence,
                            chunk=chunk,
                            chunk_index=chunk_index,
                            sentence_index=sentence_index,
                            score=_score(sentence, chunk.section),
                        )
                    )

        candidates.sort(
            key=lambda candidate: (
                -candidate.score,
                candidate.chunk_index,
                candidate.sentence_index,
            )
        )

        selected: list[_Candidate] = []
        selected_chunk_ids: set[str] = set()
        selected_sentences: set[str] = set()
        for candidate in candidates:
            if candidate.chunk.chunk_id in selected_chunk_ids:
                continue
            if candidate.sentence in selected_sentences:
                continue
            if any(
                _jaccard(candidate.sentence, prior.sentence) > _DIVERSITY_THRESHOLD
                for prior in selected
            ):
                continue
            selected.append(candidate)
            selected_chunk_ids.add(candidate.chunk.chunk_id)
            selected_sentences.add(candidate.sentence)
            if len(selected) == 3:
                break

        if len(selected) != 3:
            raise ExtractiveFallbackError(
                "Could not produce three eligible, distinct findings."
            )

        return ResearchMap(
            paper_id=extraction.paper_id,
            research_question=_RESEARCH_QUESTION,
            findings=[
                Finding(
                    statement=candidate.sentence,
                    evidence=[
                        Evidence(
                            chunk_id=candidate.chunk.chunk_id,
                            page=candidate.chunk.page,
                            excerpt=candidate.sentence,
                        )
                    ],
                    confidence="partial",
                )
                for candidate in selected
            ],
            limitations=[limitation or _FALLBACK_LIMITATION],
        )
