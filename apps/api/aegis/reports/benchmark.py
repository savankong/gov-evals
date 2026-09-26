"""Benchmark report: a published-benchmark write-up built from stored results.

The structure follows what a reader of a public benchmark expects -- key
measurements, a results table across models and conditions, breakdowns by
topic, how grading was done and how far to trust it, one graded example, the
method, and the limits. Every section is computed; nothing here is typed in.

It states measurements only. Interpretation and recommendations belong to the
program that publishes it, and the report says so rather than supplying them.
"""

from __future__ import annotations

from ..models import Project
from .generators import _banner, _now

_NOT_RECORDED = "not recorded"


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if isinstance(value, (int, float)) else "—"


def _points(value: float | None) -> str:
    return f"{value * 100:+.1f} pts" if isinstance(value, (int, float)) else "—"


def _money(value: float | None) -> str:
    return f"${value:.4f}" if isinstance(value, (int, float)) else _NOT_RECORDED


def _seconds(ms: float | None) -> str:
    return f"{ms / 1000:.1f} s" if isinstance(ms, (int, float)) else _NOT_RECORDED


def _cell(text: object) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def _sort_condition(data: dict) -> str | None:
    """Rank by the condition the most models ran under, so the ordering covers
    as much of the field as possible."""
    counts: dict[str, int] = {}
    for row in data["leaderboard"]:
        if row["pass_rate"] is not None:
            counts[row["condition"]] = counts.get(row["condition"], 0) + 1
    return max(sorted(counts), key=lambda c: counts[c]) if counts else None


def benchmark_report(db, project: Project, data: dict, title: str | None = None) -> str:
    name = title or f"{project.name} benchmark"
    lines = [
        _banner(project.classification),
        "",
        f"# {name}",
        "",
        f"Generated {_now()} from campaign(s): "
        + ", ".join(f"{c['name']} (`{c['id']}`)" for c in data["campaigns"])
        + ".",
        "",
        *_demonstration(data),
    ]

    if not data["leaderboard"] or data["results_scored"] == 0:
        lines += [
            "No result in these campaigns was scored against criteria, so there is nothing to "
            "report. A benchmark campaign needs an evaluation using the `rubric_criteria` "
            "evaluator, scenarios with criteria, and a judge model configured on the campaign.",
            "",
            _banner(project.classification),
        ]
        return "\n".join(lines)

    lines += _key_measurements(data)
    lines += _results(data)
    lines += _conditions(data)
    lines += _breakdowns(data)
    lines += _grading(data)
    lines += _example(data)
    lines += _methodology(data)
    lines += _limitations(data)
    lines += [
        "## How to read this",
        "",
        "The pass rate is the share of judged criteria that answers met on this question set. "
        "It is a measurement on these questions under these conditions. It is not a trust "
        "score, and it does not stand for performance on any other task.",
        "",
        "This report states measurements only. Interpretation and recommendations are the "
        "publishing program's, and are published alongside it.",
        "",
        "---",
        "",
        _banner(project.classification),
    ]
    return "\n".join(lines)


def _demonstration(data: dict) -> list[str]:
    """The statement a demonstration campaign carries, at the top of the report.

    It says what in the data is a stand-in, so nobody reads a demonstration as
    a published benchmark or its reviewer as a qualified expert.
    """
    statements = data.get("demonstration") or []
    if not statements:
        return []
    out = ["> **DEMONSTRATION DATA -- NOT A PUBLISHED BENCHMARK.**", ">"]
    for statement in statements:
        out.append("> " + _cell(statement.get("statement") or "This campaign was run as a demonstration."))
        out.extend(f"> - {_cell(item)}" for item in statement.get("stand_ins") or [])
    return [*out, ""]


def _simulated_review(data: dict) -> bool:
    return any(s.get("simulated_reviewer") for s in data.get("demonstration") or [])


