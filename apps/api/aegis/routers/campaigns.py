"""Campaign execution, runs, results and human review (sections 18, 20, 36)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..enums import ResultStatus, RunStatus
from ..models import (
    Campaign,
    Evaluation,
    EvaluationPlan,
    Evidence,
    HumanReview,
    Result,
    Run,
    Scenario,
    SystemVersion,
    User,
)
from ..runner import get_queue, summarize_campaign
from ..runner.comparison import compare_campaign, compare_campaigns, compare_runs
from ..schemas import (
    CampaignIn,
    CampaignOut,
    HumanReviewIn,
    HumanReviewOut,
    ResultOut,
    RunOut,
    StatusResponse,
)
from ..security import Permission, get_current_user, require
from .deps import audit_context, fetch, get_project

router = APIRouter(tags=["campaigns"])


def _resolve_evaluations(db: Session, payload: CampaignIn, project_id: str) -> list[Evaluation]:
    """Work out which evaluations a campaign runs.

    Precedence: an approved plan, then explicit ids, then library keys.
    """
    if payload.plan_id:
        plan = db.get(EvaluationPlan, payload.plan_id)
        if plan is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation plan not found")
        evaluations = []
        for item in sorted(plan.items, key=lambda i: i.ordinal):
            if not item.included:
                continue
            evaluation = db.get(Evaluation, item.evaluation_id)
            if evaluation:
                evaluations.append((evaluation, item))
        return evaluations

    evaluations = []
    if payload.evaluation_ids:
        for evaluation_id in payload.evaluation_ids:
            evaluation = db.get(Evaluation, evaluation_id)
            if evaluation:
                evaluations.append((evaluation, None))
    if payload.evaluation_keys:
        rows = db.execute(
            select(Evaluation).where(
                Evaluation.key.in_(payload.evaluation_keys),
                (Evaluation.project_id == project_id) | (Evaluation.project_id.is_(None)),
            )
        ).scalars()
        seen = {e.id for e, _ in evaluations}
        for evaluation in rows:
            if evaluation.id not in seen:
                evaluations.append((evaluation, None))
    return evaluations


@router.get("/projects/{project_id}/campaigns", response_model=list[CampaignOut])
def list_campaigns(project_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list(
        db.execute(
            select(Campaign)
            .where(Campaign.project_id == project_id)
            .order_by(Campaign.created_at.desc())
        ).scalars()
    )


@router.post("/projects/{project_id}/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    project_id: str,
    payload: CampaignIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.CAMPAIGN_EXECUTE)),
):
    """Create a campaign and materialise one run per (evaluation x system version)."""
    project = get_project(db, project_id)
    evaluations = _resolve_evaluations(db, payload, project_id)
    if not evaluations:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No evaluations resolved. Supply a plan_id, evaluation_ids or evaluation_keys.",
        )
    if not payload.system_version_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one system version is required.")

    versions = []
    for version_id in payload.system_version_ids:
        version = db.get(SystemVersion, version_id)
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"System version {version_id} not found")
        versions.append(version)

    campaign = Campaign(
        project_id=project_id,
        plan_id=payload.plan_id,
        name=payload.name,
        description=payload.description,
        kind=payload.kind,
        trigger=payload.trigger,
        trigger_detail=payload.trigger_detail,
        baseline_campaign_id=payload.baseline_campaign_id,
        status=RunStatus.QUEUED,
    )
    db.add(campaign)
    db.flush()

    for evaluation, plan_item in evaluations:
        # Threshold precedence: explicit override, then the plan's, then none.
        # A library default is never silently promoted to a passing bar.
        threshold = payload.thresholds.get(evaluation.key)
        if threshold is None and plan_item is not None:
            threshold = dict(plan_item.threshold or {})
            if threshold.get("source") == "library_default_unconfirmed":
                threshold = {}
        for version in versions:
            db.add(
                Run(
                    campaign_id=campaign.id,
                    evaluation_id=evaluation.id,
                    system_version_id=version.id,
                    dataset_version_id=payload.dataset_version_id,
                    plan_item_id=plan_item.id if plan_item else None,
                    threshold=threshold or {},
                    status=RunStatus.QUEUED,
                )
            )

    audit.record(
        db,
        action="campaign.created",
        object_type="campaign",
        object_id=campaign.id,
        detail={
            "evaluations": [e.key for e, _ in evaluations],
            "system_versions": [v.id for v in versions],
            "trigger": campaign.trigger,
        },
        **audit_context(db, project, user, request),
    )
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/campaigns/{campaign_id}/execute", response_model=StatusResponse)
def execute(
    campaign_id: str,
    request: Request,
    judge: dict | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.CAMPAIGN_EXECUTE)),
):
    campaign = fetch(db, Campaign, campaign_id, "Campaign")
    if campaign.status == RunStatus.RUNNING:
        return StatusResponse(status="already_running", detail={"campaign_id": campaign.id})

    audit.record(
        db,
        action="campaign.executed",
        object_type="campaign",
        object_id=campaign.id,
        project_id=campaign.project_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"judge_configured": bool(judge)},
    )
    db.commit()

    outcome = get_queue().enqueue(campaign_id, judge)
    return StatusResponse(status=outcome, detail={"campaign_id": campaign.id})


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def read_campaign(campaign_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, Campaign, campaign_id, "Campaign")


@router.get("/campaigns/{campaign_id}/summary")
def campaign_summary(campaign_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    campaign = fetch(db, Campaign, campaign_id, "Campaign")
    summary = campaign.summary or summarize_campaign(db, campaign)
    runs = list(db.execute(select(Run).where(Run.campaign_id == campaign_id)).scalars())
    return {
        "campaign": CampaignOut.model_validate(campaign).model_dump(),
        "summary": summary,
        "runs": [
            {
                **RunOut.model_validate(run).model_dump(),
                "evaluation": _evaluation_brief(db, run.evaluation_id),
                "system_version": _version_brief(db, run.system_version_id),
            }
            for run in runs
        ],
    }


def _evaluation_brief(db: Session, evaluation_id: str) -> dict | None:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        return None
    return {
        "id": evaluation.id,
        "key": evaluation.key,
        "name": evaluation.name,
        "layer": evaluation.layer,
        "domain": evaluation.domain,
        "metric": evaluation.metric,
        "aggregation": evaluation.aggregation,
        "evaluators": [e.get("evaluator") for e in evaluation.evaluators or []],
        "framework_refs": evaluation.framework_refs,
    }


def _version_brief(db: Session, version_id: str) -> dict | None:
    version = db.get(SystemVersion, version_id)
    if version is None:
        return None
    system = version.system
    return {
        "id": version.id,
        "label": f"{system.name} {version.version}" if system else version.version,
        "system_id": system.id if system else None,
        "model_name": version.model_name,
        "config_hash": version.config_hash,
    }


@router.get("/campaigns/{campaign_id}/comparison")
def campaign_comparison(campaign_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Side-by-side of every system evaluated in this campaign (section 31)."""
    campaign = fetch(db, Campaign, campaign_id, "Campaign")
    return compare_campaign(db, campaign)


