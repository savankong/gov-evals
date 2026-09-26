/**
 * Presenter mode: straight to any step of either path, for a sales call or a
 * demo. `?tour=lead&step=4` on any page. Steps are numbered from 1, the way
 * the popover numbers them; no step (or `step=0`) opens that path's preview.
 */

import { PATHS } from "./steps";
import { PATH_IDS, type PathId } from "./types";

export type PresenterRequest =
  | { kind: "none" }
  | { kind: "invalid" }
  | { kind: "jump"; path: PathId; step: number | null };

export function parsePresenterParams(search: string): PresenterRequest {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  if (!params.has("tour") && !params.has("step")) return { kind: "none" };
  const path = params.get("tour") as PathId | null;
  if (!path || !PATH_IDS.includes(path)) return { kind: "invalid" };
  const raw = params.get("step");
  if (raw === null || raw === "" || raw === "0") return { kind: "jump", path, step: null };
  if (!/^\d+$/.test(raw)) return { kind: "invalid" };
  const step = Number(raw);
  if (step < 1 || step > PATHS[path].steps.length) return { kind: "invalid" };
  return { kind: "jump", path, step: step - 1 };
}

/** Behind the flag and an administrator's account both. The sample never
 *  touches real data, so this is not a security boundary; it keeps a sales
 *  tool out of a working reader's way. */
export function presenterAllowed(flag: boolean, can: (permission: string) => boolean): boolean {
  return flag && can("org:administer");
}

/** The same URL without the presenter parameters, so a reload does not jump
 *  again and a copied link does not carry them. */
export function stripTourParams(pathname: string, search: string): string {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  params.delete("tour");
  params.delete("step");
  const rest = params.toString();
  return rest ? `${pathname}?${rest}` : pathname;
}

export function presenterUrl(path: PathId, step: number | null, pathname = "/"): string {
  return `${pathname}?tour=${path}${step === null ? "" : `&step=${step + 1}`}`;
}
