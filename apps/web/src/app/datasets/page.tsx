"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useResource } from "@/components/shell";
import {
  Caveat,
  Card,
  Empty,
  ErrorNote,
  PageTitle,
  Table,
  TableSkeleton,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { api } from "@/lib/api";

interface DatasetRow {
  id: string;
  name: string;
  description: string | null;
  project_id: string;
  project_name: string | null;
  modality: string;
  split: string;
  classification: string;
  contains_pii: boolean;
  tags: string[];
  required_expertise: string[];
  owner: string | null;
  example_count: number;
  version_count: number;
  current_version: string | null;
  run_count: number;
  updated_at: string;
}

interface Discipline {
  key: string;
  label: string;
}

export default function DatasetsPage() {
  const [query, setQuery] = useState("");
  const datasets = useResource<DatasetRow[]>(() => api.get("/datasets"));
  const disciplines = useResource<{ disciplines: Discipline[] }>(() => api.get("/disciplines"));

  const labelFor = useMemo(() => {
    const map = new Map((disciplines.data?.disciplines ?? []).map((d) => [d.key, d.label]));
    return (key: string) => map.get(key) ?? key.replace(/_/g, " ");
  }, [disciplines.data]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return datasets.data ?? [];
    return (datasets.data ?? []).filter(
      (d) =>
        d.name.toLowerCase().includes(needle) ||
        (d.project_name ?? "").toLowerCase().includes(needle) ||
        d.required_expertise.some((e) => labelFor(e).toLowerCase().includes(needle)),
    );
  }, [datasets.data, query, labelFor]);

  const undeclared = (datasets.data ?? []).filter((d) => d.required_expertise.length === 0).length;

  return (
    <div className="space-y-4">
      <PageTitle
        title="Datasets"
        subtitle="The cases a system is tested against, and who is qualified to judge the answers."
      />

      {datasets.error ? <ErrorNote message={datasets.error} /> : null}

      {datasets.loading ? (
        <Card>
          <TableSkeleton rows={5} cols={6} />
        </Card>
      ) : (datasets.data ?? []).length === 0 ? (
        <Card>
          <Empty
            title="No datasets yet"
            detail="A dataset is the set of cases a system is put through. Upload one against a project — JSONL, JSON, CSV or plain text — and the platform reports what it found in the file before anything runs against it: empty inputs, duplicates, and whether any row carries an expected answer at all."
          />
        </Card>
      ) : (
        <>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name, project or expertise…"
            aria-label="Search datasets"
            className="h-7 w-full max-w-xs border border-line bg-panel px-2.5 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-faint focus:border-line-strong"
          />

          <Card>
            <Table minWidth={860}>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th align="right">Examples</Th>
                  <Th align="right">Runs</Th>
                  <Th>Required expertise</Th>
                  <Th>Project</Th>
                  <Th>Owner</Th>
                  <Th>Updated</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((dataset, index) => (
                  <Tr key={dataset.id} index={index}>
                    <Td>
                      <Link
                        href={`/datasets/${dataset.id}`}
                        className="text-ink underline-offset-2 hover:underline"
                      >
                        {dataset.name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1">
                        {dataset.current_version ? (
                          <Tag mono>{dataset.current_version}</Tag>
                        ) : null}
                        {dataset.contains_pii ? <Tag tone="warn">PII</Tag> : null}
                        {dataset.tags.slice(0, 3).map((tag) => (
                          <Tag key={tag}>{tag}</Tag>
                        ))}
                      </div>
                    </Td>
                    <Td align="right" className="tnum">
                      {dataset.example_count || "—"}
                    </Td>
                    <Td align="right" className="tnum">
                      {dataset.run_count || "—"}
                    </Td>
                    <Td>
                      {dataset.required_expertise.length ? (
                        <div className="flex flex-wrap gap-1">
                          {dataset.required_expertise.map((key) => (
                            <Tag key={key} tone="strong">
                              {labelFor(key)}
                            </Tag>
                          ))}
                        </div>
                      ) : (
                        <span
                          className="text-xs text-faint"
                          title="No discipline is declared, so no reviewer can be checked against one."
                        >
                          Not declared
                        </span>
                      )}
                    </Td>
                    <Td className="text-muted">{dataset.project_name ?? "—"}</Td>
                    <Td className="text-muted">{dataset.owner ?? "—"}</Td>
                    <Td className="text-muted">{formatDate(dataset.updated_at)}</Td>
                  </Tr>
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <Td colSpan={7}>
                      <p className="py-6 text-center text-sm text-muted">
                        No dataset matches that search.
                      </p>
                    </Td>
                  </tr>
                ) : null}
              </tbody>
            </Table>
          </Card>

          {undeclared ? (
            <Caveat>
              {undeclared} dataset{undeclared === 1 ? "" : "s"} declare no required expertise.
              Reviews of their results are recorded, but nothing can be checked against a
              requirement that does not exist — the review will say it was not checked rather
              than implying the reviewer was vetted for it.
            </Caveat>
          ) : null}
        </>
      )}
    </div>
  );
}
