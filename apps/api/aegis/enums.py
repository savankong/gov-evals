"""Controlled vocabularies.

These are plain string constants rather than database enums so that a customer
can extend a vocabulary (severity scales, classification banners, risk scoring)
without a schema migration. Section 28 of the PRD requires risk scoring to be
customisable per customer rather than imposed by the product.
"""

from __future__ import annotations


class TEVVLayer:
    """CDAO's four AI T&E framework areas (PRD section 8)."""

    MODEL = "model"
    HUMAN_SYSTEMS = "human_systems"
    SYSTEMS_INTEGRATION = "systems_integration"
    OPERATIONAL = "operational"

    ALL = [MODEL, HUMAN_SYSTEMS, SYSTEMS_INTEGRATION, OPERATIONAL]
    LABELS = {
        MODEL: "Model T&E",
        HUMAN_SYSTEMS: "Human Systems Integration T&E",
        SYSTEMS_INTEGRATION: "Systems Integration T&E",
        OPERATIONAL: "Operational T&E",
    }


class Domain:
    """Cross-cutting evaluation domains (PRD section 9)."""

    PERFORMANCE = "performance"
    RELIABILITY = "reliability"
    ROBUSTNESS = "robustness"
    SECURITY = "security"
    SAFETY = "safety"
    RESPONSIBLE_AI = "responsible_ai"
    HUMAN_FACTORS = "human_factors"
    MISSION_EFFECTIVENESS = "mission_effectiveness"
    INTEGRATION = "integration"
    RESILIENCE = "resilience"
    TRACEABILITY = "traceability"

    ALL = [
        PERFORMANCE,
        RELIABILITY,
        ROBUSTNESS,
        SECURITY,
        SAFETY,
        RESPONSIBLE_AI,
        HUMAN_FACTORS,
        MISSION_EFFECTIVENESS,
        INTEGRATION,
        RESILIENCE,
        TRACEABILITY,
    ]
    LABELS = {
        PERFORMANCE: "Performance",
        RELIABILITY: "Reliability",
        ROBUSTNESS: "Robustness",
        SECURITY: "Security",
        SAFETY: "Safety",
        RESPONSIBLE_AI: "Responsible AI",
        HUMAN_FACTORS: "Human Factors",
        MISSION_EFFECTIVENESS: "Mission Effectiveness",
        INTEGRATION: "Integration",
        RESILIENCE: "Resilience",
        TRACEABILITY: "Traceability",
    }


class Discipline:
    """Subject-matter expertise a reviewer judges under (section 20).

    Distinct from `Domain`, which says *what property* an evaluation measures.
    This says *who is qualified to judge it*. A contracting officer and a
    security engineer can both review the same output; only one of them is
    evidence about whether the contract analysis is correct.

    Deliberately a suggestion, not a closed set: expertise is program-specific
    and a customer must be able to add "targeteering" or "flight surgeon"
    without a schema migration. Anything stored here is a free-form slug.
    """

    ACQUISITION = "acquisition"
    INTELLIGENCE_ANALYSIS = "intelligence_analysis"
    LEGAL = "legal"
    CYBER = "cyber"
    LOGISTICS = "logistics"
    MEDICAL = "medical"
    LINGUISTICS = "linguistics"
    OPERATIONS = "operations"
    ENGINEERING = "engineering"
    POLICY = "policy"

    SUGGESTED = [
        ACQUISITION,
        INTELLIGENCE_ANALYSIS,
        LEGAL,
        CYBER,
        LOGISTICS,
        MEDICAL,
        LINGUISTICS,
        OPERATIONS,
        ENGINEERING,
        POLICY,
    ]
    LABELS = {
        ACQUISITION: "Acquisition & contracting",
        INTELLIGENCE_ANALYSIS: "Intelligence analysis",
        LEGAL: "Legal & compliance",
        CYBER: "Cybersecurity",
        LOGISTICS: "Logistics & sustainment",
        MEDICAL: "Medical",
        LINGUISTICS: "Language & translation",
        OPERATIONS: "Operations",
        ENGINEERING: "Systems engineering",
        POLICY: "Policy & governance",
    }

    @staticmethod
    def label(slug: str) -> str:
        """Label a slug, including one this vocabulary has never seen."""
        return Discipline.LABELS.get(slug, slug.replace("_", " ").strip().capitalize())


class ResultStatus:
    """Outcome of a single evaluated scenario.

    NOT_EVALUATED is a first-class value. PRD section 71: an untested property
    is never inferred to be a pass.
    """

    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    ERROR = "error"
    NOT_EVALUATED = "not_evaluated"
    PENDING_HUMAN = "pending_human"

    ALL = [PASS, WARNING, FAIL, ERROR, NOT_EVALUATED, PENDING_HUMAN]
    # Statuses that represent a completed, scoreable judgement.
    SCOREABLE = [PASS, WARNING, FAIL]


class RunStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_HUMAN = "awaiting_human"

    ALL = [QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED, AWAITING_HUMAN]
    TERMINAL = [COMPLETED, FAILED, CANCELLED]


class Severity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    ALL = [CRITICAL, HIGH, MEDIUM, LOW, INFO]
    ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4}


class FindingStatus:
    OPEN = "open"
    TRIAGED = "triaged"
    MITIGATING = "mitigating"
    RETEST = "awaiting_retest"
    RESOLVED = "resolved"
    ACCEPTED = "risk_accepted"
    FALSE_POSITIVE = "false_positive"

    ALL = [OPEN, TRIAGED, MITIGATING, RETEST, RESOLVED, ACCEPTED, FALSE_POSITIVE]
    ACTIVE = [OPEN, TRIAGED, MITIGATING, RETEST]


