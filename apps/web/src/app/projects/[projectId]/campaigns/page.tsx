"use client";

import { useRouter } from "next/navigation";
import { use } from "react";

import { useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Empty,
  ErrorNote,
  SplitBar,
  Table,
  TableSkeleton,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

export default function CampaignsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const router = useRouter();
  const { data, error, loading } = useResource<Campaign[]>(
    () => api.get<Campaign[]>(`/projects/${projectId}/campaigns`),
    [projectId],
  );

  if (error) return <ErrorNote message={error} />;

  const campaigns = data ?? [];

  if (!loading && campaigns.length === 0) {
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
      <CardHead
        title="Campaigns"
        meta={loading ? undefined : `${campaigns.length} recorded`}
      />
      {loading ? (
        <div className="border-t border-line">
          <TableSkeleton rows={6} cols={5} />
        </div>
      ) : (
        <Table minWidth={900}>
          <thead>
            <tr>
              <Th>Campaign</Th>
              <Th className="w-[110px]">Trigger</Th>
              <Th className="w-[96px]">Status</Th>
              <Th className="w-[130px]">Outcome</Th>
              <Th className="w-[80px]" align="right">
                Exec
              </Th>
              <Th className="w-[80px]" align="right">
                Passed
              </Th>
              <Th className="w-[80px]" align="right">
                Failed
              </Th>
              <Th className="w-[90px]" align="right">
                Awaiting
              </Th>
              <Th className="w-[130px]">Completed</Th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((campaign, index) => {
              const summary = campaign.summary ?? {};
              const passed = summary.passed ?? 0;
              const failed = summary.failed ?? 0;
              const awaiting = summary.pending_human ?? 0;
              return (
                <Tr
                  key={campaign.id}
                  index={index}
                  onClick={() => router.push(`/campaigns/${campaign.id}`)}
                >
                  <Td>
                    <span className="text-sm text-ink">{campaign.name}</span>
                    {campaign.kind !== "evaluation" ? (
                      <span className="ml-2 align-middle">
                        <Tag>{campaign.kind}</Tag>
                      </span>
                    ) : null}
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">{campaign.trigger}</span>
                  </Td>
                  <Td>
                    <span className="text-2xs uppercase tracking-wider text-muted">
                      {campaign.status}
                    </span>
                  </Td>
                  <Td>
                    {/* The three-way split, not a percentage: a campaign that
                        is 80% passed and 20% awaiting review has decided
                        nothing about that 20%. */}
                    <div className="pt-2">
                      <SplitBar
                        parts={[
                          { value: passed, tone: "pass" },
                          { value: awaiting, tone: "warn" },
                          { value: failed, tone: "fail" },
                        ]}
                      />
                    </div>
                  </Td>
                  <Td align="right">
                    <span className="tnum text-sm text-ink">{summary.executed ?? "—"}</span>
                  </Td>
                  <Td align="right">
                    <span className="tnum text-sm text-pass">{summary.passed ?? "—"}</span>
                  </Td>
                  <Td align="right">
                    <span className={`tnum text-sm ${failed ? "text-fail" : "text-faint"}`}>
                      {failed}
                    </span>
                  </Td>
                  <Td align="right">
                    <span className={`tnum text-sm ${awaiting ? "text-pending" : "text-faint"}`}>
                      {awaiting}
                    </span>
                  </Td>
                  <Td>
                    <span className="tnum text-xs text-muted">
                      {formatDate(campaign.completed_at)}
                    </span>
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
