"use client";

import Link from "next/link";
import { use, useState } from "react";

import { SeverityChip } from "@/components/status";
import { useResource } from "@/components/shell";
import { Card, CardHeader, Empty, ErrorNote, FilterChips, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Finding, Severity } from "@/lib/types";

interface Cluster {
  cluster_key: string;
  count: number;
  active: number;
  severities: Record<string, number>;
  domains: string[];
  finding_keys: string[];
}

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export default function FindingsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const [severity, setSeverity] = useState<string | null>(null);
  const [cluster, setCluster] = useState<string | null>(null);

  const findings = useResource<Finding[]>(
    () => api.get<Finding[]>(`/projects/${projectId}/findings`),
    [projectId],
  );
  const clusters = useResource<{ clusters: Cluster[] }>(
    () => api.get<{ clusters: Cluster[] }>(`/projects/${projectId}/findings/clusters`),
    [projectId],
  );

  if (findings.loading) return <Spinner label="Loading findings" />;
  if (findings.error) return <ErrorNote message={findings.error} />;

  const all = findings.data ?? [];
  const rows = all.filter(
    (f) => (!severity || f.severity === severity) && (!cluster || f.cluster_key === cluster),
  );
  const counts = all.reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {/* Summary cards above the list, so the shape of the problem is visible
          before the individual rows. */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader title="By severity" subtitle={`${all.length} findings`} />
          <div className="divide-y divide-line">
            {SEVERITIES.map((s) => {
              const count = counts[s] ?? 0;
              const width = all.length ? (count / all.length) * 100 : 0;
              return (
                <div key={s} className="flex items-center gap-3 px-4 py-2">
                  <SeverityChip severity={s} />
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-[rgb(var(--unknown-bg))]">
                    <div
                      className={`h-full rounded-full ${
                        s === "critical"
                          ? "bg-[rgb(var(--fail))]"
                          : s === "high"
                            ? "bg-[rgb(var(--warn))]"
                            : "bg-[rgb(var(--accent))]"
                      }`}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <span className="tnum w-8 text-right text-sm">{count}</span>
                </div>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Failure clusters"
            subtitle="Grouped by the evaluator that rejected them"
          />
          {(clusters.data?.clusters ?? []).length === 0 ? (
            <Empty title="No clusters" />
          ) : (
            <div className="divide-y divide-line">
              {(clusters.data?.clusters ?? []).slice(0, 6).map((item) => (
                <button
                  key={item.cluster_key}
                  onClick={() =>
                    setCluster(cluster === item.cluster_key ? null : item.cluster_key)
                  }
                  className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left transition-colors hover:bg-[rgb(var(--unknown-bg))] ${
                    cluster === item.cluster_key ? "bg-[rgb(var(--unknown-bg))]" : ""
                  }`}
                >
                  <span className="truncate text-sm">
                    {item.cluster_key.replace(/_/g, " ")}
                    {item.domains.length ? (
                      <span className="ml-2 text-xs text-muted">{item.domains.join(", ")}</span>
                    ) : null}
                  </span>
                  <span className="tnum shrink-0 text-sm text-muted">{item.count}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <FilterChips
          options={SEVERITIES.filter((s) => counts[s]).map((s) => ({
            key: s,
            label: s,
            count: counts[s],
          }))}
          active={severity}
          onChange={setSeverity}
          allLabel={`All severities (${all.length})`}
        />
        {cluster ? (
          <button
            onClick={() => setCluster(null)}
            className="rounded-full border border-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 px-2.5 py-1 text-xs"
          >
            cluster: {cluster} ×
          </button>
        ) : null}
      </div>

      <Card>
        <CardHeader title="Findings" subtitle={`${rows.length} shown`} />
        {rows.length === 0 ? (
          <Empty
            title="No findings match this filter"
            detail={all.length === 0 ? "No evaluation has produced a failure yet." : undefined}
          />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((finding) => (
              <Link
                key={finding.id}
                href={`/findings/${finding.id}`}
                className="block px-4 py-3 transition-colors hover:bg-[rgb(var(--unknown-bg))]"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <code className="tnum font-mono text-xs text-muted">{finding.key}</code>
                  <SeverityChip severity={finding.severity} />
                  <span className="text-sm font-medium">{finding.title}</span>
                  <span className="ml-auto text-xs text-muted">{finding.status}</span>
                </div>
                {finding.actual_behavior ? (
                  <p className="mt-1 line-clamp-2 text-xs text-muted">{finding.actual_behavior}</p>
                ) : null}
                <div className="mt-1.5 flex flex-wrap gap-3 text-[11px] text-muted">
                  {finding.reproduction?.failed_executions ? (
                    <span>
                      reproduced {finding.reproduction.failed_executions}/
                      {finding.reproduction.total_executions} executions
                    </span>
                  ) : null}
                  {finding.domain ? <span>{finding.domain.replace(/_/g, " ")}</span> : null}
                  {finding.owner ? <span>owner: {finding.owner}</span> : null}
                  {finding.retest_status ? <span>retest: {finding.retest_status}</span> : null}
                </div>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
