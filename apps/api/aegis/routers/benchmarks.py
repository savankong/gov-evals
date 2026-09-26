"""Benchmark report pages: an index of benchmark reports and one report's data.

The report body is Markdown and carries its own digest. These endpoints serve
the same figures as data, recomputed from the campaigns the report covers, so
the web page can chart them. Nothing here is typed in: every number comes from
`benchmark_data`, and every question row resolves to stored results.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..benchmark import DEFAULT_CONDITION, EVALUATOR_KEY, _facets, benchmark_data
from ..db import get_db
from ..enums import Classification, Permission
from ..models import (
    Campaign,
    Membership,
    Program,
    Project,
    Report,
    Result,
    Run,
    Scenario,
    SystemVersion,
    User,
    utcnow,
)
from ..security import get_current_user, permissions_for
from .deps import audit_context

router = APIRouter(tags=["benchmarks"])


def _visible_project_ids(db: Session, user: User) -> set[str]:
    """The projects this user can see, by the same rule as the project list."""
    memberships = list(db.execute(select(Membership).where(Membership.user_id == user.id)).scalars())
    org_ids = {m.organization_id for m in memberships}
    projects = set(
        db.execute(
            select(Project.id).join(Program).where(Program.organization_id.in_(org_ids or [""]))
        ).scalars()
    )
    scoped = {m.project_id for m in memberships if m.project_id}
    if memberships and all(m.project_id for m in memberships):
        projects &= scoped
    return projects


def _campaigns(db: Session, report: Report) -> list[Campaign]:
    ids = list((report.scope or {}).get("campaign_ids") or [])
    campaigns = [db.get(Campaign, cid) for cid in ids]
    return [c for c in campaigns if c is not None and c.project_id == report.project_id]


def _summary(report: Report, project: Project, data: dict, public: bool = False) -> dict:
    ranked = sorted(
        (r for r in data["leaderboard"] if r["pass_rate"] is not None),
        key=lambda r: r["pass_rate"],
        reverse=True,
    )
    return {
        "id": report.id,
        "title": report.title,
        "created_at": report.created_at,
        "sha256": report.sha256,
        "classification": report.classification,
        "project": {
            **({} if public else {"id": project.id}),
            "name": project.name,
            "description": project.description,
        },
        "demonstration": bool(data.get("demonstration")),
        "models": len(data["models"]),
        "conditions": data["conditions"],
        "questions": data["dataset"]["questions"],
        "criteria": data["dataset"]["criteria"],
        "required_expertise": data["dataset"]["required_expertise"],
        "published_at": report.published_at,
        "top": [
            {"model": r["model"], "condition": r["condition"], "pass_rate": r["pass_rate"]}
            for r in ranked[:3]
        ],
    }


def _benchmark_reports(db: Session, user: User) -> list[tuple[Report, Project]]:
    visible = _visible_project_ids(db, user)
    rows = db.execute(
        select(Report, Project)
        .join(Project, Project.id == Report.project_id)
        .where(Report.kind == "benchmark", Report.project_id.in_(visible or {""}))
        .order_by(Report.created_at.desc())
    ).all()
    return [(r, p) for r, p in rows]


@router.get("/benchmarks")
def list_benchmarks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """The latest benchmark report per project, newest first."""
    seen: set[str] = set()
    out = []
    for report, project in _benchmark_reports(db, user):
        if project.id in seen:
            continue
        seen.add(project.id)
        out.append(_summary(report, project, benchmark_data(db, _campaigns(db, report))))
    return out


@router.get("/benchmarks/{report_id}")
def read_benchmark(
    report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    report = db.get(Report, report_id)
    if (
        report is None
        or report.kind != "benchmark"
        or report.project_id not in _visible_project_ids(db, user)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benchmark report not found")
    project = db.get(Project, report.project_id)
    campaigns = _campaigns(db, report)
    data = benchmark_data(db, campaigns)
    return {
        **_summary(report, project, data),
        "data": data,
        "question_rows": _question_rows(db, campaigns),
    }


def _question_rows(db: Session, campaigns: list[Campaign]) -> list[dict]:
    """Every scored question with each model's criterion verdicts and answer.

    Calibration results measure the judge and are left out, as they are from
    every pass rate.
    """
    rows = db.execute(
        select(Result, Scenario, SystemVersion)
        .join(Run, Run.id == Result.run_id)
        .join(Scenario, Scenario.id == Result.scenario_id)
        .join(SystemVersion, SystemVersion.id == Run.system_version_id)
        .where(Run.campaign_id.in_([c.id for c in campaigns] or [""]))
    ).all()
    questions: dict[str, dict] = {}
    runs: dict[str, dict] = defaultdict(dict)
    for result, scenario, version in rows:
        meta = next(
            (
                j.get("evaluator_metadata") or {}
                for j in result.judgements or []
                if j.get("evaluator_key") == EVALUATOR_KEY
            ),
            None,
        )
        if meta is None or meta.get("calibration"):
            continue
        questions.setdefault(
            scenario.key,
            {
                "key": scenario.key,
                "title": scenario.title,
                "knowledge_area": scenario.knowledge_area,
                "facets": _facets(scenario.tags),
                "question": (result.request or {}).get("prompt"),
                "criteria": [{"id": c.get("id"), "text": c.get("text")} for c in scenario.criteria or []],
            },
        )
        model = version.model_name or version.version
        condition = str((version.parameters or {}).get("condition") or DEFAULT_CONDITION)
        runs[scenario.key][f"{model} / {condition}"] = {
            "model": model,
            "condition": condition,
            "result_id": result.id,
            "content_hash": result.content_hash,
            "answer": (result.response or {}).get("text"),
            "verdicts": {
                row.get("id"): {"verdict": row.get("verdict"), "rationale": row.get("rationale")}
                for row in meta.get("criteria") or []
            },
        }
    return [
        {**q, "results": runs[key]} for key, q in sorted(questions.items())
    ]


# ---------------------------------------------------------------------------
# Publishing and the public pages
# ---------------------------------------------------------------------------


def _publishable(db: Session, report_id: str, user: User) -> Report:
    report = db.get(Report, report_id)
    if (
        report is None
        or report.kind != "benchmark"
        or report.project_id not in _visible_project_ids(db, user)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benchmark report not found")
    if Permission.REPORT_GENERATE not in permissions_for(db, user, report.project_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Missing permission 'report:generate' for this project"
        )
    return report


@router.post("/benchmarks/{report_id}/publish")
def publish_benchmark(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Put a benchmark report on the public pages, which need no login."""
    report = _publishable(db, report_id, user)
    if report.classification != Classification.UNCLASSIFIED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"This report is marked {report.classification}. Only an UNCLASSIFIED report can "
            "be published to pages anyone can read.",
        )
    report.published_at = utcnow()
    report.published_by = user.email
    audit.record(
        db, action="report.published", object_type="report", object_id=report.id,
        detail={"sha256": report.sha256},
        **audit_context(db, db.get(Project, report.project_id), user, request),
    )
    db.commit()
    return {"id": report.id, "published_at": report.published_at, "published_by": report.published_by}


