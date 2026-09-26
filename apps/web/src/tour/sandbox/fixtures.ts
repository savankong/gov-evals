/**
 * The sample the tour runs on.
 *
 * Fictional, and says so wherever it is shown: every id starts with "sample-",
 * every document title ends "(sample)", and the banner stays up while any of it
 * is on screen. None of it is ever written to the server.
 *
 * It is shaped to make one point without being staged: Source selection is
 * where the model is wrong *and sure*, and it stays that way when the reader
 * raises the confidence bar, while Small business set-asides drops out. The
 * top problem is a real trap in FAR 15.306 -- letting one offeror in the
 * competitive range revise its price is discussions, not a clarification --
 * and the model's answer is the confident wrong one a contracting officer
 * would actually be handed.
 */

export type ResultStatus = "pass" | "fail" | "warning" | "not_evaluated" | "pending_human";

export interface SampleScenario {
  id: string;
  key: string;
  title: string;
  task: string;
  knowledge_area: string | null;
  required_expertise: string[];
  prompt: string;
  context: string | null;
  documents: Array<{ source_id: string | null; title: string | null; text: string | null }>;
  classification: string;
}

export interface SampleResult {
  id: string;
  scenario_id: string;
  status: ResultStatus;
  confidence: number | null;
  confidence_source: string | null;
  text: string | null;
  created_at: string;
}

export interface SampleTrace {
  id: string;
  scenario_id: string;
  result_id: string | null;
  author: string;
  by_viewer: boolean;
  knowledge_area: string | null;
  steps: Array<{ text: string; basis: string | null }>;
  final_answer: string;
  sources: string[];
  time_spent_seconds: number | null;
  confidence: number | null;
  expertise: string | null;
  qualified: boolean;
  qualification_note: string;
  classification: string;
  contains_pii: boolean;
  content_hash: string;
  created_at: string;
}

export const SOURCE_SELECTION = "Source selection (FAR 15.3)";
export const SET_ASIDES = "Small business set-asides (FAR 19)";
export const CONTRACT_TYPES = "Contract types (FAR 16)";
export const PROTESTS = "Bid protests (GAO)";

/** The problem both paths lead to. */
export const TARGET_SCENARIO = "sample-ss-discussions";

export const DISCIPLINES = [
  { key: "acquisition", label: "Acquisition & contracting" },
  { key: "intelligence_analysis", label: "Intelligence analysis" },
  { key: "legal", label: "Legal & compliance" },
  { key: "cyber", label: "Cybersecurity" },
  { key: "logistics", label: "Logistics" },
  { key: "medical", label: "Medical" },
  { key: "linguistics", label: "Linguistics" },
  { key: "operations", label: "Operations" },
  { key: "engineering", label: "Engineering" },
  { key: "policy", label: "Policy" },
];

const U = "UNCLASSIFIED";

function scenario(
  id: string,
  title: string,
  area: string | null,
  required: string[],
  prompt: string,
  extra: Partial<SampleScenario> = {},
): SampleScenario {
  return {
    id,
    key: id.replace(/^sample-/, ""),
    title,
    task: extra.task ?? (area ? area.replace(/ \(.*\)$/, "") : "Undeclared"),
    knowledge_area: area,
    required_expertise: required,
    prompt,
    context: extra.context ?? null,
    documents: extra.documents ?? [],
    classification: U,
  };
}

