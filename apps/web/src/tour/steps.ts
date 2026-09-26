/**
 * How each step is wired: what it points at, where it happens, and what the
 * reader has to do for it to count. The words are in copy.ts.
 *
 * Every step is finished by something the reader does in the product -- a
 * page they open, a control they use, a request that succeeds -- never by a
 * "Next" in the popover.
 */

import { SOURCE_SELECTION, TARGET_SCENARIO, WORKED_EXAMPLE } from "./sandbox/fixtures";
import type { PathDef, PathId, StepDef } from "./types";

const AREA = encodeURIComponent(SOURCE_SELECTION);
const PROBLEM = `/capture/${TARGET_SCENARIO}`;
const ON_PROBLEM = new RegExp(`^/capture/${TARGET_SCENARIO}(\\?|$)`);

/** Anchors are `data-tour` attribute values. A trailing `:value` names one
 *  instance of a repeated element, e.g. one row of a table. */
export const anchor = {
  openNav: "shell.open-nav",
  nav: (slug: string) => `nav.${slug}`,
  threshold: (value: string) => `weakness.threshold.${value}`,
  area: (knowledgeArea: string) => `weakness.area:${knowledgeArea}`,
  areaTable: "weakness.table",
  task: (scenarioId: string) => `capture.task:${scenarioId}`,
  document: (index: number) => `solve.document:${index}`,
  steps: "solve.steps",
  record: "solve.record",
  modelAnswer: "solve.model-answer",
  packageForm: "packages.new",
  packageBuild: "packages.build",
} as const;

const lead: StepDef[] = [
  {
    id: "open-map",
    anchors: [anchor.nav("weakness"), anchor.openNav],
    at: /^/,
    route: "/",
    done: { route: /^\/weakness(\?|$)/ },
    assist: [{ navigate: "/weakness" }],
  },
  {
    id: "raise-bar",
    anchors: [anchor.threshold("0.9")],
    at: /^\/weakness(\?|$)/,
    route: "/weakness",
    done: { signal: "weakness.threshold:0.9" },
    keep: [anchor.areaTable],
    assist: [{ click: anchor.threshold("0.9") }],
  },
  {
    id: "pick-area",
    anchors: [anchor.area(SOURCE_SELECTION)],
    at: /^\/weakness(\?|$)/,
    route: "/weakness",
    done: { route: /^\/capture\?(.*&)?area=Source/ },
    keep: [anchor.areaTable],
    assist: [{ click: anchor.area(SOURCE_SELECTION) }],
  },
  {
    id: "open-problem",
    anchors: [anchor.task(TARGET_SCENARIO)],
    at: /^\/capture(\?|$)/,
    route: `/capture?area=${AREA}`,
    done: { route: ON_PROBLEM },
    assist: [{ click: anchor.task(TARGET_SCENARIO) }],
  },
  {
    id: "see-answer",
    anchors: [anchor.modelAnswer],
    at: ON_PROBLEM,
    route: PROBLEM,
    done: { signal: "solve.model-answer:opened" },
    assist: [{ click: anchor.modelAnswer }],
  },
  {
    id: "build-package",
    // On Packages, the form. Anywhere else, the way to Packages.
    anchors: [anchor.packageForm, anchor.nav("packages"), anchor.openNav],
    at: /^/,
    route: "/packages",
    done: { request: "POST /data-packages" },
    assist: [
      { navigate: "/packages" },
      {
        command: "packages.fill",
        payload: {
          name: "Source selection, confidently wrong",
          customer: "Lab A (sample)",
          knowledge_areas: [SOURCE_SELECTION],
        },
      },
      { click: anchor.packageBuild },
    ],
    leaves: ["lead.package-built"],
  },
];

const expert: StepDef[] = [
  {
    id: "open-solve",
    anchors: [anchor.nav("capture"), anchor.openNav],
    at: /^/,
    route: "/",
    done: { route: /^\/capture(\?|$)/ },
    assist: [{ navigate: "/capture" }],
  },
  {
    id: "pick-problem",
    anchors: [anchor.task(TARGET_SCENARIO)],
    at: /^\/capture(\?|$)/,
    route: "/capture",
    done: { route: ON_PROBLEM },
    assist: [{ click: anchor.task(TARGET_SCENARIO) }],
  },
  {
    id: "read-material",
    anchors: [anchor.document(0)],
    at: ON_PROBLEM,
    route: PROBLEM,
    done: { signal: "solve.document:opened" },
    assist: [{ click: anchor.document(0) }],
  },
  {
    id: "write-step",
    anchors: [anchor.steps],
    at: ON_PROBLEM,
    route: PROBLEM,
    done: { signal: "solve.step-written" },
    assist: [{ command: "solve.fill-example", payload: WORKED_EXAMPLE }],
  },
  {
    id: "record",
    anchors: [anchor.record],
    at: ON_PROBLEM,
    route: PROBLEM,
    done: { request: "POST /reasoning-traces" },
    assist: [
      { command: "solve.fill-example", payload: WORKED_EXAMPLE },
      { click: anchor.record },
    ],
    leaves: ["expert.trace-recorded"],
  },
  {
    id: "compare",
    anchors: [anchor.modelAnswer],
    at: ON_PROBLEM,
    route: PROBLEM,
    done: { signal: "solve.model-answer:opened" },
    assist: [{ click: anchor.modelAnswer }],
  },
];

export const PATHS: Record<PathId, PathDef> = {
  lead: { id: "lead", steps: lead },
  expert: { id: "expert", steps: expert },
};

/** Which path a reader starts on, from what their account can do. A lead
 *  decides where expert hours go; an expert spends them. Either can switch. */
export function defaultPath(can: (permission: string) => boolean): PathId {
  if (can("org:administer") || can("project:write")) return "lead";
  if (can("human:score")) return "expert";
  return "lead";
}
