"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return (
    <Tag className={`rounded-lg border border-line bg-raised ${className}`}>{children}</Tag>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-muted">{subtitle}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/** A single measurement. `value` renders as-is so "—" and "NOT EVALUATED"
 *  read differently from a zero. */
export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "fail" | "warn" | "pass" | "muted";
}) {
  const tones = {
    default: "text-ink",
    fail: "text-[rgb(var(--fail))]",
    warn: "text-[rgb(var(--warn))]",
    pass: "text-[rgb(var(--pass))]",
    muted: "text-muted",
  };
  return (
    <div className="px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`tnum mt-1 text-2xl font-semibold ${tones[tone]}`}>{value}</div>
      {hint ? <div className="mt-0.5 text-xs text-muted">{hint}</div> : null}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  type = "button",
  size = "md",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  size?: "sm" | "md";
}) {
  const variants = {
    primary:
      "bg-[rgb(var(--accent))] text-white hover:opacity-90 border-transparent disabled:opacity-50",
    secondary: "bg-raised text-ink border-line hover:bg-[rgb(var(--unknown-bg))] disabled:opacity-50",
    ghost: "bg-transparent text-muted border-transparent hover:text-ink",
    danger:
      "bg-[rgb(var(--fail-bg))] text-[rgb(var(--fail))] border-[rgb(var(--fail))]/30 hover:opacity-90",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors disabled:cursor-not-allowed ${
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm"
      } ${variants[variant]}`}
    >
      {children}
    </button>
  );
}

export function Hash({ value, length = 12 }: { value?: string | null; length?: number }) {
  if (!value) return <span className="text-muted">—</span>;
  return (
    <code
      title={value}
      className="tnum rounded bg-[rgb(var(--unknown-bg))] px-1 py-0.5 font-mono text-[11px] text-muted"
    >
      {value.slice(0, length)}
    </code>
  );
}

export function Empty({ title, detail, action }: { title: string; detail?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {detail ? <p className="max-w-md text-xs text-muted">{detail}</p> : null}
      {action}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-6 py-12 text-sm text-muted">
      <span
        className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-[rgb(var(--accent))]"
        aria-hidden
      />
      {label}…
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-[rgb(var(--fail))]/30 bg-[rgb(var(--fail-bg))] px-3 py-2 text-sm text-[rgb(var(--fail))]">
      {message}
    </div>
  );
}

/** A statement the product makes about its own limits. These appear next to
 *  anything a reader might otherwise over-read. */
export function Caveat({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-line py-0.5 pl-3 text-xs leading-relaxed text-muted">
      {children}
    </p>
  );
}

export function Crumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav className="flex flex-wrap items-center gap-1.5 text-xs text-muted" aria-label="Breadcrumb">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="flex items-center gap-1.5">
          {i > 0 ? <span aria-hidden>/</span> : null}
          {item.href ? (
            <Link href={item.href} className="hover:text-ink hover:underline">
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
    <div className="flex gap-1 overflow-x-auto border-b border-line" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm transition-colors ${
            active === tab.key
              ? "border-[rgb(var(--accent))] font-medium text-ink"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          {tab.label}
          {tab.count !== undefined ? (
            <span className="tnum ml-1.5 text-xs text-muted">{tab.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

/** Filter chip row, following the pattern used by findings dashboards:
 *  a compact always-visible row rather than a hidden filter panel. */
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
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        onClick={() => onChange(null)}
        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
          active === null
            ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 text-ink"
            : "border-line text-muted hover:text-ink"
        }`}
      >
        {allLabel}
      </button>
      {options.map((option) => (
        <button
          key={option.key}
          onClick={() => onChange(option.key)}
          className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
            active === option.key
              ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 text-ink"
              : "border-line text-muted hover:text-ink"
          }`}
        >
          {option.label}
          {option.count !== undefined ? (
            <span className="tnum ml-1 opacity-70">{option.count}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(value >= 0.995 || value === 0 ? 0 : 1)}%`;
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
