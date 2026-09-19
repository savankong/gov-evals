"""Organizations, programs, projects, mission profiles, requirements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..classification import enforce as enforce_classification
from ..db import get_db
from ..models import (
    Membership,
    MissionProfile,
    Organization,
    Program,
    Project,
    Requirement,
    User,
)
from ..schemas import (
    MissionProfileIn,
    MissionProfileOut,
    OrganizationIn,
    OrganizationOut,
    ProgramIn,
    ProgramOut,
    ProjectIn,
    ProjectOut,
    RequirementIn,
    RequirementOut,
)
from ..security import Permission, ensure_role_definitions, get_current_user, require
from .deps import audit_context, get_project, slugify

router = APIRouter(tags=["projects"])


# -- organizations ----------------------------------------------------------


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org_ids = {
        m.organization_id
        for m in db.execute(select(Membership).where(Membership.user_id == user.id)).scalars()
    }
    return list(
        db.execute(select(Organization).where(Organization.id.in_(org_ids or [""]))).scalars()
    )


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    payload: OrganizationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = Organization(**payload.model_dump())
    db.add(org)
    db.flush()
    ensure_role_definitions(db, org.id)
    # The creator administers the organization they created.
    db.add(Membership(user_id=user.id, organization_id=org.id, role="org_admin"))
    audit.record(
        db,
        action="organization.created",
        object_type="organization",
        object_id=org.id,
        organization_id=org.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"name": org.name},
    )
    db.commit()
    db.refresh(org)
    return org


# -- programs ---------------------------------------------------------------


@router.get("/programs", response_model=list[ProgramOut])
def list_programs(
    organization_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org_ids = {
        m.organization_id
        for m in db.execute(select(Membership).where(Membership.user_id == user.id)).scalars()
    }
    if organization_id:
        org_ids &= {organization_id}
    return list(db.execute(select(Program).where(Program.organization_id.in_(org_ids or [""]))).scalars())


@router.post("/programs", response_model=ProgramOut, status_code=201)
def create_program(
    payload: ProgramIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    program = Program(**payload.model_dump())
    db.add(program)
    db.flush()
    audit.record(
        db,
        action="program.created",
        object_type="program",
        object_id=program.id,
        organization_id=program.organization_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"name": program.name},
    )
    db.commit()
    db.refresh(program)
    return program


# -- projects ---------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    program_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    memberships = list(db.execute(select(Membership).where(Membership.user_id == user.id)).scalars())
    org_ids = {m.organization_id for m in memberships}
    scoped_project_ids = {m.project_id for m in memberships if m.project_id}

    stmt = select(Project).join(Program).where(Program.organization_id.in_(org_ids or [""]))
    if program_id:
        stmt = stmt.where(Project.program_id == program_id)
    projects = list(db.execute(stmt).scalars())

    # An org-wide membership sees every project; a project-scoped one sees only
    # the projects it names.
    if all(m.project_id for m in memberships) and scoped_project_ids:
        projects = [p for p in projects if p.id in scoped_project_ids]
    return projects


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    program = db.get(Program, payload.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")

    data = payload.model_dump()
    data["slug"] = data.get("slug") or slugify(payload.name)
    enforce_classification(data.get("classification"))
    enforce_classification(data.get("data_classification"), field="data_classification")
    project = Project(**data, owner=user.email)
    db.add(project)
    db.flush()
    audit.record(
        db,
        action="project.created",
        object_type="project",
        object_id=project.id,
        project_id=project.id,
        organization_id=program.organization_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"name": project.name, "impact_level": project.impact_level},
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def read_project(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return get_project(db, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.PROJECT_WRITE)),
):
    project = get_project(db, project_id)
    editable = {
        "name", "description", "capability_type", "impact_level", "data_classification",
        "deployment_environment", "system_owner", "evaluation_owner", "classification", "status",
    }
    if "classification" in payload:
        enforce_classification(payload["classification"])
    if "data_classification" in payload:
        enforce_classification(payload["data_classification"], field="data_classification")

    changed = {}
    for field, value in payload.items():
        if field in editable and getattr(project, field) != value:
            changed[field] = {"from": getattr(project, field), "to": value}
            setattr(project, field, value)
    if changed:
        audit.record(
            db, action="project.updated", object_type="project", object_id=project.id,
            detail={"changes": changed}, **audit_context(db, project, user, request),
        )
    db.commit()
    db.refresh(project)
    return project


# -- mission profile --------------------------------------------------------


@router.get("/projects/{project_id}/mission", response_model=MissionProfileOut | None)
def read_mission(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()


@router.put("/projects/{project_id}/mission", response_model=MissionProfileOut)
def upsert_mission(
    project_id: str,
    payload: MissionProfileIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.PROJECT_WRITE)),
):
    project = get_project(db, project_id)
    profile = db.execute(
        select(MissionProfile).where(MissionProfile.project_id == project_id)
    ).scalar_one_or_none()
    created = profile is None
    if profile is None:
        profile = MissionProfile(project_id=project_id, mission=payload.mission)
        db.add(profile)
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    profile.classification = project.classification
    profile.owner = user.email
    db.flush()
    audit.record(
        db,
        action="mission_profile.created" if created else "mission_profile.updated",
        object_type="mission_profile",
        object_id=profile.id,
        detail={"mission": profile.mission[:200]},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(profile)
    return profile


# -- requirements -----------------------------------------------------------


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(Requirement).where(Requirement.project_id == project_id).order_by(Requirement.key)
        ).scalars()
    )


@router.post("/projects/{project_id}/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(
    project_id: str,
    payload: RequirementIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.PROJECT_WRITE)),
):
    project = get_project(db, project_id)
    requirement = Requirement(project_id=project_id, **payload.model_dump())
    db.add(requirement)
    db.flush()
    audit.record(
        db, action="requirement.created", object_type="requirement", object_id=requirement.id,
        detail={"key": requirement.key}, **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(requirement)
    return requirement
