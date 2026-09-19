"""Model comparison and regression analysis (sections 31, 32).

Both views deliberately stop short of declaring a winner. The platform reports
measurements by dimension; weighting them against mission requirements is the
decision-maker's job, not the product's.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import Domain, ResultStatus
from ..models import Campaign, Evaluation, Result, Run, SystemVersion


def _system_label(db: Session, system_version_id: str) -> dict:
    version = db.get(SystemVersion, system_version_id)
    if version is None:
        return {"id": system_version_id, "label": "unknown"}
    system = version.system
    return {
        "id": version.id,
        "system_id": system.id if system else None,
        "label": f"{system.name} {version.version}" if system else version.version,
        "model": version.model_name,
        "model_version": version.model_version,
        "connector": version.connector_type,
        "config_hash": version.config_hash,
    }


def compare_campaign(db: Session, campaign: Campaign) -> dict:
    """Side-by-side of every system version evaluated in one campaign.

    Because all columns come from the same campaign, they ran the same
    scenarios under the same conditions -- the property that makes a
    procurement comparison defensible (section 65).
    """
    runs = list(db.execute(select(Run).where(Run.campaign_id == campaign.id)).scalars())
    if not runs:
        return {"campaign_id": campaign.id, "systems": [], "rows": [], "note": "No runs executed."}

    version_ids: list[str] = []
    for run in runs:
        if run.system_version_id not in version_ids:
            version_ids.append(run.system_version_id)
    systems = [_system_label(db, vid) for vid in version_ids]

    evaluations: dict[str, Evaluation] = {}
    for run in runs:
        if run.evaluation_id not in evaluations:
            evaluation = db.get(Evaluation, run.evaluation_id)
            if evaluation:
                evaluations[run.evaluation_id] = evaluation

    rows = []
    for evaluation_id, evaluation in sorted(evaluations.items(), key=lambda kv: kv[1].key):
        cells = []
        for version_id in version_ids:
            match = next(
                (r for r in runs if r.evaluation_id == evaluation_id and r.system_version_id == version_id),
                None,
            )
            if match is None:
                # A system that was not put through this evaluation reports
                # NOT EVALUATED rather than a blank that reads as a zero.
                cells.append({"status": ResultStatus.NOT_EVALUATED, "note": "Not run for this system."})
                continue
            cells.append(
                {
                    "run_id": match.id,
                    "status": match.verdict,
                    "pass_rate": (match.metrics or {}).get("pass_rate"),
                    "passed": match.passed,
                    "failed": match.failed,
                    "warning": match.warned,
                    "pending_human": match.pending_human,
                    "executions": match.scenario_count,
                    "latency_ms": (match.metrics or {}).get("latency_ms", {}).get("median"),
                    "scores": {
                        k.removeprefix("score."): v
                        for k, v in (match.metrics or {}).items()
                        if k.startswith("score.")
                    },
                }
            )
        rows.append(
            {
                "evaluation_id": evaluation_id,
                "evaluation_key": evaluation.key,
                "evaluation_name": evaluation.name,
                "domain": evaluation.domain,
                "domain_label": Domain.LABELS.get(evaluation.domain, evaluation.domain),
                "layer": evaluation.layer,
                "metric": evaluation.metric,
                "cells": cells,
            }
        )

    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "systems": systems,
        "rows": rows,
        "note": (
            "Metrics are reported per dimension. Weighting them against mission requirements "
            "is a program decision; the platform does not rank the systems."
        ),
    }


def compare_runs(db: Session, baseline_run: Run, candidate_run: Run) -> dict:
    """Scenario-level diff between two runs of the same evaluation."""
    baseline_results = {
        _result_key(r): r
        for r in db.execute(select(Result).where(Result.run_id == baseline_run.id)).scalars()
    }
    candidate_results = {
        _result_key(r): r
        for r in db.execute(select(Result).where(Result.run_id == candidate_run.id)).scalars()
    }

    new_failures, resolved, degraded, improved, unchanged, changed_output = [], [], [], [], [], []

    for key, candidate in candidate_results.items():
        baseline = baseline_results.get(key)
        if baseline is None:
            continue
        entry = {
            "scenario_key": key,
            "baseline_status": baseline.status,
            "candidate_status": candidate.status,
            "baseline_result_id": baseline.id,
            "candidate_result_id": candidate.id,
        }
        if baseline.status == ResultStatus.PASS and candidate.status == ResultStatus.FAIL:
            new_failures.append(entry)
        elif baseline.status == ResultStatus.FAIL and candidate.status == ResultStatus.PASS:
            resolved.append(entry)
        elif _rank(candidate.status) > _rank(baseline.status):
            degraded.append(entry)
        elif _rank(candidate.status) < _rank(baseline.status):
            improved.append(entry)
        else:
            unchanged.append(entry)
            # Same verdict, materially different text: worth a reviewer's eye
            # even though no metric moved (section 32).
            baseline_text = (baseline.response or {}).get("text") or ""
            candidate_text = (candidate.response or {}).get("text") or ""
            if baseline_text and candidate_text and baseline_text != candidate_text:
                from difflib import SequenceMatcher

                similarity = SequenceMatcher(None, baseline_text, candidate_text).ratio()
                if similarity < 0.6:
                    changed_output.append({**entry, "similarity": round(similarity, 3)})

    only_in_candidate = sorted(set(candidate_results) - set(baseline_results))
    only_in_baseline = sorted(set(baseline_results) - set(candidate_results))

    metric_deltas = {}
    for metric, candidate_value in (candidate_run.metrics or {}).items():
        baseline_value = (baseline_run.metrics or {}).get(metric)
        if isinstance(candidate_value, (int, float)) and isinstance(baseline_value, (int, float)):
            metric_deltas[metric] = {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": round(candidate_value - baseline_value, 4),
            }

    return {
        "baseline_run_id": baseline_run.id,
        "candidate_run_id": candidate_run.id,
        "new_failures": new_failures,
        "resolved_failures": resolved,
        "degraded": degraded,
        "improved": improved,
        "unchanged": len(unchanged),
        "significant_output_changes": changed_output,
        "scenarios_only_in_candidate": only_in_candidate,
        "scenarios_only_in_baseline": only_in_baseline,
        "metric_deltas": metric_deltas,
        "regression_detected": bool(new_failures or degraded),
    }


def compare_campaigns(db: Session, baseline: Campaign, candidate: Campaign) -> dict:
    """Regression view across two campaigns, matched by evaluation."""
    baseline_runs = {
        r.evaluation_id: r
        for r in db.execute(select(Run).where(Run.campaign_id == baseline.id)).scalars()
    }
    candidate_runs = list(
        db.execute(select(Run).where(Run.campaign_id == candidate.id)).scalars()
    )

    comparisons, totals = [], {"new_failures": 0, "resolved": 0, "degraded": 0, "improved": 0}
    for run in candidate_runs:
        baseline_run = baseline_runs.get(run.evaluation_id)
        if baseline_run is None:
            comparisons.append(
                {
                    "evaluation_id": run.evaluation_id,
                    "status": "no_baseline",
                    "note": "This evaluation has no counterpart in the baseline campaign.",
                }
            )
            continue
        evaluation = db.get(Evaluation, run.evaluation_id)
        diff = compare_runs(db, baseline_run, run)
        totals["new_failures"] += len(diff["new_failures"])
        totals["resolved"] += len(diff["resolved_failures"])
        totals["degraded"] += len(diff["degraded"])
        totals["improved"] += len(diff["improved"])
        comparisons.append(
            {
                "evaluation_id": run.evaluation_id,
                "evaluation_key": evaluation.key if evaluation else None,
                "evaluation_name": evaluation.name if evaluation else None,
                "domain": evaluation.domain if evaluation else None,
                "baseline_verdict": baseline_run.verdict,
                "candidate_verdict": run.verdict,
                **diff,
            }
        )

    return {
        "baseline_campaign": {"id": baseline.id, "name": baseline.name},
        "candidate_campaign": {"id": candidate.id, "name": candidate.name},
        "totals": totals,
        "regression_detected": totals["new_failures"] > 0 or totals["degraded"] > 0,
        "comparisons": comparisons,
    }


def _result_key(result: Result) -> str:
    if result.scenario is not None:
        return f"{result.scenario.key}#{result.repetition}"
    return f"{result.dataset_item_id}#{result.repetition}"


_RANK = {
    ResultStatus.PASS: 0,
    ResultStatus.NOT_EVALUATED: 1,
    ResultStatus.PENDING_HUMAN: 2,
    ResultStatus.WARNING: 3,
    ResultStatus.ERROR: 4,
    ResultStatus.FAIL: 5,
}


def _rank(status: str) -> int:
    return _RANK.get(status, 1)
