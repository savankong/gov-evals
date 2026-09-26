"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Button, Key, Note } from "@/components/ui";

import { PATH_COPY, UI } from "./copy";
import { findAnchor, reserveSheet, reveal, revealKept, runAssist } from "./dom";
import { place, sameRect, type Rect } from "./placement";
import { useTour } from "./provider";
import { PATHS } from "./steps";
import { PATH_IDS, type PathId } from "./types";

/* ------------------------------------------------------------------ *
 * Shared
 * ------------------------------------------------------------------ */

const EASE = [0.16, 1, 0.3, 1] as const;

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

/** Another dialog the product has open -- a slide-over, the command palette.
 *  Escape belongs to it, not to the tour. */
function otherDialogOpen(): boolean {
  return document.querySelector('[role="dialog"]:not([data-tour-ui])') !== null;
}

function focusIfFree(el: HTMLElement | null): void {
  if (!el) return;
  const active = document.activeElement as HTMLElement | null;
  // Never take focus from someone typing into the page.
  if (!active || active === document.body || active.closest("[data-tour-ui]")) {
    el.focus({ preventScroll: true });
  }
}

function Progress({ total, at }: { total: number; at: number }) {
  return (
    <div className="flex items-center gap-1" aria-hidden>
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={`h-[5px] w-[5px] ${i < at ? "bg-ink" : i === at ? "bg-muted" : "bg-line-strong"}`}
        />
      ))}
    </div>
  );
}

