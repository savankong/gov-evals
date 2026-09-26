"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useResource } from "@/components/shell";
import {
  Caveat,
  Card,
  Empty,
  ErrorNote,
  PageTitle,
  Segmented,
  SplitBar,
  Table,
  TableSkeleton,
  Td,
  Th,
  Tr,
} from "@/components/ui";
import { api } from "@/lib/api";
import { tourSignal } from "@/tour/signal";

interface AreaRow {
  knowledge_area: string | null;
  label: string;
  declared: boolean;
  results: number;
  passed: number;
  failed: number;
  warned: number;
  unresolved: number;
  confident_wrong: number;
  unsure_wrong: number;
  confidence_unknown_wrong: number;
  scenarios: number;
  failed_scenarios: number;
  failed_without_trace: number;
  traces: number;
  qualified_traces: number;
  expert_seconds: number;
  traces_without_time: number;
}

interface WeaknessMap {
  confident_at: number;
  areas: AreaRow[];
  results: number;
  confidence: {
    with_confidence: number;
    without_confidence: number;
    sources: Record<string, number>;
  };
}

const THRESHOLDS = ["0.6", "0.7", "0.8", "0.9"];

const SORTS: Array<{ key: string; label: string; by: (r: AreaRow) => number }> = [
  { key: "confident", label: "Confidently wrong", by: (r) => r.confident_wrong },
  { key: "failed", label: "Failed", by: (r) => r.failed },
  { key: "backlog", label: "Not yet captured", by: (r) => r.failed_without_trace },
  { key: "effort", label: "Expert time", by: (r) => r.expert_seconds },
];

const SOURCE_LABELS: Record<string, string> = {
  reported: "stated by the model",
  logprob: "token probabilities",
  sample_agreement: "agreement across samples",
};

function hours(seconds: number): string {
  if (!seconds) return "—";
  const h = seconds / 3600;
  return h < 1 ? `${Math.round(seconds / 60)} min` : `${h.toFixed(1)} h`;
}

function Count({ value, tone }: { value: number; tone?: "fail" | "warn" }) {
  const colour = value === 0 ? "text-faint" : tone === "fail" ? "text-fail" : tone === "warn" ? "text-warn" : "text-ink";
  return <span className={`tnum ${colour}`}>{value}</span>;
}

