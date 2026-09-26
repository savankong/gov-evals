import { describe, expect, it } from "vitest";

import { place, type Rect } from "../placement";

const viewport = { width: 1280, height: 800 };
const POPOVER = { width: 352, height: 170 };

function covers(at: { top: number; left: number }, r: Rect): boolean {
  return (
    at.left < r.left + r.width &&
    at.left + POPOVER.width > r.left &&
    at.top < r.top + r.height &&
    at.top + POPOVER.height > r.top
  );
}

// Measured from the weakness map at 1280x800, lead step 2.
const threshold: Rect = { top: 207, left: 519, width: 64, height: 28 };
const table: Rect = { top: 388, left: 245, width: 1015, height: 350 };

describe("popover placement", () => {
  it("does not cover the numbers a step asks the reader to watch", () => {
    const at = place(threshold, POPOVER.width, POPOVER.height, [table], viewport);
    expect(covers(at, table)).toBe(false);
    expect(covers(at, threshold)).toBe(false);
  });

  it("would have, without being told what to keep clear", () => {
    const at = place(threshold, POPOVER.width, POPOVER.height, [], viewport);
    expect(covers(at, table)).toBe(true);
  });

  it("never covers the element itself when there is room anywhere", () => {
    const tall: Rect = { top: 40, left: 300, width: 600, height: 720 };
    const at = place(tall, POPOVER.width, POPOVER.height, [], viewport);
    expect(covers(at, tall)).toBe(false);
  });

  it("stays on screen", () => {
    for (const target of [
      { top: 780, left: 1250, width: 20, height: 10 },
      { top: 0, left: 0, width: 10, height: 10 },
      { top: 400, left: 600, width: 30, height: 20 },
    ]) {
      const at = place(target, POPOVER.width, POPOVER.height, [], viewport);
      expect(at.top).toBeGreaterThanOrEqual(16);
      expect(at.left).toBeGreaterThanOrEqual(16);
      expect(at.top + POPOVER.height).toBeLessThanOrEqual(viewport.height - 16);
      expect(at.left + POPOVER.width).toBeLessThanOrEqual(viewport.width - 16);
    }
  });

  it("centres when the element cannot be found", () => {
    const at = place(null, POPOVER.width, POPOVER.height, [], viewport);
    expect(at).toEqual({ top: (800 - 170) / 2, left: (1280 - 352) / 2 });
  });
});
