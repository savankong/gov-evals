"""Expert reviewers and the queue that routes work to them (section 20).

Two things live here. Profiles record what a reviewer is qualified to judge,
and the queue puts results in front of the people qualified to judge them.

The queue deliberately does not hide work a reviewer is unqualified for. It
separates it. Someone outside the discipline can still look, and still leave a
review -- it is recorded, labelled, and does not satisfy an evaluation that
requires expertise. Hiding it would lose a real signal; counting it would be a
false one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, expertise
from ..db import get_db
from ..enums import Discipline, ResultStatus
from ..models import (
    Campaign,
    Dataset,
    Evaluation,
    ExpertProfile,
    HumanReview,
    Project,
    Result,
    Run,
    Scenario,
    User,
    utcnow,
)
from ..schemas import ExpertProfileIn, ExpertProfileOut, ReviewQueueItem
from ..security import Permission, get_current_user, require
from .deps import fetch

router = APIRouter(tags=["experts"])


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


@router.get("/disciplines")
def list_disciplines(_: User = Depends(get_current_user)):
    """The suggested expertise vocabulary.

    Suggested, not enforced: a program can record expertise this list has never
    heard of, and the API accepts it. The UI offers these and allows free text.
    """
    return {
        "disciplines": [
            {"key": key, "label": Discipline.LABELS[key]} for key in Discipline.SUGGESTED
        ],
        "extensible": True,
    }


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@router.get("/expert-profiles", response_model=list[ExpertProfileOut])
def list_profiles(
    discipline: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    profiles = list(
        db.execute(select(ExpertProfile).order_by(ExpertProfile.display_name)).scalars()
    )
    if discipline:
        profiles = [p for p in profiles if discipline in (p.disciplines or [])]
    return profiles


@router.get("/expert-profiles/me", response_model=ExpertProfileOut | None)
def read_my_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The caller's own profile, or null if they have not declared one."""
    return expertise.profile_for_user(db, user.id)


