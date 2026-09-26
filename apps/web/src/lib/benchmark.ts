/** Types and formatting for the benchmark pages. The shapes mirror
 *  `aegis/routers/benchmarks.py` and `aegis/benchmark.py`. */

export interface BenchmarkSummary {
  id: string;
  title: string;
  created_at: string;
  sha256: string;
  classification: string;
  project: { id: string; name: string; description: string | null };
  demonstration: boolean;
  models: number;
  conditions: string[];
  questions: number;
  criteria: number;
  required_expertise: string[];
  published_at: string | null;
  top: Array<{ model: string; condition: string; pass_rate: number | null }>;
}

export interface Tally {
  criteria_passed: number;
  criteria_judged: number;
  criteria_not_judged: number;
  criteria_total: number;
  questions: number;
  pass_rate: number | null;
}

export interface LeaderRow extends Tally {
  model: string;
  condition: string;
  provider: string | null;
  cost_per_test: number | null;
  results_without_cost: number;
  latency_ms_median: number | null;
  errors: number;
}

export interface FacetValue extends Tally {
  value: string;
  enough_questions: boolean;
  by_system: Record<string, number | null>;
}

export interface Verdict {
  verdict: "pass" | "fail" | "not_evaluated" | string;
  rationale: string | null;
}

export interface BenchmarkData {
  campaigns: Array<{ id?: string; name: string }>;
  demonstration: Array<{ statement?: string; stand_ins?: string[]; simulated_reviewer?: boolean }>;
  models: string[];
  conditions: string[];
  leaderboard: LeaderRow[];
  condition_effects: Array<{ condition: string; models_compared: number; mean_change: number | null }>;
  facets: Record<string, FacetValue[]>;
  dataset: {
    questions: number;
    criteria: number;
    criteria_per_question: number | null;
    splits: Record<string, number>;
    packs: string[];
    approved_by: string[];
    questions_without_named_approver: number;
    model_drafted: number;
    required_expertise: string[];
  };
  judge: { models: string[]; modes: string[] };
  judge_alignment: {
    true_pass: number;
    true_fail: number;
    false_pass: number;
    false_fail: number;
    comparisons: number;
    criteria_compared: number;
    experts: number;
    accuracy: number | null;
    false_pass_rate: number | null;
    unqualified_reviews_excluded: number;
  };
  example: {
    result_id?: string;
    content_hash: string;
    title: string | null;
    question: string | null;
    answer: string | null;
    model: string;
    condition: string;
    criteria: Array<{ id: string; text: string } & Verdict>;
  } | null;
  results_scored: number;
  calibration_results: number;
  results_without_criteria_scores: number;
}

export interface QuestionRow {
  key: string;
  title: string;
  knowledge_area: string | null;
  facets: Record<string, string>;
  question: string | null;
  criteria: Array<{ id: string; text: string }>;
  results: Record<
    string,
    {
      model: string;
      condition: string;
      /** Absent on the public page, which never links into the app. */
      result_id?: string;
      content_hash: string;
      answer: string | null;
      verdicts: Record<string, Verdict>;
    }
  >;
}

export interface BenchmarkDetail extends BenchmarkSummary {
  data: BenchmarkData;
  question_rows: QuestionRow[];
}

export function pct(value: number | null | undefined): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

export function points(value: number | null | undefined): string {
  return typeof value === "number" ? `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pts` : "—";
}

export function verdictLabel(verdict: string): string {
  return verdict === "pass" ? "Met" : verdict === "fail" ? "Not met" : "Not judged";
}
