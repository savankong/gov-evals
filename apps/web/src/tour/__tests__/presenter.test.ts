import { describe, expect, it } from "vitest";

import { parseFlag } from "../flags";
import { parsePresenterParams, presenterAllowed, presenterUrl, stripTourParams } from "../presenter";
import { PATHS } from "../steps";

describe("presenter links", () => {
  it("read a path and a step, numbered from 1", () => {
    expect(parsePresenterParams("?tour=lead&step=4")).toEqual({ kind: "jump", path: "lead", step: 3 });
    expect(parsePresenterParams("tour=expert&step=1")).toEqual({ kind: "jump", path: "expert", step: 0 });
  });

  it("open the preview without a step", () => {
    expect(parsePresenterParams("?tour=expert")).toEqual({ kind: "jump", path: "expert", step: null });
    expect(parsePresenterParams("?tour=lead&step=0")).toEqual({ kind: "jump", path: "lead", step: null });
  });

  it("refuse what is not a step", () => {
    const last = PATHS.lead.steps.length;
    for (const search of [
      "?tour=admin&step=1",
      "?tour=&step=1",
      "?step=2",
      `?tour=lead&step=${last + 1}`,
      "?tour=lead&step=-1",
      "?tour=lead&step=two",
      "?tour=lead&step=1.5",
    ]) {
      expect(parsePresenterParams(search), search).toEqual({ kind: "invalid" });
    }
  });

  it("ignore a URL with neither parameter", () => {
    expect(parsePresenterParams("?area=x")).toEqual({ kind: "none" });
    expect(parsePresenterParams("")).toEqual({ kind: "none" });
  });

  it("round-trip through presenterUrl for every step", () => {
    for (const path of ["lead", "expert"] as const) {
      PATHS[path].steps.forEach((_, index) => {
        const url = presenterUrl(path, index);
        expect(parsePresenterParams(url.split("?")[1])).toEqual({ kind: "jump", path, step: index });
      });
    }
  });

  it("are stripped without disturbing the rest of the query", () => {
    expect(stripTourParams("/capture", "?area=X&tour=lead&step=2")).toBe("/capture?area=X");
    expect(stripTourParams("/", "?tour=lead")).toBe("/");
  });
});

describe("presenter access", () => {
  const admin = (p: string) => p === "org:administer";
  const reviewer = (p: string) => p === "human:score";

  it("needs the flag and an administrator both", () => {
    expect(presenterAllowed(true, admin)).toBe(true);
    expect(presenterAllowed(false, admin)).toBe(false);
    expect(presenterAllowed(true, reviewer)).toBe(false);
    expect(presenterAllowed(false, reviewer)).toBe(false);
  });
});

describe("flags", () => {
  it("parse on, off, and unset", () => {
    expect(parseFlag("1", false)).toBe(true);
    expect(parseFlag("true", false)).toBe(true);
    expect(parseFlag("0", true)).toBe(false);
    expect(parseFlag("off", true)).toBe(false);
    expect(parseFlag(undefined, true)).toBe(true);
    expect(parseFlag("", false)).toBe(false);
    expect(parseFlag("maybe", false)).toBe(false);
  });
});
