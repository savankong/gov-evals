/**
 * What a screen imports to take part in the tour, and nothing else.
 *
 * Every function here is a no-op when no tour is running, so a page can call
 * them unconditionally and behave exactly as before with the flag off.
 *
 *   tourSignal(name)          report that something with no URL or request
 *                             happened, e.g. a disclosure opened.
 *   useTourCommand(name, fn)  let "Show me" do something on this screen, e.g.
 *                             fill in a worked example.
 *   tourSeed(key)             screen state a presenter jump needs, e.g. the
 *                             "Trace recorded" panel after jumping past it.
 */

import { useEffect, useRef } from "react";

type SignalListener = (name: string) => void;
type SeedReader = (key: string) => unknown;

let signalListener: SignalListener | null = null;
let seedReader: SeedReader | null = null;
const commands = new Map<string, (payload: unknown) => void>();

export function tourSignal(name: string): void {
  signalListener?.(name);
}

export function tourSeed<T>(key: string): T | null {
  return (seedReader?.(key) as T | undefined) ?? null;
}

export function useTourCommand<T = unknown>(name: string, handler: (payload: T) => void): void {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const run = (payload: unknown) => ref.current(payload as T);
    commands.set(name, run);
    return () => {
      if (commands.get(name) === run) commands.delete(name);
    };
  }, [name]);
}

/* -- used by the tour itself ------------------------------------------ */

export function setSignalListener(listener: SignalListener | null): void {
  signalListener = listener;
}

export function setSeedReader(reader: SeedReader | null): void {
  seedReader = reader;
}

export function hasCommand(name: string): boolean {
  return commands.has(name);
}

export function runCommand(name: string, payload?: unknown): boolean {
  const command = commands.get(name);
  if (!command) return false;
  command(payload);
  return true;
}
