"""Acquisition Bench demonstration: a benchmark report built end to end.

Two Claude models answered the Acquisition Bench questions and a third
graded every answer criterion by criterion. Those responses are recordings
(`aegis/recordings/`), replayed here through the ordinary engine by the
`recorded` connector, so every result carries the same request, response,
judgements and digest a live run would.

What is a stand-in, and says so everywhere it appears:

- The models were called through Claude Code, not the API, so latency, token
  counts and cost were not recorded and are reported as not recorded.
- The questions were drafted by a model. The shipped pack stays unapproved;
  this demonstration runs project-scoped copies approved by a stand-in.
- The calibration labels come from a simulated reviewer who is not an expert.

Every campaign built here carries a `demonstration` statement in its trigger
detail, and the benchmark report prints it at the top.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .benchmark import benchmark_data
from .connectors.builtin import load_recording
from .enums import Classification, Role, RunStatus, SystemKind
from .hashing import content_hash, evidence_store
from .models import (
    Campaign,
    Evaluation,
    ExpertProfile,
    HumanReview,
    Membership,
    Organization,
    Program,
    Project,
    Report,
    Result,
    Run,
    Scenario,
    System,
    SystemVersion,
    User,
)
from .runner.engine import execute_campaign
from .security import ensure_role_definitions

log = logging.getLogger("aegis.demo_bench")

PROJECT_SLUG = "acquisition-bench-demo"
QUESTIONS_PACK = "bench-acquisition-questions"
CRITERIA_EVALUATION = "acquisition-bench-criteria"
CALIBRATION_EVALUATION = "acquisition-bench-calibration"
CONDITION = "closed_book"

# What each model was told, word for word, as its instructions for every answer.
ANSWER_SYSTEM_PROMPT = (
    "You are an AI assistant supporting U.S. government contracting professionals "
    "(GS-1102 contract specialists and contracting officers). Answer the user's question "
    "directly and helpfully."
)

MODELS = [
    # (display name, model id, recording)
    ("Claude Haiku 4.5", "claude-haiku-4-5", "acquisition-bench-claude-haiku-4-5"),
    ("Claude Sonnet 5", "claude-sonnet-5", "acquisition-bench-claude-sonnet-5"),
]

JUDGE = {
    "connector_type": "recorded",
    "model_name": "Claude Opus 5.5",
    "model_version": "claude-opus-5-5",
    "parameters": {"recording": "acquisition-bench-judge-claude-opus-5-5"},
}

LABELS_RECORDING = "acquisition-bench-demo-labels"

STAND_IN = "Demo reviewer (simulated, not an expert)"
REVIEWER_EMAIL = "demo.reviewer@aegis.local"

DEMONSTRATION = {
    "statement": (
        "This report was produced to demonstrate the benchmark workflow end to end. "
        "Its figures are real measurements of recorded answers. How it differs from a "
        "published benchmark, and which steps were done by stand-ins rather than qualified "
        "people, is listed here."
    ),
    "stand_ins": [
        "Questions and criteria were drafted by a model and approved for this demonstration "
        f"by '{STAND_IN}'. No acquisition expert has reviewed them.",
        "The answering models (Claude Haiku 4.5, Claude Sonnet 5) were run through Claude "
        "Code rather than the API, closed-book, and their answers are replayed from "
        "recordings. Latency, token counts and cost were not recorded.",
        "The judge (Claude Opus 5.5) graded each answer blind to which model wrote it, and "
        "judged all of one answer's criteria in a single pass rather than one call per "
        "criterion. Its verdicts are replayed one criterion at a time.",
        f"Calibration labels come from '{STAND_IN}', not a qualified expert. The labels "
        "were written by an instance of the same model as the judge, working from the "
        "answers without seeing the judge's verdicts, so agreement between the two is "
        "expected and shows how the measurement works, not how far to trust the judge.",
    ],
    "simulated_reviewer": True,
}


def seed_acquisition_bench_demo(db: Session, admin: User) -> str:
    """Build the demonstration project, run both campaigns and generate the report."""
    if db.execute(select(Project).where(Project.slug == PROJECT_SLUG)).scalar_one_or_none():
        return "exists"

    shipped = list(
        db.execute(
            select(Scenario).where(Scenario.source == QUESTIONS_PACK, Scenario.project_id.is_(None))
        ).scalars()
    )
    evaluations = {
        e.key: e
        for e in db.execute(
            select(Evaluation).where(Evaluation.key.in_([CRITERIA_EVALUATION, CALIBRATION_EVALUATION]))
        ).scalars()
    }
    if not shipped or len(evaluations) < 2:
        return "skipped: Acquisition Bench packs are not installed"

    project = _project(db, admin)
    _approved_copies(db, project, shipped)
    versions = _versions(db, project)
    reviewer, profile = _reviewer(db)

    criteria = _campaign(db, project, "Acquisition Bench -- criteria met", evaluations[CRITERIA_EVALUATION], versions)
    calibration = _campaign(
        db, project, "Acquisition Bench -- judge calibration", evaluations[CALIBRATION_EVALUATION], versions
    )
    for campaign in (criteria, calibration):
        execute_campaign(db, campaign, JUDGE)

    _label_calibration(db, calibration, reviewer, profile)

    _report(db, project, admin, [criteria, calibration])
    db.flush()
    log.info("Acquisition Bench demonstration seeded: %s", project.id)
    return "created"


def _project(db: Session, admin: User) -> Project:
    org = db.execute(
        select(Organization).where(Organization.short_name == "DEMO-PEO")
    ).scalar_one_or_none()
    if org is None:
        org = Organization(
            name="Program Executive Office (demonstration)",
            short_name="DEMO-PEO",
            default_classification=Classification.UNCLASSIFIED,
        )
        db.add(org)
        db.flush()
        ensure_role_definitions(db, org.id)
        db.add(Membership(user_id=admin.id, organization_id=org.id, role=Role.ORG_ADMIN))

    program = Program(
        organization_id=org.id,
        name="Acquisition Bench",
        description="Demonstration of a published-style benchmark report.",
        program_office="DEMO-PEO/AB",
    )
    db.add(program)
    db.flush()
    project = Project(
        program_id=program.id,
        name="Acquisition Bench (demonstration)",
        slug=PROJECT_SLUG,
        description=(
            "How often do Claude models meet the criteria for 30 questions a government "
            "contract specialist asks across the contract lifecycle? Demonstration data: the "
            "reviewer and the question approvals are stand-ins, and the report says so."
        ),
        capability_type=SystemKind.LLM,
        data_classification=Classification.UNCLASSIFIED,
        classification=Classification.UNCLASSIFIED,
        owner=admin.email,
    )
    db.add(project)
    db.flush()
    return project


_NOT_COPIED = {"id", "project_id", "approved", "approved_by", "created_at", "updated_at"}


def _approved_copies(db: Session, project: Project, shipped: list[Scenario]) -> None:
    """Project-scoped copies of the questions, approved by the stand-in.

    The shipped scenarios stay unapproved, so nothing outside this project can
    run them until an expert approves them.
    """
    for scenario in shipped:
        values = {
            c.name: getattr(scenario, c.name)
            for c in Scenario.__table__.columns
            if c.name not in _NOT_COPIED
        }
        db.add(Scenario(**values, project_id=project.id, approved=True, approved_by=STAND_IN))
    db.flush()


def _versions(db: Session, project: Project) -> list[SystemVersion]:
    system = System(
        project_id=project.id,
        name="Claude models (recorded answers)",
        slug="claude-recorded",
        kind=SystemKind.LLM,
        vendor="Anthropic",
        description="Answers recorded through Claude Code and replayed by the recorded connector.",
        classification=Classification.UNCLASSIFIED,
    )
    db.add(system)
    db.flush()
    versions = []
    for name, model_id, recording in MODELS:
        load_recording(recording)  # fail here, not mid-run, if a recording is missing
        version = SystemVersion(
            system_id=system.id,
            version=f"{model_id}-{CONDITION}",
            model_provider="Anthropic",
            model_name=name,
            model_version=model_id,
            connector_type="recorded",
            parameters={"recording": recording, "condition": CONDITION},
            system_prompt=ANSWER_SYSTEM_PROMPT,
            change_note="Closed-book answers recorded through Claude Code; replayed.",
            is_current=True,
        )
        db.add(version)
        db.flush()
        version.config_hash = content_hash(
            {"connector_type": version.connector_type, "model_name": version.model_name,
             "parameters": version.parameters, "system_prompt": version.system_prompt}
        )
        versions.append(version)
    return versions


def _reviewer(db: Session) -> tuple[User, ExpertProfile]:
    user = db.execute(select(User).where(User.email == REVIEWER_EMAIL)).scalar_one_or_none()
    if user is None:
        user = User(
            email=REVIEWER_EMAIL,
            full_name=STAND_IN,
            # Not a login: no password and inactive. The account exists only so
            # the demonstration labels have a named, clearly marked author.
            password_hash=None,
            identity_provider="local",
            is_active=False,
        )
        db.add(user)
        db.flush()
    profile = ExpertProfile(
        user_id=user.id,
        display_name=STAND_IN,
        disciplines=["acquisition"],
        title="Simulated reviewer for the Acquisition Bench demonstration",
        notes=(
            "Not a person and not an expert. Labels were written by the AI assistant that "
            "built the demonstration, so the judge agreement table has something to show."
        ),
        verified=False,
    )
    db.add(profile)
    db.flush()
    return user, profile


def _campaign(db, project, name, evaluation, versions) -> Campaign:
    campaign = Campaign(
        project_id=project.id,
        name=name,
        description="Demonstration campaign. See the benchmark report for what is a stand-in.",
        trigger="demonstration",
        trigger_detail={"demonstration": DEMONSTRATION},
        status=RunStatus.QUEUED,
    )
    db.add(campaign)
    db.flush()
    for version in versions:
        db.add(
            Run(
                campaign_id=campaign.id,
                evaluation_id=evaluation.id,
                system_version_id=version.id,
                threshold={},
                status=RunStatus.QUEUED,
            )
        )
    db.flush()
    return campaign


def _label_calibration(db: Session, campaign: Campaign, reviewer: User, profile: ExpertProfile) -> None:
    # Imported here: the review path lives with the API route that normally runs it.
    from . import expertise
    from .routers.campaigns import _check_criteria_labels, _reresolve

    labels = load_recording(LABELS_RECORDING)["labels"]
    rows = db.execute(
        select(Result, Scenario, SystemVersion)
        .join(Run, Run.id == Result.run_id)
        .join(Scenario, Scenario.id == Result.scenario_id)
        .join(SystemVersion, SystemVersion.id == Run.system_version_id)
        .where(Run.campaign_id == campaign.id)
    ).all()
    for result, scenario, version in rows:
        given = (labels.get(version.model_version) or {}).get(scenario.key)
        if not given:
            continue
        _check_criteria_labels(db, result, given)
        required = expertise.required_for_result(db, result)
        qualified, note = expertise.qualify(required, profile, "acquisition")
        db.add(
            HumanReview(
                result_id=result.id,
                reviewer_id=reviewer.id,
                reviewer_label=STAND_IN,
                rubric_key="acquisition-criteria-labels",
                status="fail" if "fail" in given.values() else "pass",
                comments="Simulated label for the demonstration; not expert evidence.",
                expertise="acquisition",
                expert_profile_id=profile.id,
                qualified=qualified,
                qualification_note=note,
                criteria_labels=given,
            )
        )
        db.flush()
        _reresolve(db, result)
    db.flush()


def _report(db: Session, project: Project, admin: User, campaigns: list[Campaign]) -> Report:
    from .reports import benchmark_report

    title = "Acquisition Bench: Claude models on contract specialist questions (demonstration)"
    body = benchmark_report(db, project, benchmark_data(db, campaigns), title)
    digest = content_hash(body)
    stored = evidence_store().put(
        f"reports/{project.id}/benchmark-{digest[:12]}.md", body.encode("utf-8"), "text/markdown"
    )
    report = Report(
        project_id=project.id,
        kind="benchmark",
        title=title,
        format="markdown",
        scope={"campaign_ids": [c.id for c in campaigns]},
        body=body,
        storage_uri=stored["storage_uri"],
        sha256=stored["sha256"],
        classification=project.classification,
        generated_by=admin.email,
    )
    db.add(report)
    db.flush()
    return report

