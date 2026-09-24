"""Aegis Eval persistence model.

The shape follows PRD section 57 and the evidence graph in section 30:

    Mission -> Requirement -> Risk -> Evaluation -> Scenario -> Execution
            -> Result -> Evidence -> Finding -> Mitigation -> Retest
            -> Assurance Claim

Every scoreable object carries enough configuration to be re-executed
(section 51) and a content hash so later readers can prove the artifact they
are looking at is the one that was evaluated (section 52).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums import Classification, ResultStatus, RunStatus


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class GovernedArtifactMixin:
    """Section 47 -- every artifact carries handling metadata."""

    classification: Mapped[str] = mapped_column(String(64), default=Classification.UNCLASSIFIED)
    owner: Mapped[str | None] = mapped_column(String(255))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_policy: Mapped[str | None] = mapped_column(String(255))


# ---------------------------------------------------------------------------
# Identity and tenancy
# ---------------------------------------------------------------------------


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(64))
    # Default classification banner applied to new artifacts in this tenant.
    default_classification: Mapped[str] = mapped_column(
        String(64), default=Classification.UNCLASSIFIED
    )
    # Customer-owned risk scoring matrix (section 28).
    risk_scoring: Mapped[dict] = mapped_column(JSON, default=dict)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    programs: Mapped[list[Program]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Populated when the account is federated (OIDC / SAML / CAC-PIV).
    external_subject: Mapped[str | None] = mapped_column(String(255), index=True)
    identity_provider: Mapped[str] = mapped_column(String(64), default="local")
    # DoD EDIPI from a CAC/PIV certificate, when that path is configured.
    edipi: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RoleDefinition(Base, TimestampMixin):
    """Editable role -> permission mapping (section 49)."""

    __tablename__ = "role_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "role", name="uq_role_per_org"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text)


class Membership(Base, TimestampMixin):
    __tablename__ = "memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    # Null scope = organization-wide. Otherwise the grant is project-scoped.
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# Program / project structure
# ---------------------------------------------------------------------------


class Program(Base, TimestampMixin):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    program_office: Mapped[str | None] = mapped_column(String(255))

    organization: Mapped[Organization] = relationship(back_populates="programs")
    projects: Mapped[list[Project]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )


class Project(Base, TimestampMixin, GovernedArtifactMixin):
    """An evaluation project (PRD section 10)."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    program_id: Mapped[str] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    capability_type: Mapped[str | None] = mapped_column(String(64))
    impact_level: Mapped[str | None] = mapped_column(String(16))
    data_classification: Mapped[str | None] = mapped_column(String(64))
    deployment_environment: Mapped[str | None] = mapped_column(String(128))
    system_owner: Mapped[str | None] = mapped_column(String(255))
    evaluation_owner: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")

    program: Mapped[Program] = relationship(back_populates="projects")
    mission_profile: Mapped[MissionProfile | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    systems: Mapped[list[System]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    requirements: Mapped[list[Requirement]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class MissionProfile(Base, TimestampMixin, GovernedArtifactMixin):
    """Section 11 -- the operational context every evaluation is judged against."""

    __tablename__ = "mission_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    tasks: Mapped[list] = mapped_column(JSON, default=list)
    users: Mapped[list] = mapped_column(JSON, default=list)
    expected_decisions: Mapped[list] = mapped_column(JSON, default=list)
    operational_environment: Mapped[str | None] = mapped_column(Text)
    expected_inputs: Mapped[list] = mapped_column(JSON, default=list)
    expected_outputs: Mapped[list] = mapped_column(JSON, default=list)
    acceptable_errors: Mapped[list] = mapped_column(JSON, default=list)
    unacceptable_failures: Mapped[list] = mapped_column(JSON, default=list)
    adversaries: Mapped[list] = mapped_column(JSON, default=list)
    environmental_constraints: Mapped[list] = mapped_column(JSON, default=list)
    latency_requirement_ms: Mapped[int | None] = mapped_column(Integer)
    information_sensitivity: Mapped[str | None] = mapped_column(String(128))
    human_oversight: Mapped[str | None] = mapped_column(Text)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    operating_assumptions: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped[Project] = relationship(back_populates="mission_profile")


class Requirement(Base, TimestampMixin):
    """A program requirement an evaluation can be traced to (section 30)."""

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64), index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255))
    threshold: Mapped[str | None] = mapped_column(String(255))
    objective: Mapped[str | None] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(64))

    project: Mapped[Project] = relationship(back_populates="requirements")


