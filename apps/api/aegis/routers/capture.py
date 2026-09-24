"""Target and Capture: where the model is weak, and experts working those problems.

Target reads evaluation results by knowledge area and asks where the model is
wrong, and wrong while confident. Capture puts those problems in front of
people qualified to solve them and records how they did it.

The capture queue leads with problems the model failed that no qualified
expert has worked yet. That order is the whole point: expert hours are the
expensive input, and an hour spent on a problem the model already gets right
produces data nobody will pay for.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, expertise, targeting
from ..classification import enforce as enforce_classification
from ..classification import rank
from ..db import get_db
from ..enums import Classification, ResultStatus
from ..hashing import content_hash
from ..models import ReasoningTrace, Result, Scenario, User
from ..schemas import ReasoningTraceIn, ReasoningTraceOut
from ..security import Permission, get_current_user, require
from .deps import fetch

router = APIRouter(tags=["capture"])


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@router.get("/weakness-map")
def read_weakness_map(
    project_id: str | None = None,
    confident_at: float = Query(targeting.CONFIDENT_AT, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Model outcomes and expert effort per knowledge area. Counts, not a score."""
    return targeting.weakness_map(db, project_id=project_id, confident_at=confident_at)


# ---------------------------------------------------------------------------
# Capture queue
# ---------------------------------------------------------------------------


def _problem(scenario: Scenario) -> dict:
    """The problem as the expert is shown it. No reference answer: an expert
    handed the answer is checking it, not solving the problem."""
    payload = scenario.input or {}
    return {
        "scenario_key": scenario.key,
        "scenario_version": scenario.version,
        "scenario_hash": scenario.content_hash,
        "title": scenario.title,
        "task": scenario.task,
        "context": scenario.context,
        "prompt": payload.get("prompt"),
        "documents": [
            {
                "source_id": d.get("source_id"),
                "title": d.get("title"),
                "text": d.get("text"),
            }
            for d in payload.get("documents") or []
            if isinstance(d, dict)
        ],
    }


def _priority(outcome: dict, qualified_traces: int) -> tuple:
    """Failed and untraced first, then unknown, then what the model got right.

    Evidence compared in a fixed order, not a weighted sum: each position is a
    count a reader can see on the row.
    """
    stage = {"failed": 0, "not_evaluated": 1, "passed": 2}[outcome["outcome"]]
    return (qualified_traces > 0, stage, -outcome["confident_wrong"], -outcome["failed"])


