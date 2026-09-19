"use client";

import { use, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import { Button, Card, CardHeader, Empty, ErrorNote, Hash, Spinner, formatDate } from "@/components/ui";
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
];

export default function ReportsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { can } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Report | null>(null);

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
      const report = await api.post<Report>(`/projects/${projectId}/reports`, {
        kind,
        campaign_id: needs === "campaign" ? campaignId : undefined,
      });
      setPreview(report);
      reports.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not generate the report.");
    } finally {
      setBusy(null);
    }
  }

  if (reports.loading) return <Spinner label="Loading reports" />;
  if (reports.error) return <ErrorNote message={reports.error} />;

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      {can("report:generate") ? (
        <div className="flex flex-wrap gap-2">
          {KINDS.map((kind) => (
            <Button
              key={kind.key}
              size="sm"
              onClick={() => generate(kind.key, kind.needs)}
              disabled={busy !== null}
            >
              {busy === kind.key ? "Generating…" : kind.label}
            </Button>
          ))}
        </div>
      ) : null}

      <Card>
        <CardHeader title="Generated artifacts" subtitle={`${(reports.data ?? []).length} reports`} />
        {(reports.data ?? []).length === 0 ? (
          <Empty
            title="No reports yet"
            detail="Every report is assembled from stored records and carries a digest so it can be tied back to the evidence it came from."
          />
        ) : (
          <div className="divide-y divide-line">
            {(reports.data ?? []).map((report) => (
              <button
                key={report.id}
                onClick={() => setPreview(report)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[rgb(var(--unknown-bg))]"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{report.title}</div>
                  <div className="mt-0.5 text-[11px] text-muted">
                    {formatDate(report.created_at)} · {report.generated_by ?? "—"} ·{" "}
                    {report.classification}
                  </div>
                </div>
                <Hash value={report.sha256} />
              </button>
            ))}
          </div>
        )}
      </Card>

      {preview ? (
        <Card>
          <CardHeader
            title={preview.title}
            subtitle={`SHA-256 ${preview.sha256.slice(0, 32)}…`}
            action={
              <Button size="sm" onClick={() => setPreview(null)}>
                Close
              </Button>
            }
          />
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap px-4 py-3 text-xs leading-relaxed">
            {preview.body}
          </pre>
        </Card>
      ) : null}
    </div>
  );
}
