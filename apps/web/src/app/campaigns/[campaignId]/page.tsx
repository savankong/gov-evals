"use client";

import Link from "next/link";
import { use, useMemo, useState } from "react";

import { Status, StatusSquare } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Crumbs,
  ErrorNote,
  Figure,
  Hash,
  Segmented,
  Table,
  TableSkeleton,
  Td,
  Th,
  Tr,
  formatMs,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, CampaignSummary, Run } from "@/lib/types";

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

  const filtered = useMemo(
    () =>
      (data?.runs ?? []).filter(
        (run) =>
          (!domain || run.evaluation?.domain === domain) &&
          (!verdict || run.verdict === verdict),
      ),
    [data?.runs, domain, verdict],
  );

  if (loading) {
    return (
      <Card>
        <TableSkeleton rows={10} cols={6} />
      </Card>
    );
  }
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { campaign, summary, runs } = data;
  const scoreable = summary.passed + summary.warning + summary.failed;
  const passRate = scoreable > 0 ? summary.passed / scoreable : null;
  const unjudged = Math.max(
    0,
    summary.executed - scoreable - summary.errors - summary.pending_human,
  );

  const domains = Object.entries(summary.domains ?? {}).map(([key, bucket]) => ({
    key,
    label: key.replace(/_/g, " "),
    count: bucket.runs,
  }));

  return (
    <div className="space-y-4">
      <div className="animate-rise">
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Project", href: `/projects/${campaign.project_id}` },
            { label: campaign.name },
          ]}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-normal text-ink">{campaign.name}</h1>
          <span className="inline-flex items-center gap-1.5 border border-line px-1.5 py-0.5 text-2xs uppercase tracking-wider text-muted">
            <StatusSquare
              status={campaign.status === "completed" ? "pass" : "pending_human"}
              live={campaign.status === "running"}
            />
            {campaign.status.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {/* Headline figure with every status counted beside it, including the
          ones that never reached a judgement. */}
      <Card>
        <div className="flex flex-col gap-8 px-5 py-5 lg:flex-row lg:items-center">
          <div className="lg:w-64">
            {passRate === null ? (
              <Figure label="Pass rate" value="No judgements yet" size="sm" tone="muted" />
            ) : (
              <Figure
                label="Pass rate"
                countTo={passRate}
                format={(n) => formatPercent(n)}
                size="xl"
                note={`of ${scoreable.toLocaleString()} judged executions`}
              />
            )}
          </div>

          <div className="grid flex-1 grid-cols-2 gap-x-8 gap-y-2.5 sm:grid-cols-3">
            {[
              { label: "Passed", value: summary.passed, status: "pass" },
              { label: "Warning", value: summary.warning, status: "warning" },
              { label: "Failed", value: summary.failed, status: "fail" },
              { label: "Errored", value: summary.errors, status: "error" },
              { label: "Awaiting review", value: summary.pending_human, status: "pending_human" },
              { label: "Not judged", value: unjudged, status: "not_evaluated" },
            ].map((item, index) => (
              <div
                key={item.label}
                className="stagger flex items-baseline gap-2"
                style={{ ["--stagger-delay" as string]: `${index * 30}ms` }}
              >
                <StatusSquare status={item.status} className="translate-y-[-1px]" />
                <span className="tnum text-lg text-ink">{item.value}</span>
                <span className="text-xs text-muted">{item.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-line px-5 py-3">
          <Caveat>
            A pass rate is the share of executions that reached a judgement and passed.
            Executions that reached none are counted separately and never folded into it.
          </Caveat>
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          options={[
            { key: null, label: "All domains", count: runs.length },
            ...domains.map((d) => ({ key: d.key, label: d.label, count: d.count })),
          ]}
          active={domain}
          onChange={setDomain}
        />
        <Segmented
          options={[
            { key: null, label: "Any verdict" },
            { key: "pass", label: "Pass" },
            { key: "warning", label: "Warning" },
            { key: "fail", label: "Fail" },
            { key: "not_evaluated", label: "Not evaluated" },
          ]}
          active={verdict}
          onChange={setVerdict}
        />
      </div>

      <Card>
        <CardHead
          title="Runs"
          meta={`${filtered.length} of ${runs.length}`}
          action={
            <Link
              href={`/projects/${campaign.project_id}/compare?campaign=${campaign.id}`}
              className="link-underline text-xs text-muted hover:text-ink"
            >
              Compare systems
            </Link>
          }
        />
        <Table minWidth={900}>
          <thead>
            <tr>
              <Th>Evaluation</Th>
              <Th>System</Th>
              <Th>Evaluators</Th>
              <Th>Verdict</Th>
              <Th align="right">Pass rate</Th>
              <Th align="right">P / W / F</Th>
              <Th align="right">Duration</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((run, index) => (
              <Tr key={run.id} index={index}>
                <Td>
                  <Link href={`/runs/${run.id}`} className="link-underline text-ink">
                    {run.evaluation?.name ?? run.evaluation_id}
                  </Link>
                  <div className="mt-0.5 text-2xs text-faint">
                    {run.evaluation?.domain?.replace(/_/g, " ")} ·{" "}
                    {run.evaluation?.layer?.replace(/_/g, " ")}
                  </div>
                </Td>
                <Td className="text-xs">
                  {run.system_version?.label ?? "—"}
                  <div className="mt-0.5">
                    <Hash value={run.system_version?.config_hash} />
                  </div>
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {(run.evaluation?.evaluators ?? []).map((ev) => (
                      <span
                        key={ev}
                        className="border border-line px-1 py-px text-2xs text-faint"
                      >
                        {ev}
                      </span>
                    ))}
                  </div>
                </Td>
                <Td>
                  <Status status={run.verdict} />
                  {Object.keys(run.threshold ?? {}).length === 0 ? (
                    <div className="mt-0.5 text-2xs text-faint">no threshold set</div>
                  ) : null}
                </Td>
                <Td align="right" className="tnum">
                  {formatPercent((run.metrics as { pass_rate?: number | null })?.pass_rate)}
                </Td>
                <Td align="right" className="tnum text-xs">
                  <span className="text-pass">{run.passed}</span>
                  <span className="text-faint"> / </span>
                  <span className="text-warn">{run.warned}</span>
                  <span className="text-faint"> / </span>
                  <span className="text-fail">{run.failed}</span>
                </Td>
                <Td align="right" className="tnum text-xs text-muted">
                  {formatMs(run.duration_ms)}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  );
}
