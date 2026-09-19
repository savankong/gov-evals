"use client";

import { useRouter } from "next/navigation";
import { use, useState } from "react";

import { SeverityTag } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Bar,
  Card,
  CardHead,
  Empty,
  ErrorNote,
  FilterChips,
  Table,
  TableSkeleton,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui";
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

/** Severity drives the bar's weight, so the eye lands on critical first even
 *  when a lower severity is the more numerous. */
const SEVERITY_TONE: Record<string, "fail" | "warn" | "ink" | "muted"> = {
  critical: "fail",
  high: "warn",
  medium: "ink",
  low: "muted",
  info: "muted",
};

export default function FindingsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const router = useRouter();
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

  if (findings.error)
    return <ErrorNote message={findings.error} status={findings.status} onRetry={findings.reload} />;

  const all = findings.data ?? [];
  const rows = all.filter(
    (f) => (!severity || f.severity === severity) && (!cluster || f.cluster_key === cluster),
  );
  const counts = all.reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1;
    return acc;
  }, {});
  const peak = Math.max(1, ...SEVERITIES.map((s) => counts[s] ?? 0));

  return (
    <div className="space-y-4">
      {/* The shape of the problem, before the rows. A reader should be able to
          tell whether this is two serious failures or forty trivial ones
          without scrolling a list. */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHead title="By severity" meta={`${all.length} findings`} />
          <div className="border-t border-line">
            {SEVERITIES.map((s) => {
              const count = counts[s] ?? 0;
              return (
                <button
                  key={s}
                  onClick={() => setSeverity(severity === s ? null : s)}
                  disabled={count === 0}
                  className={`flex w-full items-center gap-3 border-b border-line px-4 py-2 text-left transition-colors duration-150 ease-out last:border-b-0 enabled:hover:bg-sunken disabled:cursor-default ${
                    severity === s ? "bg-sunken" : ""
                  }`}
                >
                  <span className="w-20 shrink-0">
                    <SeverityTag severity={s} />
                  </span>
                  {/* Scaled against the largest bucket rather than the total,
                      so a lopsided distribution still shows its smaller bars. */}
                  <Bar
                    value={count / peak}
                    tone={count === 0 ? "muted" : SEVERITY_TONE[s]}
                    className="flex-1"
                  />
                  <span
                    className={`numeral tnum w-8 shrink-0 text-right text-base ${
                      count === 0 ? "text-faint" : "text-ink"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </Card>

        <Card>
          <CardHead
            title="Failure clusters"
            meta="Grouped by the evaluator that rejected them"
          />
          {(clusters.data?.clusters ?? []).length === 0 ? (
            <div className="border-t border-line">
              <Empty title="No clusters" />
            </div>
          ) : (
            <div className="border-t border-line">
              {(clusters.data?.clusters ?? []).slice(0, 6).map((item) => (
                <button
                  key={item.cluster_key}
                  onClick={() =>
                    setCluster(cluster === item.cluster_key ? null : item.cluster_key)
                  }
                  className={`flex w-full items-center justify-between gap-3 border-b border-line px-4 py-2 text-left transition-colors duration-150 ease-out last:border-b-0 hover:bg-sunken ${
                    cluster === item.cluster_key ? "bg-sunken" : ""
                  }`}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm text-ink">
                      {item.cluster_key.replace(/_/g, " ")}
                    </span>
                    {item.domains.slice(0, 2).map((domain) => (
                      <Tag key={domain}>{domain.replace(/_/g, " ")}</Tag>
                    ))}
                  </span>
                  <span className="numeral tnum shrink-0 text-base text-ink">{item.count}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-2">
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
          <Tag tone="strong" onClear={() => setCluster(null)} title="Clear this filter">
            cluster {cluster.replace(/_/g, " ")}
          </Tag>
        ) : null}
      </div>

      <Card>
        <CardHead
          title="Findings"
          meta={rows.length === all.length ? `${all.length} total` : `${rows.length} of ${all.length}`}
        />
        {findings.loading ? (
          <div className="border-t border-line">
            <TableSkeleton rows={6} cols={5} />
          </div>
        ) : rows.length === 0 ? (
          <div className="border-t border-line">
            <Empty
              title="No findings match this filter"
              detail={
                all.length === 0
                  ? "No evaluation has produced a failure yet. That is a statement about what has run, not about what is safe."
                  : undefined
              }
            />
          </div>
        ) : (
          <Table minWidth={860}>
            <thead>
              <tr>
                <Th className="w-[72px]">ID</Th>
                <Th className="w-[90px]">Severity</Th>
                <Th>Finding</Th>
                <Th className="w-[120px]">Domain</Th>
                <Th className="w-[130px]" align="right">
                  Reproduced
                </Th>
                <Th className="w-[96px]">Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((finding, index) => (
                <Tr
                  key={finding.id}
                  index={index}
                  onClick={() => router.push(`/findings/${finding.id}`)}
                >
                  <Td>
                    <span className="tnum font-mono text-2xs text-faint">{finding.key}</span>
                  </Td>
                  <Td>
                    <SeverityTag severity={finding.severity} />
                  </Td>
                  <Td>
                    <div className="text-sm text-ink">{finding.title}</div>
                    {finding.actual_behavior ? (
                      <div className="mt-0.5 line-clamp-1 text-xs text-muted">
                        {finding.actual_behavior}
                      </div>
                    ) : null}
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">
                      {finding.domain ? finding.domain.replace(/_/g, " ") : "—"}
                    </span>
                  </Td>
                  <Td align="right">
                    {finding.reproduction?.total_executions ? (
                      <span className="tnum text-xs text-muted">
                        {finding.reproduction.failed_executions}/
                        {finding.reproduction.total_executions} exec
                      </span>
                    ) : (
                      <span className="text-xs text-faint">—</span>
                    )}
                  </Td>
                  <Td>
                    <span className="text-2xs uppercase tracking-wider text-muted">
                      {finding.retest_status ?? finding.status}
                    </span>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