function Panel({
  children,
  label,
  labelledBy,
  className = "",
  style,
  modal = false,
}: {
  children: ReactNode;
  label?: string;
  labelledBy?: string;
  className?: string;
  style?: React.CSSProperties;
  modal?: boolean;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      data-tour-ui
      role="dialog"
      aria-modal={modal}
      aria-label={label}
      aria-labelledby={labelledBy}
      className={`z-[70] border border-line-strong bg-panel ${className}`}
      style={style}
      initial={reduced ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: 4 }}
      transition={{ duration: 0.16, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------------------ *
 * The layer
 * ------------------------------------------------------------------ */

export function TourLayer() {
  const { snapshot, controller, presenterOpen } = useTour();
  if (!snapshot || !controller) return null;
  const { state, resumable, notice } = snapshot;

  return (
    <>
      <AnimatePresence>{state.status === "preview" ? <Preview key="preview" /> : null}</AnimatePresence>
      {state.status === "active" ? <ActiveStep key={`${state.path}-${state.step}`} /> : null}
      <AnimatePresence>{state.status === "finished" ? <Finish key="finish" /> : null}</AnimatePresence>
      <AnimatePresence>
        {state.status === "idle" && resumable ? <Resume key="resume" /> : null}
      </AnimatePresence>
      <AnimatePresence>{notice ? <Notice key="notice" /> : null}</AnimatePresence>
      <AnimatePresence>{presenterOpen ? <PresenterPanel key="presenter" /> : null}</AnimatePresence>
      <Announcer />
    </>
  );
}

/** Says each step aloud to a screen reader, whatever has focus. */
function Announcer() {
  const { snapshot } = useTour();
  const [text, setText] = useState("");
  const state = snapshot?.state;
  useEffect(() => {
    if (!state) return;
    if (state.status === "active") {
      const step = PATHS[state.path].steps[state.step];
      const copy = PATH_COPY[state.path].steps[step.id];
      setText(`${UI.stepOf(state.step + 1, PATHS[state.path].steps.length)}. ${copy.title}. ${copy.body}`);
    } else if (state.status === "finished") {
      setText(PATH_COPY[state.path].finish.title);
    }
  }, [state]);
  return (
    <div className="sr-only" role="status" aria-live="polite">
      {text}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Preview: the finished result first
 * ------------------------------------------------------------------ */

function Preview() {
  const { snapshot, controller } = useTour();
  const titleId = useId();
  const dialog = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const path = snapshot!.state.path;
  const copy = PATH_COPY[path];

  useEffect(() => {
    const timer = window.setTimeout(() => startRef.current?.focus(), 30);
    return () => window.clearTimeout(timer);
  }, []);

  // Modal: Escape is "Not now", and Tab stays inside.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        controller!.dismissPreview();
      }
      if (event.key === "Tab" && dialog.current) {
        const items = Array.from(
          dialog.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]"),
        );
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [controller]);

  return (
    <motion.div
      className="fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:px-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.14 }}
    >
      <div className="absolute inset-0 bg-ink/20" onClick={() => controller!.dismissPreview()} aria-hidden />
      <div
        ref={dialog}
        data-tour-ui
        role="dialog"
        aria-modal
        aria-labelledby={titleId}
        className="relative max-h-[92vh] w-full overflow-y-auto border border-line-strong bg-panel sm:max-w-[34rem]"
      >
        <div className="px-5 pb-4 pt-5">
          <div className="text-2xs uppercase tracking-wider text-faint">{UI.tourName}</div>

          <fieldset className="mt-3">
            <legend className="text-xs text-muted">{UI.preview.choose}</legend>
            <div role="radiogroup" className="mt-1.5 grid grid-cols-2 gap-px border border-line bg-line">
              {PATH_IDS.map((id) => {
                const on = id === path;
                return (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => controller!.choosePath(id)}
                    className={`px-3 py-2 text-left transition-colors duration-150 ${
                      on ? "bg-sunken" : "bg-panel hover:bg-sunken"
                    }`}
                  >
                    <span className={`block text-sm ${on ? "text-ink" : "text-muted"}`}>
                      {PATH_COPY[id].name}
                    </span>
                    <span className="block text-xs text-muted">{PATH_COPY[id].who}</span>
                  </button>
                );
              })}
            </div>
          </fieldset>

          <h2 id={titleId} className="mt-4 font-serif text-2xl text-ink">
            {copy.preview.title}
          </h2>
          <p className="mt-1.5 text-sm text-ink-soft">{copy.preview.lede}</p>

          {/* The finished result, drawn the way the product draws it. */}
          <div className="mt-3 border border-line bg-canvas" aria-label="What you will have at the end">
            <div className="border-b border-line px-3 py-2 text-sm text-ink">{copy.preview.result.heading}</div>
            <dl>
              {copy.preview.result.rows.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between gap-3 border-b border-line px-3 py-1.5 last:border-b-0">
                  <dt className="text-xs text-muted">{row.label}</dt>
                  <dd className="tnum text-sm text-ink">{row.value}</dd>
                </div>
              ))}
            </dl>
            <div className="border-t border-line px-3 py-1.5 text-2xs text-faint">{copy.preview.result.footnote}</div>
          </div>

          <Note className="mt-3">{UI.preview.sampleNote}</Note>
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-line px-5 py-3">
          <span className="hidden items-center gap-1.5 text-2xs text-faint sm:flex">
            <Key>esc</Key>
            <span>not now</span>
          </span>
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" onClick={() => controller!.dismissPreview()}>
              {UI.preview.notNow}
            </Button>
            <button
              ref={startRef}
              type="button"
              onClick={() => controller!.start(path)}
              className="inline-flex h-7 items-center border border-accent bg-accent px-3 text-sm text-accent-ink transition-opacity duration-150 hover:opacity-85"
            >
              {UI.preview.start}
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ *
 * A step
 * ------------------------------------------------------------------ */

function toRect(box: DOMRect | undefined): Rect | null {
  return box ? { top: box.top, left: box.left, width: box.width, height: box.height } : null;
}

interface Tracked {
  rect: Rect | null;
  el: HTMLElement | null;
  keep: Rect[];
}

/** Follows the step's element, and whatever the reader is asked to look at,
 *  every frame: pages animate in, tables load, drawers slide, and the
 *  highlight has to stay on the thing. */
function useAnchorRect(anchors: string[], keep: string[] = []): Tracked {
  const [found, setFound] = useState<Tracked>({ rect: null, el: null, keep: [] });
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const hit = findAnchor(anchors);
      const rect = toRect(hit?.el.getBoundingClientRect());
      const kept = keep
        .map((id) => toRect(findAnchor([id])?.el.getBoundingClientRect()))
        .filter((r): r is Rect => r !== null);
      setFound((prev) =>
        prev.el === (hit?.el ?? null) &&
        sameRect(prev.rect, rect) &&
        prev.keep.length === kept.length &&
        prev.keep.every((r, i) => sameRect(r, kept[i]))
          ? prev
          : { rect, el: hit?.el ?? null, keep: kept },
      );
      frame = window.requestAnimationFrame(tick);
    };
    tick();
    return () => window.cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchors.join("|"), keep.join("|")]);
  return found;
}

