"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  IconChevron,
  IconClose,
  IconError,
  IconNote,
  IconWarning,
} from "@/components/icons";

/* ------------------------------------------------------------------ *
 * Surfaces
 * ------------------------------------------------------------------ */

export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <Tag className={`border border-line bg-panel ${className}`}>{children}</Tag>;
}

export function CardHead({
  title,
  meta,
  subtitle,
  action,
}: {
  title: ReactNode;
  meta?: ReactNode;
  /** Alias of `meta`, for call sites where "subtitle" reads better. */
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  const secondary = meta ?? subtitle;
  return (
    <div className="flex items-start justify-between gap-4 px-4 pb-3 pt-3.5">
      <div className="min-w-0">
        <h2 className="text-sm font-medium text-ink">{title}</h2>
        {secondary ? <p className="mt-0.5 text-xs text-muted">{secondary}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Numerals
 * ------------------------------------------------------------------ */

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const listener = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return reduced;
}

/**
 * Counts a figure up on first paint.
 *
 * Eased rather than linear, and it always lands exactly on the target: a
 * metric that settles on 93.7% when the real number is 94% would be a lie
 * told by an animation. Skipped entirely under reduced motion.
 */
export function useCountUp(target: number | null, durationMs = 520): number | null {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState<number | null>(reduced ? target : 0);
  const frame = useRef<number>(0);

  useEffect(() => {
    if (target === null) {
      setValue(null);
      return;
    }
    if (reduced) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(progress === 1 ? target : target * eased);
      if (progress < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [target, durationMs, reduced]);

  return value;
}

/**
 * The signature element: a tiny muted label over a large light numeral.
 *
 * `value` is pre-formatted so a dash, a percentage and "NOT EVALUATED" can all
 * occupy the same slot without the component knowing what a metric is.
 */
export function Figure({
  label,
  value,
  note,
  tone = "ink",
  size = "lg",
  countTo,
  format,
}: {
  label: string;
  value?: ReactNode;
  note?: ReactNode;
  tone?: "ink" | "muted" | "pass" | "warn" | "fail";
  size?: "sm" | "lg" | "xl";
  countTo?: number | null;
  format?: (n: number) => string;
}) {
  const counted = useCountUp(countTo ?? null);
  const tones = {
    ink: "text-ink",
    muted: "text-faint",
    pass: "text-pass",
    warn: "text-warn",
    fail: "text-fail",
  };
  const sizes = { sm: "text-xl", lg: "text-3xl", xl: "text-5xl" };

  const rendered =
    countTo !== undefined && countTo !== null && counted !== null
      ? format
        ? format(counted)
        : Math.round(counted).toLocaleString()
      : value;

  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className={`numeral mt-1.5 ${sizes[size]} ${tones[tone]}`}>{rendered}</div>
      {note ? <div className="mt-1 text-xs text-muted">{note}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Controls
 * ------------------------------------------------------------------ */

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  /** Accepted for call-site readability. Controls are a single height in this
   *  system, so the value does not change the rendering. */
  size?: "sm" | "md";
}) {
  const variants = {
    primary:
      "bg-accent text-accent-ink border-accent hover:opacity-85 disabled:opacity-40",
    secondary:
      "bg-panel text-ink border-line hover:border-line-strong hover:bg-sunken disabled:opacity-40",
    ghost: "bg-transparent text-muted border-transparent hover:text-ink",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-7 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap border px-2.5 text-sm transition-[opacity,background-color,border-color] duration-150 ease-out disabled:cursor-not-allowed ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

/** Segmented control, the way a table switches between All and a subset. */
export function Segmented({
  options,
  active,
  onChange,
}: {
  options: Array<{ key: string | null; label: string; count?: number }>;
  active: string | null;
  onChange: (key: string | null) => void;
}) {
  return (
    // Scrolls rather than wraps. A label that wraps inside a fixed-height
    // segment breaks the control open; one that runs past the edge of a strip
    // is still a control. Long option sets belong in a Select instead.
    <div className="-mx-1 max-w-full overflow-x-auto px-1 py-px">
      <div className="inline-flex border border-line bg-panel">
        {options.map((option, index) => (
          <button
            key={option.key ?? "all"}
            onClick={() => onChange(option.key)}
            className={`h-7 shrink-0 whitespace-nowrap px-2.5 text-sm transition-colors duration-150 ease-out ${
              index > 0 ? "border-l border-line" : ""
            } ${
              active === option.key
                ? "bg-sunken font-medium text-ink"
                : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="tnum ml-1.5 text-faint">{option.count}</span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

/** A filter row: the segmented control with an explicit "all" option. */
export function FilterChips({
  options,
  active,
  onChange,
  allLabel = "All",
}: {
  options: Array<{ key: string; label: string; count?: number }>;
  active: string | null;
  onChange: (key: string | null) => void;
  allLabel?: string;
}) {
  return (
    <Segmented
      options={[{ key: null, label: allLabel }, ...options]}
      active={active}
      onChange={onChange}
    />
  );
}

/** Tabs are the same control; only the caller's intent differs. */
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ key: string; label: string; count?: number }>;
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <Segmented
      options={tabs}
      active={active}
      onChange={(key) => onChange(key ?? tabs[0]?.key ?? "")}
    />
  );
}

export function Hash({ value, length = 10 }: { value?: string | null; length?: number }) {
  if (!value) return <span className="text-faint">—</span>;
  return (
    <code
      title={value}
      className="tnum font-mono text-2xs text-faint transition-colors duration-150 hover:text-muted"
    >
      {value.slice(0, length)}
    </code>
  );
}

/** Keyboard hint, shown in slide-over footers and the command palette. */
export function Key({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-[18px] min-w-[18px] items-center justify-center border border-line bg-sunken px-1 font-mono text-2xs text-muted">
      {children}
    </kbd>
  );
}

/* ------------------------------------------------------------------ *
 * Tables
 * ------------------------------------------------------------------ */

export function Table({ children, minWidth }: { children: ReactNode; minWidth?: number }) {
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full border-collapse text-sm"
        style={minWidth ? { minWidth } : undefined}
      >
        {children}
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  className = "",
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}) {
  return (
    <th
      className={`border-b border-line px-3 py-1.5 text-${align} text-2xs font-normal uppercase tracking-wider text-faint ${className}`}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className = "",
  colSpan,
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  colSpan?: number;
}) {
  return (
    <td
      colSpan={colSpan}
      className={`border-b border-line px-3 py-2 text-${align} align-top ${className}`}
    >
      {children}
    </td>
  );
}

/** A table row that rises in, staggered by position and capped so a long
 *  table is never waiting on its own animation. */
export function Tr({
  children,
  index = 0,
  onClick,
  className = "",
}: {
  children: ReactNode;
  index?: number;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <tr
      onClick={onClick}
      style={{ ["--stagger-delay" as string]: `${Math.min(index, 14) * 18}ms` }}
      className={`stagger transition-colors duration-150 ease-out hover:bg-sunken ${
        onClick ? "cursor-pointer" : ""
      } ${className}`}
    >
      {children}
    </tr>
  );
}

/* ------------------------------------------------------------------ *
 * States
 * ------------------------------------------------------------------ */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

/** Loading placeholder shaped like the table it precedes, so the page does
 *  not jump when the data lands. */
export function TableSkeleton({ rows = 6, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="animate-fade">
      {Array.from({ length: rows }).map((_, row) => (
        <div key={row} className="flex items-center gap-4 border-b border-line px-3 py-2.5">
          {Array.from({ length: cols }).map((_, col) => (
            <Skeleton
              key={col}
              className="h-3"
              // Varied widths so it reads as content, not as a progress bar.
              {...{ style: { width: `${[34, 18, 12, 22, 14][col % 5]}%` } }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Empty({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="mb-1 h-6 w-6 border border-dashed border-line-strong" aria-hidden />
      <p className="text-base text-ink">{title}</p>
      {detail ? <p className="max-w-sm text-xs leading-relaxed text-muted">{detail}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-6 py-14 text-sm text-muted">
      <span
        className="h-2.5 w-2.5 animate-spin border border-line border-t-ink"
        aria-hidden
      />
      {label}…
    </div>
  );
}

/** An aside, marked by what it is rather than by a rule down its side.
 *
 *  The rule was the wrong instrument. A line can only be darker or lighter, so
 *  it says "pay attention" and nothing else, and every kind of aside ended up
 *  wearing the same one. A glyph names the kind and its colour carries the
 *  weight: red is something that went wrong, amber is something to be careful
 *  of, and a quiet note is the product stating its own limits. */
export function Note({
  tone = "muted",
  children,
  className = "",
}: {
  tone?: "muted" | "warn" | "fail";
  children: ReactNode;
  className?: string;
}) {
  const Icon = tone === "fail" ? IconError : tone === "warn" ? IconWarning : IconNote;
  const colour = tone === "fail" ? "text-fail" : tone === "warn" ? "text-warn" : "text-faint";
  const body = tone === "fail" ? "text-fail" : tone === "warn" ? "text-warn" : "text-muted";

  return (
    <div className={`flex gap-2 text-xs leading-relaxed ${className}`}>
      <Icon className={`mt-[2px] shrink-0 ${colour}`} aria-hidden />
      <div className={`min-w-0 flex-1 ${body}`}>{children}</div>
    </div>
  );
}

/** Something the interface could not do.
 *
 *  Red, because a failure is a failure -- but carried by the glyph, not by a
 *  bar drawn down the edge of the block. The colour lands on the one mark
 *  whose job is to say what kind of thing this is, and the words stay legible
 *  text rather than a paragraph tinted to match. */
export function ErrorNote({
  message,
  status,
  onRetry,
}: {
  message: string;
  status?: number | null;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="animate-rise flex gap-2.5 bg-sunken px-3 py-2.5 text-sm">
      <IconError className="mt-[3px] shrink-0 text-fail" aria-hidden />
      {/* The icon sits outside the wrapping row, so when the retry drops to a
          second line it lands under the message rather than under the glyph.
          The message keeps a measure of its own so that on a narrow screen it
          wraps as a sentence instead of one word to a row. */}
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2.5 gap-y-1">
        {status ? (
          <span className="tnum shrink-0 font-mono text-2xs text-faint">{status}</span>
        ) : null}
        <p className="min-w-[12rem] flex-1 text-ink-soft">{message}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 text-xs text-muted underline underline-offset-2 transition-colors duration-150 hover:text-ink"
          >
            Try again
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** A statement the product makes about its own limits. Appears beside
 *  anything a reader might otherwise over-read. */
export function Caveat({ children }: { children: ReactNode }) {
  return <Note tone="muted">{children}</Note>;
}

/* ------------------------------------------------------------------ *
 * Navigation
 * ------------------------------------------------------------------ */

export function Crumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav className="flex flex-wrap items-center gap-1.5 text-xs text-muted" aria-label="Breadcrumb">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="flex items-center gap-1.5">
          {i > 0 ? <span className="text-faint">/</span> : null}
          {item.href ? (
            <Link href={item.href} className="link-underline hover:text-ink">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function PageTitle({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="animate-rise flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate text-xl font-normal text-ink">{title}</h1>
        {subtitle ? <p className="mt-0.5 max-w-3xl text-sm text-muted">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Formatting
 * ------------------------------------------------------------------ */

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(value >= 0.995 || value === 0 ? 0 : 1)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value}ms`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/* ------------------------------------------------------------------ *
 * Inputs
 * ------------------------------------------------------------------ */

/**
 * The only dropdown in the system.
 *
 * A native `select` painted to match: the platform menu is better than
 * anything a hairline interface would rebuild, but the closed control has to
 * read like every other 28px control on the page, so the chevron is drawn and
 * the native arrow removed.
 */
export function Select({
  label,
  value,
  onChange,
  options,
  id,
  className = "",
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  id?: string;
  className?: string;
}) {
  const selectId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      {label ? (
        <label htmlFor={selectId} className="text-2xs uppercase tracking-wider text-faint">
          {label}
        </label>
      ) : null}
      <div className="relative">
        <select
          id={selectId}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-7 appearance-none border border-line bg-panel py-0 pl-2.5 pr-7 text-sm text-ink transition-colors duration-150 ease-out hover:border-line-strong focus:outline-none focus-visible:outline-1"
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <IconChevron
          aria-hidden
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rotate-90 text-faint"
          width={12}
          height={12}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Tokens
 * ------------------------------------------------------------------ */

/**
 * A small hairline token: a tag, a domain, a layer, an applied filter.
 *
 * Square, uncoloured and quiet. When `onClear` is given it becomes the
 * dismissable form used to show a filter that is currently narrowing a list.
 */
export function Tag({
  children,
  tone = "quiet",
  mono = false,
  onClear,
  title,
}: {
  children: ReactNode;
  tone?: "quiet" | "strong" | "warn" | "fail";
  mono?: boolean;
  onClear?: () => void;
  title?: string;
}) {
  const tones = {
    quiet: "border-line text-muted",
    strong: "border-line-strong text-ink",
    warn: "border-warn/40 text-warn",
    fail: "border-fail/40 text-fail",
  };
  const body = (
    <>
      {children}
      {onClear ? (
        <IconClose width={10} height={10} aria-hidden className="text-faint" />
      ) : null}
    </>
  );
  const shared = `inline-flex shrink-0 items-center gap-1 whitespace-nowrap border px-1.5 py-px text-2xs tracking-wide ${
    mono ? "font-mono" : ""
  } ${tones[tone]}`;

  if (onClear) {
    return (
      <button
        type="button"
        title={title}
        onClick={onClear}
        className={`${shared} transition-colors duration-150 ease-out hover:border-line-strong hover:text-ink`}
      >
        {body}
      </button>
    );
  }
  return (
    <span title={title} className={shared}>
      {body}
    </span>
  );
}

/**
 * A proportion bar: one hairline-thin track, one filled segment.
 *
 * Grows from zero on mount so a distribution reads as it draws, and is
 * deliberately 2px tall -- at this weight it is an annotation on the number
 * beside it, never a substitute for it.
 */
export function Bar({
  value,
  tone = "ink",
  className = "",
}: {
  /** 0..1 */
  value: number;
  tone?: "ink" | "muted" | "pass" | "warn" | "fail";
  className?: string;
}) {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setWidth(Math.max(0, Math.min(1, value)) * 100));
    return () => cancelAnimationFrame(frame);
  }, [value]);

  const tones = {
    ink: "bg-ink",
    muted: "bg-line-strong",
    pass: "bg-pass",
    warn: "bg-warn",
    fail: "bg-fail",
  };
  return (
    <div className={`h-[2px] w-full bg-sunken ${className}`}>
      <div
        className={`h-full transition-[width] duration-500 ease-out ${tones[tone]}`}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}

/**
 * A three-part proportion bar, for a set that divides into passed, other and
 * failed. Segments are laid out in one row so the whole always reads as one
 * bar rather than three.
 */
export function SplitBar({
  parts,
  className = "",
}: {
  parts: Array<{ value: number; tone: "pass" | "warn" | "fail" | "muted" }>;
  className?: string;
}) {
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  if (total <= 0) return null;

  const tones = {
    pass: "bg-pass",
    warn: "bg-warn",
    fail: "bg-fail",
    muted: "bg-line-strong",
  };
  return (
    <div className={`flex h-[2px] w-full gap-px bg-sunken ${className}`}>
      {parts
        .filter((part) => part.value > 0)
        .map((part, index) => (
          <div
            key={index}
            className={`h-full transition-[width] duration-500 ease-out ${tones[part.tone]}`}
            style={{ width: mounted ? `${(part.value / total) * 100}%` : "0%" }}
          />
        ))}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Code and specifications
 * ------------------------------------------------------------------ */

export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-xs text-muted ${className}`}>{children}</span>;
}

export function CodeBlock({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <pre
      className={`overflow-x-auto whitespace-pre-wrap break-words border border-line bg-sunken px-3 py-2 font-mono text-xs leading-relaxed text-ink-soft ${className}`}
    >
      {children}
    </pre>
  );
}

const SPEC_LABELS: Record<string, string> = {
  min_pass_rate: "min pass rate",
  max_failures: "max failures",
  max_latency_ms: "max latency",
  max_p95_latency_ms: "max p95 latency",
  finding_severity: "finding severity",
  tags_match: "tags match",
  min_score: "min score",
  max_score: "max score",
};

function formatSpecValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    if (key.endsWith("_rate") || key.startsWith("min_pass")) return formatPercent(value);
    if (key.endsWith("_ms")) return formatMs(value);
    return String(value);
  }
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * A threshold or selector, rendered as readable pairs.
 *
 * These are JSON on the wire, and a program office reading its own passing bar
 * should not have to parse `{"min_pass_rate":0.98}` to find out what it agreed
 * to. The raw object stays available on hover for anyone reproducing a run.
 */
export function Spec({
  value,
  empty = "not set",
}: {
  value: Record<string, unknown> | null | undefined;
  empty?: string;
}) {
  const entries = Object.entries(value ?? {});
  if (entries.length === 0) {
    return <span className="text-2xs uppercase tracking-wider text-faint">{empty}</span>;
  }
  return (
    <span
      className="flex flex-wrap items-center gap-x-3 gap-y-1"
      title={JSON.stringify(value)}
    >
      {entries.map(([key, raw]) => (
        <span key={key} className="whitespace-nowrap text-xs">
          <span className="text-faint">{SPEC_LABELS[key] ?? key.replace(/_/g, " ")}</span>{" "}
          <span className="tnum text-ink">{formatSpecValue(key, raw)}</span>
        </span>
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Disclosure
 * ------------------------------------------------------------------ */

/**
 * A section that opens and closes.
 *
 * The chevron rotates rather than swapping glyphs, and the body is measured by
 * the browser rather than by a fixed height, so a claim with twelve pieces of
 * evidence and one with none animate the same way.
 */
export function Disclosure({
  open,
  onToggle,
  summary,
  children,
  className = "",
}: {
  open: boolean;
  onToggle: () => void;
  summary: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="group flex w-full items-start gap-2 text-left"
      >
        <IconChevron
          aria-hidden
          width={12}
          height={12}
          className={`mt-1 shrink-0 text-faint transition-transform duration-200 ease-out group-hover:text-muted ${
            open ? "rotate-90" : "rotate-0"
          }`}
        />
        <span className="min-w-0 flex-1">{summary}</span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="pl-5">{children}</div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
