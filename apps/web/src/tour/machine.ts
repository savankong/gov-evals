/**
 * Step logic, with no React and no browser in it.
 *
 * A step is done when the reader does the thing it asks for. The only other
 * rule is how far one action may carry the tour:
 *
 *   - A signal (a disclosure opened, a field filled in) finishes the current
 *     step and nothing else. The same signal can belong to a later step --
 *     both paths open the model's answer -- and doing it early must not skip
 *     the reader past everything in between.
 *   - A route or a successful request is progress that has happened, so it
 *     may finish a later step too, and the tour catches up with the reader
 *     rather than sending them back.
 */

import type { Completion, PathDef, TourEvent, TourState } from "./types";

export function matches(done: Completion, event: TourEvent): boolean {
  if ("route" in done) return event.type === "route" && done.route.test(event.url);
  if ("request" in done) {
    if (event.type !== "request") return false;
    const [method, path] = done.request.split(" ");
    return event.method.toUpperCase() === method && event.path.split("?")[0] === path;
  }
  if ("signal" in done) return event.type === "signal" && event.name === done.signal;
  return event.type === "next";
}

export interface Advance {
  state: TourState;
  /** Indices of the steps this event finished, in order. Empty if none. */
  completed: number[];
  finished: boolean;
}

export function advance(state: TourState, event: TourEvent, path: PathDef): Advance {
  const unchanged = { state, completed: [], finished: false };
  if (state.status !== "active") return unchanged;
  const steps = path.steps;

  let hit = -1;
  if (matches(steps[state.step].done, event)) hit = state.step;
  else if (event.type === "route" || event.type === "request") {
    for (let i = state.step + 1; i < steps.length; i++) {
      const done = steps[i].done;
      if (("route" in done || "request" in done) && matches(done, event)) {
        hit = i;
        break;
      }
    }
  }
  if (hit < 0) return unchanged;

  const completed = Array.from({ length: hit - state.step + 1 }, (_, i) => state.step + i);
  const next = hit + 1;
  if (next >= steps.length) {
    return { state: { ...state, status: "finished", step: steps.length - 1 }, completed, finished: true };
  }
  return { state: { ...state, step: next }, completed, finished: false };
}
