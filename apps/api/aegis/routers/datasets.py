"""Evaluation dataset management (section 16)."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..classification import enforce as enforce_classification
from ..db import get_db
from ..hashing import content_hash
from ..models import Dataset, DatasetItem, DatasetVersion, User
from ..schemas import DatasetIn, DatasetOut, DatasetVersionOut
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["datasets"])

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetOut])
def list_datasets(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.name)).scalars()
    )


@router.post("/projects/{project_id}/datasets", response_model=DatasetOut, status_code=201)
def create_dataset(
    project_id: str,
    payload: DatasetIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.DATASET_WRITE)),
):
    project = get_project(db, project_id)
    enforce_classification(payload.classification)
    dataset = Dataset(project_id=project_id, owner=user.email, **payload.model_dump())
    db.add(dataset)
    db.flush()
    audit.record(
        db, action="dataset.created", object_type="dataset", object_id=dataset.id,
        detail={"name": dataset.name, "classification": dataset.classification,
                "contains_pii": dataset.contains_pii},
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(dataset)
    return dataset


def _parse(content: bytes, filename: str) -> tuple[list[dict], str]:
    """Parse JSONL, JSON or CSV into a list of row dicts."""
    name = (filename or "").lower()
    text = content.decode("utf-8-sig", errors="replace")

    if name.endswith((".jsonl", ".ndjson")):
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        return rows, "jsonl"
    if name.endswith(".json"):
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("items") or parsed.get("data") or [parsed]
        return list(parsed), "json"
    if name.endswith((".csv", ".tsv")):
        delimiter = "\t" if name.endswith(".tsv") else ","
        return list(csv.DictReader(io.StringIO(text), delimiter=delimiter)), "csv"

    # Unlabelled text: one scenario per non-empty line.
    return [{"input": line} for line in text.splitlines() if line.strip()], "text"


def _quality_report(rows: list[dict]) -> dict:
    """Dataset quality analysis surfaced at upload rather than at run time."""
    if not rows:
        return {"items": 0, "issues": ["The uploaded file contained no rows."]}

    issues: list[str] = []
    keys: dict[str, int] = {}
    empty_inputs = 0
    seen: set[str] = set()
    duplicates = 0
    with_expected = 0

    for row in rows:
        for key in row:
            keys[key] = keys.get(key, 0) + 1
        value = row.get("input") or row.get("prompt") or ""
        if not str(value).strip():
            empty_inputs += 1
        digest = content_hash(value)
        if digest in seen:
            duplicates += 1
        seen.add(digest)
        if row.get("expected") or row.get("reference"):
            with_expected += 1

    if empty_inputs:
        issues.append(f"{empty_inputs} row(s) have no input text.")
    if duplicates:
        issues.append(f"{duplicates} duplicate input(s) detected.")
    if not with_expected:
        issues.append(
            "No row carries an expected answer. Deterministic comparison evaluators will "
            "report NOT EVALUATED against this dataset."
        )
    inconsistent = [k for k, count in keys.items() if 0 < count < len(rows)]
    if inconsistent:
        issues.append(f"Fields present on only some rows: {sorted(inconsistent)[:8]}.")

    return {
        "items": len(rows),
        "fields": sorted(keys),
        "empty_inputs": empty_inputs,
        "duplicates": duplicates,
        "rows_with_expected_answer": with_expected,
        "issues": issues,
    }


@router.post("/datasets/{dataset_id}/versions", response_model=DatasetVersionOut, status_code=201)
async def upload_version(
    dataset_id: str,
    request: Request,
    file: UploadFile = File(...),
    version: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.DATASET_WRITE)),
):
    dataset = fetch(db, Dataset, dataset_id, "Dataset")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 64 MB limit")

    try:
        rows, source_format = _parse(content, file.filename or "")
    except (json.JSONDecodeError, csv.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse file: {exc}") from exc
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File contained no usable rows")

    for existing in dataset.versions:
        existing.is_current = False

    dataset_version = DatasetVersion(
        dataset_id=dataset_id,
        version=version or f"v{len(dataset.versions) + 1}",
        item_count=len(rows),
        source_format=source_format,
        content_hash=content_hash(rows),
        quality_report=_quality_report(rows),
        is_current=True,
    )
    db.add(dataset_version)
    db.flush()

    for ordinal, row in enumerate(rows):
        db.add(
            DatasetItem(
                dataset_version_id=dataset_version.id,
                ordinal=ordinal,
                payload=row if isinstance(row, dict) else {"input": row},
                content_hash=content_hash(row),
            )
        )

    audit.record(
        db,
        action="dataset_version.created",
        object_type="dataset_version",
        object_id=dataset_version.id,
        detail={
            "dataset": dataset.name,
            "version": dataset_version.version,
            "items": len(rows),
            "content_hash": dataset_version.content_hash,
        },
        **audit_context(db, dataset.project, user, request),
    )
    db.commit()
    db.refresh(dataset_version)
    return dataset_version


@router.get("/datasets/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_versions(dataset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.created_at.desc())
        ).scalars()
    )


@router.get("/dataset-versions/{version_id}/items")
def list_items(
    version_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    items = list(
        db.execute(
            select(DatasetItem)
            .where(DatasetItem.dataset_version_id == version_id)
            .order_by(DatasetItem.ordinal)
            .offset(offset)
            .limit(min(limit, 500))
        ).scalars()
    )
    return {
        "items": [
            {"id": i.id, "ordinal": i.ordinal, "payload": i.payload, "content_hash": i.content_hash}
            for i in items
        ],
        "offset": offset,
        "limit": limit,
    }
