import { describe, expect, it } from "vitest";

import { effectsBefore } from "../controller";
import { SOURCE_SELECTION, TARGET_SCENARIO, WORKED_EXAMPLE } from "../sandbox/fixtures";
import { seed } from "../sandbox/store";
import { PATHS } from "../steps";
import { PATH_IDS } from "../types";
import { harness, tick } from "./helpers";

const PROBLEM = `/capture/${TARGET_SCENARIO}`;
const AREA = `/capture?area=${encodeURIComponent(SOURCE_SELECTION)}`;

function events(track: ReturnType<typeof harness>["track"]) {
  return track.mock.calls.map(([name, props]) => ({ name, ...(props as object) }));
}

describe("first run", () => {
  it("offers the preview to someone who has never seen it", () => {
    const h = harness();
    h.controller.identify("a@x", "expert");
    expect(h.controller.getSnapshot().state).toEqual({ status: "preview", path: "expert", step: 0 });
  });

  it("does not offer it off the portfolio, or again once dismissed", () => {
    const h = harness("/datasets");
    h.controller.identify("a@x", "lead", { offer: false });
    expect(h.controller.getSnapshot().state.status).toBe("idle");

    h.controller.identify("a@x", "lead");
    h.controller.dismissPreview();
    expect(events(h.track)).toContainEqual(expect.objectContaining({ name: "tour_skipped", at: "preview" }));
    h.controller.identify("a@x", "lead");
    expect(h.controller.getSnapshot().state.status).toBe("idle");
  });

  it("switches the app onto the sample only when the tour starts", () => {
    const h = harness();
    h.controller.identify("a@x", "lead");
    expect(h.setTransport).not.toHaveBeenCalledWith(h.controller.transport);
    const before = h.controller.getSnapshot().epoch;
    h.controller.start("lead");
    expect(h.setTransport).toHaveBeenLastCalledWith(h.controller.transport);
    expect(h.controller.getSnapshot().sampleOn).toBe(true);
    expect(h.controller.getSnapshot().epoch).toBeGreaterThan(before);
    expect(events(h.track)).toContainEqual(expect.objectContaining({ name: "tour_started", path: "lead", step: 1 }));
  });
});

describe("a whole path, done the way a reader does it", () => {
  it("lead: weakness map to a built package", async () => {
    const h = harness();
    h.controller.identify("a@x", "lead");
    h.controller.start("lead");
    const step = () => h.controller.getSnapshot().state.step;

    h.go("/weakness");
    expect(step()).toBe(1);
    h.controller.dispatch({ type: "signal", name: "weakness.threshold:0.9" });
    expect(step()).toBe(2);
    h.go(AREA);
    expect(step()).toBe(3);
    h.go(PROBLEM);
    expect(step()).toBe(4);
    h.controller.dispatch({ type: "signal", name: "solve.model-answer:opened" });
    expect(step()).toBe(5);
    h.go("/packages");
    expect(step()).toBe(5);

    const response = await h.request("POST", "/data-packages", {
      name: "Source selection",
      knowledge_areas: [SOURCE_SELECTION],
    });
    expect(response.status).toBe(201);
    await tick();
    expect(h.controller.getSnapshot().state.status).toBe("finished");

    const names = events(h.track).map((e) => e.name);
    expect(names.filter((n) => n === "tour_step_completed")).toHaveLength(PATHS.lead.steps.length);
    expect(names).toContain("tour_finished");
    expect(h.controller.progress()).toEqual({ path: "lead", step: 5, status: "completed" });
  });

  it("expert: solve blind, record, then compare", async () => {
    const h = harness();
    h.controller.identify("a@x", "expert");
    h.controller.start("expert");
    const step = () => h.controller.getSnapshot().state.step;

    h.go("/capture");
    h.go(PROBLEM);
    expect(step()).toBe(2);
    h.controller.dispatch({ type: "signal", name: "solve.document:opened" });
    h.controller.dispatch({ type: "signal", name: "solve.step-written" });
    expect(step()).toBe(4);

    const response = await h.request("POST", "/reasoning-traces", {
      scenario_id: TARGET_SCENARIO,
      steps: WORKED_EXAMPLE.steps,
      final_answer: WORKED_EXAMPLE.answer,
      sources: [],
      expertise: "acquisition",
    });
    const trace = (await response.json()) as { qualified: boolean; content_hash: string };
    expect(trace.qualified).toBe(true);
    expect(trace.content_hash).toMatch(/^[0-9a-f]{64}$/);
    await tick();
    expect(step()).toBe(5);

    h.controller.dispatch({ type: "signal", name: "solve.model-answer:opened" });
    expect(h.controller.getSnapshot().state.status).toBe("finished");
  });

  it("a failed request does not count", async () => {
    const h = harness();
    h.controller.jump("lead", 5);
    const response = await h.request("POST", "/data-packages", { name: "x", knowledge_areas: ["Nothing"] });
    expect(response.status).toBe(422);
    await tick();
    expect(h.controller.getSnapshot().state).toMatchObject({ status: "active", step: 5 });
  });
});

