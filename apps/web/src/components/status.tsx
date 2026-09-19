import type { ResultStatus, Severity } from "@/lib/types";

/**
 * Status vocabulary.
 *
 * Status is carried by a small solid square, the way a category is in a dense
 * financial table: it survives at eleven pixels, in a column, at a glance.
 * Everything else about the row stays monochrome so the squares are the only
 * thing competing for attention.
 *
 * NOT EVALUATED is the exception that proves the rule -- it gets a hollow
 * square with a dashed edge, because an untested property must not read like
 * a quiet pass sitting next to real ones.
 */
const STATUS: Record<
  string,
  { label: string; short: string; square: string; text: string }
> = {
  pass: {
    label: "Pass",
    short: "PASS",
    square: "bg-pass",
    text: "text-pass",
  },
  warning: {
    label: "Warning",
    short: "WARN",
    square: "bg-warn",
    text: "text-warn",
  },
  fail: {
    label: "Fail",
    short: "FAIL",
    square: "bg-fail",
    text: "text-fail",
  },
  error: {
    label: "Error",
    short: "ERR",
    square: "bg-fail",
    text: "text-fail",
  },
  not_evaluated: {
    label: "Not evaluated",
    short: "NOT EVALUATED",
    square: "bg-transparent border border-dashed border-unknown",
    text: "text-muted",
  },
  pending_human: {
    label: "Awaiting review",
    short: "AWAITING",
    square: "bg-pending",
    text: "text-pending",
  },
};

export function statusMeta(status: string) {
  return STATUS[status] ?? STATUS.not_evaluated;
}

/** The square alone, for table cells where the column header supplies meaning. */
export function StatusSquare({
  status,
  live = false,
  className = "",
}: {
  status: string;
  live?: boolean;
  className?: string;
}) {
  const meta = statusMeta(status);
  return (
    <span
      role="img"
      aria-label={meta.label}
      title={meta.label}
      className={`inline-block h-[7px] w-[7px] shrink-0 ${meta.square} ${
        live ? "animate-breathe" : ""
      } ${className}`}
    />
  );
}

/** Square plus label. The default way a verdict appears outside a table. */
export function Status({
  status,
  live = false,
  className = "",
}: {
  status: ResultStatus | string;
  live?: boolean;
  className?: string;
  /** Accepted for call-site readability. Status is one size in this system. */
  size?: "xs" | "sm";
}) {
  const meta = statusMeta(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-2xs font-medium uppercase tracking-wider ${meta.text} ${className}`}
    >
      <StatusSquare status={status} live={live} />
      {meta.short}
    </span>
  );
}

const SEVERITY: Record<string, { square: string; text: string }> = {
  critical: { square: "bg-fail", text: "text-fail" },
  high: { square: "bg-warn", text: "text-warn" },
  medium: { square: "bg-pending", text: "text-pending" },
  low: { square: "bg-unknown", text: "text-muted" },
  info: { square: "bg-unknown", text: "text-muted" },
};

export function SeverityTag({
  severity,
  withSquare = true,
}: {
  severity: Severity | string;
  withSquare?: boolean;
}) {
  const meta = SEVERITY[severity] ?? SEVERITY.info;
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap text-2xs font-medium uppercase tracking-wider ${meta.text}`}
    >
      {withSquare ? <span className={`h-[7px] w-[7px] shrink-0 ${meta.square}`} /> : null}
      {severity}
    </span>
  );
}

/**
 * Evaluator kind.
 *
 * A model-based judgement is labelled wherever it appears. It is advisory
 * evidence and must never be mistaken for the deterministic judgement beside
 * it, so the label travels with the score rather than living in a legend.
 */
export function EvaluatorKind({ kind }: { kind: string }) {
  const map: Record<string, { label: string; hint: string; emphasis: boolean }> = {
    deterministic: {
      label: "deterministic",
      hint: "Same input always produces the same judgement.",
      emphasis: false,
    },
    model_based: {
      label: "model judge",
      hint: "Advisory evidence from another model. Not ground truth.",
      emphasis: true,
    },
    human: {
      label: "human",
      hint: "Recorded by a person against a rubric.",
      emphasis: false,
    },
    external_tool: {
      label: "external tool",
      hint: "Judgement from an external validator.",
      emphasis: false,
    },
  };
  const meta = map[kind] ?? { label: kind, hint: "", emphasis: false };
  return (
    <span
      title={meta.hint}
      className={`whitespace-nowrap border px-1 py-px text-2xs tracking-wide ${
        meta.emphasis
          ? "border-warn/40 text-warn"
          : "border-line text-faint"
      }`}
    >
      {meta.label}
    </span>
  );
}
