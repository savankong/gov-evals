"use client";

import Link from "next/link";

import { Bar, Tag, formatDate } from "@/components/ui";
import { type BenchmarkSummary, pct } from "@/lib/benchmark";

/** One benchmark's leaders as a ranked list: rank, model, a proportion bar and
 *  the pass rate, with the link to the full report beside the title. The list
 *  shape follows the "top models" leaderboards of model gateways; the bar is
 *  the product's own 2px annotation, so the number stays the reading. */
export function BenchmarkLeaders({ b, compact = false }: { b: BenchmarkSummary; compact?: boolean }) {
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            {b.demonstration ? <Tag tone="warn">Demonstration</Tag> : null}
            {b.required_expertise.map((d) => (
              <Tag key={d}>{d}</Tag>
            ))}
          </div>
          <h3 className="mt-2 truncate text-base text-ink">{b.project.name}</h3>
          <p className="tnum mt-0.5 text-2xs text-muted">
            {formatDate(b.created_at)} · {b.models} models · {b.questions} questions · {b.criteria} criteria
          </p>
        </div>
        <Link href={`/benchmarks/${b.id}`} className="link-underline shrink-0 text-xs text-ink">
          View report
        </Link>
      </div>
      {!compact && b.project.description ? (
        <p className="line-clamp-2 text-sm text-ink-soft">{b.project.description}</p>
      ) : null}
      <ol className="mt-auto divide-y divide-line border-t border-line">
        {b.top.map((t, i) => (
          <li key={`${t.model}-${t.condition}`} className="grid grid-cols-[1.5rem_1fr_4.5rem] items-center gap-3 py-2">
            <span className="tnum font-mono text-2xs text-faint">{i + 1}</span>
            <div className="min-w-0">
              <div className="truncate text-sm text-ink">
                {t.model}
                {b.conditions.length > 1 ? <span className="text-2xs text-muted"> · {t.condition}</span> : null}
              </div>
              <Bar value={t.pass_rate ?? 0} tone={i === 0 ? "ink" : "muted"} className="mt-1.5" />
            </div>
            <span className="tnum text-right font-mono text-sm text-ink">{pct(t.pass_rate)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
