/**
 * The sample's answers to the requests the tour's screens make.
 *
 * Each handler mirrors the server's rule for that endpoint (targeting.py,
 * routers/capture.py, routers/delivery.py) closely enough that what the reader
 * does in the sample changes what they see the way it would for real: record
 * a trace and the weakness map counts it; build a package and the manifest
 * counts what was left out and why.
 *
 * Anything not handled here is refused, never forwarded. A sample that fell
 * through to the server for the requests it did not know would mix the two on
 * one screen, which is the one thing it must not do.
 */

import { DISCIPLINES, SAMPLE_PROFILE, type SampleResult } from "./fixtures";
import { canonicalJson, contentHash, sha256Hex } from "./sha256";
import {
  covers,
  nextId,
  problemOf,
  recordViewerTrace,
  type SamplePackage,
  type SandboxData,
} from "./store";

export interface SandboxResponse {
  status: number;
  body?: unknown;
  /** Raw text for a download. */
  text?: string;
  headers?: Record<string, string>;
}

export const NOT_IN_SAMPLE =
  "Not part of the sample. Exit the tour to see your own data.";

const CONFIDENT_AT = 0.8;
const UNDECLARED = "Not declared";

/* ------------------------------------------------------------------ *
 * Outcomes, as targeting.Outcome computes them
 * ------------------------------------------------------------------ */

interface Outcome {
  passed: number;
  failed: number;
  warned: number;
  unresolved: number;
  confident_wrong: number;
  unsure_wrong: number;
  confidence_unknown_wrong: number;
}

function emptyOutcome(): Outcome {
  return {
    passed: 0,
    failed: 0,
    warned: 0,
    unresolved: 0,
    confident_wrong: 0,
    unsure_wrong: 0,
    confidence_unknown_wrong: 0,
  };
}

function add(outcome: Outcome, result: SampleResult, confidentAt: number): void {
  if (result.status === "pass") outcome.passed += 1;
  else if (result.status === "warning") outcome.warned += 1;
  else if (result.status === "fail") {
    outcome.failed += 1;
    if (result.confidence === null) outcome.confidence_unknown_wrong += 1;
    else if (result.confidence >= confidentAt) outcome.confident_wrong += 1;
    else outcome.unsure_wrong += 1;
  } else outcome.unresolved += 1;
}

function label(outcome: Outcome): "failed" | "passed" | "not_evaluated" {
  if (outcome.failed) return "failed";
  if (outcome.passed || outcome.warned) return "passed";
  return "not_evaluated";
}

function outcomes(data: SandboxData, confidentAt: number): Map<string, Outcome> {
  const out = new Map<string, Outcome>();
  for (const result of data.results) {
    const entry = out.get(result.scenario_id) ?? emptyOutcome();
    add(entry, result, confidentAt);
    out.set(result.scenario_id, entry);
  }
  return out;
}

function areaOf(data: SandboxData, scenarioId: string): string | null {
  return data.scenarios.find((s) => s.id === scenarioId)?.knowledge_area ?? null;
}

/* ------------------------------------------------------------------ *
 * Endpoints
 * ------------------------------------------------------------------ */

function weaknessMap(data: SandboxData, confidentAt: number) {
  type Row = {
    outcome: Outcome;
    scenarios: Set<string>;
    failed: Set<string>;
    traced: Set<string>;
    traces: number;
    qualified: number;
    seconds: number;
    untimed: number;
  };
  const rows = new Map<string | null, Row>();
  const row = (area: string | null) => {
    let entry = rows.get(area);
    if (!entry) {
      entry = {
        outcome: emptyOutcome(),
        scenarios: new Set(),
        failed: new Set(),
        traced: new Set(),
        traces: 0,
        qualified: 0,
        seconds: 0,
        untimed: 0,
      };
      rows.set(area, entry);
    }
    return entry;
  };

  let withConfidence = 0;
  const sources: Record<string, number> = {};
  for (const result of data.results) {
    const entry = row(areaOf(data, result.scenario_id));
    add(entry.outcome, result, confidentAt);
    entry.scenarios.add(result.scenario_id);
    if (result.status === "fail") entry.failed.add(result.scenario_id);
    if (result.confidence !== null) {
      withConfidence += 1;
      const source = result.confidence_source ?? "unspecified";
      sources[source] = (sources[source] ?? 0) + 1;
    }
  }
  for (const trace of data.traces) {
    const entry = row(trace.knowledge_area);
    entry.traces += 1;
    if (trace.qualified) {
      entry.qualified += 1;
      entry.traced.add(trace.scenario_id);
      if (trace.time_spent_seconds === null) entry.untimed += 1;
      else entry.seconds += trace.time_spent_seconds;
    }
  }

  const areas = Array.from(rows.entries()).map(([area, entry]) => {
    const o = entry.outcome;
    return {
      knowledge_area: area,
      label: area ?? UNDECLARED,
      declared: area !== null,
      results: o.passed + o.failed + o.warned + o.unresolved,
      ...o,
      scenarios: entry.scenarios.size,
      failed_scenarios: entry.failed.size,
      failed_without_trace: Array.from(entry.failed).filter((id) => !entry.traced.has(id)).length,
      traces: entry.traces,
      qualified_traces: entry.qualified,
      expert_seconds: entry.seconds,
      traces_without_time: entry.untimed,
    };
  });
  areas.sort(
    (a, b) =>
      Number(!a.declared) - Number(!b.declared) ||
      b.confident_wrong - a.confident_wrong ||
      b.failed - a.failed ||
      a.label.toLowerCase().localeCompare(b.label.toLowerCase()),
  );

  return {
    confident_at: confidentAt,
    areas,
    results: data.results.length,
    confidence: {
      with_confidence: withConfidence,
      without_confidence: data.results.length - withConfidence,
      sources,
    },
  };
}

