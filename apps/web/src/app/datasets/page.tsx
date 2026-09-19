"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SlideOver, useAuth, useResource } from "@/components/shell";
import {
  Button,
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
import { ApiError, api } from "@/lib/api";

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

interface Project {
  id: string;
  name: string;
  classification: string;
}

interface Vocabularies {
  classification_policy: {
    max_classification: string | null;
    permitted: string[];
    note: string;
  };
}

/**
 * Create a dataset.
 *
 * Only the markings this deployment actually accepts are offered. Showing
 * SECRET on a deployment whose API refuses it would invite someone to paste
 * material in and find out afterwards.
 */
function NewDataset({
  projects,
  disciplines,
  policy,
  onClose,
}: {
  projects: Project[];
  disciplines: Discipline[];
  policy: Vocabularies["classification_policy"] | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const permitted = policy?.permitted ?? ["UNCLASSIFIED"];

  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [classification, setClassification] = useState(permitted[0] ?? "UNCLASSIFIED");
  const [containsPii, setContainsPii] = useState(false);
  const [expertise, setExpertise] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = useMemo(() => {
    const keys = new Set(disciplines.map((d) => d.key));
    return [
      ...disciplines,
      ...expertise.filter((e) => !keys.has(e)).map((e) => ({ key: e, label: e })),
    ];
  }, [disciplines, expertise]);

  const create = async () => {
    if (!projectId || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.post<{ id: string }>(`/projects/${projectId}/datasets`, {
        name: name.trim(),
        description: description.trim() || null,
        classification,
        contains_pii: containsPii,
        required_expertise: expertise,
      });
      // Straight to the detail view, which is where the data gets uploaded.
      router.push(`/datasets/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create this dataset.");
      setSaving(false);
    }
  };

  const field =
    "h-7 w-full border border-line bg-panel px-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-line-strong";

  return (
    <SlideOver open onClose={onClose} label="New dataset">
      <div className="space-y-3.5 p-4">
        <div>
          <h2 className="text-lg text-ink">New dataset</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            A dataset is the set of cases a system is put through. Create it here, then upload
            the data — the platform reports what it found in the file before anything runs
            against it.
          </p>
        </div>

        <div>
          <label htmlFor="ds-project" className="text-2xs uppercase tracking-wider text-faint">
            Project
          </label>
          <select
            id="ds-project"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            className={`mt-1 appearance-none ${field}`}
          >
            {projects.length === 0 ? <option value="">No project available</option> : null}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="ds-name" className="text-2xs uppercase tracking-wider text-faint">
            Name
          </label>
          <input
            id="ds-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Contract clause review"
            className={`mt-1 ${field}`}
          />
        </div>

        <div>
          <label htmlFor="ds-desc" className="text-2xs uppercase tracking-wider text-faint">
            Description
          </label>
          <textarea
            id="ds-desc"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
            placeholder="What these cases are meant to cover, and what they are not."
            className="mt-1 w-full border border-line bg-panel px-2.5 py-2 text-sm leading-relaxed text-ink outline-none placeholder:text-faint focus:border-line-strong"
          />
        </div>

        <div>
          <label htmlFor="ds-class" className="text-2xs uppercase tracking-wider text-faint">
            Classification
          </label>
          <select
            id="ds-class"
            value={classification}
            onChange={(event) => setClassification(event.target.value)}
            className={`mt-1 appearance-none ${field}`}
          >
            {permitted.map((marking) => (
              <option key={marking} value={marking}>
                {marking}
              </option>
            ))}
          </select>
          {policy?.note ? (
            <p className="mt-1 text-xs leading-relaxed text-muted">{policy.note}</p>
          ) : null}
        </div>

        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={containsPii}
            onChange={(event) => setContainsPii(event.target.checked)}
            className="h-3.5 w-3.5 accent-[rgb(var(--accent))]"
          />
          Contains personally identifiable information
        </label>

        <div>
          <div className="text-2xs uppercase tracking-wider text-faint">Required expertise</div>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            Who is qualified to judge these cases. Can be left empty and set later — a review
            will then record that no requirement was checked.
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {options.map((option) => {
              const on = expertise.includes(option.key);
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setExpertise((current) =>
                      current.includes(option.key)
                        ? current.filter((k) => k !== option.key)
                        : [...current, option.key],
                    )
                  }
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
          <input
            value={custom}
            onChange={(event) => setCustom(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              const slug = custom.trim().toLowerCase().replace(/\s+/g, "_");
              if (slug && !expertise.includes(slug)) setExpertise([...expertise, slug]);
              setCustom("");
            }}
            placeholder="Add a discipline not listed…"
            aria-label="Add a discipline not listed"
            className={`mt-2 w-56 ${field}`}
          />
        </div>

        {error ? <ErrorNote message={error} /> : null}

        <div className="flex items-center gap-2 pb-2">
          <Button
            variant="primary"
            onClick={create}
            disabled={saving || !projectId || !name.trim()}
          >
            {saving ? "Creating…" : "Create dataset"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </SlideOver>
  );
}

export default function DatasetsPage() {
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const datasets = useResource<DatasetRow[]>(() => api.get("/datasets"));
  const disciplines = useResource<{ disciplines: Discipline[] }>(() => api.get("/disciplines"));
  const projects = useResource<Project[]>(() => api.get("/projects"));
  const vocabularies = useResource<Vocabularies>(() => api.get("/vocabularies"));
  const canWrite = can("dataset:write");

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
        action={
          canWrite ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              New dataset
            </Button>
          ) : null
        }
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
            detail="A dataset is the set of cases a system is put through. Create one against a project and upload JSONL, JSON, CSV or plain text — the platform reports what it found in the file before anything runs against it: empty inputs, duplicates, and whether any row carries an expected answer at all."
            action={
              canWrite ? (
                <Button variant="primary" onClick={() => setCreating(true)}>
                  New dataset
                </Button>
              ) : null
            }
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

      {creating ? (
        <NewDataset
          projects={projects.data ?? []}
          disciplines={disciplines.data?.disciplines ?? []}
          policy={vocabularies.data?.classification_policy ?? null}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  );
}