function ActiveStep() {
  const { snapshot, controller, url } = useTour();
  const router = useRouter();
  const narrow = useNarrow();
  const reduced = useReducedMotion();
  const state = snapshot!.state;
  const path = PATHS[state.path];
  const step = path.steps[state.step];
  const copy = PATH_COPY[state.path].steps[step.id];
  const onPage = step.at.test(url);
  const { rect, el, keep } = useAnchorRect(step.anchors, step.keep);

  const [waited, setWaited] = useState(false);
  const [assisting, setAssisting] = useState(false);
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setWaited(true), 2500);
    return () => window.clearTimeout(timer);
  }, []);

  const exit = useCallback(() => controller!.exit(), [controller]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || otherDialogOpen()) return;
      event.preventDefault();
      exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [exit]);

  const assist = async () => {
    setAssisting(true);
    setStuck(false);
    const ok = await runAssist(step.assist, (target) => router.push(target));
    setAssisting(false);
    if (!ok) setStuck(true);
  };

  if (!onPage) return <Dock n={state.step + 1} onBack={() => controller!.backToStep()} onExit={exit} />;

  const missing = !rect && waited;
  if (!rect && !waited) return null;

  return (
    <>
      {rect ? <Ring rect={rect} /> : null}
      <StepPopover
        rect={missing ? null : rect}
        keep={keep}
        keepIds={step.keep ?? []}
        narrow={narrow}
        smooth={!reduced}
        heading={`${UI.tourName} · ${PATH_COPY[state.path].name} · ${UI.stepOf(state.step + 1, path.steps.length)}`}
        title={copy.title}
        body={missing ? `${copy.body} ${UI.missing}` : copy.body}
        total={path.steps.length}
        at={state.step}
        stuck={stuck}
        actions={
          <>
            <Button variant="ghost" onClick={exit}>
              {UI.exit}
            </Button>
            {"next" in step.done ? (
              <Button variant="primary" onClick={() => controller!.dispatch({ type: "next" })}>
                {UI.next}
              </Button>
            ) : (
              <Button onClick={assist} disabled={assisting}>
                {copy.assist ?? UI.showMe}
              </Button>
            )}
          </>
        }
        focusTarget={el}
        stepKey={step.id}
      />
    </>
  );
}

function Ring({ rect }: { rect: Rect }) {
  const pad = 4;
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed z-[65] outline outline-2 outline-ink"
      style={{
        top: rect.top - pad,
        left: rect.left - pad,
        width: rect.width + pad * 2,
        height: rect.height + pad * 2,
      }}
    />
  );
}

