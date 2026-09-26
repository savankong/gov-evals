"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Fragment,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ComponentType, ReactNode } from "react";

import {
  IconBell,
  IconBenchmark,
  IconCapture,
  IconCollapse,
  IconAdmin,
  IconCompass,
  IconDataset,
  IconExpand,
  IconExpert,
  IconLibrary,
  IconMoon,
  IconPackage,
  IconPortfolio,
  IconReview,
  IconRoster,
  IconSearch,
  IconSun,
  IconTarget,
} from "@/components/icons";
import { Key } from "@/components/ui";
import { ApiError, api, getToken } from "@/lib/api";
import { TourBanner, TourHelpMenu, useTourShell } from "@/tour";

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
/**
 * The marking banner.
 *
 * Shown once, at the top. The paper convention is to repeat the marking at the
 * foot of every page; on a single continuously scrolling application view a
 * second copy is pinned to the bottom of the viewport rather than to the end
 * of the content, so it marks the window and not the document -- which is not
 * what the convention is for.
 */
export function ClassificationBanner({ classification }: { classification: string }) {
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
      className={`${tone} shrink-0 px-3 py-[3px] text-center text-2xs font-semibold tracking-[0.2em]`}
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
        entries.push(
          {
            id: "weakness",
            group: "Go to",
            label: "Weakness map",
            hint: "Where the model is wrong",
            href: "/weakness",
          },
          {
            id: "capture",
            group: "Go to",
            label: "Capture",
            hint: "Solve a problem step by step",
            href: "/capture",
          },
          {
            id: "library",
            group: "Go to",
            label: "Library",
            hint: "Connectors, evaluators, attacks",
            href: "/library",
          },
          {
            id: "packages",
            group: "Go to",
            label: "Packages",
            hint: "Deliveries to customers",
            href: "/packages",
          },
        );
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
            className="relative w-full max-w-[27.5rem] border border-line-strong bg-panel"
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
 * Sidebar
 * ------------------------------------------------------------------ */

interface NavItem {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  exact?: boolean;
  /** Shown beside the label when expanded. Suppressed when collapsed, because
   *  a count with no label attached to it is a number floating in a rail. */
  badge?: number;
}

interface NavGroup {
  /** Null for a group that needs no heading above its first item. */
  label: string | null;
  items: NavItem[];
}

/**
 * Three groups, by what you came to do: see where the model stands, move data
 * through, or do expert work. The six pipeline verbs in the README are the
 * design; the rail is for getting somewhere, and a heading over one link is
 * a heading with nothing to group. See docs/platform.md.
 */
const NAV: NavGroup[] = [
  {
    label: null,
    items: [
      { href: "/", label: "Portfolio", Icon: IconPortfolio, exact: true },
      { href: "/weakness", label: "Weakness map", Icon: IconTarget },
      { href: "/benchmarks", label: "Benchmarks", Icon: IconBenchmark },
    ],
  },
  {
    label: "Data",
    items: [
      { href: "/datasets", label: "Datasets", Icon: IconDataset },
      { href: "/library", label: "Library", Icon: IconLibrary },
      { href: "/packages", label: "Packages", Icon: IconPackage },
    ],
  },
  {
    label: "Capture",
    items: [
      { href: "/capture", label: "Solve", Icon: IconCapture },
      { href: "/review", label: "Review queue", Icon: IconReview },
      { href: "/experts", label: "Experts", Icon: IconExpert },
    ],
  },
];

/** Pinned to the foot of the rail: visited once, or rarely, not every day. */
const NAV_FOOTER: NavItem[] = [
  { href: "/welcome", label: "Getting started", Icon: IconCompass },
  { href: "/admin", label: "Administration", Icon: IconAdmin },
];

const NAV_STORAGE_KEY = "aegis.nav.expanded";

/**
 * Sidebar open/closed state.
 *
 * Persisted per viewer, because which one you want depends on the screen you
 * are at rather than on the work: the same person wants labels on a desktop
 * and a rail on a laptop beside a spreadsheet. Defaults to expanded -- a new
 * reviewer should see what the sections are called before learning the glyphs.
 */
function useNavExpanded(): [boolean, () => void] {
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(NAV_STORAGE_KEY);
      if (stored !== null) setExpanded(stored === "true");
    } catch {
      /* per-viewer convenience only; the default stands */
    }
  }, []);

  const toggle = useCallback(() => {
    setExpanded((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(NAV_STORAGE_KEY, String(next));
      } catch {
        /* per-viewer convenience only */
      }
      return next;
    });
  }, []);

  return [expanded, toggle];
}

