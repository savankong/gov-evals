"use client";

import { BenchmarkLeaders } from "@/components/benchmark-leaders";
import { useResource } from "@/components/shell";
import { Card, Empty, ErrorNote, PageTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { BenchmarkSummary } from "@/lib/benchmark";

export default function PublicBenchmarksPage() {
  const list = useResource<BenchmarkSummary[]>(() => api.get<BenchmarkSummary[]>("/public/benchmarks"), []);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Benchmarks"
        subtitle="How often AI models meet the criteria written for mission questions, checked criterion by criterion, with the grading and its limits published beside every score."
      />
      {list.error ? (
        <ErrorNote message={list.error} status={list.status} onRetry={list.reload} />
      ) : list.loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      ) : (list.data ?? []).length === 0 ? (
        <Card>
          <Empty title="No published benchmarks" detail="Nothing has been published here yet." />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {(list.data ?? []).map((b) => (
            <Card key={b.id} as="article" className="p-4">
              <BenchmarkLeaders b={b} href={`/public/benchmarks/${b.id}`} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
