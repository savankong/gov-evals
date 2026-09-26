/**
 * The shapes the tour is built from.
 *
 * A tour is a list of steps per path. Each step names the real element it
 * points at, where in the app it happens, what the reader has to *do* for it to
 * count as done, and how to get there if they are lost. The words live apart,
 * in copy.ts, so they can be edited without touching any of this.
 */

export type PathId = "lead" | "expert";

export const PATH_IDS: readonly PathId[] = ["lead", "expert"];

/** What finishes a step. Wherever possible it is something the reader did in
 *  the product, not a button in the popover. */
export type Completion =
  /** The reader arrived at a URL (pathname plus query) matching this. */
  | { route: RegExp }
  /** The sample answered this request successfully, e.g. "POST /data-packages". */
  | { request: string }
  /** A screen reported something happened that has no URL or request, such as
   *  opening a disclosure. Screens call `tourSignal(name)`; it is a no-op when
   *  the tour is off. */
  | { signal: string }
  /** Nothing to do but read. Used as sparingly as possible. */
  | { next: true };

/** How "Show me" gets there when the reader is stuck. Run in order. */
export type Assist =
  | { click: string }
  | { navigate: string }
  | { command: string; payload?: unknown };

/** Sample state a step leaves behind once it is done. A presenter jumping
 *  past the step gets it applied directly, so step N always starts from the
 *  state steps 1..N-1 would have produced. */
export type Effect = "expert.trace-recorded" | "lead.package-built";

export interface StepDef {
  id: string;
  /** `data-tour` values to point at, first visible one wins. A later entry is
   *  the fallback, e.g. the "Open navigation" button when the rail is a drawer. */
  anchors: string[];
  /** Where the step happens. Off this, the tour docks and offers the way back. */
  at: RegExp;
  /** Where setup takes the reader, for a jump, a resume or "Back to step". */
  route: string;
  done: Completion;
  /** What the reader is asked to look at, which the popover must not cover. */
  keep?: string[];
  assist: Assist[];
  leaves?: Effect[];
}

export interface PathDef {
  id: PathId;
  steps: StepDef[];
}

export type TourStatus = "idle" | "preview" | "active" | "finished";

export interface TourState {
  status: TourStatus;
  path: PathId;
  /** Index into the path's steps. Meaningful while active. */
  step: number;
}

export type TourEvent =
  | { type: "route"; url: string }
  | { type: "request"; method: string; path: string }
  | { type: "signal"; name: string }
  | { type: "next" };
