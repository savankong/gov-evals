import { vi } from "vitest";

import { TourController } from "../controller";
import type { KeyValueStore } from "../sandbox/store";

export class MemoryStorage implements KeyValueStore {
  map = new Map<string, string>();
  getItem(key: string) {
    return this.map.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.map.set(key, value);
  }
  removeItem(key: string) {
    this.map.delete(key);
  }
}

/** A controller wired to fakes: a URL it keeps itself, storage in memory,
 *  and spies for everything it tells the outside world. */
export function harness(start = "/") {
  let url = start;
  const session = new MemoryStorage();
  const local = new MemoryStorage();
  const navigate = vi.fn((to: string) => {
    url = to;
  });
  const setTransport = vi.fn();
  const track = vi.fn();
  const controller = new TourController({
    navigate,
    currentUrl: () => url,
    setTransport,
    session,
    local,
    track,
  });
  return {
    controller,
    session,
    local,
    navigate,
    setTransport,
    track,
    url: () => url,
    /** Go somewhere the way a reader would, and tell the tour. */
    go(to: string) {
      url = to;
      controller.dispatch({ type: "route", url: to });
    },
    async request(method: string, path: string, body?: unknown) {
      const response = await controller.transport(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      await Promise.resolve();
      return response;
    },
  };
}

export const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
