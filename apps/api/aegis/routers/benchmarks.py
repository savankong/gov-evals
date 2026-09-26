"""Benchmark report pages: an index of benchmark reports and one report's data.

The report body is Markdown and carries its own digest. These endpoints serve
the same figures as data, recomputed from the campaigns the report covers, so
the web page can chart them. Nothing here is typed in: every number comes from
`benchmark_data`, and every question row resolves to stored results.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..benchmark import DEFAULT_CONDITION, EVALUATOR_KEY, _facets, benchmark_data
from ..db import get_db
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
)
from ..security import get_current_user

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


def _summary(report: Report, project: Project, data: dict) -> dict:
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
        "project": {"id": project.id, "name": project.name, "description": project.description},
        "demonstration": bool(data.get("demonstration")),
        "models": len(data["models"]),
        "conditions": data["conditions"],
        "questions": data["dataset"]["questions"],
        "criteria": data["dataset"]["criteria"],
        "required_expertise": data["dataset"]["required_expertise"],
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
