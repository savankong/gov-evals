"use client";

import { use, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import { Button, Card, CardHeader, Caveat, Empty, ErrorNote, Spinner } from "@/components/ui";
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
  if (plans.error) return <ErrorNote message={plans.error} />;

  const coverage = detail.data?.coverage;

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        {(plans.data ?? []).map((plan) => (
          <button
            key={plan.id}
            onClick={() => setPlanId(plan.id)}
            className={`rounded-full border px-3 py-1 text-xs ${
              activeId === plan.id
                ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 text-ink"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {plan.name} · {plan.status}
          </button>
        ))}
        {can("evaluation:write") ? (
          <Button onClick={generate} disabled={busy} size="sm">
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
        <ErrorNote message={detail.error} />
      ) : detail.data && coverage ? (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader title="Coverage by T&E area" />
              <div className="divide-y divide-line">
                {Object.entries(coverage.layers).map(([key, info]) => (
                  <div key={key} className="flex items-center justify-between px-4 py-2 text-sm">
                    <span>{info.label}</span>
                    {info.count > 0 ? (
                      <span className="tnum text-muted">{info.count}</span>
                    ) : (
                      <span className="text-xs font-medium text-[rgb(var(--warn))]">
                        not covered
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            <Card>
              <CardHeader title="Readiness to approve" />
              <div className="space-y-2 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted">Evaluations in plan</span>
                  <span className="tnum">{coverage.evaluations}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">Thresholds unconfirmed</span>
                  <span
                    className={`tnum ${
                      coverage.thresholds_unconfirmed ? "text-[rgb(var(--warn))]" : ""
                    }`}
                  >
                    {coverage.thresholds_unconfirmed}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted">Evaluations without scenarios</span>
                  <span
                    className={`tnum ${
                      coverage.evaluations_without_scenarios.length
                        ? "text-[rgb(var(--warn))]"
                        : ""
                    }`}
                  >
                    {coverage.evaluations_without_scenarios.length}
                  </span>
                </div>
                {coverage.uncovered_domains.length > 0 ? (
                  <p className="border-t border-line pt-2 text-xs text-muted">
                    Not covered: {coverage.uncovered_domains.join(", ")}. Those domains will report
                    NOT EVALUATED.
                  </p>
                ) : null}
                <Caveat>
                  {coverage.thresholds_unconfirmed > 0
                    ? "A library default is a suggestion, not a passing bar. The program office confirms each threshold before this plan can be approved."
                    : coverage.note}
                </Caveat>
              </div>
            </Card>
          </div>

          <Card>
            <CardHeader
              title={detail.data.plan.name}
              subtitle={detail.data.plan.rationale ?? undefined}
            />
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2 font-medium">Evaluation</th>
                    <th className="px-4 py-2 font-medium">Layer / domain</th>
                    <th className="px-4 py-2 font-medium">Threshold</th>
                    <th className="px-4 py-2 font-medium">Why it is in this plan</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.data.items.map((item) => {
                    const threshold = { ...item.threshold };
                    const unconfirmed =
                      threshold.source === "library_default_unconfirmed";
                    delete threshold.source;
                    return (
                      <tr key={item.id} className="border-b border-line last:border-0">
                        <td className="px-4 py-2.5">
                          <div className="font-medium">{item.evaluation?.name}</div>
                          <code className="font-mono text-[11px] text-muted">
                            {item.evaluation?.key}
                          </code>
                        </td>
                        <td className="px-4 py-2.5 text-xs text-muted">
                          {item.evaluation?.layer?.replace(/_/g, " ")}
                          <br />
                          {item.evaluation?.domain?.replace(/_/g, " ")}
                        </td>
                        <td className="px-4 py-2.5">
                          <code className="tnum rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 font-mono text-[11px]">
                            {Object.keys(threshold).length
                              ? JSON.stringify(threshold)
                              : "not set"}
                          </code>
                          {unconfirmed ? (
                            <div className="mt-0.5 text-[10px] text-[rgb(var(--warn))]">
                              library default, unconfirmed
                            </div>
                          ) : null}
                        </td>
                        <td className="px-4 py-2.5 text-xs leading-relaxed text-muted">
                          {item.rationale}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}
