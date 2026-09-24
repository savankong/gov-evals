"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useResource } from "@/components/shell";
import { Button, Card, CardHead, Caveat, ErrorNote, Key, Note, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

export interface OnboardingStep {
  key: string;
  title: string;
  detail: string;
  done: boolean;
  evidence: string;
  href: string | null;
  command: string | null;
  blocked: string | null;
}

export interface Onboarding {
  steps: OnboardingStep[];
  done: number;
  total: number;
  complete: boolean;
  first_run: boolean;
  project_id: string | null;
  note: string;
}

export function useOnboarding() {
  return useResource<Onboarding>(() => api.get("/onboarding"));
}

/* ------------------------------------------------------------------ *
 * The primer
 * ------------------------------------------------------------------ */

const PRIMER_KEY = "aegis.primer.seen";

/**
 * What the product is, before what to click.
 *
 * Three of these five panels are the rules the software actually enforces,
 * because someone who does not know them will read a `not_evaluated` as a bug
 * and a missing composite score as an omission. Teaching them first is cheaper
 * than explaining them afterwards.
 */
const PANELS = [
  {
    title: "One question",
    body: "Aegis Eval answers: what evidence justifies using this AI for this mission, under these conditions? A model can score well on a public benchmark and still fail on unfamiliar mission data, under adversarial input, or in the hands of an operator who trusts it more than the evidence supports.",
    note: "Everything in the product exists to answer that question, or to refuse to.",
  },
  {
    title: "There is no overall score",
    body: "Results roll up per dimension — performance, robustness, security, human factors, integration, Responsible AI. You will not find a composite trust score anywhere, because weighting those dimensions against mission requirements is a programme decision, not ours.",
    note: "If you are looking for one number, that absence is the feature.",
  },
  {
    title: "Unknown is a valid result",
    body: "An untested property reports NOT EVALUATED. A run that produced no judgement never counts as a pass, and a threshold like max_failures: 0 cannot be satisfied by a run that evaluated nothing. A gate with an unmeasured criterion is undetermined — the CLI has its own exit code for it.",
    note: "An empty queue is not the same as a system that passed.",
  },
  {
    title: "Evidence over claims",
    body: "Every score resolves to the exact request, the source material supplied, the output, the execution trace, each evaluator's judgement with its own provenance, and a SHA-256 digest of the stored record. A model-based judgement is advisory and is recorded with the judge and rubric that produced it.",
    note: "It is never presented as ground truth, and never outranks the human or deterministic judgements beside it.",
  },
  {
    title: "How the work goes",
    body: "Mission profile → system version → evaluation plan → campaign → evidence → findings → assurance case. The checklist on your portfolio tracks where you actually are, derived from what is in the database rather than from steps you have ticked off.",
    note: "You cannot mark a step done without doing it. That is the same rule as everything above.",
  },
];

export function Primer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const last = index === PANELS.length - 1;

  const close = useCallback(() => {
    try {
      window.localStorage.setItem(PRIMER_KEY, "true");
    } catch {
      /* per-viewer convenience; it will simply show again */
    }
    onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) setIndex(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "ArrowRight" && !last) setIndex((i) => i + 1);
      if (event.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, last, close]);

  const panel = PANELS[index];

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.14 }}
        >
          <div className="absolute inset-0 bg-ink/20 backdrop-blur-[1px]" onClick={close} aria-hidden />
          <motion.div
            role="dialog"
            aria-label="Welcome to Aegis Eval"
            aria-describedby="primer-body"
            className="relative w-full max-w-[32.5rem] border border-line-strong bg-panel"
            initial={{ opacity: 0, y: 8, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.995 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="px-5 pb-4 pt-5">
              <div className="text-2xs uppercase tracking-wider text-faint">
                {index + 1} of {PANELS.length}
              </div>
              <h2 className="mt-1.5 font-serif text-2xl text-ink">{panel.title}</h2>
              <p id="primer-body" className="mt-2.5 text-sm leading-relaxed text-ink-soft">
                {panel.body}
              </p>
              <Note className="mt-2.5">{panel.note}</Note>
            </div>

            <div className="flex items-center justify-between border-t border-line px-5 py-3">
              <div className="flex items-center gap-1.5" aria-hidden>
                {PANELS.map((p, i) => (
                  <button
                    key={p.title}
                    onClick={() => setIndex(i)}
                    aria-label={`Go to panel ${i + 1}`}
                    className={`h-[5px] w-[5px] transition-colors duration-150 ${
                      i === index ? "bg-ink" : "bg-line-strong hover:bg-muted"
                    }`}
                  />
                ))}
              </div>
              <div className="flex items-center gap-2">
                {/* Skip is always available. A primer you cannot leave is a
                    tollbooth, not an introduction. */}
                <Button variant="ghost" onClick={close}>
                  {last ? "Close" : "Skip"}
                </Button>
                {index > 0 ? (
                  <Button onClick={() => setIndex((i) => i - 1)}>Back</Button>
                ) : null}
                {last ? (
                  <Button variant="primary" onClick={close}>
                    Start
                  </Button>
                ) : (
                  <Button variant="primary" onClick={() => setIndex((i) => i + 1)}>
                    Next
                  </Button>
                )}
              </div>
            </div>

            <div className="flex items-center justify-end gap-1.5 border-t border-line px-5 py-2 text-2xs text-faint">
              <Key>←</Key>
              <Key>→</Key>
              <span className="mr-1">move</span>
              <Key>esc</Key>
              <span>close</span>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/** Whether this viewer has seen the primer. Read once, on the client. */
export function usePrimer(): { show: boolean; open: () => void; close: () => void } {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(PRIMER_KEY) !== "true") setShow(true);
    } catch {
      /* storage unavailable: show it, which is the safe default */
      setShow(true);
    }
  }, []);
  return {
    show,
    open: () => setShow(true),
    close: () => setShow(false),
  };
}

