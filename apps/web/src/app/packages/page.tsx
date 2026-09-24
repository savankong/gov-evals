"use client";

import { useState } from "react";

import { Field, FormActions, Label } from "@/components/forms";
import { SlideOver, useResource } from "@/components/shell";
import {
  Button,
  Caveat,
  Card,
  CardHead,
  Empty,
  ErrorNote,
  Hash,
  Note,
  PageTitle,
  Table,
  TableSkeleton,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface Bin {
  knowledge_area: string | null;
  model_outcome: string;
  kind: string;
  records: number;
}

interface Exclusion {
  reason: string;
  label: string;
  records: number;
}

interface DataPackage {
  id: string;
  name: string;
  customer: string | null;
  selection: {
    knowledge_areas: string[];
    include_traces: boolean;
    include_scored_responses: boolean;
  };
  record_count: number;
  manifest: {
    schema: string;
    confident_at: number;
    kinds: Record<string, number>;
    bins: Bin[];
    excluded: Exclusion[];
  };
  sha256: string;
  size_bytes: number;
  classification: string;
  created_by: string | null;
  created_at: string;
}

interface WeaknessMap {
  areas: Array<{ knowledge_area: string | null; label: string; qualified_traces: number }>;
}

const KIND_LABELS: Record<string, string> = {
  reasoning_trace: "Reasoning traces",
  scored_response: "Scored model answers",
};

const OUTCOME_LABELS: Record<string, string> = {
  failed: "model wrong",
  passed: "model right",
  not_evaluated: "model not evaluated",
};

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function NewPackage({ onCreated }: { onCreated: (pkg: DataPackage) => void }) {
  const areas = useResource(() => api.get<WeaknessMap>("/weakness-map"), []);
  const [name, setName] = useState("");
  const [customer, setCustomer] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [traces, setTraces] = useState(true);
  const [scored, setScored] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const pkg = await api.post<DataPackage>("/data-packages", {
        name: name.trim(),
        customer: customer.trim() || null,
        knowledge_areas: selected,
        include_traces: traces,
        include_scored_responses: scored,
      });
      setName("");
      setSelected([]);
      onCreated(pkg);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not build the package.");
    } finally {
      setSubmitting(false);
    }
  };

  const options = areas.data?.areas ?? [];

  return (
    <Card>
      <CardHead
        title="Build a package"
        subtitle="Choose what to send. What may leave is decided by the platform, not here: only UNCLASSIFIED, PII-free work by qualified experts, and only judgements someone actually made."
      />
      <div className="space-y-3 border-t border-line px-4 py-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id="pkg-name" label="Name" value={name} onChange={setName} required
            placeholder="Source selection, September" />
          <Field id="pkg-customer" label="Customer" value={customer} onChange={setCustomer}
            placeholder="Lab A" />
        </div>
        <div>
          <div className="text-2xs uppercase tracking-wider text-faint">Knowledge areas</div>
          {areas.error ? (
            <p className="mt-1 text-xs text-muted">
              Could not load the areas ({areas.error}). Leaving none selected sends every area.
            </p>
          ) : (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {options.map((area) => {
                const key = area.knowledge_area ?? "";
                const on = selected.includes(key);
                return (
                  <button
                    key={area.label}
                    type="button"
                    onClick={() =>
                      setSelected(on ? selected.filter((s) => s !== key) : [...selected, key])
                    }
                    className={`border px-2 py-0.5 text-xs transition-colors duration-150 ${
                      on ? "border-line-strong bg-sunken text-ink" : "border-line text-muted hover:text-ink"
                    }`}
                  >
                    {area.label}
                    <span className="tnum ml-1.5 text-faint">{area.qualified_traces}</span>
                  </button>
                );
              })}
            </div>
          )}
          <p className="mt-1 text-xs text-muted">
            {selected.length ? `${selected.length} selected.` : "None selected sends every area."}{" "}
            The number is qualified traces in each.
          </p>
        </div>
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <input id="inc-traces" type="checkbox" checked={traces}
              onChange={(e) => setTraces(e.target.checked)} />
            <Label htmlFor="inc-traces">Reasoning traces</Label>
          </div>
          <div className="flex items-center gap-2">
            <input id="inc-scored" type="checkbox" checked={scored}
              onChange={(e) => setScored(e.target.checked)} />
            <Label htmlFor="inc-scored">Scored model answers</Label>
          </div>
        </div>
        <FormActions
          onSubmit={submit}
          submitting={submitting}
          disabled={!name.trim() || (!traces && !scored)}
          error={error}
          submitLabel="Build package"
          busyLabel="Building…"
        />
      </div>
    </Card>
  );
}