@router.post("/benchmarks/{report_id}/unpublish")
def unpublish_benchmark(
    report_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    report = _publishable(db, report_id, user)
    report.published_at = None
    report.published_by = None
    audit.record(
        db, action="report.unpublished", object_type="report", object_id=report.id,
        detail={"sha256": report.sha256},
        **audit_context(db, db.get(Project, report.project_id), user, request),
    )
    db.commit()
    return {"id": report.id, "published_at": None}


def _public_reports(db: Session) -> list[tuple[Report, Project]]:
    rows = db.execute(
        select(Report, Project)
        .join(Project, Project.id == Report.project_id)
        .where(
            Report.kind == "benchmark",
            Report.published_at.is_not(None),
            Report.classification == Classification.UNCLASSIFIED,
        )
        .order_by(Report.published_at.desc())
    ).all()
    return [(r, p) for r, p in rows]


def _public_rows(rows: list[dict]) -> list[dict]:
    """Only questions marked split:public, and nothing that points into the app.

    A held-out question is part of the pass rate but its wording, criteria and
    answers stay private, or it stops being held out.
    """
    out = []
    for row in rows:
        if row["facets"].get("split") != "public":
            continue
        results = {
            k: {kk: vv for kk, vv in v.items() if kk != "result_id"}
            for k, v in row["results"].items()
        }
        out.append({**row, "results": results})
    return out


@router.get("/public/benchmarks")
def list_public_benchmarks(db: Session = Depends(get_db)) -> list[dict]:
    """Published benchmark reports, newest per project first. No login."""
    seen: set[str] = set()
    out = []
    for report, project in _public_reports(db):
        if project.id in seen:
            continue
        seen.add(project.id)
        out.append(_summary(report, project, benchmark_data(db, _campaigns(db, report)), public=True))
    return out


@router.get("/public/benchmarks/{report_id}")
def read_public_benchmark(report_id: str, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if (
        report is None
        or report.kind != "benchmark"
        or report.published_at is None
        or report.classification != Classification.UNCLASSIFIED
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benchmark report not found")
    project = db.get(Project, report.project_id)
    campaigns = _campaigns(db, report)
    data = benchmark_data(db, campaigns)
    rows = _public_rows(_question_rows(db, campaigns))
    public_keys = {r["key"] for r in rows}
    data = {
        **data,
        # Campaign ids name internal records; the report's own digest is the
        # public handle.
        "campaigns": [{"name": c["name"]} for c in data["campaigns"]],
        "example": data["example"]
        if data["example"] and data["example"].get("scenario_key") in public_keys
        else None,
    }
    if data["example"]:
        data["example"] = {k: v for k, v in data["example"].items() if k != "result_id"}
    return {**_summary(report, project, data, public=True), "data": data, "question_rows": rows}
