"use client";

import { use, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import {
  Bar,
  Button,
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Select,
  Spec,
  Spinner,
  Table,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { EvaluationBrief } from "@/lib/types";

interface PlanItem {
  id: string;
  evaluation_id: string;
  threshold: Record<string, unknown>;
  rationale: string | null;
  included: boolean;
  ordinal: number;
  evaluation: (EvaluationBrief & { description: string | null }) | null;
}

interface Coverage {
  evaluations: number;
  layers: Record<string, { label: string; count: number; covered: boolean }>;
  domains: Record<string, { label: string; count: number; covered: boolean }>;
  uncovered_layers: string[];
  uncovered_domains: string[];
  thresholds_unconfirmed: number;
  evaluations_without_scenarios: Array<{
    evaluation_key: string;
    evaluation_name: string;
    selector: Record<string, unknown>;
  }>;
  ready_to_approve: boolean;
  note: string;
}

interface PlanDetail {
  plan: { id: string; name: string; rationale: string | null; status: string };
  items: PlanItem[];
  coverage: Coverage;
}

export default function PlanPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { can } = useAuth();
  const [planId, setPlanId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const plans = useResource<Array<{ id: string; name: string; status: string }>>(
    () => api.get(`/projects/${projectId}/plans`),
    [projectId],
  );
  const activeId = planId ?? plans.data?.[0]?.id ?? null;

  const detail = useResource<PlanDetail | null>(
    () => (activeId ? api.get<PlanDetail>(`/plans/${activeId}`) : Promise.resolve(null)),
    [activeId],
  );

  async function generate() {
    setBusy(true);
    setActionError(null);
    try {
      const plan = await api.post<{ id: string }>(`/projects/${projectId}/plans/generate`, {});
      setPlanId(plan.id);
      plans.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not draft a plan.");
    } finally {
      setBusy(false);
    }
  }

  if (plans.loading) return <Spinner label="Loading plans" />;
  if (plans.error)
    return <ErrorNote message={plans.error} status={plans.status} onRetry={plans.reload} />;

  const coverage = detail.data?.coverage;

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        {(plans.data ?? []).length > 0 ? (
          <Select
            label="Plan"
            value={activeId ?? ""}
            onChange={setPlanId}
            options={(plans.data ?? []).map((plan) => ({
              value: plan.id,
              label: `${plan.name} · ${plan.status}`,
            }))}
          />
        ) : null}
        {can("evaluation:write") ? (
          <Button onClick={generate} disabled={busy}>
            {busy ? "Drafting…" : "Draft from mission profile"}
          </Button>
        ) : null}
      </div>

      {!activeId ? (
        <Card>
          <Empty
            title="No evaluation plan yet"
            detail="A plan is drafted from the mission profile, the system architecture and the deployment context, then edited and approved by the program office."
          />
        </Card>
      ) : detail.loading ? (
        <Spinner label="Loading plan" />
      ) : detail.error ? (
        <ErrorNote message={detail.error} status={detail.status} onRetry={detail.reload} />
      ) : detail.data && coverage ? (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHead
                title="Coverage by T&E area"
                meta="The four layers a system is evaluated across"
              />
              <div className="border-t border-line">
                {Object.entries(coverage.layers).map(([key, info]) => {
                  const peak = Math.max(
                    1,
                    ...Object.values(coverage.layers).map((layer) => layer.count),
                  );
                  return (
                    <div
                      key={key}
                      className="flex items-center gap-3 border-b border-line px-4 py-2 last:border-b-0"
                    >
                      <span className="w-52 shrink-0 truncate text-sm text-ink">{info.label}</span>
                      <Bar
                        value={info.count / peak}
                        tone={info.count === 0 ? "muted" : "ink"}
                        className="flex-1"
                      />
                      {info.count > 0 ? (
                        <span className="numeral tnum w-8 shrink-0 text-right text-base text-ink">
                          {info.count}
                        </span>
                      ) : (
                        <span className="w-8 shrink-0 text-right text-2xs uppercase tracking-wider text-warn">
                          none
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card>
              <CardHead
                title="Readiness to approve"
                meta="What stands between this draft and an approved plan"
              />
              <div className="border-t border-line">
                {[
                  {
                    label: "Evaluations in plan",
                    value: coverage.evaluations,
                    warn: false,
                  },
                  {
                    label: "Thresholds unconfirmed",
                    value: coverage.thresholds_unconfirmed,
                    warn: coverage.thresholds_unconfirmed > 0,
                  },
                  {
                    label: "Evaluations without scenarios",
                    value: coverage.evaluations_without_scenarios.length,
                    warn: coverage.evaluations_without_scenarios.length > 0,
                  },
                ].map((row) => (
                  <div
                    key={row.label}
                    className="flex items-center justify-between border-b border-line px-4 py-2"
                  >
                    <span className="text-sm text-muted">{row.label}</span>
                    <span
                      className={`numeral tnum text-base ${row.warn ? "text-warn" : "text-ink"}`}
                    >
                      {row.value}
                    </span>
                  </div>
                ))}
                <div className="space-y-2 px-4 py-3">
                  {coverage.uncovered_domains.length > 0 ? (
                    <p className="text-xs leading-relaxed text-muted">
                      Not covered: {coverage.uncovered_domains.join(", ")}. Those domains will
                      report NOT EVALUATED.
                    </p>
                  ) : null}
                  <Caveat>
                    {coverage.thresholds_unconfirmed > 0
                      ? "A library default is a suggestion, not a passing bar. The program office confirms each threshold before this plan can be approved."
                      : coverage.note}
                  </Caveat>
                </div>
              </div>
            </Card>
          </div>

          <Card>
            <CardHead
              title={detail.data.plan.name}
              meta={detail.data.plan.rationale ?? undefined}
              action={<Tag tone="strong">{detail.data.plan.status}</Tag>}
            />
            {detail.data.items.length === 0 ? (
              <div className="border-t border-line">
                <Empty title="This plan lists no evaluations" />
              </div>
            ) : (
              <Table minWidth={880}>
                <thead>
                  <tr>
                    <Th className="w-[18rem]">Evaluation</Th>
                    <Th className="w-[11.25rem]">Layer / domain</Th>
                    <Th className="w-[17.25rem]">Threshold</Th>
                    <Th>Why it is in this plan</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.data.items.map((item, index) => {
                    const threshold = { ...item.threshold };
                    const unconfirmed = threshold.source === "library_default_unconfirmed";
                    delete threshold.source;
                    return (
                      <Tr key={item.id} index={index}>
                        <Td>
                          <div className="text-sm text-ink">{item.evaluation?.name}</div>
                          <div className="font-mono text-2xs text-faint">
                            {item.evaluation?.key}
                          </div>
                        </Td>
                        <Td>
                          <div className="text-xs text-muted">
                            {item.evaluation?.layer?.replace(/_/g, " ")}
                          </div>
                          <div className="text-xs text-faint">
                            {item.evaluation?.domain?.replace(/_/g, " ")}
                          </div>
                        </Td>
                        <Td>
                          {/* Rendered as pairs rather than as the JSON on the
                              wire: this is the bar the program office agreed
                              to, and it should read as one. */}
                          <Spec value={threshold} />
                          {unconfirmed ? (
                            <div className="mt-1">
                              <Tag tone="warn">library default, unconfirmed</Tag>
                            </div>
                          ) : null}
                        </Td>
                        <Td>
                          <span className="text-xs leading-relaxed text-muted">
                            {item.rationale}
                          </span>
                        </Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Card>
        </>
      ) : null}
    </div>
  );
}