function StepPopover({
  rect,
  keep,
  keepIds,
  narrow,
  smooth,
  heading,
  title,
  body,
  total,
  at,
  stuck,
  actions,
  focusTarget,
  stepKey,
}: {
  rect: Rect | null;
  keep: Rect[];
  keepIds: string[];
  narrow: boolean;
  smooth: boolean;
  heading: string;
  title: string;
  body: string;
  total: number;
  at: number;
  stuck: boolean;
  actions: ReactNode;
  focusTarget: HTMLElement | null;
  stepKey: string;
}) {
  const titleId = useId();
  const bodyId = useId();
  const box = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  // A guess until the popover has been measured; nothing is scrolled on it.
  const [size, setSize] = useState({ width: 352, height: 180, measured: false });

  useLayoutEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.target.getBoundingClientRect();
      setSize((prev) =>
        prev.measured && Math.round(prev.width) === Math.round(width) && Math.round(prev.height) === Math.round(height)
          ? prev
          : { width, height, measured: true },
      );
    });
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    focusIfFree(titleRef.current);
  }, [stepKey]);

  // On a phone the popover is a sheet over the foot of the screen. The page
  // gets that much room below it, and the element is scrolled clear of it.
  const sheet = narrow && size.measured ? Math.round(size.height) : 0;
  useEffect(() => (sheet ? reserveSheet(sheet) : undefined), [sheet]);
  const revealed = useRef<string | null>(null);
  useEffect(() => {
    if (!focusTarget || !size.measured) return;
    const key = `${stepKey}:${sheet}`;
    if (revealed.current === key) return;
    revealed.current = key;
    // After the page has laid out the room the sheet asked for.
    const frame = window.requestAnimationFrame(() => reveal(focusTarget, sheet, smooth));
    // What the step asks the reader to look at may still be opening (a
    // disclosure animates for 200ms), so it is brought into view after that.
    const later = window.setTimeout(() => {
      const kept = keepIds.map((id) => findAnchor([id])?.el).filter((e): e is HTMLElement => !!e);
      revealKept(focusTarget, kept, sheet, smooth);
    }, 260);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(later);
    };
  }, [focusTarget, stepKey, sheet, smooth, size.measured]);

  const position = narrow ? null : place(rect, size.width, size.height, keep);

  return (
    <div
      ref={box}
      data-tour-ui
      role="dialog"
      aria-modal={false}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      className={`fixed z-[70] border border-line-strong bg-panel ${
        narrow ? "inset-x-0 bottom-0 max-h-[42vh] overflow-y-auto border-x-0 border-b-0" : "w-[22rem] max-w-[calc(100vw-2rem)]"
      }`}
      style={position ? { top: position.top, left: position.left } : undefined}
    >
      <div className="px-4 pb-3 pt-3.5">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate text-2xs uppercase tracking-wider text-faint">{heading}</span>
          <Progress total={total} at={at} />
        </div>
        <h2 id={titleId} ref={titleRef} tabIndex={-1} className="mt-1.5 text-base text-ink focus-visible:outline-none">
          {title}
        </h2>
        <p id={bodyId} className="mt-1 text-sm leading-relaxed text-ink-soft">
          {body}
        </p>
        {stuck ? (
          <Note tone="warn" className="mt-2">
            That didn&apos;t work on this screen. Try the highlighted control directly, or exit and replay.
          </Note>
        ) : null}
        {focusTarget ? (
          <button
            type="button"
            onClick={() => {
              const control = focusTarget.matches("button, a, input, textarea, select")
                ? focusTarget
                : focusTarget.querySelector<HTMLElement>("button, a, input, textarea, select");
              (control ?? focusTarget).focus();
            }}
            className="sr-only text-xs text-muted underline focus:not-sr-only focus:mt-2 focus:inline-block"
          >
            Move focus to the highlighted control
          </button>
        ) : null}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5">
        <span className="hidden items-center gap-1.5 text-2xs text-faint sm:flex">
          <Key>esc</Key>
          <span>exit</span>
        </span>
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </div>
    </div>
  );
}