# ---------------------------------------------------------------------------
# Systems under test
# ---------------------------------------------------------------------------


class System(Base, TimestampMixin, GovernedArtifactMixin):
    """AI System Card (section 12)."""

    __tablename__ = "systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="llm")
    vendor: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="systems")
    versions: Mapped[list[SystemVersion]] = relationship(
        back_populates="system", cascade="all, delete-orphan", order_by="SystemVersion.created_at"
    )


class SystemVersion(Base, TimestampMixin):
    """An immutable configuration snapshot.

    Every result references one of these, which is what makes a run
    reproducible (section 51) and a score traceable (section 72).
    """

    __tablename__ = "system_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    system_id: Mapped[str] = mapped_column(ForeignKey("systems.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)

    model_provider: Mapped[str | None] = mapped_column(String(128))
    model_name: Mapped[str | None] = mapped_column(String(255))
    model_version: Mapped[str | None] = mapped_column(String(128))
    architecture: Mapped[str | None] = mapped_column(String(255))
    hosting_location: Mapped[str | None] = mapped_column(String(255))

    connector_type: Mapped[str] = mapped_column(String(64), default="echo")
    endpoint: Mapped[str | None] = mapped_column(String(1024))
    # Secret material is referenced, never stored inline.
    credential_ref: Mapped[str | None] = mapped_column(String(255))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)

    system_prompt: Mapped[str | None] = mapped_column(Text)
    weights_available: Mapped[bool] = mapped_column(Boolean, default=False)
    fine_tuned: Mapped[bool] = mapped_column(Boolean, default=False)
    training_data_notes: Mapped[str | None] = mapped_column(Text)

    rag_architecture: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    retrieval_source: Mapped[str | None] = mapped_column(String(255))
    tool_access: Mapped[list] = mapped_column(JSON, default=list)
    agent_capabilities: Mapped[list] = mapped_column(JSON, default=list)
    guardrails: Mapped[list] = mapped_column(JSON, default=list)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    data_flows: Mapped[list] = mapped_column(JSON, default=list)

    change_note: Mapped[str | None] = mapped_column(Text)
    config_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    system: Mapped[System] = relationship(back_populates="versions")


# ---------------------------------------------------------------------------
# Datasets and scenarios
# ---------------------------------------------------------------------------


class Dataset(Base, TimestampMixin, GovernedArtifactMixin):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(32), default="text")
    split: Mapped[str] = mapped_column(String(32), default="test")
    contains_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Which subject-matter expertise is needed to judge these cases. Empty means
    # the program has not said -- which the review queue reports as unknown
    # rather than treating as "anyone will do".
    required_expertise: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped[Project] = relationship(back_populates="datasets")
    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class DatasetVersion(Base, TimestampMixin):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    source_format: Mapped[str] = mapped_column(String(32), default="jsonl")
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    generation_note: Mapped[str | None] = mapped_column(Text)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    items: Mapped[list[DatasetItem]] = relationship(
        back_populates="dataset_version", cascade="all, delete-orphan"
    )


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    dataset_version_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")

    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="items")


class Scenario(Base, TimestampMixin, GovernedArtifactMixin):
    """The fundamental test object (section 15)."""

    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Library scenarios are shared; project_id is set when the scenario is local.
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    mission: Mapped[str | None] = mapped_column(String(512))
    task: Mapped[str | None] = mapped_column(String(512))
    context: Mapped[str | None] = mapped_column(Text)

    input: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_behavior: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_behavior: Mapped[list] = mapped_column(JSON, default=list)
    rubric: Mapped[str | None] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    reference_sources: Mapped[list] = mapped_column(JSON, default=list)

    difficulty: Mapped[str] = mapped_column(String(32), default="standard")
    threat_type: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32), default="1")
    # Overrides the dataset's declaration when set on the scenario itself.
    required_expertise: Mapped[list] = mapped_column(JSON, default=list)
    # The body of government knowledge this problem tests -- "Source selection
    # (FAR 15.3)", "Bid protests". What a weakness is found in, what expert
    # time is spent on, and what a delivery is binned by. Null means nobody
    # said, which is reported as undeclared rather than guessed from tags.
    knowledge_area: Mapped[str | None] = mapped_column(String(255), index=True)
    # Generated scenarios stay drafts until a human approves them (section 17).
    approved: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    # Null for library scenarios, set for project-local ones.
    project: Mapped[Project | None] = relationship()


