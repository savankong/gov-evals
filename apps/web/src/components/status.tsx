import type { ResultStatus, Severity } from "@/lib/types";

/** Status vocabulary shared by every surface.
 *
 * NOT EVALUATED is styled as an outlined, dashed chip rather than a filled
 * neutral one: an untested property should look unlike a tested one at a
 * glance, never like a quiet pass.
 */
const STATUS: Record<
  ResultStatus | string,
  { label: string; className: string; dot: string }
> = {
  pass: {
    label: "PASS",
    className: "text-[rgb(var(--pass))] bg-[rgb(var(--pass-bg))] border-[rgb(var(--pass))]/25",
    dot: "bg-[rgb(var(--pass))]",
  },
  warning: {
    label: "WARNING",
    className: "text-[rgb(var(--warn))] bg-[rgb(var(--warn-bg))] border-[rgb(var(--warn))]/25",
    dot: "bg-[rgb(var(--warn))]",
  },
  fail: {
    label: "FAIL",
    className: "text-[rgb(var(--fail))] bg-[rgb(var(--fail-bg))] border-[rgb(var(--fail))]/25",
    dot: "bg-[rgb(var(--fail))]",
  },
  error: {
    label: "ERROR",
    className: "text-[rgb(var(--fail))] bg-[rgb(var(--fail-bg))] border-[rgb(var(--fail))]/25",
    dot: "bg-[rgb(var(--fail))]",
  },
  not_evaluated: {
    label: "NOT EVALUATED",
    className:
      "text-[rgb(var(--unknown))] bg-transparent border-dashed border-[rgb(var(--unknown))]/50",
    dot: "bg-transparent ring-1 ring-[rgb(var(--unknown))]/60",
  },
  pending_human: {
    label: "AWAITING REVIEW",
    className:
      "text-[rgb(var(--pending))] bg-[rgb(var(--pending-bg))] border-[rgb(var(--pending))]/25",
    dot: "bg-[rgb(var(--pending))]",
  },
};

export function statusMeta(status: string) {
  return STATUS[status] ?? STATUS.not_evaluated;
}

export function StatusChip({
  status,
  size = "sm",
  title,
}: {
  status: ResultStatus | string;
  size?: "xs" | "sm";
  title?: string;
}) {
  const meta = statusMeta(status);
  return (
    <span
      title={title ?? meta.label}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border font-medium tracking-wide ${
        size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"
      } ${meta.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} aria-hidden />
      {meta.label}
    </span>
  );
}

const SEVERITY: Record<Severity | string, string> = {
  critical: "text-[rgb(var(--fail))] bg-[rgb(var(--fail-bg))] border-[rgb(var(--fail))]/30",
  high: "text-[rgb(var(--warn))] bg-[rgb(var(--warn-bg))] border-[rgb(var(--warn))]/30",
  medium: "text-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 border-[rgb(var(--accent))]/25",
  low: "text-muted bg-[rgb(var(--unknown-bg))] border-line",
  info: "text-muted bg-[rgb(var(--unknown-bg))] border-line",
};

export function SeverityChip({ severity }: { severity: Severity | string }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
        SEVERITY[severity] ?? SEVERITY.info
      }`}
    >
      {severity}
    </span>
  );
}

/** Evaluator kind badge. Model-based judgements are labelled everywhere they
 *  appear so they are never read as ground truth. */
export function EvaluatorKindBadge({ kind }: { kind: string }) {
  const map: Record<string, { label: string; hint: string }> = {
    deterministic: { label: "deterministic", hint: "Same input always produces the same judgement." },
    model_based: {
      label: "model judge",
      hint: "Advisory evidence from another model. Not ground truth.",
    },
    human: { label: "human", hint: "Judgement recorded by a person against a rubric." },
    external_tool: { label: "external tool", hint: "Judgement from an external validator." },
  };
  const meta = map[kind] ?? { label: kind, hint: "" };
  return (
    <span
      title={meta.hint}
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
        kind === "model_based"
          ? "bg-[rgb(var(--warn-bg))] text-[rgb(var(--warn))]"
          : "bg-[rgb(var(--unknown-bg))] text-muted"
      }`}
    >
      {meta.label}
    </span>
  );
}