function PackageDetail({ pkg }: { pkg: DataPackage }) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verified, setVerified] = useState<string | null>(null);

  const download = async () => {
    setDownloading(true);
    setError(null);
    try {
      const { sha256 } = await api.download(`/data-packages/${pkg.id}/download`, `${pkg.name}.jsonl`);
      setVerified(sha256);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download the package.");
    } finally {
      setDownloading(false);
    }
  };

  const excluded = pkg.manifest.excluded ?? [];
  return (
    <div className="space-y-4 p-4">
      <div>
        <h2 className="text-base text-ink">{pkg.name}</h2>
        <p className="mt-0.5 text-xs text-muted">
          {pkg.customer ?? "No customer named"} · {formatDate(pkg.created_at)} ·{" "}
          {pkg.created_by ?? "unknown"}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-px border border-line bg-line">
        <div className="bg-panel px-3 py-2">
          <div className="text-2xs uppercase tracking-wider text-faint">Records</div>
          <div className="tnum text-xl text-ink">{pkg.record_count}</div>
        </div>
        <div className="bg-panel px-3 py-2">
          <div className="text-2xs uppercase tracking-wider text-faint">Left out</div>
          <div className="tnum text-xl text-ink">
            {excluded.reduce((sum, e) => sum + e.records, 0)}
          </div>
        </div>
      </div>

      <div>
        <div className="text-2xs uppercase tracking-wider text-faint">Bins</div>
        <Table>
          <thead>
            <tr>
              <Th>Knowledge area</Th>
              <Th>Kind</Th>
              <Th align="right">Records</Th>
            </tr>
          </thead>
          <tbody>
            {pkg.manifest.bins.map((bin, index) => (
              <Tr key={index} index={index}>
                <Td>
                  <span className={bin.knowledge_area ? "text-ink" : "text-muted"}>
                    {bin.knowledge_area ?? "Not declared"}
                  </span>
                  <div className="mt-0.5 text-2xs text-faint">
                    {OUTCOME_LABELS[bin.model_outcome] ?? bin.model_outcome}
                  </div>
                </Td>
                <Td className="text-muted">{KIND_LABELS[bin.kind] ?? bin.kind}</Td>
                <Td align="right" className="tnum">{bin.records}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </div>

      <div>
        <div className="text-2xs uppercase tracking-wider text-faint">Left out, and why</div>
        {excluded.length === 0 ? (
          <p className="mt-1 text-xs text-muted">Everything considered was deliverable.</p>
        ) : (
          <ul className="mt-1 space-y-1">
            {excluded.map((e) => (
              <li key={e.reason} className="flex justify-between gap-3 text-xs">
                <span className="text-muted">{e.label}</span>
                <span className="tnum text-ink">{e.records}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-1 text-xs text-muted">
        <div>
          SHA-256 <Hash value={pkg.sha256} length={24} />
        </div>
        <div>
          {size(pkg.size_bytes)} · {pkg.manifest.schema} · marked {pkg.classification}
        </div>
      </div>

      {error ? <ErrorNote message={error} /> : null}
      {verified ? (
        <Note>
          Saved. The server checked the file against the digest recorded when it was built
          before sending it{verified === pkg.sha256 ? ", and the digests match" : ""}.
        </Note>
      ) : null}
      <Button variant="primary" onClick={download} disabled={downloading}>
        {downloading ? "Downloading…" : "Download JSONL"}
      </Button>
    </div>
  );
}

export default function PackagesPage() {
  const packages = useResource(() => api.get<DataPackage[]>("/data-packages"), []);
  const [active, setActive] = useState<DataPackage | null>(null);

  return (
    <div className="space-y-4">
      <PageTitle
        title="Packages"
        subtitle="Deliveries to a customer's ingest pipeline. Each is built once, stored, and hashed; what the record shows is what was sent."
      />

      <NewPackage
        onCreated={(pkg) => {
          packages.reload();
          setActive(pkg);
        }}
      />

      {packages.error ? (
        <ErrorNote message={packages.error} status={packages.status} onRetry={packages.reload} />
      ) : null}

      <Card>
        {packages.loading && !packages.data ? (
          <TableSkeleton rows={4} cols={5} />
        ) : packages.error ? null : (packages.data ?? []).length === 0 ? (
          <Empty
            title="No packages built yet"
            detail="A package is built from qualified reasoning traces and qualified judgements on model answers. Capture some first, then build one above."
          />
        ) : (
          <Table minWidth={760}>
            <thead>
              <tr>
                <Th>Package</Th>
                <Th>Customer</Th>
                <Th align="right">Records</Th>
                <Th align="right">Left out</Th>
                <Th>SHA-256</Th>
                <Th>Built</Th>
              </tr>
            </thead>
            <tbody>
              {(packages.data ?? []).map((pkg, index) => (
                <Tr key={pkg.id} index={index} onClick={() => setActive(pkg)}>
                  <Td className="text-ink">{pkg.name}</Td>
                  <Td className="text-muted">{pkg.customer ?? "—"}</Td>
                  <Td align="right" className="tnum">{pkg.record_count}</Td>
                  <Td align="right" className="tnum text-muted">
                    {(pkg.manifest.excluded ?? []).reduce((sum, e) => sum + e.records, 0)}
                  </Td>
                  <Td><Hash value={pkg.sha256} /></Td>
                  <Td className="text-muted">{formatDate(pkg.created_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Caveat>
        Experts appear in a package by pseudonym, discipline and whether that was verified —
        never by name. Every record carries its own SHA-256, and the file as a whole is checked
        against its recorded digest before each download.
      </Caveat>

      <SlideOver open={active !== null} onClose={() => setActive(null)} label="Package">
        {active ? <PackageDetail pkg={active} /> : null}
      </SlideOver>
    </div>
  );
}
