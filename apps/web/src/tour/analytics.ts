/**
 * Tour analytics, kept in the browser.
 *
 * The product has no analytics and promises it never phones home, so these
 * events go nowhere on their own: each is dispatched as an `aegis:tour`
 * window event (and logged to the console in development). A deployment
 * that wants counts can listen for the event and forward it to its own
 * collector; nothing here decides that for them.
 */

export type TourAnalyticsEvent =
  | "tour_started"
  | "tour_step_completed"
  | "tour_skipped"
  | "tour_finished"
  | "tour_jumped";

export interface TourAnalyticsDetail {
  name: TourAnalyticsEvent;
  at: string;
  [key: string]: unknown;
}

export type Tracker = (name: TourAnalyticsEvent, props?: Record<string, unknown>) => void;

export const track: Tracker = (name, props = {}) => {
  const detail: TourAnalyticsDetail = { name, at: new Date().toISOString(), ...props };
  if (typeof window !== "undefined" && typeof CustomEvent !== "undefined") {
    window.dispatchEvent(new CustomEvent<TourAnalyticsDetail>("aegis:tour", { detail }));
  }
  if (process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.debug("[tour]", name, props);
  }
};
