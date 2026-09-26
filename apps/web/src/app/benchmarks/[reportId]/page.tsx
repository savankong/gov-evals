"use client";

import { use, useMemo, useState } from "react";

import { useResource } from "@/components/shell";
import {
  Bar,
  Card,
  CardHead,
  Caveat,
  CodeBlock,
  Crumbs,
  ErrorNote,
  Hash,
  Note,
  Skeleton,
  Table,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { api } from "@/lib/api";
import {
  type BenchmarkData,
  type BenchmarkDetail,
  type FacetValue,
  type QuestionRow,
  pct,
  points,
  verdictLabel,
} from "@/lib/benchmark";

/* A model's identity is carried by position and a direct label, not by hue:
 * saturated colour in this product is a verdict. Four steps of ink, then the
 * legend and labels carry the rest. */
const SERIES = ["bg-ink", "bg-muted", "bg-line-strong", "bg-faint"];

/* Facets the report knows how to name. Anything else is shown by its key. */
const FACET_TITLES: Record<string, string> = {
  phase: "lifecycle phase",
  task: "kind of task",
  topic: "topic",
};

export default function BenchmarkReportPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const detail = useResource<BenchmarkDetail>(
    () => api.get<BenchmarkDetail>(`/benchmarks/${reportId}`),
    [reportId],
  );

  if (detail.error)
    return <ErrorNote message={detail.error} status={detail.status} onRetry={detail.reload} />;
  if (detail.loading || !detail.data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-72" />
      </div>
    );

  return <Report b={detail.data} />;
}

