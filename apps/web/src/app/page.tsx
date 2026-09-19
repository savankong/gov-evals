"use client";

import Link from "next/link";

import { Card, CardHeader, Empty, ErrorNote, Spinner, Stat, formatPercent } from "@/components/ui";
import { SeverityChip } from "@/components/status";
import { useResource } from "@/components/shell";
import { api } from "@/lib/api";
import type { Overview, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export default function PortfolioPage() {
  const { data, error, loading } = useResource<Overview>(() => api.get<Overview>("/dashboard"));

  if (loading) return <Spinner label="Loading portfolio" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { counts, findings, risks, evidence_coverage: coverage } = data;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Portfolio</h1>
        <p className="mt-0.5 text-sm text-muted">
          Every AI capability under evaluation, and the evidence behind it.
        </p>
      </div>

      {/* North star: not a score, a coverage ratio with its definition attached. */}
      <Card>
        <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">
              Complete evidence chain
            </div>
            <div className="tnum mt-1 text-3xl font-semibold">
              {coverage.projects_with_complete_chain}
              <span className="text-lg font-normal text-muted"> / {coverage.projects}</span>
              {coverage.ratio !== null ? (
                <span className="ml-2 text-base font-normal text-muted">
                  ({formatPercent(coverage.ratio)})
                </span>
              ) : null}
            </div>
          </div>
          <p className="max-w-2xl border-l-2 border-line pl-3 text-xs leading-relaxed text-muted sm:ml-4">
            {coverage.definition}
          </p>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "Projects", value: counts.projects },
          { label: "Systems", value: counts.systems },
          { label: "Campaigns", value: counts.campaigns },
          { label: "Executions", value: counts.executions?.toLocaleString() },
          {
            label: "Failures",
            value: counts.failures,
            tone: counts.failures > 0 ? ("fail" as const) : undefined,
          },
          {
            label: "Awaiting review",
            value: counts.awaiting_human_review,
            tone: counts.awaiting_human_review > 0 ? ("warn" as const) : undefined,
          },
        ].map((stat) => (
          <div key={stat.label} className="bg-raised">
            <Stat label={stat.label} value={stat.value ?? "—"} tone={stat.tone} />
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Projects"
            subtitle={`${data.projects.length} under evaluation`}
          />
          {data.projects.length === 0 ? (
            <Empty
              title="No projects yet"
              detail="A project pairs an AI capability with the mission it is intended for."
            />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2 font-medium">Project</th>
                  <th className="px-4 py-2 font-medium">Marking</th>
                  <th className="px-4 py-2 font-medium">Impact</th>
                  <th className="px-4 py-2 text-right font-medium">Open findings</th>
                  <th className="px-4 py-2 text-right font-medium">Critical</th>
                </tr>
              </thead>
              <tbody>
                {data.projects.map((project) => (
                  <tr
                    key={project.id}
                    className="border-b border-line last:border-0 hover:bg-[rgb(var(--unknown-bg))]"
                  >
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/projects/${project.id}`}
                        className="font-medium hover:underline"
                      >
                        {project.name}
                      </Link>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{project.classification}</td>
                    <td className="px-4 py-2.5 text-xs text-muted">
                      {project.impact_level ?? "—"}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right">{project.open_findings}</td>
                    <td className="tnum px-4 py-2.5 text-right">
                      {project.critical_findings > 0 ? (
                        <span className="font-semibold text-[rgb(var(--fail))]">
                          {project.critical_findings}
                        </span>
                      ) : (
                        <span className="text-muted">0</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Open findings" subtitle="Unresolved, across the portfolio" />
            <div className="divide-y divide-line">
              {SEVERITIES.map((severity) => {
                const count = findings[severity] ?? 0;
                const total = SEVERITIES.reduce((sum, s) => sum + (findings[s] ?? 0), 0);
                const width = total > 0 ? (count / total) * 100 : 0;
                return (
                  <div key={severity} className="flex items-center gap-3 px-4 py-2">
                    <SeverityChip severity={severity} />
                    <div className="h-1 flex-1 overflow-hidden rounded-full bg-[rgb(var(--unknown-bg))]">
                      <div
                        className={`h-full rounded-full ${
                          severity === "critical"
                            ? "bg-[rgb(var(--fail))]"
                            : severity === "high"
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
            <CardHeader title="Risks" />
            <div className="grid grid-cols-3 divide-x divide-line">
              <Stat label="Total" value={risks.total} />
              <Stat label="Open" value={risks.open} tone={risks.open ? "warn" : "muted"} />
              <Stat label="Accepted" value={risks.accepted} tone="muted" />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
