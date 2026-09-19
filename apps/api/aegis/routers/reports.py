"""Report generation, gates, continuous triggers and audit access."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..hashing import content_hash, evidence_store
from ..models import (
    AssuranceCase,
    Campaign,
    ContinuousTrigger,
    EvaluationPlan,
    Gate,
    GateCheck,
    Report,
    User,
    utcnow,
)
from ..reports import (
    REPORT_KINDS,
    assurance_case_report,
    comparison_report,
    evaluation_plan_report,
    executive_report,
    findings_report,
)
from ..runner.comparison import compare_campaign
from ..runner.gates import evaluate_gate
from ..schemas import (
    AuditEventOut,
    GateIn,
    GateOut,
    ReportOut,
    ReportRequest,
    TriggerIn,
    TriggerOut,
)
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["reports"])


@router.get("/report-kinds")
def report_kinds(_: User = Depends(get_current_user)) -> dict:
    return {"kinds": [{"key": k, "label": v} for k, v in REPORT_KINDS.items()]}


@router.get("/projects/{project_id}/reports", response_model=list[ReportOut])
def list_reports(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())
        ).scalars()
    )


@router.post("/projects/{project_id}/reports", response_model=ReportOut, status_code=201)
def generate_report(
    project_id: str,
    payload: ReportRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.REPORT_GENERATE)),
):
    project = get_project(db, project_id)

    if payload.kind == "executive_summary":
        campaign = db.get(Campaign, payload.campaign_id) if payload.campaign_id else None
        body = executive_report(db, project, campaign)
        scope = {"campaign_id": campaign.id if campaign else None}
    elif payload.kind == "evaluation_plan":
        if not payload.plan_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "plan_id is required for this report")
        plan = fetch(db, EvaluationPlan, payload.plan_id, "Evaluation plan")
        body = evaluation_plan_report(db, project, plan)
        scope = {"plan_id": plan.id}
    elif payload.kind == "findings":
        body = findings_report(db, project)
        scope = {}
    elif payload.kind == "comparison":
        if not payload.campaign_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "campaign_id is required for this report")
        campaign = fetch(db, Campaign, payload.campaign_id, "Campaign")
        body = comparison_report(db, project, compare_campaign(db, campaign))
        scope = {"campaign_id": campaign.id}
    elif payload.kind == "assurance_case":
        if not payload.assurance_case_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "assurance_case_id is required for this report"
            )
        case = fetch(db, AssuranceCase, payload.assurance_case_id, "Assurance case")
        body = assurance_case_report(db, project, case)
        scope = {"assurance_case_id": case.id}
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown report kind '{payload.kind}'. Known: {sorted(REPORT_KINDS)}",
        )

    digest = content_hash(body)
    stored = evidence_store().put(
        f"reports/{project_id}/{payload.kind}-{digest[:12]}.md", body.encode("utf-8"), "text/markdown"
    )

    report = Report(
        project_id=project_id,
        kind=payload.kind,
        title=payload.title or REPORT_KINDS.get(payload.kind, payload.kind),
        format="markdown",
        scope=scope,
        body=body,
        storage_uri=stored["storage_uri"],
        sha256=stored["sha256"],
        classification=project.classification,
        generated_by=user.email,
    )
    db.add(report)
    db.flush()
    audit.record(
        db, action="report.generated", object_type="report", object_id=report.id,
        detail={"kind": report.kind, "sha256": report.sha256, "scope": scope},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports/{report_id}/download")
def download_report(report_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    report = fetch(db, Report, report_id, "Report")
    filename = f"{report.kind}-{report.id[:8]}.md"
    return Response(
        content=report.body,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-SHA256": report.sha256,
            "X-Classification": report.classification,
        },
    )


# -- gates ------------------------------------------------------------------


@router.get("/projects/{project_id}/gates", response_model=list[GateOut])
def list_gates(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(db.execute(select(Gate).where(Gate.project_id == project_id)).scalars())


@router.post("/projects/{project_id}/gates", response_model=GateOut, status_code=201)
def create_gate(
    project_id: str,
    payload: GateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.PROJECT_WRITE)),
):
    """Define a deployment gate. Criteria always come from the customer."""
    project = get_project(db, project_id)
    gate = Gate(project_id=project_id, **payload.model_dump())
    gate.defined_by = gate.defined_by or user.email
    db.add(gate)
    db.flush()
    audit.record(
        db, action="gate.created", object_type="gate", object_id=gate.id,
        detail={"name": gate.name, "criteria": gate.criteria, "defined_by": gate.defined_by},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(gate)
    return gate


@router.post("/gates/{gate_id}/check")
def check_gate(
    gate_id: str,
    campaign_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.CAMPAIGN_EXECUTE)),
):
    gate = fetch(db, Gate, gate_id, "Gate")
    campaign = fetch(db, Campaign, campaign_id, "Campaign")
    check = evaluate_gate(db, gate, campaign)
    audit.record(
        db,
        action="gate.checked",
        object_type="gate",
        object_id=gate.id,
        project_id=gate.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"campaign_id": campaign_id, "status": check.status},
    )
    db.commit()
    return {
        "gate": {"id": gate.id, "name": gate.name, "environment": gate.environment},
        "status": check.status,
        "criteria_results": check.criteria_results,
        "evaluated_at": check.evaluated_at,
        "note": (
            "A gate with an unmeasured criterion reports NOT EVALUATED. It is not a pass."
        ),
    }


@router.get("/gates/{gate_id}/checks")
def gate_history(gate_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    checks = list(
        db.execute(
            select(GateCheck).where(GateCheck.gate_id == gate_id).order_by(GateCheck.evaluated_at.desc())
        ).scalars()
    )
    return {
        "checks": [
            {
                "id": c.id,
                "campaign_id": c.campaign_id,
                "status": c.status,
                "criteria_results": c.criteria_results,
                "evaluated_at": c.evaluated_at,
            }
            for c in checks
        ]
    }


# -- continuous evaluation triggers ----------------------------------------


@router.get("/projects/{project_id}/triggers", response_model=list[TriggerOut])
def list_triggers(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(select(ContinuousTrigger).where(ContinuousTrigger.project_id == project_id)).scalars()
    )


@router.post("/projects/{project_id}/triggers", response_model=TriggerOut, status_code=201)
def create_trigger(
    project_id: str,
    payload: TriggerIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.PROJECT_WRITE)),
):
    project = get_project(db, project_id)
    trigger = ContinuousTrigger(project_id=project_id, **payload.model_dump())
    db.add(trigger)
    db.flush()
    audit.record(
        db, action="continuous_trigger.created", object_type="continuous_trigger",
        object_id=trigger.id, detail={"event": trigger.event, "name": trigger.name},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(trigger)
    return trigger


@router.post("/triggers/{trigger_id}/fire")
def fire_trigger(
    trigger_id: str,
    system_version_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.CAMPAIGN_EXECUTE)),
):
    """Fire a continuous-evaluation trigger (section 33).

    Creates a campaign from the trigger's plan or evaluation keys, links the
    previous campaign as its baseline so the regression view works immediately,
    and queues it.
    """
    from ..runner import get_queue
    from ..schemas import CampaignIn
    from .campaigns import create_campaign

    trigger = fetch(db, ContinuousTrigger, trigger_id, "Trigger")
    if not trigger.enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trigger is disabled")

    previous = db.execute(
        select(Campaign)
        .where(Campaign.project_id == trigger.project_id)
        .order_by(Campaign.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    payload = CampaignIn(
        name=f"{trigger.name} — {utcnow().strftime('%Y-%m-%d %H:%M')}",
        description=f"Fired by continuous trigger on event '{trigger.event}'.",
        kind="continuous",
        plan_id=trigger.plan_id,
        evaluation_keys=trigger.evaluation_keys or [],
        system_version_ids=[system_version_id],
        baseline_campaign_id=previous.id if previous else None,
        trigger=trigger.event,
        trigger_detail={"trigger_id": trigger.id},
    )
    campaign = create_campaign(trigger.project_id, payload, request, db, user)
    trigger.last_fired_at = utcnow()
    db.commit()

    get_queue().enqueue(campaign.id, None)
    return {
        "campaign_id": campaign.id,
        "status": "queued",
        "baseline_campaign_id": campaign.baseline_campaign_id,
    }


# -- audit ------------------------------------------------------------------


@router.get("/projects/{project_id}/audit", response_model=list[AuditEventOut])
def project_audit(
    project_id: str,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from ..models import AuditEvent

    stmt = select(AuditEvent).where(AuditEvent.project_id == project_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    return list(
        db.execute(
            stmt.order_by(AuditEvent.sequence.desc()).offset(offset).limit(min(limit, 500))
        ).scalars()
    )


@router.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db), _: User = Depends(require(Permission.ORG_ADMINISTER))):
    """Recompute the audit hash chain and report any break."""
    result = audit.verify_chain(db)
    return {
        **result,
        "note": (
            "Each event stores the digest of the previous event. A break means a record was "
            "altered or removed after it was written."
        ),
    }