describe("leaving", () => {
  it("exit puts the app back on real data and forgets the sample", () => {
    const h = harness();
    h.controller.identify("a@x", "lead");
    h.controller.start("lead");
    h.go("/weakness");
    const epoch = h.controller.getSnapshot().epoch;

    h.controller.exit();
    const snap = h.controller.getSnapshot();
    expect(snap.state.status).toBe("idle");
    expect(snap.sampleOn).toBe(false);
    expect(snap.epoch).toBeGreaterThan(epoch);
    expect(h.controller.sample()).toBeNull();
    expect(h.setTransport).toHaveBeenLastCalledWith(null);
    expect(h.session.map.size).toBe(0);
    expect(events(h.track)).toContainEqual(
      expect.objectContaining({ name: "tour_skipped", path: "lead", step: 2, stepId: "raise-bar" }),
    );
    expect(h.controller.progress()?.status).toBe("dismissed");
  });

  it("never leaves the reader on a page that only existed in the sample", () => {
    const h = harness();
    h.controller.start("expert");
    h.go(PROBLEM);
    h.controller.exit();
    expect(h.navigate).toHaveBeenLastCalledWith("/capture");
    // The page being left must not be asked for from the server: the sample
    // stays until the reader has arrived.
    expect(h.controller.getSnapshot().sampleOn).toBe(true);
    h.go("/capture");
    expect(h.controller.getSnapshot().sampleOn).toBe(false);
    expect(h.setTransport).toHaveBeenLastCalledWith(null);
    expect(h.session.map.size).toBe(0);

    const r = harness();
    r.controller.jump("lead", 4);
    expect(r.url()).toBe(PROBLEM);
    r.controller.replay();
    expect(r.navigate).toHaveBeenLastCalledWith("/capture");
    r.go("/capture");
    expect(r.controller.sample()).toBeNull();
  });

  it("starting again while stepping off a sample page starts cleanly", () => {
    const h = harness();
    h.controller.jump("expert", 5);
    h.controller.openPreview("lead");
    h.controller.start("lead");
    expect(h.controller.sample()).toEqual(seed());
    h.go("/capture");
    expect(h.controller.getSnapshot().sampleOn).toBe(true);
  });

  it("stays put on a page that exists outside the sample", () => {
    const h = harness();
    h.controller.jump("lead", 5);
    const calls = h.navigate.mock.calls.length;
    h.controller.exit();
    expect(h.navigate.mock.calls.length).toBe(calls);
    expect(h.url()).toBe("/packages");
  });

  it("steps aside off the app's own pages, and ignores what happens there", () => {
    const h = harness();
    h.controller.start("lead");
    h.controller.setSuspended(true);
    expect(h.setTransport).toHaveBeenLastCalledWith(null);
    h.go("/weakness");
    expect(h.controller.getSnapshot().state.step).toBe(0);
    h.controller.setSuspended(false);
    expect(h.setTransport).toHaveBeenLastCalledWith(h.controller.transport);
  });

  it("does not hand one person's tour to the next person on the tab", () => {
    const h = harness();
    h.controller.identify("a@x", "lead");
    h.controller.start("lead");
    h.controller.identify("b@x", "expert");
    expect(h.controller.sample()).toBeNull();
    expect(h.controller.getSnapshot().state).toMatchObject({ status: "preview", path: "expert" });
  });
});

describe("replay", () => {
  it("starts over from the preview with a fresh sample, leaving nothing behind", async () => {
    const h = harness();
    h.controller.identify("a@x", "expert");
    h.controller.start("expert");
    h.go(PROBLEM);
    await h.request("POST", "/reasoning-traces", {
      scenario_id: TARGET_SCENARIO,
      steps: [{ text: "x", basis: null }],
      final_answer: "y",
    });
    expect(h.controller.sample()!.traces.some((t) => t.by_viewer)).toBe(true);

    h.controller.replay();
    expect(h.controller.getSnapshot().state).toEqual({ status: "preview", path: "expert", step: 0 });
    h.go("/capture");
    expect(h.controller.sample()).toBeNull();
    expect(h.setTransport).toHaveBeenLastCalledWith(null);
    expect(h.session.map.size).toBe(0);

    h.controller.start("expert");
    expect(h.controller.sample()).toEqual(seed());
  });

  it("from idle, replays the reader's own path", () => {
    const h = harness();
    h.controller.identify("a@x", "expert", { offer: false });
    h.controller.replay();
    expect(h.controller.getSnapshot().state).toMatchObject({ status: "preview", path: "expert" });
  });

  it("after finishing, can replay the same path", async () => {
    const h = harness();
    h.controller.jump("lead", 5);
    await h.request("POST", "/data-packages", { name: "x", knowledge_areas: [SOURCE_SELECTION] });
    await tick();
    expect(h.controller.getSnapshot().state.status).toBe("finished");
    h.controller.replay("lead");
    expect(h.controller.getSnapshot().state).toMatchObject({ status: "preview", path: "lead" });
    expect(h.controller.sample()).toBeNull();
  });
});

