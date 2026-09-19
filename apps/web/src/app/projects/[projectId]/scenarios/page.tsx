"use client";

import { use, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import { Button, Card, CardHeader, Caveat, Empty, ErrorNote, FilterChips, Hash, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface Scenario {
  id: string;
  key: string;
  title: string;
  task: string | null;
  difficulty: string;
  threat_type: string | null;
  tags: string[];
  source: string | null;
  approved: boolean;
  generated: boolean;
  content_hash: string;
  expected_behavior: string[];
  prohibited_behavior: string[];
}

export default function ScenariosPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { can } = useAuth();
  const [tag, setTag] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const scenarios = useResource<Scenario[]>(
    () => api.get<Scenario[]>(`/projects/${projectId}/scenarios`),
    [projectId],
  );

  async function approve(id: string) {
    setActionError(null);
    try {
      await api.post(`/scenarios/${id}/approve`);
      scenarios.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not approve.");
    }
  }

  async function generate() {
    setBusy(true);
    setActionError(null);
    try {
      await api.post(`/projects/${projectId}/scenarios/generate`, { mode: "mission_expansion" });
      scenarios.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not generate scenarios.");
    } finally {
      setBusy(false);
    }
  }

  async function materialiseRedTeam() {
    setBusy(true);
    setActionError(null);
    try {
      await api.post(`/projects/${projectId}/scenarios/red-team`, {
        attack_keys: [],
        mission_tasks: [],
      });
      scenarios.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not build attack scenarios.");
    } finally {
      setBusy(false);
    }
  }

  if (scenarios.loading) return <Spinner label="Loading scenarios" />;
  if (scenarios.error) return <ErrorNote message={scenarios.error} />;

  const all = scenarios.data ?? [];
  const drafts = all.filter((s) => !s.approved);
  const tags = Array.from(new Set(all.flatMap((s) => s.tags))).sort();
  const rows = all.filter((s) => !tag || s.tags.includes(tag));

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      {can("evaluation:write") ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={generate} disabled={busy} size="sm">
            Generate from mission profile
          </Button>
          <Button onClick={materialiseRedTeam} disabled={busy} size="sm">
            Build adversarial scenarios
          </Button>
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <Card>
          <CardHeader
            title={`${drafts.length} draft${drafts.length === 1 ? "" : "s"} awaiting approval`}
            subtitle="Generated scenarios do not run until a person approves them"
          />
          <div className="divide-y divide-line">
            {drafts.slice(0, 12).map((scenario) => (
              <div key={scenario.id} className="flex items-start gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{scenario.title}</p>
                  <code className="font-mono text-[11px] text-muted">{scenario.key}</code>
                  {scenario.expected_behavior.length > 0 ? (
                    <p className="mt-1 text-xs text-muted">
                      Expects: {scenario.expected_behavior.join("; ")}
                    </p>
                  ) : null}
                </div>
                {can("evaluation:write") ? (
                  <Button size="sm" onClick={() => approve(scenario.id)}>
                    Approve
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
          <div className="border-t border-line px-4 py-2.5">
            <Caveat>
              A drafted scenario is a proposal. It stays out of every run until a person has read
              it and accepted it as a fair test.
            </Caveat>
          </div>
        </Card>
      ) : null}

      <FilterChips
        options={tags.map((t) => ({
          key: t,
          label: t,
          count: all.filter((s) => s.tags.includes(t)).length,
        }))}
        active={tag}
        onChange={setTag}
        allLabel={`All (${all.length})`}
      />

      <Card>
        <CardHeader title="Scenario library" subtitle={`${rows.length} shown`} />
        {rows.length === 0 ? (
          <Empty title="No scenarios match this filter" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2 font-medium">Scenario</th>
                  <th className="px-4 py-2 font-medium">Tags</th>
                  <th className="px-4 py-2 font-medium">Difficulty</th>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Version hash</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((scenario) => (
                  <tr key={scenario.id} className="border-b border-line last:border-0">
                    <td className="px-4 py-2.5">
                      <div className="text-sm">{scenario.title}</div>
                      <code className="font-mono text-[11px] text-muted">{scenario.key}</code>
                      {!scenario.approved ? (
                        <span className="ml-2 rounded bg-[rgb(var(--warn-bg))] px-1.5 py-0.5 text-[10px] text-[rgb(var(--warn))]">
                          draft
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {scenario.tags.slice(0, 4).map((t) => (
                          <span
                            key={t}
                            className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] text-muted"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{scenario.difficulty}</td>
                    <td className="px-4 py-2.5 text-xs text-muted">{scenario.source ?? "—"}</td>
                    <td className="px-4 py-2.5">
                      <Hash value={scenario.content_hash} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
