"""Scenario library, generation and red-team materialisation (sections 15, 17, 22)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..hashing import content_hash
from ..models import MissionProfile, Scenario, User
from ..runner import generator, redteam
from ..schemas import GenerateScenariosRequest, RedTeamRequest, ScenarioIn, ScenarioOut
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_library(
    tag: str | None = None,
    threat_type: str | None = None,
    approved: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """The shared scenario library (project-independent entries)."""
    stmt = select(Scenario).where(Scenario.project_id.is_(None))
    if threat_type:
        stmt = stmt.where(Scenario.threat_type == threat_type)
    if approved is not None:
        stmt = stmt.where(Scenario.approved.is_(approved))
    scenarios = list(db.execute(stmt.order_by(Scenario.key)).scalars())
    if tag:
        scenarios = [s for s in scenarios if tag in (s.tags or [])]
    return scenarios


@router.get("/projects/{project_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(
    project_id: str,
    include_library: bool = True,
    approved: bool | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Scenario).where(Scenario.project_id == project_id)
    if include_library:
        stmt = select(Scenario).where(
            (Scenario.project_id == project_id) | (Scenario.project_id.is_(None))
        )
    if approved is not None:
        stmt = stmt.where(Scenario.approved.is_(approved))
    scenarios = list(db.execute(stmt.order_by(Scenario.key)).scalars())
    if tag:
        scenarios = [s for s in scenarios if tag in (s.tags or [])]
    return scenarios


@router.post("/projects/{project_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(
    project_id: str,
    payload: ScenarioIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    project = get_project(db, project_id)
    scenario = Scenario(project_id=project_id, owner=user.email, **payload.model_dump())
    scenario.content_hash = content_hash(
        {"key": scenario.key, "input": scenario.input, "version": scenario.version}
    )
    db.add(scenario)
    db.flush()
    audit.record(
        db, action="scenario.created", object_type="scenario", object_id=scenario.id,
        detail={"key": scenario.key}, **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(scenario)
    return scenario


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(
    scenario_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    scenario = fetch(db, Scenario, scenario_id, "Scenario")
    editable = {
        "title", "mission", "task", "context", "input", "expected_behavior",
        "prohibited_behavior", "rubric", "reference_answer", "difficulty", "tags",
        "threat_type", "classification",
    }
    changed = {}
    for field, value in payload.items():
        if field in editable and getattr(scenario, field) != value:
            changed[field] = True
            setattr(scenario, field, value)
    if changed:
        # An edited scenario is a new version: results reference the hash they ran against.
        scenario.version = str(int(scenario.version) + 1) if scenario.version.isdigit() else scenario.version
        scenario.content_hash = content_hash(
            {"key": scenario.key, "input": scenario.input, "version": scenario.version}
        )
        audit.record(
            db, action="scenario.updated", object_type="scenario", object_id=scenario.id,
            detail={"fields": sorted(changed), "new_version": scenario.version},
            **audit_context(db, scenario.project if scenario.project_id else None, user, request),
        )
    db.commit()
    db.refresh(scenario)
    return scenario


@router.post("/scenarios/{scenario_id}/approve", response_model=ScenarioOut)
def approve_scenario(
    scenario_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    """A generated scenario runs only after a human approves it (section 17)."""
    scenario = fetch(db, Scenario, scenario_id, "Scenario")
    scenario.approved = True
    scenario.approved_by = user.email
    audit.record(
        db, action="scenario.approved", object_type="scenario", object_id=scenario.id,
        detail={"key": scenario.key, "generated": scenario.generated},
        **audit_context(db, scenario.project if scenario.project_id else None, user, request),
    )
    db.commit()
    db.refresh(scenario)
    return scenario


@router.post("/projects/{project_id}/scenarios/generate", response_model=list[ScenarioOut], status_code=201)
def generate_scenarios(
    project_id: str,
    payload: GenerateScenariosRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    """Draft additional scenarios. Everything produced stays unapproved."""
    project = get_project(db, project_id)
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This project has no mission profile. Scenario generation is driven by the mission, "
            "so define one first.",
        )

    if payload.mode == "model_assisted":
        if not payload.generator:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Model-assisted generation needs a generator connector configuration.",
            )
        try:
            drafts = generator.generate_with_model(
                db,
                project_id=project_id,
                mission=mission,
                generator_config=payload.generator,
                count=payload.count,
            )
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    else:
        drafts = generator.generate_from_mission(db, project_id=project_id, mission=mission)

    audit.record(
        db,
        action="scenarios.generated",
        object_type="project",
        object_id=project_id,
        detail={"mode": payload.mode, "count": len(drafts), "approved": False},
        **audit_context(db, project, user, request),
    )
    db.commit()
    for draft in drafts:
        db.refresh(draft)
    return drafts


@router.post("/projects/{project_id}/scenarios/red-team", response_model=list[ScenarioOut], status_code=201)
def materialize_red_team(
    project_id: str,
    payload: RedTeamRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.EVALUATION_WRITE)),
):
    """Cross the attack library with this mission's tasks (section 22)."""
    project = get_project(db, project_id)
    mission = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    tasks = payload.mission_tasks or (list(mission.tasks) if mission and mission.tasks else [])

    # Remove any previous materialisation so re-running does not duplicate keys.
    existing = db.execute(
        select(Scenario).where(
            Scenario.project_id == project_id, Scenario.source == "redteam-baseline"
        )
    ).scalars()
    for scenario in existing:
        db.delete(scenario)
    db.flush()

    scenarios = redteam.build_attack_scenarios(
        db, project_id=project_id, mission_tasks=tasks, attack_keys=payload.attack_keys or None
    )
    audit.record(
        db,
        action="red_team.materialized",
        object_type="project",
        object_id=project_id,
        detail={"scenarios": len(scenarios), "attacks": payload.attack_keys or "all"},
        **audit_context(db, project, user, request),
    )
    db.commit()
    for scenario in scenarios:
        db.refresh(scenario)
    return scenarios
