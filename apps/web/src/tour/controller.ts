/**
 * The tour, without React.
 *
 * Owns the tour's state, the sample, and the transport that answers requests
 * from the sample while the tour is on. The provider renders what this holds;
 * the tests drive it directly. Starting, resuming, replaying and a presenter's
 * jump are all the same operation -- seed the sample for a step, switch the
 * app onto it, go to where the step happens -- so a step can be entered from
 * anywhere and look the same every time.
 */

import type { Transport } from "@/lib/api";

import type { Tracker } from "./analytics";
import { advance } from "./machine";
import { NOT_IN_SAMPLE, handle } from "./sandbox/handlers";
import {
  loadSnapshot,
  saveSnapshot,
  seed,
  type KeyValueStore,
  type SandboxData,
} from "./sandbox/store";
import { PATHS } from "./steps";
import { PATH_IDS, type Effect, type PathId, type TourEvent, type TourState } from "./types";

export interface ControllerDeps {
  navigate: (url: string) => void;
  /** Pathname plus query, e.g. "/capture?area=x". */
  currentUrl: () => string;
  setTransport: (transport: Transport | null) => void;
  /** This tab: the running tour and its sample. */
  session: KeyValueStore | null;
  /** This browser, per user: where they got to, for resume. */
  local: KeyValueStore | null;
  track: Tracker;
}

export interface Progress {
  path: PathId;
  step: number;
  status: "active" | "dismissed" | "completed";
}

export interface TourSnapshot {
  state: TourState;
  /** Changes whenever the app switches between real and sample data, so the
   *  shell can remount the page and nothing loaded from one is shown under
   *  the other. */
  epoch: number;
  sampleOn: boolean;
  resumable: { path: PathId; step: number } | null;
  notice: string | null;
  defaultPath: PathId;
}

const TAB_KEY = "aegis.tour.tab";
const PROGRESS_PREFIX = "aegis.tour.v1:";

const IDLE: TourState = { status: "idle", path: "lead", step: 0 };

/** What the server rendered: no tour, no sample. The page hydrates against
 *  this and only then shows a tour picked up from this tab, so the first
 *  client render matches the HTML it is hydrating. */
export const SERVER_SNAPSHOT: TourSnapshot = {
  state: IDLE,
  epoch: 0,
  sampleOn: false,
  resumable: null,
  notice: null,
  defaultPath: "lead",
};

function read<T>(storage: KeyValueStore | null, key: string): T | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(storage: KeyValueStore | null, key: string, value: unknown): void {
  if (!storage) return;
  try {
    if (value === null) storage.removeItem(key);
    else storage.setItem(key, JSON.stringify(value));
  } catch {
    /* per-viewer convenience only; the tour still runs */
  }
}

function validState(value: unknown): value is TourState {
  const s = value as TourState | null;
  return (
    !!s &&
    PATH_IDS.includes(s.path) &&
    (s.status === "active" || s.status === "finished") &&
    Number.isInteger(s.step) &&
    s.step >= 0 &&
    s.step < PATHS[s.path].steps.length
  );
}

export function validProgress(value: unknown): value is Progress {
  const p = value as Progress | null;
  return (
    !!p &&
    PATH_IDS.includes(p.path) &&
    ["active", "dismissed", "completed"].includes(p.status) &&
    Number.isInteger(p.step) &&
    p.step >= 0 &&
    p.step < PATHS[p.path].steps.length
  );
}

function isSamplePage(pathname: string): boolean {
  return /\/sample-[^/]*/.test(pathname);
}

/** The effects every step before `index` leaves behind. */
export function effectsBefore(path: PathId, index: number): Effect[] {
  return PATHS[path].steps.slice(0, index).flatMap((step) => step.leaves ?? []);
}

export class TourController {
  private deps: ControllerDeps;
  private state: TourState = IDLE;
  private data: SandboxData | null = null;
  private epoch = 0;
  private suspended = false;
  private user: string | null = null;
  private fallbackPath: PathId = "lead";
  private resumable: { path: PathId; step: number } | null = null;
  private notice: string | null = null;
  private listeners = new Set<() => void>();
  private snapshot: TourSnapshot;

  constructor(deps: ControllerDeps) {
    this.deps = deps;
    this.snapshot = this.build();
  }