export const SCENARIOS: SampleScenario[] = [
  scenario(
    TARGET_SCENARIO,
    "Discussions with one offeror in a competitive range of three",
    SOURCE_SELECTION,
    ["acquisition"],
    "A best-value tradeoff has three offerors in the competitive range. The lowest-priced " +
      "offeror entered one labor rate per day instead of per hour. The contracting officer " +
      "wants to let that offeror alone fix the rate and lower its total price, then award to " +
      "it. May the contracting officer do this without contacting the other two offerors?",
    {
      task: "Exchanges with offerors",
      context:
        "Negotiated acquisition under FAR Part 15. The competitive range has been established.",
      documents: [
        {
          source_id: "SAMPLE-RFP-M.2",
          title: "Section M excerpt (sample)",
          text:
            "M.2 Basis for award. The Government intends to evaluate proposals and award a " +
            "contract without discussions with offerors (except clarifications as described " +
            "in FAR 15.306(a)). The Government reserves the right to conduct discussions if " +
            "the Contracting Officer later determines them to be necessary.",
        },
        {
          source_id: "SAMPLE-FILE-07",
          title: "Contracting officer's file note (sample)",
          text:
            "Competitive range established: Offerors A, B and C. Offeror C is lowest priced. " +
            "Its labor category 3 rate appears to be a daily rate entered in the hourly " +
            "column; corrected, C's total falls by about 6%. Intend to have C confirm and " +
            "correct, then proceed to award.",
        },
      ],
    },
  ),
  scenario(
    "sample-ss-clarification",
    "Is letting an offeror fix its price a clarification?",
    SOURCE_SELECTION,
    ["acquisition"],
    "The agency intends to award without discussions. It asks one offeror to correct a price " +
      "it believes is a clerical error. Is that a clarification under FAR 15.306(a)?",
    { task: "Exchanges with offerors" },
  ),
  scenario(
    "sample-ss-neutral-pp",
    "An offeror with no past performance record",
    SOURCE_SELECTION,
    ["acquisition"],
    "An offeror has no relevant past performance. May the agency rate it unfavourably on past " +
      "performance for that reason?",
    { task: "Past performance" },
  ),
  scenario(
    "sample-ss-tradeoff",
    "Paying more for a higher-rated proposal without a written rationale",
    SOURCE_SELECTION,
    ["acquisition"],
    "The source selection authority picks a higher-priced, higher-rated proposal and records " +
      "only the adjectival ratings. Is the award decision adequately documented?",
    { task: "Best-value tradeoff" },
  ),
  scenario(
    "sample-ss-unstated",
    "Evaluating on a factor not stated in Section M",
    SOURCE_SELECTION,
    ["acquisition"],
    "Evaluators downgrade a proposal for key-personnel turnover, which Section M does not " +
      "mention. Is that permissible?",
    { task: "Evaluation factors" },
  ),
  scenario(
    "sample-sb-rule-of-two",
    "Rule of two on a $180,000 services buy",
    SET_ASIDES,
    ["acquisition"],
    "Market research finds two capable small businesses for a $180,000 requirement. Must the " +
      "contracting officer set it aside?",
    { task: "Set-aside decisions" },
  ),
  scenario(
    "sample-sb-nonmanufacturer",
    "Nonmanufacturer rule on a supply set-aside",
    SET_ASIDES,
    ["acquisition"],
    "A small business dealer offers a large manufacturer's product on a total small business " +
      "set-aside. What must be true for the offer to be eligible?",
    { task: "Eligibility" },
  ),
  scenario(
    "sample-sb-sdvosb",
    "SDVOSB sole-source ceiling",
    SET_ASIDES,
    ["acquisition"],
    "What is the ceiling for a sole-source award to a service-disabled veteran-owned small " +
      "business for services?",
    { task: "Sole source" },
  ),
  scenario(
    "sample-bp-timeliness",
    "Timeliness of a pre-award protest",
    PROTESTS,
    ["legal"],
    "An offeror objects to an evaluation criterion apparent in the solicitation after the " +
      "closing date. Is a GAO protest timely?",
    { task: "Timeliness" },
  ),
  scenario(
    "sample-bp-stay",
    "The automatic stay after a required debriefing",
    PROTESTS,
    ["legal"],
    "How long after a required debriefing does a disappointed offeror have to file at GAO and " +
      "still trigger the automatic stay?",
    { task: "CICA stay" },
  ),
  scenario(
    "sample-ct-tm",
    "Time-and-materials without a determination and findings",
    CONTRACT_TYPES,
    ["acquisition"],
    "May a time-and-materials contract be awarded without a determination and findings?",
    { task: "Contract type selection" },
  ),
  scenario(
    "sample-ct-award-fee",
    "Award fee on a firm-fixed-price contract",
    CONTRACT_TYPES,
    ["acquisition"],
    "Can an award fee be added to a firm-fixed-price contract?",
    { task: "Incentives" },
  ),
  scenario(
    "sample-nd-card",
    "Splitting a purchase to stay under the micro-purchase threshold",
    null,
    [],
    "A requester asks to split a purchase into two card transactions to stay under the " +
      "micro-purchase threshold. Is that allowed?",
    { task: "Undeclared" },
  ),
];

