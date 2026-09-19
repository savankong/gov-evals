"use client";

import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { Field, FormActions, Lines, TextArea } from "@/components/forms";
import { useResource } from "@/components/shell";
import { Card, CardHead, Caveat, Crumbs, ErrorNote, PageTitle, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface MissionProfile {
  mission: string;
  tasks: string[];
  users: string[];
  expected_decisions: string[];
  operational_environment: string | null;
  expected_inputs: string[];
  expected_outputs: string[];
  acceptable_errors: string[];
  unacceptable_failures: string[];
  adversaries: string[];
  environmental_constraints: string[];
  latency_requirement_ms: number | null;
  human_oversight: string | null;
  dependencies: string[];
  operating_assumptions: string[];
}

const EMPTY: MissionProfile = {
  mission: "",
  tasks: [],
  users: [],
  expected_decisions: [],
  operational_environment: null,
  expected_inputs: [],
  expected_outputs: [],
  acceptable_errors: [],
  unacceptable_failures: [],
  adversaries: [],
  environmental_constraints: [],
  latency_requirement_ms: null,
  human_oversight: null,
  dependencies: [],
  operating_assumptions: [],
};

export default function MissionProfilePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = use(params);
  const router = useRouter();
  const existing = useResource<MissionProfile | null>(
    () => api.get(`/projects/${projectId}/mission`),
    [projectId],
  );
  const project = useResource<{ name: string }>(
    () => api.get(`/projects/${projectId}`),
    [projectId],
  );

  const [form, setForm] = useState<MissionProfile>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (existing.data) setForm({ ...EMPTY, ...existing.data });
  }, [existing.data]);

  const set = <K extends keyof MissionProfile>(key: K, value: MissionProfile[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.put(`/projects/${projectId}/mission`, {
        ...form,
        latency_requirement_ms: form.latency_requirement_ms || null,
      });
      setSaved(true);
      existing.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the mission profile.");
    } finally {
      setSaving(false);
    }
  };

  if (existing.loading) return <Spinner label="Loading the mission profile" />;

  return (
    <div className="space-y-4">
      <Crumbs
        items={[
          { label: "Portfolio", href: "/" },
          { label: project.data?.name ?? "Project", href: `/projects/${projectId}` },
          { label: "Mission profile" },
        ]}
      />

      <PageTitle
        title="Mission profile"
        subtitle="What the system is for. Every result is judged against this — it is what separates “how good is this model” from “good enough for this mission”."
      />

      {existing.error ? <ErrorNote message={existing.error} /> : null}

      <Card>
        <CardHead title="The mission" />
        <div className="space-y-3.5 border-t border-line px-4 py-3">
          <TextArea
            id="mission"
            label="Mission"
            value={form.mission}
            onChange={(v) => set("mission", v)}
            rows={3}
            required
            placeholder="Review draft contract documents and surface clauses that conflict with federal acquisition regulation."
          />
          <div className="grid gap-3.5 sm:grid-cols-2">
            <Lines
              id="tasks"
              label="Tasks"
              value={form.tasks}
              onChange={(v) => set("tasks", v)}
              placeholder={"Summarise a clause\nFlag a conflict"}
              help="One per line."
            />
            <Lines
              id="users"
              label="Users"
              value={form.users}
              onChange={(v) => set("users", v)}
              placeholder={"Contracting officer\nProgramme analyst"}
            />
            <Lines
              id="inputs"
              label="Expected inputs"
              value={form.expected_inputs}
              onChange={(v) => set("expected_inputs", v)}
            />
            <Lines
              id="outputs"
              label="Expected outputs"
              value={form.expected_outputs}
              onChange={(v) => set("expected_outputs", v)}
            />
            <Lines
              id="decisions"
              label="Decisions it informs"
              value={form.expected_decisions}
              onChange={(v) => set("expected_decisions", v)}
            />
            <Lines
              id="dependencies"
              label="Dependencies"
              value={form.dependencies}
              onChange={(v) => set("dependencies", v)}
            />
          </div>
        </div>
      </Card>

      <Card>
        <CardHead
          title="What failure means here"
          subtitle="The part that does the work. An error the programme can absorb and one it cannot are not the same finding, and only you can say which is which."
        />
        <div className="grid gap-3.5 border-t border-line px-4 py-3 sm:grid-cols-2">
          <Lines
            id="acceptable"
            label="Acceptable errors"
            value={form.acceptable_errors}
            onChange={(v) => set("acceptable_errors", v)}
            help="Mistakes the mission can absorb."
          />
          <Lines
            id="unacceptable"
            label="Unacceptable failures"
            value={form.unacceptable_failures}
            onChange={(v) => set("unacceptable_failures", v)}
            help="Declare these and a campaign that produces one is a finding, not a statistic."
          />
          <Lines
            id="adversaries"
            label="Adversaries"
            value={form.adversaries}
            onChange={(v) => set("adversaries", v)}
            help="Who would want this to fail, and how."
          />
          <Lines
            id="constraints"
            label="Environmental constraints"
            value={form.environmental_constraints}
            onChange={(v) => set("environmental_constraints", v)}
          />
          <Lines
            id="assumptions"
            label="Operating assumptions"
            value={form.operating_assumptions}
            onChange={(v) => set("operating_assumptions", v)}
          />
        </div>
      </Card>

      <Card>
        <CardHead title="Conditions" />
        <div className="grid gap-3.5 border-t border-line px-4 py-3 sm:grid-cols-2">
          <TextArea
            id="environment"
            label="Operational environment"
            value={form.operational_environment ?? ""}
            onChange={(v) => set("operational_environment", v || null)}
            rows={2}
          />
          <TextArea
            id="oversight"
            label="Human oversight"
            value={form.human_oversight ?? ""}
            onChange={(v) => set("human_oversight", v || null)}
            rows={2}
            help="Who reviews the output, and with how much time."
          />
          <Field
            id="latency"
            label="Latency requirement (ms)"
            value={form.latency_requirement_ms?.toString() ?? ""}
            onChange={(v) => set("latency_requirement_ms", v ? Number(v) : null)}
            type="number"
          />
        </div>
      </Card>

      <div className="space-y-2.5">
        {saved ? <Caveat>Saved. Plans generated from now on are drafted against this.</Caveat> : null}
        <FormActions
          onSubmit={save}
          onCancel={() => router.push(`/projects/${projectId}`)}
          submitting={saving}
          disabled={!form.mission.trim()}
          error={error}
          submitLabel={existing.data ? "Save the mission profile" : "Create the mission profile"}
        />
      </div>

      <Caveat>
        An empty field is not a neutral choice. A plan drafted against a profile with no declared
        unacceptable failures has nothing to treat as unacceptable, and will say so rather than
        inventing one.
      </Caveat>
    </div>
  );
}
