"use client";

import { use, useState } from "react";

import { SlideOver, useAuth, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  CodeBlock,
  Empty,
  ErrorNote,
  Hash,
  Key,
  Spinner,
  Table,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

interface Report {
  id: string;
  kind: string;
  title: string;
  format: string;
  body: string;
  sha256: string;
  classification: string;
  generated_by: string | null;
  created_at: string;
}

const KINDS = [
  { key: "executive_summary", label: "Executive summary", needs: "campaign" },
  { key: "findings", label: "Findings report", needs: null },
  { key: "comparison", label: "Model comparison", needs: "campaign" },
  { key: "benchmark", label: "Benchmark report", needs: "campaigns" },
];

export default function ReportsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { can } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Report | null>(null);
  // A benchmark report spans campaigns (the scored run and the calibration
  // run), so it is generated over the ones picked here rather than the latest.
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);

  const reports = useResource<Report[]>(
    () => api.get<Report[]>(`/projects/${projectId}/reports`),
    [projectId],
  );
  const campaigns = useResource<Campaign[]>(
    () => api.get<Campaign[]>(`/projects/${projectId}/campaigns`),
    [projectId],
  );

  async function generate(kind: string, needs: string | null) {
    setBusy(kind);
    setActionError(null);
    try {
      const campaignId = campaigns.data?.[0]?.id;
      if (needs === "campaign" && !campaignId) {
        throw new ApiError("Run a campaign before generating this report.", 400);
      }
      if (needs === "campaigns" && picked.length === 0) {
        throw new ApiError("Pick at least one campaign for the benchmark report.", 400);
      }
      const report = await api.post<Report>(`/projects/${projectId}/reports`, {
        kind,
        campaign_id: needs === "campaign" ? campaignId : undefined,
        campaign_ids: needs === "campaigns" ? picked : undefined,
      });
      if (needs === "campaigns") setPicking(false);
      setPreview(report);
      reports.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not generate the report.");
    } finally {
      setBusy(null);
    }
  }

  if (reports.loading) return <Spinner label="Loading reports" />;
  if (reports.error)
    return <ErrorNote message={reports.error} status={reports.status} onRetry={reports.reload} />;

  const rows = reports.data ?? [];

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      {can("report:generate") ? (
        <div className="flex flex-wrap gap-2">
          {KINDS.map((kind) => (
            <Button
              key={kind.key}
              onClick={() =>
                kind.needs === "campaigns" ? setPicking(!picking) : generate(kind.key, kind.needs)
              }
              disabled={busy !== null}
            >
              {busy === kind.key ? "Generating…" : kind.label}
            </Button>
          ))}
        </div>
      ) : null}

      {picking ? (
        <Card>
          <CardHead
            title="Benchmark report"
            meta="Pick the campaigns to report on: the scored run and, if there is one, its judge calibration run"
          />
          <div className="space-y-2 border-t border-line p-4">
            {campaigns.error ? (
              <ErrorNote message={campaigns.error} status={campaigns.status} onRetry={campaigns.reload} />
            ) : campaigns.loading ? (
              <Spinner label="Loading campaigns" />
            ) : (campaigns.data ?? []).length === 0 ? (
              <p className="text-sm text-muted">This project has no campaigns yet.</p>
            ) : (
              (campaigns.data ?? []).map((campaign) => (
                <label key={campaign.id} className="flex items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={picked.includes(campaign.id)}
                    onChange={(e) =>
                      setPicked(
                        e.target.checked
                          ? [...picked, campaign.id]
                          : picked.filter((id) => id !== campaign.id),
                      )
                    }
                  />
                  {campaign.name}
                  <span className="text-2xs uppercase tracking-wider text-faint">
                    {campaign.trigger} · {formatDate(campaign.created_at)}
                  </span>
                </label>
              ))
            )}
            <div className="pt-2">
              <Button
                onClick={() => generate("benchmark", "campaigns")}
                disabled={busy !== null || picked.length === 0}
              >
                {busy === "benchmark" ? "Generating…" : `Generate over ${picked.length} campaign(s)`}
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHead
          title="Generated artifacts"
          meta="Each report is assembled from stored records and carries its own digest"
        />
        {rows.length === 0 ? (
          <div className="border-t border-line">
            <Empty
              title="No reports yet"
              detail="Every report is assembled from stored records and carries a digest so it can be tied back to the evidence it came from."
            />
          </div>
        ) : (
          <Table minWidth={720}>
            <thead>
              <tr>
                <Th>Report</Th>
                <Th className="w-[9rem]">Marking</Th>
                <Th className="w-[12rem]">Generated</Th>
                <Th className="w-[10.5rem]">By</Th>
                <Th className="w-[9.75rem]">Digest</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((report, index) => (
                <Tr key={report.id} index={index} onClick={() => setPreview(report)}>
                  <Td>
                    <div className="text-sm text-ink">{report.title}</div>
                    <div className="mt-0.5 text-2xs uppercase tracking-wider text-faint">
                      {report.kind.replace(/_/g, " ")} · {report.format}
                    </div>
                  </Td>
                  <Td>
                    <Tag>{report.classification}</Tag>
                  </Td>
                  <Td>
                    <span className="tnum text-xs text-muted">
                      {formatDate(report.created_at)}
                    </span>
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">{report.generated_by ?? "—"}</span>
                  </Td>
                  <Td>
                    <Hash value={report.sha256} length={12} />
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <SlideOver
        open={preview !== null}
        onClose={() => setPreview(null)}
        label={preview?.title ?? "Report"}
        footer={
          <div className="flex items-center justify-between gap-3">
            <span className="text-2xs text-faint">
              <Key>Esc</Key> to close
            </span>
            {preview ? (
              <span className="text-2xs text-faint">
                {/* The digest is the point: a report that cannot be tied back
                    to the records it was built from is a document, not
                    evidence. */}
                SHA-256 <Hash value={preview.sha256} length={24} />
              </span>
            ) : null}
          </div>
        }
      >
        {preview ? (
          <div className="space-y-3 p-4">
            <div>
              <h2 className="text-lg text-ink">{preview.title}</h2>
              <p className="mt-0.5 text-xs text-muted">
                {formatDate(preview.created_at)} · {preview.generated_by ?? "—"} ·{" "}
                {preview.classification}
              </p>
            </div>
            <CodeBlock className="max-h-[calc(100vh-220px)] overflow-auto">
              {preview.body}
            </CodeBlock>
          </div>
        ) : null}
      </SlideOver>
    </div>
  );
}
