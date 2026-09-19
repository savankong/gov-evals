"use client";

import { useState } from "react";

import { EvaluatorKindBadge } from "@/components/status";
import { useResource } from "@/components/shell";
import { Card, CardHeader, Caveat, ErrorNote, Spinner, Tabs } from "@/components/ui";
import { api } from "@/lib/api";

interface Evaluator {
  key: string;
  kind: string;
  label: string;
  description: string;
}
interface Connector {
  key: string;
  label: string;
  requires_egress: boolean;
}
interface Attack {
  key: string;
  name: string;
  category: string;
  description: string;
  vector: string;
  severity: string;
  mitigation: string;
}
interface Pack {
  key: string;
  name: string;
  kind: string;
  version: string;
  publisher: string | null;
  description: string | null;
  content_hash: string;
}

export default function LibraryPage() {
  const [tab, setTab] = useState("packs");

  const packs = useResource<{ packs: Pack[] }>(() => api.get("/packs"));
  const evaluators = useResource<{ evaluators: Evaluator[] }>(() => api.get("/evaluators"));
  const connectors = useResource<{ connectors: Connector[] }>(() => api.get("/connectors"));
  const attacks = useResource<{ attacks: Attack[] }>(() => api.get("/attacks"));

  const loading = packs.loading || evaluators.loading || connectors.loading || attacks.loading;
  const error = packs.error ?? evaluators.error ?? connectors.error ?? attacks.error;

  if (loading) return <Spinner label="Loading library" />;
  if (error) return <ErrorNote message={error} />;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Library</h1>
        <p className="mt-0.5 text-sm text-muted">
          What this deployment can evaluate with, and what it can evaluate against.
        </p>
      </div>

      <Tabs
        tabs={[
          { key: "packs", label: "Packs", count: packs.data?.packs.length },
          { key: "evaluators", label: "Evaluators", count: evaluators.data?.evaluators.length },
          { key: "connectors", label: "Connectors", count: connectors.data?.connectors.length },
          { key: "attacks", label: "Attack library", count: attacks.data?.attacks.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "packs" ? (
        <div className="grid gap-3 md:grid-cols-2">
          {(packs.data?.packs ?? []).map((pack) => (
            <Card key={pack.key} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">{pack.name}</h3>
                  <code className="font-mono text-[11px] text-muted">{pack.key}</code>
                </div>
                <span className="shrink-0 rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                  {pack.kind}
                </span>
              </div>
              {pack.description ? (
                <p className="mt-2 text-xs leading-relaxed text-muted">{pack.description}</p>
              ) : null}
              <div className="mt-2 flex items-center gap-3 text-[11px] text-muted">
                <span>v{pack.version}</span>
                {pack.publisher ? <span>{pack.publisher}</span> : null}
              </div>
            </Card>
          ))}
        </div>
      ) : null}

      {tab === "evaluators" ? (
        <Card>
          <CardHeader
            title="Evaluators"
            subtitle="Four kinds, so no single evaluator is treated as definitive"
          />
          <div className="divide-y divide-line">
            {(evaluators.data?.evaluators ?? []).map((evaluator) => (
              <div key={evaluator.key} className="px-4 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="font-mono text-xs">{evaluator.key}</code>
                  <EvaluatorKindBadge kind={evaluator.kind} />
                  <span className="text-sm">{evaluator.label}</span>
                </div>
                {evaluator.description ? (
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">
                    {evaluator.description}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {tab === "connectors" ? (
        <Card>
          <CardHeader
            title="Connectors"
            subtitle="Adapters speak wire protocols, not vendors"
          />
          <div className="divide-y divide-line">
            {(connectors.data?.connectors ?? []).map((connector) => (
              <div key={connector.key} className="flex items-center gap-3 px-4 py-2.5">
                <code className="font-mono text-xs">{connector.key}</code>
                <span className="flex-1 text-sm">{connector.label}</span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] ${
                    connector.requires_egress
                      ? "bg-[rgb(var(--warn-bg))] text-[rgb(var(--warn))]"
                      : "bg-[rgb(var(--pass-bg))] text-[rgb(var(--pass))]"
                  }`}
                >
                  {connector.requires_egress ? "needs egress" : "stays inside the boundary"}
                </span>
              </div>
            ))}
          </div>
          <div className="border-t border-line px-4 py-3">
            <Caveat>
              Under a deny egress policy, a connector whose host is not on the allowlist is
              refused before any request leaves the deployment.
            </Caveat>
          </div>
        </Card>
      ) : null}

      {tab === "attacks" ? (
        <div className="grid gap-3 md:grid-cols-2">
          {(attacks.data?.attacks ?? []).map((attack) => (
            <Card key={attack.key} className="p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold">{attack.name}</h3>
                <span className="shrink-0 rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-[10px] text-muted">
                  {attack.vector}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5 text-[10px]">
                <span className="rounded bg-[rgb(var(--unknown-bg))] px-1.5 py-0.5 text-muted">
                  {attack.category}
                </span>
                <span className="rounded bg-[rgb(var(--fail-bg))] px-1.5 py-0.5 text-[rgb(var(--fail))]">
                  {attack.severity}
                </span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted">{attack.description}</p>
              <p className="mt-2 border-l-2 border-line pl-2 text-xs leading-relaxed">
                <span className="text-muted">Mitigation. </span>
                {attack.mitigation}
              </p>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
