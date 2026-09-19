"use client";

import { use, useCallback, useMemo, useState } from "react";

import { EvidencePanel } from "@/components/evidence-panel";
import { EvaluatorKind, Status, StatusSquare } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Crumbs,
  Empty,
  ErrorNote,
  Figure,
  Hash,
  Key,
  Segmented,
  Spec,
  TableSkeleton,
  formatMs,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Result, Run } from "@/lib/types";

export default function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const [status, setStatus] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const run = useResource<Run>(() => api.get<Run>(`/runs/${runId}`), [runId]);
  const results = useResource<Result[]>(
    () => api.get<Result[]>(`/runs/${runId}/results?limit=300`),
    [runId],
  );
  const campaign = useResource<{ classification: string | null } | null>(
    () =>
      run.data
        ? api.get<{ classification: string | null }>(`/campaigns/${run.data.campaign_id}/summary`)
        : Promise.resolve(null),
    [run.data?.campaign_id],
  );
  useDeclaredClassification(campaign.data?.classification);

  const rows = useMemo(
    () => (results.data ?? []).filter((r) => !status || r.status === status),
    [results.data, status],
  );

  /** Arrow keys walk the filtered list without closing the panel. */
  const step = useCallback(
    (direction: 1 | -1) => {
      if (!openId) return;
      const index = rows.findIndex((r) => r.id === openId);
      const next = rows[index + direction];
      if (next) setOpenId(next.id);
    },
    [openId, rows],
  );

  if (run.loading) {
    return (
      <Card>
        <TableSkeleton rows={10} cols={4} />
      </Card>
    );
  }
  if (run.error) return <ErrorNote message={run.error} />;
  if (!run.data) return null;

  const metrics = run.data.metrics as Record<string, unknown>;
  const latency = metrics?.latency_ms as { median?: number; p95?: number } | undefined;
  const counts = (results.data ?? []).reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="animate-rise">
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Campaign", href: `/campaigns/${run.data.campaign_id}` },
            { label: "Run" },
          ]}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-normal text-ink">Run results</h1>
          <Status status={run.data.verdict} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "Executions", count: run.data.scenario_count },
          {
            label: "Pass rate",
            value: formatPercent((metrics?.pass_rate as number | null) ?? null),
          },
          { label: "Passed", count: run.data.passed },
          { label: "Failed", count: run.data.failed },
          { label: "Awaiting review", count: run.data.pending_human },
          { label: "Median latency", value: formatMs(latency?.median) },
        ].map((stat, index) => (
          <div
            key={stat.label}
            className="stagger bg-panel px-4 py-3.5"
            style={{ ["--stagger-delay" as string]: `${index * 28}ms` }}
          >
            <Figure
              label={stat.label}
              size="sm"
              value={stat.value}
              countTo={stat.count}
            />
          </div>
        ))}
      </div>

      {Object.keys(run.data.threshold ?? {}).length === 0 ? (
        <Caveat>
          No threshold was set for this evaluation, so the measurements above are recorded
          without a pass or fail judgement. The passing bar is the program office&apos;s to set.
        </Caveat>
      ) : (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-2xs uppercase tracking-wider text-faint">Threshold</span>
          <Spec value={run.data.threshold as Record<string, unknown>} />
        </div>
      )}

      {run.data.error ? <ErrorNote message={run.data.error} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented
          options={[
            { key: null, label: "All", count: (results.data ?? []).length },
            ...(["pass", "warning", "fail", "pending_human", "not_evaluated", "error"] as const)
              .filter((key) => counts[key])
              .map((key) => ({
                key,
                label: key.replace(/_/g, " "),
                count: counts[key],
              })),
          ]}
          active={status}
          onChange={setStatus}
        />
        <span className="flex items-center gap-1.5 text-2xs text-faint">
          <Key>↑</Key>
          <Key>↓</Key>
          step through results once one is open
        </span>
      </div>

      <Card>
        <CardHead title="Scenario results" meta={`${rows.length} shown`} />
        {results.loading ? (
          <TableSkeleton rows={8} cols={3} />
        ) : rows.length === 0 ? (
          <Empty title="No results match this filter" />
        ) : (
          <div className="border-t border-line">
            {rows.map((result, index) => (
              <button
                key={result.id}
                onClick={() => setOpenId(result.id)}
                style={{ ["--stagger-delay" as string]: `${Math.min(index, 14) * 18}ms` }}
                className={`stagger flex w-full items-start gap-3 border-b border-line px-4 py-2.5 text-left transition-colors duration-150 last:border-0 hover:bg-sunken ${
                  openId === result.id ? "bg-sunken" : ""
                }`}
              >
                <StatusSquare status={result.status} className="mt-[7px]" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink">
                    {result.request?.prompt?.slice(0, 150) ?? "(no prompt recorded)"}
                  </p>
                  <p className="mt-0.5 line-clamp-1 text-xs text-muted">
                    {result.response?.text?.slice(0, 180) ?? "(no output)"}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    {result.judgements.map((judgement, i) => (
                      <span
                        key={`${judgement.evaluator_key}-${i}`}
                        className="inline-flex items-center gap-1"
                        title={judgement.rationale ?? undefined}
                      >
                        <StatusSquare status={judgement.status} />
                        <span className="text-2xs text-faint">{judgement.evaluator_key}</span>
                        <EvaluatorKind kind={judgement.kind} />
                      </span>
                    ))}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className="tnum text-2xs text-faint">{formatMs(result.latency_ms)}</div>
                  <div className="mt-1">
                    <Hash value={result.content_hash} length={8} />
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </Card>

      <EvidencePanel resultId={openId} onClose={() => setOpenId(null)} onStep={step} />
    </div>
  );
}
