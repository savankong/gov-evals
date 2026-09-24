"""Deliver: package captured data for a customer's ingest pipeline.

A package leaves the deployment, so what may go into one is decided here, in
code, and not by whoever builds it:

  * Only UNCLASSIFIED, exactly. Not CUI, not a caveated banner, not a marking
    this deployment does not recognise. A lab's training pipeline is not an
    accredited system.
  * Nothing flagged as containing personal information.
  * Only what a qualified expert produced. An unqualified trace or review is
    kept on the record as an opinion; it is not sold as expert data.
  * No label that was never made. A result still `pending_human`,
    `not_evaluated` or in error has no judgement to deliver, so it is left
    out rather than shipped with a guessed one.

Every record considered and left out is counted by reason in the manifest.
Experts are identified to the customer by a pseudonym, their discipline and
whether that was verified -- never by name.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, targeting
from ..db import get_db
from ..enums import Classification, ResultStatus
from ..hashing import canonical_json, content_hash, evidence_store, sha256_bytes
from ..models import (
    DataPackage,
    Dataset,
    DatasetVersion,
    ExpertProfile,
    HumanReview,
    ReasoningTrace,
    Result,
    Run,
    User,
)
from ..schemas import DataPackageIn, DataPackageOut
from ..security import Permission, get_current_user, require
from .deps import fetch

router = APIRouter(tags=["delivery"])

SCHEMA = "aegis.delivery/1"


class Exclusion:
    """Why a record was considered and left out. Counted in every manifest."""

    NOT_QUALIFIED = "not_qualified"
    NOT_UNCLASSIFIED = "not_unclassified"
    CONTAINS_PII = "contains_pii"
    NO_JUDGEMENT = "no_judgement"
    NO_QUALIFIED_JUDGEMENT = "no_qualified_judgement"

    LABELS = {
        NOT_QUALIFIED: "Author was not qualified for the problem",
        NOT_UNCLASSIFIED: "Marked anything other than UNCLASSIFIED",
        CONTAINS_PII: "Flagged as containing personal information",
        NO_JUDGEMENT: "No judgement was ever made (pending, not evaluated or error)",
        NO_QUALIFIED_JUDGEMENT: "Reviewed, but by nobody qualified to judge it",
    }


def releasable_marking(marking: str | None) -> bool:
    """Exactly UNCLASSIFIED. Everything else, including unknown, stays home."""
    return (marking or "").strip().upper() == Classification.UNCLASSIFIED


def _pseudonym(profile_id: str | None) -> str | None:
    if not profile_id:
        return None
    return "expert-" + hashlib.sha256(f"aegis-expert:{profile_id}".encode()).hexdigest()[:12]


def _expert(db: Session, profile_id: str | None, discipline: str | None) -> dict:
    profile = db.get(ExpertProfile, profile_id) if profile_id else None
    return {
        "id": _pseudonym(profile_id),
        "discipline": discipline,
        "verified": bool(profile and profile.verified),
        "years_experience": profile.years_experience if profile else None,
    }


def _sealed(record: dict) -> dict:
    """Attach the digest of the record as it stands without one."""
    return {**record, "sha256": content_hash(record)}


def _trace_records(db, selection, outcomes, excluded) -> list[dict]:
    records = []
    project_id = selection.get("project_id")
    resolver = targeting.AreaResolver(db)
    for trace in db.execute(
        select(ReasoningTrace).order_by(ReasoningTrace.created_at)
    ).scalars():
        if not _area_selected(trace.knowledge_area, selection):
            continue
        if project_id:
            scenario = resolver.scenario(trace.scenario_id)
            if scenario is None or scenario.project_id not in (None, project_id):
                continue
        reason = None
        if not trace.qualified:
            reason = Exclusion.NOT_QUALIFIED
        elif not releasable_marking(trace.classification):
            reason = Exclusion.NOT_UNCLASSIFIED
        elif trace.contains_pii:
            reason = Exclusion.CONTAINS_PII
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue

        outcome = outcomes.get(trace.scenario_id, targeting.Outcome())
        records.append(
            _sealed(
                {
                    "kind": "reasoning_trace",
                    "id": trace.id,
                    "knowledge_area": trace.knowledge_area,
                    "problem": trace.problem,
                    "steps": trace.steps,
                    "final_answer": trace.final_answer,
                    "sources": trace.sources,
                    "expert": _expert(db, trace.expert_profile_id, trace.expertise),
                    "expert_confidence": trace.confidence,
                    "time_spent_seconds": trace.time_spent_seconds,
                    "shown_model_answer": bool(trace.result_id),
                    "model_outcome": outcome.label,
                    "model_confidently_wrong": outcome.confident_wrong > 0,
                    "trace_hash": trace.content_hash,
                }
            )
        )
    return records


def _result_marking(db, result, resolver) -> tuple[str, bool]:
    """The strictest marking on anything this result was built from."""
    markings = []
    pii = False
    scenario = resolver.scenario(result.scenario_id)
    if scenario is not None:
        markings.append(scenario.classification)
    run = db.get(Run, result.run_id)
    if run is not None and run.dataset_version_id:
        version = db.get(DatasetVersion, run.dataset_version_id)
        dataset = db.get(Dataset, version.dataset_id) if version else None
        if dataset is not None:
            markings.append(dataset.classification)
            pii = bool(dataset.contains_pii)
    for marking in markings:
        if not releasable_marking(marking):
            return marking, pii
    return Classification.UNCLASSIFIED, pii


def _scored_records(db, selection, excluded) -> list[dict]:
    records = []
    resolver = targeting.AreaResolver(db)
    reviews: dict[str, list[HumanReview]] = {}
    for review in db.execute(select(HumanReview).order_by(HumanReview.created_at)).scalars():
        reviews.setdefault(review.result_id, []).append(review)
    if not reviews:
        return records

    in_scope = {r.id for r in targeting.results_in_scope(db, selection.get("project_id"))}
    for result_id, filed in reviews.items():
        if result_id not in in_scope:
            continue
        result = db.get(Result, result_id)
        area = resolver.for_result(result)
        if not _area_selected(area, selection):
            continue

        qualified = [r for r in filed if r.qualified]
        marking, pii = _result_marking(db, result, resolver)
        reason = None
        if result.status in targeting.UNRESOLVED:
            reason = Exclusion.NO_JUDGEMENT
        elif not qualified:
            reason = Exclusion.NO_QUALIFIED_JUDGEMENT
        elif not releasable_marking(marking):
            reason = Exclusion.NOT_UNCLASSIFIED
        elif pii:
            reason = Exclusion.CONTAINS_PII
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue

        confidence, source = targeting.confidence_of(result.response)
        records.append(
            _sealed(
                {
                    "kind": "scored_response",
                    "id": result.id,
                    "knowledge_area": area,
                    "prompt": (result.request or {}).get("prompt"),
                    "documents": (result.request or {}).get("documents") or [],
                    "response": (result.response or {}).get("text"),
                    "model_confidence": confidence,
                    "confidence_source": source,
                    "outcome": result.status,
                    "model_outcome": "failed" if result.status == ResultStatus.FAIL else "passed",
                    "judgements": [
                        {
                            "status": r.status,
                            "score": r.score,
                            "comments": r.comments,
                            "confidence": r.confidence,
                            "expert": _expert(db, r.expert_profile_id, r.expertise),
                        }
                        for r in qualified
                    ],
                    "result_hash": result.content_hash,
                }
            )
        )
    return records


def _area_selected(area: str | None, selection: dict) -> bool:
    wanted = selection.get("knowledge_areas") or []
    return not wanted or (area or "") in wanted


def build_package(db: Session, payload: DataPackageIn, author: str | None) -> DataPackage:
    selection = {
        "knowledge_areas": [a.strip() for a in payload.knowledge_areas],
        "include_traces": payload.include_traces,
        "include_scored_responses": payload.include_scored_responses,
        "project_id": payload.project_id,
    }
    confident_at = targeting.CONFIDENT_AT
    excluded: dict[str, int] = {}
    records: list[dict] = []
    if payload.include_traces:
        outcomes = targeting.scenario_outcomes(
            db, confident_at=confident_at, project_id=payload.project_id
        )
        records += _trace_records(db, selection, outcomes, excluded)
    if payload.include_scored_responses:
        records += _scored_records(db, selection, excluded)

    if not records:
        considered = ", ".join(
            f"{count} {Exclusion.LABELS[reason].lower()}" for reason, count in sorted(excluded.items())
        )
        raise HTTPException(
            422,
            detail=(
                "Nothing in this selection can be delivered. "
                + (f"Left out: {considered}." if considered else "Nothing matched it at all.")
            ),
        )

    bins: dict[tuple, int] = {}
    kinds: dict[str, int] = {}
    for record in records:
        key = (record["knowledge_area"], record["model_outcome"], record["kind"])
        bins[key] = bins.get(key, 0) + 1
        kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1

    body = "".join(canonical_json(record) + "\n" for record in records).encode("utf-8")
    package = DataPackage(
        name=payload.name.strip(),
        customer=(payload.customer or "").strip() or None,
        selection=selection,
        record_count=len(records),
        classification=Classification.UNCLASSIFIED,
        created_by=author,
    )
    db.add(package)
    db.flush()

    stored = evidence_store().put(f"packages/{package.id}.jsonl", body, package.media_type)
    package.storage_uri = stored["storage_uri"]
    package.sha256 = stored["sha256"]
    package.size_bytes = stored["size_bytes"]
    package.manifest = {
        "schema": SCHEMA,
        "confident_at": confident_at,
        "kinds": kinds,
        "bins": [
            {"knowledge_area": area, "model_outcome": outcome, "kind": kind, "records": count}
            for (area, outcome, kind), count in sorted(
                bins.items(), key=lambda item: (item[0][0] or "￿", item[0][1], item[0][2])
            )
        ],
        "excluded": [
            {"reason": reason, "label": Exclusion.LABELS[reason], "records": count}
            for reason, count in sorted(excluded.items())
        ],
    }
    return package


@router.post("/data-packages", response_model=DataPackageOut, status_code=201)
def create_package(
    payload: DataPackageIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.REPORT_GENERATE)),
):
    package = build_package(db, payload, user.email)
    audit.record(
        db,
        action="data_package.created",
        object_type="data_package",
        object_id=package.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={
            "name": package.name,
            "customer": package.customer,
            "records": package.record_count,
            "sha256": package.sha256,
            "excluded": package.manifest.get("excluded"),
        },
    )
    db.commit()
    db.refresh(package)
    return package


@router.get("/data-packages", response_model=list[DataPackageOut])
def list_packages(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(select(DataPackage).order_by(DataPackage.created_at.desc())).scalars()
    )


@router.get("/data-packages/{package_id}", response_model=DataPackageOut)
def read_package(package_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, DataPackage, package_id, "Data package")


@router.get("/data-packages/{package_id}/download")
def download_package(
    package_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.REPORT_GENERATE)),
):
    """The stored file, checked against its recorded digest before it leaves.

    A package that no longer matches what was recorded is refused rather than
    sent: the customer would be ingesting something nobody can vouch for.
    """
    package = fetch(db, DataPackage, package_id, "Data package")
    if not package.storage_uri:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This package has no stored file.")
    body = evidence_store().get(package.storage_uri)
    if sha256_bytes(body) != package.sha256:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The stored package no longer matches the digest recorded when it was built. "
            "It has not been sent. Rebuild it from the current record.",
        )
    audit.record(
        db,
        action="data_package.downloaded",
        object_type="data_package",
        object_id=package.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"sha256": package.sha256},
    )
    db.commit()
    filename = "".join(c if c.isalnum() or c in "-_" else "-" for c in package.name)[:80]
    return Response(
        content=body,
        media_type=package.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename or "package"}.jsonl"',
            "X-Content-SHA256": package.sha256,
        },
    )