function captureTasks(data: SandboxData, query: URLSearchParams) {
  const scope = query.get("scope") ?? "mine";
  const area = query.get("knowledge_area");
  const confidentAt = Number(query.get("confident_at") ?? CONFIDENT_AT);
  const byScenario = outcomes(data, confidentAt);

  let scenarios = data.scenarios;
  if (area === "") scenarios = scenarios.filter((s) => !s.knowledge_area);
  else if (area !== null) scenarios = scenarios.filter((s) => s.knowledge_area === area);

  const rows = scenarios
    .map((scenario) => {
      const qualifiedViewer = covers(scenario.required_expertise);
      const outcome = byScenario.get(scenario.id) ?? emptyOutcome();
      const mine = data.traces.filter((t) => t.scenario_id === scenario.id);
      const qualified = mine.filter((t) => t.qualified).length;
      return {
        row: {
          scenario_id: scenario.id,
          key: scenario.key,
          title: scenario.title,
          task: scenario.task,
          knowledge_area: scenario.knowledge_area,
          required_expertise: scenario.required_expertise,
          viewer_is_qualified: qualifiedViewer,
          model: { ...outcome, outcome: label(outcome) },
          traces: mine.length,
          qualified_traces: qualified,
          traced_by_me: mine.some((t) => t.by_viewer),
        },
        priority: [
          qualified > 0 ? 1 : 0,
          { failed: 0, not_evaluated: 1, passed: 2 }[label(outcome)],
          -outcome.confident_wrong,
          -outcome.failed,
        ],
        include: scope !== "mine" || qualifiedViewer,
      };
    })
    .filter((entry) => entry.include);

  rows.sort((a, b) => {
    for (let i = 0; i < a.priority.length; i++) {
      if (a.priority[i] !== b.priority[i]) return a.priority[i] - b.priority[i];
    }
    return a.row.title.toLowerCase().localeCompare(b.row.title.toLowerCase());
  });

  return {
    confident_at: confidentAt,
    has_profile: true,
    tasks: rows.map((entry) => entry.row),
    total: rows.length,
  };
}

