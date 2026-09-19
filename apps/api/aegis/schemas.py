"""API request and response models."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .enums import Classification

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    """Shape check only.

    Deliberately not a public-internet email validator: disconnected and
    on-premises deployments legitimately use internal domains (.local, .mil
    enclave names, reserved TLDs) that such validators reject. Deliverability
    is not this system's concern -- identity is.
    """
    value = value.strip()
    if not _EMAIL_PATTERN.match(value):
        raise ValueError("Not a valid address. Expected the form name@domain.tld")
    return value.lower()


EmailAddress = Annotated[str, AfterValidator(_validate_email)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -- auth -------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str | None = None
    identity_provider: str
    is_active: bool


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[dict]
    permissions: list[str]


# -- tenancy ----------------------------------------------------------------


class OrganizationIn(BaseModel):
    name: str
    short_name: str | None = None
    default_classification: str = Classification.UNCLASSIFIED
    risk_scoring: dict = Field(default_factory=dict)


class OrganizationOut(ORMModel):
    id: str
    name: str
    short_name: str | None = None
    default_classification: str
    risk_scoring: dict
    created_at: datetime


class ProgramIn(BaseModel):
    organization_id: str
    name: str
    description: str | None = None
    program_office: str | None = None


class ProgramOut(ORMModel):
    id: str
    organization_id: str
    name: str
    description: str | None = None
    program_office: str | None = None


class ProjectIn(BaseModel):
    program_id: str
    name: str
    slug: str | None = None
    description: str | None = None
    capability_type: str | None = None
    impact_level: str | None = None
    data_classification: str | None = None
    deployment_environment: str | None = None
    system_owner: str | None = None
    evaluation_owner: str | None = None
    classification: str = Classification.UNCLASSIFIED


class ProjectOut(ORMModel):
    id: str
    program_id: str
    name: str
    slug: str
    description: str | None = None
    capability_type: str | None = None
    impact_level: str | None = None
    data_classification: str | None = None
    deployment_environment: str | None = None
    system_owner: str | None = None
    evaluation_owner: str | None = None
    classification: str
    status: str
    created_at: datetime


class MissionProfileIn(BaseModel):
    mission: str
    tasks: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)
    expected_decisions: list[str] = Field(default_factory=list)
    operational_environment: str | None = None
    expected_inputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    acceptable_errors: list[str] = Field(default_factory=list)
    unacceptable_failures: list[str] = Field(default_factory=list)
    adversaries: list[str] = Field(default_factory=list)
    environmental_constraints: list[str] = Field(default_factory=list)
    latency_requirement_ms: int | None = None
    information_sensitivity: str | None = None
    human_oversight: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    operating_assumptions: list[str] = Field(default_factory=list)


class MissionProfileOut(MissionProfileIn, ORMModel):
    id: str
    project_id: str
    updated_at: datetime


class RequirementIn(BaseModel):
    key: str
    statement: str
    source: str | None = None
    threshold: str | None = None
    objective: str | None = None
    domain: str | None = None


class RequirementOut(RequirementIn, ORMModel):
    id: str
    project_id: str


# -- systems ----------------------------------------------------------------


class SystemIn(BaseModel):
    name: str
    slug: str | None = None
    kind: str = "llm"
    vendor: str | None = None
    description: str | None = None
    classification: str = Classification.UNCLASSIFIED


class SystemOut(ORMModel):
    id: str
    project_id: str
    name: str
    slug: str
    kind: str
    vendor: str | None = None
    description: str | None = None
    classification: str
    created_at: datetime


class SystemVersionIn(BaseModel):
    version: str
    model_provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None
    architecture: str | None = None
    hosting_location: str | None = None
    connector_type: str = "echo"
    endpoint: str | None = None
    credential_ref: str | None = None
    parameters: dict = Field(default_factory=dict)
    system_prompt: str | None = None
    weights_available: bool = False
    fine_tuned: bool = False
    training_data_notes: str | None = None
    rag_architecture: dict = Field(default_factory=dict)
    embedding_model: str | None = None
    retrieval_source: str | None = None
    tool_access: list[dict] = Field(default_factory=list)
    agent_capabilities: list[str] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    data_flows: list[dict] = Field(default_factory=list)
    change_note: str | None = None


class SystemVersionOut(SystemVersionIn, ORMModel):
    id: str
    system_id: str
    config_hash: str
    is_current: bool
    created_at: datetime


# -- datasets and scenarios -------------------------------------------------


class DatasetIn(BaseModel):
    name: str
    description: str | None = None
    modality: str = "text"
    split: str = "test"
    contains_pii: bool = False
    tags: list[str] = Field(default_factory=list)
    classification: str = Classification.UNCLASSIFIED


class DatasetOut(ORMModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    modality: str
    split: str
    contains_pii: bool
    tags: list
    classification: str
    created_at: datetime


class DatasetVersionOut(ORMModel):
    id: str
    dataset_id: str
    version: str
    item_count: int
    source_format: str
    content_hash: str
    generated: bool
    is_current: bool
    quality_report: dict
    created_at: datetime


class ScenarioIn(BaseModel):
    key: str
    title: str
    mission: str | None = None
    task: str | None = None
    context: str | None = None
    input: dict = Field(default_factory=dict)
    expected_behavior: list[str] = Field(default_factory=list)
    prohibited_behavior: list[str] = Field(default_factory=list)
    rubric: str | None = None
    reference_answer: str | None = None
    reference_sources: list[dict] = Field(default_factory=list)
    difficulty: str = "standard"
    threat_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    classification: str = Classification.UNCLASSIFIED
    approved: bool = True


class ScenarioOut(ORMModel):
    id: str
    project_id: str | None = None
    key: str
    title: str
    mission: str | None = None
    task: str | None = None
    context: str | None = None
    input: dict
    expected_behavior: list
    prohibited_behavior: list
    rubric: str | None = None
    reference_answer: str | None = None
    difficulty: str
    threat_type: str | None = None
    tags: list
    source: str | None = None
    version: str
    approved: bool
    generated: bool
    classification: str
    content_hash: str


# -- evaluations ------------------------------------------------------------


class EvaluationIn(BaseModel):
    key: str
    name: str
    description: str | None = None
    layer: str = "model"
    domain: str = "performance"
    system_types: list[str] = Field(default_factory=list)
    mission_applicability: list[str] = Field(default_factory=list)
    evaluators: list[dict] = Field(default_factory=list)
    aggregation: str = "all_must_pass"
    metric: str | None = None
    default_threshold: dict = Field(default_factory=dict)
    scenario_selector: dict = Field(default_factory=dict)
    framework_refs: list[str] = Field(default_factory=list)


class EvaluationOut(ORMModel):
    id: str
    project_id: str | None = None
    key: str
    name: str
    description: str | None = None
    layer: str
    domain: str
    system_types: list
    evaluators: list
    aggregation: str
    metric: str | None = None
    default_threshold: dict
    scenario_selector: dict
    framework_refs: list
    pack_key: str | None = None
    provenance: dict
    version: str


class PlanItemIn(BaseModel):
    evaluation_id: str
    requirement_id: str | None = None
    threshold: dict = Field(default_factory=dict)
    rationale: str | None = None
    included: bool = True
    ordinal: int = 0


class PlanItemOut(ORMModel):
    id: str
    plan_id: str
    evaluation_id: str
    requirement_id: str | None = None
    threshold: dict
    rationale: str | None = None
    included: bool
    ordinal: int


class EvaluationPlanOut(ORMModel):
    id: str
    project_id: str
    name: str
    rationale: str | None = None
    status: str
    generated_from: dict
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class GeneratePlanRequest(BaseModel):
    system_version_id: str | None = None
    name: str | None = None


class ApprovePlanRequest(BaseModel):
    approved_by: str
    note: str | None = None


# -- campaigns and runs -----------------------------------------------------


class CampaignIn(BaseModel):
    name: str
    description: str | None = None
    kind: str = "evaluation"
    plan_id: str | None = None
    # Evaluations to run. Either names from the library, or everything in a plan.
    evaluation_ids: list[str] = Field(default_factory=list)
    evaluation_keys: list[str] = Field(default_factory=list)
    system_version_ids: list[str] = Field(default_factory=list)
    dataset_version_id: str | None = None
    baseline_campaign_id: str | None = None
    trigger: str = "manual"
    trigger_detail: dict = Field(default_factory=dict)
    # Connector configuration for the model-based judge, when one is used.
    judge: dict | None = None
    thresholds: dict[str, dict] = Field(default_factory=dict)


class CampaignOut(ORMModel):
    id: str
    project_id: str
    plan_id: str | None = None
    name: str
    description: str | None = None
    kind: str
    status: str
    trigger: str
    baseline_campaign_id: str | None = None
    summary: dict
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class RunOut(ORMModel):
    id: str
    campaign_id: str
    evaluation_id: str
    system_version_id: str
    dataset_version_id: str | None = None
    status: str
    verdict: str
    threshold: dict
    metrics: dict
    scenario_count: int
    passed: int
    warned: int
    failed: int
    errored: int
    pending_human: int
    duration_ms: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ResultOut(ORMModel):
    id: str
    run_id: str
    scenario_id: str | None = None
    status: str
    score: float | None = None
    request: dict
    response: dict
    trace: list
    retrieval: dict
    judgements: list
    latency_ms: int | None = None
    repetition: int
    error: str | None = None
    content_hash: str
    created_at: datetime


class HumanReviewIn(BaseModel):
    status: str
    score: float | None = None
    rubric_key: str | None = None
    comments: str | None = None
    confidence: float | None = None
    time_spent_seconds: int | None = None


class HumanReviewOut(HumanReviewIn, ORMModel):
    id: str
    result_id: str
    reviewer_label: str | None = None
    created_at: datetime


# -- findings, risks, assurance --------------------------------------------


class FindingIn(BaseModel):
    title: str
    severity: str = "medium"
    domain: str | None = None
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    root_cause_hypothesis: str | None = None
    owner: str | None = None
    mitigation: str | None = None


class FindingUpdate(BaseModel):
    title: str | None = None
    severity: str | None = None
    status: str | None = None
    owner: str | None = None
    root_cause_hypothesis: str | None = None
    mitigation: str | None = None
    mitigation_status: str | None = None
    retest_required: bool | None = None
    retest_status: str | None = None


class FindingOut(ORMModel):
    id: str
    project_id: str
    key: str
    title: str
    severity: str
    status: str
    domain: str | None = None
    cluster_key: str | None = None
    run_id: str | None = None
    evaluation_id: str | None = None
    system_version_id: str | None = None
    result_ids: list
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    root_cause_hypothesis: str | None = None
    reproduction: dict
    owner: str | None = None
    mitigation: str | None = None
    mitigation_status: str
    retest_required: bool
    retest_status: str | None = None
    framework_refs: list
    created_at: datetime


class RiskIn(BaseModel):
    title: str
    description: str | None = None
    mission_impact: str | None = None
    probability: str | None = None
    consequence: str | None = None
    finding_ids: list[str] = Field(default_factory=list)
    mitigation: str | None = None
    owner: str | None = None


class RiskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    probability: str | None = None
    consequence: str | None = None
    status: str | None = None
    mitigation: str | None = None
    owner: str | None = None
    residual_probability: str | None = None
    residual_consequence: str | None = None


class RiskAcceptIn(BaseModel):
    acceptance_authority: str
    residual_risk_statement: str | None = None


class RiskOut(ORMModel):
    id: str
    project_id: str
    key: str
    title: str
    description: str | None = None
    mission_impact: str | None = None
    probability: str | None = None
    consequence: str | None = None
    severity: str | None = None
    score: float | None = None
    finding_ids: list
    mitigation: str | None = None
    owner: str | None = None
    status: str
    residual_severity: str | None = None
    acceptance_authority: str | None = None
    accepted_at: datetime | None = None
    created_at: datetime


class AssuranceCaseIn(BaseModel):
    title: str
    context: str | None = None
    system_version_id: str | None = None
    decision_authority: str | None = None


class ClaimIn(BaseModel):
    statement: str
    argument: str | None = None
    parent_id: str | None = None
    requirement_id: str | None = None
    known_limitations: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    confidence_note: str | None = None
    ordinal: int = 0


class EvidenceLinkIn(BaseModel):
    ref_type: str
    ref_id: str
    note: str | None = None
    stance: str = "supports"


class AssuranceCaseOut(ORMModel):
    id: str
    project_id: str
    system_version_id: str | None = None
    title: str
    context: str | None = None
    status: str
    decision_authority: str | None = None
    residual_risk_statement: str | None = None
    accepted_at: datetime | None = None
    created_at: datetime


# -- gates, triggers, reports ----------------------------------------------


class GateIn(BaseModel):
    name: str
    description: str | None = None
    environment: str = "production"
    criteria: list[dict] = Field(default_factory=list)
    enabled: bool = True
    defined_by: str | None = None


class GateOut(GateIn, ORMModel):
    id: str
    project_id: str
    created_at: datetime


class TriggerIn(BaseModel):
    name: str
    event: str
    plan_id: str | None = None
    evaluation_keys: list[str] = Field(default_factory=list)
    schedule_cron: str | None = None
    enabled: bool = True


class TriggerOut(TriggerIn, ORMModel):
    id: str
    project_id: str
    last_fired_at: datetime | None = None


class ReportRequest(BaseModel):
    kind: str
    campaign_id: str | None = None
    plan_id: str | None = None
    assurance_case_id: str | None = None
    title: str | None = None


class ReportOut(ORMModel):
    id: str
    project_id: str
    kind: str
    title: str
    format: str
    scope: dict
    body: str
    sha256: str
    classification: str
    generated_by: str | None = None
    created_at: datetime


class AuditEventOut(ORMModel):
    id: str
    sequence: int
    actor_label: str | None = None
    action: str
    object_type: str
    object_id: str | None = None
    detail: dict
    created_at: datetime
    hash: str


class GenerateScenariosRequest(BaseModel):
    mode: str = "mission_expansion"
    count: int = 10
    generator: dict | None = None


class RedTeamRequest(BaseModel):
    attack_keys: list[str] = Field(default_factory=list)
    mission_tasks: list[str] = Field(default_factory=list)


class AdaptiveRedTeamRequest(BaseModel):
    attack_key: str
    system_version_id: str
    budget: int = 8
    stop_on_first_success: bool = True
    mission_task: str | None = None


class StatusResponse(BaseModel):
    status: str
    detail: Any = None
