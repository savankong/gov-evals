import { afterEach, describe, expect, it, vi } from "vitest";

import { api, setTransport } from "@/lib/api";

import { SET_ASIDES, SOURCE_SELECTION, TARGET_SCENARIO, WORKED_EXAMPLE } from "../sandbox/fixtures";
import { NOT_IN_SAMPLE, handle } from "../sandbox/handlers";
import { contentHash, sha256Hex } from "../sandbox/sha256";
import { loadSnapshot, saveSnapshot, seed } from "../sandbox/store";
import { MemoryStorage, harness } from "./helpers";

type Area = { label: string; confident_wrong: number; failed: number; failed_without_trace: number; qualified_traces: number };
const area = (data: ReturnType<typeof seed>, label: string, at = 0.8) =>
  (handle(data, "GET", `/weakness-map?confident_at=${at}`).body as { areas: Area[] }).areas.find(
    (a) => a.label === label,
  )!;

afterEach(() => {
  setTransport(null);
  vi.unstubAllGlobals();
});

describe("sha256", () => {
  it("is SHA-256", () => {
    expect(sha256Hex("")).toBe("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
    expect(sha256Hex("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  });

  it("hashes canonical JSON, so key order does not matter", () => {
    expect(contentHash({ b: 1, a: [1, { d: 2, c: 3 }] })).toBe(contentHash({ a: [1, { c: 3, d: 2 }], b: 1 }));
  });
});

describe("seeding", () => {
  it("is deterministic", () => {
    expect(seed()).toEqual(seed());
  });

  it("shares nothing between seeds", () => {
    const a = seed();
    a.scenarios[0].title = "changed";
    a.traces.pop();
    expect(seed().scenarios[0].title).not.toBe("changed");
    expect(seed().traces.length).toBe(a.traces.length + 1);
  });

  it("marks everything as sample", () => {
    const data = seed();
    for (const record of [...data.scenarios, ...data.results, ...data.traces]) {
      expect(record.id.startsWith("sample-")).toBe(true);
    }
    for (const doc of data.scenarios.flatMap((s) => s.documents)) expect(doc.title).toMatch(/\(sample\)$/);
  });

  it("gives every trace the digest of what it contains", () => {
    const data = seed();
    const hashes = new Set(data.traces.map((t) => t.content_hash));
    expect(hashes.size).toBe(data.traces.length);
    for (const trace of data.traces) expect(trace.content_hash).toMatch(/^[0-9a-f]{64}$/);
  });

  it("applies what a step leaves behind", () => {
    const data = seed(["expert.trace-recorded"]);
    const mine = data.traces.filter((t) => t.by_viewer);
    expect(mine).toHaveLength(1);
    expect(mine[0].scenario_id).toBe(TARGET_SCENARIO);
    expect(mine[0].qualified).toBe(true);
    expect(data.ui[`solve.saved:${TARGET_SCENARIO}`]).toEqual(mine[0]);
    // Applying it twice changes nothing.
    const again = seed(["expert.trace-recorded", "expert.trace-recorded"]);
    expect(again.traces.filter((t) => t.by_viewer)).toHaveLength(1);
  });
});

describe("the sample's answers", () => {
  it("shows Source selection staying confidently wrong at 0.9 while set-asides drops out", () => {
    const data = seed();
    expect(area(data, SOURCE_SELECTION, 0.8).confident_wrong).toBe(9);
    expect(area(data, SOURCE_SELECTION, 0.9).confident_wrong).toBe(8);
    expect(area(data, SET_ASIDES, 0.8).confident_wrong).toBe(3);
    expect(area(data, SET_ASIDES, 0.9).confident_wrong).toBe(0);
    // What the step copy promises: "2 of those problems have no expert answer yet".
    expect(area(data, SOURCE_SELECTION).failed_without_trace).toBe(2);
  });

  it("puts the target problem first in its area", () => {
    const body = handle(seed(), "GET", `/capture/tasks?scope=mine&knowledge_area=${encodeURIComponent(SOURCE_SELECTION)}`)
      .body as { tasks: Array<{ scenario_id: string }> };
    expect(body.tasks[0].scenario_id).toBe(TARGET_SCENARIO);
  });

  it("counts a recorded trace on the weakness map", () => {
    const data = seed();
    const before = area(data, SOURCE_SELECTION);
    const response = handle(data, "POST", "/reasoning-traces", {
      scenario_id: TARGET_SCENARIO,
      steps: WORKED_EXAMPLE.steps,
      final_answer: WORKED_EXAMPLE.answer,
      sources: WORKED_EXAMPLE.sources,
      expertise: "acquisition",
    });
    expect(response.status).toBe(201);
    const after = area(data, SOURCE_SELECTION);
    expect(after.qualified_traces).toBe(before.qualified_traces + 1);
    expect(after.failed_without_trace).toBe(before.failed_without_trace - 1);
  });

  it("refuses a blank step, as the server does", () => {
    const response = handle(seed(), "POST", "/reasoning-traces", {
      scenario_id: TARGET_SCENARIO,
      steps: [{ text: "  " }],
      final_answer: "x",
    });
    expect(response.status).toBe(400);
  });

  it("builds a package that counts what it left out, and why", () => {
    const data = seed();
    const response = handle(data, "POST", "/data-packages", {
      name: "Source selection",
      knowledge_areas: [SOURCE_SELECTION],
    });
    expect(response.status).toBe(201);
    const pkg = response.body as {
      record_count: number;
      sha256: string;
      manifest: { excluded: Array<{ reason: string; records: number }>; bins: Array<{ model_outcome: string }> };
    };
    // What the lead preview promises.
    expect(pkg.record_count).toBe(3);
    expect(pkg.manifest.excluded).toEqual([
      expect.objectContaining({ reason: "contains_pii", records: 1 }),
      expect.objectContaining({ reason: "not_qualified", records: 1 }),
    ]);
    expect(pkg.manifest.bins.every((b) => b.model_outcome === "failed")).toBe(true);
    expect(pkg.sha256).toBe(sha256Hex(data.packages[0].body));
    expect(response.body).not.toHaveProperty("body");
  });

  it("refuses a package with nothing deliverable in it", () => {
    const response = handle(seed(), "POST", "/data-packages", { name: "x", knowledge_areas: ["Nothing"] });
    expect(response.status).toBe(422);
  });

  it("refuses what it does not know, rather than inventing it", () => {
    for (const [method, path] of [
      ["GET", "/projects/abc"],
      ["GET", "/datasets"],
      ["POST", "/projects"],
      ["DELETE", "/data-packages/x"],
      ["GET", "/reasoning-traces"],
    ]) {
      const response = handle(seed(), method, path);
      expect(response.status).toBe(404);
      expect(response.body).toEqual({ detail: NOT_IN_SAMPLE });
    }
  });
});

describe("the transport", () => {
  it("never calls the network, for anything", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const h = harness();
    h.controller.start("lead");
    for (const [method, path] of [
      ["GET", "/weakness-map"],
      ["GET", "/datasets"],
      ["POST", "/data-packages"],
      ["POST", "/projects"],
      ["GET", "/admin/users"],
    ]) {
      await h.request(method, path, method === "POST" ? { name: "x" } : undefined);
    }
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("refuses an upload", async () => {
    const h = harness();
    h.controller.start("lead");
    const response = await h.controller.transport("/datasets/x/upload", { method: "POST", body: new FormData() });
    expect(response.status).toBe(404);
  });

  it("is what api.ts uses while installed, except for identity", async () => {
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ user: {}, permissions: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    const h = harness();
    h.controller.start("lead");
    setTransport(h.controller.transport);

    const map = await api.get<{ areas: unknown[] }>("/weakness-map");
    expect(map.areas.length).toBeGreaterThan(0);
    expect(fetchSpy).not.toHaveBeenCalled();

    await expect(api.get("/datasets")).rejects.toThrow(NOT_IN_SAMPLE);
    expect(fetchSpy).not.toHaveBeenCalled();

    await api.get("/auth/me");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String((fetchSpy.mock.calls[0] as unknown[])[0])).toMatch(/\/auth\/me$/);

    setTransport(null);
    await api.get("/weakness-map").catch(() => {});
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});

describe("snapshots", () => {
  it("round-trips, and refuses anything that is not one", () => {
    const storage = new MemoryStorage();
    const data = seed(["expert.trace-recorded"]);
    saveSnapshot(storage, data);
    expect(loadSnapshot(storage)).toEqual(data);
    storage.setItem("aegis.tour.sample", "{not json");
    expect(loadSnapshot(storage)).toBeNull();
    storage.setItem("aegis.tour.sample", JSON.stringify({ version: 2 }));
    expect(loadSnapshot(storage)).toBeNull();
    saveSnapshot(storage, null);
    expect(storage.map.size).toBe(0);
  });
});