export default function WeaknessMapPage() {
  const [threshold, setThreshold] = useState("0.8");
  const [sort, setSort] = useState("confident");

  const map = useResource(
    () => api.get<WeaknessMap>(`/weakness-map?confident_at=${threshold}`),
    [threshold],
  );

  const rows = useMemo(() => {
    const by = SORTS.find((s) => s.key === sort)?.by ?? SORTS[0].by;
    // Undeclared stays last whatever the sort: it is not a bin anyone can buy.
    return [...(map.data?.areas ?? [])].sort(
      (a, b) => Number(!a.declared) - Number(!b.declared) || by(b) - by(a),
    );
  }, [map.data, sort]);

  const data = map.data;
  const sources = Object.entries(data?.confidence.sources ?? {});

  return (
    <div className="space-y-4">
      <PageTitle
        title="Weakness map"
        subtitle="Where the model is wrong, by knowledge area, and how much expert time has gone there. Start here: expert hours are the expensive input, and they are worth most where the model is wrong and sure of itself."
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex items-center gap-2">
          <span className="text-2xs uppercase tracking-wider text-faint">Confident at</span>
          <Segmented
            options={THRESHOLDS.map((t) => ({ key: t, label: `≥ ${t}`, tour: `weakness.threshold.${t}` }))}
            active={threshold}
            onChange={(key) => {
              setThreshold(key ?? "0.8");
              tourSignal(`weakness.threshold:${key}`);
            }}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs uppercase tracking-wider text-faint">Sort by</span>
          <Segmented
            options={SORTS.map(({ key, label }) => ({ key, label }))}
            active={sort}
            onChange={(key) => setSort(key ?? "confident")}
          />
        </div>
      </div>

      {map.error ? (
        <ErrorNote message={map.error} status={map.status} onRetry={map.reload} />
      ) : null}

      {data ? (
        <div className="grid gap-px border border-line bg-line sm:grid-cols-3">
          <div className="bg-panel px-4 py-3">
            <div className="text-2xs uppercase tracking-wider text-faint">Model answers judged</div>
            <div className="tnum mt-0.5 text-2xl text-ink">{data.results}</div>
          </div>
          <div className="bg-panel px-4 py-3">
            <div className="text-2xs uppercase tracking-wider text-faint">With a confidence</div>
            <div className="tnum mt-0.5 text-2xl text-ink">{data.confidence.with_confidence}</div>
            {sources.length ? (
              <div className="mt-0.5 text-xs text-muted">
                {sources
                  .map(([key, n]) => `${n} ${SOURCE_LABELS[key] ?? key}`)
                  .join(" · ")}
              </div>
            ) : null}
          </div>
          <div className="bg-panel px-4 py-3">
            <div className="text-2xs uppercase tracking-wider text-faint">Confidence unknown</div>
            <div className="tnum mt-0.5 text-2xl text-ink">
              {data.confidence.without_confidence}
            </div>
            <div className="mt-0.5 text-xs text-muted">
              Counted apart, never as sure or unsure.
            </div>
          </div>
        </div>
      ) : null}

      <Card tour="weakness.table">
        {map.loading && !data ? (
          <TableSkeleton rows={5} cols={6} />
        ) : map.error ? null : rows.length === 0 ? (
          <Empty
            title="No model answers have been judged yet"
            detail="The map is built from evaluation results. Run a campaign against the customer's model from a project in Evaluate, and each knowledge area it touches appears here with what the model got wrong."
            action={
              <Link href="/" className="text-sm text-muted underline underline-offset-2 hover:text-ink">
                Go to projects
              </Link>
            }
          />
        ) : (
          <Table minWidth={980}>
            <thead>
              <tr>
                {/* Pinned below md, so a row keeps its name while the counts
                    scroll sideways on a phone. */}
                <Th className="max-md:sticky max-md:left-0 max-md:z-[1] max-md:bg-panel">Knowledge area</Th>
                <Th align="right">Judged</Th>
                <Th align="right">Wrong</Th>
                <Th align="right" tour="weakness.col.confident">Confidently</Th>
                <Th align="right">Unsure</Th>
                <Th align="right">Unknown</Th>
                <Th align="right">No judgement</Th>
                <Th align="right">Not yet captured</Th>
                <Th align="right">Expert traces</Th>
                <Th align="right">Expert time</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <Tr key={row.label} index={index}>
                  <Td className="max-md:sticky max-md:left-0 max-md:z-[1] max-md:bg-panel">
                    {row.declared ? (
                      <Link
                        href={`/capture?area=${encodeURIComponent(row.knowledge_area ?? "")}`}
                        className="link-underline text-ink"
                        data-tour={`weakness.area:${row.knowledge_area}`}
                      >
                        {row.label}
                      </Link>
                    ) : (
                      <span className="text-muted" title="Problems nobody has assigned to a knowledge area. They cannot be binned for delivery until someone does.">
                        {row.label}
                      </span>
                    )}
                    <SplitBar
                      className="mt-1.5 max-w-[14rem]"
                      parts={[
                        { value: row.passed + row.warned, tone: "pass" },
                        { value: row.unresolved, tone: "muted" },
                        { value: row.failed, tone: "fail" },
                      ]}
                    />
                  </Td>
                  <Td align="right"><Count value={row.results} /></Td>
                  <Td align="right"><Count value={row.failed} tone="fail" /></Td>
                  <Td align="right"><Count value={row.confident_wrong} tone="fail" /></Td>
                  <Td align="right"><Count value={row.unsure_wrong} tone="warn" /></Td>
                  <Td align="right"><Count value={row.confidence_unknown_wrong} /></Td>
                  <Td align="right"><Count value={row.unresolved} /></Td>
                  <Td align="right">
                    <Count value={row.failed_without_trace} />
                    <span className="tnum text-faint">/{row.failed_scenarios}</span>
                  </Td>
                  <Td align="right">
                    <Count value={row.qualified_traces} />
                    {row.traces > row.qualified_traces ? (
                      <div
                        className="mt-0.5 text-2xs text-faint"
                        title="Written by people without the expertise the problem requires. Kept on the record; not delivered."
                      >
                        +{row.traces - row.qualified_traces} uncounted
                      </div>
                    ) : null}
                  </Td>
                  <Td align="right" className="tnum text-muted">
                    {hours(row.expert_seconds)}
                    {row.traces_without_time ? (
                      <div className="mt-0.5 text-2xs text-faint">
                        +{row.traces_without_time} untimed
                      </div>
                    ) : null}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <div className="space-y-1.5">
        <Caveat>
          Wrong answers are split by the model&apos;s own confidence. Confidently wrong means a
          confidence of {data?.confident_at ?? threshold} or more. A wrong answer with no
          confidence is counted as unknown, not folded into either side.
        </Caveat>
        <Caveat>
          There is no combined score. Which area is worth most to a customer is a commercial
          decision, so the map shows the counts and leaves the sort to you. &ldquo;Not yet
          captured&rdquo; is problems the model failed that no qualified expert has worked.
        </Caveat>
      </div>
    </div>
  );
}
