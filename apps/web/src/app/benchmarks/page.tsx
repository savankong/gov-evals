"use client";

import { useResource } from "@/components/shell";
import { BenchmarkLeaders } from "@/components/benchmark-leaders";
import { Card, Caveat, Empty, ErrorNote, PageTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { BenchmarkSummary } from "@/lib/benchmark";

export default function BenchmarksPage() {
  const list = useResource<BenchmarkSummary[]>(() => api.get<BenchmarkSummary[]>("/benchmarks"), []);

  return (
    <div className="space-y-6">
      <PageTitle
        title="Benchmarks"
        subtitle="Question sets written for a mission, answered by the models you evaluate, and checked criterion by criterion. Each benchmark resolves to its stored results and a SHA-256."
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
          <Empty
            title="No benchmark reports yet"
            detail="Generate one from a project's Reports page over a campaign that used the per-criterion judge. It will appear here with its leaders."
          />
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {(list.data ?? []).map((b) => (
            <BenchmarkCard key={b.id} b={b} />
          ))}
        </div>
      )}

      <Caveat>
        A benchmark ranks models on one question set under stated conditions. A pass rate is not a trust
        score and does not stand for performance on any other task.
      </Caveat>
    </div>
  );
}

function BenchmarkCard({ b }: { b: BenchmarkSummary }) {
  return (
    <Card as="article" className="p-4">
      <BenchmarkLeaders b={b} />
    </Card>
  );
}