const WRONG_DISCUSSIONS =
  "Yes. FAR 15.306(d) lets discussions be tailored to each offeror's proposal, so the " +
  "contracting officer may hold discussions with the lowest-priced offeror alone to correct " +
  "the pricing error and settle its price before award. The other offerors in the competitive " +
  "range do not need to be contacted, because their proposals do not contain the same error.";

let resultSeq = 0;
function r(
  scenarioId: string,
  status: ResultStatus,
  confidence: number | null = null,
  source: string | null = null,
  text: string | null = null,
): SampleResult {
  resultSeq += 1;
  const day = String(1 + (resultSeq % 20)).padStart(2, "0");
  return {
    id: `sample-result-${String(resultSeq).padStart(3, "0")}`,
    scenario_id: scenarioId,
    status,
    confidence,
    confidence_source: confidence === null ? null : source,
    text,
    created_at: `2026-09-${day}T14:${String(resultSeq % 60).padStart(2, "0")}:00Z`,
  };
}

function buildResults(): SampleResult[] {
  resultSeq = 0;
  const agree = "sample_agreement";
  const logprob = "logprob";
  return [
    // Source selection: wrong, and sure of it. Eight of nine still count as
    // confidently wrong at 0.9.
    r(TARGET_SCENARIO, "fail", 0.91, agree, WRONG_DISCUSSIONS),
    r(TARGET_SCENARIO, "fail", 0.92, agree, WRONG_DISCUSSIONS),
    r(TARGET_SCENARIO, "fail", 0.94, agree, WRONG_DISCUSSIONS),
    r("sample-ss-clarification", "fail", 0.93, agree, "Yes. Correcting a clerical price error is a clarification."),
    r("sample-ss-clarification", "fail", 0.9, agree, "Yes, as long as only the price changes."),
    r("sample-ss-clarification", "pass", 0.7, agree),
    r("sample-ss-neutral-pp", "fail", 0.95, agree, "Yes. No record is a performance risk and may be rated marginal."),
    r("sample-ss-neutral-pp", "pass", 0.8, agree),
    r("sample-ss-tradeoff", "fail", 0.88, agree, "Yes. The adjectival ratings document the tradeoff."),
    r("sample-ss-tradeoff", "fail", 0.97, agree, "Yes. Ratings are sufficient documentation."),
    r("sample-ss-unstated", "fail", 0.91, agree, "Yes. Key personnel stability is inherent in any services evaluation."),
    r("sample-ss-unstated", "pass", 0.6, agree),
    // Set-asides: wrong, but only fairly sure. Confident at 0.8, not at 0.9.
    r("sample-sb-rule-of-two", "fail", 0.84, logprob, "No. The rule of two applies only above the simplified acquisition threshold."),
    r("sample-sb-rule-of-two", "fail", 0.82, logprob, "No, set-aside is discretionary below $250,000."),
    r("sample-sb-rule-of-two", "pass", 0.77, logprob),
    r("sample-sb-nonmanufacturer", "fail", 0.86, logprob, "The dealer must have 500 or fewer employees; nothing else."),
    r("sample-sb-nonmanufacturer", "pass", 0.9, logprob),
    r("sample-sb-sdvosb", "fail", 0.55, logprob, "About $4 million."),
    r("sample-sb-sdvosb", "pass", 0.62, logprob),
    // Protests: wrong with no confidence at all. Counted as unknown.
    r("sample-bp-timeliness", "fail", null, null, "Yes, within 10 days of award."),
    r("sample-bp-timeliness", "fail", null, null, "Yes, if filed before award."),
    r("sample-bp-timeliness", "pass"),
    r("sample-bp-stay", "fail", null, null, "Ten days after the debriefing is requested."),
    r("sample-bp-stay", "pending_human"),
    // Contract types: the model is mostly right here.
    r("sample-ct-tm", "pass", 0.93, logprob),
    r("sample-ct-tm", "pass", 0.91, logprob),
    r("sample-ct-tm", "pass", 0.95, logprob),
    r("sample-ct-award-fee", "pass", 0.88, logprob),
    r("sample-ct-award-fee", "warning", 0.81, logprob),
    r("sample-ct-award-fee", "not_evaluated"),
    // Nobody declared an area for this one.
    r("sample-nd-card", "pass"),
    r("sample-nd-card", "fail", null, null, "Yes, if the purchases are on different days."),
  ];
}

