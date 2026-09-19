"use client";

import Link from "next/link";
import { use, useState } from "react";

import { EvaluatorKindBadge, StatusChip } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHeader,
  Caveat,
  Crumbs,
  Empty,
  ErrorNote,
  FilterChips,
  Hash,
  Spinner,
  formatMs,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Result, Run } from "@/lib/types";

export default function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const [status, setStatus] = useState<string | null>(null);

  const run = useResource<Run>(() => api.get<Run>(`/runs/${runId}`), [runId]);
  // The run record does not carry a marking; its campaign does.
  const campaign = useResource<{ classification: string | null } | null>(
    () =>
      run.data
        ? api.get<{ classification: string | null }>(`/campaigns/${run.data.campaign_id}/summary`)
        : Promise.resolve(null),
    [run.data?.campaign_id],
  );
  useDeclaredClassification(campaign.data?.classification);
  const results = useResource<Result[]>(
    () => api.get<Result[]>(`/runs/${runId}/results?limit=300`),
    [runId],
  );

  if (run.loading || results.loading) return <Spinner label="Loading run" />;
  if (run.error) return <ErrorNote message={run.error} />;
  if (!run.data) return null;

  const rows = (results.data ?? []).filter((r) => !status || r.status === status);
  const metrics = run.data.metrics as Record<string, unknown>;
  const latency = metrics?.latency_ms as { median?: number; p95?: number } | undefined;

  const counts = (results.data ?? []).reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div>
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Campaign", href: `/campaigns/${run.data.campaign_id}` },
            { label: "Run" },
          ]}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">Run results</h1>
          <StatusChip status={run.data.verdict} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4 lg:grid-cols-6">
        {[
          { label: "Executions", value: run.data.scenario_count },
          {
            label: "Pass rate",
            value: formatPercent((metrics?.pass_rate as number | null) ?? null),
          },
          { label: "Passed", value: run.data.passed },
          { label: "Failed", value: run.data.failed },
          { label: "Awaiting review", value: run.data.pending_human },
          { label: "Median latency", value: formatMs(latency?.median) },
        ].map((stat) => (
          <div key={stat.label} className="bg-raised px-4 py-3">
            <div className="text-[11px] uppercase tracking-wider text-muted">{stat.label}</div>
            <div className="tnum mt-1 text-xl font-semibold">{stat.value}</div>
          </div>
        ))}
      </div>

      {Object.keys(run.data.threshold ?? {}).length === 0 ? (
        <Caveat>
          No threshold was set for this evaluation, so the measurements above are recorded without
          a pass or fail judgement. The passing bar is the program office&apos;s to set.
        </Caveat>
      ) : (
        <p className="text-xs text-muted">
          Threshold:{" "}
          <code className="rounded bg-[rgb(var(--unknown-bg))] px-1 py-0.5 font-mono text-[11px]">
            {JSON.stringify(run.data.threshold)}
          </code>
        </p>
      )}

      {run.data.error ? <ErrorNote message={run.data.error} /> : null}

      <FilterChips
        options={[
          { key: "pass", label: "Pass", count: counts.pass },
          { key: "warning", label: "Warning", count: counts.warning },
          { key: "fail", label: "Fail", count: counts.fail },
          { key: "pending_human", label: "Awaiting review", count: counts.pending_human },
          { key: "not_evaluated", label: "Not evaluated", count: counts.not_evaluated },
          { key: "error", label: "Error", count: counts.error },
        ].filter((option) => option.count)}
        active={status}
        onChange={setStatus}
        allLabel={`All (${(results.data ?? []).length})`}
      />

      <Card>
        <CardHeader title="Scenario results" subtitle={`${rows.length} shown`} />
        {rows.length === 0 ? (
          <Empty title="No results match this filter" />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((result) => (
              <Link
                key={result.id}
                href={`/results/${result.id}`}
                className="block px-4 py-3 transition-colors hover:bg-[rgb(var(--unknown-bg))]"
              >
                <div className="flex flex-wrap items-start gap-3">
                  <StatusChip status={result.status} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">
                      {result.request?.prompt?.slice(0, 160) ?? "(no prompt recorded)"}
                    </p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted">
                      {result.response?.text?.slice(0, 220) ?? "(no output)"}
                    </p>

                    {/* Each evaluator's judgement, with its kind, so a model
                        judgement is never mistaken for a deterministic one. */}
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {result.judgements.map((judgement, i) => (
                        <span
                          key={`${judgement.evaluator_key}-${i}`}
                          className="inline-flex items-center gap-1 text-[11px]"
                          title={judgement.rationale ?? undefined}
                        >
                          <StatusChip status={judgement.status} size="xs" />
                          <span className="text-muted">{judgement.evaluator_key}</span>
                          <EvaluatorKindBadge kind={judgement.kind} />
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="shrink-0 text-right text-xs text-muted">
                    <div className="tnum">{formatMs(result.latency_ms)}</div>
                    <div className="mt-1">
                      <Hash value={result.content_hash} length={8} />
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
