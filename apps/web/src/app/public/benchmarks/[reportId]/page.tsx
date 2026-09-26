"use client";

import { use } from "react";

import { BenchmarkReport } from "@/components/benchmark-report";
import { useResource } from "@/components/shell";
import { ErrorNote, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { BenchmarkDetail } from "@/lib/benchmark";

export default function PublicBenchmarkPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const detail = useResource<BenchmarkDetail>(
    () => api.get<BenchmarkDetail>(`/public/benchmarks/${reportId}`),
    [reportId],
  );

  if (detail.error)
    return (
      <ErrorNote
        message={detail.status === 404 ? "This benchmark is not published, or no longer is." : detail.error}
        status={detail.status}
        onRetry={detail.reload}
      />
    );
  if (detail.loading || !detail.data)
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-72" />
      </div>
    );

  return <BenchmarkReport b={detail.data} publicView />;
}
