/**
 * The sample's state, and how it is seeded for any step.
 *
 * Lives in memory, and in this tab's sessionStorage so a refresh keeps it.
 * Clearing it is dropping it: there is nothing on the server to undo, because
 * nothing in the sample is ever sent there.
 */

import type { Effect } from "../types";
import {
  SAMPLE_PROFILE,
  SCENARIOS,
  TARGET_SCENARIO,
  WORKED_EXAMPLE,
  freshSample,
  type SampleResult,
  type SampleScenario,
  type SampleTrace,
} from "./fixtures";
import { contentHash } from "./sha256";

export interface SamplePackage {
  id: string;
  name: string;
  customer: string | null;
  selection: { knowledge_areas: string[]; include_traces: boolean; include_scored_responses: boolean };
  record_count: number;
  manifest: {
    schema: string;
    confident_at: number;
    kinds: Record<string, number>;
    bins: Array<{ knowledge_area: string | null; model_outcome: string; kind: string; records: number }>;
    excluded: Array<{ reason: string; label: string; records: number }>;
  };
  body: string;
  sha256: string;
  size_bytes: number;
  classification: string;
  created_by: string | null;
  created_at: string;
}

export interface SandboxData {
  version: 1;
  scenarios: SampleScenario[];
  results: SampleResult[];
  traces: SampleTrace[];
  packages: SamplePackage[];
  /** Screen state a step needs that has no request behind it, e.g. the
   *  "Trace recorded" panel a presenter lands on after jumping past step 5. */
  ui: Record<string, unknown>;
  seq: number;
}

/** The problem as the expert is shown it, which is also what a trace hashes. */
export function problemOf(scenario: SampleScenario) {
  return {
    scenario_key: scenario.key,
    scenario_version: 1,
    scenario_hash: contentHash({ key: scenario.key, prompt: scenario.prompt, documents: scenario.documents }),
    title: scenario.title,
    task: scenario.task,
    context: scenario.context,
    prompt: scenario.prompt,
    documents: scenario.documents,
  };
}

export function traceHash(trace: Pick<SampleTrace, "scenario_id" | "steps" | "final_answer" | "sources" | "result_id">): string {
  const scenario = SCENARIOS.find((s) => s.id === trace.scenario_id);
  return contentHash({
    problem: scenario ? problemOf(scenario) : null,
    steps: trace.steps,
    final_answer: trace.final_answer,
    sources: trace.sources,
    result_id: trace.result_id,
  });
}

/** A fresh sample, with the state the given effects leave behind. */
export function seed(effects: Effect[] = []): SandboxData {
  const sample = freshSample();
  const data: SandboxData = {
    version: 1,
    scenarios: sample.scenarios,
    results: sample.results,
    traces: sample.traces.map((trace) => ({ ...trace, content_hash: traceHash(trace) })),
    packages: [],
    ui: {},
    seq: 0,
  };
  for (const effect of effects) applyEffect(data, effect);
  return data;
}

export function nextId(data: SandboxData, prefix: string): string {
  data.seq += 1;
  return `sample-${prefix}-${String(data.seq).padStart(3, "0")}`;
}

/** Record the viewer's own trace on the target problem, the way step 5 of the
 *  expert path would have. */
export function recordViewerTrace(
  data: SandboxData,
  input: {
    scenario_id: string;
    steps: Array<{ text: string; basis: string | null }>;
    final_answer: string;
    sources: string[];
    result_id: string | null;
    time_spent_seconds: number | null;
    confidence: number | null;
    expertise: string | null;
    contains_pii: boolean;
  },
  now: string = new Date().toISOString(),
): SampleTrace | { error: string } {
  const scenario = data.scenarios.find((s) => s.id === input.scenario_id);
  if (!scenario) return { error: "That is not here." };
  if (!input.steps.length || input.steps.some((s) => !s.text.trim())) {
    return { error: "A step cannot be blank." };
  }
  const { qualified, note } = qualify(scenario.required_expertise, input.expertise);
  const trace: SampleTrace = {
    id: nextId(data, "trace"),
    scenario_id: scenario.id,
    result_id: input.result_id,
    author: "you",
    by_viewer: true,
    knowledge_area: scenario.knowledge_area,
    steps: input.steps,
    final_answer: input.final_answer,
    sources: input.sources,
    time_spent_seconds: input.time_spent_seconds,
    confidence: input.confidence,
    expertise: input.expertise,
    qualified,
    qualification_note: note,
    classification: scenario.classification,
    contains_pii: input.contains_pii,
    content_hash: "",
    created_at: now,
  };
  trace.content_hash = traceHash(trace);
  data.traces.push(trace);
  return trace;
}

