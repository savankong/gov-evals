import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { PATH_COPY } from "../copy";
import { handle } from "../sandbox/handlers";
import { seed } from "../sandbox/store";
import { PATHS, defaultPath } from "../steps";
import { PATH_IDS } from "../types";

const SRC = join(__dirname, "..", "..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sources(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

/** Every `data-tour` value the app can render, as patterns: a literal is
 *  itself, and each `${...}` in a template may be anything. */
function anchorPatterns(): Array<{ pattern: RegExp; file: string }> {
  const out: Array<{ pattern: RegExp; file: string }> = [];
  const attr = /(?:data-tour=|\btour[=:]\s*)(?:\{\s*)?(["'`])((?:(?!\1).)+)\1/g;
  for (const file of sources(SRC)) {
    if (file.includes(`${join("src", "tour")}`)) continue;
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(attr)) {
      const body = match[2]
        .split(/\$\{[^}]*\}/)
        .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join(".+");
      out.push({ pattern: new RegExp(`^${body}$`), file: relative(SRC, file) });
    }
  }
  return out;
}

describe("steps", () => {
  const patterns = anchorPatterns();

  it("point at anchors that exist in the app", () => {
    for (const path of PATH_IDS) {
      for (const step of PATHS[path].steps) {
        const clicks = step.assist.flatMap((a) => ("click" in a ? [a.click] : []));
        for (const id of [...step.anchors, ...clicks]) {
          const found = patterns.some(({ pattern }) => pattern.test(id));
          expect(found, `${path}/${step.id}: no element carries data-tour="${id}"`).toBe(true);
        }
      }
    }
  });

  it("point at nav entries that exist", () => {
    const shell = readFileSync(join(SRC, "components", "shell.tsx"), "utf8");
    for (const path of PATH_IDS) {
      for (const step of PATHS[path].steps) {
        for (const id of step.anchors.filter((a) => a.startsWith("nav."))) {
          expect(shell, `${path}/${step.id}: no nav entry for ${id}`).toContain(`href: "/${id.slice(4)}"`);
        }
      }
    }
  });

  it("take the reader somewhere the step happens", () => {
    for (const path of PATH_IDS) {
      for (const step of PATHS[path].steps) {
        expect(step.at.test(step.route), `${path}/${step.id}: ${step.route} is not where it happens`).toBe(true);
      }
    }
  });

  it("wait on requests the sample can answer", () => {
    for (const path of PATH_IDS) {
      for (const step of PATHS[path].steps) {
        if (!("request" in step.done)) continue;
        const [method, url] = step.done.request.split(" ");
        const response = handle(seed(), method, url, {});
        expect(response.status, `${path}/${step.id}`).not.toBe(404);
      }
    }
  });

  it("are between four and seven per path, each finished by an action", () => {
    for (const path of PATH_IDS) {
      const steps = PATHS[path].steps;
      expect(steps.length).toBeGreaterThanOrEqual(4);
      expect(steps.length).toBeLessThanOrEqual(7);
      for (const step of steps) expect("next" in step.done, `${path}/${step.id} waits on Next`).toBe(false);
    }
  });

  it("all have copy, and all copy has a step", () => {
    for (const path of PATH_IDS) {
      const ids = PATHS[path].steps.map((s) => s.id);
      expect(Object.keys(PATH_COPY[path].steps).sort()).toEqual([...ids].sort());
      for (const id of ids) {
        const copy = PATH_COPY[path].steps[id];
        expect(copy.title.trim(), `${path}/${id} title`).not.toBe("");
        expect(copy.body.trim(), `${path}/${id} body`).not.toBe("");
      }
    }
  });
});

describe("defaultPath", () => {
  const can = (...held: string[]) => (p: string) => held.includes(p);
  it("sends people who run the work to the lead path, and experts to the expert path", () => {
    expect(defaultPath(can("org:administer"))).toBe("lead");
    expect(defaultPath(can("project:write", "human:score"))).toBe("lead");
    expect(defaultPath(can("human:score"))).toBe("expert");
    expect(defaultPath(can("project:read"))).toBe("lead");
  });
});
