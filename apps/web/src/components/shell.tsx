"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";

import {
  IconBell,
  IconLibrary,
  IconMoon,
  IconPortfolio,
  IconSearch,
  IconSun,
} from "@/components/icons";
import { Key } from "@/components/ui";
import { ApiError, api, getToken } from "@/lib/api";

/* ------------------------------------------------------------------ *
 * Session
 * ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ *
 * Classification banner
 * ------------------------------------------------------------------ */

const ClassificationContext = createContext<{
  classification: string;
  declare: (value: string) => void;
}>({ classification: "UNCLASSIFIED", declare: () => {} });

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

/** Declare the marking of the content this page displays, taken from the
 *  record itself rather than a constant. Withdrawn on unmount so a later page
 *  cannot inherit a marking from one the viewer has navigated away from. */
export function useDeclaredClassification(classification: string | null | undefined): void {
  const { declare } = useContext(ClassificationContext);
  useEffect(() => {
    if (!classification) return;
    declare(classification);
    return () => declare("UNCLASSIFIED");
  }, [classification, declare]);
}

/**
 * Handling banner, top and bottom.
 *
 * The one place in the interface where a saturated fill is used edge to edge:
 * a marking has to be unmissable, and it is the only element allowed to shout.
 */
export function ClassificationBanner({
  classification,
  position,
}: {
  classification: string;
  position: "top" | "bottom";
}) {
  const level = classification.toUpperCase();
  const tone = level.includes("TOP SECRET")
    ? "bg-[#c2410c] text-white"
    : level.includes("SECRET")
      ? "bg-[#b91c1c] text-white"
      : level.includes("CONFIDENTIAL")
        ? "bg-[#1e40af] text-white"
        : level.includes("CUI")
          ? "bg-[#6b21a8] text-white"
          : "bg-[#166534] text-white";
  return (
    <div
      className={`${tone} shrink-0 px-3 py-[3px] text-center text-2xs font-semibold tracking-[0.2em] ${
        position === "top" ? "" : "mt-auto"
      }`}
    >
      {level}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Theme
 * ------------------------------------------------------------------ */

function useTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const stored = (() => {
      try {
        return window.localStorage.getItem("aegis.theme");
      } catch {
        return null;
      }
    })();
    const prefers =
      stored === "dark" ||
      (stored === null && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(prefers);
    document.documentElement.classList.toggle("dark", prefers);
  }, []);
  const toggle = useCallback(() => {
    setDark((current) => {
      const next = !current;
      document.documentElement.classList.toggle("dark", next);
      try {
        window.localStorage.setItem("aegis.theme", next ? "dark" : "light");
      } catch {
        /* per-viewer convenience only */
      }
      return next;
    });
  }, []);
  return { dark, toggle };
}

/* ------------------------------------------------------------------ *
 * Command palette
 * ------------------------------------------------------------------ */

interface Command {
  id: string;
  group: string;
  label: string;
  hint?: string;
  href: string;
}

