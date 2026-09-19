"use client";

import Link from "next/link";
import { use, useState } from "react";

import { Status } from "@/components/status";
import { useAuth, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  Caveat,
  Disclosure,
  Empty,
  ErrorNote,
  Select,
  Spinner,
  Tag,
} from "@/components/ui";
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

/**
 * Stance carries the same square vocabulary as a verdict, because that is what
 * it is: evidence either argues for the claim, against it, or settles nothing.
 * The third case is the one people skim past, so it is drawn hollow rather than
 * left unmarked.
 */
const STANCE: Record<string, { square: string; text: string }> = {
  supports: { square: "bg-pass", text: "text-pass" },
  counters: { square: "bg-fail", text: "text-fail" },
  inconclusive: {
    square: "bg-transparent border border-dashed border-unknown",
    text: "text-muted",
  },
};

function Detail({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="text-2xs uppercase tracking-wider text-faint">{label}</div>
      <ul className="mt-1 space-y-0.5">
        {items.map((item) => (
          <li key={item} className="text-xs leading-relaxed text-muted">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClaimNode({ claim, depth }: { claim: AssuranceClaim; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const expandable = claim.evidence.length > 0 || claim.children.length > 0;

  const summary = (
    <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1 py-0.5">
      <Status status={claim.support_status} />
      <span className={`min-w-0 flex-1 text-sm ${depth === 0 ? "text-ink" : "text-ink-soft"}`}>
        {claim.statement}
      </span>
      {claim.evidence.length > 0 ? (
        <span className="tnum shrink-0 text-2xs text-faint">
          {claim.evidence.length} evidence
        </span>
      ) : null}
    </div>
  );

  const body = (
    <div className="space-y-2.5 pb-1 pt-1.5">
      {claim.argument ? (
        <p className="text-xs leading-relaxed text-muted">{claim.argument}</p>
      ) : null}

      {claim.evidence.length === 0 ? (
        // An unevidenced claim is the one thing an assurance case must never
        // let pass quietly, so it is stated rather than left blank.
        <p className="border-l border-warn/40 pl-2.5 text-xs leading-relaxed text-warn">
          No evidence is linked. A claim with no evidence is an assertion, not an argument.
        </p>
      ) : (
        <ul className="space-y-1">
          {claim.evidence.map((item) => {
            const stance = STANCE[item.stance] ?? STANCE.inconclusive;
            return (
              <li key={item.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
                <span
                  className={`inline-flex shrink-0 items-center gap-1.5 text-2xs uppercase tracking-wider ${stance.text}`}
                >
                  <span className={`h-[7px] w-[7px] shrink-0 ${stance.square}`} />
                  {item.stance}
                </span>
                {item.ref_type === "run" ? (
                  <Link href={`/runs/${item.ref_id}`} className="link-underline text-ink-soft hover:text-ink">
                    {item.detail?.label ?? "Run"}
                  </Link>
                ) : item.ref_type === "finding" ? (
                  <Link
                    href={`/findings/${item.ref_id}`}
                    className="link-underline text-ink-soft hover:text-ink"
                  >
                    {item.detail?.label ?? "Finding"}
                  </Link>
                ) : (
                  <span className="text-ink-soft">{item.detail?.label ?? item.ref_type}</span>
                )}
                {item.detail?.system ? (
                  <span className="text-muted">on {item.detail.system}</span>
                ) : null}
                {item.detail?.verdict ? (
                  <span className="tnum text-muted">
                    {item.detail.passed}/{item.detail.executions} passed
                  </span>
                ) : null}
                {item.note ? <span className="text-faint">— {item.note}</span> : null}
              </li>
            );
          })}
        </ul>
      )}

      <Detail label="Known limitations" items={claim.known_limitations} />
      <Detail label="Mitigations" items={claim.mitigations} />

      {claim.children.length > 0 ? (
        <div className="border-l border-line pl-3">
          {claim.children.map((child) => (
            <ClaimNode key={child.id} claim={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  );

  if (!expandable) {
    return (
      <div className="border-b border-line py-2 last:border-b-0">
        <div className="pl-5">{summary}</div>
        {claim.argument ? (
          <p className="mt-1 pl-5 text-xs leading-relaxed text-muted">{claim.argument}</p>
        ) : null}
      </div>
    );
  }

  return (
    <Disclosure
      open={open}
      onToggle={() => setOpen(!open)}
      summary={summary}
      className="border-b border-line py-2 last:border-b-0"
    >
      {body}
    </Disclosure>
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

      <div className="flex flex-wrap items-center gap-3">
        {(cases.data ?? []).length > 0 ? (
          <Select
            label="Case"
            value={activeId ?? ""}
            onChange={setSelected}
            options={(cases.data ?? []).map((item) => ({
              value: item.id,
              label: `${item.title} · ${item.status}`,
            }))}
          />
        ) : null}
        {can("assurance:write") ? (
          <Button onClick={draft} disabled={busy}>
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
          <CardHead
            title={detail.data.case.title}
            meta={detail.data.case.context ?? undefined}
            action={<Tag tone="strong">{detail.data.case.status}</Tag>}
          />
          <div className="border-t border-line px-4">
            {detail.data.claims.map((claim) => (
              <ClaimNode key={claim.id} claim={claim} depth={0} />
            ))}
          </div>

          <div className="space-y-2 border-t border-line px-4 py-3.5">
            <div className="text-2xs uppercase tracking-wider text-faint">Residual risk</div>
            <p className="text-sm leading-relaxed text-ink">
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
