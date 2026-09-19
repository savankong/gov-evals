"""The first-run walkthrough (sections 10-22, in the order they are done).

Every step here is derived from what is actually in the database. Nothing is
marked done because somebody pressed "mark as done", and there is no endpoint
to assert completion -- which is the same rule the rest of the product runs on.
A step reports what was found, so the walkthrough can be checked rather than
believed.

Steps also say honestly where they can be done. Datasets, plans, campaigns and
expert profiles have interfaces; projects, mission profiles and system versions
are API-only today, so those steps carry the request instead of a button that
would go nowhere.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Campaign,
    Dataset,
    DatasetVersion,
    EvaluationPlan,
    ExpertProfile,
    MissionProfile,
    Project,
    Result,
    Scenario,
    SystemVersion,
    User,
)
from ..security import get_current_user

router = APIRouter(tags=["onboarding"])


def _count(db: Session, model) -> int:
    return db.execute(select(func.count()).select_from(model)).scalar_one()


@router.get("/onboarding")
def onboarding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What this account has actually done, in the order the workflow goes.

    The evidence string on each step is the point: "3 projects" is checkable,
    "completed" is not.
    """
    project = db.execute(select(Project).order_by(Project.created_at)).scalars().first()
    pid = project.id if project else None

    projects = _count(db, Project)
    missions = _count(db, MissionProfile)
    versions = _count(db, SystemVersion)
    datasets = _count(db, Dataset)
    dataset_items = db.execute(
        select(func.coalesce(func.sum(DatasetVersion.item_count), 0)).where(
            DatasetVersion.is_current.is_(True)
        )
    ).scalar_one()
    scenarios = db.execute(
        select(func.count()).select_from(Scenario).where(Scenario.approved.is_(True))
    ).scalar_one()
    approved_plans = db.execute(
        select(func.count()).select_from(EvaluationPlan).where(
            EvaluationPlan.approved_at.is_not(None)
        )
    ).scalar_one()
    campaigns = _count(db, Campaign)
    results = _count(db, Result)
    experts = db.execute(
        select(func.count()).select_from(ExpertProfile).where(ExpertProfile.active.is_(True))
    ).scalar_one()

    def step(
        key: str,
        title: str,
        detail: str,
        done: bool,
        evidence: str,
        href: str | None = None,
        command: str | None = None,
    ) -> dict:
        return {
            "key": key,
            "title": title,
            "detail": detail,
            "done": done,
            # What was counted, so the claim can be checked rather than trusted.
            "evidence": evidence,
            "href": href,
            "command": command,
        }

    steps = [
        step(
            "project",
            "Create an evaluation project",
            "A project pairs one AI capability with the mission it is meant for. "
            "Everything else hangs off that pairing.",
            projects > 0,
            f"{projects} project(s)",
            command="POST /api/v1/projects  {\"program_id\": \"…\", \"name\": \"…\"}",
        ),
        step(
            "mission",
            "Write the mission profile",
            "Tasks, users, environment, acceptable errors, the failures the programme "
            "declares unacceptable. Every result is judged against this — it is what "
            "separates \"how good is this model\" from \"good enough for this mission\".",
            missions > 0,
            f"{missions} mission profile(s)",
            command=f"POST /api/v1/projects/{pid or '{project_id}'}/mission-profile",
        ),
        step(
            "system",
            "Register a system version",
            "An immutable snapshot of model, prompt, parameters, retrieval and tool "
            "access, fingerprinted so a result can always name the exact configuration "
            "that produced it.",
            versions > 0,
            f"{versions} system version(s)",
            command=f"POST /api/v1/projects/{pid or '{project_id}'}/systems",
        ),
        step(
            "cases",
            "Load the cases to test against",
            "A dataset of real cases, approved scenarios, or both. The upload reports "
            "what it found in the file — duplicates, empty inputs, whether any row "
            "carries an expected answer — before a campaign spends anything on it.",
            datasets > 0 or scenarios > 0,
            f"{datasets} dataset(s), {dataset_items} example(s), {scenarios} approved scenario(s)",
            href="/datasets",
        ),
        step(
            "plan",
            "Approve an evaluation plan",
            "Drafted from the mission profile with a written reason for every evaluation. "
            "Thresholds arrive unconfirmed: the plan cannot be approved while any is still "
            "a library default, or while an evaluation has no scenario matching it.",
            approved_plans > 0,
            f"{approved_plans} approved plan(s)",
            href=f"/projects/{pid}/plan" if pid else None,
            command=None if pid else "Create a project first.",
        ),
        step(
            "campaign",
            "Run a campaign",
            "Executes the plan against one or more system versions under identical "
            "conditions — the property that makes a procurement comparison defensible.",
            campaigns > 0 and results > 0,
            f"{campaigns} campaign(s), {results} stored result(s)",
            href=f"/projects/{pid}/campaigns" if pid else None,
            command=None if pid else "Create a project first.",
        ),
        step(
            "experts",
            "Declare who can judge the results",
            "A human judgement is evidence to the extent the judge was qualified to make "
            "it. Without a declared discipline, reviews are recorded as opinions and will "
            "not satisfy an evaluation that requires expertise — so results can sit at "
            "pending_human indefinitely.",
            experts > 0,
            f"{experts} active expert profile(s)",
            href="/experts",
        ),
    ]

    done = sum(1 for s in steps if s["done"])
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "complete": done == len(steps),
        # Nothing exists yet: the account has never been used.
        "first_run": projects == 0 and datasets == 0 and campaigns == 0,
        "project_id": pid,
        "viewer": user.full_name or user.email,
        "note": (
            "Every step is derived from what is in the database. There is no way to mark "
            "one done without doing it."
        ),
    }
