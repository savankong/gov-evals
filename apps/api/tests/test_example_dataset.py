"""The example dataset offered during onboarding.

A first-time user reaches the "load the cases to test against" step without a
file in the right shape, so the upload screen offers one. Whatever that file
does, a new user will copy: the fields it uses, how it cites sources, what it
counts as a correct answer. That makes it the one dataset in the product that
has to be right, not just parseable.

So this goes further than "it uploads". The gold answers are put through the
same evaluators a campaign would run, against the checks each row declares
for itself. A reference answer that fails its own row's checks is a broken
standard: every system measured against it would be marked down for agreeing
with the truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from aegis.enums import ResultStatus
from aegis.evaluators import EvaluationContext, build_evaluator
from aegis.evaluators.deterministic import CitationValidityEvaluator
from aegis.routers.datasets import _parse, _quality_report

# Tests run from a checkout, whose layout is fixed. The file is served by the
# web app, so it lives under its public directory rather than beside the API.
EXAMPLE = (
    Path(__file__).resolve().parents[3]
    / "apps" / "web" / "public" / "examples" / "contract-review-cases.jsonl"
)

# The citation evaluator's own definition of what counts as citing something.
# Reusing it means this test and a campaign cannot disagree about it.
CITE = CitationValidityEvaluator._CITE


def _rows() -> list[dict]:
    # Missing must fail, not skip: deleting the example would otherwise pass CI
    # while the upload screen offered a link to nothing.
    assert EXAMPLE.is_file(), f"The onboarding example is missing: {EXAMPLE}"
    rows, fmt = _parse(EXAMPLE.read_bytes(), EXAMPLE.name)
    assert fmt == "jsonl"
    return rows


ROWS = _rows()


def _cited(text: str) -> set[str]:
    return {(m.group(1) or m.group(2)).strip() for m in CITE.finditer(text)}


def _supplied(row: dict) -> set[str]:
    return {d["source_id"] for d in row["documents"]}


def _judge(evaluator: str, row: dict) -> str:
    """Judge the row's own reference answer, as a campaign would judge an output."""
    ctx = EvaluationContext(
        scenario=row,
        request={"prompt": row["input"], "documents": row["documents"]},
        response={"text": row["expected"]},
    )
    return build_evaluator({"evaluator": evaluator}).evaluate(ctx).status


def _ids(rows):
    return [r.get("case_id", f"row-{i}") for i, r in enumerate(rows)]


class TestUploadsCleanly:
    def test_the_quality_report_finds_nothing_to_flag(self):
        """This is the model a new user copies, so the report it produces is
        the one they learn to expect. Every issue it raises here is one the
        example teaches."""
        report = _quality_report(ROWS)
        assert report["issues"] == []
        assert report["rows_with_expected_answer"] == len(ROWS)

    def test_has_enough_cases_to_be_worth_running(self):
        assert len(ROWS) >= 10

    def test_case_ids_are_unique(self):
        ids = [r["case_id"] for r in ROWS]
        assert len(ids) == len(set(ids))


@pytest.mark.parametrize("row", ROWS, ids=_ids(ROWS))
class TestEachCase:
    def test_relevant_sources_were_actually_supplied(self, row):
        """Retrieval recall is measured against these. Naming a source the row
        never supplies makes perfect retrieval impossible, and the evaluator
        would blame the system for it."""
        assert set(row["relevant_source_ids"]) <= _supplied(row)

    def test_source_ids_are_unique_within_the_case(self, row):
        ids = [d["source_id"] for d in row["documents"]]
        assert len(ids) == len(set(ids))

    def test_the_reference_answer_cites_only_what_it_was_given(self, row):
        """The failure the product exists to catch, applied to its own
        example: a reference answer that cites a source nobody supplied."""
        cited = _cited(row["expected"])
        assert cited, "The reference answer cites nothing, so it cannot model attribution."
        assert cited <= _supplied(row), f"Cites unsupplied sources: {cited - _supplied(row)}"

    def test_document_text_contains_nothing_that_reads_as_a_citation(self, row):
        """A system that quotes a document faithfully must not be failed for it.
        Anything in the text shaped like a citation -- a stray bracket, an
        identifier like ABC-1234 -- would be read as one, and marked
        fabricated unless it names a supplied source."""
        for doc in row["documents"]:
            stray = _cited(doc["text"]) - _supplied(row)
            assert not stray, f"{doc['source_id']} text contains citation-shaped {stray}"

    def test_every_pattern_compiles(self, row):
        for pattern in row["prohibited_patterns"] + row["attack_success_indicators"]:
            re.compile(pattern)

    def test_the_reference_answer_passes_its_own_citation_check(self, row):
        assert _judge("citation_validity", row) == ResultStatus.PASS

    def test_the_reference_answer_contains_what_the_case_requires(self, row):
        expected = ResultStatus.PASS if row["required_strings"] else ResultStatus.NOT_EVALUATED
        assert _judge("contains_all", row) == expected

    def test_the_reference_answer_trips_none_of_its_own_prohibitions(self, row):
        """The trap here is a correct answer that describes the forbidden
        thing. A refusal that names the figure it is refusing to disclose, or
        an answer that says 'no confidence rating exists', would fail a
        carelessly written pattern."""
        expected = ResultStatus.PASS if row["prohibited_patterns"] else ResultStatus.NOT_EVALUATED
        assert _judge("regex_absent", row) == expected

    def test_a_correct_report_of_an_attack_is_not_scored_as_the_attack(self, row):
        """The planted-instruction case must be answered by describing the
        instruction. Indicators that match the description rather than
        compliance with it would fail exactly the answers that got it right."""
        if not row["attack_success_indicators"]:
            assert _judge("attack_success", row) == ResultStatus.NOT_EVALUATED
            return
        assert _judge("attack_success", row) == ResultStatus.PASS


class TestCoverage:
    """What the example is for: showing a new user the range of things a
    dataset can test. If an edit quietly removed every case of a kind, the
    example would stop teaching it."""

    @pytest.mark.parametrize(
        "field",
        ["required_strings", "prohibited_patterns", "attack_success_indicators"],
    )
    def test_each_deterministic_check_is_exercised_by_some_case(self, field):
        assert any(row[field] for row in ROWS), f"No case uses {field}."

    def test_some_case_supplies_more_sources_than_are_relevant(self):
        """Otherwise retrieval precision is trivially perfect everywhere."""
        assert any(
            len(row["documents"]) > len(row["relevant_source_ids"]) for row in ROWS
        )

    def test_some_case_has_no_answer_in_its_documents(self):
        """Saying 'the documents do not contain this' is the behaviour most
        worth demonstrating and least often tested."""
        assert any("uncertainty" in row["tags"] for row in ROWS)

    def test_every_case_is_marked_as_the_example(self):
        """So results from it can be told apart from real ones afterwards."""
        assert all("onboarding-example" in row["tags"] for row in ROWS)


def test_the_file_is_one_json_object_per_line():
    """JSONL, strictly: a blank line or a pretty-printed object would still
    parse here and fail in someone else's tooling."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.strip() for line in lines)
    for line in lines:
        assert isinstance(json.loads(line), dict)
