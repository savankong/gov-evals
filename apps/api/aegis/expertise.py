"""Whether a human judgement counts as expert evidence (section 20).

The product's position on model judges -- advisory, recorded with the provenance
that produced it, never ground truth -- applies to people too. A human review is
evidence about a mission output to the extent the reviewer was qualified to make
it. A contracting officer and a security engineer can both press "fail" on the
same contract analysis; only one of them is telling you the analysis is wrong.

So a review is never suppressed for lack of expertise -- an unqualified opinion
is still worth recording, and hiding it would be worse -- but it is labelled,
and an evaluation configured to require expertise will not treat it as a
judgement. A run reviewed only by people outside the discipline has not been
reviewed, and stays `pending_human` rather than passing.
"""

from __future__ import annotations

from typing import Protocol

from .enums import Discipline


class _Profile(Protocol):
    """Structural type so this works on the ORM object and on a plain dict."""

    disciplines: list
    active: bool
    verified: bool


def _label_list(slugs: list[str]) -> str:
    return ", ".join(Discipline.label(s) for s in slugs) or "none"


def qualify(
    required: list[str] | None,
    profile: _Profile | None,
    submitted_under: str | None = None,
) -> tuple[bool, str]:
    """Decide whether a review counts as expert evidence, and say why.

    Returns `(qualified, note)`. The note is stored on the review and shown in
    the evidence panel, because "did not count" without a reason is the kind of
    silent rule that erodes trust in the whole record.
    """
    required = [r for r in (required or []) if r]

    if profile is None:
        return False, (
            "Recorded without an expert profile, so it is an opinion rather than "
            "expert evidence."
        )
    if not profile.active:
        return False, "The reviewer's expert profile is inactive."

    held = [d for d in (profile.disciplines or []) if d]

    if not required:
        # Nothing to check against. Say that plainly rather than implying the
        # reviewer was vetted for this item.
        return True, (
            "No expertise requirement is declared for this item, so none was checked."
        )

    if submitted_under and submitted_under not in held:
        return False, (
            f"Submitted under {Discipline.label(submitted_under)}, which is not on "
            f"the reviewer's profile ({_label_list(held)})."
        )
    if submitted_under and submitted_under not in required:
        return False, (
            f"Submitted under {Discipline.label(submitted_under)}; this item needs "
            f"{_label_list(required)}."
        )

    overlap = [d for d in held if d in required]
    if not overlap:
        return False, (
            f"The reviewer's expertise ({_label_list(held)}) does not cover "
            f"{_label_list(required)}."
        )

    note = f"Reviewer holds {_label_list(overlap)}."
    if not profile.verified:
        note += " Profile is self-declared and has not been verified."
    return True, note


def covers(required: list[str] | None, profile: _Profile | None) -> bool:
    """Whether this reviewer could qualify on this item at all.

    Used to route the review queue. Unlike `qualify` this makes no judgement
    about a specific submission; it answers "should this land in front of them".
    """
    return qualify(required, profile)[0]


def required_for_result(db, result) -> list[str]:
    """Which expertise this result's item asks for.

    The scenario wins when it declares one, because a single dataset can hold
    cases that need different disciplines. Otherwise the dataset's declaration
    stands for all of its items. Neither means undeclared, which `qualify`
    reports rather than guesses at.
    """
    from .models import Dataset, DatasetVersion, Run, Scenario

    if result.scenario_id:
        scenario = db.get(Scenario, result.scenario_id)
        if scenario is not None and scenario.required_expertise:
            return list(scenario.required_expertise)

    run = db.get(Run, result.run_id)
    if run is None or not run.dataset_version_id:
        return []
    version = db.get(DatasetVersion, run.dataset_version_id)
    if version is None:
        return []
    dataset = db.get(Dataset, version.dataset_id)
    return list(dataset.required_expertise) if dataset else []


def profile_for_user(db, user_id: str | None):
    """The caller's active expert profile, if they have one."""
    from sqlalchemy import select

    from .models import ExpertProfile

    if not user_id:
        return None
    return db.execute(
        select(ExpertProfile)
        .where(ExpertProfile.user_id == user_id, ExpertProfile.active.is_(True))
        .order_by(ExpertProfile.created_at)
    ).scalars().first()