# ---------------------------------------------------------------------------
# Evaluation library and plans
# ---------------------------------------------------------------------------


class Evaluation(Base, TimestampMixin):
    """A reusable evaluation definition (section 14)."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    layer: Mapped[str] = mapped_column(String(32), default="model")
    domain: Mapped[str] = mapped_column(String(32), default="performance")
    system_types: Mapped[list] = mapped_column(JSON, default=list)
    mission_applicability: Mapped[list] = mapped_column(JSON, default=list)

    # One evaluation may carry several evaluators -- section 21 requires
    # multiple independent evidence sources for high-risk claims.
    evaluators: Mapped[list] = mapped_column(JSON, default=list)
    aggregation: Mapped[str] = mapped_column(String(32), default="all_must_pass")

    metric: Mapped[str | None] = mapped_column(String(128))
    # Thresholds always belong to the customer's plan (section 34). A library
    # default is a suggestion the plan must explicitly adopt.
    default_threshold: Mapped[dict] = mapped_column(JSON, default=dict)
    scenario_selector: Mapped[dict] = mapped_column(JSON, default=dict)
    dataset_ref: Mapped[str | None] = mapped_column(String(255))

    framework_refs: Mapped[list] = mapped_column(JSON, default=list)
    risk_refs: Mapped[list] = mapped_column(JSON, default=list)
    pack_key: Mapped[str | None] = mapped_column(String(128), index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(32), default="1")
    content_hash: Mapped[str] = mapped_column(String(64), default="")


class EvaluationPlan(Base, TimestampMixin):
    """Section 13 -- a drafted, human-editable T&E strategy."""

    __tablename__ = "evaluation_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    generated_from: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[EvaluationPlanItem]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class EvaluationPlanItem(Base, TimestampMixin):
    __tablename__ = "evaluation_plan_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_plans.id", ondelete="CASCADE"), index=True
    )
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="SET NULL")
    )
    # The plan owns the threshold, not the library entry.
    threshold: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text)
    included: Mapped[bool] = mapped_column(Boolean, default=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped[EvaluationPlan] = relationship(back_populates="items")
    evaluation: Mapped[Evaluation] = relationship()


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class Campaign(Base, TimestampMixin):
    """A bounded execution of a set of evaluations against target systems."""

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_plans.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default="evaluation")
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.QUEUED)
    # What triggered this campaign (section 33).
    trigger: Mapped[str] = mapped_column(String(64), default="manual")
    trigger_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    # For regression campaigns: the campaign this one is compared against.
    baseline_campaign_id: Mapped[str | None] = mapped_column(String(36))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="campaigns")
    runs: Mapped[list[Run]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class Run(Base, TimestampMixin):
    """One evaluation executed against one system version.

    The `reproducibility` column captures the full section 51 record.
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    evaluation_id: Mapped[str] = mapped_column(ForeignKey("evaluations.id", ondelete="CASCADE"))
    system_version_id: Mapped[str] = mapped_column(
        ForeignKey("system_versions.id", ondelete="CASCADE"), index=True
    )
    dataset_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    plan_item_id: Mapped[str | None] = mapped_column(String(36))

    status: Mapped[str] = mapped_column(String(32), default=RunStatus.QUEUED, index=True)
    threshold: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    # pass | warning | fail | not_evaluated -- the run-level verdict.
    verdict: Mapped[str] = mapped_column(String(32), default=ResultStatus.NOT_EVALUATED)
    reproducibility: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    scenario_count: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    warned: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    pending_human: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    campaign: Mapped[Campaign] = relationship(back_populates="runs")
    evaluation: Mapped[Evaluation] = relationship()
    system_version: Mapped[SystemVersion] = relationship()
    results: Mapped[list[Result]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Result(Base):
    """One scenario executed once, with its judgements."""

    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), index=True
    )
    dataset_item_id: Mapped[str | None] = mapped_column(String(36))

    status: Mapped[str] = mapped_column(String(32), default=ResultStatus.NOT_EVALUATED, index=True)
    score: Mapped[float | None] = mapped_column(Float)

    request: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    # Observable execution trace -- tool calls, retrieval, timings. Hidden model
    # chain-of-thought is deliberately not required or stored (section 25).
    trace: Mapped[list] = mapped_column(JSON, default=list)
    retrieval: Mapped[dict] = mapped_column(JSON, default=dict)

    # One entry per evaluator that judged this result (section 21).
    judgements: Mapped[list] = mapped_column(JSON, default=list)
    attack: Mapped[dict] = mapped_column(JSON, default=dict)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    repetition: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)

    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[Run] = relationship(back_populates="results")
    scenario: Mapped[Scenario | None] = relationship()


