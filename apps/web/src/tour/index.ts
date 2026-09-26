/**
 * The product tour. Everything it needs lives in this folder; the rest of the
 * app touches it in three places:
 *
 *   - the shell mounts the provider, the sample banner and the help menu;
 *   - `lib/api.ts` accepts the transport the sample answers through;
 *   - screens on the tour's path carry `data-tour` anchors and call the
 *     no-op-when-off helpers in ./signal.
 *
 * Behind NEXT_PUBLIC_AEGIS_TOUR (see ./flags). With it off, the first-run
 * walkthrough is exactly as it was.
 */

export { tourEnabled } from "./flags";
export { TourProvider, useTour, useTourShell } from "./provider";
export { TourBanner, TourHelpMenu } from "./shell-parts";
export { TourWelcome } from "./welcome";
