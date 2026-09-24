"""Evaluation dataset management (section 16)."""

from __future__ import annotations

import csv
import io
import json
import zipfile

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..classification import enforce as enforce_classification
from ..db import get_db
from ..hashing import content_hash, sha256_bytes
from ..models import Dataset, DatasetItem, DatasetVersion, Run, User
from ..schemas import DatasetIn, DatasetOut, DatasetUpdate, DatasetVersionOut
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["datasets"])

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


@router.get("/datasets")
def index_datasets(
    q: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Every dataset the caller can see, with the counts the index column shows.

    Separate from the per-project list because a reviewer works across programs
    and needs one place that answers "what test cases exist, and who is
    qualified to judge them".
    """
    datasets = list(db.execute(select(Dataset).order_by(Dataset.name)).scalars())
    if q:
        needle = q.strip().lower()
        datasets = [d for d in datasets if needle in d.name.lower()]

    rows = []
    for dataset in datasets:
        current = next((v for v in dataset.versions if v.is_current), None)
        latest = max(
            (v.created_at for v in dataset.versions if v.created_at),
            default=dataset.updated_at or dataset.created_at,
        )
        version_ids = [v.id for v in dataset.versions]
        run_count = (
            db.execute(
                select(func.count())
                .select_from(Run)
                .where(Run.dataset_version_id.in_(version_ids))
            ).scalar_one()
            if version_ids
            else 0
        )
        rows.append(
            {
                "id": dataset.id,
                "name": dataset.name,
                "description": dataset.description,
                "project_id": dataset.project_id,
                "project_name": dataset.project.name if dataset.project else None,
                "modality": dataset.modality,
                "split": dataset.split,
                "classification": dataset.classification,
                "contains_pii": dataset.contains_pii,
                "tags": dataset.tags or [],
                "required_expertise": dataset.required_expertise or [],
                "owner": dataset.owner,
                "example_count": current.item_count if current else 0,
                "version_count": len(dataset.versions),
                "current_version": current.version if current else None,
                "run_count": run_count,
                "updated_at": latest,
            }
        )
    return rows


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


# An archive is decompressed in memory, so what it may expand to is bounded
# independently of what it weighs on the wire. A 64 MB zip can declare
# terabytes; these are checked against what is actually read, not declared.
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_EXPANDED_BYTES = 256 * 1024 * 1024

_STRUCTURED = (".jsonl", ".ndjson", ".json", ".csv", ".tsv")


class ArchiveRefused(ValueError):
    """The archive is outside what this endpoint will expand."""


def _parse(content: bytes, filename: str) -> tuple[list[dict], str]:
    """Parse JSONL, JSON, CSV or a zip archive into a list of row dicts."""
    name = (filename or "").lower()
    if name.endswith(".zip"):
        return _parse_archive(content), "zip"
    return _parse_text(content.decode("utf-8-sig", errors="replace"), name)


def _parse_archive(content: bytes) -> list[dict]:
    """Expand a provider's archive into rows.

    Data providers hand over one large zip and leave the sorting to whoever
    receives it. Structured files inside are expanded row by row; every other
    file becomes one row carrying its text. A file that is not UTF-8 text --
    a PDF, a scan -- is still a row, with its digest and no text, so the
    quality report can say how much of the archive nobody can read yet instead
    of the upload silently dropping it.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ArchiveRefused(f"Not a readable zip archive: {exc}") from exc

    entries = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and not info.filename.rsplit("/", 1)[-1].startswith(".")
    ]
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise ArchiveRefused(
            f"The archive holds {len(entries)} files; at most {MAX_ARCHIVE_ENTRIES} are expanded "
            "per upload. Split it and upload each part as a version."
        )

    rows: list[dict] = []
    expanded = 0
    for info in sorted(entries, key=lambda i: i.filename):
        budget = MAX_ARCHIVE_EXPANDED_BYTES - expanded
        with archive.open(info) as handle:
            data = handle.read(budget + 1)
        expanded += len(data)
        if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
            raise ArchiveRefused(
                f"The archive expands past {MAX_ARCHIVE_EXPANDED_BYTES // (1024 * 1024)} MB. "
                "Split it and upload each part as a version."
            )

        source = {"source_file": info.filename, "source_sha256": sha256_bytes(data)}
        lower = info.filename.lower()
        if lower.endswith(".zip"):
            rows.append({**source, "input": "", "text_extracted": False,
                         "note": "Nested archive; not expanded."})
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            rows.append({**source, "input": "", "text_extracted": False,
                         "size_bytes": len(data)})
            continue
        if lower.endswith(_STRUCTURED):
            parsed, _ = _parse_text(text, lower)
            rows.extend({**source, **(r if isinstance(r, dict) else {"input": r})} for r in parsed)
        else:
            rows.append({**source, "input": text, "text_extracted": True})
    return rows


def _parse_text(text: str, name: str) -> tuple[list[dict], str]:
    """Parse JSONL, JSON or CSV text into a list of row dicts."""

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
    unread = sum(1 for row in rows if row.get("text_extracted") is False)
    if unread:
        issues.append(
            f"{unread} archived file(s) are not text, so nothing was extracted from them. "
            "Each is recorded by name and digest."
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
        "files_without_text": unread,
        "issues": issues,
    }


@router.get("/datasets/{dataset_id}")
def read_dataset(
    dataset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    """One dataset with its versions and the expertise it asks reviewers for."""
    dataset = fetch(db, Dataset, dataset_id, "Dataset")
    versions = sorted(dataset.versions, key=lambda v: v.created_at, reverse=True)
    return {
        "dataset": DatasetOut.model_validate(dataset).model_dump(),
        "project": (
            {"id": dataset.project.id, "name": dataset.project.name}
            if dataset.project
            else None
        ),
        "versions": [DatasetVersionOut.model_validate(v).model_dump() for v in versions],
        "current_version_id": next((v.id for v in versions if v.is_current), None),
    }


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
def update_dataset(
    dataset_id: str,
    payload: DatasetUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.DATASET_WRITE)),
):
    """Amend a dataset, including which expertise its cases need to be judged.

    Changing `required_expertise` does not retroactively re-qualify reviews
    already submitted. Each review stores the decision made when it was filed,
    with the reason, so the record says what was true at the time rather than
    what the rule happens to be now.
    """
    dataset = fetch(db, Dataset, dataset_id, "Dataset")
    fields = payload.model_dump(exclude_unset=True)
    if "classification" in fields:
        enforce_classification(fields["classification"])

    before = list(dataset.required_expertise or [])
    for field, value in fields.items():
        setattr(dataset, field, value)

    audit.record(
        db,
        action="dataset.updated",
        object_type="dataset",
        object_id=dataset.id,
        detail={
            "fields": sorted(fields),
            "required_expertise_before": before,
            "required_expertise_after": list(dataset.required_expertise or []),
        },
        **audit_context(db, dataset.project, user, request),
    )
    db.commit()
    db.refresh(dataset)
    return dataset


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
    except ArchiveRefused as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
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