class Evidence(Base):
    """An immutable artifact backing a result (section 52)."""

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    result_id: Mapped[str | None] = mapped_column(
        ForeignKey("results.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64), default="transcript")
    label: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128), default="application/json")
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    inline: Mapped[dict] = mapped_column(JSON, default=dict)
    sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(64), default=Classification.UNCLASSIFIED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HumanReview(Base, TimestampMixin):
    """A human judgement recorded against a result (section 20)."""

    __tablename__ = "human_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    result_id: Mapped[str] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_label: Mapped[str | None] = mapped_column(String(255))
    rubric_key: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default=ResultStatus.PASS)
    comments: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)

    # The authority the judgement was made under. A review with no expertise
    # behind it is still recorded -- it is an opinion, and suppressing it would
    # be worse -- but `qualified` is what decides whether it counts as expert
    # evidence. See ExpertProfile.
    expert_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("expert_profiles.id", ondelete="SET NULL")
    )
    expertise: Mapped[str | None] = mapped_column(String(128))
    # The reviewer's own rating of how familiar they are with THIS item, which
    # is not the same as holding the credential in general.
    familiarity: Mapped[float | None] = mapped_column(Float)
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Why it was or was not counted, in words, so the evidence explains itself.
    qualification_note: Mapped[str | None] = mapped_column(Text)

    expert_profile: Mapped[ExpertProfile | None] = relationship()


class ExpertProfile(Base, TimestampMixin):
    """A reviewer's declared subject-matter expertise (section 20).

    The product records who judged an output and on what authority, because a
    human judgement is only evidence to the extent the judge was qualified to
    make it. An unverified profile is usable and says so; verification is an
    organisational act, recorded with who performed it.
    """

    __tablename__ = "expert_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Free-form discipline slugs; see enums.Discipline for the suggested set.
    disciplines: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str | None] = mapped_column(String(255))
    organization: Mapped[str | None] = mapped_column(String(255))
    credentials: Mapped[str | None] = mapped_column(Text)
    years_experience: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User | None] = relationship()


class HumanStudySession(Base, TimestampMixin):
    """Human systems integration measurement (sections 26, P2)."""

    __tablename__ = "human_study_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    operator_label: Mapped[str] = mapped_column(String(255))
    task_key: Mapped[str | None] = mapped_column(String(128))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    time_to_complete_seconds: Mapped[int | None] = mapped_column(Integer)
    operator_confidence: Mapped[float | None] = mapped_column(Float)
    system_correct: Mapped[bool | None] = mapped_column(Boolean)
    operator_accepted: Mapped[bool | None] = mapped_column(Boolean)
    interventions: Mapped[int] = mapped_column(Integer, default=0)
    overrides: Mapped[int] = mapped_column(Integer, default=0)
    errors_detected: Mapped[int] = mapped_column(Integer, default=0)
    workload_score: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Capture and delivery
# ---------------------------------------------------------------------------