@router.put("/expert-profiles/me", response_model=ExpertProfileOut)
def upsert_my_profile(
    payload: ExpertProfileIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Declare or amend your own expertise.

    Editing the disciplines drops any verification, because a verification is a
    statement about a specific claim. Re-declaring the claim invalidates it --
    otherwise "verified" would drift into meaning "was verified about something,
    once".
    """
    profile = expertise.profile_for_user(db, user.id)
    created = profile is None

    if profile is None:
        profile = ExpertProfile(user_id=user.id, **payload.model_dump())
        db.add(profile)
    else:
        changed_claim = set(payload.disciplines or []) != set(profile.disciplines or [])
        for field, value in payload.model_dump().items():
            setattr(profile, field, value)
        if changed_claim and profile.verified:
            profile.verified = False
            profile.verified_by = None
            profile.verified_at = None
    db.flush()

    audit.record(
        db,
        action="expert_profile.created" if created else "expert_profile.updated",
        object_type="expert_profile",
        object_id=profile.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"disciplines": profile.disciplines, "verified": profile.verified},
    )
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/expert-profiles/{profile_id}/verify", response_model=ExpertProfileOut)
def verify_profile(
    profile_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.ORG_ADMINISTER)),
):
    """Vouch for someone else's declared expertise.

    Nobody verifies their own profile. A credential nobody but its holder
    attests to is a self-declaration, and the record should say which it is.
    """
    profile = fetch(db, ExpertProfile, profile_id, "Expert profile")
    if profile.user_id == user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "An expert profile cannot be verified by the person it describes.",
        )
    profile.verified = True
    profile.verified_by = user.full_name or user.email
    profile.verified_at = utcnow()

    audit.record(
        db,
        action="expert_profile.verified",
        object_type="expert_profile",
        object_id=profile.id,
        actor_id=user.id,
        actor_label=user.email,
        detail={"subject": profile.display_name, "disciplines": profile.disciplines},
    )
    db.commit()
    db.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


def _first_text(payload: dict | None, *keys: str) -> str | None:
    for key in keys:
        value = (payload or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _required_reviews(evaluation: Evaluation | None) -> int:
    """How many counted reviews this evaluation asks for."""
    for spec in (evaluation.evaluators if evaluation else None) or []:
        if (spec.get("evaluator") or spec.get("key")) == "human_review":
            return int((spec.get("config") or {}).get("required_reviews", 1))
    return 1


@router.get("/review-queue", response_model=list[ReviewQueueItem])
def review_queue(
    project_id: str | None = None,
    scope: str = Query("mine", pattern="^(mine|all|unqualified)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Results awaiting a human judgement.

    `scope=mine` is the work this reviewer is qualified for, `unqualified` is
    the rest, and `all` is both. The split exists so a reviewer's queue is
    theirs, without pretending the other work does not exist.
    """
    profile = expertise.profile_for_user(db, user.id)

    query = (
        select(Result)
        .where(Result.status == ResultStatus.PENDING_HUMAN)
        .order_by(Result.created_at.desc())
    )
    results = list(db.execute(query).scalars())

    items: list[ReviewQueueItem] = []
    for result in results:
        run = db.get(Run, result.run_id)
        if run is None:
            continue
        campaign = db.get(Campaign, run.campaign_id)
        if campaign is None:
            continue
        if project_id and campaign.project_id != project_id:
            continue
        project = db.get(Project, campaign.project_id)
        if project is None:
            continue

        required = expertise.required_for_result(db, result)
        qualified_viewer = expertise.covers(required, profile)
        if scope == "mine" and not qualified_viewer:
            continue
        if scope == "unqualified" and qualified_viewer:
            continue

        evaluation = db.get(Evaluation, run.evaluation_id)
        scenario = db.get(Scenario, result.scenario_id) if result.scenario_id else None
        reviews = list(
            db.execute(select(HumanReview).where(HumanReview.result_id == result.id)).scalars()
        )
        version = run.system_version
        system = version.system if version else None

        items.append(
            ReviewQueueItem(
                result_id=result.id,
                run_id=run.id,
                campaign_id=campaign.id,
                project_id=project.id,
                project_name=project.name,
                evaluation=evaluation.name if evaluation else run.evaluation_id,
                domain=evaluation.domain if evaluation else None,
                system_version=(
                    f"{system.name} {version.version}" if system and version else None
                ),
                scenario_title=scenario.title if scenario else None,
                prompt=_first_text(result.request, "prompt", "input", "text"),
                response=_first_text(result.response, "text", "output", "content", "answer"),
                rubric=scenario.rubric if scenario else None,
                expected_behavior=(scenario.expected_behavior or []) if scenario else [],
                prohibited_behavior=(scenario.prohibited_behavior or []) if scenario else [],
                required_expertise=required,
                viewer_is_qualified=qualified_viewer,
                review_count=len(reviews),
                qualified_review_count=sum(1 for r in reviews if r.qualified),
                required_reviews=_required_reviews(evaluation),
                created_at=result.created_at,
            )
        )
        if len(items) >= limit:
            break

    return items


@router.get("/review-queue/summary")
def review_queue_summary(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Counts for the queue, and whether the caller can act on any of it."""
    profile = expertise.profile_for_user(db, user.id)
    results = list(
        db.execute(select(Result).where(Result.status == ResultStatus.PENDING_HUMAN)).scalars()
    )

    mine = 0
    undeclared = 0
    for result in results:
        required = expertise.required_for_result(db, result)
        if not required:
            undeclared += 1
        if expertise.covers(required, profile):
            mine += 1

    return {
        "pending_total": len(results),
        "pending_for_me": mine,
        "pending_outside_my_expertise": len(results) - mine,
        # Items nobody declared a requirement for. Not an error, but the program
        # has not said who is qualified, so nothing can be checked against.
        "pending_with_no_declared_expertise": undeclared,
        "has_profile": profile is not None,
        "my_disciplines": list(profile.disciplines or []) if profile else [],
        "profile_verified": bool(profile.verified) if profile else False,
    }


# ---------------------------------------------------------------------------
# Expertise coverage across the datasets a program holds
# ---------------------------------------------------------------------------


@router.get("/expertise-coverage")
def expertise_coverage(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Which required disciplines have an available reviewer, and which do not.

    A program that has written "this needs a contracting officer" on a dataset
    and has no contracting officer on the platform has a gap it should know
    about before the campaign runs, not after the queue stalls.
    """
    datasets = list(db.execute(select(Dataset)).scalars())
    profiles = list(
        db.execute(select(ExpertProfile).where(ExpertProfile.active.is_(True))).scalars()
    )

    held: dict[str, list[dict]] = {}
    for profile in profiles:
        for discipline in profile.disciplines or []:
            held.setdefault(discipline, []).append(
                {"id": profile.id, "name": profile.display_name, "verified": profile.verified}
            )

    rows = []
    for discipline in sorted({d for ds in datasets for d in (ds.required_expertise or [])}):
        reviewers = held.get(discipline, [])
        rows.append(
            {
                "discipline": discipline,
                "label": Discipline.label(discipline),
                "datasets": [
                    {"id": ds.id, "name": ds.name}
                    for ds in datasets
                    if discipline in (ds.required_expertise or [])
                ],
                "reviewers": reviewers,
                "verified_reviewers": sum(1 for r in reviewers if r["verified"]),
                "covered": bool(reviewers),
            }
        )

    return {
        "coverage": rows,
        "gaps": [r["discipline"] for r in rows if not r["covered"]],
        "datasets_with_no_declared_expertise": [
            {"id": ds.id, "name": ds.name} for ds in datasets if not ds.required_expertise
        ],
    }
