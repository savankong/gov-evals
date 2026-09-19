"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, api, getToken } from "@/lib/api";

interface Session {
  email: string;
  fullName: string | null;
  permissions: string[];
}

interface AuthValue {
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

/** The banner must state the highest marking of the content on screen, so
 *  pages declare what they are showing rather than the shell guessing. */
const ClassificationContext = createContext<{
  classification: string;
  declare: (value: string) => void;
}>({ classification: "UNCLASSIFIED", declare: () => {} });

/** Order matters: the banner shows the highest marking declared. */
const MARKING_RANK: Record<string, number> = {
  UNCLASSIFIED: 0,
  CUI: 1,
  CONFIDENTIAL: 2,
  SECRET: 3,
  "TOP SECRET": 4,
};

function rankOf(marking: string): number {
  const upper = marking.toUpperCase();
  const match = Object.keys(MARKING_RANK)
    .filter((key) => upper.includes(key))
    .sort((a, b) => MARKING_RANK[b] - MARKING_RANK[a])[0];
  return match ? MARKING_RANK[match] : 0;
}

/** Declare the marking of the content this page displays.
 *
 * Called with the value from the record itself, never a constant. On unmount
 * the declaration is withdrawn so a later page cannot inherit a marking from
 * one the viewer has navigated away from. */
export function useDeclaredClassification(classification: string | null | undefined): void {
  const { declare } = useContext(ClassificationContext);
  useEffect(() => {
    if (!classification) return;
    declare(classification);
    return () => declare("UNCLASSIFIED");
  }, [classification, declare]);
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const load = useCallback(async () => {
    if (!getToken()) {
      setSession(null);
      setLoading(false);
      return;
    }
    try {
      const body = await api.get<{
        user: { email: string; full_name: string | null };
        permissions: string[];
      }>("/auth/me");
      setSession({
        email: body.user.email,
        fullName: body.user.full_name,
        permissions: body.permissions,
      });
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const value = useMemo<AuthValue>(
    () => ({
      session,
      loading,
      signIn: async (email, password) => {
        await api.login(email, password);
        await load();
      },
      signOut: () => {
        api.logout();
        setSession(null);
        router.push("/login");
      },
      can: (permission) => session?.permissions.includes(permission) ?? false,
    }),
    [session, loading, load, router],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Classification banner.
 *
 * Marked artifacts carry a banner top and bottom, which is the handling
 * convention these users work under. The value comes from the data, never a
 * hard-coded default.
 */
export function ClassificationBanner({
  classification,
  position,
}: {
  classification: string;
  position: "top" | "bottom";
}) {
  const level = classification.toUpperCase();
  const tone =
    level.includes("TOP SECRET")
      ? "bg-orange-600 text-white"
      : level.includes("SECRET")
        ? "bg-red-700 text-white"
        : level.includes("CONFIDENTIAL")
          ? "bg-blue-800 text-white"
          : level.includes("CUI")
            ? "bg-purple-800 text-white"
            : "bg-green-800 text-white";
  return (
    <div
      className={`${tone} px-3 py-0.5 text-center text-[11px] font-bold tracking-[0.18em] ${
        position === "top" ? "" : "mt-auto"
      }`}
    >
      {level}
    </div>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = (() => {
      try {
        return window.localStorage.getItem("aegis.theme");
      } catch {
        return null;
      }
    })();
    const prefersDark =
      stored === "dark" ||
      (stored === null && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(prefersDark);
    document.documentElement.classList.toggle("dark", prefersDark);
  }, []);

  return (
    <button
      onClick={() => {
        const next = !dark;
        setDark(next);
        document.documentElement.classList.toggle("dark", next);
        try {
          window.localStorage.setItem("aegis.theme", next ? "dark" : "light");
        } catch {
          /* per-viewer convenience only */
        }
      }}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:text-ink"
    >
      {dark ? "Light" : "Dark"}
    </button>
  );
}

const NAV = [
  { href: "/", label: "Portfolio" },
  { href: "/library", label: "Library" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { session, loading, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [classification, setClassification] = useState("UNCLASSIFIED");

  const declare = useCallback((value: string) => {
    // Never lower the banner below what has already been declared for this
    // view; a page that shows a mix of markings shows the highest.
    setClassification((current) => (rankOf(value) > rankOf(current) ? value : current));
  }, []);

  const classificationValue = useMemo(
    () => ({ classification, declare }),
    [classification, declare],
  );

  useEffect(() => {
    // A navigation resets the banner; the new page declares its own marking.
    setClassification("UNCLASSIFIED");
  }, [pathname]);

  useEffect(() => {
    if (!loading && !session && pathname !== "/login") router.replace("/login");
  }, [loading, session, pathname, router]);

  if (pathname === "/login") return <>{children}</>;

  return (
    <ClassificationContext.Provider value={classificationValue}>
    <div className="flex min-h-screen flex-col">
      <ClassificationBanner classification={classification} position="top" />

      <header className="sticky top-0 z-20 border-b border-line bg-raised/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-4 py-2.5">
          <Link href="/" className="flex items-center gap-2">
            <span
              className="grid h-6 w-6 place-items-center rounded bg-[rgb(var(--accent))] text-[11px] font-bold text-white"
              aria-hidden
            >
              Æ
            </span>
            <span className="text-sm font-semibold tracking-tight">Aegis Eval</span>
          </Link>

          <nav className="flex items-center gap-1 text-sm">
            {NAV.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-2.5 py-1 transition-colors ${
                    active ? "bg-[rgb(var(--unknown-bg))] text-ink" : "text-muted hover:text-ink"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {session ? (
              <div className="flex items-center gap-2">
                <span className="hidden text-xs text-muted sm:inline">{session.email}</span>
                <button
                  onClick={signOut}
                  className="rounded-md border border-line px-2 py-1 text-xs text-muted hover:text-ink"
                >
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5">{children}</main>

      <footer className="border-t border-line px-4 py-3">
        <div className="mx-auto max-w-[1400px] text-[11px] leading-relaxed text-muted">
          Aegis Eval produces evaluation evidence. It is not an authorisation to operate and does
          not substitute for the government&apos;s accreditation process. A dimension marked NOT
          EVALUATED has not been tested; it is not an implied pass.
        </div>
      </footer>

      <ClassificationBanner classification={classification} position="bottom" />
    </div>
    </ClassificationContext.Provider>
  );
}

/** Wrapper that renders loading, error and empty states consistently so no
 *  page silently shows nothing. */
export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetcher()
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load this view.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}