function useCommands(): Command[] {
  const [commands, setCommands] = useState<Command[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const projects = await api.get<
          Array<{ id: string; name: string; classification: string }>
        >("/projects");
        if (cancelled) return;
        const entries: Command[] = [];
        for (const project of projects) {
          entries.push({
            id: `project-${project.id}`,
            group: "Projects",
            label: project.name,
            hint: project.classification,
            href: `/projects/${project.id}`,
          });
          for (const [slug, label] of [
            ["", "Readiness"],
            ["findings", "Findings"],
            ["compare", "Comparison"],
            ["assurance", "Assurance"],
            ["plan", "Evaluation plan"],
            ["campaigns", "Campaigns"],
            ["frameworks", "Frameworks"],
            ["scenarios", "Scenarios"],
            ["reports", "Reports"],
          ] as const) {
            entries.push({
              id: `project-${project.id}-${slug || "root"}`,
              group: "Go to",
              label: `${project.name} · ${label}`,
              href: slug ? `/projects/${project.id}/${slug}` : `/projects/${project.id}`,
            });
          }
        }
        entries.push({
          id: "library",
          group: "Go to",
          label: "Library",
          hint: "Connectors, evaluators, attacks",
          href: "/library",
        });
        setCommands(entries);
      } catch {
        /* palette degrades to navigation-only; not worth surfacing */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return commands;
}

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const commands = useCommands();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const pool = needle
      ? commands.filter((c) => c.label.toLowerCase().includes(needle))
      : commands.filter((c) => c.group === "Projects").concat(
          commands.filter((c) => c.id === "library"),
        );
    return pool.slice(0, 24);
  }, [commands, query]);

  useEffect(() => {
    setSelected(0);
  }, [query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      // Focus after the enter animation starts so the caret does not jump.
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelected((i) => Math.min(i + 1, results.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((i) => Math.max(i - 1, 0));
      } else if (event.key === "Enter") {
        event.preventDefault();
        const target = results[selected];
        if (target) {
          router.push(target.href);
          onClose();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, results, selected, router, onClose]);

  const grouped = useMemo(() => {
    const map = new Map<string, Command[]>();
    for (const command of results) {
      const list = map.get(command.group) ?? [];
      list.push(command);
      map.set(command.group, list);
    }
    return Array.from(map.entries());
  }, [results]);

  let flatIndex = -1;

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
        >
          <div
            className="absolute inset-0 bg-ink/10 backdrop-blur-[1px]"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-label="Command palette"
            className="relative w-full max-w-[440px] border border-line-strong bg-panel"
            initial={{ opacity: 0, y: -6, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.995 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
          >
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Type a command or search…"
              className="w-full border-b border-line bg-transparent px-3.5 py-3 text-base text-ink outline-none placeholder:text-faint"
            />

            <div className="max-h-[46vh] overflow-y-auto py-1.5">
              {results.length === 0 ? (
                <p className="px-3.5 py-6 text-center text-sm text-muted">No matches.</p>
              ) : (
                grouped.map(([group, items]) => (
                  <div key={group} className="mb-1">
                    <div className="px-3.5 py-1 text-2xs uppercase tracking-wider text-faint">
                      {group}
                    </div>
                    {items.map((command) => {
                      flatIndex += 1;
                      const active = flatIndex === selected;
                      const index = flatIndex;
                      return (
                        <button
                          key={command.id}
                          onMouseEnter={() => setSelected(index)}
                          onClick={() => {
                            router.push(command.href);
                            onClose();
                          }}
                          className={`flex w-full items-center gap-2.5 px-3.5 py-1.5 text-left text-sm transition-colors duration-100 ${
                            active ? "bg-sunken text-ink" : "text-ink-soft"
                          }`}
                        >
                          <span className="h-[7px] w-[7px] shrink-0 border border-line-strong" />
                          <span className="min-w-0 flex-1 truncate">{command.label}</span>
                          {command.hint ? (
                            <span className="shrink-0 text-2xs text-faint">{command.hint}</span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>

            <div className="flex items-center justify-between border-t border-line px-3.5 py-2 text-2xs text-faint">
              <span>Aegis Eval</span>
              <span className="flex items-center gap-1.5">
                <Key>↑</Key>
                <Key>↓</Key>
                <span className="mr-1">navigate</span>
                <Key>↵</Key>
                <span className="mr-1">open</span>
                <Key>esc</Key>
              </span>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/* ------------------------------------------------------------------ *
 * Rail
 * ------------------------------------------------------------------ */

const RAIL = [
  { href: "/", label: "Portfolio", Icon: IconPortfolio, exact: true },
  { href: "/library", label: "Library", Icon: IconLibrary, exact: false },
];

function Rail() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Primary"
      className="flex w-rail shrink-0 flex-col items-center border-r border-line bg-panel py-3"
    >
      <Link href="/" aria-label="Aegis Eval" className="mb-5">
        {/* The mark: a shield reduced to a single hairline stroke. */}
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
          <path
            d="M9 1.5 15.5 4v5.5c0 3.8-2.8 6.2-6.5 7-3.7-.8-6.5-3.2-6.5-7V4L9 1.5Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.2"
            className="text-ink"
          />
          <path d="M9 5.5v7" stroke="currentColor" strokeWidth="1.2" className="text-ink" />
        </svg>
      </Link>

      <div className="flex flex-col items-center gap-1">
        {RAIL.map(({ href, label, Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              aria-current={active ? "page" : undefined}
              className={`relative grid h-8 w-8 place-items-center transition-colors duration-150 ease-out ${
                active ? "text-ink" : "text-faint hover:text-ink-soft"
              }`}
            >
              {active ? (
                <motion.span
                  layoutId="rail-active"
                  className="absolute inset-0 bg-sunken"
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                />
              ) : null}
              <Icon className="relative" />
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/* ------------------------------------------------------------------ *
 * Slide-over
 * ------------------------------------------------------------------ */

/**
 * Right-hand detail panel.
 *
 * Detail opens beside the list rather than replacing it, so a tester reading
 * one failure never loses the set it came from. Escape closes; the footer
 * says so rather than assuming it is known.
 */
export function SlideOver({
  open,
  onClose,
  children,
  footer,
  label,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  label: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-ink/10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            role="dialog"
            aria-label={label}
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[560px] flex-col border-l border-line bg-panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 420, damping: 40, mass: 0.8 }}
          >
            <div className="flex-1 overflow-y-auto">{children}</div>
            {footer ? (
              <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-2xs text-faint">
                {footer}
                <span className="flex items-center gap-1.5">
                  <Key>esc</Key>
                  <span>close</span>
                </span>
              </div>
            ) : null}
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}

/* ------------------------------------------------------------------ *
 * Shell
 * ------------------------------------------------------------------ */

export function AppShell({ children }: { children: ReactNode }) {
  const { session, loading, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const { dark, toggle } = useTheme();
  const [classification, setClassification] = useState("UNCLASSIFIED");
  const [paletteOpen, setPaletteOpen] = useState(false);

  const declare = useCallback((value: string) => {
    setClassification((current) => (rankOf(value) > rankOf(current) ? value : current));
  }, []);

  const classificationValue = useMemo(
    () => ({ classification, declare }),
    [classification, declare],
  );

  useEffect(() => {
    setClassification("UNCLASSIFIED");
  }, [pathname]);

  useEffect(() => {
    if (!loading && !session && pathname !== "/login") router.replace("/login");
  }, [loading, session, pathname, router]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (pathname === "/login") return <>{children}</>;

  const initials = (session?.fullName ?? session?.email ?? "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <ClassificationContext.Provider value={classificationValue}>
      <div className="flex h-screen flex-col overflow-hidden">
        <ClassificationBanner classification={classification} position="top" />

        <div className="flex min-h-0 flex-1">
          <Rail />

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-topbar shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
              <button
                onClick={() => setPaletteOpen(true)}
                className="group flex flex-1 items-center gap-2 text-left text-sm text-faint transition-colors duration-150 hover:text-muted"
              >
                <IconSearch className="shrink-0" />
                <span>Find anything…</span>
                <span className="ml-auto flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                  <Key>⌘</Key>
                  <Key>K</Key>
                </span>
              </button>

              <button
                onClick={toggle}
                aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
                className="grid h-7 w-7 place-items-center text-faint transition-colors duration-150 hover:text-ink"
              >
                {dark ? <IconSun /> : <IconMoon />}
              </button>

              <button
                aria-label="Notifications"
                className="grid h-7 w-7 place-items-center text-faint transition-colors duration-150 hover:text-ink"
              >
                <IconBell />
              </button>

              {session ? (
                <button
                  onClick={signOut}
                  title={`${session.email} — sign out`}
                  className="grid h-6 w-6 place-items-center border border-line bg-sunken text-2xs text-muted transition-colors duration-150 hover:border-line-strong hover:text-ink"
                >
                  {initials}
                </button>
              ) : null}
            </header>

            <main className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[1320px] px-5 py-5">{children}</div>
            </main>
          </div>
        </div>

        <ClassificationBanner classification={classification} position="bottom" />
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </ClassificationContext.Provider>
  );
}

/* ------------------------------------------------------------------ *
 * Data loading
 * ------------------------------------------------------------------ */

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
