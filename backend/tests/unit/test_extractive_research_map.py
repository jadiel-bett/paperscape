"""Unit tests for the deterministic extractive ResearchMap fallback."""
from __future__ import annotations

import ast
import inspect

import pytest

from app.models.paper import Chunk, ExtractionResult
from app.services.extractive_research_map import (
    ExtractiveFallbackError,
    ExtractiveResearchMapService,
    _is_method_only,
    _split_sentences,
)

_FIXED_LIMITATION = (
    "This deterministic extractive fallback presents selected source sentences "
    "without model-generated interpretation."
)


def _extraction(*chunks: Chunk) -> ExtractionResult:
    return ExtractionResult(
        paper_id="paper-extractive",
        filename="paper.pdf",
        chunks=list(chunks),
    )


def _chunk(
    index: int,
    text: str,
    *,
    section: str | None = "Results",
    page: int | None = None,
) -> Chunk:
    resolved_page = page or index
    return Chunk(
        chunk_id=f"paper-extractive-p{resolved_page}-{index}",
        page=resolved_page,
        section=section,
        text=text,
    )


def _eligible_extraction() -> ExtractionResult:
    return _extraction(
        _chunk(
            1,
            "Participants with the intervention were more likely to complete follow-up.",
        ),
        _chunk(
            2,
            "Higher baseline scores were associated with lower attrition at six months.",
        ),
        _chunk(
            3,
            "A difference between treatment groups was observed after twelve weeks.",
        ),
        _chunk(
            4,
            "This cross-sectional design cannot establish the direction of association.",
            section="Limitations",
        ),
    )


def test_identical_input_is_deterministic_and_returns_exactly_three_findings() -> None:
    service = ExtractiveResearchMapService()
    extraction = _eligible_extraction()

    first = service.generate(extraction)
    second = service.generate(extraction)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.findings) == 3


def test_findings_and_evidence_are_exact_normalized_source_sentences() -> None:
    extraction = _eligible_extraction()
    result = ExtractiveResearchMapService().generate(extraction)
    source_by_id = {
        chunk.chunk_id: (" ".join(chunk.text.split()), chunk.page)
        for chunk in extraction.chunks
    }

    assert len({finding.evidence[0].chunk_id for finding in result.findings}) == 3
    for finding in result.findings:
        assert finding.confidence == "partial"
        assert len(finding.evidence) == 1
        evidence = finding.evidence[0]
        normalized_source, source_page = source_by_id[evidence.chunk_id]
        assert finding.statement in normalized_source
        assert evidence.excerpt == finding.statement
        assert evidence.page == source_page


