"use client";

import type { ReactNode } from "react";

import { Button, ErrorNote } from "@/components/ui";

const CONTROL =
  "w-full border border-line bg-panel px-2.5 text-sm text-ink outline-none transition-colors duration-150 placeholder:text-faint focus:border-line-strong disabled:opacity-50";

export function Label({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-2xs uppercase tracking-wider text-faint">
      {children}
    </label>
  );
}

export function Field({
  id,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  help,
  required,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: "text" | "password" | "number" | "email";
  help?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <div>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="ml-1 text-faint">·required</span> : null}
      </Label>
      <input
        id={id}
        type={type}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={`mt-1 h-7 ${CONTROL}`}
      />
      {help ? <p className="mt-1 text-xs leading-relaxed text-muted">{help}</p> : null}
    </div>
  );
}

export function TextArea({
  id,
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  help,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  help?: string;
  required?: boolean;
}) {
  return (
    <div>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="ml-1 text-faint">·required</span> : null}
      </Label>
      <textarea
        id={id}
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={`mt-1 py-2 leading-relaxed ${CONTROL}`}
      />
      {help ? <p className="mt-1 text-xs leading-relaxed text-muted">{help}</p> : null}
    </div>
  );
}

export function Choice({
  id,
  label,
  value,
  onChange,
  options,
  help,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  help?: string;
  required?: boolean;
}) {
  return (
    <div>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="ml-1 text-faint">·required</span> : null}
      </Label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`mt-1 h-7 appearance-none ${CONTROL}`}
      >
        {options.length === 0 ? <option value="">None available</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {help ? <p className="mt-1 text-xs leading-relaxed text-muted">{help}</p> : null}
    </div>
  );
}

/**
 * A list of short statements, one per line.
 *
 * A mission profile is mostly lists — tasks, users, unacceptable failures — and
 * a row-at-a-time editor with add and remove buttons is more machinery than
 * the content deserves. One per line is what people already do in a notes app,
 * and the count underneath says what the field actually parsed to, so nobody
 * has to guess whether a blank line counted.
 */
export function Lines({
  id,
  label,
  value,
  onChange,
  placeholder,
  help,
  rows = 3,
}: {
  id: string;
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  help?: string;
  rows?: number;
}) {
  const text = value.join("\n");
  const parsed = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Label htmlFor={id}>{label}</Label>
        <span className="tnum text-2xs text-faint">
          {parsed.length === 0 ? "none" : `${parsed.length} item${parsed.length === 1 ? "" : "s"}`}
        </span>
      </div>
      <textarea
        id={id}
        rows={rows}
        value={text}
        onChange={(event) =>
          onChange(
            event.target.value
              .split("\n")
              .map((line) => line.replace(/^\s+/, ""))
              .filter((line, index, all) => line !== "" || index < all.length - 1),
          )
        }
        placeholder={placeholder}
        className={`mt-1 py-2 font-mono leading-relaxed ${CONTROL}`}
      />
      {help ? <p className="mt-1 text-xs leading-relaxed text-muted">{help}</p> : null}
    </div>
  );
}

/** The footer every form in this product shares: primary, cancel, error. */
export function FormActions({
  onSubmit,
  onCancel,
  submitting,
  disabled,
  error,
  submitLabel,
  busyLabel,
  children,
}: {
  onSubmit: () => void;
  onCancel?: () => void;
  submitting?: boolean;
  disabled?: boolean;
  error?: string | null;
  submitLabel: string;
  busyLabel?: string;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-2.5">
      {error ? <ErrorNote message={error} /> : null}
      {children}
      <div className="flex items-center gap-2">
        <Button variant="primary" onClick={onSubmit} disabled={submitting || disabled}>
          {submitting ? (busyLabel ?? "Saving…") : submitLabel}
        </Button>
        {onCancel ? (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
    </div>
  );
}
