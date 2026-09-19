"use client";

import Link from "next/link";
import { use, useState } from "react";

import { StatusChip } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHeader,
  Caveat,
  Crumbs,
  ErrorNote,
  FilterChips,
  Hash,
  Spinner,
  Stat,
  formatMs,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { CampaignSummary, Campaign, Run } from "@/lib/types";

interface SummaryResponse {
  campaign: Campaign;
  classification: string | null;
  summary: CampaignSummary;
  runs: Run[];
}

export default function CampaignPage({ params }: { params: Promise<{ campaignId: string }> }) {
  const { campaignId } = use(params);
  const [domain, setDomain] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);

  const { data, error, loading } = useResource<SummaryResponse>(
    () => api.get<SummaryResponse>(`/campaigns/${campaignId}/summary`),
    [campaignId],
  );

  useDeclaredClassification(data?.classification);

  if (loading) return <Spinner label="Loading campaign" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { campaign, summary, runs } = data;
  const scoreable = summary.passed + summary.warning + summary.failed;
  const passRate = scoreable > 0 ? summary.passed / scoreable : null;

  const domains = Object.entries(summary.domains ?? {}).map(([key, bucket]) => ({
    key,
    label: key.replace(/_/g, " "),
    count: bucket.runs,
  }));

  const filtered = runs.filter(
    (run) =>
      (!domain || run.evaluation?.domain === domain) && (!verdict || run.verdict === verdict),
  );

  return (
    <div className="space-y-4">
      <div>
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Project", href: `/projects/${campaign.project_id}` },
            { label: campaign.name },
          ]}
        />
        <h1 className="mt-1.5 text-lg font-semibold tracking-tight">{campaign.name}</h1>
        {campaign.description ? (
          <p className="mt-0.5 text-sm text-muted">{campaign.description}</p>
        ) : null}
      </div>

      {/* Headline figure with the status counts beside it, including the ones
          that never reached a judgement. */}
      <Card>
        <div className="flex flex-col gap-6 p-5 lg:flex-row lg:items-center">
          <div>
            <div className="tnum text-5xl font-semibold tracking-tight">
              {passRate === null ? (
                <span className="text-2xl text-muted">No judgements yet</span>
              ) : (
                formatPercent(passRate)
              )}
            </div>
            <div className="mt-1 text-sm text-muted">
              {passRate === null
                ? `${summary.executed} executions`
                : `of ${scoreable} judged executions passed`}
            </div>
          </div>

          <div className="grid flex-1 grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
            {[
              { label: "Passed", value: summary.passed, status: "pass" },
              { label: "Warning", value: summary.warning, status: "warning" },
              { label: "Failed", value: summary.failed, status: "fail" },
              { label: "Errored", value: summary.errors, status: "error" },
              { label: "Awaiting review", value: summary.pending_human, status: "pending_human" },
              {
                label: "Not judged",
                value: summary.executed - scoreable - summary.errors - summary.pending_human,
                status: "not_evaluated",
              },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-2">
                <StatusChip status={item.status} size="xs" />
                <span className="tnum text-sm font-medium">{Math.max(0, item.value)}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-line px-5 py-3">
          <Caveat>
            A pass rate is the share of executions that reached a judgement and passed. Executions
            that reached no judgement are counted separately and never folded into it.
          </Caveat>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <FilterChips
          options={domains}
          active={domain}
          onChange={setDomain}
          allLabel={`All domains (${runs.length})`}
        />
        <div className="h-4 w-px bg-line" />
        <FilterChips
          options={[
            { key: "pass", label: "Pass" },
            { key: "warning", label: "Warning" },
            { key: "fail", label: "Fail" },
            { key: "not_evaluated", label: "Not evaluated" },
          ]}
          active={verdict}
          onChange={setVerdict}
          allLabel="Any verdict"
        />
      </div>

      <Card>
        <CardHeader
          title="Runs"
          subtitle={`${filtered.length} of ${runs.length} shown`}
          action={
            <div className="flex gap-3 text-xs">
              <Link
                href={`/projects/${campaign.project_id}/compare?campaign=${campaign.id}`}
                className="text-muted hover:text-ink hover:underline"
              >
                Compare systems →
              </Link>
            </div>
          }
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-4 py-2 font-medium">Evaluation</th>
                <th className="px-4 py-2 font-medium">System</th>
                <th className="px-4 py-2 font-medium">Evaluators</th>
                <th className="px-4 py-2 font-medium">Verdict</th>
                <th className="px-4 py-2 text-right font-medium">Pass rate</th>
                <th className="px-4 py-2 text-right font-medium">P / W / F</th>
                <th className="px-4 py-2 text-right font-medium">Duration</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((run) => (
                <tr
                  key={run.id}
                  className="border-b border-line last:border-0 hover:bg-[rgb(var(--unknown-bg))]"
                >
                  <td className="px-4 py-2.5">
                    <Link href={`/runs/${run.id}`} className="font-medium hover:underline">
                      {run.evaluation?.name ?? run.evaluation_id}
                    </Link>
                    <div className="mt-0.5 text-[11px] text-muted">
                      {run.evaluation?.domain?.replace(/_/g, " ")} ·{" "}
                      {run.evaluation?.layer?.replace(/_/g, " ")}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-xs">
                    {run.system_version?.label ?? "—"}
                    <div className="mt-0.5">
                      <Hash value={run.system_version?.config_hash} length={10} />
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {(run.evaluation?.evaluators ?? []).map((ev) => (
                        <span
                          key={ev}
                          className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] text-muted"
                        >
                          {ev}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusChip status={run.verdict} />
                    {Object.keys(run.threshold ?? {}).length === 0 ? (
                      <div className="mt-0.5 text-[10px] text-muted">no threshold set</div>
                    ) : null}
                  </td>
                  <td className="tnum px-4 py-2.5 text-right">
                    {formatPercent((run.metrics as { pass_rate?: number | null })?.pass_rate)}
                  </td>
                  <td className="tnum px-4 py-2.5 text-right text-xs">
                    <span className="text-[rgb(var(--pass))]">{run.passed}</span>
                    {" / "}
                    <span className="text-[rgb(var(--warn))]">{run.warned}</span>
                    {" / "}
                    <span className="text-[rgb(var(--fail))]">{run.failed}</span>
                  </td>
                  <td className="tnum px-4 py-2.5 text-right text-xs text-muted">
                    {formatMs(run.duration_ms)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
