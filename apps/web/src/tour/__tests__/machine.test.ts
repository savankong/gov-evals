import { describe, expect, it } from "vitest";

import { advance, matches } from "../machine";
import { PATHS } from "../steps";
import type { TourState } from "../types";

const lead = PATHS.lead;
const expert = PATHS.expert;
const at = (path: "lead" | "expert", step: number): TourState => ({ status: "active", path, step });

describe("matches", () => {
  it("matches a request by method and path, ignoring the query", () => {
    const done = { request: "POST /data-packages" };
    expect(matches(done, { type: "request", method: "post", path: "/data-packages?x=1" })).toBe(true);
    expect(matches(done, { type: "request", method: "GET", path: "/data-packages" })).toBe(false);
    expect(matches(done, { type: "request", method: "POST", path: "/reasoning-traces" })).toBe(false);
  });

  it("matches a next only for a step that asks for one", () => {
    expect(matches({ next: true }, { type: "next" })).toBe(true);
    expect(matches({ signal: "x" }, { type: "next" })).toBe(false);
  });
});

describe("advance", () => {
  it("moves on when the reader does what the step asks", () => {
    const result = advance(at("lead", 0), { type: "route", url: "/weakness" }, lead);
    expect(result.completed).toEqual([0]);
    expect(result.state).toEqual(at("lead", 1));
  });

  it("does not move on for anything else", () => {
    for (const event of [
      { type: "route" as const, url: "/datasets" },
      { type: "signal" as const, name: "weakness.threshold:0.7" },
      { type: "next" as const },
      { type: "request" as const, method: "GET", path: "/weakness-map" },
    ]) {
      const result = advance(at("lead", 1), event, lead);
      expect(result.completed).toEqual([]);
      expect(result.state).toEqual(at("lead", 1));
    }
  });

  it("catches up with a reader who got ahead by a route", () => {
    // From "open the weakness map", straight to the problem page.
    const result = advance(
      at("lead", 0),
      { type: "route", url: "/capture/sample-ss-discussions" },
      lead,
    );
    expect(result.completed).toEqual([0, 1, 2, 3]);
    expect(result.state.step).toBe(4);
  });

  it("catches up with a reader who got ahead by a request", () => {
    // Wrote a step and recorded the trace before the typing pause elapsed.
    const result = advance(
      at("expert", 3),
      { type: "request", method: "POST", path: "/reasoning-traces" },
      expert,
    );
    expect(result.completed).toEqual([3, 4]);
    expect(result.state.step).toBe(5);
  });

  it("never lets a signal skip ahead", () => {
    // Opening the model's answer early is the last expert step's signal; it
    // must not carry a reader on step 3 to the end.
    const result = advance(at("expert", 2), { type: "signal", name: "solve.model-answer:opened" }, expert);
    expect(result.completed).toEqual([]);
    expect(result.state.step).toBe(2);
  });

  it("finishes on the last step", () => {
    const last = lead.steps.length - 1;
    const result = advance(at("lead", last), { type: "request", method: "POST", path: "/data-packages" }, lead);
    expect(result.finished).toBe(true);
    expect(result.state.status).toBe("finished");
  });

  it("does nothing unless a tour is running", () => {
    for (const status of ["idle", "preview", "finished"] as const) {
      const state: TourState = { status, path: "lead", step: 0 };
      expect(advance(state, { type: "route", url: "/weakness" }, lead).state).toBe(state);
    }
  });
});
