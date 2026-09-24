"""Benchmark scoring, judge agreement and the benchmark report.

A benchmark publishes one kind of number: criteria met out of criteria judged.
These tests hold the lines that number depends on. A criterion nobody decided is
never counted as met. A calibration run that exists to measure the judge is never
counted as a score. A missing cost is reported as missing, not as free. And the
judge's agreement with experts is computed only from reviews that counted as
expert evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from aegis.benchmark import benchmark_data
from aegis.enums import ResultStatus
from aegis.evaluators import EvaluationContext, build_evaluator
from aegis.models import (
    Campaign,
    Evaluation,
    HumanReview,
    Result,
    Run,
    Scenario,
    System,
    SystemVersion,
)
from aegis.reports import benchmark_report

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

CRITERIA = [
    {"id": "c1", "text": "States the rule."},
    {"id": "c2", "text": "Names the deadline."},
    {"id": "c3", "text": "Recommends counsel."},
]


def _judge(verdicts: dict[str, str], calls: list | None = None):
    """A judge that answers from a fixed table, omitting ids not in it."""

    def judge(system_prompt, prompt, config):
        if calls is not None:
            calls.append(prompt)
        items = [
            {"id": cid, "verdict": v, "rationale": f"{cid} {v}"}
            for cid, v in verdicts.items()
            if f"[{cid}]" in prompt
        ]
        import json

        return {"text": json.dumps({"criteria": items}), "model": "judge-model-1"}

    return judge


def _ctx(judge=None, criteria=CRITERIA):
    return EvaluationContext(
        scenario={"criteria": criteria},
        request={"prompt": "Question?"},
        response={"text": "An answer."},
        judge=judge,
    )


class TestRubricCriteriaEvaluator:
    def test_all_criteria_met_is_a_pass(self):
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        j = evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "pass", "c3": "pass"})))
        assert j.status == ResultStatus.PASS
        assert j.score == 1.0
        assert j.evaluator_metadata["criteria_passed"] == 3

    def test_one_criterion_missed_is_a_fail_with_the_fraction(self):
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        j = evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "fail", "c3": "pass"})))
        assert j.status == ResultStatus.FAIL
        assert j.score == pytest.approx(2 / 3)

    def test_a_criterion_the_judge_skipped_is_never_counted_as_met(self):
        """The regression this evaluator must never have: everything the judge
        returned passed, one criterion came back with no verdict, and the answer
        is reported as meeting all its criteria."""
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        j = evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "pass"})))
        assert j.status == ResultStatus.NOT_EVALUATED
        assert j.status != ResultStatus.PASS
        rows = {r["id"]: r for r in j.evaluator_metadata["criteria"]}
        assert rows["c3"]["verdict"] == ResultStatus.NOT_EVALUATED
        assert j.evaluator_metadata["criteria_judged"] == 2
        # Pass rate is over judged criteria only.
        assert j.score == 1.0

    def test_an_unrecognised_verdict_is_not_evaluated(self):
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        j = evaluator.evaluate(_ctx(_judge({"c1": "mostly", "c2": "pass", "c3": "pass"})))
        rows = {r["id"]: r for r in j.evaluator_metadata["criteria"]}
        assert rows["c1"]["verdict"] == ResultStatus.NOT_EVALUATED
        assert j.status == ResultStatus.NOT_EVALUATED

    def test_no_judge_and_no_criteria_are_not_evaluated(self):
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        assert evaluator.evaluate(_ctx(None)).status == ResultStatus.NOT_EVALUATED
        no_criteria = evaluator.evaluate(_ctx(_judge({}), criteria=[]))
        assert no_criteria.status == ResultStatus.NOT_EVALUATED

    def test_per_criterion_mode_asks_once_per_criterion(self):
        calls: list = []
        evaluator = build_evaluator({"evaluator": "rubric_criteria"})
        evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "pass", "c3": "pass"}, calls)))
        assert len(calls) == 3
        # Each call sees only its own criterion, so verdicts stay independent.
        assert all(sum(f"[c{i}]" in p for i in (1, 2, 3)) == 1 for p in calls)

    def test_batched_mode_asks_once(self):
        calls: list = []
        evaluator = build_evaluator({"evaluator": "rubric_criteria", "config": {"mode": "batched"}})
        evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "pass", "c3": "pass"}, calls)))
        assert len(calls) == 1

    def test_calibration_is_recorded_on_the_judgement(self):
        evaluator = build_evaluator(
            {"evaluator": "rubric_criteria", "config": {"calibration": True}}
        )
        j = evaluator.evaluate(_ctx(_judge({"c1": "pass", "c2": "pass", "c3": "pass"})))
        assert j.evaluator_metadata["calibration"] is True
        assert j.evaluator_metadata["advisory"] is True


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _judgement(verdicts: list[str], calibration: bool = False) -> dict:
    rows = [
        {"id": f"c{i}", "text": f"Criterion {i}", "verdict": v, "rationale": "r"}
        for i, v in enumerate(verdicts, start=1)
    ]
    return {
        "evaluator_key": "rubric_criteria",
        "kind": "model_based",
        "evaluator_metadata": {
            "criteria": rows,
            "judge_model": "judge-model-1",
            "mode": "per_criterion",
            "calibration": calibration,
        },
    }


@pytest.fixture
def bench(db, project):
    """Two models, two conditions, two questions, and one calibration result."""
    system = System(project_id=project.id, name="Field", slug="field")
    db.add(system)
    db.flush()

    def version(model, condition, priced):
        params = {"condition": condition}
        if priced:
            params.update(price_per_mtok_in=3.0, price_per_mtok_out=15.0)
        v = SystemVersion(
            system_id=system.id, version=f"{model}-{condition}", model_name=model, parameters=params
        )
        db.add(v)
        return v

    versions = {
        ("alpha", "baseline"): version("alpha", "baseline", True),
        ("alpha", "web_search"): version("alpha", "web_search", True),
        ("beta", "baseline"): version("beta", "baseline", False),
        ("beta", "web_search"): version("beta", "web_search", False),
    }
    scenarios = []
    for key, topic in (("q1", "protests"), ("q2", "payment")):
        s = Scenario(
            key=key,
            title=f"Question {key}",
            tags=["govcon-bench", f"topic:{topic}", "split:public"],
            criteria=[{"id": f"c{i}", "text": f"Criterion {i}"} for i in (1, 2, 3)],
            approved=True,
            approved_by="jason@example.test",
            required_expertise=["acquisition"],
            provenance={"pack": "bench-govcon-questions", "pack_version": "0.1.0"},
        )
        db.add(s)
        scenarios.append(s)
    evaluation = Evaluation(key="govcon-bench-criteria", name="GovCon Bench")
    campaign = Campaign(project_id=project.id, name="GovCon Bench run 1")
    db.add_all([evaluation, campaign])
    db.flush()

    verdicts = {
        ("alpha", "baseline"): [["pass", "pass", "fail"], ["pass", "not_evaluated", "pass"]],
        ("alpha", "web_search"): [["pass", "pass", "pass"], ["pass", "pass", "pass"]],
        ("beta", "baseline"): [["fail", "fail", "fail"], ["pass", "fail", "fail"]],
        ("beta", "web_search"): [["pass", "fail", "fail"], ["pass", "pass", "fail"]],
    }
    results = {}
    for slot, v in versions.items():
        run = Run(campaign_id=campaign.id, evaluation_id=evaluation.id, system_version_id=v.id)
        db.add(run)
        db.flush()
        for scenario, vs in zip(scenarios, verdicts[slot], strict=True):
            r = Result(
                run_id=run.id,
                scenario_id=scenario.id,
                judgements=[_judgement(vs)],
                request={"prompt": f"Ask {scenario.key}"},
                response={"text": "Answer"},
                tokens_in=1000,
                tokens_out=500,
                latency_ms=2000,
                content_hash="h" * 64,
            )
            db.add(r)
            results[(slot, scenario.key)] = r

    # A calibration result: judged, then labelled by experts. It must feed the
    # agreement figures and nothing else.
    cal_run = Run(
        campaign_id=campaign.id,
        evaluation_id=evaluation.id,
        system_version_id=versions[("alpha", "baseline")].id,
    )
    db.add(cal_run)
    db.flush()
    calibration = Result(
        run_id=cal_run.id,
        scenario_id=scenarios[0].id,
        judgements=[_judgement(["pass", "pass", "fail"], calibration=True)],
    )
    db.add(calibration)
    db.flush()
    return {
        "campaign": campaign,
        "project": project,
        "results": results,
        "calibration": calibration,
        "scenarios": scenarios,
    }


def _row(data, model, condition):
    return next(r for r in data["leaderboard"] if (r["model"], r["condition"]) == (model, condition))


class TestBenchmarkData:
    def test_pass_rate_is_met_over_judged_and_undecided_is_counted_apart(self, db, bench):
        data = benchmark_data(db, [bench["campaign"]])
        row = _row(data, "alpha", "baseline")
        # 4 met of 5 judged; one not decided.
        assert row["criteria_passed"] == 4
        assert row["criteria_judged"] == 5
        assert row["criteria_not_judged"] == 1
        assert row["pass_rate"] == pytest.approx(0.8)

    def test_calibration_results_are_not_scores(self, db, bench):
        data = benchmark_data(db, [bench["campaign"]])
        assert data["calibration_results"] == 1
        assert data["results_scored"] == 8
        assert _row(data, "alpha", "baseline")["criteria_total"] == 6

    def test_missing_prices_are_not_recorded_not_zero(self, db, bench):
        data = benchmark_data(db, [bench["campaign"]])
        assert _row(data, "beta", "baseline")["cost_per_test"] is None
        # 1000 * 3/1e6 + 500 * 15/1e6
        assert _row(data, "alpha", "baseline")["cost_per_test"] == pytest.approx(0.0105)

    def test_condition_effect_is_paired_by_model(self, db, bench):
        data = benchmark_data(db, [bench["campaign"]])
        effect = next(e for e in data["condition_effects"] if e["condition"] == "web_search")
        assert effect["models_compared"] == 2
        # alpha 0.8 -> 1.0, beta 1/6 -> 3/6: mean of +0.2 and +0.333...
        assert effect["mean_change"] == pytest.approx((0.2 + 2 / 6) / 2)

    def test_facets_break_down_by_topic(self, db, bench):
        data = benchmark_data(db, [bench["campaign"]])
        topics = {v["value"]: v for v in data["facets"]["topic"]}
        assert set(topics) == {"protests", "payment"}
        assert topics["protests"]["questions"] == 1
        assert topics["protests"]["enough_questions"] is False

    def test_alignment_counts_only_qualified_expert_labels(self, db, bench):
        calibration = bench["calibration"]
        db.add_all(
            [
                HumanReview(
                    result_id=calibration.id,
                    reviewer_label="Jason",
                    status=ResultStatus.FAIL,
                    qualified=True,
                    # judge: pass, pass, fail
                    criteria_labels={"c1": "pass", "c2": "fail", "c3": "fail"},
                ),
                HumanReview(
                    result_id=calibration.id,
                    reviewer_label="Someone outside the discipline",
                    status=ResultStatus.PASS,
                    qualified=False,
                    criteria_labels={"c1": "fail", "c2": "fail", "c3": "fail"},
                ),
            ]
        )
        db.flush()
        alignment = benchmark_data(db, [bench["campaign"]])["judge_alignment"]
        assert alignment["true_pass"] == 1
        assert alignment["false_pass"] == 1
        assert alignment["true_fail"] == 1
        assert alignment["false_fail"] == 0
        assert alignment["accuracy"] == pytest.approx(2 / 3)
        assert alignment["false_pass_rate"] == pytest.approx(0.5)
        assert alignment["unqualified_reviews_excluded"] == 1

    def test_no_expert_labels_means_agreement_is_unknown(self, db, bench):
        alignment = benchmark_data(db, [bench["campaign"]])["judge_alignment"]
        assert alignment["accuracy"] is None
        assert alignment["comparisons"] == 0


class TestBenchmarkReport:
    def test_report_has_the_sections_a_reader_expects(self, db, bench):
        body = benchmark_report(db, bench["project"], benchmark_data(db, [bench["campaign"]]))
        for heading in (
            "## Key measurements",
            "## Results",
            "## Effect of conditions",
            "## Breakdowns",
            "## Grading",
            "## Example",
            "## Methodology",
            "## Limitations",
        ):
            assert heading in body
        assert "not a trust score" in body

    def test_unmeasured_judge_agreement_is_said_in_words(self, db, bench):
        body = benchmark_report(db, bench["project"], benchmark_data(db, [bench["campaign"]]))
        assert "Judge agreement with experts: not measured" in body
        assert "**Not measured.**" in body

    def test_missing_cost_reads_as_not_recorded(self, db, bench):
        body = benchmark_report(db, bench["project"], benchmark_data(db, [bench["campaign"]]))
        beta_rows = [line for line in body.splitlines() if line.startswith("| beta | baseline")]
        assert beta_rows and "not recorded" in beta_rows[0]
        assert "$0.0000" not in body

    def test_a_campaign_with_nothing_scored_says_so(self, db, project):
        campaign = Campaign(project_id=project.id, name="Empty")
        db.add(campaign)
        db.flush()
        body = benchmark_report(db, project, benchmark_data(db, [campaign]))
        assert "nothing to report" in body
        assert "## Results" not in body


# ---------------------------------------------------------------------------
# Expert labels, pack loading and validation
# ---------------------------------------------------------------------------


class TestCriteriaLabels:
    def test_labels_must_name_the_scenarios_criteria(self, db, bench):
        from aegis.routers.campaigns import _check_criteria_labels

        result = bench["results"][(("alpha", "baseline"), "q1")]
        _check_criteria_labels(db, result, {"c1": "pass", "c2": "not_evaluated"})
        with pytest.raises(HTTPException) as unknown:
            _check_criteria_labels(db, result, {"c9": "pass"})
        assert "Unknown criteria" in unknown.value.detail
        with pytest.raises(HTTPException) as bad:
            _check_criteria_labels(db, result, {"c1": "warning"})
        assert "pass, fail or not_evaluated" in bad.value.detail


class TestPackLoading:
    def _install(self, db, **scenario):
        from sqlalchemy import select

        from aegis.packs.loader import install_pack

        install_pack(
            db,
            {
                "key": "bench-test",
                "kind": "scenario",
                "version": "1.0.0",
                "scenarios": [{"key": "bq", "title": "Q", "input": {"prompt": "?"}, **scenario}],
            },
        )
        return db.execute(select(Scenario).where(Scenario.key == "bq")).scalar_one()

    def test_criteria_and_draft_status_are_installed(self, db):
        s = self._install(
            db, criteria=CRITERIA, generated=True, approved=False
        )
        assert [c["id"] for c in s.criteria] == ["c1", "c2", "c3"]
        assert s.generated is True
        assert s.approved is False

    def test_a_scenario_without_criteria_keeps_its_old_hash(self, db):
        """Existing scenarios must not change identity because a new field
        exists, or comparisons against earlier campaigns stop lining up."""
        from aegis.hashing import content_hash

        s = self._install(db)
        assert s.content_hash == content_hash({"key": "bq", "input": {"prompt": "?"}, "version": "1.0.0"})


class TestCriteriaValidation:
    def test_repeated_and_missing_ids_are_refused(self):
        from validate_packs import validate_criteria

        assert validate_criteria({"key": "ok", "criteria": CRITERIA}) == []
        problems = validate_criteria(
            {"key": "bad", "criteria": [{"id": "c1", "text": "a"}, {"id": "c1", "text": "b"}, {"text": "c"}]}
        )
        assert any("repeats criterion id" in p for p in problems)
        assert any("has no id" in p for p in problems)

    def test_empty_text_and_empty_lists_are_refused(self):
        from validate_packs import validate_criteria

        assert validate_criteria({"key": "k", "criteria": []})
        assert validate_criteria({"key": "k", "criteria": [{"id": "c1", "text": "  "}]})
