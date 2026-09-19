"""Dashboards and mission readiness (sections 35, 75).

There is no overall trust score anywhere in this module, by design. Readiness is
reported per dimension, each dimension drills into the runs behind it, and an
untested dimension reports NOT EVALUATED (sections 70, 71).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..enums import Domain, FindingStatus, ResultStatus, RunStatus, Severity
from ..models import (
    AssuranceCase,
    Campaign,
    Dataset,
    Evaluation,
    Finding,
    Membership,
    MissionProfile,
    Program,
    Project,
    Risk,
    Run,
    Scenario,
    System,
    SystemVersion,
    User,
)
from ..runner.comparison import compare_campaigns
from ..runner.engine import _domain_status
from ..security import get_current_user
from .deps import get_project

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Portfolio view across every project the caller can see."""
    org_ids = {
        m.organization_id
        for m in db.execute(select(Membership).where(Membership.user_id == user.id)).scalars()
    }
    projects = list(
        db.execute(
            select(Project).join(Program).where(Program.organization_id.in_(org_ids or [""]))
        ).scalars()
    )
    project_ids = [p.id for p in projects] or [""]

    systems = list(db.execute(select(System).where(System.project_id.in_(project_ids))).scalars())
    campaigns = list(
        db.execute(select(Campaign).where(Campaign.project_id.in_(project_ids))).scalars()
    )
    findings = list(
        db.execute(select(Finding).where(Finding.project_id.in_(project_ids))).scalars()
    )
    risks = list(db.execute(select(Risk).where(Risk.project_id.in_(project_ids))).scalars())
    runs = list(
        db.execute(select(Run).where(Run.campaign_id.in_([c.id for c in campaigns] or [""]))).scalars()
    )
    cases = list(
        db.execute(select(AssuranceCase).where(AssuranceCase.project_id.in_(project_ids))).scalars()
    )

    # North star (section 63): projects whose evidence chain is complete enough
    # to support their claims -- mission profile, executed evaluations, an
    # assurance case, and no unresolved critical finding.
    traceable = 0
    for project in projects:
        mission = db.execute(
            select(MissionProfile).where(MissionProfile.project_id == project.id)
        ).scalar_one_or_none()
        project_runs = [
            r for r in runs
            if r.campaign_id in {c.id for c in campaigns if c.project_id == project.id}
        ]
        project_cases = [c for c in cases if c.project_id == project.id]
        critical_open = [
            f for f in findings
            if f.project_id == project.id
            and f.severity == Severity.CRITICAL
            and f.status in FindingStatus.ACTIVE
        ]
        if mission and project_runs and project_cases and not critical_open:
            traceable += 1

    return {
        "counts": {
            "projects": len(projects),
            "systems": len(systems),
            "evaluations_available": len(
                list(db.execute(select(Evaluation).where(Evaluation.project_id.is_(None))).scalars())
            ),
            "campaigns": len(campaigns),
            "active_campaigns": sum(
                1 for c in campaigns if c.status in (RunStatus.QUEUED, RunStatus.RUNNING)
            ),
            "executions": sum(r.scenario_count for r in runs),
            "failures": sum(r.failed for r in runs),
            "awaiting_human_review": sum(r.pending_human for r in runs),
        },
        "findings": {
            severity: sum(
                1 for f in findings if f.severity == severity and f.status in FindingStatus.ACTIVE
            )
            for severity in Severity.ALL
        },
        "risks": {
            "total": len(risks),
            "accepted": sum(1 for r in risks if r.status == "accepted"),
            "open": sum(1 for r in risks if r.status not in ("accepted", "closed")),
        },
        "evidence_coverage": {
            "projects_with_complete_chain": traceable,
            "projects": len(projects),
            "ratio": round(traceable / len(projects), 3) if projects else None,
            "definition": (
                "A project counts when it has a mission profile, executed evaluations, an "
                "assurance case, and no unresolved critical finding."
            ),
        },
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "classification": p.classification,
                "impact_level": p.impact_level,
                "status": p.status,
                "open_findings": sum(
                    1 for f in findings if f.project_id == p.id and f.status in FindingStatus.ACTIVE
                ),
                "critical_findings": sum(
                    1
                    for f in findings
                    if f.project_id == p.id
                    and f.severity == Severity.CRITICAL
                    and f.status in FindingStatus.ACTIVE
                ),
            }
            for p in projects
        ],
    }


