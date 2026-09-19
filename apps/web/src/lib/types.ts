/** Shapes returned by the Aegis API. */

export type ResultStatus =
  | "pass"
  | "warning"
  | "fail"
  | "error"
  | "not_evaluated"
  | "pending_human";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface Project {
  id: string;
  name: string;
  slug: string;
  classification: string;
  impact_level: string | null;
  status: string;
  description?: string | null;
  deployment_environment?: string | null;
  system_owner?: string | null;
  evaluation_owner?: string | null;
}

export interface ReadinessDimension {
  domain: string;
  label: string;
  status: ResultStatus;
  evaluations: number;
  executions: number;
  passed: number;
  failed: number;
  warning: number;
  pending_human: number;
  pass_rate: number | null;
  run_ids: string[];
}

export interface ProjectDashboard {
  project: Project;
  mission: {
    mission: string;
    tasks: string[];
    users: string[];
    unacceptable_failures: string[];
    latency_requirement_ms: number | null;
  } | null;
  systems: Array<{
    system: string;
    system_id: string;
    kind: string;
    version_id: string;
    version: string;
    model_name: string | null;
    model_provider: string | null;
    connector: string;
    config_hash: string;
  }>;
  latest_campaign: {
    id: string;
    name: string;
    status: string;
    trigger: string;
    summary: CampaignSummary;
    completed_at: string | null;
  } | null;
  readiness: ReadinessDimension[];
  findings: Record<Severity, number>;
  findings_total: number;
  regression: {
    baseline_campaign: { id: string; name: string };
    candidate_campaign: { id: string; name: string };
    totals: { new_failures: number; resolved: number; degraded: number; improved: number };
    regression_detected: boolean;
  } | null;
  inventory: {
    scenarios: number;
    scenarios_awaiting_approval: number;
    datasets: number;
    campaigns: number;
  };
  note: string;
}

export interface CampaignSummary {
  executed: number;
  passed: number;
  warning: number;
  failed: number;
  errors: number;
  pending_human: number;
  runs: number;
  domains: Record<
    string,
    {
      runs: number;
      executed: number;
      passed: number;
      failed: number;
      warning: number;
      pending_human: number;
      status: ResultStatus;
      pass_rate: number | null;
    }
  >;
  findings: Record<Severity, number>;
}

export interface Campaign {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  kind: string;
  status: string;
  trigger: string;
  baseline_campaign_id: string | null;
  summary: CampaignSummary;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Run {
  id: string;
  campaign_id: string;
  evaluation_id: string;
  system_version_id: string;
  status: string;
  verdict: ResultStatus;
  threshold: Record<string, unknown>;
  metrics: Record<string, unknown>;
  scenario_count: number;
  passed: number;
  warned: number;
  failed: number;
  errored: number;
  pending_human: number;
  duration_ms: number | null;
  error: string | null;
  evaluation?: EvaluationBrief | null;
  system_version?: SystemVersionBrief | null;
}

export interface EvaluationBrief {
  id: string;
  key: string;
  name: string;
  layer: string;
  domain: string;
  metric: string | null;
  aggregation: string;
  evaluators: string[];
  framework_refs: string[];
}

export interface SystemVersionBrief {
  id: string;
  label: string;
  system_id: string | null;
  model_name: string | null;
  config_hash: string;
}

export interface Judgement {
  evaluator_key: string;
  kind: string;
  status: ResultStatus;
  score: number | null;
  rationale: string | null;
  evaluator_metadata: Record<string, unknown>;
  confidence: number | null;
  error: string | null;
}

export interface Result {
  id: string;
  run_id: string;
  scenario_id: string | null;
  status: ResultStatus;
  score: number | null;
  request: { prompt?: string; documents?: Array<Record<string, unknown>>; system_prompt?: string };
  response: { text?: string; latency_ms?: number; retrieved?: Array<Record<string, unknown>> };
  trace: Array<Record<string, unknown>>;
  retrieval: Record<string, unknown>;
  judgements: Judgement[];
  latency_ms: number | null;
  repetition: number;
  error: string | null;
  content_hash: string;
  created_at: string;
}

export interface ResultDetail {
  result: Result;
  run: Run | null;
  evaluation: EvaluationBrief | null;
  system_version: SystemVersionBrief | null;
  scenario: {
    id: string;
    key: string;
    title: string;
    expected_behavior: string[];
    prohibited_behavior: string[];
    rubric: string | null;
    content_hash: string;
  } | null;
  evidence: Array<{
    id: string;
    kind: string;
    label: string | null;
    sha256: string;
    size_bytes: number;
    storage_uri: string | null;
  }>;
  human_reviews: Array<{
    id: string;
    status: string;
    score: number | null;
    comments: string | null;
    confidence: number | null;
    reviewer_label: string | null;
  }>;
  reproducibility: Record<string, unknown>;
}

export interface Finding {
  id: string;
  project_id: string;
  key: string;
  title: string;
  severity: Severity;
  status: string;
  domain: string | null;
  cluster_key: string | null;
  run_id: string | null;
  result_ids: string[];
  expected_behavior: string | null;
  actual_behavior: string | null;
  root_cause_hypothesis: string | null;
  reproduction: Record<string, any>;
  owner: string | null;
  mitigation: string | null;
  mitigation_status: string;
  retest_required: boolean;
  retest_status: string | null;
  framework_refs: string[];
  created_at: string;
}

export interface ComparisonRow {
  evaluation_id: string;
  evaluation_key: string;
  evaluation_name: string;
  domain: string;
  domain_label: string;
  layer: string;
  metric: string | null;
  cells: Array<{
    run_id?: string;
    status: ResultStatus;
    pass_rate?: number | null;
    passed?: number;
    failed?: number;
    warning?: number;
    pending_human?: number;
    executions?: number;
    latency_ms?: number | null;
    scores?: Record<string, number>;
    note?: string;
  }>;
}

export interface Comparison {
  campaign_id: string;
  campaign_name?: string;
  systems: Array<{ id: string; label: string; model?: string | null; config_hash?: string }>;
  rows: ComparisonRow[];
  note: string;
}

export interface AssuranceClaim {
  id: string;
  statement: string;
  argument: string | null;
  support_status: ResultStatus;
  confidence_note: string | null;
  known_limitations: string[];
  mitigations: string[];
  requirement: { id: string; key: string; statement: string } | null;
  evidence: Array<{
    id: string;
    ref_type: string;
    ref_id: string;
    stance: "supports" | "counters" | "inconclusive";
    note: string | null;
    detail: Record<string, any>;
  }>;
  children: AssuranceClaim[];
}

export interface FrameworkCoverageRow {
  framework: string;
  ref: string;
  title: string;
  status: ResultStatus;
  compliance_claimable: boolean;
  evidence: Array<{
    run_id: string;
    evaluation_key: string;
    evaluation_name: string;
    verdict: ResultStatus;
    executions: number;
    passed: number;
    failed: number;
  }>;
}

export interface Overview {
  counts: Record<string, number>;
  findings: Record<Severity, number>;
  risks: { total: number; accepted: number; open: number };
  evidence_coverage: {
    projects_with_complete_chain: number;
    projects: number;
    ratio: number | null;
    definition: string;
  };
  projects: Array<{
    id: string;
    name: string;
    slug: string;
    classification: string;
    impact_level: string | null;
    status: string;
    open_findings: number;
    critical_findings: number;
  }>;
}
