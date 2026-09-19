"use client";

import Link from "next/link";
import { use, useState } from "react";

import { StatusChip } from "@/components/status";
import { useResource } from "@/components/shell";
import { Card, CardHeader, Caveat, ErrorNote, FilterChips, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { FrameworkCoverageRow } from "@/lib/types";

interface Coverage {
  rows: FrameworkCoverageRow[];
  summary: { references: number; with_evidence: number };
  note: string;
}

export default function FrameworksPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const [framework, setFramework] = useState<string | null>(null);

  const { data, error, loading } = useResource<Coverage>(
    () => api.get<Coverage>(`/projects/${projectId}/framework-coverage`),
    [projectId],
  );

  if (loading) return <Spinner label="Loading framework coverage" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const frameworks = Array.from(new Set(data.rows.map((r) => r.framework)));
  const rows = data.rows.filter((r) => !framework || r.framework === framework);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3">
        <div className="bg-raised px-4 py-3">
          <div className="text-[11px] uppercase tracking-wider text-muted">References</div>
          <div className="tnum mt-1 text-xl font-semibold">{data.summary.references}</div>
        </div>
        <div className="bg-raised px-4 py-3">
          <div className="text-[11px] uppercase tracking-wider text-muted">With evidence</div>
          <div className="tnum mt-1 text-xl font-semibold">{data.summary.with_evidence}</div>
        </div>
        <div className="bg-raised px-4 py-3">
          <div className="text-[11px] uppercase tracking-wider text-muted">No evidence</div>
          <div className="tnum mt-1 text-xl font-semibold text-muted">
            {data.summary.references - data.summary.with_evidence}
          </div>
        </div>
      </div>

      <FilterChips
        options={frameworks.map((f) => ({
          key: f,
          label: f,
          count: data.rows.filter((r) => r.framework === f).length,
        }))}
        active={framework}
        onChange={setFramework}
        allLabel="All frameworks"
      />

      <Card>
        <CardHeader title="Coverage" subtitle={`${rows.length} references`} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-4 py-2 font-medium">Reference</th>
                <th className="px-4 py-2 font-medium">Topic</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.framework}-${row.ref}`} className="border-b border-line last:border-0">
                  <td className="px-4 py-2.5">
                    <code className="font-mono text-xs">{row.ref}</code>
                    <div className="mt-0.5 text-[11px] text-muted">{row.framework}</div>
                  </td>
                  <td className="px-4 py-2.5 text-sm">{row.title}</td>
                  <td className="px-4 py-2.5">
                    <StatusChip status={row.status} />
                  </td>
                  <td className="px-4 py-2.5">
                    {row.evidence.length === 0 ? (
                      <span className="text-xs text-muted">
                        No evaluation in this project maps to this reference.
                      </span>
                    ) : (
                      <ul className="space-y-0.5">
                        {row.evidence.map((item) => (
                          <li key={item.run_id} className="text-xs">
                            <Link href={`/runs/${item.run_id}`} className="hover:underline">
                              {item.evaluation_name}
                            </Link>
                            <span className="tnum ml-2 text-muted">
                              {item.passed}/{item.executions} passed
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="border-t border-line px-4 py-3">
          <Caveat>{data.note}</Caveat>
        </div>
      </Card>
    </div>
  );
}
