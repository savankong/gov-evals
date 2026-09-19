"""Findings and risks (sections 27, 28)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..enums import FindingStatus, ResultStatus, Severity
from ..models import Finding, Organization, Result, Risk, Run, User, utcnow
from ..schemas import (
    FindingIn,
    FindingOut,
    FindingUpdate,
    RiskAcceptIn,
    RiskIn,
    RiskOut,
    RiskUpdate,
)
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["findings"])

# Fallback scale used only when an organization has not defined its own.
# Section 28: risk scoring belongs to the customer.
DEFAULT_PROBABILITY = {"remote": 1, "unlikely": 2, "likely": 3, "highly_likely": 4, "near_certain": 5}
DEFAULT_CONSEQUENCE = {"negligible": 1, "minor": 2, "moderate": 3, "significant": 4, "severe": 5}
DEFAULT_BANDS = [(20, Severity.CRITICAL), (12, Severity.HIGH), (6, Severity.MEDIUM), (3, Severity.LOW)]


def _score_risk(org: Organization | None, probability: str | None, consequence: str | None):
    """Score against the organization's matrix, falling back to the shipped scale."""
    matrix = (org.risk_scoring or {}) if org else {}
    probabilities = matrix.get("probability") or DEFAULT_PROBABILITY
    consequences = matrix.get("consequence") or DEFAULT_CONSEQUENCE
    bands = matrix.get("bands") or DEFAULT_BANDS

    if not probability or not consequence:
        return None, None
    p = probabilities.get(probability)
    c = consequences.get(consequence)
    if p is None or c is None:
        return None, None
    score = float(p) * float(c)
    for floor, severity in sorted(
        ((tuple(b) if isinstance(b, list) else b) for b in bands), key=lambda b: -b[0]
    ):
        if score >= floor:
            return score, severity
    return score, Severity.INFO


@router.get("/projects/{project_id}/findings", response_model=list[FindingOut])
def list_findings(
    project_id: str,
    severity: str | None = None,
    finding_status: str | None = None,
    domain: str | None = None,
    cluster: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Finding).where(Finding.project_id == project_id)
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    if finding_status:
        stmt = stmt.where(Finding.status == finding_status)
    if domain:
        stmt = stmt.where(Finding.domain == domain)
    if cluster:
        stmt = stmt.where(Finding.cluster_key == cluster)
    findings = list(db.execute(stmt).scalars())
    return sorted(findings, key=lambda f: (Severity.ORDER.get(f.severity, 9), f.key))