function Report({ b }: { b: BenchmarkDetail }) {
  const d = b.data;
  const systems = useMemo(
    () =>
      [...d.leaderboard]
        .sort((x, y) => (y.pass_rate ?? -1) - (x.pass_rate ?? -1))
        .map((r) => `${r.model} / ${r.condition}`),
    [d.leaderboard],
  );
  const facetNames = Object.keys(d.facets).filter((f) => f !== "split");
  const simulated = d.demonstration.some((s) => s.simulated_reviewer);

  return (
    <article className="mx-auto max-w-5xl space-y-10 pb-16">
      <header className="animate-rise space-y-4">
        <Crumbs items={[{ label: "Benchmarks", href: "/benchmarks" }, { label: b.project.name }]} />
        <div className="flex flex-wrap items-center gap-1.5">
          {b.demonstration ? <Tag tone="warn">Demonstration</Tag> : null}
          {d.dataset.required_expertise.map((x) => (
            <Tag key={x}>{x}</Tag>
          ))}
          <Tag mono>{b.classification}</Tag>
        </div>
        <div>
          <h1 className="text-3xl text-ink">{b.project.name}</h1>
          <p className="mt-1 text-sm text-muted">{b.title}</p>
        </div>
        <p className="tnum text-2xs text-muted">
          Updated {formatDate(b.created_at)} · {d.models.length} models · {d.dataset.questions} questions ·{" "}
          {d.dataset.criteria} criteria · report <Hash value={b.sha256} length={12} />
        </p>
        {b.project.description ? (
          <p className="max-w-3xl text-base text-ink-soft">{b.project.description}</p>
        ) : null}
        {d.demonstration.length ? <Demonstration d={d} /> : null}
      </header>

      <Section eyebrow="Summary" title="Key measurements">
        <KeyMeasurements d={d} systems={systems} simulated={simulated} />
      </Section>

      <Section eyebrow="Results" title="Pass rate by model">
        <Results d={d} systems={systems} />
      </Section>

      {facetNames.map((facet) => (
        <Section
          key={facet}
          eyebrow="Breakdown"
          title={`Performance by ${FACET_TITLES[facet] ?? facet}`}
        >
          <FacetChart values={d.facets[facet]} systems={systems} />
        </Section>
      ))}

      <Section eyebrow="Efficiency" title="Cost and latency">
        <CostLatency d={d} />
      </Section>

      <Section eyebrow="Every question" title="Criterion by criterion">
        <QuestionGrid rows={b.question_rows} systems={systems} />
      </Section>

      <Section eyebrow="Methodology" title="How this was measured">
        <Methodology d={d} simulated={simulated} />
      </Section>

      <Section eyebrow="Grading" title={simulated ? "Judge agreement with a simulated reviewer" : "Judge agreement with experts"}>
        <Grading d={d} simulated={simulated} />
      </Section>

      {d.example ? (
        <Section eyebrow="Sample" title="One graded answer">
          <Sample example={d.example} />
        </Section>
      ) : null}

      <Section eyebrow="Limits" title="Limitations">
        <Limitations d={d} />
      </Section>

      <Section eyebrow="Cite" title="Citation">
        <CodeBlock>{citation(b)}</CodeBlock>
      </Section>

      <Caveat>
        This page states measurements only. Interpretation and recommendations belong to the program that
        publishes the benchmark, and are published alongside it.
      </Caveat>
    </article>
  );
}

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <div className="font-mono text-2xs uppercase tracking-wider text-faint">{eyebrow}</div>
        <h2 className="mt-1 text-xl text-ink">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Demonstration({ d }: { d: BenchmarkData }) {
  const statements = d.demonstration.filter(
    (s, i) => d.demonstration.findIndex((t) => JSON.stringify(t) === JSON.stringify(s)) === i,
  );
  return (
    <Card className="p-4">
      {statements.map((s, i) => (
        <Note key={i} tone="warn">
          <p className="font-medium">Demonstration data. This is not a published benchmark.</p>
          {s.statement ? <p className="mt-1">{s.statement}</p> : null}
          <ul className="mt-2 list-disc space-y-1 pl-4">
            {(s.stand_ins ?? []).map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </Note>
      ))}
    </Card>
  );
}

function KeyMeasurements({ d, systems, simulated }: { d: BenchmarkData; systems: string[]; simulated: boolean }) {
  const rows = d.leaderboard.filter((r) => r.pass_rate !== null);
  const best = systems[0] ? d.leaderboard.find((r) => `${r.model} / ${r.condition}` === systems[0]) : null;
  const worst = systems.length > 1 ? d.leaderboard.find((r) => `${r.model} / ${r.condition}` === systems[systems.length - 1]) : null;
  const items: string[] = [];
  if (best) items.push(`Highest pass rate: ${best.model} (${best.condition}) at ${pct(best.pass_rate)}, ${best.criteria_passed} of ${best.criteria_judged} criteria met.`);
  if (worst) items.push(`Lowest: ${worst.model} (${worst.condition}) at ${pct(worst.pass_rate)}, across ${rows.length} model and condition pairs.`);
  for (const [facet, values] of Object.entries(d.facets)) {
    const readable = values.filter((v) => v.enough_questions && v.pass_rate !== null);
    if (readable.length < 2) continue;
    const lo = readable.reduce((a, v) => ((v.pass_rate ?? 0) < (a.pass_rate ?? 0) ? v : a));
    const hi = readable.reduce((a, v) => ((v.pass_rate ?? 0) > (a.pass_rate ?? 0) ? v : a));
    items.push(`By ${FACET_TITLES[facet] ?? facet}: from ${pct(lo.pass_rate)} (${lo.value}) to ${pct(hi.pass_rate)} (${hi.value}), pooled over all models.`);
  }
  for (const e of d.condition_effects)
    if (e.mean_change !== null)
      items.push(`${e.condition} against baseline: mean change ${points(e.mean_change)} across ${e.models_compared} models that ran both.`);
  const a = d.judge_alignment;
  items.push(
    a.accuracy === null
      ? "Judge agreement with qualified experts has not been measured. Every score here is the judge's."
      : simulated
        ? `The judge agreed with a simulated reviewer on ${pct(a.accuracy)} of ${a.comparisons} labels. That shows how the measurement works, not how far to trust the judge.`
        : `The judge agreed with qualified experts on ${pct(a.accuracy)} of ${a.comparisons} criterion labels.`,
  );
  return (
    <Card className="p-4">
      <ul className="list-disc space-y-1.5 pl-4 text-sm text-ink-soft">
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </Card>
  );
}

function Legend({ systems }: { systems: string[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
      {systems.map((s, i) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <i className={`inline-block h-2.5 w-2.5 rounded-full ${SERIES[i % SERIES.length]}`} aria-hidden />
          {s}
        </span>
      ))}
    </div>
  );
}

function Results({ d, systems }: { d: BenchmarkData; systems: string[] }) {
  const models = Array.from(new Set(systems.map((s) => s.split(" / ")[0])));
  const rate = (m: string, c: string) => d.leaderboard.find((r) => r.model === m && r.condition === c);
  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-4">
        {systems.map((s, i) => {
          const r = d.leaderboard.find((x) => `${x.model} / ${x.condition}` === s)!;
          return (
            <div key={s} className="grid grid-cols-[minmax(8rem,14rem)_1fr_5.5rem] items-center gap-3">
              <span className="truncate text-sm text-ink">{d.conditions.length > 1 ? s : r.model}</span>
              <div className="relative h-5 bg-sunken" title={`${r.criteria_passed} of ${r.criteria_judged} criteria met`}>
                <div className={`absolute inset-y-0 left-0 ${SERIES[i % SERIES.length]}`} style={{ width: `${(r.pass_rate ?? 0) * 100}%` }} />
              </div>
              <span className="tnum text-right font-mono text-base text-ink">{pct(r.pass_rate)}</span>
            </div>
          );
        })}
      </Card>
      <Card>
        <Table minWidth={560}>
          <thead>
            <tr>
              <Th>Model</Th>
              {d.conditions.map((c) => (
                <Th key={c} className="text-right">{c}</Th>
              ))}
              <Th className="text-right">Criteria met / judged</Th>
              <Th className="text-right">Not judged</Th>
              <Th className="text-right">Errors</Th>
            </tr>
          </thead>
          <tbody>
            {models.map((m, index) => {
              const rows = d.conditions.map((c) => rate(m, c)).filter(Boolean);
              return (
                <Tr key={m} index={index}>
                  <Td><span className="text-sm text-ink">{m}</span></Td>
                  {d.conditions.map((c) => (
                    <Td key={c} className="text-right"><span className="tnum font-mono text-sm">{pct(rate(m, c)?.pass_rate)}</span></Td>
                  ))}
                  <Td className="text-right"><span className="tnum font-mono text-xs text-muted">{rows.map((r) => `${r!.criteria_passed} / ${r!.criteria_judged}`).join(", ")}</span></Td>
                  <Td className="text-right"><span className="tnum font-mono text-xs text-muted">{rows.reduce((a, r) => a + r!.criteria_not_judged, 0)}</span></Td>
                  <Td className="text-right"><span className="tnum font-mono text-xs text-muted">{rows.reduce((a, r) => a + r!.errors, 0)}</span></Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}

function FacetChart({ values, systems }: { values: FacetValue[]; systems: string[] }) {
  const ranked = [...values].sort((a, b) => (b.pass_rate ?? -1) - (a.pass_rate ?? -1));
  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend systems={systems} />
        <span className="text-2xs text-muted">Ranked by pass rate pooled over all models</span>
      </div>
      <div className="space-y-1">
        {ranked.map((v) => {
          const rates = systems.map((s) => v.by_system[s] ?? null);
          const known = rates.filter((r): r is number => r !== null);
          const lo = Math.min(...known);
          const hi = Math.max(...known);
          return (
            <div key={v.value} className="grid grid-cols-[minmax(6rem,11rem)_1fr_4.5rem] items-center gap-3 py-1">
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">{v.value}</div>
                <div className="text-2xs text-muted">
                  {v.questions} questions{v.enough_questions ? "" : " · too few to read"}
                </div>
              </div>
              <div className="relative h-7">
                {[0, 25, 50, 75, 100].map((t) => (
                  <i key={t} className="absolute inset-y-0 w-px bg-line/60" style={{ left: `${t}%` }} aria-hidden />
                ))}
                <i className="absolute left-0 right-0 top-1/2 h-px bg-line" aria-hidden />
                {known.length > 1 ? (
                  <i className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-ink-soft/40" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} aria-hidden />
                ) : null}
                {rates.map((r, i) =>
                  r === null ? null : (
                    <span
                      key={systems[i]}
                      title={`${systems[i]} · ${v.value}: ${pct(r)}`}
                      className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-panel ${SERIES[i % SERIES.length]}`}
                      style={{ left: `${r * 100}%` }}
                    />
                  ),
                )}
              </div>
              <span className="tnum text-right font-mono text-sm text-ink-soft">{pct(v.pass_rate)}</span>
            </div>
          );
        })}
        <div className="grid grid-cols-[minmax(6rem,11rem)_1fr_4.5rem] gap-3">
          <span />
          <div className="relative h-4 font-mono text-2xs text-faint">
            {[0, 25, 50, 75, 100].map((t) => (
              <span key={t} className="absolute -translate-x-1/2" style={{ left: `${t}%` }}>{t}%</span>
            ))}
          </div>
          <span className="text-right font-mono text-2xs text-faint">pooled</span>
        </div>
      </div>
    </Card>
  );
}

function CostLatency({ d }: { d: BenchmarkData }) {
  const priced = d.leaderboard.filter((r) => r.cost_per_test !== null);
  const timed = d.leaderboard.filter((r) => r.latency_ms_median !== null);
  if (!priced.length && !timed.length)
    return (
      <Card className="p-4">
        <Note>
          Not recorded for any model. Cost needs token counts from the connector and prices declared on the system
          version, and latency needs a connector that measures it. A replayed answer has neither, so this is left
          unknown rather than shown as zero.
        </Note>
      </Card>
    );
  return (
    <Card>
      <Table minWidth={520}>
        <thead>
          <tr>
            <Th>Model</Th>
            <Th>Condition</Th>
            <Th className="text-right">Pass rate</Th>
            <Th className="text-right">Cost per test</Th>
            <Th className="text-right">Median latency</Th>
          </tr>
        </thead>
        <tbody>
          {d.leaderboard.map((r, index) => (
            <Tr key={`${r.model}-${r.condition}`} index={index}>
              <Td>{r.model}</Td>
              <Td>{r.condition}</Td>
              <Td className="text-right"><span className="tnum font-mono">{pct(r.pass_rate)}</span></Td>
              <Td className="text-right"><span className="tnum font-mono">{r.cost_per_test === null ? "not recorded" : `$${r.cost_per_test.toFixed(4)}`}</span></Td>
              <Td className="text-right"><span className="tnum font-mono">{r.latency_ms_median === null ? "not recorded" : `${(r.latency_ms_median / 1000).toFixed(1)} s`}</span></Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}

function Squares({ row, system }: { row: QuestionRow; system: string }) {
  const res = row.results[system];
  if (!res) return <span className="font-mono text-2xs text-faint">not run</span>;
  const met = row.criteria.filter((c) => res.verdicts[c.id]?.verdict === "pass").length;
  return (
    <span className="flex items-center gap-[3px]">
      {row.criteria.map((c) => {
        const v = res.verdicts[c.id]?.verdict ?? "not_evaluated";
        const tone = v === "pass" ? "bg-pass" : v === "fail" ? "bg-fail" : "bg-unknown";
        return <i key={c.id} className={`inline-block h-2.5 w-2.5 ${tone}`} title={`${verdictLabel(v)}: ${c.text}`} />;
      })}
      <b className="tnum ml-1.5 font-mono text-2xs font-normal text-ink-soft">
        {met}/{row.criteria.length}
      </b>
    </span>
  );
}

function QuestionGrid({ rows, systems }: { rows: QuestionRow[]; systems: string[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const groupBy = rows.some((r) => r.facets.phase) ? "phase" : null;
  const groups = groupBy
    ? Array.from(new Set(rows.map((r) => r.facets[groupBy] ?? "other")))
    : ["all"];
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-4 px-4 pt-3 text-xs text-ink-soft">
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 bg-pass" />Met</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 bg-fail" />Not met</span>
        <span className="inline-flex items-center gap-1.5"><i className="inline-block h-2.5 w-2.5 bg-unknown" />Not judged</span>
        <span className="text-muted">Select a question for its criteria, the judge&apos;s reasons and every answer.</span>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[36rem] p-2">
          <div className="grid items-center gap-3 px-2 pb-2 pt-3 font-mono text-2xs uppercase tracking-wider text-faint" style={{ gridTemplateColumns: `1fr repeat(${systems.length}, 9rem)` }}>
            <span>Question</span>
            {systems.map((s) => (
              <span key={s} className="truncate">{s.split(" / ")[0]}</span>
            ))}
          </div>
          {groups.map((g) => (
            <div key={g}>
              {groupBy ? (
                <div className="border-b border-line px-2 pb-1.5 pt-4 font-mono text-2xs uppercase tracking-wider text-muted">{g}</div>
              ) : null}
              {rows
                .filter((r) => !groupBy || (r.facets[groupBy] ?? "other") === g)
                .map((r) => (
                  <div key={r.key}>
                    <button
                      type="button"
                      aria-expanded={open === r.key}
                      onClick={() => setOpen(open === r.key ? null : r.key)}
                      className="grid w-full items-center gap-3 border-b border-line/60 px-2 py-2 text-left transition-colors duration-150 hover:bg-sunken aria-expanded:bg-sunken"
                      style={{ gridTemplateColumns: `1fr repeat(${systems.length}, 9rem)` }}
                    >
                      <span className="min-w-0">
                        <span className="text-sm text-ink">{r.title}</span>
                        {r.facets.task === "boundary" ? <span className="ml-2"><Tag>boundary</Tag></span> : null}
                        <span className="block truncate text-2xs text-muted">{r.knowledge_area ?? r.key}</span>
                      </span>
                      {systems.map((s) => (
                        <Squares key={s} row={r} system={s} />
                      ))}
                    </button>
                    {open === r.key ? <QuestionDetail row={r} systems={systems} /> : null}
                  </div>
                ))}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function QuestionDetail({ row, systems }: { row: QuestionRow; systems: string[] }) {
  return (
    <div className="animate-fade space-y-4 border-b border-line bg-canvas px-3 py-4">
      <div>
        <div className="mb-1 font-mono text-2xs uppercase tracking-wider text-faint">Question</div>
        <p className="whitespace-pre-wrap bg-sunken px-3 py-2.5 text-sm text-ink-soft">{row.question}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] text-xs">
          <thead>
            <tr className="text-left font-mono text-2xs uppercase tracking-wider text-faint">
              <th className="py-1.5 pr-3 font-normal">Criterion</th>
              {systems.map((s) => (
                <th key={s} className="py-1.5 pr-3 font-normal">{s.split(" / ")[0]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {row.criteria.map((c) => (
              <tr key={c.id} className="border-t border-line/60 align-top">
                <td className="py-2 pr-3 text-ink-soft">{c.text}</td>
                {systems.map((s) => {
                  const v = row.results[s]?.verdicts[c.id];
                  const tone = v?.verdict === "pass" ? "bg-pass" : v?.verdict === "fail" ? "bg-fail" : "bg-unknown";
                  return (
                    <td key={s} className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1.5 font-mono text-ink">
                        <i className={`inline-block h-2.5 w-2.5 ${tone}`} />
                        {verdictLabel(v?.verdict ?? "not_evaluated")}
                      </span>
                      {v?.rationale ? <p className="mt-1 text-muted">{v.rationale}</p> : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {systems.map((s) => {
          const res = row.results[s];
          return (
            <div key={s} className="min-w-0">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink">{s.split(" / ")[0]}</span>
                {res ? (
                  <a href={`/results/${res.result_id}`} className="link-underline font-mono text-2xs text-muted">
                    evidence <Hash value={res.content_hash} length={8} />
                  </a>
                ) : null}
              </div>
              <p className="max-h-80 overflow-auto whitespace-pre-wrap border border-line bg-panel px-3 py-2 text-xs text-ink-soft">
                {res?.answer ?? "Not run."}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Methodology({ d, simulated }: { d: BenchmarkData; simulated: boolean }) {
  const ds = d.dataset;
  const phases = d.facets.phase?.map((v) => v.value) ?? [];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHead title="Evaluation pipeline" meta="Who does what, in order" />
        <ol className="space-y-3 border-t border-line p-4 text-sm">
          <li>
            <div className="font-mono text-2xs uppercase tracking-wider text-faint">1 · Target models</div>
            <p className="mt-0.5 text-ink-soft">{d.models.join(", ")}, each under {d.conditions.join(", ")}.</p>
          </li>
          <li>
            <div className="font-mono text-2xs uppercase tracking-wider text-faint">2 · Judge</div>
            <p className="mt-0.5 text-ink-soft">
              {d.judge.models.join(", ") || "not recorded"} checks every answer against each of its criteria (
              {d.judge.modes.join(", ") || "mode not recorded"}). A criterion it cannot decide is left out of the pass
              rate and counted separately.
            </p>
          </li>
          <li>
            <div className="font-mono text-2xs uppercase tracking-wider text-faint">3 · {simulated ? "Simulated reviewer" : "Experts"}</div>
            <p className="mt-0.5 text-ink-soft">
              {d.judge_alignment.comparisons
                ? `Label a calibration subset criterion by criterion without seeing the judge's verdicts (${d.calibration_results} results). Their labels measure the judge and never count as scores.`
                : "No labels yet. The judge has not been measured against people."}
            </p>
          </li>
        </ol>
      </Card>
      <Card>
        <CardHead title="Dataset" meta={ds.packs.join(", ")} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t border-line p-4 text-sm">
          <dt className="text-muted">Questions</dt>
          <dd className="tnum text-ink">{ds.questions}</dd>
          <dt className="text-muted">Criteria</dt>
          <dd className="tnum text-ink">
            {ds.criteria}
            {ds.criteria_per_question ? ` (${ds.criteria_per_question.toFixed(1)} per question)` : ""}
          </dd>
          <dt className="text-muted">Split</dt>
          <dd className="text-ink">{Object.entries(ds.splits).map(([k, v]) => `${k} ${v}`).join(", ")}</dd>
          <dt className="text-muted">Judged by</dt>
          <dd className="text-ink">{ds.required_expertise.join(", ") || "not declared"}</dd>
          <dt className="text-muted">Approved by</dt>
          <dd className="text-ink">{ds.approved_by.join(", ") || "no named approver"}</dd>
          <dt className="text-muted">Model-drafted</dt>
          <dd className="tnum text-ink">{ds.model_drafted}</dd>
          {phases.length ? (
            <>
              <dt className="text-muted">Phases</dt>
              <dd className="text-ink">{phases.join(", ")}</dd>
            </>
          ) : null}
        </dl>
      </Card>
      <Card className="md:col-span-2">
        <CardHead title="Scoring" />
        <p className="border-t border-line p-4 text-sm text-ink-soft">
          Pass rate is criteria met divided by criteria judged, pooled over every question a model answered under a
          condition. A criterion passes only if the answer clearly meets it; partial or implied is a fail. Criteria the
          judge did not decide are excluded from both counts and reported. There is no composite score across
          benchmarks or conditions.
        </p>
      </Card>
    </div>
  );
}

function Grading({ d, simulated }: { d: BenchmarkData; simulated: boolean }) {
  const a = d.judge_alignment;
  const who = simulated ? "Reviewer" : "Expert";
  if (a.comparisons === 0)
    return (
      <Card className="p-4">
        <Note>
          Not measured. No qualified expert has labelled criteria on these results, so how often the judge agrees
          with experts is unknown. Treat every score on this page as the judge&apos;s.
        </Note>
      </Card>
    );
  return (
    <Card className="space-y-4 p-4">
      {simulated ? (
        <Note tone="warn">
          These labels come from a simulated reviewer, not a qualified expert. The figures show how the measurement
          works; they are not evidence about how far to trust the judge.
        </Note>
      ) : null}
      <div className="flex flex-wrap gap-8">
        <Stat value={pct(a.accuracy)} label={`agreement over ${a.comparisons} labels`} />
        <Stat value={pct(a.false_pass_rate)} label={`false passes, as a share of ${who.toLowerCase()} fails`} />
        <Stat value={String(a.criteria_compared)} label="criteria compared" />
      </div>
      <div className="overflow-x-auto">
        <table className="tnum border-collapse text-sm">
          <thead>
            <tr>
              <th className="border border-line px-4 py-2" />
              <th className="border border-line px-4 py-2 text-left font-mono text-2xs font-normal text-muted">{who}: met</th>
              <th className="border border-line px-4 py-2 text-left font-mono text-2xs font-normal text-muted">{who}: not met</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th className="border border-line px-4 py-2 text-left font-mono text-2xs font-normal text-muted">Judge: met</th>
              <td className="border border-line px-4 py-2 text-right font-mono">{a.true_pass}</td>
              <td className="border border-line px-4 py-2 text-right font-mono">{a.false_pass}</td>
            </tr>
            <tr>
              <th className="border border-line px-4 py-2 text-left font-mono text-2xs font-normal text-muted">Judge: not met</th>
              <td className="border border-line px-4 py-2 text-right font-mono">{a.false_fail}</td>
              <td className="border border-line px-4 py-2 text-right font-mono">{a.true_fail}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Caveat>A false pass inflates every score it touches, which is why it is reported on its own.</Caveat>
    </Card>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <div className="tnum font-mono text-2xl text-ink">{value}</div>
      <div className="mt-0.5 text-2xs text-muted">{label}</div>
    </div>
  );
}

function Sample({ example }: { example: NonNullable<BenchmarkData["example"]> }) {
  const met = example.criteria.filter((c) => c.verdict === "pass").length;
  return (
    <Card className="space-y-4 p-4">
      <p className="text-xs text-muted">
        {example.title} · {example.model} under {example.condition} · result <Hash value={example.content_hash} length={12} />
      </p>
      <div>
        <div className="mb-1 font-mono text-2xs uppercase tracking-wider text-faint">Input</div>
        <p className="whitespace-pre-wrap bg-sunken px-3 py-2.5 text-sm text-ink-soft">{example.question}</p>
      </div>
      <div>
        <div className="mb-1 font-mono text-2xs uppercase tracking-wider text-faint">{example.model}</div>
        <p className="max-h-80 overflow-auto whitespace-pre-wrap border border-line px-3 py-2.5 text-sm text-ink-soft">{example.answer}</p>
      </div>
      <div>
        <div className="mb-2 font-mono text-2xs uppercase tracking-wider text-faint">
          Rubric checks · {met} of {example.criteria.length} met
        </div>
        <ul className="space-y-2">
          {example.criteria.map((c) => (
            <li key={c.id} className="grid grid-cols-[1.25rem_1fr] gap-2 text-sm">
              <span className={`font-mono ${c.verdict === "pass" ? "text-pass" : c.verdict === "fail" ? "text-fail" : "text-unknown"}`} aria-label={verdictLabel(c.verdict)}>
                {c.verdict === "pass" ? "✓" : c.verdict === "fail" ? "✗" : "?"}
              </span>
              <span>
                <span className="text-ink">{c.text}</span>
                {c.rationale ? <span className="block text-xs text-muted">{c.rationale}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

function Limitations({ d }: { d: BenchmarkData }) {
  const notes: string[] = [];
  if (d.demonstration.length)
    notes.push("Demonstration data. The stand-ins listed at the top replace steps a published benchmark gives to people. None of these figures is a finding.");
  const thin = Object.entries(d.facets).flatMap(([f, vs]) => vs.filter((v) => !v.enough_questions).map((v) => `${f} = ${v.value} (${v.questions})`));
  if (thin.length) notes.push(`Too few questions to read as findings: ${thin.join("; ")}.`);
  const notJudged = d.leaderboard.reduce((a, r) => a + r.criteria_not_judged, 0);
  if (notJudged) notes.push(`${notJudged} criterion checks were not decided by the judge and are excluded from pass rates.`);
  if (d.leaderboard.some((r) => r.cost_per_test === null)) notes.push("Cost is not recorded for every model and condition.");
  const a = d.judge_alignment;
  if (a.comparisons === 0) notes.push("Judge agreement with qualified experts was not measured.");
  else if (a.comparisons < 100) notes.push(`Judge agreement rests on ${a.comparisons} comparisons. Treat it as indicative.`);
  if (d.dataset.questions_without_named_approver) notes.push(`${d.dataset.questions_without_named_approver} questions have no named approver.`);
  const errors = d.leaderboard.reduce((x, r) => x + r.errors, 0);
  if (errors) notes.push(`${errors} tests ended in an error.`);
  if (!notes.length) notes.push("None identified from the stored results.");
  return (
    <Card className="p-4">
      <ul className="list-disc space-y-1.5 pl-4 text-sm text-ink-soft">
        {notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </Card>
  );
}

function citation(b: BenchmarkDetail): string {
  const year = new Date(b.created_at).getFullYear();
  const key = b.project.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  return [
    `@misc{${key}_${year},`,
    `  title  = {${b.title}},`,
    `  author = {Aegis Eval},`,
    `  year   = {${year}},`,
    `  note   = {${b.demonstration ? "Demonstration data, not a published benchmark. " : ""}Report ${b.id}, SHA-256 ${b.sha256}}`,
    `}`,
  ].join("\n");
}
