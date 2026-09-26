/**
 * Feature flags for the tour.
 *
 * Build-time, like NEXT_PUBLIC_API_BASE: Next.js inlines NEXT_PUBLIC_* into the
 * client bundle, so each is read by its literal name here. Unset means on in
 * development and off in a production build.
 *
 *   NEXT_PUBLIC_AEGIS_TOUR=1            the tour replaces the first-run
 *                                       walkthrough (primer, checklist card,
 *                                       /welcome). Off: the walkthrough as before.
 *   NEXT_PUBLIC_AEGIS_TOUR_PRESENTER=1  presenter mode, for accounts that can
 *                                       administer an organization. Never shown
 *                                       to anyone else, flag or not.
 */

export function parseFlag(value: string | undefined, fallback: boolean): boolean {
  const v = (value ?? "").trim().toLowerCase();
  if (v === "1" || v === "true" || v === "on") return true;
  if (v === "0" || v === "false" || v === "off") return false;
  return fallback;
}

const DEV = process.env.NODE_ENV === "development";

export function tourEnabled(): boolean {
  return parseFlag(process.env.NEXT_PUBLIC_AEGIS_TOUR, DEV);
}

export function presenterFlag(): boolean {
  return tourEnabled() && parseFlag(process.env.NEXT_PUBLIC_AEGIS_TOUR_PRESENTER, DEV);
}