@router.get("/campaigns/{campaign_id}/regression")
def campaign_regression(
    campaign_id: str,
    baseline_campaign_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Diff this campaign against a baseline (section 32)."""
    candidate = fetch(db, Campaign, campaign_id, "Campaign")
    baseline_id = baseline_campaign_id or candidate.baseline_campaign_id
    if not baseline_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No baseline campaign. Supply baseline_campaign_id, or set one on the campaign.",
        )
    baseline = fetch(db, Campaign, baseline_id, "Baseline campaign")
    return compare_campaigns(db, baseline, candidate)


# -- runs and results -------------------------------------------------------


@router.get("/runs/{run_id}", response_model=RunOut)
def read_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return fetch(db, Run, run_id, "Run")


@router.get("/runs/{run_id}/reproducibility")
def run_reproducibility(run_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Everything needed to recreate this run (section 51)."""
    run = fetch(db, Run, run_id, "Run")
    return {"run_id": run.id, "reproducibility": run.reproducibility, "threshold": run.threshold}


@router.get("/runs/{run_id}/results", response_model=list[ResultOut])
def list_results(
    run_id: str,
    result_status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Result).where(Result.run_id == run_id)
    if result_status:
        stmt = stmt.where(Result.status == result_status)
    return list(
        db.execute(stmt.order_by(Result.created_at).offset(offset).limit(min(limit, 500))).scalars()
    )


@router.get("/runs/{run_id}/compare/{baseline_run_id}")
def run_diff(
    run_id: str, baseline_run_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    candidate = fetch(db, Run, run_id, "Run")
    baseline = fetch(db, Run, baseline_run_id, "Baseline run")
    return compare_runs(db, baseline, candidate)


@router.get("/results/{result_id}")
def read_result(result_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """One result with everything behind it. This is the section 72 drill-down."""
    result = fetch(db, Result, result_id, "Result")
    run = db.get(Run, result.run_id)
    scenario = db.get(Scenario, result.scenario_id) if result.scenario_id else None
    evidence = list(db.execute(select(Evidence).where(Evidence.result_id == result_id)).scalars())
    reviews = list(
        db.execute(select(HumanReview).where(HumanReview.result_id == result_id)).scalars()
    )
    return {
        "result": ResultOut.model_validate(result).model_dump(),
        "run": RunOut.model_validate(run).model_dump() if run else None,
        "evaluation": _evaluation_brief(db, run.evaluation_id) if run else None,
        "system_version": _version_brief(db, run.system_version_id) if run else None,
        "scenario": {
            "id": scenario.id,
            "key": scenario.key,
            "title": scenario.title,
            "expected_behavior": scenario.expected_behavior,
            "prohibited_behavior": scenario.prohibited_behavior,
            "rubric": scenario.rubric,
            "content_hash": scenario.content_hash,
        }
        if scenario
        else None,
        "evidence": [
            {
                "id": e.id,
                "kind": e.kind,
                "label": e.label,
                "sha256": e.sha256,
                "size_bytes": e.size_bytes,
                "storage_uri": e.storage_uri,
            }
            for e in evidence
        ],
        "human_reviews": [HumanReviewOut.model_validate(r).model_dump() for r in reviews],
        "reproducibility": run.reproducibility if run else {},
    }


@router.post("/results/{result_id}/reviews", response_model=HumanReviewOut, status_code=201)
def submit_review(
    result_id: str,
    payload: HumanReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.HUMAN_SCORE)),
):
    """Record a human judgement and re-resolve the result it belongs to."""
    result = fetch(db, Result, result_id, "Result")
    if payload.status not in ResultStatus.ALL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown status '{payload.status}'")

    review = HumanReview(
        result_id=result_id,
        reviewer_id=user.id,
        reviewer_label=user.full_name or user.email,
        **payload.model_dump(),
    )
    db.add(review)
    db.flush()

    _reresolve(db, result)

    audit.record(
        db,
        action="human_review.submitted",
        object_type="result",
        object_id=result_id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"status": payload.status, "score": payload.score, "rubric": payload.rubric_key},
    )
    db.commit()
    db.refresh(review)
    return review


