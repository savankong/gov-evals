"use client";

import Link from "next/link";
import { use } from "react";

import { SeverityTag, Status } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  CodeBlock,
  Crumbs,
  ErrorNote,
  Hash,
  Spinner,
  Tag,
} from "@/components/ui";
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

/** A labelled block of prose. The label is the only uppercase text on the
 *  page, which is what keeps a wall of evidence scannable. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-2xs uppercase tracking-wider text-faint">{label}</div>
      <div className="mt-1 text-sm leading-relaxed text-ink">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2 last:border-b-0">
      <span className="shrink-0 text-xs text-muted">{label}</span>
      <span className="min-w-0 text-right text-xs text-ink">{value}</span>
    </div>
  );
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
  const reproduced = finding.reproduction?.failed_executions ?? 0;
  const attempts = finding.reproduction?.total_executions ?? 0;

  return (
    <div className="space-y-4">
      <div className="animate-rise">
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            { label: "Findings", href: `/projects/${finding.project_id}/findings` },
            { label: finding.key },
          ]}
        />
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <code className="tnum font-mono text-sm text-faint">{finding.key}</code>
          <h1 className="text-xl font-normal text-ink">{finding.title}</h1>
          <SeverityTag severity={finding.severity} />
          <Tag tone="strong">{finding.status}</Tag>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHead title="What happened" />
            <div className="space-y-3.5 border-t border-line px-4 py-3.5">
              {finding.expected_behavior ? (
                <Field label="Expected behaviour">{finding.expected_behavior}</Field>
              ) : null}
              {finding.actual_behavior ? (
                <Field label="Observed behaviour">{finding.actual_behavior}</Field>
              ) : null}
              {finding.root_cause_hypothesis ? (
                // Labelled a hypothesis in the interface as well as the data,
                // so nobody reads an inference as a diagnosis.
                <Field label="Root cause hypothesis">{finding.root_cause_hypothesis}</Field>
              ) : null}
              <Field label="Reproduction">
                <span className="tnum">
                  {reproduced} of {attempts} executions reproduced this failure
                </span>
                {Array.isArray(finding.reproduction?.scenario_keys) ? (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {finding.reproduction.scenario_keys.slice(0, 10).map((key: string) => (
                      <Tag key={key} mono>
                        {key}
                      </Tag>
                    ))}
                  </div>
                ) : null}
              </Field>
            </div>
          </Card>

          {sample ? (
            <Card>
              <CardHead
                title="Evidence"
                meta={sample.scenario_title ?? sample.scenario_key ?? undefined}
                action={
                  <Link
                    href={`/results/${sample.id}`}
                    className="link-underline text-xs text-muted hover:text-ink"
                  >
                    Full record
                  </Link>
                }
              />
              <div className="space-y-3 border-t border-line px-4 py-3.5">
                <Field label="Input">
                  <CodeBlock>{sample.prompt}</CodeBlock>
                </Field>
                {sample.documents.length > 0 ? (
                  <Field label="Source material">
                    <div className="space-y-1.5">
                      {sample.documents.map((doc, i) => (
                        <CodeBlock key={i}>{String(doc.text ?? "")}</CodeBlock>
                      ))}
                    </div>
                  </Field>
                ) : null}
                <Field label="Output">
                  <CodeBlock>{sample.output}</CodeBlock>
                </Field>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-line pt-3">
                  {sample.judgements.map((judgement, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5">
                      <Status status={judgement.status} />
                      <span className="text-xs text-muted">{judgement.evaluator_key}</span>
                    </span>
                  ))}
                  <span className="ml-auto flex items-center gap-1.5 text-2xs text-faint">
                    record <Hash value={sample.content_hash} />
                  </span>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHead title="Disposition" />
            <div className="border-t border-line">
              <Row label="Owner" value={finding.owner ?? "unassigned"} />
              <Row label="Mitigation" value={finding.mitigation_status} />
              <Row
                label="Retest"
                value={
                  finding.retest_status ??
                  (finding.retest_required ? "required" : "not required")
                }
              />
            </div>
            <div className="border-t border-line px-4 py-3">
              {finding.mitigation ? (
                <p className="text-xs leading-relaxed text-ink">{finding.mitigation}</p>
              ) : (
                <p className="text-xs text-muted">No mitigation has been recorded.</p>
              )}
            </div>
          </Card>

          {finding.framework_refs.length > 0 ? (
            <Card>
              <CardHead title="Framework references" />
              <div className="flex flex-wrap gap-1.5 border-t border-line px-4 py-3">
                {finding.framework_refs.map((ref) => (
                  <Tag key={ref} mono>
                    {ref}
                  </Tag>
                ))}
              </div>
            </Card>
          ) : null}

          {data.linked_risks.length > 0 ? (
            <Card>
              <CardHead title="Linked risks" />
              <div className="border-t border-line">
                {data.linked_risks.map((risk) => (
                  <div key={risk.id} className="border-b border-line px-4 py-2 last:border-b-0">
                    <div className="flex items-baseline gap-2">
                      <code className="font-mono text-2xs text-faint">{risk.key}</code>
                      <span className="min-w-0 text-xs text-ink">{risk.title}</span>
                    </div>
                    <div className="mt-0.5 text-2xs uppercase tracking-wider text-muted">
                      {risk.status}
                    </div>
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
