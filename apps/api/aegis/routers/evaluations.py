"""Evaluation library and plan builder (sections 13, 14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..evaluators import get_evaluator
from ..hashing import content_hash
from ..models import (
    Evaluation,
    EvaluationPlan,
    EvaluationPlanItem,
    SystemVersion,
    User,
)
from ..runner.planner import coverage_report, generate_plan
from ..schemas import (
    ApprovePlanRequest,
    EvaluationIn,
    EvaluationOut,
    EvaluationPlanOut,
    GeneratePlanRequest,
    PlanItemIn,
    PlanItemOut,
)
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["evaluations"])


@router.get("/evaluations", response_model=list[EvaluationOut])
def list_library(
    layer: str | None = None,
    domain: str | None = None,
    system_type: str | None = None,
    pack: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Evaluation).where(Evaluation.project_id.is_(None))
    if layer:
        stmt = stmt.where(Evaluation.layer == layer)
    if domain:
        stmt = stmt.where(Evaluation.domain == domain)
    if pack:
        stmt = stmt.where(Evaluation.pack_key == pack)
    evaluations = list(db.execute(stmt.order_by(Evaluation.key)).scalars())
    if system_type:
        evaluations = [
            e for e in evaluations if not e.system_types or system_type in e.system_types
        ]
    return evaluations


@router.get("/projects/{project_id}/evaluations", response_model=list[EvaluationOut])
def list_project_evaluations(
    project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return list(
        db.execute(
            select(Evaluation)
            .where((Evaluation.project_id == project_id) | (Evaluation.project_id.is_(None)))
            .order_by(Evaluation.key)
        ).scalars()
    )


@router.post("/projects/{project_id}/evaluations", response_model=EvaluationOut, status_code=201)
def create_evaluation(
    project_id: str,
    payload: EvaluationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    project = get_project(db, project_id)
    for spec in payload.evaluators:
        key = spec.get("evaluator") or spec.get("key")
        try:
            get_evaluator(key)
        except KeyError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    evaluation = Evaluation(project_id=project_id, **payload.model_dump())
    evaluation.content_hash = content_hash(payload.model_dump())
    evaluation.provenance = {"author": user.email, "scope": "project"}
    db.add(evaluation)
    db.flush()
    audit.record(
        db, action="evaluation.created", object_type="evaluation", object_id=evaluation.id,
        detail={"key": evaluation.key, "evaluators": [e.get("evaluator") for e in payload.evaluators]},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(evaluation)
    return evaluation


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationOut)
def read_evaluation(evaluation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, Evaluation, evaluation_id, "Evaluation")


# -- plans ------------------------------------------------------------------


@router.get("/projects/{project_id}/plans", response_model=list[EvaluationPlanOut])
def list_plans(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(EvaluationPlan)
            .where(EvaluationPlan.project_id == project_id)
            .order_by(EvaluationPlan.created_at.desc())
        ).scalars()
    )


@router.post("/projects/{project_id}/plans/generate", response_model=EvaluationPlanOut, status_code=201)
def generate(
    project_id: str,
    payload: GeneratePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    """Draft a plan from the mission profile and system architecture."""
    project = get_project(db, project_id)
    system_version = (
        db.get(SystemVersion, payload.system_version_id) if payload.system_version_id else None
    )
    plan = generate_plan(db, project=project, system_version=system_version, name=payload.name)
    audit.record(
        db,
        action="evaluation_plan.generated",
        object_type="evaluation_plan",
        object_id=plan.id,
        detail={"items": len(plan.items), "generated_from": plan.generated_from},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/plans/{plan_id}")
def read_plan(plan_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    plan = fetch(db, EvaluationPlan, plan_id, "Evaluation plan")
    items = []
    for item in sorted(plan.items, key=lambda i: i.ordinal):
        evaluation = db.get(Evaluation, item.evaluation_id)
        items.append(
            {
                **PlanItemOut.model_validate(item).model_dump(),
                "evaluation": EvaluationOut.model_validate(evaluation).model_dump()
                if evaluation
                else None,
            }
        )
    return {
        "plan": EvaluationPlanOut.model_validate(plan).model_dump(),
        "items": items,
        "coverage": coverage_report(db, plan),
    }


@router.post("/plans/{plan_id}/items", response_model=PlanItemOut, status_code=201)
def add_plan_item(
    plan_id: str,
    payload: PlanItemIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    plan = fetch(db, EvaluationPlan, plan_id, "Evaluation plan")
    item = EvaluationPlanItem(plan_id=plan_id, **payload.model_dump())
    db.add(item)
    db.flush()
    audit.record(
        db,
        action="evaluation_plan.item_added",
        object_type="evaluation_plan",
        object_id=plan.id,
        project_id=plan.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"evaluation_id": item.evaluation_id},
    )
    db.commit()
    db.refresh(item)
    return item


@router.patch("/plan-items/{item_id}", response_model=PlanItemOut)
def update_plan_item(
    item_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    """Edit an item. Setting a threshold here is how a program adopts a passing bar."""
    item = fetch(db, EvaluationPlanItem, item_id, "Plan item")
    before = dict(item.threshold or {})
    for field in ("threshold", "rationale", "included", "ordinal", "requirement_id"):
        if field in payload:
            setattr(item, field, payload[field])
    if "threshold" in payload:
        # Clear the "unconfirmed library default" marker once a human sets it.
        threshold = dict(item.threshold or {})
        threshold.pop("source", None)
        threshold["source"] = "program_defined"
        item.threshold = threshold
        audit.record(
            db,
            action="threshold.changed",
            object_type="plan_item",
            object_id=item.id,
            project_id=item.plan.project_id if item.plan else None,
            actor_id=user.id,
            actor_label=user.email,
            detail={"from": before, "to": item.threshold},
        )
    db.commit()
    db.refresh(item)
    return item


@router.post("/plans/{plan_id}/approve", response_model=EvaluationPlanOut)
def approve_plan(
    plan_id: str,
    payload: ApprovePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    plan = fetch(db, EvaluationPlan, plan_id, "Evaluation plan")
    coverage = coverage_report(db, plan)

    if coverage["evaluations"] == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This plan contains no evaluations. Approving it would record an approval that "
            "covers nothing. Add evaluations, or install an evaluation pack first.",
        )
    if coverage["thresholds_unconfirmed"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{coverage['thresholds_unconfirmed']} evaluation(s) still carry an unconfirmed "
            "library default threshold. The program office sets the passing bar before a plan "
            "is approved.",
        )
    if coverage["evaluations_without_scenarios"]:
        names = ", ".join(
            u["evaluation_key"] for u in coverage["evaluations_without_scenarios"][:5]
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{len(coverage['evaluations_without_scenarios'])} evaluation(s) have no matching "
            f"scenario and would report NOT EVALUATED: {names}. Add scenarios, adjust the "
            "selector, or remove them from the plan before approving it.",
        )
    from ..models import utcnow

    plan.status = "approved"
    plan.approved_by = payload.approved_by
    plan.approved_at = utcnow()
    audit.record(
        db,
        action="evaluation_plan.approved",
        object_type="evaluation_plan",
        object_id=plan.id,
        project_id=plan.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"approved_by": payload.approved_by, "note": payload.note, "coverage": coverage},
    )
    db.commit()
    db.refresh(plan)
    return plan
