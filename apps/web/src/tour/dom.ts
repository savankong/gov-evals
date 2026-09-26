/**
 * Finding the real element a step points at, and acting on it for "Show me".
 */

import { hasCommand, runCommand } from "./signal";
import type { Assist } from "./types";

function visible(el: HTMLElement): boolean {
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  const style = window.getComputedStyle(el);
  return style.visibility !== "hidden";
}

/** The first of `ids` with a visible element. Several elements can carry the
 *  same anchor -- the rail and the mobile drawer both render the nav -- and
 *  the one on screen is the one that counts. */
export function findAnchor(ids: string[]): { id: string; el: HTMLElement } | null {
  for (const id of ids) {
    const nodes = document.querySelectorAll<HTMLElement>(`[data-tour="${CSS.escape(id)}"]`);
    for (const el of Array.from(nodes)) if (visible(el)) return { id, el };
  }
  return null;
}

/** The control inside an anchor: the anchor itself when it is one, else the
 *  first control it wraps. */
export function controlIn(el: HTMLElement): HTMLElement {
  if (el.matches("button, a, input, select, textarea, [role='button']")) return el;
  return el.querySelector<HTMLElement>("button, a, input, select, textarea, [role='button']") ?? el;
}

function waitFor<T>(check: () => T | null | false, timeoutMs = 4000): Promise<T | null> {
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = () => {
      const value = check();
      if (value) return resolve(value);
      if (Date.now() - started > timeoutMs) return resolve(null);
      window.setTimeout(tick, 60);
    };
    tick();
  });
}

const here = () => window.location.pathname + window.location.search;

/** Carry out a step's assist, waiting for each thing it needs to exist
 *  before touching it. Returns false if something never appeared. */
export async function runAssist(actions: Assist[], navigate: (url: string) => void): Promise<boolean> {
  for (const action of actions) {
    if ("navigate" in action) {
      const target = action.navigate;
      const pathOnly = target.split("?")[0];
      if (window.location.pathname !== pathOnly) {
        navigate(target);
        if (!(await waitFor(() => window.location.pathname === pathOnly))) return false;
      } else if (target.includes("?") && here() !== target) {
        navigate(target);
      }
    } else if ("command" in action) {
      if (!(await waitFor(() => hasCommand(action.command)))) return false;
      runCommand(action.command, action.payload);
      // Let the screen render what the command filled in.
      await new Promise((resolve) => window.setTimeout(resolve, 80));
    } else {
      const found = await waitFor(() => {
        const hit = findAnchor([action.click]);
        if (!hit) return null;
        const control = controlIn(hit.el);
        return (control as HTMLButtonElement).disabled ? null : control;
      });
      if (!found) return false;
      found.click();
    }
  }
  return true;
}

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowY } = window.getComputedStyle(node);
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) return node;
  }
  return null;
}

/** Scroll the page so an element sits in the part of the screen nothing of
 *  the tour's covers: below the page's own header, above the bottom sheet on
 *  a phone. Moves only as far as it has to. */
export function reveal(el: HTMLElement, reservedBottom: number, smooth: boolean): void {
  const parent = scrollParent(el);
  scrollIntoBand(parent, el.getBoundingClientRect(), reservedBottom, smooth);
}

/** The part of the screen a scroll container shows that nothing of the
 *  tour's covers. */
function band(parent: HTMLElement | null, reservedBottom: number): { top: number; bottom: number } {
  const frame = parent?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight };
  return { top: frame.top + 12, bottom: Math.min(frame.bottom, window.innerHeight - reservedBottom) - 12 };
}

function scrollIntoBand(
  parent: HTMLElement | null,
  rect: { top: number; bottom: number },
  reservedBottom: number,
  smooth: boolean,
): void {
  const { top, bottom } = band(parent, reservedBottom);
  let delta = 0;
  if (rect.bottom > bottom) delta = rect.bottom - bottom;
  // Taller than the space, or above it: line up its top instead.
  if (rect.top - delta < top) delta = rect.top - top;
  if (Math.abs(delta) < 1) return;
  const behavior: ScrollBehavior = smooth ? "smooth" : "auto";
  if (parent) parent.scrollBy({ top: delta, behavior });
  else window.scrollBy({ top: delta, behavior });
}

function scrollParentX(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowX } = window.getComputedStyle(node);
    if ((overflowX === "auto" || overflowX === "scroll") && node.scrollWidth > node.clientWidth) return node;
  }
  return null;
}

function pinned(el: Element | null | undefined): boolean {
  return !!el && window.getComputedStyle(el).position === "sticky";
}

/** Scroll a wide table sideways so an element is in view, beside whatever
 *  column is pinned at the left of its row. Always instant: a smooth scroll
 *  of the page around the table, which usually follows, cancels a smooth one
 *  still running inside it, and the table was left where it started. */
function revealX(el: HTMLElement, box: HTMLElement): void {
  const cell = el.closest("th, td");
  // In the pinned column itself: always in view, whatever the scroll.
  if (pinned(cell)) return;
  const frame = box.getBoundingClientRect();
  const first = el.closest("tr")?.firstElementChild;
  const inset = first && first !== cell && pinned(first) ? first.getBoundingClientRect().width : 0;
  const left = frame.left + inset + 8;
  const right = frame.right - 8;
  const rect = el.getBoundingClientRect();
  let dx = 0;
  if (rect.right > right) dx = rect.right - right;
  if (rect.left - dx < left) dx = rect.left - left;
  if (Math.abs(dx) >= 1) box.scrollBy({ left: dx, behavior: "auto" });
}

/** Bring into view what a step asks the reader to look at, as well as the
 *  control it points at, without ever pushing that control off screen.
 *
 *  Sideways, a kept element is scrolled to when the control does not scroll
 *  with it or sits in a column pinned in place. Up and down, one that scrolls
 *  with the control is brought in only together with it: kept elements are
 *  taken in order while the control and everything taken so far still fit on
 *  screen at once, and the rest are left where they are. */
export function revealKept(target: HTMLElement, kept: HTMLElement[], reservedBottom: number, smooth: boolean): void {
  const home = scrollParent(target);
  const space = band(home, reservedBottom);
  const first = target.getBoundingClientRect();
  const together = { top: first.top, bottom: first.bottom };
  for (const el of kept) {
    const box = scrollParentX(el);
    if (box && (!box.contains(target) || pinned(target.closest("th, td")))) revealX(el, box);
    const parent = scrollParent(el);
    if (!parent || !parent.contains(target)) {
      reveal(el, reservedBottom, smooth);
      continue;
    }
    const rect = el.getBoundingClientRect();
    const top = Math.min(together.top, rect.top);
    const bottom = Math.max(together.bottom, rect.bottom);
    if (bottom - top <= space.bottom - space.top) {
      together.top = top;
      together.bottom = bottom;
    }
  }
  if (together.top !== first.top || together.bottom !== first.bottom) {
    scrollIntoBand(home, together, reservedBottom, smooth);
  }
}

/** Tell the shell how much room to leave below the page for a bottom sheet. */
export function reserveSheet(height: number): () => void {
  document.documentElement.style.setProperty("--tour-sheet", `${Math.round(height)}px`);
  return () => document.documentElement.style.removeProperty("--tour-sheet");
}