/* ------------------------------------------------------------------ *
 * The checklist
 * ------------------------------------------------------------------ */

function StepRow({ step, index }: { step: OnboardingStep; index: number }) {
  const [showCommand, setShowCommand] = useState(false);

  return (
    <div className="flex gap-3 border-t border-line px-4 py-3">
      <div
        className={`mt-px grid h-5 w-5 shrink-0 place-items-center border text-2xs tnum ${
          step.done ? "border-pass/50 text-pass" : "border-line-strong text-faint"
        }`}
        aria-hidden
      >
        {step.done ? "✓" : index + 1}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <p className={`text-sm ${step.done ? "text-muted" : "text-ink"}`}>{step.title}</p>
          <span className="shrink-0 text-2xs text-faint">{step.evidence}</span>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted">{step.detail}</p>

        {!step.done ? (
          <div className="mt-2">
            {step.href ? (
              <Link href={step.href}>
                <Button>Go</Button>
              </Link>
            ) : step.blocked ? (
              // The screen exists; it is just not reachable yet. Saying "there
              // is no screen for this" here would send someone hunting for a
              // gap that is not there.
              <p className="text-xs text-faint">{step.blocked}</p>
            ) : step.command ? (
              <>
                <Button variant="ghost" onClick={() => setShowCommand((v) => !v)}>
                  {showCommand ? "Hide the request" : "There is no screen for this yet"}
                </Button>
                {showCommand ? (
                  <pre className="mt-1.5 overflow-x-auto border border-line bg-sunken px-2.5 py-2 font-mono text-xs text-ink-soft">
                    {step.command}
                  </pre>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function GettingStarted({
  data,
  onOpenPrimer,
}: {
  data: Onboarding;
  onOpenPrimer?: () => void;
}) {
  const pct = data.total ? Math.round((data.done / data.total) * 100) : 0;

  return (
    <Card>
      <CardHead
        title={data.first_run ? "Start here" : "Getting started"}
        subtitle={
          data.first_run
            ? "Nothing has been evaluated on this account yet. These are the steps, in the order they are done."
            : "Where this account actually is, derived from the database rather than from steps ticked off."
        }
        action={
          onOpenPrimer ? (
            <Button variant="ghost" onClick={onOpenPrimer}>
              How this works
            </Button>
          ) : null
        }
      />

      <div className="px-4 pb-3">
        <div className="flex items-baseline justify-between">
          <span className="text-2xs uppercase tracking-wider text-faint">Progress</span>
          <span className="tnum text-sm text-ink">
            {data.done} of {data.total}
          </span>
        </div>
        <div className="mt-1.5 h-[3px] w-full bg-sunken" role="presentation">
          <motion.div
            className="h-full bg-accent"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          />
        </div>
      </div>

      {data.steps.map((step, index) => (
        <StepRow key={step.key} step={step} index={index} />
      ))}

      <div className="border-t border-line px-4 py-2.5">
        <p className="text-xs leading-relaxed text-faint">{data.note}</p>
      </div>
    </Card>
  );
}

/** The whole walkthrough, for the dedicated page. */
export function Walkthrough() {
  const { data, error, loading } = useOnboarding();
  const primer = usePrimer();

  if (loading) return <Spinner label="Reading where you are" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <GettingStarted data={data} onOpenPrimer={primer.open} />
      {data.complete ? (
        <Caveat>
          Every step here is done. That means the workflow has been exercised end to end — it
          does not mean the system under test is ready. Read the campaign, not this checklist.
        </Caveat>
      ) : null}
      <Primer open={primer.show} onClose={primer.close} />
    </div>
  );
}
