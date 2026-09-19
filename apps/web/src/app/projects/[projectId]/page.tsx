"use client";

import Link from "next/link";
import { use } from "react";

import { StatusChip, SeverityChip } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHeader,
  Caveat,
  Empty,
  ErrorNote,
  Hash,
  Spinner,
  formatDate,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { ProjectDashboard, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export default function ProjectReadinessPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { data, error, loading } = useResource<ProjectDashboard>(
    () => api.get<ProjectDashboard>(`/projects/${projectId}/dashboard`),
    [projectId],
  );

  if (loading) return <Spinner label="Loading readiness" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const evaluated = data.readiness.filter((d) => d.status !== "not_evaluated").length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Mission readiness by dimension. Every domain appears, including the
            untested ones -- that is the point of the view. */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Mission readiness"
            subtitle={`${evaluated} of ${data.readiness.length} dimensions evaluated`}
            action={
              data.latest_campaign ? (
                <Link
                  href={`/campaigns/${data.latest_campaign.id}`}
                  className="text-xs text-muted hover:text-ink hover:underline"
                >
                  {data.latest_campaign.name} →
                </Link>
              ) : null
            }
          />

          <div className="divide-y divide-line">
            {data.readiness.map((dimension) => {
              const scoreable = dimension.passed + dimension.failed + dimension.warning;
              return (
                <div
                  key={dimension.domain}
                  className="flex flex-wrap items-center gap-3 px-4 py-2.5"
                >
                  <div className="w-44 shrink-0 text-sm font-medium">{dimension.label}</div>
                  <StatusChip status={dimension.status} />

                  {/* Proportion bar. Only drawn when something was judged, so an
                      untested dimension never shows an empty bar that reads as zero. */}
                  {scoreable > 0 ? (
                    <div className="flex h-1.5 min-w-[80px] flex-1 overflow-hidden rounded-full bg-[rgb(var(--unknown-bg))]">
                      <div
                        className="h-full bg-[rgb(var(--pass))]"
                        style={{ width: `${(dimension.passed / scoreable) * 100}%` }}
                        title={`${dimension.passed} passed`}
                      />
                      <div
                        className="h-full bg-[rgb(var(--warn))]"
                        style={{ width: `${(dimension.warning / scoreable) * 100}%` }}
                        title={`${dimension.warning} warning`}
                      />
                      <div
                        className="h-full bg-[rgb(var(--fail))]"
                        style={{ width: `${(dimension.failed / scoreable) * 100}%` }}
                        title={`${dimension.failed} failed`}
                      />
                    </div>
                  ) : (
                    <div className="min-w-[80px] flex-1 text-xs text-muted">
                      {dimension.pending_human > 0
                        ? `${dimension.pending_human} awaiting human review`
                        : dimension.executions > 0
                          ? `${dimension.executions} executed, none reached a judgement`
                          : "No evaluation covers this dimension"}
                    </div>
                  )}

                  <div className="tnum w-16 shrink-0 text-right text-sm">
                    {formatPercent(dimension.pass_rate)}
                  </div>

                  {dimension.run_ids.length > 0 ? (
                    <Link
                      href={`/runs/${dimension.run_ids[0]}`}
                      className="shrink-0 text-xs text-muted hover:text-ink hover:underline"
                    >
                      evidence →
                    </Link>
                  ) : (
                    <span className="w-[62px] shrink-0" />
                  )}
                </div>
              );
            })}
          </div>

          <div className="border-t border-line px-4 py-3">
            <Caveat>{data.note}</Caveat>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Findings" subtitle={`${data.findings_total} recorded`} />
            <div className="divide-y divide-line">
              {SEVERITIES.map((severity) => (
                <div key={severity} className="flex items-center justify-between px-4 py-2">
                  <SeverityChip severity={severity} />
                  <span className="tnum text-sm">{data.findings[severity] ?? 0}</span>
                </div>
              ))}
            </div>
            <div className="border-t border-line px-4 py-2">
              <Link
                href={`/projects/${projectId}/findings`}
                className="text-xs text-muted hover:text-ink hover:underline"
              >
                All findings →
              </Link>
            </div>
          </Card>

          {data.regression ? (
            <Card>
              <CardHeader
                title="Most recent change"
                subtitle={`vs ${data.regression.baseline_campaign.name}`}
              />
              <div className="space-y-1.5 px-4 py-3 text-sm">
                {data.regression.regression_detected ? (
                  <p className="font-medium text-[rgb(var(--fail))]">Regression detected</p>
                ) : (
                  <p className="font-medium text-[rgb(var(--pass))]">No regression detected</p>
                )}
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <dt className="text-muted">New failures</dt>
                  <dd className="tnum text-right">{data.regression.totals.new_failures}</dd>
                  <dt className="text-muted">Degraded</dt>
                  <dd className="tnum text-right">{data.regression.totals.degraded}</dd>
                  <dt className="text-muted">Resolved</dt>
                  <dd className="tnum text-right">{data.regression.totals.resolved}</dd>
                  <dt className="text-muted">Improved</dt>
                  <dd className="tnum text-right">{data.regression.totals.improved}</dd>
                </dl>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Inventory" />
            <dl className="space-y-1 px-4 py-3 text-xs">
              <div className="flex justify-between">
                <dt className="text-muted">Scenarios</dt>
                <dd className="tnum">{data.inventory.scenarios}</dd>
              </div>
              {data.inventory.scenarios_awaiting_approval > 0 ? (
                <div className="flex justify-between">
                  <dt className="text-[rgb(var(--warn))]">Drafts awaiting approval</dt>
                  <dd className="tnum text-[rgb(var(--warn))]">
                    {data.inventory.scenarios_awaiting_approval}
                  </dd>
                </div>
              ) : null}
              <div className="flex justify-between">
                <dt className="text-muted">Datasets</dt>
                <dd className="tnum">{data.inventory.datasets}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Campaigns</dt>
                <dd className="tnum">{data.inventory.campaigns}</dd>
              </div>
            </dl>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Systems under evaluation" />
          {data.systems.length === 0 ? (
            <Empty title="No system registered" detail="Register the system and its configuration." />
          ) : (
            <div className="divide-y divide-line">
              {data.systems.map((system) => (
                <div key={system.version_id} className="px-4 py-3">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-sm font-medium">{system.system}</span>
                    <span className="text-sm text-muted">{system.version}</span>
                    <span className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                      {system.kind}
                    </span>
                  </div>
                  <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-muted">
                    <div className="flex gap-1.5">
                      <dt>Model</dt>
                      <dd className="text-ink">{system.model_name ?? "not recorded"}</dd>
                    </div>
                    <div className="flex gap-1.5">
                      <dt>Connector</dt>
                      <dd className="text-ink">{system.connector}</dd>
                    </div>
                    <div className="col-span-2 flex items-center gap-1.5">
                      <dt>Configuration</dt>
                      <dd>
                        <Hash value={system.config_hash} length={16} />
                      </dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          )}
        </Card>

        {data.mission ? (
          <Card>
            <CardHeader
              title="Mission profile"
              subtitle="What the evaluation is judged against"
            />
            <div className="space-y-3 px-4 py-3 text-sm">
              {data.mission.tasks.length > 0 ? (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">Tasks</div>
                  <ul className="mt-1 space-y-0.5">
                    {data.mission.tasks.map((task) => (
                      <li key={task} className="text-sm">
                        {task}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {data.mission.unacceptable_failures.length > 0 ? (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">
                    Declared unacceptable
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {data.mission.unacceptable_failures.map((failure) => (
                      <li key={failure} className="flex gap-2 text-sm">
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--fail))]" />
                        {failure}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {data.mission.latency_requirement_ms ? (
                <div className="text-xs text-muted">
                  Latency requirement:{" "}
                  <span className="tnum text-ink">{data.mission.latency_requirement_ms} ms</span>
                </div>
              ) : null}
            </div>
          </Card>
        ) : (
          <Card>
            <Empty
              title="No mission profile"
              detail="Without operational context, results say how the system performed on some inputs, not whether it suits a mission."
            />
          </Card>
        )}
      </div>

      {data.latest_campaign ? (
        <p className="text-xs text-muted">
          Latest campaign {data.latest_campaign.name} · {data.latest_campaign.status} ·{" "}
          {formatDate(data.latest_campaign.completed_at)}
        </p>
      ) : null}
    </div>
  );
}