/** Off the step's page: the tour steps back to a strip and offers the way back. */
function Dock({ n, onBack, onExit }: { n: number; onBack: () => void; onExit: () => void }) {
  return (
    <div
      data-tour-ui
      role="region"
      aria-label={UI.tourName}
      className="fixed inset-x-0 bottom-0 z-[70] flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line bg-panel px-4 py-2.5 sm:inset-x-auto sm:bottom-4 sm:right-4 sm:max-w-[26rem] sm:border sm:border-line-strong"
    >
      <p className="min-w-0 flex-1 text-xs text-muted">{UI.dock.paused(n)}</p>
      <div className="flex items-center gap-2">
        <Button variant="ghost" onClick={onExit}>
          {UI.exit}
        </Button>
        <Button onClick={onBack}>{UI.dock.back(n)}</Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * The end, a resume, a notice
 * ------------------------------------------------------------------ */

function Finish() {
  const { snapshot, controller } = useTour();
  const narrow = useNarrow();
  const titleId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const path = snapshot!.state.path;
  const other: PathId = path === "lead" ? "expert" : "lead";
  const copy = PATH_COPY[path];

  // The end of the tour is the thing the last step showed -- the model's
  // answer, the package manifest. The card sits on the other side of the
  // screen from it, and on a phone the page is scrolled so it shows above.
  const [side, setSide] = useState<"left" | "right">("left");
  useEffect(() => {
    const last = PATHS[path].steps[PATHS[path].steps.length - 1];
    const hit = findAnchor(last.anchors);
    if (!hit) return;
    const r = hit.el.getBoundingClientRect();
    setSide(r.left + r.width / 2 < window.innerWidth / 2 ? "right" : "left");
    if (!narrow || !box.current) return;
    const panel = box.current.closest<HTMLElement>("[data-tour-ui]") ?? box.current;
    const height = panel.getBoundingClientRect().height;
    const release = reserveSheet(height);
    const frame = window.requestAnimationFrame(() => reveal(hit.el, height, true));
    return () => {
      window.cancelAnimationFrame(frame);
      release();
    };
  }, [path, narrow]);

  useEffect(() => {
    const timer = window.setTimeout(() => focusIfFree(titleRef.current), 60);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !otherDialogOpen()) controller!.exit();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [controller]);

  return (
    <Panel
      labelledBy={titleId}
      className={`fixed inset-x-0 bottom-0 border-x-0 border-b-0 sm:inset-x-auto sm:bottom-4 sm:w-[24rem] sm:border ${
        side === "left" ? "sm:left-4" : "sm:right-4"
      }`}
    >
      <div ref={box} className="px-4 pb-3 pt-3.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-2xs uppercase tracking-wider text-faint">
            {UI.tourName} · {copy.name}
          </span>
          <Progress total={PATHS[path].steps.length} at={PATHS[path].steps.length} />
        </div>
        <h2 id={titleId} ref={titleRef} tabIndex={-1} className="mt-1.5 font-serif text-xl text-ink focus-visible:outline-none">
          {copy.finish.title}
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-soft">{copy.finish.body}</p>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-4 py-2.5">
        <Button variant="ghost" onClick={() => controller!.replay(path)}>
          {UI.finish.replay}
        </Button>
        <Button onClick={() => controller!.openPreview(other)}>{UI.finish.other(PATH_COPY[other].name)}</Button>
        <Button variant="primary" onClick={() => controller!.exit()}>
          {UI.finish.exit}
        </Button>
      </div>
    </Panel>
  );
}

function Resume() {
  const { snapshot, controller } = useTour();
  const { path, step } = snapshot!.resumable!;
  return (
    <Panel
      label={UI.tourName}
      className="fixed inset-x-0 bottom-0 border-x-0 border-b-0 sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-[24rem] sm:border"
    >
      <p className="px-4 pt-3 text-sm text-ink">
        {UI.resume.text(PATH_COPY[path].name, step + 1, PATHS[path].steps.length)}
      </p>
      <div className="flex flex-wrap items-center justify-end gap-2 px-4 pb-3 pt-2.5">
        <Button variant="ghost" onClick={() => controller!.dismissResume()}>
          {UI.resume.dismiss}
        </Button>
        <Button onClick={() => controller!.replay(path)}>{UI.resume.over}</Button>
        <Button variant="primary" onClick={() => controller!.resume()}>
          {UI.resume.resume}
        </Button>
      </div>
    </Panel>
  );
}

function Notice() {
  const { controller } = useTour();
  useEffect(() => {
    const timer = window.setTimeout(() => controller!.clearNotice(), 5000);
    return () => window.clearTimeout(timer);
  }, [controller]);
  return (
    <motion.div
      data-tour-ui
      role="status"
      className="fixed bottom-4 left-1/2 z-[70] w-[calc(100%-2rem)] max-w-[26rem] -translate-x-1/2 border border-line-strong bg-panel px-4 py-2.5"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <Note>{UI.exited}</Note>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ *
 * Presenter
 * ------------------------------------------------------------------ */

function PresenterPanel() {
  const { snapshot, controller, setPresenterOpen } = useTour();
  const state = snapshot!.state;
  const titleId = useId();
  const [tab, setTab] = useState<PathId>(state.path);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPresenterOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPresenterOpen]);

  const current = (path: PathId, index: number) =>
    state.status === "active" && state.path === path && state.step === index;

  return (
    <Panel
      labelledBy={titleId}
      className="fixed inset-x-0 bottom-0 max-h-[70vh] overflow-y-auto border-x-0 border-b-0 sm:inset-x-auto sm:bottom-4 sm:left-4 sm:w-[22rem] sm:border"
    >
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <h2 id={titleId} className="text-sm text-ink">
          {UI.presenter.title}
        </h2>
        <Button variant="ghost" onClick={() => setPresenterOpen(false)}>
          {UI.presenter.close}
        </Button>
      </div>
      <p className="px-4 pt-2.5 text-xs text-muted">{UI.presenter.lede}</p>
      <div className="flex gap-px px-4 pt-2.5" role="tablist">
        {PATH_IDS.map((id) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`h-7 flex-1 border px-2.5 text-sm ${
              tab === id ? "border-line-strong bg-sunken text-ink" : "border-line text-muted hover:text-ink"
            }`}
          >
            {PATH_COPY[id].name}
          </button>
        ))}
      </div>
      <ol className="px-4 py-2.5" role="tabpanel">
        <li>
          <button
            type="button"
            onClick={() => controller!.openPreview(tab)}
            className="flex w-full items-baseline gap-2 px-1.5 py-1 text-left text-sm text-muted hover:bg-sunken hover:text-ink"
          >
            <span className="tnum w-4 font-mono text-2xs text-faint">0</span>
            {UI.presenter.preview}
          </button>
        </li>
        {PATHS[tab].steps.map((step, index) => (
          <li key={step.id}>
            <button
              type="button"
              aria-current={current(tab, index) ? "step" : undefined}
              onClick={() => controller!.jump(tab, index, "presenter")}
              className={`flex w-full items-baseline gap-2 px-1.5 py-1 text-left text-sm hover:bg-sunken ${
                current(tab, index) ? "bg-sunken text-ink" : "text-ink-soft"
              }`}
            >
              <span className="tnum w-4 font-mono text-2xs text-faint">{index + 1}</span>
              {PATH_COPY[tab].steps[step.id].title}
            </button>
          </li>
        ))}
      </ol>
      <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5">
        <code className="truncate font-mono text-2xs text-faint">?tour={tab}&amp;step=N</code>
        <Button
          onClick={() =>
            state.status === "active" || state.status === "finished"
              ? controller!.jump(state.path, state.step, "presenter")
              : controller!.jump(tab, 0, "presenter")
          }
        >
          {UI.presenter.reset}
        </Button>
      </div>
    </Panel>
  );
}
