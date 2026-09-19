"use client";

import Link from "next/link";
import { use, useState } from "react";

import { Status } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Figure,
  FilterChips,
  Spinner,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/ui";
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
  const without = data.summary.references - data.summary.with_evidence;

  return (
    <div className="space-y-4">
      <Card>
        <div className="grid grid-cols-1 divide-y divide-line sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="px-4 py-3.5">
            <Figure label="References" countTo={data.summary.references} />
          </div>
          <div className="px-4 py-3.5">
            <Figure label="With evidence" countTo={data.summary.with_evidence} />
          </div>
          {/* A reference with nothing behind it is the number that matters
              here, so it is never dimmed into the background. */}
          <div className="px-4 py-3.5">
            <Figure
              label="No evidence"
              countTo={without}
              tone={without > 0 ? "warn" : "ink"}
              note={without > 0 ? "Reports NOT EVALUATED" : undefined}
            />
          </div>
        </div>
      </Card>

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
        <CardHead title="Coverage" meta={`${rows.length} references`} />
        {rows.length === 0 ? (
          <div className="border-t border-line">
            <Empty title="No references in this framework" />
          </div>
        ) : (
          <Table minWidth={820}>
            <thead>
              <tr>
                <Th className="w-[180px]">Reference</Th>
                <Th>Topic</Th>
                <Th className="w-[140px]">Status</Th>
                <Th className="w-[320px]">Evidence</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <Tr key={`${row.framework}-${row.ref}`} index={index}>
                  <Td>
                    <div className="font-mono text-xs text-ink">{row.ref}</div>
                    <div className="mt-0.5 text-2xs uppercase tracking-wider text-faint">
                      {row.framework}
                    </div>
                  </Td>
                  <Td>
                    <span className="text-sm text-ink">{row.title}</span>
                  </Td>
                  <Td>
                    <Status status={row.status} />
                  </Td>
                  <Td>
                    {row.evidence.length === 0 ? (
                      <span className="text-xs text-muted">
                        No evaluation in this project maps to this reference.
                      </span>
                    ) : (
                      <ul className="space-y-0.5">
                        {row.evidence.map((item) => (
                          <li
                            key={item.run_id}
                            className="flex items-baseline justify-between gap-3 text-xs"
                          >
                            <Link
                              href={`/runs/${item.run_id}`}
                              className="link-underline min-w-0 truncate text-ink-soft hover:text-ink"
                            >
                              {item.evaluation_name}
                            </Link>
                            <span className="tnum shrink-0 text-faint">
                              {item.passed}/{item.executions}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}

        <div className="border-t border-line px-4 py-3">
          <Caveat>{data.note}</Caveat>
        </div>
      </Card>
    </div>
  );
}