def _key_measurements(data: dict) -> list[str]:
    out = ["## Key measurements", ""]
    for condition in data["conditions"]:
        rows = [r for r in data["leaderboard"] if r["condition"] == condition and r["pass_rate"] is not None]
        if not rows:
            continue
        best = max(rows, key=lambda r: r["pass_rate"])
        worst = min(rows, key=lambda r: r["pass_rate"])
        out.append(
            f"- **{condition}:** highest pass rate {_pct(best['pass_rate'])} ({best['model']}); "
            f"lowest {_pct(worst['pass_rate'])} ({worst['model']}); {len(rows)} models."
        )
    out.extend(
        f"- **{effect['condition']} vs baseline:** mean change "
        f"{_points(effect['mean_change'])} across {effect['models_compared']} models "
        "that ran both."
        for effect in data["condition_effects"]
        if effect["mean_change"] is not None
    )
    for facet, values in data["facets"].items():
        readable = [v for v in values if v["enough_questions"] and v["pass_rate"] is not None]
        if len(readable) >= 2:
            lo = min(readable, key=lambda v: v["pass_rate"])
            hi = max(readable, key=lambda v: v["pass_rate"])
            out.append(
                f"- **By {facet}:** from {_pct(lo['pass_rate'])} ({lo['value']}) to "
                f"{_pct(hi['pass_rate'])} ({hi['value']}), pooled over all models."
            )
    alignment = data["judge_alignment"]
    if alignment["accuracy"] is None:
        out.append(
            "- **Judge agreement with experts: not measured.** Scores below come from a model "
            "judge whose agreement with qualified experts has not been checked on these questions."
        )
    elif _simulated_review(data):
        out.append(
            f"- **Judge agreement with a simulated reviewer (not an expert):** "
            f"{_pct(alignment['accuracy'])} over {alignment['comparisons']} criterion verdicts. "
            "Agreement with qualified experts has not been measured."
        )
    else:
        out.append(
            f"- **Judge agreement with experts:** {_pct(alignment['accuracy'])} over "
            f"{alignment['comparisons']} criterion verdicts from {alignment['experts']} expert(s)."
        )
    return [*out, ""]


