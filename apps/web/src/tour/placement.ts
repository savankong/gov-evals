/**
 * Where the step popover goes on a wide screen. Pure, so it can be tested
 * without a browser.
 */

export interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export function sameRect(a: Rect | null, b: Rect | null): boolean {
  if (!a || !b) return a === b;
  return (
    Math.round(a.top) === Math.round(b.top) &&
    Math.round(a.left) === Math.round(b.left) &&
    Math.round(a.width) === Math.round(b.width) &&
    Math.round(a.height) === Math.round(b.height)
  );
}

const GUTTER = 16;
const GAP = 12;

function overlap(a: Rect, b: Rect): number {
  const x = Math.min(a.left + a.width, b.left + b.width) - Math.max(a.left, b.left);
  const y = Math.min(a.top + a.height, b.top + b.height) - Math.max(a.top, b.top);
  return x > 0 && y > 0 ? x * y : 0;
}

/**
 * Where the popover goes. Below the element, above it, beside it, or in a
 * corner -- whichever covers the least of the element itself first, and then
 * the least of what the step asks the reader to look at. A popover over the
 * numbers it is talking about is worse than no popover.
 */
export function place(
  rect: Rect | null,
  width: number,
  height: number,
  keep: Rect[] = [],
  viewport = { width: window.innerWidth, height: window.innerHeight },
): { top: number; left: number } {
  const vw = viewport.width;
  const vh = viewport.height;
  const clampTop = (top: number) => Math.max(GUTTER, Math.min(top, vh - height - GUTTER));
  const clampLeft = (left: number) => Math.max(GUTTER, Math.min(left, vw - width - GUTTER));
  if (!rect) return { top: clampTop((vh - height) / 2), left: clampLeft((vw - width) / 2) };

  const candidates = [
    { top: rect.top + rect.height + GAP, left: clampLeft(rect.left) },
    { top: rect.top - GAP - height, left: clampLeft(rect.left) },
    { top: clampTop(rect.top), left: rect.left + rect.width + GAP },
    { top: clampTop(rect.top), left: rect.left - GAP - width },
    { top: vh - height - GUTTER, left: vw - width - GUTTER },
    { top: GUTTER, left: vw - width - GUTTER },
    { top: vh - height - GUTTER, left: GUTTER },
  ].filter(
    (c) => c.top >= GUTTER && c.top + height <= vh - GUTTER && c.left >= GUTTER && c.left + width <= vw - GUTTER,
  );
  let best = { top: vh - height - GUTTER, left: vw - width - GUTTER };
  let bestScore = Infinity;
  for (const c of candidates) {
    const box = { ...c, width, height };
    const score = overlap(box, rect) * 1000 + keep.reduce((sum, k) => sum + overlap(box, k), 0);
    if (score < bestScore) {
      best = c;
      bestScore = score;
    }
  }
  return best;
}