/** Expert pseudonyms, the way a package names people. */
const EXPERT_A = "expert-4f2a91c07b1e";
const EXPERT_B = "expert-9d03e6b5a2c4";
const EXPERT_C = "expert-1b7c58f0e39d";

function t(
  id: string,
  scenarioId: string,
  author: string,
  qualified: boolean,
  note: string,
  extra: Partial<SampleTrace> = {},
): SampleTrace {
  const s = SCENARIOS.find((x) => x.id === scenarioId)!;
  return {
    id,
    scenario_id: scenarioId,
    result_id: null,
    author,
    by_viewer: false,
    knowledge_area: s.knowledge_area,
    steps: extra.steps ?? [{ text: "Worked from the solicitation and the FAR.", basis: null }],
    final_answer: extra.final_answer ?? "See steps.",
    sources: extra.sources ?? [],
    time_spent_seconds: extra.time_spent_seconds ?? 1260,
    confidence: 0.9,
    expertise: extra.expertise ?? "acquisition",
    qualified,
    qualification_note: note,
    classification: U,
    contains_pii: extra.contains_pii ?? false,
    // Filled in by the store from what the trace contains, the way the
    // server computes one.
    content_hash: "",
    created_at: extra.created_at ?? "2026-09-18T10:00:00Z",
  };
}

const HOLDS = "Reviewer holds Acquisition & contracting.";

