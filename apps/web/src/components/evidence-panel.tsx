"use client";

import { useEffect, useState } from "react";

import { EvaluatorKind, Status } from "@/components/status";
import { SlideOver } from "@/components/shell";
import { Hash, Key, formatMs } from "@/components/ui";
import { api } from "@/lib/api";
import type { ResultDetail } from "@/lib/types";

/**
 * The evidence drill-down.
 *
 * Opens beside the results list rather than replacing it, so a tester reading
 * one failure never loses the set it came from, and can walk the list with the
 * arrow keys without the panel closing. Everything that produced the verdict
 * is here: the exact request, the source material, the output, each
 * evaluator's judgement with its own provenance, the trace, the stored digest
 * and the configuration needed to run it again.
 */
export function EvidencePanel({
  resultId,
  onClose,
  onStep,
}: {
  resultId: string | null;
  onClose: () => void;
  onStep?: (direction: 1 | -1) => void;
}) {
  const [data, setData] = useState<ResultDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!resultId) return;
    let cancelled = false;
    setLoading(true);
    setData(null);
    api
      .get<ResultDetail>(`/results/${resultId}`)
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [resultId]);

  useEffect(() => {
    if (!resultId || !onStep) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        onStep(1);
      } else if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        onStep(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [resultId, onStep]);

  const result = data?.result;
  const scenario = data?.scenario;
  const repro = (data?.reproducibility ?? {}) as Record<string, unknown>;
  const documents = result?.request?.documents ?? [];

  return (
    <SlideOver
      open={Boolean(resultId)}
      onClose={onClose}
      label="Result evidence"
      footer={
        onStep ? (
          <span className="flex items-center gap-1.5">
            <Key>↑</Key>
            <Key>↓</Key>
            <span>step through results</span>
          </span>
        ) : (
          <span />
        )
      }
    >
      {loading ? (
        <div className="space-y-3 p-5">
          <div className="skeleton h-4 w-1/2" />
          <div className="skeleton h-3 w-1/3" />
          <div className="skeleton h-24 w-full" />
          <div className="skeleton h-16 w-full" />
        </div>
      ) : !data || !result ? (
        <div className="p-5 text-sm text-muted">Could not load this result.</div>
      ) : (
        <div className="divide-y divide-line">
          <div className="flex items-center justify-between px-5 py-2.5 text-2xs text-faint">
            <span>{data.evaluation?.name ?? "Evaluation"}</span>
            <span>{formatMs(result.latency_ms)}</span>
          </div>

          <div className="px-5 py-4">
            <div className="text-xs text-muted">{scenario?.key ?? "Scenario"}</div>
            <h2 className="numeral mt-1.5 text-2xl text-ink">
              {scenario?.title ?? "Result"}
            </h2>
            <div className="mt-2.5">
              <Status status={result.status} />
            </div>
          </div>

          <Section title="Request" defaultOpen>
            {result.request?.system_prompt ? (
              <Field label="System prompt">
                <pre className="whitespace-pre-wrap border border-line bg-sunken p-2.5 font-sans text-xs leading-relaxed text-ink-soft">
                  {result.request.system_prompt}
                </pre>
              </Field>
            ) : null}
            <Field label="Prompt">
              <pre className="whitespace-pre-wrap border border-line bg-sunken p-2.5 font-sans text-xs leading-relaxed text-ink">
                {result.request?.prompt ?? "(none)"}
              </pre>
            </Field>
            {documents.length > 0 ? (
              <Field label={`Source material supplied (${documents.length})`}>
                <div className="space-y-2">
                  {documents.map((doc, i) => (
                    <div key={i} className="border border-line bg-sunken p-2.5">
                      <div className="flex items-center gap-2 text-2xs text-faint">
                        <code className="font-mono">{String(doc.source_id ?? `doc-${i}`)}</code>
                        {doc.title ? <span>{String(doc.title)}</span> : null}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">
                        {String(doc.text ?? "")}
                      </p>
                    </div>
                  ))}
                </div>
              </Field>
            ) : null}
          </Section>

          <Section title="Output" defaultOpen>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink">
              {result.response?.text || "(no output)"}
            </pre>
            {result.error ? (
              <p className="mt-2 border-l-2 border-fail pl-2 text-xs text-fail">{result.error}</p>
            ) : null}
          </Section>

          <Section
            title={`Judgements (${result.judgements.length})`}
            meta={`aggregated by ${data.evaluation?.aggregation ?? "rule"}`}
            defaultOpen
          >
            {result.judgements.length === 0 ? (
              <p className="text-sm text-muted">No evaluator produced a judgement.</p>
            ) : (
              <div className="space-y-3">
                {result.judgements.map((judgement, i) => {
                  const meta = judgement.evaluator_metadata ?? {};
                  return (
                    <div key={`${judgement.evaluator_key}-${i}`} className="border border-line p-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <Status status={judgement.status} />
                        <span className="text-sm text-ink">{judgement.evaluator_key}</span>
                        <EvaluatorKind kind={judgement.kind} />
                        {judgement.score !== null ? (
                          <span className="tnum text-2xs text-faint">
                            score {judgement.score.toFixed(3)}
                          </span>
                        ) : null}
                        {judgement.confidence !== null ? (
                          <span className="tnum text-2xs text-faint">
                            conf {judgement.confidence.toFixed(2)}
                          </span>
                        ) : null}
                      </div>
                      {judgement.rationale ? (
                        <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">
                          {judgement.rationale}
                        </p>
                      ) : null}
                      {judgement.kind === "model_based" && meta.judge_model ? (
                        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5 border-t border-line pt-2 text-2xs">
                          <dt className="text-faint">Judge</dt>
                          <dd className="font-mono text-muted">{String(meta.judge_model)}</dd>
                          {meta.rubric ? (
                            <>
                              <dt className="text-faint">Rubric</dt>
                              <dd className="leading-relaxed text-muted">{String(meta.rubric)}</dd>
                            </>
                          ) : null}
                        </dl>
                      ) : null}
                      {Array.isArray(meta.unsupported) && meta.unsupported.length ? (
                        <p className="mt-1.5 text-2xs text-fail">
                          Citations not in the supplied material:{" "}
                          <code className="font-mono">{meta.unsupported.join(", ")}</code>
                        </p>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
            {result.judgements.some((j) => j.kind === "model_based") ? (
              <p className="mt-3 border-l border-line pl-3 text-xs leading-relaxed text-muted">
                A model-based judgement is advisory evidence, recorded with the judge model and
                rubric that produced it. It is not ground truth and does not outrank the
                deterministic or human judgements beside it.
              </p>
            ) : null}
          </Section>

          {scenario ? (
            <Section title="Scenario expectations">
              {scenario.expected_behavior.length > 0 ? (
                <Field label="Expected">
                  <ul className="space-y-1">
                    {scenario.expected_behavior.map((item) => (
                      <li key={item} className="flex gap-2 text-xs leading-relaxed">
                        <span className="mt-[6px] h-[5px] w-[5px] shrink-0 bg-pass" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </Field>
              ) : null}
              {scenario.prohibited_behavior.length > 0 ? (
                <Field label="Prohibited">
                  <ul className="space-y-1">
                    {scenario.prohibited_behavior.map((item) => (
                      <li key={item} className="flex gap-2 text-xs leading-relaxed">
                        <span className="mt-[6px] h-[5px] w-[5px] shrink-0 bg-fail" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </Field>
              ) : null}
            </Section>
          ) : null}

          {result.trace.length > 0 ? (
            <Section title={`Execution trace (${result.trace.length})`}>
              <ol className="divide-y divide-line border border-line">
                {result.trace.map((step, i) => (
                  <li key={i} className="flex gap-3 px-2.5 py-1.5 text-2xs">
                    <span className="tnum w-4 shrink-0 text-faint">{i + 1}</span>
                    <span className="w-20 shrink-0 text-ink">{String(step.step ?? "step")}</span>
                    <span className="min-w-0 flex-1 break-words text-muted">
                      {step.tool ? (
                        <code className="font-mono text-ink-soft">{String(step.tool)}</code>
                      ) : null}{" "}
                      {step.detail
                        ? String(step.detail)
                        : step.input
                          ? JSON.stringify(step.input).slice(0, 160)
                          : ""}
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-2xs text-faint">
                Observable steps only. Hidden model reasoning is not requested or stored.
              </p>
            </Section>
          ) : null}

          <Section title="Evidence and reproducibility">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-2xs">
              <dt className="text-faint">Result digest</dt>
              <dd className="text-right">
                <Hash value={result.content_hash} length={20} />
              </dd>
              {data.evidence.map((item) => (
                <>
                  <dt key={`${item.id}-k`} className="text-faint">
                    {item.kind.replace(/_/g, " ")}
                  </dt>
                  <dd key={`${item.id}-v`} className="text-right">
                    <Hash value={item.sha256} length={20} />
                  </dd>
                </>
              ))}
              <dt className="text-faint">Model</dt>
              <dd className="text-right text-muted">{String(repro.model_name ?? "—")}</dd>
              <dt className="text-faint">Connector</dt>
              <dd className="text-right text-muted">
                {String((repro.connector as Record<string, unknown>)?.connector_type ?? "—")}
              </dd>
              <dt className="text-faint">Random seed</dt>
              <dd className="text-right text-muted">{String(repro.random_seed ?? "not set")}</dd>
              <dt className="text-faint">Config hash</dt>
              <dd className="text-right">
                <Hash value={String(repro.system_config_hash ?? "")} length={20} />
              </dd>
            </dl>
          </Section>

          {data.human_reviews.length > 0 ? (
            <Section title={`Human reviews (${data.human_reviews.length})`}>
              <div className="space-y-2">
                {data.human_reviews.map((review) => (
                  <div key={review.id} className="border border-line p-2.5 text-xs">
                    <div className="flex items-center gap-2">
                      <Status status={review.status} />
                      <span className="text-muted">{review.reviewer_label ?? "reviewer"}</span>
                    </div>
                    {review.comments ? <p className="mt-1">{review.comments}</p> : null}
                  </div>
                ))}
              </div>
            </Section>
          ) : null}
        </div>
      )}
    </SlideOver>
  );
}

function Section({
  title,
  meta,
  children,
  defaultOpen = false,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-2.5 text-left transition-colors duration-150 hover:bg-sunken"
      >
        <span className="text-sm text-ink">
          {title}
          {meta ? <span className="ml-2 text-xs text-faint">{meta}</span> : null}
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 16 16"
          className={`text-faint transition-transform duration-200 ease-out ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.25" />
        </svg>
      </button>
      {open ? <div className="animate-fade space-y-3 px-5 pb-4">{children}</div> : null}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-2xs uppercase tracking-wider text-faint">{label}</div>
      {children}
    </div>
  );
}