class ReasoningTrace(Base, TimestampMixin, GovernedArtifactMixin):
    """An expert working a problem, step by step, in their own words.

    This is the thing the platform exists to collect. A score on a model's
    answer says the answer was wrong; a trace says how someone qualified gets
    it right -- which rule applies, what they checked, in what order, and why.

    It is human reasoning, written for the record. Model chain-of-thought is a
    different thing and is still never requested or stored (section 25).

    The problem is snapshotted at capture. A scenario can be edited later; the
    trace answers the problem as it stood when the expert read it, and the
    content hash covers that snapshot.
    """

    __tablename__ = "reasoning_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), index=True
    )
    # The model answer the expert was shown, when the trace corrects one.
    result_id: Mapped[str | None] = mapped_column(
        ForeignKey("results.id", ondelete="SET NULL"), index=True
    )
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_label: Mapped[str | None] = mapped_column(String(255))

    # Copied from the scenario, so a later edit to the scenario does not move
    # a trace between delivery bins after it was delivered.
    knowledge_area: Mapped[str | None] = mapped_column(String(255), index=True)
    problem: Mapped[dict] = mapped_column(JSON, default=dict)
    # [{"text": "...", "basis": "FAR 15.306(d)"}], in the order worked.
    steps: Mapped[list] = mapped_column(JSON, default=list)
    final_answer: Mapped[str] = mapped_column(Text, default="")
    sources: Mapped[list] = mapped_column(JSON, default=list)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)
    # The expert's own confidence in their answer, 0-1. Unset is unknown.
    confidence: Mapped[float | None] = mapped_column(Float)
    contains_pii: Mapped[bool] = mapped_column(Boolean, default=False)

    # Same rule as a human review: recorded regardless, counted only when the
    # author was qualified for this problem.
    expert_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("expert_profiles.id", ondelete="SET NULL")
    )
    expertise: Mapped[str | None] = mapped_column(String(128))
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    qualification_note: Mapped[str | None] = mapped_column(Text)

    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)

    expert_profile: Mapped[ExpertProfile | None] = relationship()


class DataPackage(Base, TimestampMixin):
    """A delivery to a customer's ingest pipeline.

    Built once and stored, never regenerated: what was sent is what the record
    shows, and the digest proves it. Everything that was considered and left
    out is counted by reason in the manifest, so "the package has 40 records"
    can always be read against how many it could have had and why it did not.
    """

    __tablename__ = "data_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer: Mapped[str | None] = mapped_column(String(255))
    # What was asked for: knowledge areas, record kinds, project.
    selection: Mapped[dict] = mapped_column(JSON, default=dict)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    # Counts per bin, per kind, and per exclusion reason.
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    media_type: Mapped[str] = mapped_column(String(128), default="application/x-ndjson")
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(64), default=Classification.UNCLASSIFIED)
    created_by: Mapped[str | None] = mapped_column(String(255))


# ---------------------------------------------------------------------------
# Findings, risks, assurance
# ---------------------------------------------------------------------------


class Finding(Base, TimestampMixin):
    """A failure promoted to a first-class, ownable object (section 27)."""

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    domain: Mapped[str | None] = mapped_column(String(32), index=True)
    cluster_key: Mapped[str | None] = mapped_column(String(128), index=True)

    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"))
    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluations.id", ondelete="SET NULL")
    )
    system_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("system_versions.id", ondelete="SET NULL")
    )
    result_ids: Mapped[list] = mapped_column(JSON, default=list)

    expected_behavior: Mapped[str | None] = mapped_column(Text)
    actual_behavior: Mapped[str | None] = mapped_column(Text)
    root_cause_hypothesis: Mapped[str | None] = mapped_column(Text)
    reproduction: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[str | None] = mapped_column(String(255))
    mitigation: Mapped[str | None] = mapped_column(Text)
    mitigation_status: Mapped[str] = mapped_column(String(32), default="pending")
    retest_required: Mapped[bool] = mapped_column(Boolean, default=True)
    retest_run_id: Mapped[str | None] = mapped_column(String(36))
    retest_status: Mapped[str | None] = mapped_column(String(32))
    framework_refs: Mapped[list] = mapped_column(JSON, default=list)


