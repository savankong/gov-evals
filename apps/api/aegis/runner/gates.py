"""Deployment gates (section 34).

Every criterion is supplied by the customer's evaluation plan. The engine
evaluates criteria; it never supplies one, and an unmeasurable criterion
reports NOT EVALUATED rather than passing by default.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import FindingStatus, ResultStatus, Severity
from ..models import Campaign, Evaluation, Finding, Gate, GateCheck, Run


def evaluate_gate(db: Session, gate: Gate, campaign: Campaign) -> GateCheck:
    runs = list(db.execute(select(Run).where(Run.campaign_id == campaign.id)).scalars())
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.project_id == campaign.project_id,
                Finding.status.in_(FindingStatus.ACTIVE),
            )
        ).scalars()
    )

    outcomes = [
        _evaluate_criterion(db, criterion, runs, findings) for criterion in gate.criteria or []
    ]

    if any(o["status"] == ResultStatus.FAIL for o in outcomes):
        status = ResultStatus.FAIL
    elif any(o["status"] == ResultStatus.NOT_EVALUATED for o in outcomes):
        # A gate with an unmeasured criterion is not passed. It is undetermined.
        status = ResultStatus.NOT_EVALUATED
    elif any(o["status"] == ResultStatus.WARNING for o in outcomes):
        status = ResultStatus.WARNING
    elif outcomes:
        status = ResultStatus.PASS
    else:
        status = ResultStatus.NOT_EVALUATED

    check = GateCheck(
        gate_id=gate.id,
        campaign_id=campaign.id,
        system_version_id=runs[0].system_version_id if runs else None,
        status=status,
        criteria_results=outcomes,
    )
    db.add(check)
    db.flush()
    return check


def _evaluate_criterion(db: Session, criterion: dict, runs: list[Run], findings: list[Finding]) -> dict:
    kind = criterion.get("type")
    label = criterion.get("label") or kind
    base = {"type": kind, "label": label, "criterion": criterion}

    if kind == "evaluation_verdict":
        key = criterion.get("evaluation_key")
        matched = [r for r in runs if _evaluation_key(db, r) == key]
        if not matched:
            return {**base, "status": ResultStatus.NOT_EVALUATED,
                    "detail": f"Evaluation '{key}' did not run in this campaign."}
        required = criterion.get("required_verdict", ResultStatus.PASS)
        actual = [r.verdict for r in matched]
        ok = all(v == required for v in actual)
        undetermined = any(v == ResultStatus.NOT_EVALUATED for v in actual)
        return {
            **base,
            "status": ResultStatus.NOT_EVALUATED if undetermined else (ResultStatus.PASS if ok else ResultStatus.FAIL),
            "detail": f"Verdicts: {actual}; gate requires '{required}'.",
        }

    if kind == "metric_threshold":
        key = criterion.get("evaluation_key")
        metric = criterion.get("metric", "pass_rate")
        matched = [r for r in runs if _evaluation_key(db, r) == key]
        if not matched:
            return {**base, "status": ResultStatus.NOT_EVALUATED,
                    "detail": f"Evaluation '{key}' did not run in this campaign."}
        values = [_metric(r.metrics or {}, metric) for r in matched]
        values = [v for v in values if v is not None]
        if not values:
            return {**base, "status": ResultStatus.NOT_EVALUATED,
                    "detail": f"Metric '{metric}' was not measured."}
        worst = min(values) if "min" in criterion else max(values)
        if "min" in criterion:
            ok = worst >= float(criterion["min"])
            detail = f"Measured {worst}; gate requires at least {criterion['min']}."
        else:
            ok = worst <= float(criterion["max"])
            detail = f"Measured {worst}; gate allows at most {criterion['max']}."
        return {**base, "status": ResultStatus.PASS if ok else ResultStatus.FAIL,
                "detail": detail, "measured": worst}

    if kind == "no_findings_at_or_above":
        severity = criterion.get("severity", Severity.CRITICAL)
        floor = Severity.ORDER.get(severity, 0)
        domain = criterion.get("domain")
        blocking = [
            f for f in findings
            if Severity.ORDER.get(f.severity, 9) <= floor and (not domain or f.domain == domain)
        ]
        return {
            **base,
            "status": ResultStatus.PASS if not blocking else ResultStatus.FAIL,
            "detail": (
                f"No unresolved findings at {severity} or above."
                if not blocking
                else f"{len(blocking)} unresolved finding(s) at {severity} or above: "
                + ", ".join(f.key for f in blocking[:5])
            ),
            "finding_keys": [f.key for f in blocking],
        }

    if kind == "regression_clean":
        # Requires a baseline; without one there is nothing to compare against.
        baseline_id = criterion.get("baseline_campaign_id")
        if not baseline_id:
            return {**base, "status": ResultStatus.NOT_EVALUATED,
                    "detail": "No baseline campaign configured for regression comparison."}
        from .comparison import compare_campaigns

        baseline = db.get(Campaign, baseline_id)
        candidate = db.get(Campaign, runs[0].campaign_id) if runs else None
        if baseline is None or candidate is None:
            return {**base, "status": ResultStatus.NOT_EVALUATED, "detail": "Campaign not found."}
        diff = compare_campaigns(db, baseline, candidate)
        ok = not diff["regression_detected"]
        return {
            **base,
            "status": ResultStatus.PASS if ok else ResultStatus.FAIL,
            "detail": (
                "No new failures or degradations against the baseline."
                if ok
                else f"{diff['totals']['new_failures']} new failure(s), "
                f"{diff['totals']['degraded']} degradation(s)."
            ),
        }

    if kind == "human_review_complete":
        outstanding = sum(r.pending_human for r in runs)
        return {
            **base,
            "status": ResultStatus.PASS if outstanding == 0 else ResultStatus.FAIL,
            "detail": (
                "All required human reviews are complete."
                if outstanding == 0
                else f"{outstanding} result(s) still awaiting human review."
            ),
        }

    return {**base, "status": ResultStatus.NOT_EVALUATED,
            "detail": f"Unrecognised criterion type '{kind}'."}


def _evaluation_key(db: Session, run: Run) -> str | None:
    evaluation = db.get(Evaluation, run.evaluation_id)
    return evaluation.key if evaluation else None


def _metric(metrics: dict, path: str):
    current = metrics
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current if isinstance(current, (int, float)) else None
