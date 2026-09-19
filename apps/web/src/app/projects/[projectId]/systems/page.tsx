"use client";

import { use, useState } from "react";

import { Choice, Field, FormActions, TextArea } from "@/components/forms";
import { SlideOver, useResource } from "@/components/shell";
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

interface System {
  id: string;
  name: string;
  slug: string;
  kind: string;
  vendor: string | null;
  description: string | null;
}
interface Version {
  id: string;
  system_id: string;
  version: string;
  model_provider: string | null;
  model_name: string | null;
  connector_type: string;
  endpoint: string | null;
  config_hash: string;
  is_current: boolean;
  created_at: string;
}
interface Connector {
  key: string;
  label: string;
  requires_egress: boolean;
}
interface Vocabularies {
  system_kinds: string[];
}

function NewSystem({
  projectId,
  kinds,
  onClose,
  onCreated,
}: {
  projectId: string;
  kinds: string[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState(kinds[0] ?? "llm");
  const [vendor, setVendor] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/projects/${projectId}/systems`, {
        name: name.trim(),
        kind,
        vendor: vendor.trim() || null,
        description: description.trim() || null,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register this system.");
      setSaving(false);
    }
  };

  return (
    <SlideOver open onClose={onClose} label="Register a system">
      <div className="space-y-3.5 p-4">
        <div>
          <h2 className="text-lg text-ink">Register a system</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            The capability under evaluation. Versions of it are registered separately, because a
            result must name the exact configuration that produced it.
          </p>
        </div>
        <Field id="sys-name" label="Name" value={name} onChange={setName} required />
        <Choice
          id="sys-kind"
          label="Kind"
          value={kind}
          onChange={setKind}
          options={kinds.map((k) => ({ value: k, label: k.replace(/_/g, " ") }))}
        />
        <Field id="sys-vendor" label="Vendor" value={vendor} onChange={setVendor} />
        <TextArea
          id="sys-desc"
          label="Description"
          value={description}
          onChange={setDescription}
          rows={2}
        />
        <FormActions
          onSubmit={create}
          onCancel={onClose}
          submitting={saving}
          disabled={!name.trim()}
          error={error}
          submitLabel="Register system"
        />
      </div>
    </SlideOver>
  );
}

function NewVersion({
  system,
  connectors,
  onClose,
  onCreated,
}: {
  system: System;
  connectors: Connector[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [version, setVersion] = useState("");
  const [connectorType, setConnectorType] = useState(connectors[0]?.key ?? "echo");
  const [provider, setProvider] = useState("");
  const [modelName, setModelName] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [changeNote, setChangeNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const connector = connectors.find((c) => c.key === connectorType);

  const create = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/systems/${system.id}/versions`, {
        version: version.trim(),
        connector_type: connectorType,
        model_provider: provider.trim() || null,
        model_name: modelName.trim() || null,
        endpoint: endpoint.trim() || null,
        system_prompt: systemPrompt.trim() || null,
        change_note: changeNote.trim() || null,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register this version.");
      setSaving(false);
    }
  };

  return (
    <SlideOver open onClose={onClose} label="Register a version">
      <div className="space-y-3.5 p-4">
        <div>
          <h2 className="text-lg text-ink">New version of {system.name}</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            An immutable snapshot — model, prompt, parameters, connector — fingerprinted so a
            result can always name what produced it. Changing any of it means a new version, not
            an edit.
          </p>
        </div>

        <Field
          id="ver"
          label="Version"
          value={version}
          onChange={setVersion}
          required
          placeholder="v1.0"
        />
        <Choice
          id="connector"
          label="Connector"
          value={connectorType}
          onChange={setConnectorType}
          options={connectors.map((c) => ({ value: c.key, label: c.label }))}
          help={
            connector?.requires_egress
              ? "This connector makes outbound calls. Under AEGIS_EGRESS_POLICY=deny its host must be on the allowlist or the request is refused before it leaves."
              : "Makes no outbound call."
          }
        />
        <div className="grid gap-3.5 sm:grid-cols-2">
          <Field id="provider" label="Model provider" value={provider} onChange={setProvider} />
          <Field id="model" label="Model name" value={modelName} onChange={setModelName} />
        </div>
        <Field
          id="endpoint"
          label="Endpoint"
          value={endpoint}
          onChange={setEndpoint}
          placeholder="https://…"
        />
        <TextArea
          id="prompt"
          label="System prompt"
          value={systemPrompt}
          onChange={setSystemPrompt}
          rows={4}
          help="Part of the fingerprint. Two versions differing only here are exactly what a comparison campaign is for."
        />
        <TextArea
          id="note"
          label="What changed"
          value={changeNote}
          onChange={setChangeNote}
          rows={2}
        />

        <FormActions
          onSubmit={create}
          onCancel={onClose}
          submitting={saving}
          disabled={!version.trim()}
          error={error}
          submitLabel="Register version"
        />
      </div>
    </SlideOver>
  );
}

function SystemVersions({ system }: { system: System }) {
  const versions = useResource<Version[]>(
    () => api.get(`/systems/${system.id}/versions`),
    [system.id],
  );
  const connectors = useResource<{ connectors: Connector[] }>(() => api.get("/connectors"));
  const [adding, setAdding] = useState(false);

  return (
    <Card>
      <CardHead
        title={system.name}
        subtitle={[system.kind.replace(/_/g, " "), system.vendor].filter(Boolean).join(" · ")}
        action={
          <Button onClick={() => setAdding(true)}>New version</Button>
        }
      />
      {versions.loading ? (
        <Spinner label="Loading versions" />
      ) : (versions.data ?? []).length === 0 ? (
        <Empty
          title="No versions registered"
          detail="A system with no version cannot be evaluated: there is nothing for a result to name."
        />
      ) : (
        <Table minWidth={720}>
          <thead>
            <tr>
              <Th>Version</Th>
              <Th>Model</Th>
              <Th>Connector</Th>
              <Th>Config hash</Th>
              <Th>Registered</Th>
            </tr>
          </thead>
          <tbody>
            {(versions.data ?? []).map((v, index) => (
              <Tr key={v.id} index={index}>
                <Td>
                  <span className="text-ink">{v.version}</span>
                  {v.is_current ? (
                    <div className="mt-0.5">
                      <Tag tone="strong">Current</Tag>
                    </div>
                  ) : null}
                </Td>
                <Td className="text-muted">
                  {[v.model_provider, v.model_name].filter(Boolean).join(" / ") || "—"}
                </Td>
                <Td className="text-muted">{v.connector_type}</Td>
                <Td>
                  <Hash value={v.config_hash} />
                </Td>
                <Td className="text-muted">{formatDate(v.created_at)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      {adding ? (
        <NewVersion
          system={system}
          connectors={connectors.data?.connectors ?? []}
          onClose={() => setAdding(false)}
          onCreated={versions.reload}
        />
      ) : null}
    </Card>
  );
}

export default function SystemsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const systems = useResource<System[]>(
    () => api.get(`/projects/${projectId}/systems`),
    [projectId],
  );
  const project = useResource<{ name: string }>(
    () => api.get(`/projects/${projectId}`),
    [projectId],
  );
  const vocab = useResource<Vocabularies>(() => api.get("/vocabularies"));
  const [creating, setCreating] = useState(false);

  return (
    <div className="space-y-4">
      <Crumbs
        items={[
          { label: "Portfolio", href: "/" },
          { label: project.data?.name ?? "Project", href: `/projects/${projectId}` },
          { label: "Systems" },
        ]}
      />

      <PageTitle
        title="Systems"
        subtitle="Each version is an immutable configuration snapshot, fingerprinted so a result can always name the exact thing that produced it."
        action={
          <Button variant="primary" onClick={() => setCreating(true)}>
            Register a system
          </Button>
        }
      />

      {systems.error ? <ErrorNote message={systems.error} /> : null}

      {systems.loading ? (
        <Spinner label="Loading systems" />
      ) : (systems.data ?? []).length === 0 ? (
        <Card>
          <Empty
            title="No systems registered"
            detail="Register the capability under evaluation, then a version of it. A campaign runs against versions, not against systems, because that is the level at which a configuration is pinned down."
            action={
              <Button variant="primary" onClick={() => setCreating(true)}>
                Register a system
              </Button>
            }
          />
        </Card>
      ) : (
        (systems.data ?? []).map((system) => <SystemVersions key={system.id} system={system} />)
      )}

      <Caveat>
        Registering a version records a configuration; it does not test that the configuration
        works. Use the connectivity check on a version before a campaign spends a budget
        discovering the endpoint was wrong.
      </Caveat>

      {creating ? (
        <NewSystem
          projectId={projectId}
          kinds={vocab.data?.system_kinds ?? ["llm"]}
          onClose={() => setCreating(false)}
          onCreated={systems.reload}
        />
      ) : null}
    </div>
  );
}