class RiskStatus:
    IDENTIFIED = "identified"
    ANALYSING = "analysing"
    MITIGATING = "mitigating"
    MONITORED = "monitored"
    ACCEPTED = "accepted"
    CLOSED = "closed"

    ALL = [IDENTIFIED, ANALYSING, MITIGATING, MONITORED, ACCEPTED, CLOSED]


class EvaluatorKind:
    DETERMINISTIC = "deterministic"
    MODEL_BASED = "model_based"
    HUMAN = "human"
    EXTERNAL_TOOL = "external_tool"
    COMPOSITE = "composite"

    ALL = [DETERMINISTIC, MODEL_BASED, HUMAN, EXTERNAL_TOOL, COMPOSITE]


class SystemKind:
    LLM = "llm"
    RAG = "rag"
    AGENT = "agent"
    MULTIMODAL = "multimodal"
    PREDICTIVE = "predictive"
    COMPUTER_VISION = "computer_vision"
    AUTONOMY = "autonomy"
    APPLICATION = "application"

    ALL = [LLM, RAG, AGENT, MULTIMODAL, PREDICTIVE, COMPUTER_VISION, AUTONOMY, APPLICATION]


class Classification:
    """Marking carried by every artifact. Customer-extensible."""

    UNCLASSIFIED = "UNCLASSIFIED"
    CUI = "CUI"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"
    TOP_SECRET = "TOP SECRET"

    ALL = [UNCLASSIFIED, CUI, CONFIDENTIAL, SECRET, TOP_SECRET]


class ImpactLevel:
    """DoD Cloud Computing SRG impact levels."""

    IL2 = "IL2"
    IL4 = "IL4"
    IL5 = "IL5"
    IL6 = "IL6"

    ALL = [IL2, IL4, IL5, IL6]


class Role:
    ORG_ADMIN = "org_admin"
    PROGRAM_ADMIN = "program_admin"
    TEST_LEAD = "test_lead"
    EVALUATOR = "evaluator"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    OPERATOR = "operator"
    READ_ONLY = "read_only"

    ALL = [
        ORG_ADMIN,
        PROGRAM_ADMIN,
        TEST_LEAD,
        EVALUATOR,
        DEVELOPER,
        REVIEWER,
        OPERATOR,
        READ_ONLY,
    ]


class Permission:
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    SYSTEM_WRITE = "system:write"
    DATASET_WRITE = "dataset:write"
    EVALUATION_WRITE = "evaluation:write"
    CAMPAIGN_EXECUTE = "campaign:execute"
    HUMAN_SCORE = "human:score"
    FINDING_WRITE = "finding:write"
    RISK_ACCEPT = "risk:accept"
    ASSURANCE_WRITE = "assurance:write"
    REPORT_GENERATE = "report:generate"
    ORG_ADMINISTER = "org:administer"

    ALL = [
        PROJECT_READ,
        PROJECT_WRITE,
        SYSTEM_WRITE,
        DATASET_WRITE,
        EVALUATION_WRITE,
        CAMPAIGN_EXECUTE,
        HUMAN_SCORE,
        FINDING_WRITE,
        RISK_ACCEPT,
        ASSURANCE_WRITE,
        REPORT_GENERATE,
        ORG_ADMINISTER,
    ]


# Default role -> permission map. Section 49 requires this to be configurable,
# so it is seeded into the database and edited there rather than hard-coded at
# the call sites.
DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.ORG_ADMIN: list(Permission.ALL),
    Role.PROGRAM_ADMIN: [
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.SYSTEM_WRITE,
        Permission.DATASET_WRITE,
        Permission.EVALUATION_WRITE,
        Permission.CAMPAIGN_EXECUTE,
        Permission.FINDING_WRITE,
        Permission.RISK_ACCEPT,
        Permission.ASSURANCE_WRITE,
        Permission.REPORT_GENERATE,
    ],
    Role.TEST_LEAD: [
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.SYSTEM_WRITE,
        Permission.DATASET_WRITE,
        Permission.EVALUATION_WRITE,
        Permission.CAMPAIGN_EXECUTE,
        Permission.HUMAN_SCORE,
        Permission.FINDING_WRITE,
        Permission.ASSURANCE_WRITE,
        Permission.REPORT_GENERATE,
    ],
    Role.EVALUATOR: [
        Permission.PROJECT_READ,
        Permission.DATASET_WRITE,
        Permission.EVALUATION_WRITE,
        Permission.CAMPAIGN_EXECUTE,
        Permission.HUMAN_SCORE,
        Permission.FINDING_WRITE,
    ],
    Role.DEVELOPER: [
        Permission.PROJECT_READ,
        Permission.SYSTEM_WRITE,
        Permission.DATASET_WRITE,
        Permission.EVALUATION_WRITE,
        Permission.CAMPAIGN_EXECUTE,
    ],
    Role.REVIEWER: [
        Permission.PROJECT_READ,
        Permission.HUMAN_SCORE,
        Permission.FINDING_WRITE,
        Permission.REPORT_GENERATE,
    ],
    Role.OPERATOR: [Permission.PROJECT_READ, Permission.HUMAN_SCORE],
    Role.READ_ONLY: [Permission.PROJECT_READ],
}
