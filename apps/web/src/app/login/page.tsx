"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/shell";
import { Button, ErrorNote } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <div className="bg-[#166534] px-3 py-[3px] text-center text-2xs font-semibold tracking-[0.2em] text-white">
        UNCLASSIFIED
      </div>

      <div className="flex flex-1 items-center justify-center px-4">
        <motion.div
          className="w-full max-w-[25.5rem]"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="mb-8 text-center">
            <svg width="26" height="26" viewBox="0 0 18 18" className="mx-auto mb-5" aria-hidden>
              <path
                d="M9 1.5 15.5 4v5.5c0 3.8-2.8 6.2-6.5 7-3.7-.8-6.5-3.2-6.5-7V4L9 1.5Z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                className="text-ink"
              />
              <path d="M9 5.5v7" stroke="currentColor" strokeWidth="1" className="text-ink" />
            </svg>
            <h1 className="font-serif text-3xl text-ink">Aegis Eval</h1>
            <p className="mt-1.5 text-sm text-muted">
              Test AI for the mission, not the benchmark.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-3">
            <div>
              <label htmlFor="email" className="mb-1.5 block text-xs text-muted">
                Email
              </label>
              <input
                id="email"
                type="text"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@organisation.mil"
                className="h-8 w-full border border-line bg-panel px-2.5 text-base text-ink outline-none transition-colors duration-150 placeholder:text-faint focus:border-ink"
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-xs text-muted">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="h-8 w-full border border-line bg-panel px-2.5 text-base text-ink outline-none transition-colors duration-150 focus:border-ink"
              />
            </div>

            {error ? <ErrorNote message={error} /> : null}

            <Button type="submit" variant="primary" disabled={busy} className="w-full">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="mt-6 border-t border-line pt-4 text-xs leading-relaxed text-muted">
            This deployment also accepts OIDC and, where a terminating proxy validates the
            certificate chain, CAC/PIV. Local accounts are intended for development.
          </p>
        </motion.div>
      </div>

    </div>
  );
}