const LABELS: Record<string, string> = {
  acquisition: "Acquisition & contracting",
  legal: "Legal & compliance",
};

/** The server's qualification rule (aegis/expertise.py), for the one profile
 *  the sample has. */
export function qualify(required: string[], submittedUnder: string | null): { qualified: boolean; note: string } {
  const held = SAMPLE_PROFILE.disciplines;
  const label = (key: string) => LABELS[key] ?? key.replace(/_/g, " ");
  const list = (keys: string[]) => keys.map(label).join(", ");
  if (!required.length) {
    return { qualified: true, note: "No expertise requirement is declared for this item, so none was checked." };
  }
  if (submittedUnder && !held.includes(submittedUnder)) {
    return {
      qualified: false,
      note: `Submitted under ${label(submittedUnder)}, which is not on the reviewer's profile (${list(held)}).`,
    };
  }
  if (submittedUnder && !required.includes(submittedUnder)) {
    return { qualified: false, note: `Submitted under ${label(submittedUnder)}; this item needs ${list(required)}.` };
  }
  const overlap = held.filter((d) => required.includes(d));
  if (!overlap.length) {
    return { qualified: false, note: `The reviewer's expertise (${list(held)}) does not cover ${list(required)}.` };
  }
  let note = `Reviewer holds ${list(overlap)}.`;
  if (!SAMPLE_PROFILE.verified) note += " Profile is self-declared and has not been verified.";
  return { qualified: true, note };
}

export function covers(required: string[]): boolean {
  return qualify(required, null).qualified;
}

/** When state a jump sets up is said to have happened. Fixed, so a step set
 *  up twice is set up identically. */
const SEEDED_AT = "2026-09-26T09:00:00Z";

export function applyEffect(data: SandboxData, effect: Effect): void {
  switch (effect) {
    case "expert.trace-recorded": {
      if (data.traces.some((t) => t.by_viewer && t.scenario_id === TARGET_SCENARIO)) return;
      const trace = recordViewerTrace(data, {
        scenario_id: TARGET_SCENARIO,
        steps: WORKED_EXAMPLE.steps,
        final_answer: WORKED_EXAMPLE.answer,
        sources: WORKED_EXAMPLE.sources,
        result_id: null,
        time_spent_seconds: 420,
        confidence: 0.9,
        expertise: "acquisition",
        contains_pii: false,
      }, SEEDED_AT);
      if (!("error" in trace)) data.ui[`solve.saved:${TARGET_SCENARIO}`] = trace;
      return;
    }
    case "lead.package-built":
      // Nothing after the last step reads this; recorded so a jump past the
      // end is still well defined.
      data.ui["lead.package-built"] = true;
      return;
  }
}

/* ------------------------------------------------------------------ *
 * Persistence (this tab only)
 * ------------------------------------------------------------------ */

const SESSION_KEY = "aegis.tour.sample";

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function saveSnapshot(storage: KeyValueStore | null, data: SandboxData | null): void {
  if (!storage) return;
  try {
    if (data) storage.setItem(SESSION_KEY, JSON.stringify(data));
    else storage.removeItem(SESSION_KEY);
  } catch {
    /* storage full or blocked: the sample simply will not survive a reload */
  }
}

export function loadSnapshot(storage: KeyValueStore | null): SandboxData | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SandboxData;
    if (parsed?.version !== 1 || !Array.isArray(parsed.scenarios) || !Array.isArray(parsed.traces)) return null;
    return parsed;
  } catch {
    return null;
  }
}
