"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";

import { Choice, FormActions, Label, Lines, TextArea } from "@/components/forms";
import { useResource } from "@/components/shell";
import {
  Button,
  Caveat,
  Card,
  CardHead,
  Crumbs,
  Disclosure,
  ErrorNote,
  Hash,
  Note,
  PageTitle,
  Spinner,
  Tag,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { tourSeed, tourSignal, useTourCommand } from "@/tour/signal";

interface Problem {
  scenario_key: string;
  title: string;
  task: string | null;
  context: string | null;
  prompt: string | null;
  documents: Array<{ source_id: string | null; title: string | null; text: string | null }>;
}

interface ModelAnswer {
  result_id: string;
  text: string | null;
  confidence: number | null;
  confidence_source: string | null;
  created_at: string;
}

interface CaptureTask {
  scenario_id: string;
  knowledge_area: string | null;
  required_expertise: string[];
  viewer_is_qualified: boolean;
  has_profile: boolean;
  problem: Problem;
  model: { failed: number; confident_wrong: number; outcome: string };
  model_answers: ModelAnswer[];
  confident_at: number;
}

interface Profile {
  disciplines: string[];
}

interface Trace {
  id: string;
  qualified: boolean;
  qualification_note: string | null;
  classification: string;
  content_hash: string;
  steps: unknown[];
}

interface Step {
  text: string;
  basis: string;
}

const CONFIDENCE = [
  { value: "", label: "Not stated" },
  { value: "0.5", label: "Could go either way" },
  { value: "0.7", label: "Fairly sure" },
  { value: "0.9", label: "Sure" },
  { value: "0.99", label: "Certain" },
];

function useElapsed(): number {
  const started = useRef(Date.now());
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(
      () => setSeconds(Math.round((Date.now() - started.current) / 1000)),
      15_000,
    );
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}

function StepEditor({
  steps,
  onChange,
}: {
  steps: Step[];
  onChange: (steps: Step[]) => void;
}) {
  const field =
    "w-full border border-line bg-panel px-2.5 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-faint focus:border-line-strong";
  const set = (index: number, patch: Partial<Step>) =>
    onChange(steps.map((step, i) => (i === index ? { ...step, ...patch } : step)));

  return (
    <div className="space-y-3">
      {steps.map((step, index) => (
        <div key={index} className="flex gap-3">
          <span className="tnum w-5 shrink-0 pt-2 text-right font-mono text-xs text-faint">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <textarea
              aria-label={`Step ${index + 1}`}
              rows={2}
              value={step.text}
              onChange={(event) => set(index, { text: event.target.value })}
              placeholder={
                index === 0
                  ? "What you checked first, and why it comes first."
                  : "What you did next, and what it told you."
              }
              className={`py-2 leading-relaxed ${field}`}
            />
            <div className="flex items-center gap-2">
              <input
                aria-label={`What step ${index + 1} rests on`}
                value={step.basis}
                onChange={(event) => set(index, { basis: event.target.value })}
                placeholder="Rests on — e.g. FAR 15.306(d)(3), the solicitation's Section M"
                className={`h-7 font-mono text-xs ${field}`}
              />
              {steps.length > 1 ? (
                <Button
                  variant="ghost"
                  onClick={() => onChange(steps.filter((_, i) => i !== index))}
                >
                  Remove
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      ))}
      <div className="pl-8">
        <Button onClick={() => onChange([...steps, { text: "", basis: "" }])}>Add a step</Button>
      </div>
    </div>
  );
}

export default function SolvePage({ params }: { params: Promise<{ scenarioId: string }> }) {
  const { scenarioId } = use(params);
  const task = useResource(() => api.get<CaptureTask>(`/capture/tasks/${scenarioId}`), [scenarioId]);
  const profile = useResource(() => api.get<Profile | null>("/expert-profiles/me"), []);
  const vocabulary = useResource(
    () => api.get<{ disciplines: Array<{ key: string; label: string }> }>("/disciplines"),
    [],
  );
  const labelFor = (key: string) =>
    vocabulary.data?.disciplines.find((d) => d.key === key)?.label ?? key.replace(/_/g, " ");
  const elapsed = useElapsed();

  const [steps, setSteps] = useState<Step[]>([{ text: "", basis: "" }]);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [confidence, setConfidence] = useState("");
  const [expertise, setExpertise] = useState("");
  const [pii, setPii] = useState(false);
  const [openDocs, setOpenDocs] = useState<Record<number, boolean>>({});
  // The model's answer is closed until asked for. Opening it is recorded,
  // because a trace written after reading the wrong answer is a correction,
  // not an independent solution, and the customer should know which.
  const [shownAnswer, setShownAnswer] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Trace | null>(null);

  // A presenter who jumps past "record the trace" lands on the recorded panel.
  useEffect(() => {
    const seeded = tourSeed<Trace>(`solve.saved:${scenarioId}`);
    if (seeded) setSaved(seeded);
  }, [scenarioId]);

  // "Use a worked example" in the product tour.
  useTourCommand<{ steps: Step[]; answer: string; sources: string[] }>(
    "solve.fill-example",
    (example) => {
      setSteps(example.steps.map((step) => ({ text: step.text, basis: step.basis })));
      setAnswer(example.answer);
      setSources(example.sources);
      setConfidence("0.9");
    },
  );

  // The tour's "write your first step" is done once a step says what it rests
  // on. Reported after a pause in typing, so the tour does not move on mid-word.
  const firstStepWritten = Boolean(steps[0]?.text.trim() && steps[0]?.basis.trim());
  useEffect(() => {
    if (!firstStepWritten) return;
    const timer = window.setTimeout(() => tourSignal("solve.step-written"), 700);
    return () => window.clearTimeout(timer);
  }, [firstStepWritten, steps]);

  const disciplines = profile.data?.disciplines ?? [];
  useEffect(() => {
    if (!expertise && task.data) {
      const match = disciplines.find((d) => task.data!.required_expertise.includes(d));
      if (match) setExpertise(match);
    }
  }, [disciplines, task.data, expertise]);

  const filled = steps.filter((s) => s.text.trim());
  const ready = filled.length > 0 && answer.trim().length > 0;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const trace = await api.post<Trace>("/reasoning-traces", {
        scenario_id: scenarioId,
        result_id: shownAnswer,
        steps: filled.map((s) => ({ text: s.text.trim(), basis: s.basis.trim() || null })),
        final_answer: answer.trim(),
        sources,
        time_spent_seconds: elapsed || null,
        confidence: confidence ? Number(confidence) : null,
        expertise: expertise || null,
        contains_pii: pii,
      });
      setSaved(trace);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the trace.");
    } finally {
      setSubmitting(false);
    }
  };

  if (task.loading && !task.data) return <Spinner label="Loading the problem" />;
  if (task.error || !task.data) {
    return (
      <ErrorNote
        message={task.error ?? "Could not load this problem."}
        status={task.status}
        onRetry={task.reload}
      />
    );
  }

  const data = task.data;
  const problem = data.problem;

  return (
    <div className="space-y-4">
      <Crumbs items={[{ label: "Capture", href: "/capture" }, { label: problem.title }]} />
      <PageTitle
        title={problem.title}
        subtitle={
          <>
            {data.knowledge_area ?? "Knowledge area not declared"}
            <span className="text-faint"> · {Math.max(1, Math.round(elapsed / 60))} min on this problem</span>
          </>
        }
      />

      {!data.viewer_is_qualified ? (
        <Note tone="warn">
          {data.has_profile
            ? "Your profile does not cover what this problem requires. Your trace will be recorded as an opinion and will not be delivered as expert data."
            : "You have no expert profile, so your trace will be recorded as an opinion and will not be delivered as expert data."}
        </Note>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="space-y-4">
          <Card>
            <CardHead title="The problem" subtitle={problem.task ?? undefined} />
            <div className="space-y-3 border-t border-line px-4 py-3 text-sm">
              {problem.prompt ? (
                <p className="whitespace-pre-wrap leading-relaxed text-ink">{problem.prompt}</p>
              ) : null}
              {problem.context ? (
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted">
                  {problem.context}
                </p>
              ) : null}
              {problem.documents.length ? (
                <div className="space-y-2">
                  <div className="text-2xs uppercase tracking-wider text-faint">
                    Material supplied
                  </div>
                  {problem.documents.map((doc, index) => (
                    <Disclosure
                      key={index}
                      tour={`solve.document:${index}`}
                      open={!!openDocs[index]}
                      onToggle={() => {
                        if (!openDocs[index]) tourSignal("solve.document:opened");
                        setOpenDocs((o) => ({ ...o, [index]: !o[index] }));
                      }}
                      summary={
                        <span className="text-sm text-ink">
                          {doc.title ?? "Untitled document"}
                          {doc.source_id ? (
                            <span className="ml-2 font-mono text-2xs text-faint">{doc.source_id}</span>
                          ) : null}
                        </span>
                      }
                    >
                      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted">
                        {doc.text}
                      </p>
                    </Disclosure>
                  ))}
                </div>
              ) : null}
              {data.required_expertise.length ? (
                <div className="flex flex-wrap items-center gap-1">
                  <span className="text-2xs uppercase tracking-wider text-faint">Needs</span>
                  {data.required_expertise.map((key) => (
                    <Tag key={key}>{labelFor(key)}</Tag>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>

          {data.model_answers.length ? (
            <Card>
              <div className="px-4 py-3">
                <Disclosure
                  tour="solve.model-answer"
                  open={shownAnswer !== null}
                  onToggle={() => {
                    if (shownAnswer === null) tourSignal("solve.model-answer:opened");
                    setShownAnswer(shownAnswer === null ? data.model_answers[0].result_id : null);
                  }}
                  summary={
                    <span className="text-sm text-ink">
                      The model&apos;s answer
                      <span className="ml-2 text-xs text-muted">
                        judged wrong {data.model.failed}×
                        {data.model.confident_wrong
                          ? `, ${data.model.confident_wrong} confidently`
                          : ""}
                      </span>
                    </span>
                  }
                >
                  <div className="mt-2 space-y-2">
                    <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted">
                      {data.model_answers[0].text ?? "No text returned."}
                    </p>
                    <p className="text-2xs text-faint">
                      Confidence{" "}
                      {data.model_answers[0].confidence === null
                        ? "unknown"
                        : `${data.model_answers[0].confidence.toFixed(2)} (${
                            data.model_answers[0].confidence_source
                          })`}
                    </p>
                  </div>
                </Disclosure>
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  {shownAnswer
                    ? "Your trace will be recorded as a correction of this answer."
                    : "Closed so it does not anchor you. Opening it records your trace as a correction rather than an independent solution."}
                </p>
              </div>
            </Card>
          ) : null}
        </div>

        <Card>
          {saved ? (
            <div className="space-y-3 px-4 py-4">
              <p className="text-sm text-ink">Trace recorded.</p>
              <Note tone={saved.qualified ? "muted" : "warn"}>
                {saved.qualified ? "Counts as expert data. " : "Recorded as an opinion; not delivered. "}
                {saved.qualification_note}
              </Note>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                <span>{saved.steps.length} steps</span>
                <span>Marked {saved.classification}</span>
                <span>
                  SHA-256 <Hash value={saved.content_hash} length={16} />
                </span>
              </div>
              <Link href="/capture">
                <Button variant="primary">Next problem</Button>
              </Link>
            </div>
          ) : (
            <>
              <CardHead
                title="Your reasoning"
                subtitle="Write it the way you would explain it to a new contracting officer: each step, and what it rests on."
              />
              <div className="space-y-4 border-t border-line px-4 py-3">
                <div data-tour="solve.steps">
                  <StepEditor steps={steps} onChange={setSteps} />
                </div>
                <TextArea
                  id="answer"
                  label="Your answer"
                  value={answer}
                  onChange={setAnswer}
                  rows={4}
                  required
                />
                <Lines
                  id="sources"
                  label="Sources you relied on"
                  value={sources}
                  onChange={setSources}
                  placeholder={"FAR 15.305(a)\nGAO B-421234, 2023"}
                  rows={2}
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Choice
                    id="confidence"
                    label="How sure you are"
                    value={confidence}
                    onChange={setConfidence}
                    options={CONFIDENCE}
                  />
                  <Choice
                    id="expertise"
                    label="Solving as"
                    value={expertise}
                    onChange={setExpertise}
                    options={[
                      { value: "", label: "Not stated" },
                      ...disciplines.map((d) => ({ value: d, label: labelFor(d) })),
                    ]}
                  />
                </div>
                <div className="flex items-start gap-2">
                  <input
                    id="pii"
                    type="checkbox"
                    checked={pii}
                    onChange={(event) => setPii(event.target.checked)}
                    className="mt-0.5"
                  />
                  <Label htmlFor="pii">Contains personal information</Label>
                </div>
                <div data-tour="solve.record">
                  <FormActions
                    onSubmit={submit}
                    submitting={submitting}
                    disabled={!ready}
                    error={error}
                    submitLabel="Record trace"
                    busyLabel="Recording…"
                  />
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      <Caveat>
        The reference answer is not shown here: an expert handed the answer is checking it, not
        solving the problem. The trace is marked at least as strictly as the problem, timed from
        when this page opened, and hashed over the problem as you saw it.
      </Caveat>
    </div>
  );
}
