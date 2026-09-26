"use client";

import Link from "next/link";

import { useResource } from "@/components/shell";
import { Bar, Card, Caveat, Empty, ErrorNote, PageTitle, Skeleton, Tag, formatDate } from "@/components/ui";
import { api } from "@/lib/api";
import { type BenchmarkSummary, pct } from "@/lib/benchmark";

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
    <Card as="article" className="flex flex-col">
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-1.5">
          {b.demonstration ? <Tag tone="warn">Demonstration</Tag> : null}
          {b.required_expertise.map((d) => (
            <Tag key={d}>{d}</Tag>
          ))}
          <Tag mono>{b.classification}</Tag>
        </div>
        <div>
          <h2 className="text-lg text-ink">{b.project.name}</h2>
          <p className="mt-0.5 text-2xs text-muted">
            Updated {formatDate(b.created_at)} · {b.models} models · {b.questions} questions ·{" "}
            {b.criteria} criteria
          </p>
        </div>
        {b.project.description ? (
          <p className="line-clamp-3 text-sm text-ink-soft">{b.project.description}</p>
        ) : null}
        <ol className="mt-auto space-y-2 pt-1">
          {b.top.map((t, i) => (
            <li key={`${t.model}-${t.condition}`} className="grid grid-cols-[1.25rem_1fr_4rem] items-center gap-2">
              <span className="tnum font-mono text-2xs text-faint">{i + 1}</span>
              <div className="min-w-0">
                <div className="truncate text-sm text-ink">
                  {t.model}
                  {b.conditions.length > 1 ? (
                    <span className="text-2xs text-muted"> · {t.condition}</span>
                  ) : null}
                </div>
                <Bar value={t.pass_rate ?? 0} tone={i === 0 ? "ink" : "muted"} className="mt-1" />
              </div>
              <span className="tnum text-right font-mono text-sm text-ink">{pct(t.pass_rate)}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="border-t border-line px-4 py-2.5">
        <Link href={`/benchmarks/${b.id}`} className="link-underline text-sm text-ink">
          View details
        </Link>
      </div>
    </Card>
  );
}