function captureTask(data: SandboxData, scenarioId: string, confidentAt: number): SandboxResponse {
  const scenario = data.scenarios.find((s) => s.id === scenarioId);
  if (!scenario) return { status: 404, body: { detail: NOT_IN_SAMPLE } };
  const outcome = emptyOutcome();
  const results = data.results
    .filter((r) => r.scenario_id === scenarioId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  for (const result of results) add(outcome, result, confidentAt);
  return {
    status: 200,
    body: {
      scenario_id: scenario.id,
      knowledge_area: scenario.knowledge_area,
      required_expertise: scenario.required_expertise,
      viewer_is_qualified: covers(scenario.required_expertise),
      has_profile: true,
      problem: problemOf(scenario),
      model: { ...outcome, outcome: label(outcome) },
      model_answers: results
        .filter((r) => r.status === "fail")
        .slice(0, 5)
        .map((r) => ({
          result_id: r.id,
          text: r.text,
          confidence: r.confidence,
          confidence_source: r.confidence_source,
          created_at: r.created_at,
        })),
      confident_at: confidentAt,
    },
  };
}

const EXCLUSION_LABELS: Record<string, string> = {
  contains_pii: "Flagged as containing personal information",
  not_qualified: "Author was not qualified for the problem",
  not_unclassified: "Marked anything other than UNCLASSIFIED",
};

function buildPackage(data: SandboxData, input: Record<string, unknown>): SandboxResponse {
  const name = String(input.name ?? "").trim();
  if (!name) return { status: 422, body: { detail: "A package needs a name." } };
  const areas = Array.isArray(input.knowledge_areas) ? (input.knowledge_areas as string[]).map((a) => a.trim()) : [];
  const includeTraces = input.include_traces !== false;
  const includeScored = input.include_scored_responses !== false;
  const selected = (area: string | null) => !areas.length || areas.includes(area ?? "");

  const byScenario = outcomes(data, CONFIDENT_AT);
  const excluded: Record<string, number> = {};
  const records: Array<Record<string, unknown>> = [];

  if (includeTraces) {
    for (const trace of data.traces) {
      if (!selected(trace.knowledge_area)) continue;
      const reason = !trace.qualified
        ? "not_qualified"
        : trace.classification.trim().toUpperCase() !== "UNCLASSIFIED"
          ? "not_unclassified"
          : trace.contains_pii
            ? "contains_pii"
            : null;
      if (reason) {
        excluded[reason] = (excluded[reason] ?? 0) + 1;
        continue;
      }
      const outcome = byScenario.get(trace.scenario_id) ?? emptyOutcome();
      const record: Record<string, unknown> = {
        kind: "reasoning_trace",
        id: trace.id,
        knowledge_area: trace.knowledge_area,
        steps: trace.steps,
        final_answer: trace.final_answer,
        sources: trace.sources,
        expert: { pseudonym: trace.by_viewer ? "expert-you-sample" : trace.author, discipline: trace.expertise },
        expert_confidence: trace.confidence,
        time_spent_seconds: trace.time_spent_seconds,
        shown_model_answer: Boolean(trace.result_id),
        model_outcome: label(outcome),
        model_confidently_wrong: outcome.confident_wrong > 0,
        trace_hash: trace.content_hash,
        sample: true,
      };
      record.record_sha256 = contentHash(record);
      records.push(record);
    }
  }
  // Scored model answers come only from results a person reviewed. The sample
  // has no reviews, so this adds nothing -- the same as the server would.
  void includeScored;

  if (!records.length) {
    const considered = Object.entries(excluded)
      .sort()
      .map(([reason, count]) => `${count} ${EXCLUSION_LABELS[reason].toLowerCase()}`)
      .join(", ");
    return {
      status: 422,
      body: {
        detail:
          "Nothing in this selection can be delivered. " +
          (considered ? `Left out: ${considered}.` : "Nothing matched it at all."),
      },
    };
  }

  const bins = new Map<string, { knowledge_area: string | null; model_outcome: string; kind: string; records: number }>();
  const kinds: Record<string, number> = {};
  for (const record of records) {
    const key = JSON.stringify([record.knowledge_area, record.model_outcome, record.kind]);
    const bin = bins.get(key) ?? {
      knowledge_area: record.knowledge_area as string | null,
      model_outcome: record.model_outcome as string,
      kind: record.kind as string,
      records: 0,
    };
    bin.records += 1;
    bins.set(key, bin);
    kinds[record.kind as string] = (kinds[record.kind as string] ?? 0) + 1;
  }

  const body = records.map((record) => canonicalJson(record) + "\n").join("");
  const pkg: SamplePackage = {
    id: nextId(data, "package"),
    name,
    customer: String(input.customer ?? "").trim() || null,
    selection: { knowledge_areas: areas, include_traces: includeTraces, include_scored_responses: includeScored },
    record_count: records.length,
    manifest: {
      schema: "aegis.data-package/v1",
      confident_at: CONFIDENT_AT,
      kinds,
      bins: Array.from(bins.values()).sort(
        (a, b) =>
          (a.knowledge_area ?? "￿").localeCompare(b.knowledge_area ?? "￿") ||
          a.model_outcome.localeCompare(b.model_outcome) ||
          a.kind.localeCompare(b.kind),
      ),
      excluded: Object.entries(excluded)
        .sort()
        .map(([reason, count]) => ({ reason, label: EXCLUSION_LABELS[reason], records: count })),
    },
    body,
    sha256: sha256Hex(body),
    size_bytes: new TextEncoder().encode(body).length,
    classification: "UNCLASSIFIED",
    created_by: "you (sample)",
    created_at: new Date().toISOString(),
  };
  data.packages.unshift(pkg);
  return { status: 201, body: withoutBody(pkg) };
}

function withoutBody(pkg: SamplePackage) {
  const { body: _body, ...rest } = pkg;
  return rest;
}

function dashboard(data: SandboxData) {
  const failures = data.results.filter((r) => r.status === "fail").length;
  const awaiting = data.results.filter((r) => r.status === "pending_human").length;
  return {
    counts: {
      projects: 1,
      systems: 1,
      campaigns: 1,
      executions: data.results.length,
      failures,
      awaiting_human_review: awaiting,
    },
    findings: { critical: 0, high: 0, medium: 0, low: 0 },
    risks: { total: 0, accepted: 0, open: 0 },
    evidence_coverage: {
      projects_with_complete_chain: 0,
      projects: 1,
      ratio: 0,
      definition:
        "A project counts when it has a mission profile, executed evaluations, an assurance case, and no unresolved critical finding.",
    },
    projects: [
      {
        id: "sample-project",
        name: "Sample: contracting assistant",
        slug: "sample-contracting-assistant",
        classification: "UNCLASSIFIED",
        impact_level: null,
        status: "active",
        open_findings: 0,
        critical_findings: 0,
      },
    ],
  };
}

/* ------------------------------------------------------------------ *
 * Router
 * ------------------------------------------------------------------ */

export function handle(data: SandboxData, method: string, url: string, body?: unknown): SandboxResponse {
  const [pathname, search = ""] = url.split("?");
  const query = new URLSearchParams(search);
  const verb = method.toUpperCase();
  const confidentAt = Number(query.get("confident_at") ?? CONFIDENT_AT);

  if (verb === "GET") {
    if (pathname === "/weakness-map") return { status: 200, body: weaknessMap(data, confidentAt) };
    if (pathname === "/capture/tasks") return { status: 200, body: captureTasks(data, query) };
    const task = /^\/capture\/tasks\/([^/]+)$/.exec(pathname);
    if (task) return captureTask(data, decodeURIComponent(task[1]), confidentAt);
    if (pathname === "/expert-profiles/me") return { status: 200, body: SAMPLE_PROFILE };
    if (pathname === "/disciplines") return { status: 200, body: { disciplines: DISCIPLINES, extensible: true } };
    if (pathname === "/data-packages") return { status: 200, body: data.packages.map(withoutBody) };
    const download = /^\/data-packages\/([^/]+)\/download$/.exec(pathname);
    if (download) {
      const pkg = data.packages.find((p) => p.id === download[1]);
      if (!pkg) return { status: 404, body: { detail: NOT_IN_SAMPLE } };
      return {
        status: 200,
        text: pkg.body,
        headers: {
          "Content-Type": "application/x-ndjson",
          "Content-Disposition": `attachment; filename="${pkg.name} (sample).jsonl"`,
          "X-Content-SHA256": pkg.sha256,
        },
      };
    }
    if (pathname === "/dashboard") return { status: 200, body: dashboard(data) };
    if (pathname === "/benchmarks") return { status: 200, body: [] };
    if (pathname === "/projects") return { status: 200, body: [] };
  }

  if (verb === "POST") {
    if (pathname === "/reasoning-traces") {
      const input = (body ?? {}) as Record<string, unknown>;
      const trace = recordViewerTrace(data, {
        scenario_id: String(input.scenario_id ?? ""),
        steps: ((input.steps as Array<{ text: string; basis: string | null }>) ?? []).map((s) => ({
          text: String(s.text ?? "").trim(),
          basis: s.basis ? String(s.basis).trim() || null : null,
        })),
        final_answer: String(input.final_answer ?? "").trim(),
        sources: ((input.sources as string[]) ?? []).map((s) => s.trim()).filter(Boolean),
        result_id: (input.result_id as string | null) ?? null,
        time_spent_seconds: (input.time_spent_seconds as number | null) ?? null,
        confidence: (input.confidence as number | null) ?? null,
        expertise: (input.expertise as string | null) ?? null,
        contains_pii: Boolean(input.contains_pii),
      });
      if ("error" in trace) return { status: 400, body: { detail: trace.error } };
      return { status: 201, body: trace };
    }
    if (pathname === "/data-packages") return buildPackage(data, (body ?? {}) as Record<string, unknown>);
  }

  return { status: 404, body: { detail: NOT_IN_SAMPLE } };
}
