"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Card, ErrorNote } from "@/components/ui";
import { useAuth } from "@/components/shell";
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
      <div className="bg-green-800 px-3 py-0.5 text-center text-[11px] font-bold tracking-[0.18em] text-white">
        UNCLASSIFIED
      </div>

      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-lg bg-[rgb(var(--accent))] text-sm font-bold text-white">
              Æ
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Aegis Eval</h1>
            <p className="mt-1 text-sm text-muted">Test AI for the mission, not the benchmark.</p>
          </div>

          <Card className="p-5">
            <form onSubmit={submit} className="space-y-3">
              <div>
                <label htmlFor="email" className="mb-1 block text-xs font-medium text-muted">
                  Email
                </label>
                <input
                  id="email"
                  type="text"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-[rgb(var(--accent))]"
                  placeholder="admin@aegis.local"
                />
              </div>
              <div>
                <label htmlFor="password" className="mb-1 block text-xs font-medium text-muted">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-[rgb(var(--accent))]"
                />
              </div>

              {error ? <ErrorNote message={error} /> : null}

              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>

            <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-muted">
              This deployment also accepts OIDC and, where a terminating proxy validates the
              certificate chain, CAC/PIV. Local accounts are intended for development.
            </p>
          </Card>
        </div>
      </div>

      <div className="bg-green-800 px-3 py-0.5 text-center text-[11px] font-bold tracking-[0.18em] text-white">
        UNCLASSIFIED
      </div>
    </div>
  );
}
