"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  Caveat,
  Crumbs,
  Empty,
  ErrorNote,
  Hash,
  PageTitle,
  Spinner,
  Table,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface Dataset {
  id: string;
  name: string;
  description: string | null;
  project_id: string;
  modality: string;
  split: string;
  contains_pii: boolean;
  tags: string[];
  required_expertise: string[];
  classification: string;
  created_at: string;
}
interface DatasetVersion {
  id: string;
  version: string;
  item_count: number;
  source_format: string;
  content_hash: string;
  generated: boolean;
  is_current: boolean;
  quality_report: {
    items?: number;
    fields?: string[];
    empty_inputs?: number;
    duplicates?: number;
    rows_with_expected_answer?: number;
    issues?: string[];
  };
}
interface Detail {
  dataset: Dataset;
  project: { id: string; name: string } | null;
  versions: DatasetVersion[];
  current_version_id: string | null;
}
interface Item {
  id: string;
  ordinal: number;
  payload: Record<string, unknown>;
  content_hash: string;
}
interface Discipline {
  key: string;
  label: string;
}

/**
 * Which disciplines these cases need.
 *
 * The suggested vocabulary is offered, and anything else can be typed: a
 * program that needs a "targeteer" must be able to say so without waiting on
 * us to add the word.
 */
function ExpertiseEditor({
  dataset,
  disciplines,
  onSaved,
}: {
  dataset: Dataset;
  disciplines: Discipline[];
  onSaved: () => void;
}) {
  const [selected, setSelected] = useState<string[]>(dataset.required_expertise);
  const [custom, setCustom] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setSelected(dataset.required_expertise), [dataset.required_expertise]);

  const dirty = useMemo(
    () =>
      selected.slice().sort().join("|") !==
      dataset.required_expertise.slice().sort().join("|"),
    [selected, dataset.required_expertise],
  );

  const options = useMemo(() => {
    const keys = new Set(disciplines.map((d) => d.key));
    const extra = selected.filter((s) => !keys.has(s)).map((s) => ({ key: s, label: s }));
    return [...disciplines, ...extra];
  }, [disciplines, selected]);

  const toggle = (key: string) =>
    setSelected((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    );

  const addCustom = () => {
    const slug = custom.trim().toLowerCase().replace(/\s+/g, "_");
    if (!slug) return;
    setSelected((current) => (current.includes(slug) ? current : [...current, slug]));
    setCustom("");
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.patch(`/datasets/${dataset.id}`, { required_expertise: selected });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHead
        title="Required expertise"
        subtitle="Who is qualified to judge these cases. A review from outside these disciplines is recorded, and does not count towards an evaluation that requires expertise."
        action={
          dirty ? (
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          ) : null
        }
      />
      <div className="space-y-3 border-t border-line px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => {
            const on = selected.includes(option.key);
            return (
              <button
                key={option.key}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(option.key)}
                className={`h-7 shrink-0 whitespace-nowrap border px-2.5 text-sm transition-colors duration-150 ease-out ${
                  on
                    ? "border-line-strong bg-sunken text-ink"
                    : "border-line text-muted hover:border-line-strong hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-2">
          <input
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addCustom();
              }
            }}
            placeholder="Add another discipline…"
            aria-label="Add a discipline not on the list"
            className="h-7 w-56 border border-line bg-panel px-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-line-strong"
          />
          <Button onClick={addCustom} disabled={!custom.trim()}>
            Add
          </Button>
        </div>

        {error ? <ErrorNote message={error} /> : null}

        {selected.length === 0 ? (
          <Caveat>
            Nothing declared. Reviews of results from this dataset will record that no
            expertise requirement was checked, rather than implying the reviewer was
            qualified for it.
          </Caveat>
        ) : null}
      </div>
    </Card>
  );
}

export default function DatasetDetailPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}) {
  const { datasetId } = use(params);
  const detail = useResource<Detail>(() => api.get(`/datasets/${datasetId}`), [datasetId]);
  const disciplines = useResource<{ disciplines: Discipline[] }>(() => api.get("/disciplines"));

  const [versionId, setVersionId] = useState<string | null>(null);
  const activeVersion = versionId ?? detail.data?.current_version_id ?? null;

  const items = useResource<{ items: Item[] }>(
    () =>
      activeVersion
        ? api.get(`/dataset-versions/${activeVersion}/items?limit=50`)
        : Promise.resolve({ items: [] }),
    [activeVersion],
  );

  useDeclaredClassification(detail.data?.dataset.classification);

  // Columns are whatever the rows actually carry: a dataset is not required to
  // use our field names, and showing "input" for a file that says "prompt"
  // would be inventing structure the file does not have.
  const columns = useMemo(() => {
    const keys = new Set<string>();
    for (const item of items.data?.items ?? []) {
      for (const key of Object.keys(item.payload ?? {})) keys.add(key);
    }
    return Array.from(keys).slice(0, 6);
  }, [items.data]);

  if (detail.loading) return <Spinner label="Loading dataset" />;
  if (detail.error) return <ErrorNote message={detail.error} />;
  if (!detail.data) return null;

  const { dataset, project, versions } = detail.data;
  const version = versions.find((v) => v.id === activeVersion) ?? null;
  const report = version?.quality_report ?? {};

  return (
    <div className="space-y-4">
      <Crumbs
        items={[
          { label: "Datasets", href: "/datasets" },
          ...(project ? [{ label: project.name, href: `/projects/${project.id}` }] : []),
          { label: dataset.name },
        ]}
      />

      <PageTitle
        title={dataset.name}
        subtitle={dataset.description ?? undefined}
        action={
          <div className="flex items-center gap-1.5">
            <Tag mono>{dataset.modality}</Tag>
            <Tag>{dataset.split}</Tag>
            {dataset.contains_pii ? <Tag tone="warn">PII</Tag> : null}
          </div>
        }
      />

      <ExpertiseEditor
        dataset={dataset}
        disciplines={disciplines.data?.disciplines ?? []}
        onSaved={detail.reload}
      />

      <Card>
        <CardHead
          title="Versions"
          subtitle="Every upload is kept. A result always names the version it ran against."
        />
        {versions.length === 0 ? (
          <Empty
            title="No data uploaded yet"
            detail="Upload a JSONL, JSON, CSV or plain-text file against this dataset. The platform reports what it found in the file before anything runs against it."
          />
        ) : (
          <Table minWidth={620}>
            <thead>
              <tr>
                <Th>Version</Th>
                <Th align="right">Items</Th>
                <Th>Format</Th>
                <Th>Content hash</Th>
                <Th>State</Th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v, index) => (
                <Tr key={v.id} index={index} onClick={() => setVersionId(v.id)}>
                  <Td>
                    <span className={v.id === activeVersion ? "text-ink" : "text-muted"}>
                      {v.version}
                    </span>
                  </Td>
                  <Td align="right" className="tnum">
                    {v.item_count}
                  </Td>
                  <Td className="text-muted">{v.source_format}</Td>
                  <Td>
                    <Hash value={v.content_hash} />
                  </Td>
                  <Td>
                    <div className="flex gap-1">
                      {v.is_current ? <Tag tone="strong">Current</Tag> : null}
                      {v.generated ? <Tag>Generated</Tag> : null}
                    </div>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {version ? (
        <Card>
          <CardHead
            title={`Quality report — ${version.version}`}
            subtitle="Computed at upload, so a problem with the file is known before a campaign spends a budget on it."
          />
          <div className="grid gap-px border-t border-line bg-line sm:grid-cols-4">
            {[
              ["Items", report.items ?? version.item_count],
              ["Empty inputs", report.empty_inputs ?? 0],
              ["Duplicates", report.duplicates ?? 0],
              ["With expected answer", report.rows_with_expected_answer ?? 0],
            ].map(([label, value]) => (
              <div key={String(label)} className="bg-panel px-4 py-3">
                <div className="text-2xs uppercase tracking-wider text-faint">{label}</div>
                <div className="tnum mt-0.5 text-lg text-ink">{String(value)}</div>
              </div>
            ))}
          </div>
          {(report.issues ?? []).length ? (
            <div className="space-y-1.5 border-t border-line px-4 py-3">
              {(report.issues ?? []).map((issue) => (
                <p key={issue} className="text-xs leading-relaxed text-muted">
                  {issue}
                </p>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <CardHead
          title="Examples"
          subtitle={
            version ? `First 50 rows of ${version.version}.` : "Select a version to see its rows."
          }
        />
        {items.loading ? (
          <Spinner label="Loading examples" />
        ) : (items.data?.items ?? []).length === 0 ? (
          <Empty title="No rows to show" />
        ) : (
          <Table minWidth={720}>
            <thead>
              <tr>
                <Th align="right">#</Th>
                {columns.map((column) => (
                  <Th key={column}>{column}</Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(items.data?.items ?? []).map((item, index) => (
                <Tr key={item.id} index={index}>
                  <Td align="right" className="tnum text-faint">
                    {item.ordinal + 1}
                  </Td>
                  {columns.map((column) => {
                    const value = item.payload?.[column];
                    const text =
                      value === undefined || value === null
                        ? "—"
                        : typeof value === "string"
                          ? value
                          : JSON.stringify(value);
                    return (
                      <Td key={column} className="max-w-[24rem]">
                        <span className="line-clamp-3 text-muted">{text}</span>
                      </Td>
                    );
                  })}
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Caveat>
        A dataset is evidence about the cases it contains and nothing else. Passing every row
        here does not establish that the system handles cases nobody wrote down — see the
        mission profile for what this dataset was meant to cover.{" "}
        {project ? (
          <Link href={`/projects/${project.id}`} className="underline underline-offset-2">
            {project.name}
          </Link>
        ) : null}
      </Caveat>
    </div>
  );
}