def _reresolve(db: Session, result: Result) -> None:
    """Fold a newly submitted review into the result and its run counters."""
    reviews = list(
        db.execute(select(HumanReview).where(HumanReview.result_id == result.id)).scalars()
    )
    run = db.get(Run, result.run_id)
    if run is None:
        return
    evaluation = db.get(Evaluation, run.evaluation_id)
    if evaluation is None:
        return

    from ..evaluators import EvaluationContext, Judgement, aggregate, build_evaluator

    previous_status = result.status
    judgements = [
        Judgement(**{k: v for k, v in j.items() if k in Judgement.__dataclass_fields__})
        for j in (result.judgements or [])
    ]
    review_dicts = [
        {
            "reviewer_label": r.reviewer_label,
            "rubric_key": r.rubric_key,
            "score": r.score,
            "status": r.status,
            "comments": r.comments,
            "confidence": r.confidence,
        }
        for r in reviews
    ]

    ctx = EvaluationContext(
        scenario={},
        request=result.request or {},
        response=result.response or {},
        threshold=run.threshold or {},
        human_reviews=review_dicts,
    )
    # Re-run only the human evaluators; automated judgements are unchanged.
    rebuilt = []
    for judgement in judgements:
        spec = next(
            (
                s
                for s in (evaluation.evaluators or [])
                if (s.get("evaluator") or s.get("key")) == judgement.evaluator_key
            ),
            None,
        )
        if spec and judgement.kind == "human":
            try:
                rebuilt.append(build_evaluator(spec).evaluate(ctx))
                continue
            except KeyError:
                pass
        rebuilt.append(judgement)

    status_value, score = aggregate(rebuilt, evaluation.aggregation)
    result.judgements = [j.to_dict() for j in rebuilt]
    result.status = status_value
    result.score = score

    if previous_status != status_value:
        _recount(db, run)


def _recount(db: Session, run: Run) -> None:
    results = list(db.execute(select(Result).where(Result.run_id == run.id)).scalars())
    run.passed = sum(1 for r in results if r.status == ResultStatus.PASS)
    run.warned = sum(1 for r in results if r.status == ResultStatus.WARNING)
    run.failed = sum(1 for r in results if r.status == ResultStatus.FAIL)
    run.errored = sum(1 for r in results if r.status == ResultStatus.ERROR)
    run.pending_human = sum(1 for r in results if r.status == ResultStatus.PENDING_HUMAN)

    scoreable = run.passed + run.warned + run.failed
    metrics = dict(run.metrics or {})
    metrics["pass_rate"] = round(run.passed / scoreable, 4) if scoreable else None
    metrics["fail_rate"] = round(run.failed / scoreable, 4) if scoreable else None
    metrics["pending_human"] = run.pending_human
    run.metrics = metrics

    from ..runner.engine import _run_verdict

    run.verdict = _run_verdict(run, metrics)
    if run.status == RunStatus.AWAITING_HUMAN and not run.pending_human:
        run.status = RunStatus.COMPLETED

    campaign = db.get(Campaign, run.campaign_id)
    if campaign:
        db.flush()
        campaign.summary = summarize_campaign(db, campaign)