class Risk(Base, TimestampMixin):
    """Section 28. Scoring comes from the organization's matrix."""

    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    mission_impact: Mapped[str | None] = mapped_column(Text)

    probability: Mapped[str | None] = mapped_column(String(32))
    consequence: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str | None] = mapped_column(String(32), index=True)
    score: Mapped[float | None] = mapped_column(Float)

    finding_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)
    mitigation: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="identified", index=True)
    residual_probability: Mapped[str | None] = mapped_column(String(32))
    residual_consequence: Mapped[str | None] = mapped_column(String(32))
    residual_severity: Mapped[str | None] = mapped_column(String(32))
    acceptance_authority: Mapped[str | None] = mapped_column(String(255))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssuranceCase(Base, TimestampMixin):
    """Section 29."""

    __tablename__ = "assurance_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    system_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("system_versions.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    decision_authority: Mapped[str | None] = mapped_column(String(255))
    residual_risk_statement: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    claims: Mapped[list[AssuranceClaim]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class AssuranceClaim(Base, TimestampMixin):
    __tablename__ = "assurance_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("assurance_cases.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("assurance_claims.id", ondelete="CASCADE"), index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    argument: Mapped[str | None] = mapped_column(Text)
    # supported | partially_supported | unsupported | not_evaluated
    support_status: Mapped[str] = mapped_column(String(32), default=ResultStatus.NOT_EVALUATED)
    confidence_note: Mapped[str | None] = mapped_column(Text)
    known_limitations: Mapped[list] = mapped_column(JSON, default=list)
    mitigations: Mapped[list] = mapped_column(JSON, default=list)
    requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="SET NULL")
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    case: Mapped[AssuranceCase] = relationship(back_populates="claims")
    evidence_links: Mapped[list[AssuranceEvidenceLink]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class AssuranceEvidenceLink(Base):
    """Ties a claim to the run, finding or artifact that supports it."""

    __tablename__ = "assurance_evidence_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("assurance_claims.id", ondelete="CASCADE"), index=True
    )
    # run | finding | evidence | result | human_review | external
    ref_type: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[str] = mapped_column(String(36))
    note: Mapped[str | None] = mapped_column(Text)
    # Whether this evidence supports or counters the claim.
    stance: Mapped[str] = mapped_column(String(16), default="supports")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    claim: Mapped[AssuranceClaim] = relationship(back_populates="evidence_links")


# ---------------------------------------------------------------------------
# Gates, framework mapping, audit
# ---------------------------------------------------------------------------


class Gate(Base, TimestampMixin):
    """Deployment gate (section 34). Criteria are always customer-defined."""

    __tablename__ = "gates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str] = mapped_column(String(64), default="production")
    criteria: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    defined_by: Mapped[str | None] = mapped_column(String(255))


class GateCheck(Base):
    __tablename__ = "gate_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    gate_id: Mapped[str] = mapped_column(ForeignKey("gates.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    system_version_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), default="not_evaluated")
    criteria_results: Mapped[list] = mapped_column(JSON, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FrameworkRequirement(Base, TimestampMixin):
    """A reference from an external framework (section 37)."""

    __tablename__ = "framework_requirements"
    __table_args__ = (UniqueConstraint("framework", "ref", name="uq_framework_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    framework: Mapped[str] = mapped_column(String(128), index=True)
    framework_version: Mapped[str | None] = mapped_column(String(64))
    ref: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    text: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1024))
    # Whether satisfying a mapped evaluation can be claimed as compliance.
    # Defaults to False: the platform reports coverage, not compliance.
    compliance_claimable: Mapped[bool] = mapped_column(Boolean, default=False)


class ContinuousTrigger(Base, TimestampMixin):
    """Section 33 -- what causes an evaluation suite to re-run."""

    __tablename__ = "continuous_triggers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    # model_update | prompt_update | corpus_update | release | drift |
    # schedule | security_finding | operator_complaint
    event: Mapped[str] = mapped_column(String(64), index=True)
    plan_id: Mapped[str | None] = mapped_column(String(36))
    evaluation_keys: Mapped[list] = mapped_column(JSON, default=list)
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Append-only audit log (section 50).

    `prev_hash`/`hash` chain the records so tampering inside the application is
    detectable. Rows are never updated or deleted through the API.
    """

    __tablename__ = "audit_events"

    # `sequence` is the primary key so the database supplies a monotonically
    # increasing ordering natively (AUTOINCREMENT on SQLite, a sequence on
    # Postgres). The chain in `audit.verify_chain` is walked in this order.
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    actor_label: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(128), index=True)
    object_type: Mapped[str] = mapped_column(String(64), index=True)
    object_id: Mapped[str | None] = mapped_column(String(36), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="", index=True)


class Report(Base, TimestampMixin):
    """A generated artifact (sections 40, 41)."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    format: Mapped[str] = mapped_column(String(16), default="markdown")
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    body: Mapped[str] = mapped_column(Text, default="")
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64), default="")
    classification: Mapped[str] = mapped_column(String(64), default=Classification.UNCLASSIFIED)
    generated_by: Mapped[str | None] = mapped_column(String(255))


class Pack(Base, TimestampMixin):
    """An installed evaluation / attack / framework pack (sections 38, 39, 61)."""

    __tablename__ = "packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="evaluation")
    version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    publisher: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
