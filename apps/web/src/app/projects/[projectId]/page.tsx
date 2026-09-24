"use client";

import Link from "next/link";
import { use } from "react";

import { SeverityTag, Status, StatusSquare } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Figure,
  Hash,
  TableSkeleton,
  formatDate,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { ProjectDashboard, ReadinessDimension, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export default function ReadinessPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const { data, error, loading } = useResource<ProjectDashboard>(
    () => api.get<ProjectDashboard>(`/projects/${projectId}/dashboard`),
    [projectId],
  );

  if (loading) {
    return (
      <Card>
        <TableSkeleton rows={8} cols={4} />
      </Card>
    );
  }
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const evaluated = data.readiness.filter((d) => d.status !== "not_evaluated").length;
  const live = data.latest_campaign?.status === "running";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHead
            title="Mission readiness"
            meta={`${evaluated} of ${data.readiness.length} dimensions evaluated`}
            action={
              data.latest_campaign ? (
                <Link
                  href={`/campaigns/${data.latest_campaign.id}`}
                  className="link-underline inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
                >
                  {live ? <StatusSquare status="pending_human" live /> : null}
                  {data.latest_campaign.name}
                </Link>
              ) : null
            }
          />

          <div className="border-t border-line">
            {data.readiness.map((dimension, index) => (
              <DimensionRow key={dimension.domain} dimension={dimension} index={index} />
            ))}
          </div>

          <div className="border-t border-line px-4 py-3">
            <Caveat>{data.note}</Caveat>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHead title="Findings" meta={`${data.findings_total} recorded`} />
            <div className="border-t border-line">
              {SEVERITIES.map((severity, index) => (
                <div
                  key={severity}
                  className="stagger flex items-center justify-between border-b border-line px-4 py-2 last:border-0"
                  style={{ ["--stagger-delay" as string]: `${index * 30}ms` }}
                >
                  <SeverityTag severity={severity} />
                  <span className="tnum text-base">{data.findings[severity] ?? 0}</span>
                </div>
              ))}
            </div>
            <Link
              href={`/projects/${projectId}/findings`}
              className="link-underline block border-t border-line px-4 py-2 text-xs text-muted hover:text-ink"
            >
              All findings
            </Link>
          </Card>

          {data.regression ? (
            <Card>
              <CardHead
                title="Most recent change"
                meta={`vs ${data.regression.baseline_campaign.name}`}
              />
              <div className="border-t border-line px-4 py-3">
                <p
                  className={`text-sm ${
                    data.regression.regression_detected ? "text-fail" : "text-pass"
                  }`}
                >
                  {data.regression.regression_detected
                    ? "Regression detected"
                    : "No regression detected"}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {[
                    ["New failures", data.regression.totals.new_failures],
                    ["Degraded", data.regression.totals.degraded],
                    ["Resolved", data.regression.totals.resolved],
                    ["Improved", data.regression.totals.improved],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex justify-between">
                      <dt className="text-muted">{label}</dt>
                      <dd className="tnum">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHead title="Inventory" />
            <dl className="border-t border-line px-4 py-3 text-xs">
              {[
                ["Scenarios", data.inventory.scenarios, false],
                [
                  "Drafts awaiting approval",
                  data.inventory.scenarios_awaiting_approval,
                  data.inventory.scenarios_awaiting_approval > 0,
                ],
                ["Datasets", data.inventory.datasets, false],
                ["Campaigns", data.inventory.campaigns, false],
              ].map(([label, value, warn]) =>
                label === "Drafts awaiting approval" && !value ? null : (
                  <div key={String(label)} className="flex justify-between py-0.5">
                    <dt className={warn ? "text-warn" : "text-muted"}>{label}</dt>
                    <dd className={`tnum ${warn ? "text-warn" : ""}`}>{String(value)}</dd>
                  </div>
                ),
              )}
            </dl>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHead title="Systems under evaluation" />
          {data.systems.length === 0 ? (
            <Empty title="No system registered" detail="Register the system and its configuration." />
          ) : (
            <div className="border-t border-line">
              {data.systems.map((system, index) => (
                <div
                  key={system.version_id}
                  className="stagger border-b border-line px-4 py-3 last:border-0"
                  style={{ ["--stagger-delay" as string]: `${index * 40}ms` }}
                >
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-base text-ink">{system.system}</span>
                    <span className="text-sm text-muted">{system.version}</span>
                    <span className="border border-line px-1 py-px text-2xs uppercase tracking-wider text-faint">
                      {system.kind}
                    </span>
                  </div>
                  <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-muted">
                    <dt>Model</dt>
                    <dd className="text-ink-soft">{system.model_name ?? "not recorded"}</dd>
                    <dt>Connector</dt>
                    <dd className="text-ink-soft">{system.connector}</dd>
                    <dt>Configuration</dt>
                    <dd>
                      <Hash value={system.config_hash} length={16} />
                    </dd>
                  </dl>
                </div>
              ))}
            </div>
          )}
        </Card>

        {data.mission ? (
          <Card>
            <CardHead title="Mission profile" meta="What the evaluation is judged against" />
            <div className="space-y-3 border-t border-line px-4 py-3">
              {data.mission.tasks.length > 0 ? (
                <div>
                  <div className="text-2xs uppercase tracking-wider text-faint">Tasks</div>
                  <ul className="mt-1 space-y-0.5 text-sm">
                    {data.mission.tasks.map((task) => (
                      <li key={task}>{task}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {data.mission.unacceptable_failures.length > 0 ? (
                <div>
                  <div className="text-2xs uppercase tracking-wider text-faint">
                    Declared unacceptable
                  </div>
                  <ul className="mt-1 space-y-1">
                    {data.mission.unacceptable_failures.map((failure) => (
                      <li key={failure} className="flex gap-2 text-sm">
                        <span className="mt-[7px] h-[5px] w-[5px] shrink-0 bg-fail" />
                        {failure}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {data.mission.latency_requirement_ms ? (
                <p className="text-xs text-muted">
                  Latency requirement{" "}
                  <span className="tnum text-ink">{data.mission.latency_requirement_ms} ms</span>
                </p>
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
        <p className="text-xs text-faint">
          Latest campaign {data.latest_campaign.name} · {data.latest_campaign.status} ·{" "}
          {formatDate(data.latest_campaign.completed_at)}
        </p>
      ) : null}
    </div>
  );
}

/**
 * One dimension of readiness.
 *
 * The proportion bar is drawn only when something was judged. An empty bar
 * beside an untested dimension would read as a score of zero, which is a
 * different claim from "not tested" — so the row says which it is in words.
 */
function DimensionRow({
  dimension,
  index,
}: {
  dimension: ReadinessDimension;
  index: number;
}) {
  const scoreable = dimension.passed + dimension.failed + dimension.warning;

  return (
    <div
      className="stagger group flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5 transition-colors duration-150 last:border-0 hover:bg-sunken"
      style={{ ["--stagger-delay" as string]: `${index * 24}ms` }}
    >
      <div className="w-40 shrink-0 text-base text-ink">{dimension.label}</div>
      <div className="w-[8rem] shrink-0">
        <Status status={dimension.status} />
      </div>

      {scoreable > 0 ? (
        <div className="flex h-[3px] min-w-[5.25rem] flex-1 overflow-hidden bg-line">
          {[
            { n: dimension.passed, cls: "bg-pass" },
            { n: dimension.warning, cls: "bg-warn" },
            { n: dimension.failed, cls: "bg-fail" },
          ].map((part, i) => (
            <div
              key={i}
              className={`h-full ${part.cls} transition-[width] duration-700 ease-out`}
              style={{ width: `${(part.n / scoreable) * 100}%` }}
            />
          ))}
        </div>
      ) : (
        <div className="min-w-[5.25rem] flex-1 text-xs text-faint">
          {dimension.pending_human > 0
            ? `${dimension.pending_human} awaiting human review`
            : dimension.executions > 0
              ? `${dimension.executions} executed, none reached a judgement`
              : "No evaluation covers this dimension"}
        </div>
      )}

      <div className="tnum w-14 shrink-0 text-right text-base">
        {formatPercent(dimension.pass_rate)}
      </div>

      <div className="w-16 shrink-0 text-right">
        {dimension.run_ids.length > 0 ? (
          <Link
            href={`/runs/${dimension.run_ids[0]}`}
            className="link-underline text-xs text-faint opacity-0 transition-opacity duration-150 group-hover:opacity-100 hover:text-ink"
          >
            evidence
          </Link>
        ) : null}
      </div>
    </div>
  );
}
