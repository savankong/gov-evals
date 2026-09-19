"use client";

import Link from "next/link";
import { use } from "react";

import { StatusChip } from "@/components/status";
import { useResource } from "@/components/shell";
import { Card, Empty, ErrorNote, Spinner, formatDate } from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function CampaignsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { data, error, loading } = useResource<Campaign[]>(
    () => api.get<Campaign[]>(`/projects/${projectId}/campaigns`),
    [projectId],
  );

  if (loading) return <Spinner label="Loading campaigns" />;
  if (error) return <ErrorNote message={error} />;

  const campaigns = data ?? [];
  if (campaigns.length === 0) {
    return (
      <Card>
        <Empty
          title="No campaigns yet"
          detail="A campaign executes a set of evaluations against one or more system versions under identical conditions."
        />
      </Card>
    );
  }

  return (
    <Card>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
            <th className="px-4 py-2 font-medium">Campaign</th>
            <th className="px-4 py-2 font-medium">Trigger</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 text-right font-medium">Executions</th>
            <th className="px-4 py-2 text-right font-medium">Passed</th>
            <th className="px-4 py-2 text-right font-medium">Failed</th>
            <th className="px-4 py-2 text-right font-medium">Awaiting</th>
            <th className="px-4 py-2 font-medium">Completed</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((campaign) => {
            const summary = campaign.summary ?? {};
            return (
              <tr
                key={campaign.id}
                className="border-b border-line last:border-0 hover:bg-[rgb(var(--unknown-bg))]"
              >
                <td className="px-4 py-2.5">
                  <Link href={`/campaigns/${campaign.id}`} className="font-medium hover:underline">
                    {campaign.name}
                  </Link>
                  {campaign.kind !== "evaluation" ? (
                    <span className="ml-2 rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] text-muted">
                      {campaign.kind}
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-2.5 text-xs text-muted">{campaign.trigger}</td>
                <td className="px-4 py-2.5 text-xs">{campaign.status}</td>
                <td className="tnum px-4 py-2.5 text-right">{summary.executed ?? "—"}</td>
                <td className="tnum px-4 py-2.5 text-right text-[rgb(var(--pass))]">
                  {summary.passed ?? "—"}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {summary.failed ? (
                    <span className="text-[rgb(var(--fail))]">{summary.failed}</span>
                  ) : (
                    <span className="text-muted">0</span>
                  )}
                </td>
                <td className="tnum px-4 py-2.5 text-right">
                  {summary.pending_human ? (
                    <span className="text-[rgb(var(--pending))]">{summary.pending_human}</span>
                  ) : (
                    <span className="text-muted">0</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs text-muted">
                  {formatDate(campaign.completed_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