@router.get("/projects/{project_id}/dashboard")
def project_dashboard(
    project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    """The project screen in section 75, computed from stored records."""
    project = get_project(db, project_id)
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    systems = list(db.execute(select(System).where(System.project_id == project_id)).scalars())
    campaigns = list(
        db.execute(
            select(Campaign).where(Campaign.project_id == project_id).order_by(Campaign.created_at.desc())
        ).scalars()
    )
    latest = campaigns[0] if campaigns else None
    runs = (
        list(db.execute(select(Run).where(Run.campaign_id == latest.id)).scalars()) if latest else []
    )
    findings = list(db.execute(select(Finding).where(Finding.project_id == project_id)).scalars())

    # Readiness by dimension. Every domain appears, including untested ones.
    by_domain: dict[str, list[Run]] = {}
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if evaluation:
            by_domain.setdefault(evaluation.domain, []).append(run)

    readiness = []
    for domain in Domain.ALL:
        domain_runs = by_domain.get(domain, [])
        scoreable = sum(r.passed + r.warned + r.failed for r in domain_runs)
        passed = sum(r.passed for r in domain_runs)
        readiness.append(
            {
                "domain": domain,
                "label": Domain.LABELS[domain],
                "status": _domain_status([r.verdict for r in domain_runs]),
                "evaluations": len(domain_runs),
                "executions": sum(r.scenario_count for r in domain_runs),
                "passed": passed,
                "failed": sum(r.failed for r in domain_runs),
                "warning": sum(r.warned for r in domain_runs),
                "pending_human": sum(r.pending_human for r in domain_runs),
                # Reported alongside the status, never in place of it.
                "pass_rate": round(passed / scoreable, 4) if scoreable else None,
                "run_ids": [r.id for r in domain_runs],
            }
        )

    # Regression against the previous campaign, when there is one.
    regression = None
    if latest and len(campaigns) > 1:
        baseline_id = latest.baseline_campaign_id or campaigns[1].id
        baseline = db.get(Campaign, baseline_id)
        if baseline and baseline.id != latest.id:
            diff = compare_campaigns(db, baseline, latest)
            regression = {
                "baseline_campaign": diff["baseline_campaign"],
                "candidate_campaign": diff["candidate_campaign"],
                "totals": diff["totals"],
                "regression_detected": diff["regression_detected"],
            }

    current_versions = []
    for system in systems:
        for version in system.versions:
            if version.is_current:
                current_versions.append(
                    {
                        "system": system.name,
                        "system_id": system.id,
                        "kind": system.kind,
                        "version_id": version.id,
                        "version": version.version,
                        "model_name": version.model_name,
                        "model_provider": version.model_provider,
                        "connector": version.connector_type,
                        "config_hash": version.config_hash,
                    }
                )

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "classification": project.classification,
            "impact_level": project.impact_level,
            "deployment_environment": project.deployment_environment,
            "system_owner": project.system_owner,
            "evaluation_owner": project.evaluation_owner,
        },
        "mission": {
            "mission": mission.mission,
            "tasks": mission.tasks,
            "users": mission.users,
            "unacceptable_failures": mission.unacceptable_failures,
            "latency_requirement_ms": mission.latency_requirement_ms,
        }
        if mission
        else None,
        "systems": current_versions,
        "latest_campaign": {
            "id": latest.id,
            "name": latest.name,
            "status": latest.status,
            "trigger": latest.trigger,
            "summary": latest.summary,
            "completed_at": latest.completed_at,
        }
        if latest
        else None,
        "readiness": readiness,
        "findings": {
            severity: sum(
                1 for f in findings if f.severity == severity and f.status in FindingStatus.ACTIVE
            )
            for severity in Severity.ALL
        },
        "findings_total": len(findings),
        "regression": regression,
        "inventory": {
            "scenarios": len(
                list(
                    db.execute(
                        select(Scenario).where(
                            (Scenario.project_id == project_id) | (Scenario.project_id.is_(None))
                        )
                    ).scalars()
                )
            ),
            "scenarios_awaiting_approval": len(
                list(
                    db.execute(
                        select(Scenario).where(
                            Scenario.project_id == project_id, Scenario.approved.is_(False)
                        )
                    ).scalars()
                )
            ),
            "datasets": len(
                list(db.execute(select(Dataset).where(Dataset.project_id == project_id)).scalars())
            ),
            "campaigns": len(campaigns),
        },
        "note": (
            "Readiness is reported per dimension. There is no single trust score: a dimension "
            "marked NOT EVALUATED has not been tested and is not an implied pass."
        ),
    }