function buildTraces(): SampleTrace[] {
  return [
    t("sample-trace-01", "sample-ss-clarification", EXPERT_A, true, HOLDS, {
      time_spent_seconds: 1440,
      steps: [
        {
          text: "A clarification may resolve minor or clerical errors, but only when award without discussions is contemplated.",
          basis: "FAR 15.306(a)(1)-(2)",
        },
        {
          text: "A change to price is a change to the proposal, so it cannot be done as a clarification.",
          basis: "FAR 15.306(d)",
        },
      ],
      final_answer:
        "No. Letting an offeror change its price is a proposal revision, which is discussions, not a clarification.",
      sources: ["FAR 15.306(a)", "FAR 15.306(d)"],
    }),
    t("sample-trace-02", "sample-ss-neutral-pp", EXPERT_B, true, HOLDS, {
      time_spent_seconds: 960,
      steps: [
        {
          text: "An offeror without a record of relevant past performance may not be evaluated favourably or unfavourably on it.",
          basis: "FAR 15.305(a)(2)(iv)",
        },
      ],
      final_answer: "No. It must receive a neutral rating on past performance.",
      sources: ["FAR 15.305(a)(2)(iv)"],
    }),
    t("sample-trace-03", "sample-ss-tradeoff", EXPERT_A, true, HOLDS, {
      time_spent_seconds: 1980,
      steps: [
        {
          text: "A tradeoff must be documented with the rationale for any business judgements, including the benefits for the added cost.",
          basis: "FAR 15.308",
        },
        {
          text: "Adjectival ratings alone do not say why the higher rating is worth the higher price.",
          basis: "FAR 15.101-1(c)",
        },
      ],
      final_answer:
        "No. The decision must say why the higher-rated proposal's benefits justify its price; ratings alone are not enough.",
      sources: ["FAR 15.308", "FAR 15.101-1"],
    }),
    // Kept on the record, never delivered: the author is outside the discipline
    // the problem needs.
    t(
      "sample-trace-04",
      "sample-ss-unstated",
      EXPERT_C,
      false,
      "The reviewer's expertise (Legal & compliance) does not cover Acquisition & contracting.",
      {
        expertise: "legal",
        time_spent_seconds: 780,
        steps: [
          {
            text: "Agencies must evaluate on the factors stated in the solicitation.",
            basis: "FAR 15.305(a)",
          },
        ],
        final_answer: "Generally no, unless the consideration is reasonably encompassed by a stated factor.",
        sources: ["FAR 15.305(a)"],
      },
    ),
    // Qualified, but flagged as containing personal information, so it stays home.
    t("sample-trace-05", "sample-ss-tradeoff", EXPERT_B, true, HOLDS, {
      contains_pii: true,
      time_spent_seconds: 1500,
      steps: [
        {
          text: "Compared this to a tradeoff I documented for a named program office, including the evaluators involved.",
          basis: "FAR 15.308",
        },
      ],
      final_answer: "No. The rationale for paying more has to be written down.",
      sources: ["FAR 15.308"],
    }),
    t("sample-trace-06", "sample-sb-sdvosb", EXPERT_B, true, HOLDS, {
      time_spent_seconds: 600,
      steps: [
        {
          text: "The SDVOSB sole-source ceiling for services is set in the FAR and adjusted for inflation.",
          basis: "FAR 19.1406",
        },
      ],
      final_answer: "Check the current threshold in FAR 19.1406; it differs for manufacturing and for other acquisitions.",
      sources: ["FAR 19.1406"],
    }),
  ];
}

/** The viewer's own profile inside the sample: an acquisition expert whose
 *  claim is self-declared, which the product says rather than hides. */
export const SAMPLE_PROFILE = {
  id: "sample-profile-viewer",
  disciplines: ["acquisition"],
  verified: false,
  active: true,
};

/** What "Use a worked example" fills in on the target problem. The reasoning
 *  is the correct one; it is here so a busy reader can see the workflow
 *  without having to know FAR 15.306 by heart. */
export const WORKED_EXAMPLE = {
  steps: [
    {
      text:
        "Letting Offeror C fix its rate and lower its price means C revises its proposal. " +
        "That is discussions, not a clarification.",
      basis: "FAR 15.306(a)(2), 15.306(d)",
    },
    {
      text:
        "Once discussions are opened they must be held with every offeror still in the " +
        "competitive range, not one.",
      basis: "FAR 15.306(d)(1), (d)(3)",
    },
    {
      text:
        "So the contracting officer holds discussions with A, B and C and asks all three for " +
        "final proposal revisions, or does not let C revise.",
      basis: "FAR 15.307(b)",
    },
  ],
  answer:
    "No. Letting one offeror revise its price is discussions, and discussions must be held " +
    "with every offeror in the competitive range. Open discussions with all three and request " +
    "final proposal revisions from each, or evaluate the proposals as submitted.",
  sources: ["FAR 15.306(a)", "FAR 15.306(d)", "FAR 15.307(b)"],
};

/** A fresh copy of the sample. Nothing is shared between calls, so clearing
 *  the store can never leave a mutated fixture behind. */
export function freshSample(): {
  scenarios: SampleScenario[];
  results: SampleResult[];
  traces: SampleTrace[];
} {
  return {
    scenarios: structuredClone(SCENARIOS),
    results: buildResults(),
    traces: buildTraces(),
  };
}