  /* -- reading --------------------------------------------------------- */

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): TourSnapshot => this.snapshot;

  /** The sample as it stands. Tests read it; nothing else should need to. */
  sample(): SandboxData | null {
    return this.data;
  }

  readSeed = (key: string): unknown => this.data?.ui[key] ?? null;

  private build(): TourSnapshot {
    return {
      state: this.state,
      epoch: this.epoch,
      sampleOn: this.data !== null && !this.suspended,
      resumable: this.resumable,
      notice: this.notice,
      defaultPath: this.fallbackPath,
    };
  }

  private changed(): void {
    this.snapshot = this.build();
    for (const listener of this.listeners) listener();
  }

  /* -- the sample ------------------------------------------------------ */

  /** Answers requests from the sample. Never calls the network: anything the
   *  sample does not know is refused, not passed on. */
  readonly transport: Transport = async (path, init) => {
    const method = (init.method ?? "GET").toUpperCase();
    const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json", ...headers },
      });
    if (!this.data) return json(404, { detail: NOT_IN_SAMPLE });

    let body: unknown;
    if (typeof init.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        return json(400, { detail: "The request body is not JSON." });
      }
    } else if (init.body) {
      // An upload. The sample has nowhere to put a file.
      return json(404, { detail: NOT_IN_SAMPLE });
    }

    const result = handle(this.data, method, path, body);
    if (method !== "GET") saveSnapshot(this.deps.session, this.data);
    const response =
      result.text !== undefined
        ? new Response(result.text, { status: result.status, headers: result.headers })
        : json(result.status, result.body ?? null, result.headers);
    if (result.status < 400 && method !== "GET") {
      // After the caller has its response, as the server's would arrive.
      queueMicrotask(() => this.dispatch({ type: "request", method, path }));
    }
    return response;
  };

  /** Set while stepping off a sample-only page: the sample stays in place
   *  until the reader has arrived somewhere real, so the page being left is
   *  never asked for from the server. */
  private leaving = false;

  /** Leave the sample. A sample record's page means nothing without it, so
   *  from one the reader goes back to the list it came from rather than to a
   *  404, and the switch to real data waits until they get there. */
  private leaveSample(): void {
    const [path] = this.deps.currentUrl().split("?");
    if (this.data && isSamplePage(path)) {
      this.leaving = true;
      this.deps.navigate(path.replace(/\/sample-[^/]*.*$/, "") || "/");
      return;
    }
    this.disengage();
  }

  private engage(data: SandboxData): void {
    this.data = data;
    saveSnapshot(this.deps.session, data);
    if (!this.suspended) this.deps.setTransport(this.transport);
    this.epoch += 1;
  }

  private disengage(): void {
    this.leaving = false;
    const was = this.data !== null;
    this.data = null;
    this.deps.setTransport(null);
    saveSnapshot(this.deps.session, null);
    write(this.deps.session, TAB_KEY, null);
    if (was) this.epoch += 1;
  }

  /** Off the app's own pages (sign-in, public reports) the sample steps aside
   *  and those pages talk to the server as usual. */
  setSuspended(suspended: boolean): void {
    if (suspended === this.suspended) return;
    this.suspended = suspended;
    this.deps.setTransport(this.data && !suspended ? this.transport : null);
    this.changed();
  }

  /* -- lifecycle ------------------------------------------------------- */

  /** Pick the tour back up in this tab after a reload. Synchronous, so the
   *  transport is in place before any page on screen asks for data. */
  restoreTab(): boolean {
    const state = read<TourState>(this.deps.session, TAB_KEY);
    const data = loadSnapshot(this.deps.session);
    if (!validState(state) || !data) {
      write(this.deps.session, TAB_KEY, null);
      saveSnapshot(this.deps.session, null);
      return false;
    }
    this.state = state;
    this.data = data;
    if (!this.suspended) this.deps.setTransport(this.transport);
    this.snapshot = this.build();
    return true;
  }

  /** Who is looking, and what they can do. Decides whether to offer the
   *  preview (never seen it), a resume (left part way), or nothing. */
  identify(user: string, defaultPath: PathId, options: { offer?: boolean } = {}): void {
    const offer = options.offer ?? true;
    if (this.user !== null && this.user !== user) {
      // Someone else signed in on this tab. The last person's tour is theirs.
      this.disengage();
      this.state = IDLE;
      this.resumable = null;
    }
    this.user = user;
    this.fallbackPath = defaultPath;
    if (this.state.status === "active" || this.state.status === "finished") {
      this.changed();
      return;
    }
    const progress = this.progress();
    if (!progress) {
      if (offer) this.state = { status: "preview", path: defaultPath, step: 0 };
    } else if (progress.status === "active") {
      this.resumable = { path: progress.path, step: progress.step };
    }
    this.changed();
  }

  private progressKey(): string | null {
    return this.user ? `${PROGRESS_PREFIX}${this.user}` : null;
  }

  progress(): Progress | null {
    const key = this.progressKey();
    const value = key ? read<Progress>(this.deps.local, key) : null;
    return validProgress(value) ? value : null;
  }

  private saveProgress(status: Progress["status"]): void {
    const key = this.progressKey();
    if (!key) return;
    write(this.deps.local, key, { path: this.state.path, step: this.state.step, status });
  }

  private saveTab(): void {
    write(this.deps.session, TAB_KEY, this.state.status === "active" || this.state.status === "finished" ? this.state : null);
  }

  openPreview(path?: PathId): void {
    this.leaveSample();
    this.resumable = null;
    this.notice = null;
    this.state = { status: "preview", path: path ?? this.fallbackPath, step: 0 };
    this.changed();
  }

  choosePath(path: PathId): void {
    if (this.state.status !== "preview") return;
    this.state = { ...this.state, path };
    this.changed();
  }

  dismissPreview(): void {
    if (this.state.status !== "preview") return;
    this.deps.track("tour_skipped", { path: this.state.path, at: "preview" });
    this.state = { ...this.state, status: "idle" };
    this.saveProgress("dismissed");
    this.changed();
  }

  start(path: PathId, source = "preview"): void {
    this.enter(path, 0, source, false);
  }

  /** Straight to a step, with the sample in the state the earlier steps would
   *  have left it. Used by presenter mode and by resume. */
  jump(path: PathId, index: number, source = "presenter"): void {
    this.enter(path, index, source, true);
  }

  resume(): void {
    if (!this.resumable) return;
    const { path, step } = this.resumable;
    this.enter(path, step, "resume", true);
  }

  dismissResume(): void {
    if (!this.resumable) return;
    this.resumable = null;
    this.saveProgress("dismissed");
    this.changed();
  }

  private enter(path: PathId, index: number, source: string, alwaysNavigate: boolean): void {
    const steps = PATHS[path].steps;
    const step = Math.max(0, Math.min(index, steps.length - 1));
    this.disengage();
    this.engage(seed(effectsBefore(path, step)));
    this.resumable = null;
    this.notice = null;
    this.state = { status: "active", path, step };
    this.saveTab();
    this.saveProgress("active");
    this.deps.track(source === "presenter" ? "tour_jumped" : "tour_started", { path, step: step + 1, source });
    this.changed();
    const target = steps[step];
    if (alwaysNavigate || !target.at.test(this.deps.currentUrl())) this.deps.navigate(target.route);
  }

  /** Start the reader's path over from the preview, with a fresh sample. */
  replay(path?: PathId): void {
    this.openPreview(path ?? (this.state.status === "idle" ? this.fallbackPath : this.state.path));
  }

  exit(): void {
    const { status, path, step } = this.state;
    if (status === "active") {
      this.deps.track("tour_skipped", { path, step: step + 1, stepId: PATHS[path].steps[step].id });
      this.saveProgress("dismissed");
      this.notice = "exited";
    } else if (status === "finished") {
      this.saveProgress("completed");
    } else if (status === "preview") {
      this.dismissPreview();
    }
    this.leaveSample();
    this.state = { ...this.state, status: "idle" };
    this.changed();
  }

  clearNotice(): void {
    if (this.notice === null) return;
    this.notice = null;
    this.changed();
  }

  backToStep(): void {
    if (this.state.status !== "active") return;
    this.deps.navigate(PATHS[this.state.path].steps[this.state.step].route);
  }

  /* -- progress -------------------------------------------------------- */

  dispatch = (event: TourEvent): void => {
    if (this.leaving && event.type === "route" && !isSamplePage(event.url.split("?")[0])) {
      this.disengage();
      this.changed();
      return;
    }
    if (this.state.status !== "active" || this.suspended) return;
    const path = PATHS[this.state.path];
    const result = advance(this.state, event, path);
    if (!result.completed.length) return;
    for (const index of result.completed) {
      this.deps.track("tour_step_completed", {
        path: path.id,
        step: index + 1,
        stepId: path.steps[index].id,
        skippedAhead: index !== result.completed[result.completed.length - 1] ? true : undefined,
      });
    }
    this.state = result.state;
    if (result.finished) {
      this.deps.track("tour_finished", { path: path.id });
      this.saveProgress("completed");
    } else {
      this.saveProgress("active");
    }
    this.saveTab();
    this.changed();
  };
}
