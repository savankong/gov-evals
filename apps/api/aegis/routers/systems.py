"""System registry and immutable version snapshots (section 12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..classification import enforce as enforce_classification
from ..connectors import TargetRequest, build_adapter, get_adapter
from ..db import get_db
from ..hashing import content_hash
from ..models import System, SystemVersion, User
from ..schemas import StatusResponse, SystemIn, SystemOut, SystemVersionIn, SystemVersionOut
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project, slugify

router = APIRouter(tags=["systems"])


def _config_hash(version: SystemVersion) -> str:
    """Fingerprint of everything that changes system behaviour.

    Deliberately excludes descriptive fields (change notes, ownership) so two
    versions that behave identically hash identically.
    """
    return content_hash(
        {
            "connector_type": version.connector_type,
            "endpoint": version.endpoint,
            "model_provider": version.model_provider,
            "model_name": version.model_name,
            "model_version": version.model_version,
            "parameters": version.parameters,
            "system_prompt": version.system_prompt,
            "rag_architecture": version.rag_architecture,
            "embedding_model": version.embedding_model,
            "retrieval_source": version.retrieval_source,
            "tool_access": version.tool_access,
            "agent_capabilities": version.agent_capabilities,
            "guardrails": version.guardrails,
        }
    )


@router.get("/projects/{project_id}/systems", response_model=list[SystemOut])
def list_systems(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(select(System).where(System.project_id == project_id).order_by(System.name)).scalars()
    )


@router.post("/projects/{project_id}/systems", response_model=SystemOut, status_code=201)
def create_system(
    project_id: str,
    payload: SystemIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.SYSTEM_WRITE)),
):
    project = get_project(db, project_id)
    enforce_classification(payload.classification)
    data = payload.model_dump()
    data["slug"] = data.get("slug") or slugify(payload.name)
    system = System(project_id=project_id, owner=user.email, **data)
    db.add(system)
    db.flush()
    audit.record(
        db, action="system.created", object_type="system", object_id=system.id,
        detail={"name": system.name, "kind": system.kind},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(system)
    return system


@router.get("/systems/{system_id}", response_model=SystemOut)
def read_system(system_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, System, system_id, "System")


@router.get("/systems/{system_id}/versions", response_model=list[SystemVersionOut])
def list_versions(system_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(SystemVersion)
            .where(SystemVersion.system_id == system_id)
            .order_by(SystemVersion.created_at.desc())
        ).scalars()
    )


@router.post("/systems/{system_id}/versions", response_model=SystemVersionOut, status_code=201)
def create_version(
    system_id: str,
    payload: SystemVersionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.SYSTEM_WRITE)),
):
    system = fetch(db, System, system_id, "System")
    try:
        get_adapter(payload.connector_type)
    except KeyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    version = SystemVersion(system_id=system_id, **payload.model_dump())
    version.config_hash = _config_hash(version)

    # Previous versions stay queryable; only one is current.
    for existing in system.versions:
        existing.is_current = False
    version.is_current = True

    db.add(version)
    db.flush()
    audit.record(
        db,
        action="system_version.created",
        object_type="system_version",
        object_id=version.id,
        detail={
            "system": system.name,
            "version": version.version,
            "config_hash": version.config_hash,
            "connector": version.connector_type,
        },
        **audit_context(db, system.project, user, request),
    )
    db.commit()
    db.refresh(version)
    return version


@router.get("/system-versions/{version_id}", response_model=SystemVersionOut)
def read_version(version_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, SystemVersion, version_id, "System version")


@router.post("/system-versions/{version_id}/connectivity", response_model=StatusResponse)
def check_connectivity(
    version_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.SYSTEM_WRITE)),
):
    """Send one trivial request to confirm the target is reachable.

    Run before a campaign so a misconfigured endpoint surfaces as a setup error
    rather than as thousands of errored results.
    """
    version = fetch(db, SystemVersion, version_id, "System version")
    adapter = build_adapter(
        {
            "connector_type": version.connector_type,
            "endpoint": version.endpoint,
            "credential_ref": version.credential_ref,
            "parameters": version.parameters,
            "model_name": version.model_name,
        }
    )
    response = adapter.invoke(
        TargetRequest(
            prompt="Reply with the single word: ready",
            system_prompt=version.system_prompt,
            parameters=version.parameters or {},
        )
    )
    audit.record(
        db,
        action="system_version.connectivity_checked",
        object_type="system_version",
        object_id=version.id,
        detail={"ok": response.error is None, "latency_ms": response.latency_ms},
        **audit_context(db, version.system.project if version.system else None, user, request),
    )
    db.commit()

    if response.error:
        return StatusResponse(status="unreachable", detail={"error": response.error})
    return StatusResponse(
        status="reachable",
        detail={
            "latency_ms": response.latency_ms,
            "excerpt": (response.text or "")[:200],
            "connector": adapter.describe(),
        },
    )