@router.get("/capture/tasks")
def capture_tasks(
    scope: str = Query("mine", pattern="^(mine|all)$"),
    knowledge_area: str | None = None,
    project_id: str | None = None,
    confident_at: float = Query(targeting.CONFIDENT_AT, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Problems to solve, the model's record on each, and who can take them."""
    profile = expertise.profile_for_user(db, user.id)

    query = select(Scenario).where(Scenario.approved.is_(True))
    if project_id:
        query = query.where(
            (Scenario.project_id == project_id) | (Scenario.project_id.is_(None))
        )
    scenarios = list(db.execute(query).scalars())
    if knowledge_area == "":
        scenarios = [s for s in scenarios if not s.knowledge_area]
    elif knowledge_area:
        scenarios = [s for s in scenarios if s.knowledge_area == knowledge_area]

    outcomes = targeting.scenario_outcomes(
        db, [s.id for s in scenarios], confident_at=confident_at, project_id=project_id
    )
    traces: dict[str, list[ReasoningTrace]] = {}
    for trace in db.execute(select(ReasoningTrace)).scalars():
        if trace.scenario_id:
            traces.setdefault(trace.scenario_id, []).append(trace)

    rows = []
    for scenario in scenarios:
        required = list(scenario.required_expertise or [])
        qualified_viewer = expertise.covers(required, profile)
        if scope == "mine" and not qualified_viewer:
            continue
        outcome = outcomes.get(scenario.id, targeting.Outcome()).as_dict()
        mine = traces.get(scenario.id, [])
        qualified = sum(1 for t in mine if t.qualified)
        rows.append(
            {
                "scenario_id": scenario.id,
                "key": scenario.key,
                "title": scenario.title,
                "task": scenario.task,
                "knowledge_area": scenario.knowledge_area,
                "required_expertise": required,
                "viewer_is_qualified": qualified_viewer,
                "model": outcome,
                "traces": len(mine),
                "qualified_traces": qualified,
                "traced_by_me": any(t.author_id == user.id for t in mine),
                "_priority": _priority(outcome, qualified),
            }
        )

    rows.sort(key=lambda r: (*r["_priority"], r["title"].lower()))
    for row in rows:
        del row["_priority"]
    return {
        "confident_at": confident_at,
        "has_profile": profile is not None,
        "tasks": rows[:limit],
        "total": len(rows),
    }


@router.get("/capture/tasks/{scenario_id}")
def capture_task(
    scenario_id: str,
    confident_at: float = Query(targeting.CONFIDENT_AT, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One problem, ready to solve, with the model's wrong answers set aside.

    The model's answers are returned so the interface can offer them, but the
    interface keeps them closed until asked: an expert who reads the wrong
    answer first is anchored by it. A trace records whether one was opened.
    """
    scenario = fetch(db, Scenario, scenario_id, "Scenario")
    profile = expertise.profile_for_user(db, user.id)
    required = list(scenario.required_expertise or [])

    results = list(
        db.execute(
            select(Result)
            .where(Result.scenario_id == scenario.id)
            .order_by(Result.created_at.desc())
        ).scalars()
    )
    outcome = targeting.Outcome()
    for result in results:
        outcome.add(result, confident_at)

    model_answers = []
    for result in results:
        if result.status != ResultStatus.FAIL:
            continue
        confidence, source = targeting.confidence_of(result.response)
        model_answers.append(
            {
                "result_id": result.id,
                "text": (result.response or {}).get("text"),
                "confidence": confidence,
                "confidence_source": source,
                "created_at": result.created_at,
            }
        )
        if len(model_answers) >= 5:
            break

    return {
        "scenario_id": scenario.id,
        "knowledge_area": scenario.knowledge_area,
        "required_expertise": required,
        "viewer_is_qualified": expertise.covers(required, profile),
        "has_profile": profile is not None,
        "problem": _problem(scenario),
        "model": outcome.as_dict(),
        "model_answers": model_answers,
        "confident_at": confident_at,
    }


# ---------------------------------------------------------------------------
# Reasoning traces
# ---------------------------------------------------------------------------


def _most_restrictive(a: str, b: str) -> str:
    """The stricter of two markings. On a tie the one carrying more than the
    bare word UNCLASSIFIED wins, so a caveat is never dropped."""
    if rank(a) != rank(b):
        return a if rank(a) > rank(b) else b
    return b if a.strip().upper() == Classification.UNCLASSIFIED else a


@router.post("/reasoning-traces", response_model=ReasoningTraceOut, status_code=201)
def submit_trace(
    payload: ReasoningTraceIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.HUMAN_SCORE)),
):
    """Record an expert solving a problem.

    Recorded whoever submits it. Counted as expert data only when the author's
    profile covers what the problem requires -- the same rule, and the same
    written reason, as a human review.
    """
    scenario = fetch(db, Scenario, payload.scenario_id, "Scenario")
    if payload.result_id:
        result = fetch(db, Result, payload.result_id, "Result")
        if result.scenario_id != scenario.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "That model answer is to a different problem.",
            )

    steps = [
        {"text": step.text.strip(), "basis": (step.basis or "").strip() or None}
        for step in payload.steps
    ]
    if not all(step["text"] for step in steps):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A step cannot be blank.")

    declared = enforce_classification(payload.classification) or Classification.UNCLASSIFIED
    # A trace about a problem is at least as sensitive as the problem.
    marking = _most_restrictive(declared, scenario.classification or Classification.UNCLASSIFIED)

    profile = expertise.profile_for_user(db, user.id)
    required = list(scenario.required_expertise or [])
    qualified, note = expertise.qualify(required, profile, payload.expertise)

    problem = _problem(scenario)
    sources = [s.strip() for s in payload.sources if s and s.strip()]
    trace = ReasoningTrace(
        scenario_id=scenario.id,
        result_id=payload.result_id,
        author_id=user.id,
        author_label=user.full_name or user.email,
        knowledge_area=scenario.knowledge_area,
        problem=problem,
        steps=steps,
        final_answer=payload.final_answer.strip(),
        sources=sources,
        time_spent_seconds=payload.time_spent_seconds,
        confidence=payload.confidence,
        contains_pii=payload.contains_pii,
        expert_profile_id=profile.id if profile else None,
        expertise=payload.expertise,
        qualified=qualified,
        qualification_note=note,
        classification=marking,
        owner=user.email,
        provenance={"captured_via": "api", "shown_model_answer": bool(payload.result_id)},
    )
    trace.content_hash = content_hash(
        {
            "problem": problem,
            "steps": steps,
            "final_answer": trace.final_answer,
            "sources": sources,
            "result_id": payload.result_id,
        }
    )
    db.add(trace)
    db.flush()

    audit.record(
        db,
        action="reasoning_trace.submitted",
        object_type="reasoning_trace",
        object_id=trace.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={
            "scenario": scenario.key,
            "knowledge_area": scenario.knowledge_area,
            "steps": len(steps),
            "qualified": qualified,
            "qualification_note": note,
            "classification": marking,
            "content_hash": trace.content_hash,
        },
    )
    db.commit()
    db.refresh(trace)
    return trace


@router.get("/reasoning-traces", response_model=list[ReasoningTraceOut])
def list_traces(
    scenario_id: str | None = None,
    knowledge_area: str | None = None,
    mine: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ReasoningTrace).order_by(ReasoningTrace.created_at.desc())
    if scenario_id:
        query = query.where(ReasoningTrace.scenario_id == scenario_id)
    if knowledge_area:
        query = query.where(ReasoningTrace.knowledge_area == knowledge_area)
    if mine:
        query = query.where(ReasoningTrace.author_id == user.id)
    return list(db.execute(query.limit(limit)).scalars())


@router.get("/reasoning-traces/{trace_id}", response_model=ReasoningTraceOut)
def read_trace(trace_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, ReasoningTrace, trace_id, "Reasoning trace")