function NavLink({ item, expanded }: { item: NavItem; expanded: boolean }) {
  const pathname = usePathname();
  const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
  const { Icon } = item;

  return (
    <Link
      href={item.href}
      // The tooltip is the only thing naming the destination when collapsed, so
      // it is not optional there.
      title={expanded ? undefined : item.label}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      // The product tour points at the rail by these; see src/tour/steps.ts.
      data-tour={`nav.${item.href.replace(/^\//, "") || "portfolio"}`}
      className={`relative flex h-8 items-center transition-colors duration-150 ease-out ${
        expanded ? "gap-2.5 px-2.5" : "justify-center px-0"
      } ${active ? "text-ink" : "text-faint hover:text-ink-soft"}`}
    >
      {active ? (
        <motion.span
          layoutId="nav-active"
          className="absolute inset-0 bg-sunken"
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
        />
      ) : null}
      {/* With the rule gone, the icon is what marks the current page: full
          ink against the faint icons of everything else. */}
      <Icon className={`relative shrink-0 ${active ? "text-ink" : ""}`} />
      {expanded ? (
        <span className="relative min-w-0 flex-1 truncate text-sm">{item.label}</span>
      ) : null}
      {expanded && item.badge ? (
        <span className="tnum relative shrink-0 text-2xs text-faint">{item.badge}</span>
      ) : null}
    </Link>
  );
}