def test_result_section_outranks_background_and_source_order_breaks_ties() -> None:
    extraction = _extraction(
        _chunk(
            1,
            "Adults with flexible schedules were more likely to attend every visit.",
            section="Background",
        ),
        _chunk(
            2,
            "Higher engagement was observed among participants receiving reminders.",
        ),
        _chunk(
            3,
            "Lower attrition was observed among participants receiving transport.",
        ),
        _chunk(
            4,
            "Increased completion was observed among participants receiving childcare.",
        ),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert [finding.evidence[0].chunk_id for finding in result.findings] == [
        extraction.chunks[1].chunk_id,
        extraction.chunks[2].chunk_id,
        extraction.chunks[3].chunk_id,
    ]


def test_near_duplicates_are_not_selected_together() -> None:
    extraction = _extraction(
        _chunk(
            1,
            "Higher participation was observed among adults receiving weekly text reminders.",
        ),
        _chunk(
            2,
            "Higher participation was observed among adults receiving weekly email reminders.",
        ),
        _chunk(
            3,
            "Lower attrition was associated with access to reliable transport services.",
        ),
        _chunk(
            4,
            "A difference between groups was observed during the final assessment visit.",
        ),
    )

    result = ExtractiveResearchMapService().generate(extraction)
    statements = [finding.statement for finding in result.findings]

    assert extraction.chunks[0].text in statements
    assert extraction.chunks[1].text not in statements


def test_numeric_symbols_percentages_comparators_and_ranges_are_preserved() -> None:
    source_sentences = [
        "Higher response was observed for 25.5% of participants with scores >=10.",
        "Lower risk was associated with values from -3 to +7 points.",
        "The odds of completion increased by 2.4% compared with 1.1% at baseline.",
    ]
    result = ExtractiveResearchMapService().generate(
        _extraction(*(_chunk(index, text) for index, text in enumerate(source_sentences, 1)))
    )

    assert set(finding.statement for finding in result.findings) == set(source_sentences)


def test_split_chunks_are_not_joined_and_truncated_fragments_are_rejected() -> None:
    extraction = _extraction(
        _chunk(1, "Higher participation was associated with"),
        _chunk(2, "lower attrition across all follow-up visits."),
        _chunk(3, "... higher retention was observed across later visits."),
        _chunk(
            4,
            "Higher attendance was observed among participants offered transport.",
        ),
        _chunk(
            5,
            "Lower attrition was associated with receiving weekly appointment reminders.",
        ),
        _chunk(
            6,
            "A difference between groups was observed during the final assessment.",
        ),
    )

    result = ExtractiveResearchMapService().generate(extraction)
    statements = [finding.statement for finding in result.findings]

    assert all("associated with lower attrition" not in statement for statement in statements)
    assert all(not statement.startswith("...") for statement in statements)


def test_headings_copyright_and_method_only_sentences_are_rejected() -> None:
    extraction = _extraction(
        _chunk(1, "RESULTS SHOWED HIGHER SCORES ACROSS ALL STUDY GROUPS."),
        _chunk(
            2,
            "Copyright 2026; higher use was observed across registered participants.",
        ),
        _chunk(
            3,
            "Groups were compared with standard tests and lower thresholds were recorded.",
            section="Methods",
        ),
        _chunk(
            4,
            "Higher attendance was observed among participants offered transport.",
        ),
        _chunk(
            5,
            "Lower attrition was associated with receiving weekly appointment reminders.",
        ),
        _chunk(
            6,
            "A difference between groups was observed during the final assessment.",
        ),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert {finding.evidence[0].chunk_id for finding in result.findings} == {
        extraction.chunks[3].chunk_id,
        extraction.chunks[4].chunk_id,
        extraction.chunks[5].chunk_id,
    }


def test_causal_wording_is_rejected_conservatively() -> None:
    causal = "The reminder caused higher attendance during all scheduled visits."
    extraction = _extraction(
        _chunk(1, causal),
        _chunk(
            2,
            "Higher attendance was observed among participants offered transport.",
        ),
        _chunk(
            3,
            "Lower attrition was associated with receiving weekly appointment reminders.",
        ),
        _chunk(
            4,
            "A difference between groups was observed during the final assessment.",
        ),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert causal not in [finding.statement for finding in result.findings]


def test_exact_limitation_sentence_is_selected_in_source_order() -> None:
    extraction = _eligible_extraction()

    result = ExtractiveResearchMapService().generate(extraction)

    assert result.limitations == [
        "This cross-sectional design cannot establish the direction of association."
    ]


def test_fixed_transparent_limitation_is_used_when_source_has_none() -> None:
    result = ExtractiveResearchMapService().generate(
        _extraction(*_eligible_extraction().chunks[:3])
    )

    assert result.limitations == [_FIXED_LIMITATION]


def test_fewer_than_three_eligible_findings_raises() -> None:
    extraction = _extraction(
        _chunk(1, "Higher attendance was observed among participants offered transport."),
        _chunk(2, "This sentence reports descriptive background information only."),
    )

    with pytest.raises(ExtractiveFallbackError):
        ExtractiveResearchMapService().generate(extraction)


def test_service_has_no_network_provider_environment_or_filesystem_dependency() -> None:
    source = inspect.getsource(
        __import__(
            "app.services.extractive_research_map",
            fromlist=["ExtractiveResearchMapService"],
        )
    )
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert imported_roots <= {
        "__future__",
        "re",
        "unicodedata",
        "dataclasses",
        "app",
    }
    assert all(
        token not in source
        for token in ("os.environ", "getenv(", "open(", "Path(", "datetime.now")
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "Participants in the U.S. were more likely to report poor sleep.",
            ["Participants in the U.S. were more likely to report poor sleep."],
        ),
        (
            "The U.S. Department reported participants were more likely to improve.",
            [
                "The U.S. Department reported participants were more likely "
                "to improve."
            ],
        ),
        (
            "The U.K. Biobank found participants were less likely to withdraw.",
            ["The U.K. Biobank found participants were less likely to withdraw."],
        ),
        (
            "Treatment vs. Control participants were more likely to improve.",
            ["Treatment vs. Control participants were more likely to improve."],
        ),
        (
            "Participants were recruited throughout the U.S.",
            ["Participants were recruited throughout the U.S."],
        ),
        (
            '"Participants were recruited throughout the U.S."',
            ['"Participants were recruited throughout the U.S."'],
        ),
        (
            "Participants lived throughout the northeastern U.S. Results showed "
            "higher attendance among all participants.",
            [],
        ),
        (
            "Participants lived throughout the rural U.K. Findings indicated "
            "lower attrition across follow-up visits.",
            [],
        ),
        (
            "Participants lived throughout the northeastern U.S. Researchers "
            "reported higher attendance among all participants.",
            [],
        ),
        (
            "Participants lived throughout the rural U.K. Participants reported "
            "lower attrition across follow-up visits.",
            [],
        ),
        (
            "Participants lived throughout the northeastern U.S. Alice reported "
            "that participants were more likely to attend.",
            [],
        ),
        (
            "They surveyed the U.S. Researchers reported higher attendance among "
            "all participants.",
            [],
        ),
        (
            "They surveyed the U.K. Participants reported lower attrition across "
            "follow-up visits.",
            [],
        ),
        (
            "They surveyed the U.S. Alice reported that participants were more "
            "likely to attend.",
            [],
        ),
        (
            "Participants lived throughout the northeastern U.S. Researchers "
            "reported higher attendance among all participants. Lower attrition "
            "was associated with reminder access.",
            ["Lower attrition was associated with reminder access."],
        ),
        (
            "Higher Exposure Was Associated With\n"
            "Poorer Sleep among participants in the cohort.",
            [
                "Higher Exposure Was Associated With Poorer Sleep among "
                "participants in the cohort."
            ],
        ),
        (
            "Participants Were More Likely To\n"
            "Report difficulty returning to sleep.",
            [
                "Participants Were More Likely To Report difficulty returning "
                "to sleep."
            ],
        ),
        (
            "Exposure Was Compared With\n"
            "The reference group in the adjusted analysis.",
            [
                "Exposure Was Compared With The reference group in the adjusted "
                "analysis."
            ],
        ),
        (
            "Participant Characteristics\n"
            "Participants were more likely to report poor sleep.",
            ["Participants were more likely to report poor sleep."],
        ),
        (
            "Results\nParticipants were more likely to report poor sleep.",
            ["Participants were more likely to report poor sleep."],
        ),
        (
            "STUDY FINDINGS\nParticipants were more likely to report poor sleep.",
            ["Participants were more likely to report poor sleep."],
        ),
        (
            "Higher Blood Pressure Was Measured Using\nAn automated cuff.",
            ["Higher Blood Pressure Was Measured Using An automated cuff."],
        ),
        (
            "A. Smith reported that participants were more likely to improve.",
            ["A. Smith reported that participants were more likely to improve."],
        ),
        (
            "J. K. Smith found that participants were less likely to withdraw.",
            ["J. K. Smith found that participants were less likely to withdraw."],
        ),
        (
            "Results\nParticipants were more likely to report late sleep onset.",
            ["Participants were more likely to report late sleep onset."],
        ),
        (
            '\"The association was significant.\"',
            ['\"The association was significant.\"'],
        ),
        (
            "(The association was significant.)",
            ["(The association was significant.)"],
        ),
        (
            "Higher response was observed for 31.6% with an interval of 1.83 to 2.50.",
            [
                "Higher response was observed for 31.6% with an interval of "
                "1.83 to 2.50."
            ],
        ),
        (
            "The result was significant. Another result followed.",
            ["The result was significant.", "Another result followed."],
        ),
        (
            "RESULTS\nFindings\nHigher attendance was observed across all visits.",
            ["Higher attendance was observed across all visits."],
        ),
    ],
)
def test_sentence_scanner_handles_scientific_boundaries(
    source: str,
    expected: list[str],
) -> None:
    assert _split_sentences(source) == expected


def test_abbreviation_never_creates_an_eligible_trailing_fragment() -> None:
    source = "Participants in the U.S. were more likely to report poor sleep."
    extraction = _extraction(
        _chunk(1, source),
        _chunk(2, "Lower attrition was associated with reminder access."),
        _chunk(3, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert source in [finding.statement for finding in result.findings]
    assert all(
        not finding.statement.startswith("were more likely")
        for finding in result.findings
    )


def test_uppercase_abbreviation_continuations_remain_complete_findings() -> None:
    sources = {
        "The U.S. Department reported participants were more likely to improve.",
        "The U.K. Biobank found participants were less likely to withdraw.",
        "Treatment vs. Control participants were more likely to improve.",
    }
    extraction = _extraction(
        *(_chunk(index, source) for index, source in enumerate(sorted(sources), start=1))
    )

    result = ExtractiveResearchMapService().generate(extraction)

    statements = {finding.statement for finding in result.findings}
    assert statements == sources
    assert all(
        not statement.startswith(("Department ", "Biobank ", "Control "))
        for statement in statements
    )


def test_ambiguous_terminal_abbreviation_span_is_rejected() -> None:
    source = (
        "They surveyed the U.S. Researchers reported higher attendance among all "
        "participants."
    )
    extraction = _extraction(
        _chunk(1, source),
        _chunk(2, "Lower attrition was associated with reminder access."),
        _chunk(3, "A difference between groups was observed after follow-up."),
        _chunk(4, "Higher retention was observed among transport recipients."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    statements = {finding.statement for finding in result.findings}
    assert source not in statements
    assert all("Researchers reported" not in statement for statement in statements)


def test_wrapped_result_remains_exact_normalized_source_text() -> None:
    source = (
        "Higher Exposure Was Associated With\n"
        "Poorer Sleep among participants in the cohort."
    )
    joined = (
        "Higher Exposure Was Associated With Poorer Sleep among participants "
        "in the cohort."
    )
    extraction = _extraction(
        _chunk(1, source, section=None),
        _chunk(2, "Lower attrition was associated with reminder access."),
        _chunk(3, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    finding = next(item for item in result.findings if item.statement == joined)
    assert finding.evidence[0].excerpt == joined
    assert joined in " ".join(source.split())


@pytest.mark.parametrize(
    "procedure",
    [
        "Higher blood pressure was measured using an automated cuff.",
        "Higher symptom severity was assessed using clinical interviews.",
        "Model performance was evaluated with repeated cross-validation.",
        "The classifier was trained using labelled examples.",
        "The regression model was fitted by maximum likelihood.",
        "Measurements were collected using a digital monitor.",
    ],
)
def test_high_confidence_passive_procedures_are_method_only(procedure: str) -> None:
    assert _is_method_only(procedure)


def test_passive_procedures_with_weak_finding_cues_are_rejected_without_section() -> None:
    measured = "Higher blood pressure was measured using an automated cuff."
    assessed = "Higher symptom severity was assessed using clinical interviews."
    extraction = _extraction(
        _chunk(1, measured, section=None),
        _chunk(2, assessed, section=None),
        _chunk(3, "Higher attendance was observed among transport recipients."),
        _chunk(4, "Lower attrition was associated with reminder access."),
        _chunk(5, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    statements = {finding.statement for finding in result.findings}
    assert measured not in statements
    assert assessed not in statements


@pytest.mark.parametrize(
    "result_sentence",
    [
        "Higher blood pressure was associated with poorer sleep.",
        "Higher symptom severity was observed among exposed participants.",
        "In the adjusted model, higher exposure was associated with poorer sleep.",
        "The analysis showed that participants were more likely to report insomnia.",
    ],
)
def test_legitimate_results_near_procedural_vocabulary_remain_eligible(
    result_sentence: str,
) -> None:
    extraction = _extraction(
        _chunk(1, result_sentence, section=None),
        _chunk(2, "Lower attrition was associated with reminder access."),
        _chunk(3, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert result_sentence in {finding.statement for finding in result.findings}


def test_wrapped_passive_method_is_joined_then_rejected() -> None:
    source = "Higher Blood Pressure Was Measured Using\nAn automated cuff."
    joined = "Higher Blood Pressure Was Measured Using An automated cuff."
    extraction = _extraction(
        _chunk(1, source, section=None),
        _chunk(2, "Higher attendance was observed among transport recipients."),
        _chunk(3, "Lower attrition was associated with reminder access."),
        _chunk(4, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert joined not in {finding.statement for finding in result.findings}


def test_method_only_sentence_without_section_metadata_is_rejected() -> None:
    method = "The linear model was compared with a logistic model using cross-validation."
    extraction = _extraction(
        _chunk(1, method, section=None),
        _chunk(2, "Higher attendance was observed among transport recipients."),
        _chunk(3, "Lower attrition was associated with reminder access."),
        _chunk(4, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert method not in [finding.statement for finding in result.findings]


def test_unlabelled_pymupdf_style_procedure_is_rejected() -> None:
    method = (
        "We used logistic regression, which was compared with a linear model "
        "using cross-validation."
    )
    extraction = _extraction(
        _chunk(1, method, section=None),
        _chunk(2, "Higher attendance was observed among transport recipients."),
        _chunk(3, "Lower attrition was associated with reminder access."),
        _chunk(4, "A difference between groups was observed after follow-up."),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert method not in [finding.statement for finding in result.findings]


def test_result_sentences_mentioning_model_and_analysis_remain_eligible() -> None:
    adjusted = "In the adjusted model, higher exposure was associated with poorer sleep."
    analysis = "The analysis showed that participants were more likely to report insomnia."
    third = "A difference between groups was observed after follow-up."
    extraction = _extraction(
        _chunk(1, adjusted, section=None),
        _chunk(2, analysis, section=None),
        _chunk(3, third, section=None),
    )

    result = ExtractiveResearchMapService().generate(extraction)

    assert {finding.statement for finding in result.findings} == {
        adjusted,
        analysis,
        third,
    }


def test_method_filtering_can_leave_too_few_findings() -> None:
    extraction = _extraction(
        _chunk(
            1,
            "The linear model was compared with a logistic model using cross-validation.",
            section=None,
        ),
        _chunk(2, "Higher attendance was observed among transport recipients."),
        _chunk(3, "Lower attrition was associated with reminder access."),
    )

    with pytest.raises(ExtractiveFallbackError):
        ExtractiveResearchMapService().generate(extraction)


def test_passive_method_filtering_can_leave_too_few_findings() -> None:
    extraction = _extraction(
        _chunk(
            1,
            "Higher blood pressure was measured using an automated cuff.",
            section=None,
        ),
        _chunk(2, "Higher attendance was observed among transport recipients."),
        _chunk(3, "Lower attrition was associated with reminder access."),
    )

    with pytest.raises(ExtractiveFallbackError):
        ExtractiveResearchMapService().generate(extraction)
