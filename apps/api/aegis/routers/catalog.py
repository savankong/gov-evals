"""Read-only catalogues: connectors, evaluators, packs, frameworks, vocabularies."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors import available_adapters
from ..db import get_db
from ..enums import (
    Classification,
    Domain,
    EvaluatorKind,
    ImpactLevel,
    ResultStatus,
    Role,
    Severity,
    SystemKind,
    TEVVLayer,
)
from ..evaluators import available_evaluators
from ..models import FrameworkRequirement, Pack
from ..packs import install_all
from ..runner.redteam import ATTACK_LIBRARY
from ..security import Permission, get_current_user, require

router = APIRouter(tags=["catalog"])


@router.get("/connectors")
def connectors(_: object = Depends(get_current_user)) -> dict:
    return {"connectors": available_adapters()}


@router.get("/evaluators")
def evaluators(_: object = Depends(get_current_user)) -> dict:
    return {"evaluators": available_evaluators()}


@router.get("/attacks")
def attacks(_: object = Depends(get_current_user)) -> dict:
    return {
        "attacks": [
            {
                "key": a.key,
                "name": a.name,
                "category": a.category,
                "description": a.description,
                "vector": a.vector,
                "severity": a.severity,
                "mitigation": a.mitigation,
                "framework_refs": a.framework_refs,
            }
            for a in ATTACK_LIBRARY
        ]
    }


@router.get("/packs")
def packs(db: Session = Depends(get_db), _: object = Depends(get_current_user)) -> dict:
    rows = list(db.execute(select(Pack).order_by(Pack.kind, Pack.key)).scalars())
    return {
        "packs": [
            {
                "key": p.key,
                "name": p.name,
                "kind": p.kind,
                "version": p.version,
                "publisher": p.publisher,
                "description": p.description,
                "provenance": p.provenance,
                "content_hash": p.content_hash,
                "installed_at": p.installed_at,
            }
            for p in rows
        ]
    }


@router.post("/packs/install")
def install_packs(
    db: Session = Depends(get_db),
    _: object = Depends(require(Permission.EVALUATION_WRITE)),
) -> dict:
    results = install_all(db)
    db.commit()
    return {"results": results}


@router.get("/frameworks")
def frameworks(db: Session = Depends(get_db), _: object = Depends(get_current_user)) -> dict:
    rows = list(
        db.execute(
            select(FrameworkRequirement).order_by(
                FrameworkRequirement.framework, FrameworkRequirement.ref
            )
        ).scalars()
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        bucket = grouped.setdefault(
            row.framework,
            {"framework": row.framework, "version": row.framework_version, "url": row.url, "requirements": []},
        )
        bucket["requirements"].append(
            {
                "ref": row.ref,
                "title": row.title,
                "text": row.text,
                "compliance_claimable": row.compliance_claimable,
            }
        )
    return {
        "frameworks": list(grouped.values()),
        "note": (
            "A mapping records which framework topic an evaluation speaks to and what evidence "
            "exists. It does not assert compliance. Only a customer with authority over a "
            "requirement may mark it claimable."
        ),
    }


@router.get("/vocabularies")
def vocabularies(_: object = Depends(get_current_user)) -> dict:
    """Controlled vocabularies, so the UI never hard-codes a list."""
    from ..classification import describe as describe_classification

    return {
        "classification_policy": describe_classification(),
        "layers": [{"key": k, "label": TEVVLayer.LABELS[k]} for k in TEVVLayer.ALL],
        "domains": [{"key": k, "label": Domain.LABELS[k]} for k in Domain.ALL],
        "result_statuses": ResultStatus.ALL,
        "severities": Severity.ALL,
        "system_kinds": SystemKind.ALL,
        "classifications": Classification.ALL,
        "impact_levels": ImpactLevel.ALL,
        "roles": Role.ALL,
        "evaluator_kinds": EvaluatorKind.ALL,
        "permissions": Permission.ALL,
    }
