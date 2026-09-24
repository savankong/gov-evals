"""Benchmark analysis: criteria pass rates across models and conditions.

A published benchmark answers a narrower question than an assurance report:
on this set of questions, how often did each model meet the criteria experts
wrote for them, and under which conditions. Everything here is computed from
stored results, so every figure resolves to the results behind it.

Three rules carried over from the rest of the product:

- A criterion the judge did not decide is left out of the pass rate and
  counted separately. It is never folded in as a pass or as a fail.
- A figure that was not recorded -- cost without a price, a pass rate with
  nothing judged -- is `None`, and is reported as not recorded. Zero is a
  measurement; missing is not zero.
- The model judge is advisory. How often it agrees with qualified experts on
  the same criteria is measured and published next to its scores.

Conventions a benchmark campaign follows:

- Each system version is one model under one condition. The condition is
  `parameters["condition"]` (for example baseline, web_search, multi_turn),
  and defaults to `baseline`.
- A scenario tag of the form `name:value` is a facet (`topic:set-asides`,
  `phase:award`, `split:public`) and gets its own breakdown.
- Cost is computed only when the system version declares its prices, as
  `price_per_mtok_in` and `price_per_mtok_out` in US dollars per million tokens.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enums import ResultStatus
from .models import Campaign, HumanReview, Result, Run, Scenario, SystemVersion

EVALUATOR_KEY = "rubric_criteria"
DEFAULT_CONDITION = "baseline"
# Below this many questions a facet value is shown but not read as a finding.
MIN_QUESTIONS_FOR_FACET = 5

_DECIDED = (ResultStatus.PASS, ResultStatus.FAIL)


def _rate(passed: int, judged: int) -> float | None:
    return passed / judged if judged else None


def _criteria_judgement(result: Result, evaluator_key: str) -> dict | None:
    for judgement in result.judgements or []:
        if judgement.get("evaluator_key") == evaluator_key:
            return judgement.get("evaluator_metadata") or {}
    return None


def _cost(result: Result, version: SystemVersion) -> float | None:
    params = version.parameters or {}
    price_in, price_out = params.get("price_per_mtok_in"), params.get("price_per_mtok_out")
    if price_in is None or price_out is None:
        return None
    if result.tokens_in is None or result.tokens_out is None:
        return None
    return (result.tokens_in * float(price_in) + result.tokens_out * float(price_out)) / 1_000_000


def _facets(tags: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in tags or []:
        if ":" in tag:
            name, _, value = tag.partition(":")
            if name and value:
                out[name] = value
    return out


class _Tally:
    __slots__ = ("failed", "passed", "question_keys", "undecided")

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.undecided = 0
        self.question_keys: set[str] = set()

    def add(self, rows: list[dict], question_key: str) -> None:
        self.question_keys.add(question_key)
        for row in rows:
            verdict = row.get("verdict")
            if verdict == ResultStatus.PASS:
                self.passed += 1
            elif verdict == ResultStatus.FAIL:
                self.failed += 1
            else:
                self.undecided += 1

    def as_dict(self) -> dict:
        judged = self.passed + self.failed
        return {
            "criteria_passed": self.passed,
            "criteria_judged": judged,
            "criteria_not_judged": self.undecided,
            "criteria_total": judged + self.undecided,
            "questions": len(self.question_keys),
            "pass_rate": _rate(self.passed, judged),
        }


def benchmark_data(
    db: Session, campaigns: list[Campaign], evaluator_key: str = EVALUATOR_KEY
) -> dict:
    """Everything a benchmark report states, as data."""
    runs = [
        run
        for campaign in campaigns
        for run in db.execute(select(Run).where(Run.campaign_id == campaign.id)).scalars()
    ]

    versions: dict[str, SystemVersion] = {}
    scenarios: dict[str, Scenario] = {}
    systems: dict[tuple[str, str], dict] = {}
    facet_tallies: dict[str, dict[str, _Tally]] = defaultdict(lambda: defaultdict(_Tally))
    facet_by_system: dict[str, dict[str, dict[tuple[str, str], _Tally]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(_Tally))
    )
    judged_results: list[tuple[Result, list[dict], tuple[str, str]]] = []
    calibration_results: list[tuple[Result, list[dict], tuple[str, str]]] = []
    unscored_results = 0

    for run in runs:
        version = versions.get(run.system_version_id) or db.get(SystemVersion, run.system_version_id)
        if version is None:
            continue
        versions[version.id] = version
        model = version.model_name or version.version
        condition = str((version.parameters or {}).get("condition") or DEFAULT_CONDITION)
        slot = (model, condition)
        entry = systems.setdefault(
            slot,
            {
                "model": model,
                "condition": condition,
                "provider": version.model_provider,
                "system_version_ids": set(),
                "tally": _Tally(),
                "costs": [],
                "results_without_cost": 0,
                "latencies": [],
                "errors": 0,
            },
        )
        entry["system_version_ids"].add(version.id)

        for result in db.execute(select(Result).where(Result.run_id == run.id)).scalars():
            if result.error:
                entry["errors"] += 1
            meta = _criteria_judgement(result, evaluator_key)
            if meta is None:
                unscored_results += 1
                continue
            rows = list(meta.get("criteria") or [])
            if meta.get("calibration"):
                # Judged so experts can label the same criteria. It measures
                # the judge; counting it in scores would count a question twice.
                calibration_results.append((result, rows, (model, condition)))
                continue
            scenario = None
            if result.scenario_id:
                scenario = scenarios.get(result.scenario_id) or db.get(Scenario, result.scenario_id)
                if scenario is not None:
                    scenarios[scenario.id] = scenario
            question_key = scenario.key if scenario else (result.scenario_id or result.id)

            entry["tally"].add(rows, question_key)
            judged_results.append((result, rows, slot))
            cost = _cost(result, version)
            if cost is None:
                entry["results_without_cost"] += 1
            else:
                entry["costs"].append(cost)
            if result.latency_ms is not None:
                entry["latencies"].append(result.latency_ms)

            for name, value in _facets(scenario.tags if scenario else []).items():
                facet_tallies[name][value].add(rows, question_key)
                facet_by_system[name][value][slot].add(rows, question_key)

    leaderboard = []
    for entry in systems.values():
        row = {
            "model": entry["model"],
            "condition": entry["condition"],
            "provider": entry["provider"],
            "system_version_ids": sorted(entry["system_version_ids"]),
            **entry["tally"].as_dict(),
            # Mean over the results that carry a cost. When some do not, the
            # count says so rather than the mean quietly covering fewer tests.
            "cost_per_test": (sum(entry["costs"]) / len(entry["costs"])) if entry["costs"] else None,
            "results_without_cost": entry["results_without_cost"],
            "latency_ms_median": median(entry["latencies"]) if entry["latencies"] else None,
            "errors": entry["errors"],
        }
        leaderboard.append(row)

    conditions = sorted({row["condition"] for row in leaderboard})
    models = sorted({row["model"] for row in leaderboard})

    facets = {}
    for name, values in sorted(facet_tallies.items()):
        facets[name] = [
            {
                "value": value,
                **tally.as_dict(),
                "enough_questions": len(tally.question_keys) >= MIN_QUESTIONS_FOR_FACET,
                "by_system": {
                    f"{model} / {condition}": t.as_dict()["pass_rate"]
                    for (model, condition), t in sorted(facet_by_system[name][value].items())
                },
            }
            for value, tally in sorted(values.items())
        ]

    return {
        "campaigns": [{"id": c.id, "name": c.name} for c in campaigns],
        "evaluator_key": evaluator_key,
        "models": models,
        "conditions": conditions,
        "leaderboard": leaderboard,
        "condition_effects": _condition_effects(leaderboard, conditions),
        "facets": facets,
        "dataset": _dataset(list(scenarios.values())),
        "judge": _judge_info(judged_results),
        "judge_alignment": judge_alignment(db, judged_results + calibration_results),
        "example": _example(judged_results, scenarios),
        "results_scored": len(judged_results),
        "calibration_results": len(calibration_results),
        "results_without_criteria_scores": unscored_results,
    }


def _condition_effects(leaderboard: list[dict], conditions: list[str]) -> list[dict]:
    """Mean change in pass rate from baseline, over models that ran both.

    Pairing by model is what makes the difference about the condition rather
    than about which models happened to run under it.
    """
    if DEFAULT_CONDITION not in conditions:
        return []
    by_model: dict[str, dict[str, float | None]] = defaultdict(dict)
    for row in leaderboard:
        by_model[row["model"]][row["condition"]] = row["pass_rate"]
    effects = []
    for condition in conditions:
        if condition == DEFAULT_CONDITION:
            continue
        deltas = [
            rates[condition] - rates[DEFAULT_CONDITION]
            for rates in by_model.values()
            if rates.get(condition) is not None and rates.get(DEFAULT_CONDITION) is not None
        ]
        effects.append(
            {
                "condition": condition,
                "models_compared": len(deltas),
                "mean_change": (sum(deltas) / len(deltas)) if deltas else None,
            }
        )
    return effects


def _dataset(scenarios: list[Scenario]) -> dict:
    criteria = sum(len(s.criteria or []) for s in scenarios)
    splits: dict[str, int] = defaultdict(int)
    for scenario in scenarios:
        splits[_facets(scenario.tags).get("split", "unspecified")] += 1
    return {
        "questions": len(scenarios),
        "criteria": criteria,
        "criteria_per_question": (criteria / len(scenarios)) if scenarios else None,
        "splits": dict(sorted(splits.items())),
        "packs": sorted(
            {
                f"{(s.provenance or {}).get('pack', s.source)} "
                f"{(s.provenance or {}).get('pack_version', s.version)}"
                for s in scenarios
            }
        ),
        "approved_by": sorted({s.approved_by for s in scenarios if s.approved_by}),
        "questions_without_named_approver": sum(1 for s in scenarios if not s.approved_by),
        "model_drafted": sum(1 for s in scenarios if s.generated),
        "required_expertise": sorted({d for s in scenarios for d in (s.required_expertise or [])}),
    }


def _judge_info(judged_results: list[tuple[Result, list[dict], tuple[str, str]]]) -> dict:
    models, modes = set(), set()
    for result, _, _ in judged_results:
        for judgement in result.judgements or []:
            if judgement.get("evaluator_key") == EVALUATOR_KEY:
                meta = judgement.get("evaluator_metadata") or {}
                if meta.get("judge_model"):
                    models.add(str(meta["judge_model"]))
                if meta.get("mode"):
                    modes.add(str(meta["mode"]))
    return {"models": sorted(models), "modes": sorted(modes)}


def judge_alignment(
    db: Session, judged_results: list[tuple[Result, list[dict], tuple[str, str]]]
) -> dict:
    """How often the model judge agrees with qualified experts, per criterion.

    Only reviews that counted as expert evidence are compared. A review from
    outside the required discipline is an opinion; measuring the judge against
    it would measure the wrong thing, so it is counted and set aside.
    """
    by_result = {result.id: rows for result, rows, _ in judged_results}
    if not by_result:
        return _empty_alignment()

    reviews = list(
        db.execute(
            select(HumanReview).where(
                HumanReview.result_id.in_(list(by_result)),
                HumanReview.criteria_labels.is_not(None),
            )
        ).scalars()
    )

    matrix = {"true_pass": 0, "true_fail": 0, "false_pass": 0, "false_fail": 0}
    unqualified, reviewers, items = 0, set(), set()
    for review in reviews:
        if not review.qualified:
            unqualified += 1
            continue
        judge = {row.get("id"): row.get("verdict") for row in by_result[review.result_id]}
        for criterion_id, label in (review.criteria_labels or {}).items():
            verdict = judge.get(criterion_id)
            if label not in _DECIDED or verdict not in _DECIDED:
                continue
            reviewers.add(review.reviewer_id or review.reviewer_label)
            items.add((review.result_id, criterion_id))
            if verdict == ResultStatus.PASS:
                matrix["true_pass" if label == ResultStatus.PASS else "false_pass"] += 1
            else:
                matrix["true_fail" if label == ResultStatus.FAIL else "false_fail"] += 1

    compared = sum(matrix.values())
    return {
        **matrix,
        "comparisons": compared,
        "criteria_compared": len(items),
        "experts": len(reviewers),
        "accuracy": _rate(matrix["true_pass"] + matrix["true_fail"], compared),
        # The error that matters most for a benchmark: a criterion the judge
        # passed that an expert failed inflates every score it touches.
        "false_pass_rate": _rate(matrix["false_pass"], matrix["false_pass"] + matrix["true_fail"]),
        "unqualified_reviews_excluded": unqualified,
    }


def _empty_alignment() -> dict:
    return {
        "true_pass": 0,
        "true_fail": 0,
        "false_pass": 0,
        "false_fail": 0,
        "comparisons": 0,
        "criteria_compared": 0,
        "experts": 0,
        "accuracy": None,
        "false_pass_rate": None,
        "unqualified_reviews_excluded": 0,
    }


def _example(
    judged_results: list[tuple[Result, list[dict], tuple[str, str]]],
    scenarios: dict[str, Scenario],
) -> dict | None:
    """One graded answer to show what the grading looks like.

    Chosen deterministically: an answer with both passed and failed criteria
    shows more than one that met or missed everything, and ties go to the
    lowest scenario key so the same report comes out the same way twice.
    """
    def order(item):
        result, rows, slot = item
        verdicts = {r.get("verdict") for r in rows}
        mixed = ResultStatus.PASS in verdicts and ResultStatus.FAIL in verdicts
        scenario = scenarios.get(result.scenario_id or "")
        return (not mixed, scenario.key if scenario else result.id, slot)

    if not judged_results:
        return None
    result, rows, (model, condition) = sorted(judged_results, key=order)[0]
    scenario = scenarios.get(result.scenario_id or "")
    return {
        "result_id": result.id,
        "content_hash": result.content_hash,
        "scenario_key": scenario.key if scenario else None,
        "title": scenario.title if scenario else None,
        "question": (result.request or {}).get("prompt"),
        "answer": (result.response or {}).get("text"),
        "model": model,
        "condition": condition,
        "criteria": rows,
    }