describe("jumping to a step", () => {
  for (const path of PATH_IDS) {
    PATHS[path].steps.forEach((step, index) => {
      it(`${path} step ${index + 1} (${step.id}) sets up its own state`, () => {
        const h = harness("/somewhere/else");
        h.controller.identify("a@x", path);
        h.controller.jump(path, index);
        const snap = h.controller.getSnapshot();

        expect(snap.state).toEqual({ status: "active", path, step: index });
        expect(snap.sampleOn).toBe(true);
        expect(h.navigate).toHaveBeenLastCalledWith(step.route);
        expect(step.at.test(h.url())).toBe(true);
        expect(h.controller.sample()).toEqual(seed(effectsBefore(path, index)));
        expect(events(h.track)).toContainEqual(
          expect.objectContaining({ name: "tour_jumped", path, step: index + 1 }),
        );
      });
    });
  }

  it("past recording a trace, lands with the trace recorded", () => {
    const h = harness();
    const compare = PATHS.expert.steps.findIndex((s) => s.id === "compare");
    h.controller.jump("expert", compare);
    expect(h.controller.sample()!.traces.filter((t) => t.by_viewer)).toHaveLength(1);
    expect(h.controller.readSeed(`solve.saved:${TARGET_SCENARIO}`)).toMatchObject({ qualified: true });

    h.controller.jump("expert", compare - 1);
    expect(h.controller.sample()!.traces.filter((t) => t.by_viewer)).toHaveLength(0);
    expect(h.controller.readSeed(`solve.saved:${TARGET_SCENARIO}`)).toBeNull();
  });

  it("resets whatever the last jump left behind", async () => {
    const h = harness();
    h.controller.jump("lead", 5);
    await h.request("POST", "/data-packages", { name: "x", knowledge_areas: [SOURCE_SELECTION] });
    expect(h.controller.sample()!.packages).toHaveLength(1);
    h.controller.jump("lead", 5);
    expect(h.controller.sample()!.packages).toHaveLength(0);
  });

  it("changes the epoch every time, so a page on the same URL reloads", () => {
    const h = harness();
    h.controller.jump("expert", 4);
    const first = h.controller.getSnapshot().epoch;
    h.controller.jump("expert", 5);
    expect(h.controller.getSnapshot().epoch).toBeGreaterThan(first);
  });
});

describe("resume", () => {
  it("offers to pick up where the reader left off, set up as that step", () => {
    const h = harness();
    h.local.setItem("aegis.tour.v1:a@x", JSON.stringify({ path: "expert", step: 3, status: "active" }));
    h.controller.identify("a@x", "lead");
    expect(h.controller.getSnapshot().resumable).toEqual({ path: "expert", step: 3 });
    expect(h.controller.getSnapshot().state.status).toBe("idle");

    h.controller.resume();
    expect(h.controller.getSnapshot().state).toEqual({ status: "active", path: "expert", step: 3 });
    expect(h.navigate).toHaveBeenLastCalledWith(PATHS.expert.steps[3].route);
    expect(events(h.track)).toContainEqual(expect.objectContaining({ name: "tour_started", source: "resume" }));
  });

  it("ignores progress it cannot read", () => {
    const h = harness();
    h.local.setItem("aegis.tour.v1:a@x", JSON.stringify({ path: "expert", step: 99, status: "active" }));
    h.controller.identify("a@x", "lead");
    expect(h.controller.getSnapshot().resumable).toBeNull();
    expect(h.controller.getSnapshot().state.status).toBe("preview");
  });

  it("picks a running tour back up after a reload in the same tab", async () => {
    const a = harness();
    a.controller.start("expert");
    a.go("/capture");
    await a.request("POST", "/reasoning-traces", {
      scenario_id: TARGET_SCENARIO,
      steps: [{ text: "x", basis: null }],
      final_answer: "y",
    });

    const b = harness();
    for (const [k, v] of a.session.map) b.session.setItem(k, v);
    expect(b.controller.restoreTab()).toBe(true);
    expect(b.controller.getSnapshot().state).toEqual(a.controller.getSnapshot().state);
    expect(b.controller.sample()).toEqual(a.controller.sample());
    expect(b.setTransport).toHaveBeenLastCalledWith(b.controller.transport);
  });

  it("does not restore from a damaged tab", () => {
    const h = harness();
    h.session.setItem("aegis.tour.tab", JSON.stringify({ status: "active", path: "lead", step: 42 }));
    h.session.setItem("aegis.tour.sample", "{}");
    expect(h.controller.restoreTab()).toBe(false);
    expect(h.session.map.size).toBe(0);
    expect(h.setTransport).not.toHaveBeenCalled();
  });
});
