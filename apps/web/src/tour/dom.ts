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
  const frame = parent?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight };
  const top = frame.top + 12;
  const bottom = Math.min(frame.bottom, window.innerHeight - reservedBottom) - 12;
  const rect = el.getBoundingClientRect();
  let delta = 0;
  if (rect.bottom > bottom) delta = rect.bottom - bottom;
  // Taller than the space, or above it: line up its top instead.
  if (rect.top - delta < top) delta = rect.top - top;
  if (Math.abs(delta) < 1) return;
  const behavior: ScrollBehavior = smooth ? "smooth" : "auto";
  if (parent) parent.scrollBy({ top: delta, behavior });
  else window.scrollBy({ top: delta, behavior });
}

/** Tell the shell how much room to leave below the page for a bottom sheet. */
export function reserveSheet(height: number): () => void {
  document.documentElement.style.setProperty("--tour-sheet", `${Math.round(height)}px`);
  return () => document.documentElement.style.removeProperty("--tour-sheet");
}
