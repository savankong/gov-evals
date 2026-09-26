"use client";

import Link from "next/link";
import { use, useState } from "react";

import { BenchmarkReport } from "@/components/benchmark-report";
import { useAuth, useResource } from "@/components/shell";
import { Button, ErrorNote, Skeleton, formatDate } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { BenchmarkDetail } from "@/lib/benchmark";

export default function BenchmarkReportPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const detail = useResource<BenchmarkDetail>(
    () => api.get<BenchmarkDetail>(`/benchmarks/${reportId}`),
    [reportId],
  );

  if (detail.error)
    return <ErrorNote message={detail.error} status={detail.status} onRetry={detail.reload} />;
  if (detail.loading || !detail.data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-72" />
      </div>
    );

  return <BenchmarkReport b={detail.data} action={<Publication b={detail.data} onChange={detail.reload} />} />;
}

/** Whether this report is on the public pages, and the control that changes it.
 *  Only an UNCLASSIFIED report can be published; the server refuses the rest. */
function Publication({ b, onChange }: { b: BenchmarkDetail; onChange: () => void }) {
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const published = Boolean(b.published_at);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/benchmarks/${b.id}/${published ? "unpublish" : "publish"}`, {});
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change publication.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex flex-wrap items-center justify-end gap-2 text-2xs text-muted">
      {published ? (
        <>
          <span>Public since {formatDate(b.published_at)}</span>
          <Link href={`/public/benchmarks/${b.id}`} className="link-underline text-ink">
            Open public page
          </Link>
        </>
      ) : (
        <span>Private</span>
      )}
      {can("report:generate") ? (
        <Button onClick={toggle} disabled={busy} variant={published ? "secondary" : "primary"}>
          {busy ? "Saving…" : published ? "Unpublish" : "Publish"}
        </Button>
      ) : null}
      {error ? <span className="basis-full text-right text-fail">{error}</span> : null}
    </span>
  );
}
