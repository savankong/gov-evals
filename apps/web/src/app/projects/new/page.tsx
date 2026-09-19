"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Choice, Field, FormActions, TextArea } from "@/components/forms";
import { useResource } from "@/components/shell";
import { Card, CardHead, Caveat, PageTitle, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface Program {
  id: string;
  name: string;
}
interface Vocabularies {
  classification_policy: { permitted: string[]; note: string };
  impact_levels: string[];
  system_kinds: string[];
}

export default function NewProjectPage() {
  const router = useRouter();
  const programs = useResource<Program[]>(() => api.get("/programs"));
  const vocab = useResource<Vocabularies>(() => api.get("/vocabularies"));

  const [programId, setProgramId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [classification, setClassification] = useState("UNCLASSIFIED");
  const [impactLevel, setImpactLevel] = useState("");
  const [systemOwner, setSystemOwner] = useState("");
  const [evaluationOwner, setEvaluationOwner] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!programId && programs.data?.length) setProgramId(programs.data[0].id);
  }, [programs.data, programId]);

  useEffect(() => {
    const permitted = vocab.data?.classification_policy.permitted;
    if (permitted?.length && !permitted.includes(classification)) setClassification(permitted[0]);
  }, [vocab.data, classification]);

  const create = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await api.post<{ id: string }>("/projects", {
        program_id: programId,
        name: name.trim(),
        description: description.trim() || null,
        classification,
        impact_level: impactLevel || null,
        system_owner: systemOwner.trim() || null,
        evaluation_owner: evaluationOwner.trim() || null,
      });
      // Straight to the mission profile: a project without one cannot judge
      // anything, and this is the moment somebody has the context to write it.
      router.push(`/projects/${created.id}/mission`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create this project.");
      setSaving(false);
    }
  };

  if (programs.loading) return <Spinner label="Loading programmes" />;

  return (
    <div className="space-y-4">
      <PageTitle
        title="New evaluation project"
        subtitle="A project pairs one AI capability with the mission it is meant for. Everything else hangs off that pairing."
      />

      <Card>
        <CardHead title="The project" />
        <div className="space-y-3.5 border-t border-line px-4 py-3">
          <Choice
            id="program"
            label="Programme"
            value={programId}
            onChange={setProgramId}
            required
            options={(programs.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
            help={
              (programs.data ?? []).length === 0
                ? "No programme is visible to your account. One must exist before a project can hang off it."
                : undefined
            }
          />
          <Field
            id="name"
            label="Name"
            value={name}
            onChange={setName}
            required
            placeholder="Contract Review Assistant"
          />
          <TextArea
            id="description"
            label="Description"
            value={description}
            onChange={setDescription}
            placeholder="What this capability is for, in a sentence or two."
          />

          <div className="grid gap-3.5 sm:grid-cols-2">
            <Choice
              id="classification"
              label="Classification"
              value={classification}
              onChange={setClassification}
              options={(vocab.data?.classification_policy.permitted ?? ["UNCLASSIFIED"]).map(
                (m) => ({ value: m, label: m }),
              )}
              help={vocab.data?.classification_policy.note}
            />
            <Choice
              id="impact"
              label="Impact level"
              value={impactLevel}
              onChange={setImpactLevel}
              options={[
                { value: "", label: "Not stated" },
                ...(vocab.data?.impact_levels ?? []).map((l) => ({ value: l, label: l })),
              ]}
            />
            <Field
              id="system-owner"
              label="System owner"
              value={systemOwner}
              onChange={setSystemOwner}
            />
            <Field
              id="eval-owner"
              label="Evaluation owner"
              value={evaluationOwner}
              onChange={setEvaluationOwner}
            />
          </div>

          <FormActions
            onSubmit={create}
            onCancel={() => router.push("/")}
            submitting={saving}
            disabled={!programId || !name.trim()}
            error={error}
            submitLabel="Create and write the mission profile"
            busyLabel="Creating…"
          />
        </div>
      </Card>

      <Caveat>
        Only the markings this deployment accepts are offered. Creating a project does not
        evaluate anything — it opens a place to record what evaluation is for.
      </Caveat>
    </div>
  );
}
