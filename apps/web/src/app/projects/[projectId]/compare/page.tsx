"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Status } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Hash,
  Select,
  Spinner,
  TableSkeleton,
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
  if (campaigns.error)
    return <ErrorNote message={campaigns.error} status={campaigns.status} onRetry={campaigns.reload} />;
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
      <Select
        label="Campaign"
        value={campaignId ?? ""}
        onChange={setCampaignId}
        options={(campaigns.data ?? []).map((campaign) => ({
          value: campaign.id,
          label: campaign.name,
        }))}
      />

      {comparison.error ? (
        <ErrorNote
          message={comparison.error}
          status={comparison.status}
          onRetry={comparison.reload}
        />
      ) : null}

      {comparison.loading ? (
        <Card>
          <CardHead title="Model comparison" />
          <div className="border-t border-line">
            <TableSkeleton rows={8} cols={4} />
          </div>
        </Card>
      ) : data && data.systems.length > 0 ? (
        <Card>
          <CardHead
            title="Model comparison"
            meta="Every column ran the same scenarios under the same conditions"
          />

          <div className="overflow-x-auto border-t border-line">
            <table className="w-full border-collapse text-sm" style={{ minWidth: 720 }}>
              <thead>
                <tr>
                  {/* The evaluation column stays put while the systems scroll:
                      a verdict three columns right is meaningless once its row
                      label has slid off the screen. */}
                  <th className="sticky left-0 z-10 w-[21rem] border-b border-line bg-panel px-3 py-2.5 text-left text-2xs font-normal uppercase tracking-wider text-faint">
                    Evaluation
                  </th>
                  {data.systems.map((system) => (
                    <th
                      key={system.id}
                      className="border-b border-l border-line px-3 py-2.5 text-left align-bottom font-normal"
                    >
                      <div className="text-sm text-ink">{system.label}</div>
                      <div className="mt-0.5 text-xs text-muted">
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
                    <tr key={`group-${domain}`}>
                      <td
                        colSpan={data.systems.length + 1}
                        className="sticky left-0 border-b border-line bg-sunken px-3 py-1.5 text-2xs uppercase tracking-wider text-faint"
                      >
                        {domain}
                      </td>
                    </tr>
                    {rows.map((row, index) => (
                      <tr
                        key={row.evaluation_id}
                        style={{ ["--stagger-delay" as string]: `${Math.min(index, 10) * 16}ms` }}
                        className="stagger group"
                      >
                        <td className="sticky left-0 z-10 border-b border-line bg-panel px-3 py-2.5 align-top transition-colors duration-150 group-hover:bg-sunken">
                          <div className="text-sm text-ink">{row.evaluation_name}</div>
                          {row.metric ? (
                            <div className="font-mono text-2xs text-faint">{row.metric}</div>
                          ) : null}
                        </td>
                        {row.cells.map((cell, i) => (
                          <td
                            key={i}
                            className="border-b border-l border-line px-3 py-2.5 align-top transition-colors duration-150 group-hover:bg-sunken"
                          >
                            <div className="flex flex-col items-start gap-1">
                              <Status status={cell.status} />
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
                                <span className="text-xs text-muted">
                                  {cell.note ??
                                    (cell.executions
                                      ? `${cell.executions} executed, no judgement`
                                      : "not run")}
                                </span>
                              )}
                              {cell.latency_ms ? (
                                <span className="tnum text-xs text-faint">
                                  {cell.latency_ms} ms median
                                </span>
                              ) : null}
                              {cell.run_id ? (
                                <Link
                                  href={`/runs/${cell.run_id}`}
                                  className="link-underline text-xs text-muted hover:text-ink"
                                >
                                  evidence
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
