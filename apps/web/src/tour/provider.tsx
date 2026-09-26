"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/shell";
import { setTransport } from "@/lib/api";

import { track } from "./analytics";
import { SERVER_SNAPSHOT, TourController, type TourSnapshot } from "./controller";
import { presenterFlag, tourEnabled } from "./flags";
import { TourLayer } from "./layer";
import { parsePresenterParams, presenterAllowed, stripTourParams } from "./presenter";
import { defaultPath } from "./steps";
import { setSeedReader, setSignalListener } from "./signal";

interface TourContextValue {
  enabled: boolean;
  controller: TourController | null;
  snapshot: TourSnapshot | null;
  /** Pathname plus query, kept current while the tour runs. */
  url: string;
  presenter: boolean;
  presenterOpen: boolean;
  setPresenterOpen: (open: boolean) => void;
}

const TourContext = createContext<TourContextValue>({
  enabled: false,
  controller: null,
  snapshot: null,
  url: "/",
  presenter: false,
  presenterOpen: false,
  setPresenterOpen: () => {},
});

export function useTour(): TourContextValue {
  return useContext(TourContext);
}

/** What the shell needs: whether to show the tour's parts, and a key that
 *  changes when the app moves between real and sample data. */
export function useTourShell(): { enabled: boolean; epoch: number; sampleOn: boolean } {
  const { enabled, snapshot } = useTour();
  return { enabled, epoch: snapshot?.epoch ?? 0, sampleOn: snapshot?.sampleOn ?? false };
}

function outsideApp(pathname: string): boolean {
  return pathname === "/login" || pathname === "/public" || pathname.startsWith("/public/");
}

function storage(kind: "session" | "local") {
  try {
    return kind === "session" ? window.sessionStorage : window.localStorage;
  } catch {
    return null;
  }
}

export function TourProvider({ children }: { children: ReactNode }) {
  if (!tourEnabled()) return <>{children}</>;
  return <EnabledTourProvider>{children}</EnabledTourProvider>;
}

function EnabledTourProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { session, can } = useAuth();
  const routerRef = useRef(router);
  routerRef.current = router;

  const [controller] = useState(() => {
    const instance = new TourController({
      navigate: (url) => routerRef.current.push(url),
      currentUrl: () =>
        typeof window === "undefined" ? "/" : window.location.pathname + window.location.search,
      setTransport,
      session: typeof window === "undefined" ? null : storage("session"),
      local: typeof window === "undefined" ? null : storage("local"),
      track,
    });
    // In the browser, pick up a tour already running in this tab before any
    // page asks for data, so a reload never shows real data under the
    // sample banner or the other way round.
    if (typeof window !== "undefined") {
      instance.setSuspended(outsideApp(window.location.pathname));
      instance.restoreTab();
    }
    return instance;
  });

  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, () => SERVER_SNAPSHOT);
  const [url, setUrl] = useState(pathname);
  const [presenterOpen, setPresenterOpen] = useState(false);
  const presenter = presenterAllowed(presenterFlag(), can);

  useEffect(() => {
    setSignalListener((name) => controller.dispatch({ type: "signal", name }));
    setSeedReader(controller.readSeed);
    return () => {
      setSignalListener(null);
      setSeedReader(null);
    };
  }, [controller]);

  useEffect(() => {
    controller.setSuspended(outsideApp(pathname));
  }, [controller, pathname]);

  // The URL, including the query, which Next.js does not report on its own
  // without a Suspense boundary around the whole app. Polled while a tour is
  // running; cheap, and it catches every way the URL can change.
  const running = snapshot.state.status === "active";
  useEffect(() => {
    const read = () => window.location.pathname + window.location.search;
    setUrl(read());
    if (!running) return;
    const timer = window.setInterval(() => setUrl((current) => (current === read() ? current : read())), 200);
    return () => window.clearInterval(timer);
  }, [pathname, running]);

  useEffect(() => {
    controller.dispatch({ type: "route", url });
  }, [controller, url]);

  // Who is looking. The preview is offered on the portfolio, the page a new
  // account lands on, and only to someone who has never seen or dismissed it.
  const user = session?.email ?? null;
  const onPortfolio = pathname === "/";
  const path = defaultPath(can);
  useEffect(() => {
    if (!user) return;
    controller.identify(user, path, { offer: onPortfolio });
  }, [controller, user, path, onPortfolio]);

  // Presenter links: ?tour=lead&step=4 on any page.
  const handledSearch = useRef<string | null>(null);
  useEffect(() => {
    if (!user) return;
    const search = window.location.search;
    if (handledSearch.current === search) return;
    handledSearch.current = search;
    const request = parsePresenterParams(search);
    if (request.kind === "none") return;
    const clean = stripTourParams(window.location.pathname, search);
    // Replaced first, so Back does not land on the link and jump again.
    router.replace(clean);
    if (request.kind === "jump" && presenter) {
      if (request.step === null) controller.openPreview(request.path);
      else controller.jump(request.path, request.step, "presenter");
      return;
    }
    // Not allowed, or not a step that exists: the parameters are dropped and
    // nothing else happens.
  }, [controller, user, presenter, router, url]);

  const set = useCallback((open: boolean) => setPresenterOpen(open), []);
  const value = useMemo<TourContextValue>(
    () => ({
      enabled: true,
      controller,
      snapshot,
      url,
      presenter,
      presenterOpen: presenter && presenterOpen,
      setPresenterOpen: set,
    }),
    [controller, snapshot, url, presenter, presenterOpen, set],
  );

  return (
    <TourContext.Provider value={value}>
      {children}
      {user && !outsideApp(pathname) ? <TourLayer /> : null}
    </TourContext.Provider>
  );
}