function Sidebar({
  expanded,
  onToggle,
  overlay = false,
}: {
  expanded: boolean;
  onToggle: () => void;
  overlay?: boolean;
}) {
  return (
    <motion.nav
      aria-label="Primary"
      initial={false}
      // As a drawer the nav is always at its full width -- the collapsed
      // 44px rail is a desktop affordance, and on a phone it would be a
      // column of unlabelled icons over the content.
      animate={overlay ? { width: 224 } : { width: expanded ? 224 : 44 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={`flex shrink-0 flex-col overflow-hidden border-r border-line bg-panel py-3 ${
        overlay ? "h-full" : ""
      }`}
    >
      <div
        className={`mb-4 flex h-8 items-center ${
          expanded ? "justify-between px-2.5" : "justify-center"
        }`}
      >
        <Link href="/" aria-label="Aegis Eval" className="flex items-center gap-2 text-ink">
          {/* The mark: a shield reduced to a single hairline stroke. */}
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden className="shrink-0">
            <path
              d="M9 1.5 15.5 4v5.5c0 3.8-2.8 6.2-6.5 7-3.7-.8-6.5-3.2-6.5-7V4L9 1.5Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.2"
            />
            <path d="M9 5.5v7" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          {expanded ? (
            <span className="whitespace-nowrap text-sm text-ink">Aegis Eval</span>
          ) : null}
        </Link>
        {expanded ? (
          <button
            onClick={onToggle}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
            aria-expanded
            className="grid h-6 w-6 shrink-0 place-items-center text-faint transition-colors duration-150 hover:text-ink"
          >
            <IconCollapse />
          </button>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
        {NAV.map((group) => (
          <div key={group.label ?? "root"}>
            {group.label ? (
              expanded ? (
                <div className="px-2.5 pb-1 text-2xs uppercase tracking-wider text-faint">
                  {group.label}
                </div>
              ) : (
                // Collapsed, a group heading has nowhere to go. A rule keeps the
                // grouping legible without inventing an abbreviation for it.
                <div className="mx-auto mb-1.5 h-px w-4 bg-line" aria-hidden />
              )
            ) : null}
            <div className="flex flex-col">
              {group.items.map((item) => (
                <NavLink key={item.href} item={item} expanded={expanded} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex shrink-0 flex-col border-t border-line pt-3">
        {NAV_FOOTER.map((item) => (
          <NavLink key={item.href} item={item} expanded={expanded} />
        ))}
        {/* Aegis Eval is part of Your Roster. Said once, at the foot of the
            rail below everything you would come here to use, in the faintest
            ink the interface has: present for anyone who looks, never in the
            way of anyone who does not. */}
        <a
          href="https://www.yourrosterapp.com"
          target="_blank"
          rel="noopener noreferrer"
          title="Aegis Eval is part of Your Roster"
          aria-label="Part of Your Roster"
          className={`mt-1 flex h-7 items-center text-faint transition-colors duration-150 hover:text-muted ${
            expanded ? "gap-2 px-2.5" : "justify-center"
          }`}
        >
          <IconRoster className="shrink-0" aria-hidden />
          {expanded ? (
            <span className="whitespace-nowrap text-2xs">Part of Your Roster</span>
          ) : null}
        </a>
      </div>

      {!expanded ? (
        <button
          onClick={onToggle}
          title="Expand sidebar"
          aria-label="Expand sidebar"
          aria-expanded={false}
          className="mx-auto grid h-8 w-8 shrink-0 place-items-center text-faint transition-colors duration-150 hover:text-ink"
        >
          <IconExpand />
        </button>
      ) : null}
    </motion.nav>
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
            className="fixed right-0 top-0 z-50 flex h-full w-full max-w-[35rem] flex-col border-l border-line bg-panel"
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
  const [navExpanded, toggleNav] = useNavExpanded();
  const [navOpen, setNavOpen] = useState(false);
  const [classification, setClassification] = useState("UNCLASSIFIED");
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Changes when the tour switches the app onto its sample or back, so the
  // page remounts and reloads: nothing fetched from one is left on screen
  // under the other.
  const tour = useTourShell();

  const declare = useCallback((value: string) => {
    setClassification((current) => (rankOf(value) > rankOf(current) ? value : current));
  }, []);

  const classificationValue = useMemo(
    () => ({ classification, declare }),
    [classification, declare],
  );

  useEffect(() => {
    setClassification("UNCLASSIFIED");
    // A drawer left open over the page someone just navigated to is a
    // second tap they did not ask for.
    setNavOpen(false);
  }, [pathname]);

  // Published benchmark pages are read without an account. They render
  // outside the shell, which is where the session, navigation and project
  // data live.
  const isPublic = pathname === "/public" || pathname.startsWith("/public/");

  useEffect(() => {
    if (!loading && !session && pathname !== "/login" && !isPublic) router.replace("/login");
  }, [loading, session, pathname, router, isPublic]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      // Bare "[" toggles the sidebar, but not while someone is typing it into
      // a field.
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;
      if (event.key === "[" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        toggleNav();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleNav]);

  if (pathname === "/login" || isPublic) return <>{children}</>;

  const initials = (session?.fullName ?? session?.email ?? "?")
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <ClassificationContext.Provider value={classificationValue}>
      <div className="flex h-screen flex-col overflow-hidden">
        <ClassificationBanner classification={classification} />
        <TourBanner />

        {/* `relative` so the drawer below can be positioned against this row
            rather than the viewport, which keeps it under the classification
            banner. A marking that a navigation drawer can cover is not a
            marking. */}
        <div className="relative flex min-h-0 flex-1">
          {/* Below md the nav is a drawer. Rendered inline it took 224px of a
              390px viewport, which left the topbar and the table clipped off
              the right edge with no way to scroll to them. */}
          <div className="hidden md:flex">
            <Sidebar expanded={navExpanded} onToggle={toggleNav} />
          </div>

          <AnimatePresence>
            {navOpen ? (
              <>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  onClick={() => setNavOpen(false)}
                  className="absolute inset-0 z-40 bg-ink/20 md:hidden"
                  aria-hidden
                />
                <motion.div
                  initial={{ x: -224 }}
                  animate={{ x: 0 }}
                  exit={{ x: -224 }}
                  transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                  className="absolute inset-y-0 left-0 z-50 md:hidden"
                  onClick={() => setNavOpen(false)}
                >
                  <Sidebar expanded overlay onToggle={() => setNavOpen(false)} />
                </motion.div>
              </>
            ) : null}
          </AnimatePresence>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-topbar shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
              <button
                type="button"
                onClick={() => setNavOpen(true)}
                aria-label="Open navigation"
                data-tour="shell.open-nav"
                className="-ml-1 shrink-0 p-1 text-muted transition-colors duration-150 hover:text-ink md:hidden"
              >
                <IconExpand />
              </button>
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

              <TourHelpMenu />

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
              <div
                className="mx-auto w-full max-w-[82.5rem] px-5 py-5"
                // Room below the page for the tour's bottom sheet on a phone,
                // so whatever it points at can be scrolled clear of it.
                style={{ paddingBottom: "calc(1.25rem + var(--tour-sheet, 0px))" }}
              >
                <Fragment key={tour.epoch}>{children}</Fragment>
              </div>
            </main>
          </div>
        </div>
      </div>

      <CommandPalette
        key={tour.epoch}
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
      />
    </ClassificationContext.Provider>
  );
}

/* ------------------------------------------------------------------ *
 * Data loading
 * ------------------------------------------------------------------ */

export function useResource<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): {
  data: T | null;
  error: string | null;
  // The status is kept beside the message so a view can show what the server
  // actually said. A reader who reports "it says 500" is telling an operator
  // something a sentence alone does not.
  status: number | null;
  loading: boolean;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setStatus(null);
    fetcher()
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load this view.");
        setStatus(err instanceof ApiError ? err.status : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, status, loading, reload: () => setNonce((n) => n + 1) };
}