def _results(data: dict) -> list[str]:
    sort_by = _sort_condition(data)
    conditions = data["conditions"]
    by_model: dict[str, dict[str, dict]] = {}
    for row in data["leaderboard"]:
        by_model.setdefault(row["model"], {})[row["condition"]] = row

    def key(model: str):
        rate = (by_model[model].get(sort_by) or {}).get("pass_rate")
        return (rate is None, -(rate or 0), model)

    out = [
        "## Results",
        "",
        f"Pass rate by model and condition, sorted by **{sort_by}**. A dash means the model "
        "did not run under that condition or had nothing judged.",
        "",
        "| Model | " + " | ".join(conditions) + " |",
        "| --- | " + " | ".join("---:" for _ in conditions) + " |",
    ]
    for model in sorted(by_model, key=key):
        cells = [_pct((by_model[model].get(c) or {}).get("pass_rate")) for c in conditions]
        out.append(f"| {_cell(model)} | " + " | ".join(cells) + " |")

    out += [
        "",
        "### Detail",
        "",
        "| Model | Condition | Pass rate | Criteria met / judged | Not judged | Questions "
        "| Cost per test | Median latency | Errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(data["leaderboard"], key=lambda r: (r["model"], r["condition"])):
        cost = _money(row["cost_per_test"])
        if row["cost_per_test"] is not None and row["results_without_cost"]:
            cost += f" ({row['results_without_cost']} tests unpriced)"
        out.append(
            f"| {_cell(row['model'])} | {_cell(row['condition'])} | {_pct(row['pass_rate'])} "
            f"| {row['criteria_passed']} / {row['criteria_judged']} | {row['criteria_not_judged']} "
            f"| {row['questions']} | {cost} | {_seconds(row['latency_ms_median'])} "
            f"| {row['errors']} |"
        )
    return [*out, ""]


def _conditions(data: dict) -> list[str]:
    effects = [e for e in data["condition_effects"] if e["models_compared"]]
    if not effects:
        return []
    out = [
        "## Effect of conditions",
        "",
        "Change in pass rate from baseline, paired by model so the difference reflects the "
        "condition rather than which models ran under it.",
        "",
        "| Condition | Models compared | Mean change from baseline |",
        "| --- | ---: | ---: |",
    ]
    out.extend(
        f"| {_cell(effect['condition'])} | {effect['models_compared']} "
        f"| {_points(effect['mean_change'])} |"
        for effect in effects
    )
    return [*out, ""]


def _breakdowns(data: dict) -> list[str]:
    if not data["facets"]:
        return []
    out = ["## Breakdowns", ""]
    for facet, values in data["facets"].items():
        out += [
            f"### By {facet}",
            "",
            "Pooled over all models and conditions. Values with fewer than five questions are "
            "shown but marked, and are not read as findings.",
            "",
            f"| {facet.capitalize()} | Questions | Criteria judged | Pass rate |",
            "| --- | ---: | ---: | ---: |",
        ]
        for value in sorted(values, key=lambda v: (v["pass_rate"] is None, -(v["pass_rate"] or 0))):
            marker = "" if value["enough_questions"] else " (too few questions)"
            out.append(
                f"| {_cell(value['value'])}{marker} | {value['questions']} "
                f"| {value['criteria_judged']} | {_pct(value['pass_rate'])} |"
            )
        out.append("")
    return out


def _grading(data: dict) -> list[str]:
    judge = data["judge"]
    alignment = data["judge_alignment"]
    out = [
        "## Grading",
        "",
        f"Each answer was checked against each of its criteria separately by a model judge "
        f"({', '.join(judge['models']) or 'judge model not recorded'}; mode: "
        f"{', '.join(judge['modes']) or 'not recorded'}). A criterion the judge could not "
        "decide is excluded from the pass rate and counted under *not judged*.",
        "",
        "### Agreement with qualified experts",
        "",
    ]
    if alignment["comparisons"] == 0:
        out += [
            "**Not measured.** No qualified expert has labelled criteria on these results, so "
            "how often the judge agrees with experts is unknown. Treat every score above as the "
            "judge's, not the experts'.",
            "",
        ]
    else:
        who = "Reviewer" if _simulated_review(data) else "Expert"
        if _simulated_review(data):
            out += [
                "**Simulated reviewer.** In this demonstration the labels below come from a "
                "stand-in reviewer, not a qualified expert. The table shows how the agreement "
                "measurement works; it is not evidence that the judge agrees with experts.",
                "",
            ]
        out += [
            f"{alignment['experts']} "
            + ("reviewer(s)" if _simulated_review(data) else "qualified expert(s)")
            + f" labelled {alignment['criteria_compared']} "
            f"criteria ({alignment['comparisons']} comparisons). Only reviews that counted as "
            "expert evidence are compared"
            + (
                f"; {alignment['unqualified_reviews_excluded']} review(s) from outside the "
                "required discipline were set aside."
                if alignment["unqualified_reviews_excluded"]
                else "."
            ),
            "",
            f"| | {who}: pass | {who}: fail |",
            "| --- | ---: | ---: |",
            f"| **Judge: pass** | {alignment['true_pass']} | {alignment['false_pass']} |",
            f"| **Judge: fail** | {alignment['false_fail']} | {alignment['true_fail']} |",
            "",
            f"- Agreement: **{_pct(alignment['accuracy'])}**",
            f"- False passes (judge passed what the {who.lower()} failed), as a share of "
            f"{who.lower()} fails: **{_pct(alignment['false_pass_rate'])}**. These inflate scores.",
            "",
        ]
    return out


def _example(data: dict) -> list[str]:
    example = data["example"]
    if not example:
        return []
    rows = example["criteria"]
    met = sum(1 for r in rows if r.get("verdict") == "pass")
    answer = (example.get("answer") or "").strip()
    if len(answer) > 2500:
        answer = answer[:2500] + " […]"
    out = [
        "## Example",
        "",
        f"**{_cell(example['title'])}** — {example['model']} under {example['condition']}. "
        f"{met} of {len(rows)} criteria met. Result `{example['result_id']}`, "
        f"SHA-256 `{example['content_hash']}`.",
        "",
        "**Question**",
        "",
        "> " + (example.get("question") or "").replace("\n", "\n> "),
        "",
        "**Answer**",
        "",
        "> " + answer.replace("\n", "\n> "),
        "",
        "| Criterion | Verdict | Judge's reason |",
        "| --- | --- | --- |",
    ]
    out.extend(
        f"| {_cell(row.get('text'))} | {_cell(row.get('verdict'))} | {_cell(row.get('rationale'))} |"
        for row in rows
    )
    return [*out, ""]


def _methodology(data: dict) -> list[str]:
    ds = data["dataset"]
    out = [
        "## Methodology",
        "",
        "### Dataset",
        "",
        f"- **{ds['questions']} questions**, **{ds['criteria']} criteria** "
        f"({ds['criteria_per_question']:.1f} per question)."
        if ds["criteria_per_question"] is not None
        else f"- **{ds['questions']} questions**.",
        "- Split: " + ", ".join(f"{k} {v}" for k, v in ds["splits"].items()) + ".",
        "- Packs: " + (", ".join(f"`{p}`" for p in ds["packs"]) or "not recorded") + ".",
        "- Expertise required to judge: " + (", ".join(ds["required_expertise"]) or "not declared") + ".",
        "- Approved for use by: " + (", ".join(ds["approved_by"]) or "no named approver") + ".",
    ]
    if ds["model_drafted"] and data.get("demonstration"):
        out.append(
            f"- {ds['model_drafted']} question(s) were drafted by a model. For this demonstration "
            "they were approved by the stand-in named above, not by an expert."
        )
    elif ds["model_drafted"]:
        out.append(
            f"- {ds['model_drafted']} question(s) were first drafted by a model and ran only after "
            "a person approved them."
        )
    out += [
        "",
        "### Conditions",
        "",
        "Each model ran under each condition listed below as a separate system version, with "
        "the same questions. The exact configuration of each is the system version's snapshot, "
        "identified in the detail table by model and condition.",
        "",
        "- " + "\n- ".join(data["conditions"]),
        "",
        "### Scoring",
        "",
        "Pass rate = criteria met ÷ criteria judged, pooled over every question the model "
        "answered under that condition. Criteria the judge did not decide are excluded from "
        "both and reported separately. Cost per test is computed from recorded token counts "
        "and the prices declared on the system version; where either is missing it is "
        "reported as not recorded, not as zero.",
        "",
    ]
    return out


def _limitations(data: dict) -> list[str]:
    notes = []
    if data.get("demonstration"):
        notes.append(
            "Demonstration data. The stand-ins listed at the top of this report replace steps "
            "a published benchmark gives to people; none of these figures is a finding."
        )
    thin = [
        f"{facet} = {v['value']} ({v['questions']})"
        for facet, values in data["facets"].items()
        for v in values
        if not v["enough_questions"]
    ]
    if thin:
        notes.append(
            "Too few questions to read as findings: " + "; ".join(thin[:12])
            + ("; …" if len(thin) > 12 else "") + "."
        )
    not_judged = sum(r["criteria_not_judged"] for r in data["leaderboard"])
    total = sum(r["criteria_total"] for r in data["leaderboard"])
    if not_judged:
        notes.append(
            f"{not_judged} of {total} criterion checks ({not_judged / total:.1%}) were not decided "
            "by the judge and are excluded from pass rates."
        )
    if data["results_without_criteria_scores"]:
        notes.append(
            f"{data['results_without_criteria_scores']} result(s) in these campaigns carry no "
            "criteria scores and are not counted here."
        )
    unpriced = [r for r in data["leaderboard"] if r["cost_per_test"] is None]
    if unpriced:
        notes.append(
            f"Cost is not recorded for {len(unpriced)} model/condition pair(s): no declared "
            "prices, or no token counts from the connector."
        )
    alignment = data["judge_alignment"]
    if alignment["comparisons"] == 0:
        notes.append("Judge agreement with qualified experts was not measured.")
    elif alignment["comparisons"] < 100:
        notes.append(
            f"Judge agreement rests on {alignment['comparisons']} comparisons; treat the "
            "agreement figure as indicative."
        )
    if data["dataset"]["questions_without_named_approver"]:
        notes.append(
            f"{data['dataset']['questions_without_named_approver']} question(s) have no named "
            "approver on record."
        )
    errors = sum(r["errors"] for r in data["leaderboard"])
    if errors:
        notes.append(f"{errors} test(s) ended in an error and are shown in the detail table.")
    if not notes:
        notes.append("None identified from the stored results beyond those stated above.")
    return ["## Limitations", ""] + [f"- {n}" for n in notes] + [""]
