"use client";

import Link from "next/link";
import { use } from "react";

import { EvaluatorKindBadge, StatusChip } from "@/components/status";
import { useDeclaredClassification, useResource } from "@/components/shell";
import {
  Card,
  CardHeader,
  Caveat,
  Crumbs,
  ErrorNote,
  Hash,
  Spinner,
  formatMs,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { ResultDetail } from "@/lib/types";

/**
 * The drill-down that answers "why should I believe this?".
 * Everything that produced the verdict is on this page: the exact request, the
 * source material, the output, each evaluator's judgement with its own
 * provenance, the execution trace, the stored evidence digest and the
 * configuration needed to run it again.
 */
export default function ResultPage({ params }: { params: Promise<{ resultId: string }> }) {
  const { resultId } = use(params);
  const { data, error, loading } = useResource<ResultDetail>(
    () => api.get<ResultDetail>(`/results/${resultId}`),
    [resultId],
  );

  useDeclaredClassification((data as { classification?: string | null } | null)?.classification);

  if (loading) return <Spinner label="Loading evidence" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const { result, run, evaluation, system_version: systemVersion, scenario } = data;
  const documents = result.request?.documents ?? [];
  const repro = data.reproducibility as Record<string, any>;

  return (
    <div className="space-y-4">
      <div>
        <Crumbs
          items={[
            { label: "Portfolio", href: "/" },
            ...(run ? [{ label: "Run", href: `/runs/${run.id}` }] : []),
            { label: "Result" },
          ]}
        />
        <div className="mt-1.5 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight">
            {scenario?.title ?? "Scenario result"}
          </h1>
          <StatusChip status={result.status} />
          {evaluation ? (
            <span className="text-sm text-muted">{evaluation.name}</span>
          ) : null}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader title="Request" subtitle="Exactly what the system was given" />
            <div className="space-y-3 px-4 py-3">
              {result.request?.system_prompt ? (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">
                    System prompt
                  </div>
                  <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-surface p-2.5 text-xs leading-relaxed">
                    {result.request.system_prompt}
                  </pre>
                </div>
              ) : null}
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted">Prompt</div>
                <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-surface p-2.5 text-xs leading-relaxed">
                  {result.request?.prompt ?? "(none)"}
                </pre>
              </div>

              {documents.length > 0 ? (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted">
                    Source material supplied ({documents.length})
                  </div>
                  <div className="mt-1 space-y-2">
                    {documents.map((doc, i) => (
                      <div key={i} className="rounded border border-line bg-surface p-2.5">
                        <div className="flex items-center gap-2 text-[11px] text-muted">
                          <code className="font-mono">{String(doc.source_id ?? `doc-${i}`)}</code>
                          {doc.title ? <span>{String(doc.title)}</span> : null}
                        </div>
                        <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">
                          {String(doc.text ?? "")}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Output"
              subtitle={`${formatMs(result.latency_ms)}${
                result.repetition > 1 ? ` · repetition ${result.repetition}` : ""
              }`}
            />
            <pre className="whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed">
              {result.response?.text || "(no output)"}
            </pre>
            {result.error ? (
              <div className="border-t border-line px-4 py-2">
                <ErrorNote message={result.error} />
              </div>
            ) : null}
          </Card>

          <Card>
            <CardHeader
              title="Judgements"
              subtitle={`${result.judgements.length} evaluator(s), aggregated by ${
                evaluation?.aggregation ?? "rule"
              }`}
            />
            <div className="divide-y divide-line">
              {result.judgements.length === 0 ? (
                <p className="px-4 py-3 text-sm text-muted">
                  No evaluator produced a judgement for this result.
                </p>
              ) : (
                result.judgements.map((judgement, i) => {
                  const meta = judgement.evaluator_metadata ?? {};
                  return (
                    <div key={`${judgement.evaluator_key}-${i}`} className="px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusChip status={judgement.status} />
                        <span className="text-sm font-medium">{judgement.evaluator_key}</span>
                        <EvaluatorKindBadge kind={judgement.kind} />
                        {judgement.score !== null ? (
                          <span className="tnum text-xs text-muted">
                            score {judgement.score.toFixed(3)}
                          </span>
                        ) : null}
                        {judgement.confidence !== null ? (
                          <span className="tnum text-xs text-muted">
                            confidence {judgement.confidence.toFixed(2)}
                          </span>
                        ) : null}
                      </div>

                      {judgement.rationale ? (
                        <p className="mt-1.5 text-sm leading-relaxed">{judgement.rationale}</p>
                      ) : null}
                      {judgement.error ? (
                        <p className="mt-1.5 text-sm text-[rgb(var(--fail))]">{judgement.error}</p>
                      ) : null}

                      {/* A model judgement carries its own provenance, shown
                          inline so the reader can weigh it. */}
                      {judgement.kind === "model_based" && meta.judge_model ? (
                        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 rounded border border-line bg-surface px-2.5 py-2 text-[11px]">
                          <dt className="text-muted">Judge model</dt>
                          <dd className="font-mono">{String(meta.judge_model)}</dd>
                          {meta.temperature !== undefined ? (
                            <>
                              <dt className="text-muted">Temperature</dt>
                              <dd className="tnum">{String(meta.temperature)}</dd>
                            </>
                          ) : null}
                          {meta.rubric ? (
                            <>
                              <dt className="text-muted">Rubric</dt>
                              <dd className="leading-relaxed">{String(meta.rubric)}</dd>
                            </>
                          ) : null}
                        </dl>
                      ) : null}

                      {Array.isArray(meta.matched_patterns) && meta.matched_patterns.length ? (
                        <p className="mt-1.5 text-[11px] text-muted">
                          Matched: <code className="font-mono">{meta.matched_patterns.join(", ")}</code>
                        </p>
                      ) : null}
                      {Array.isArray(meta.unsupported) && meta.unsupported.length ? (
                        <p className="mt-1.5 text-[11px] text-[rgb(var(--fail))]">
                          Citations not in the supplied material:{" "}
                          <code className="font-mono">{meta.unsupported.join(", ")}</code>
                        </p>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>

            {result.judgements.some((j) => j.kind === "model_based") ? (
              <div className="border-t border-line px-4 py-2.5">
                <Caveat>
                  A model-based judgement is advisory evidence, recorded with the judge model and
                  rubric that produced it. It is not ground truth and does not outrank the
                  deterministic or human judgements beside it.
                </Caveat>
              </div>
            ) : null}
          </Card>

          {result.trace.length > 0 ? (
            <Card>
              <CardHeader
                title="Execution trace"
                subtitle="Observable steps. Hidden model reasoning is not requested or stored."
              />
              <ol className="divide-y divide-line">
                {result.trace.map((step, i) => (
                  <li key={i} className="flex gap-3 px-4 py-2 text-xs">
                    <span className="tnum w-5 shrink-0 text-muted">{i + 1}</span>
                    <span className="w-24 shrink-0 font-medium">{String(step.step ?? "step")}</span>
                    <span className="min-w-0 flex-1 break-words text-muted">
                      {step.tool ? (
                        <code className="font-mono text-ink">{String(step.tool)}</code>
                      ) : null}{" "}
                      {step.detail
                        ? String(step.detail)
                        : step.input
                          ? JSON.stringify(step.input).slice(0, 200)
                          : step.output
                            ? String(step.output).slice(0, 200)
                            : ""}
                    </span>
                  </li>
                ))}
              </ol>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          {scenario ? (
            <Card>
              <CardHeader title="Scenario" subtitle={scenario.key} />
              <div className="space-y-3 px-4 py-3 text-sm">
                {scenario.expected_behavior.length > 0 ? (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted">
                      Expected behaviour
                    </div>
                    <ul className="mt-1 space-y-1">
                      {scenario.expected_behavior.map((item) => (
                        <li key={item} className="flex gap-2 text-xs leading-relaxed">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--pass))]" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {scenario.prohibited_behavior.length > 0 ? (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted">
                      Prohibited behaviour
                    </div>
                    <ul className="mt-1 space-y-1">
                      {scenario.prohibited_behavior.map((item) => (
                        <li key={item} className="flex gap-2 text-xs leading-relaxed">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--fail))]" />
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {scenario.rubric ? (
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-muted">Rubric</div>
                    <p className="mt-1 text-xs leading-relaxed">{scenario.rubric}</p>
                  </div>
                ) : null}
                <div className="flex items-center gap-2 border-t border-line pt-2 text-[11px] text-muted">
                  Scenario version hash <Hash value={scenario.content_hash} />
                </div>
              </div>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Evidence" subtitle="Stored, hashed, retrievable" />
            <div className="space-y-2 px-4 py-3 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted">Result digest</span>
                <Hash value={result.content_hash} length={16} />
              </div>
              {data.evidence.map((item) => (
                <div key={item.id} className="border-t border-line pt-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted">{item.kind.replace(/_/g, " ")}</span>
                    <Hash value={item.sha256} length={16} />
                  </div>
                  <div className="tnum mt-0.5 text-[11px] text-muted">
                    {item.size_bytes.toLocaleString()} bytes
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Reproducibility" subtitle="What is needed to run this again" />
            <dl className="space-y-1 px-4 py-3 text-[11px]">
              {[
                ["System version", systemVersion?.label],
                ["Model", repro?.model_name],
                ["Model version", repro?.model_version],
                ["Connector", repro?.connector?.connector_type],
                ["Random seed", repro?.random_seed ?? "not set"],
                ["Evaluation", repro?.evaluation_key],
                ["Platform", repro?.platform_version],
                ["Python", repro?.python_version],
              ].map(([label, value]) => (
                <div key={String(label)} className="flex justify-between gap-3">
                  <dt className="text-muted">{label}</dt>
                  <dd className="truncate text-right">{value ? String(value) : "—"}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3 border-t border-line pt-1.5">
                <dt className="text-muted">Config hash</dt>
                <dd>
                  <Hash value={repro?.system_config_hash} />
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">Prompt hash</dt>
                <dd>
                  <Hash value={repro?.system_prompt_hash} />
                </dd>
              </div>
            </dl>
          </Card>

          {data.human_reviews.length > 0 ? (
            <Card>
              <CardHeader title="Human reviews" />
              <div className="divide-y divide-line">
                {data.human_reviews.map((review) => (
                  <div key={review.id} className="px-4 py-2.5 text-xs">
                    <div className="flex items-center gap-2">
                      <StatusChip status={review.status} size="xs" />
                      <span className="text-muted">{review.reviewer_label ?? "reviewer"}</span>
                      {review.confidence !== null ? (
                        <span className="tnum text-muted">
                          confidence {review.confidence.toFixed(2)}
                        </span>
                      ) : null}
                    </div>
                    {review.comments ? <p className="mt-1">{review.comments}</p> : null}
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
