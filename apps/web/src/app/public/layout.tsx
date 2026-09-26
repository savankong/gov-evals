import Link from "next/link";
import type { ReactNode } from "react";

/** The public benchmark pages: no account, no app navigation, nothing that
 *  links into records behind a login. */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 md:px-8">
          <Link href="/public/benchmarks" className="flex items-baseline gap-2 text-ink">
            <span className="text-sm font-medium">Aegis Eval</span>
            <span className="text-2xs uppercase tracking-wider text-muted">Benchmarks</span>
          </Link>
          <Link href="/login" className="link-underline text-xs text-muted hover:text-ink">
            Sign in
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 md:px-8">{children}</main>
      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl space-y-1 px-4 py-6 text-2xs text-muted md:px-8">
          <p>
            Each figure is computed from stored results and each report carries a SHA-256. A pass rate is a
            measurement on one question set under stated conditions. It is not a trust score.
          </p>
          <p>UNCLASSIFIED. Only reports marked UNCLASSIFIED and published by their program appear here.</p>
        </div>
      </footer>
    </div>
  );
}
