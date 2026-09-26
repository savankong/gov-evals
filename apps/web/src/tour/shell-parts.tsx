"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { UI } from "./copy";
import { useTour } from "./provider";

/** A question mark in a circle, on the product's 16px hairline grid. */
function IconHelp({ className = "" }: { className?: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <circle cx="8" cy="8" r="6" />
      <path d="M6.3 6.4a1.8 1.8 0 0 1 3.5.5c0 1.2-1.8 1.5-1.8 2.6" />
      <path d="M8 11.3v.01" />
    </svg>
  );
}

/**
 * Stays up the whole time the sample is on screen, under the marking banner.
 * Monochrome: a saturated colour in this product is a verdict about the system
 * under test, and "this is sample data" is not one.
 */
export function TourBanner() {
  const { snapshot, controller } = useTour();
  if (!snapshot?.sampleOn) return null;
  return (
    <div
      role="region"
      aria-label="Sample data"
      className="flex shrink-0 items-center justify-center gap-3 border-b border-line bg-sunken px-3 py-1 text-xs text-ink-soft"
    >
      <span className="min-w-0 truncate">{UI.banner.text}</span>
      <button
        type="button"
        onClick={() => controller?.exit()}
        className="shrink-0 text-xs text-ink underline underline-offset-2 hover:text-muted"
      >
        {UI.banner.exit}
      </button>
    </div>
  );
}

export function TourHelpMenu() {
  const { enabled, controller, snapshot, presenter, setPresenterOpen } = useTour();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const first = wrap.current?.querySelector<HTMLElement>("[role='menuitem']");
    first?.focus();
    const onDown = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      const items = Array.from(wrap.current?.querySelectorAll<HTMLElement>("[role='menuitem']") ?? []);
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        button.current?.focus();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        items[(index + 1) % items.length]?.focus();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        items[(index - 1 + items.length) % items.length]?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  if (!enabled || !controller) return null;

  const seen = snapshot?.state.status !== "preview" && controller.progress() !== null;
  const item =
    "block w-full px-3 py-1.5 text-left text-sm text-ink-soft outline-none transition-colors duration-100 hover:bg-sunken hover:text-ink focus:bg-sunken focus:text-ink";

  return (
    <div ref={wrap} className="relative">
      <button
        ref={button}
        type="button"
        aria-label={UI.help.button}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="grid h-7 w-7 place-items-center text-faint transition-colors duration-150 hover:text-ink"
      >
        <IconHelp />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label={UI.help.button}
          className="absolute right-0 top-8 z-[60] w-48 border border-line-strong bg-panel py-1"
        >
          <Link href="/welcome" role="menuitem" className={item} onClick={() => setOpen(false)}>
            {UI.help.gettingStarted}
          </Link>
          <button
            type="button"
            role="menuitem"
            className={item}
            onClick={() => {
              setOpen(false);
              controller.replay();
            }}
          >
            {seen ? UI.help.replay : UI.help.take}
          </button>
          {presenter ? (
            <button
              type="button"
              role="menuitem"
              className={item}
              onClick={() => {
                setOpen(false);
                setPresenterOpen(true);
              }}
            >
              {UI.help.presenter}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
