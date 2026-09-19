"use client";

import { use, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Select,
  Hash,
  Spinner,
  Table,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui";
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
  if (scenarios.error)
    return <ErrorNote message={scenarios.error} status={scenarios.status} onRetry={scenarios.reload} />;

  const all = scenarios.data ?? [];
  const drafts = all.filter((s) => !s.approved);
  const tags = Array.from(new Set(all.flatMap((s) => s.tags))).sort();
  const rows = all.filter((s) => !tag || s.tags.includes(tag));

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      {can("evaluation:write") ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={generate} disabled={busy}>
            Generate from mission profile
          </Button>
          <Button onClick={materialiseRedTeam} disabled={busy}>
            Build adversarial scenarios
          </Button>
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <Card>
          <CardHead
            title={`${drafts.length} draft${drafts.length === 1 ? "" : "s"} awaiting approval`}
            meta="Generated scenarios do not run until a person approves them"
          />
          <div className="border-t border-line">
            {drafts.slice(0, 12).map((scenario) => (
              <div
                key={scenario.id}
                className="flex items-start gap-3 border-b border-line px-4 py-2.5 transition-colors duration-150 ease-out last:border-b-0 hover:bg-sunken"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{scenario.title}</p>
                  <code className="font-mono text-2xs text-faint">{scenario.key}</code>
                  {scenario.expected_behavior.length > 0 ? (
                    <p className="mt-1 text-xs text-muted">
                      Expects: {scenario.expected_behavior.join("; ")}
                    </p>
                  ) : null}
                </div>
                {can("evaluation:write") ? (
                  <Button onClick={() => approve(scenario.id)}>Approve</Button>
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

      {/* A library this size carries more tags than a segmented control can
          hold, and a row of chips that runs off the edge is worse than a
          list. The tags are ordered by how much of the library each one
          actually narrows. */}
      <Select
        label="Tag"
        value={tag ?? ""}
        onChange={(value) => setTag(value === "" ? null : value)}
        options={[
          { value: "", label: `All tags (${all.length})` },
          ...tags
            .map((t) => ({ tag: t, count: all.filter((s) => s.tags.includes(t)).length }))
            .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
            .map(({ tag: t, count }) => ({ value: t, label: `${t} · ${count}` })),
        ]}
      />

      <Card>
        <CardHead
          title="Scenario library"
          meta={rows.length === all.length ? `${all.length} total` : `${rows.length} of ${all.length}`}
        />
        {rows.length === 0 ? (
          <div className="border-t border-line">
            <Empty title="No scenarios match this filter" />
          </div>
        ) : (
          <Table minWidth={820}>
            <thead>
              <tr>
                <Th>Scenario</Th>
                <Th className="w-[220px]">Tags</Th>
                <Th className="w-[110px]">Difficulty</Th>
                <Th className="w-[130px]">Source</Th>
                <Th className="w-[120px]">Version hash</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((scenario, index) => (
                <Tr key={scenario.id} index={index}>
                  <Td>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-ink">{scenario.title}</span>
                      {/* A draft is marked everywhere it appears. A scenario
                          nobody has accepted as fair is not part of the test
                          set yet, however finished it looks. */}
                      {!scenario.approved ? <Tag tone="warn">draft</Tag> : null}
                    </div>
                    <code className="font-mono text-2xs text-faint">{scenario.key}</code>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {scenario.tags.slice(0, 4).map((t) => (
                        <Tag key={t}>{t}</Tag>
                      ))}
                      {scenario.tags.length > 4 ? (
                        <span className="text-2xs text-faint">
                          +{scenario.tags.length - 4}
                        </span>
                      ) : null}
                    </div>
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">{scenario.difficulty}</span>
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">{scenario.source ?? "—"}</span>
                  </Td>
                  <Td>
                    <Hash value={scenario.content_hash} />
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