@router.get("/projects/{project_id}/framework-coverage")
def framework_coverage(
    project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    """Which framework references have evidence, and what that evidence is (section 37)."""
    from ..models import FrameworkRequirement

    get_project(db, project_id)
    campaigns = list(db.execute(select(Campaign).where(Campaign.project_id == project_id)).scalars())
    runs = list(
        db.execute(select(Run).where(Run.campaign_id.in_([c.id for c in campaigns] or [""]))).scalars()
    )

    evidence: dict[str, list[dict]] = {}
    for run in runs:
        evaluation = db.get(Evaluation, run.evaluation_id)
        if not evaluation:
            continue
        for ref in evaluation.framework_refs or []:
            evidence.setdefault(ref, []).append(
                {
                    "run_id": run.id,
                    "evaluation_key": evaluation.key,
                    "evaluation_name": evaluation.name,
                    "verdict": run.verdict,
                    "executions": run.scenario_count,
                    "passed": run.passed,
                    "failed": run.failed,
                }
            )

    requirements = list(db.execute(select(FrameworkRequirement)).scalars())
    rows = []
    for requirement in requirements:
        linked = evidence.get(requirement.ref, [])
        if linked:
            verdicts = [e["verdict"] for e in linked]
            status = _domain_status(verdicts)
        else:
            status = ResultStatus.NOT_EVALUATED
        rows.append(
            {
                "framework": requirement.framework,
                "ref": requirement.ref,
                "title": requirement.title,
                "status": status,
                "evidence": linked,
                "compliance_claimable": requirement.compliance_claimable,
            }
        )

    covered = sum(1 for r in rows if r["status"] != ResultStatus.NOT_EVALUATED)
    return {
        "rows": sorted(rows, key=lambda r: (r["framework"], r["ref"])),
        "summary": {"references": len(rows), "with_evidence": covered},
        "note": (
            "A row with evidence shows which evaluations speak to that reference and what they "
            "found. It does not assert compliance: no requirement here is marked claimable, and "
            "only a customer with authority over a requirement may change that."
        ),
    }


@router.get("/projects/{project_id}/trust-calibration")
def trust_calibration(
    project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    """AI accuracy versus operator trust (section 26).

    Each point is one review: the operator's stated confidence against whether
    the system was in fact correct. Over-reliance sits top-left, under-reliance
    bottom-right.
    """
    from ..models import HumanReview, Result

    campaigns = list(db.execute(select(Campaign).where(Campaign.project_id == project_id)).scalars())
    runs = list(
        db.execute(select(Run).where(Run.campaign_id.in_([c.id for c in campaigns] or [""]))).scalars()
    )
    results = list(
        db.execute(select(Result).where(Result.run_id.in_([r.id for r in runs] or [""]))).scalars()
    )
    reviews = list(
        db.execute(
            select(HumanReview).where(HumanReview.result_id.in_([r.id for r in results] or [""]))
        ).scalars()
    )

    by_result = {r.id: r for r in results}
    points, over, under, calibrated = [], 0, 0, 0
    for review in reviews:
        if review.confidence is None:
            continue
        result = by_result.get(review.result_id)
        if result is None:
            continue
        system_correct = result.status == ResultStatus.PASS
        points.append(
            {
                "result_id": result.id,
                "reviewer": review.reviewer_label,
                "operator_confidence": review.confidence,
                "system_correct": system_correct,
                "result_status": result.status,
            }
        )
        if not system_correct and review.confidence > 0.6:
            over += 1
        elif system_correct and review.confidence < 0.4:
            under += 1
        else:
            calibrated += 1

    return {
        "points": points,
        "summary": {
            "reviews_with_confidence": len(points),
            "over_reliance": over,
            "under_reliance": under,
            "calibrated": calibrated,
        },
        "note": (
            "Over-reliance is confident acceptance of an incorrect output. Under-reliance is "
            "doubt about a correct one. Both are human-systems findings, not model findings."
        )
        if points
        else "No human reviews carry a confidence rating yet, so calibration is NOT EVALUATED.",
    }
