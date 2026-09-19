"use client";

import Link from "next/link";
import { use } from "react";

import { SeverityChip, StatusChip } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import { Card, CardHeader, Crumbs, ErrorNote, Hash, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Finding, Judgement } from "@/lib/types";

interface FindingDetail {
  finding: Finding;
  classification: string | null;
  results: Array<{
    id: string;
    status: string;
    scenario_key: string | null;
    scenario_title: string | null;
    prompt: string;
    documents: Array<Record<string, unknown>>;
    output: string;
    judgements: Judgement[];
    trace: Array<Record<string, unknown>>;
    content_hash: string;
  }>;
  reproducibility: Record<string, any>;
  linked_risks: Array<{ id: string; key: string; title: string; status: string }>;
}

export default function FindingPage({ params }: { params: Promise<{ findingId: string }> }) {
  const { findingId } = use(params);
  const { data, error, loading } = useResource<FindingDetail>(
    () => api.get<FindingDetail>(`/findings/${findingId}`),
    [findingId],
  );

  useDeclaredClassification(data?.classification);

  if (loading) return <Spinner label="Loading finding" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { finding } = data;
  const sample = data.results[0];

  return (
    <div className="space-y-4">
      <div>
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Findings", href: `/projects/${finding.project_id}/findings` },
            { label: finding.key },
          ]}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
          <code className="tnum font-mono text-sm text-muted">{finding.key}</code>
          <h1 className="text-lg font-semibold tracking-tight">{finding.title}</h1>
          <SeverityChip severity={finding.severity} />
          <span className="rounded border border-line px-2 py-0.5 text-xs text-muted">
            {finding.status}
          </span>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader title="What happened" />
            <dl className="space-y-3 px-4 py-3 text-sm">
              {finding.expected_behavior ? (
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-muted">
                    Expected behaviour
                  </dt>
                  <dd className="mt-0.5 leading-relaxed">{finding.expected_behavior}</dd>
                </div>
              ) : null}
              {finding.actual_behavior ? (
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-muted">
                    Observed behaviour
                  </dt>
                  <dd className="mt-0.5 leading-relaxed">{finding.actual_behavior}</dd>
                </div>
              ) : null}
              {finding.root_cause_hypothesis ? (
                <div>
                  <dt className="text-[11px] uppercase tracking-wider text-muted">
                    Root cause hypothesis
                  </dt>
                  <dd className="mt-0.5 leading-relaxed">{finding.root_cause_hypothesis}</dd>
                </div>
              ) : null}
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-muted">Reproduction</dt>
                <dd className="tnum mt-0.5">
                  {finding.reproduction?.failed_executions ?? 0} of{" "}
                  {finding.reproduction?.total_executions ?? 0} executions reproduced this failure
                </dd>
                {Array.isArray(finding.reproduction?.scenario_keys) ? (
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {finding.reproduction.scenario_keys.slice(0, 10).map((key: string) => (
                      <code
                        key={key}
                        className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 font-mono text-[11px] text-muted"
                      >
                        {key}
                      </code>
                    ))}
                  </dd>
                ) : null}
              </div>
            </dl>
          </Card>

          {sample ? (
            <Card>
              <CardHeader
                title="Evidence"
                subtitle={sample.scenario_title ?? sample.scenario_key ?? undefined}
                action={
                  <Link
                    href={`/results/${sample.id}`}
                    className="text-xs text-muted hover:text-ink hover:underline"
                  >
                    Full record →
                  </Link>
                }
              />
              <div className="space-y-3 px-4 py-3">
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">Input</div>
                  <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-surface p-2.5 text-xs leading-relaxed">
                    {sample.prompt}
                  </pre>
                </div>
                {sample.documents.length > 0 ? (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted">
                      Source material
                    </div>
                    {sample.documents.map((doc, i) => (
                      <pre
                        key={i}
                        className="mt-1 whitespace-pre-wrap rounded border border-line bg-surface p-2.5 text-xs leading-relaxed"
                      >
                        {String(doc.text ?? "")}
                      </pre>
                    ))}
                  </div>
                ) : null}
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">Output</div>
                  <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-surface p-2.5 text-xs leading-relaxed">
                    {sample.output}
                  </pre>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {sample.judgements.map((judgement, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 text-[11px]">
                      <StatusChip status={judgement.status} size="xs" />
                      <span className="text-muted">{judgement.evaluator_key}</span>
                    </span>
                  ))}
                  <span className="ml-auto flex items-center gap-1.5 text-[11px] text-muted">
                    record <Hash value={sample.content_hash} />
                  </span>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Disposition" />
            <dl className="space-y-2 px-4 py-3 text-xs">
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Owner</dt>
                <dd>{finding.owner ?? "unassigned"}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Mitigation</dt>
                <dd className="text-right">{finding.mitigation_status}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">Retest</dt>
                <dd className="text-right">
                  {finding.retest_status ??
                    (finding.retest_required ? "required" : "not required")}
                </dd>
              </div>
            </dl>
            {finding.mitigation ? (
              <div className="border-t border-line px-4 py-3 text-xs leading-relaxed">
                {finding.mitigation}
              </div>
            ) : (
              <div className="border-t border-line px-4 py-3 text-xs text-muted">
                No mitigation has been recorded.
              </div>
            )}
          </Card>

          {finding.framework_refs.length > 0 ? (
            <Card>
              <CardHeader title="Framework references" />
              <div className="flex flex-wrap gap-1.5 px-4 py-3">
                {finding.framework_refs.map((ref) => (
                  <code
                    key={ref}
                    className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 font-mono text-[11px] text-muted"
                  >
                    {ref}
                  </code>
                ))}
              </div>
            </Card>
          ) : null}

          {data.linked_risks.length > 0 ? (
            <Card>
              <CardHeader title="Linked risks" />
              <div className="divide-y divide-line">
                {data.linked_risks.map((risk) => (
                  <div key={risk.id} className="px-4 py-2 text-xs">
                    <code className="font-mono text-muted">{risk.key}</code> {risk.title}
                    <div className="mt-0.5 text-muted">{risk.status}</div>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
