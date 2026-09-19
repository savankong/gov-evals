"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { StatusChip } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHeader,
  Caveat,
  Empty,
  ErrorNote,
  Hash,
  Spinner,
  formatPercent,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign, Comparison, ComparisonRow } from "@/lib/types";

/**
 * Side-by-side evaluation of every system in one campaign.
 *
 * Deliberately has no "winner" column and no composite score. Weighting these
 * dimensions against mission requirements is a program decision, and different
 * missions weight them differently.
 */
export default function ComparePage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const [campaignId, setCampaignId] = useState<string | null>(null);

  const campaigns = useResource<Campaign[]>(
    () => api.get<Campaign[]>(`/projects/${projectId}/campaigns`),
    [projectId],
  );

  useEffect(() => {
    if (!campaignId && campaigns.data?.length) setCampaignId(campaigns.data[0].id);
  }, [campaigns.data, campaignId]);

  const comparison = useResource<Comparison>(
    () =>
      campaignId
        ? api.get<Comparison>(`/campaigns/${campaignId}/comparison`)
        : Promise.resolve({ campaign_id: "", systems: [], rows: [], note: "" }),
    [campaignId],
  );

  if (campaigns.loading) return <Spinner label="Loading campaigns" />;
  if (campaigns.error) return <ErrorNote message={campaigns.error} />;
  if (!campaigns.data?.length) {
    return (
      <Card>
        <Empty
          title="No campaigns to compare"
          detail="Run one campaign covering several system versions so every column faces identical conditions."
        />
      </Card>
    );
  }

  const data = comparison.data;
  const grouped = (data?.rows ?? []).reduce<Record<string, ComparisonRow[]>>((acc, row) => {
    (acc[row.domain_label] ??= []).push(row);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="campaign" className="text-xs text-muted">
          Campaign
        </label>
        <select
          id="campaign"
          value={campaignId ?? ""}
          onChange={(e) => setCampaignId(e.target.value)}
          className="rounded-md border border-line bg-raised px-2 py-1 text-sm outline-none focus:border-[rgb(var(--accent))]"
        >
          {campaigns.data.map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.name}
            </option>
          ))}
        </select>
      </div>

      {comparison.loading ? <Spinner label="Loading comparison" /> : null}
      {comparison.error ? <ErrorNote message={comparison.error} /> : null}

      {data && data.systems.length > 0 ? (
        <Card>
          <CardHeader
            title="Model comparison"
            subtitle="Every column ran the same scenarios under the same conditions"
          />

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="sticky left-0 bg-raised px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-muted">
                    Evaluation
                  </th>
                  {data.systems.map((system) => (
                    <th key={system.id} className="px-4 py-2.5 align-bottom">
                      <div className="text-sm font-semibold">{system.label}</div>
                      <div className="mt-0.5 text-[11px] font-normal text-muted">
                        {system.model ?? "model not recorded"}
                      </div>
                      <div className="mt-0.5">
                        <Hash value={system.config_hash} length={10} />
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {Object.entries(grouped).map(([domain, rows]) => (
                  <>
                    <tr key={`group-${domain}`} className="bg-[rgb(var(--unknown-bg))]">
                      <td
                        colSpan={data.systems.length + 1}
                        className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                      >
                        {domain}
                      </td>
                    </tr>
                    {rows.map((row) => (
                      <tr key={row.evaluation_id} className="border-b border-line last:border-0">
                        <td className="sticky left-0 bg-raised px-4 py-2.5">
                          <div className="text-sm">{row.evaluation_name}</div>
                          {row.metric ? (
                            <div className="text-[11px] text-muted">{row.metric}</div>
                          ) : null}
                        </td>
                        {row.cells.map((cell, i) => (
                          <td key={i} className="px-4 py-2.5 align-top">
                            <div className="flex flex-col items-start gap-1">
                              <StatusChip status={cell.status} />
                              {cell.status !== "not_evaluated" ? (
                                <span className="tnum text-xs text-muted">
                                  {formatPercent(cell.pass_rate)}
                                  {cell.executions ? ` · ${cell.executions} exec` : ""}
                                </span>
                              ) : (
                                // A cell can be unevaluated for two different
                                // reasons, and conflating them misleads: the
                                // evaluation never ran for this system, or it
                                // ran and no evaluator reached a judgement.
                                <span className="text-[11px] text-muted">
                                  {cell.note ??
                                    (cell.executions
                                      ? `${cell.executions} executed, no judgement`
                                      : "not run")}
                                </span>
                              )}
                              {cell.latency_ms ? (
                                <span className="tnum text-[11px] text-muted">
                                  {cell.latency_ms} ms median
                                </span>
                              ) : null}
                              {cell.run_id ? (
                                <Link
                                  href={`/runs/${cell.run_id}`}
                                  className="text-[11px] text-muted hover:text-ink hover:underline"
                                >
                                  evidence →
                                </Link>
                              ) : null}
                            </div>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>

          <div className="border-t border-line px-4 py-3">
            <Caveat>{data.note}</Caveat>
          </div>
        </Card>
      ) : null}

      {data && data.systems.length === 0 && !comparison.loading ? (
        <Card>
          <Empty title="This campaign evaluated no systems" />
        </Card>
      ) : null}
    </div>
  );
}
