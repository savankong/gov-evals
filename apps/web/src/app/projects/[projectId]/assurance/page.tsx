"use client";

import Link from "next/link";
import { use, useState } from "react";

import { StatusChip } from "@/components/status";
import { useAuth, useResource } from "@/components/shell";
import { Button, Card, CardHeader, Caveat, Empty, ErrorNote, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { AssuranceClaim } from "@/lib/types";

interface CaseSummary {
  id: string;
  title: string;
  status: string;
  context: string | null;
  decision_authority: string | null;
  residual_risk_statement: string | null;
}

interface CaseDetail {
  case: CaseSummary;
  claims: AssuranceClaim[];
}

const STANCE_STYLE: Record<string, string> = {
  supports: "text-[rgb(var(--pass))]",
  counters: "text-[rgb(var(--fail))]",
  inconclusive: "text-muted",
};

function ClaimNode({ claim, depth }: { claim: AssuranceClaim; depth: number }) {
  const [open, setOpen] = useState(depth < 2);

  return (
    <div className={depth > 0 ? "border-l border-line pl-4" : ""}>
      <div className="py-2.5">
        <div className="flex flex-wrap items-start gap-2">
          <StatusChip status={claim.support_status} />
          <p className={`min-w-0 flex-1 ${depth === 0 ? "text-sm font-medium" : "text-sm"}`}>
            {claim.statement}
          </p>
          {(claim.evidence.length > 0 || claim.children.length > 0) && (
            <button
              onClick={() => setOpen(!open)}
              className="shrink-0 text-xs text-muted hover:text-ink"
            >
              {open ? "Hide" : `Show ${claim.evidence.length} evidence`}
            </button>
          )}
        </div>

        {claim.argument ? (
          <p className="mt-1 pl-1 text-xs leading-relaxed text-muted">{claim.argument}</p>
        ) : null}

        {open ? (
          <div className="mt-2 space-y-2 pl-1">
            {claim.evidence.length === 0 ? (
              <p className="text-xs italic text-muted">
                No evidence is linked. A claim with no evidence is an assertion, not an argument.
              </p>
            ) : (
              <ul className="space-y-1">
                {claim.evidence.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-baseline gap-2 text-xs">
                    <span
                      className={`shrink-0 font-medium uppercase tracking-wide ${
                        STANCE_STYLE[item.stance] ?? "text-muted"
                      }`}
                    >
                      {item.stance}
                    </span>
                    {item.ref_type === "run" ? (
                      <Link href={`/runs/${item.ref_id}`} className="hover:underline">
                        {item.detail?.label ?? "Run"}
                      </Link>
                    ) : item.ref_type === "finding" ? (
                      <Link href={`/findings/${item.ref_id}`} className="hover:underline">
                        {item.detail?.label ?? "Finding"}
                      </Link>
                    ) : (
                      <span>{item.detail?.label ?? item.ref_type}</span>
                    )}
                    {item.detail?.system ? (
                      <span className="text-muted">on {item.detail.system}</span>
                    ) : null}
                    {item.detail?.verdict ? (
                      <span className="text-muted">
                        {item.detail.passed}/{item.detail.executions} passed
                      </span>
                    ) : null}
                    {item.note ? <span className="text-muted">— {item.note}</span> : null}
                  </li>
                ))}
              </ul>
            )}

            {claim.known_limitations.length > 0 ? (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted">
                  Known limitations
                </div>
                <ul className="mt-0.5 space-y-0.5">
                  {claim.known_limitations.map((item) => (
                    <li key={item} className="text-xs text-muted">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {claim.mitigations.length > 0 ? (
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted">Mitigations</div>
                <ul className="mt-0.5 space-y-0.5">
                  {claim.mitigations.map((item) => (
                    <li key={item} className="text-xs">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {open && claim.children.length > 0 ? (
        <div className="space-y-0">
          {claim.children.map((child) => (
            <ClaimNode key={child.id} claim={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function AssurancePage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params);
  const { can } = useAuth();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const cases = useResource<CaseSummary[]>(
    () => api.get<CaseSummary[]>(`/projects/${projectId}/assurance`),
    [projectId],
  );
  const [selected, setSelected] = useState<string | null>(null);
  const activeId = selected ?? cases.data?.[0]?.id ?? null;

  const detail = useResource<CaseDetail | null>(
    () => (activeId ? api.get<CaseDetail>(`/assurance/${activeId}`) : Promise.resolve(null)),
    [activeId],
  );

  async function draft() {
    setBusy(true);
    setActionError(null);
    try {
      const created = await api.post<{ id: string }>(`/projects/${projectId}/assurance/draft`);
      setSelected(created.id);
      cases.reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not draft a case.");
    } finally {
      setBusy(false);
    }
  }

  if (cases.loading) return <Spinner label="Loading assurance cases" />;
  if (cases.error) return <ErrorNote message={cases.error} />;

  return (
    <div className="space-y-4">
      {actionError ? <ErrorNote message={actionError} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        {(cases.data ?? []).map((item) => (
          <button
            key={item.id}
            onClick={() => setSelected(item.id)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              activeId === item.id
                ? "border-[rgb(var(--accent))] bg-[rgb(var(--accent))]/10 text-ink"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {item.title} · {item.status}
          </button>
        ))}
        {can("assurance:write") ? (
          <Button onClick={draft} disabled={busy} size="sm">
            {busy ? "Drafting…" : "Draft from evidence"}
          </Button>
        ) : null}
      </div>

      {!activeId ? (
        <Card>
          <Empty
            title="No assurance case yet"
            detail="An assurance case turns scattered results into a structured argument: claim, argument, evidence, limitation, residual risk."
          />
        </Card>
      ) : detail.loading ? (
        <Spinner label="Loading case" />
      ) : detail.error ? (
        <ErrorNote message={detail.error} />
      ) : detail.data ? (
        <Card>
          <CardHeader
            title={detail.data.case.title}
            subtitle={detail.data.case.context ?? undefined}
          />
          <div className="px-4 py-2">
            {detail.data.claims.map((claim) => (
              <ClaimNode key={claim.id} claim={claim} depth={0} />
            ))}
          </div>

          <div className="space-y-2 border-t border-line px-4 py-3">
            <div className="text-[11px] uppercase tracking-wider text-muted">Residual risk</div>
            <p className="text-sm">
              {detail.data.case.residual_risk_statement ??
                "No residual risk statement has been recorded."}
            </p>
            <p className="text-xs text-muted">
              Decision authority: {detail.data.case.decision_authority ?? "not recorded"}
            </p>
            <Caveat>
              Residual risk is accepted by the designated authority, not by this platform. This
              case assembles the evidence for that decision; it does not make it. A subclaim marked
              NOT EVALUATED has no supporting evidence either way.
            </Caveat>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