@router.get("/projects/{project_id}/findings/clusters")
def finding_clusters(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Group findings by failure mode so a reviewer sees patterns, not a list."""
    findings = list(db.execute(select(Finding).where(Finding.project_id == project_id)).scalars())
    clusters: dict[str, dict] = {}
    for finding in findings:
        key = finding.cluster_key or "unclustered"
        bucket = clusters.setdefault(
            key,
            {"cluster_key": key, "count": 0, "severities": {}, "domains": set(), "finding_keys": [],
             "active": 0},
        )
        bucket["count"] += 1
        bucket["severities"][finding.severity] = bucket["severities"].get(finding.severity, 0) + 1
        if finding.domain:
            bucket["domains"].add(finding.domain)
        bucket["finding_keys"].append(finding.key)
        if finding.status in FindingStatus.ACTIVE:
            bucket["active"] += 1
    return {
        "clusters": sorted(
            ({**c, "domains": sorted(c["domains"])} for c in clusters.values()),
            key=lambda c: -c["count"],
        )
    }


@router.post("/projects/{project_id}/findings", response_model=FindingOut, status_code=201)
def create_finding(
    project_id: str,
    payload: FindingIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.FINDING_WRITE)),
):
    project = get_project(db, project_id)
    count = len(list(db.execute(select(Finding.id).where(Finding.project_id == project_id)).scalars()))
    finding = Finding(project_id=project_id, key=f"F-{count + 1:04d}", **payload.model_dump())
    db.add(finding)
    db.flush()
    audit.record(
        db, action="finding.created", object_type="finding", object_id=finding.id,
        detail={"key": finding.key, "severity": finding.severity},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.get("/findings/{finding_id}")
def read_finding(finding_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """A finding with the results that produced it (section 76 in API form)."""
    finding = fetch(db, Finding, finding_id, "Finding")
    results = []
    for result_id in (finding.result_ids or [])[:20]:
        result = db.get(Result, result_id)
        if result is None:
            continue
        results.append(
            {
                "id": result.id,
                "status": result.status,
                "scenario_key": result.scenario.key if result.scenario else None,
                "scenario_title": result.scenario.title if result.scenario else None,
                "prompt": (result.request or {}).get("prompt", "")[:1200],
                "documents": (result.request or {}).get("documents", []),
                "output": (result.response or {}).get("text", "")[:2000],
                "judgements": result.judgements,
                "trace": result.trace,
                "content_hash": result.content_hash,
            }
        )
    run = db.get(Run, finding.run_id) if finding.run_id else None
    return {
        "finding": FindingOut.model_validate(finding).model_dump(),
        "results": results,
        "reproducibility": run.reproducibility if run else {},
        "linked_risks": [
            {"id": r.id, "key": r.key, "title": r.title, "status": r.status}
            for r in db.execute(select(Risk).where(Risk.project_id == finding.project_id)).scalars()
            if finding.id in (r.finding_ids or [])
        ],
    }


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: str,
    payload: FindingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.FINDING_WRITE)),
):
    finding = fetch(db, Finding, finding_id, "Finding")
    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if getattr(finding, field) != value:
            changes[field] = {"from": getattr(finding, field), "to": value}
            setattr(finding, field, value)
    if changes:
        audit.record(
            db,
            action="finding.updated",
            object_type="finding",
            object_id=finding.id,
            project_id=finding.project_id,
            actor_id=user.id,
            actor_label=user.email,
            detail={"key": finding.key, "changes": changes},
        )
    db.commit()
    db.refresh(finding)
    return finding


@router.post("/findings/{finding_id}/retest", response_model=FindingOut)
def record_retest(
    finding_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.FINDING_WRITE)),
):
    """Attach a retest run and read its verdict back onto the finding."""
    finding = fetch(db, Finding, finding_id, "Finding")
    run = fetch(db, Run, run_id, "Run")
    finding.retest_run_id = run.id
    finding.retest_status = run.verdict
    if run.verdict == ResultStatus.PASS:
        finding.status = FindingStatus.RESOLVED
    elif run.verdict == ResultStatus.FAIL:
        finding.status = FindingStatus.MITIGATING
    audit.record(
        db,
        action="finding.retested",
        object_type="finding",
        object_id=finding.id,
        project_id=finding.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"run_id": run.id, "verdict": run.verdict, "finding_status": finding.status},
    )
    db.commit()
    db.refresh(finding)
    return finding


# -- risks ------------------------------------------------------------------


@router.get("/projects/{project_id}/risks", response_model=list[RiskOut])
def list_risks(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(select(Risk).where(Risk.project_id == project_id).order_by(Risk.key)).scalars()
    )


@router.post("/projects/{project_id}/risks", response_model=RiskOut, status_code=201)
def create_risk(
    project_id: str,
    payload: RiskIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.FINDING_WRITE)),
):
    project = get_project(db, project_id)
    org = project.program.organization if project.program else None
    count = len(list(db.execute(select(Risk.id).where(Risk.project_id == project_id)).scalars()))

    risk = Risk(project_id=project_id, key=f"R-{count + 1:04d}", **payload.model_dump())
    risk.score, risk.severity = _score_risk(org, risk.probability, risk.consequence)
    risk.evidence_refs = [{"type": "finding", "id": fid} for fid in (risk.finding_ids or [])]
    db.add(risk)
    db.flush()
    audit.record(
        db, action="risk.created", object_type="risk", object_id=risk.id,
        detail={"key": risk.key, "severity": risk.severity, "score": risk.score},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(risk)
    return risk


@router.patch("/risks/{risk_id}", response_model=RiskOut)
def update_risk(
    risk_id: str,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.FINDING_WRITE)),
):
    risk = fetch(db, Risk, risk_id, "Risk")
    project = risk.project if hasattr(risk, "project") else None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(risk, field, value)

    from ..models import Project

    project = db.get(Project, risk.project_id)
    org = project.program.organization if project and project.program else None
    risk.score, risk.severity = _score_risk(org, risk.probability, risk.consequence)
    if risk.residual_probability and risk.residual_consequence:
        _, risk.residual_severity = _score_risk(
            org, risk.residual_probability, risk.residual_consequence
        )
    audit.record(
        db,
        action="risk.updated",
        object_type="risk",
        object_id=risk.id,
        project_id=risk.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"key": risk.key, "severity": risk.severity},
    )
    db.commit()
    db.refresh(risk)
    return risk


@router.post("/risks/{risk_id}/accept", response_model=RiskOut)
def accept_risk(
    risk_id: str,
    payload: RiskAcceptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.RISK_ACCEPT)),
):
    """Record a risk acceptance.

    Acceptance is an authority's decision, recorded here with the name of that
    authority. The platform does not accept risk on anyone's behalf.
    """
    risk = fetch(db, Risk, risk_id, "Risk")
    if not risk.residual_severity and not payload.residual_risk_statement:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Record the residual risk before accepting it: set residual probability and "
            "consequence, or supply a residual risk statement.",
        )
    risk.status = "accepted"
    risk.acceptance_authority = payload.acceptance_authority
    risk.accepted_at = utcnow()
    if payload.residual_risk_statement:
        risk.description = (risk.description or "") + (
            f"\n\nResidual risk accepted: {payload.residual_risk_statement}"
        )
    audit.record(
        db,
        action="risk.accepted",
        object_type="risk",
        object_id=risk.id,
        project_id=risk.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={
            "key": risk.key,
            "acceptance_authority": payload.acceptance_authority,
            "residual_severity": risk.residual_severity,
            "recorded_by": user.email,
        },
    )
    db.commit()
    db.refresh(risk)
    return risk
