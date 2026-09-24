"use client";

import { useState } from "react";

import { EvaluatorKind, SeverityTag } from "@/components/status";
import { useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  ErrorNote,
  Hash,
  PageTitle,
  Spinner,
  Table,
  Tabs,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui";
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
      <PageTitle
        title="Library"
        subtitle="What this deployment can evaluate with, and what it can evaluate against."
      />

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
        <Card>
          <CardHead
            title="Installed packs"
            meta="Content is versioned and hashed, so a run can name exactly what it tested against"
          />
          <Table minWidth={760}>
            <thead>
              <tr>
                <Th>Pack</Th>
                <Th className="w-[8.25rem]">Kind</Th>
                <Th className="w-[6rem]">Version</Th>
                <Th className="w-[11.25rem]">Publisher</Th>
                <Th className="w-[9rem]">Content hash</Th>
              </tr>
            </thead>
            <tbody>
              {(packs.data?.packs ?? []).map((pack, index) => (
                <Tr key={pack.key} index={index}>
                  <Td>
                    <div className="text-sm text-ink">{pack.name}</div>
                    <div className="font-mono text-2xs text-faint">{pack.key}</div>
                    {pack.description ? (
                      <div className="mt-0.5 max-w-xl text-xs leading-relaxed text-muted">
                        {pack.description}
                      </div>
                    ) : null}
                  </Td>
                  <Td>
                    <Tag>{pack.kind}</Tag>
                  </Td>
                  <Td>
                    <span className="tnum text-xs text-muted">v{pack.version}</span>
                  </Td>
                  <Td>
                    <span className="text-xs text-muted">{pack.publisher ?? "—"}</span>
                  </Td>
                  <Td>
                    <Hash value={pack.content_hash} />
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}

      {tab === "evaluators" ? (
        <Card>
          <CardHead
            title="Evaluators"
            meta="Four kinds, so no single evaluator is treated as definitive"
          />
          <Table minWidth={720}>
            <thead>
              <tr>
                <Th className="w-[15rem]">Key</Th>
                <Th className="w-[9.75rem]">Kind</Th>
                <Th>What it judges</Th>
              </tr>
            </thead>
            <tbody>
              {(evaluators.data?.evaluators ?? []).map((evaluator, index) => (
                <Tr key={evaluator.key} index={index}>
                  <Td>
                    <code className="font-mono text-xs text-ink">{evaluator.key}</code>
                  </Td>
                  <Td>
                    <EvaluatorKind kind={evaluator.kind} />
                  </Td>
                  <Td>
                    <div className="text-sm text-ink">{evaluator.label}</div>
                    {evaluator.description ? (
                      <div className="mt-0.5 text-xs leading-relaxed text-muted">
                        {evaluator.description}
                      </div>
                    ) : null}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}

      {tab === "connectors" ? (
        <Card>
          <CardHead title="Connectors" meta="Adapters speak wire protocols, not vendors" />
          <Table minWidth={680}>
            <thead>
              <tr>
                <Th className="w-[13.5rem]">Key</Th>
                <Th>Adapter</Th>
                <Th className="w-[17.25rem]">Network</Th>
              </tr>
            </thead>
            <tbody>
              {(connectors.data?.connectors ?? []).map((connector, index) => (
                <Tr key={connector.key} index={index}>
                  <Td>
                    <code className="font-mono text-xs text-ink">{connector.key}</code>
                  </Td>
                  <Td>
                    <span className="text-sm text-ink">{connector.label}</span>
                  </Td>
                  <Td>
                    {/* Egress is the property a disconnected deployment cares
                        about most, so it is a column rather than a footnote. */}
                    {connector.requires_egress ? (
                      <Tag tone="warn">needs egress</Tag>
                    ) : (
                      <Tag>stays inside the boundary</Tag>
                    )}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <div className="border-t border-line px-4 py-3">
            <Caveat>
              Under a deny egress policy, a connector whose host is not on the allowlist is
              refused before any request leaves the deployment.
            </Caveat>
          </div>
        </Card>
      ) : null}

      {tab === "attacks" ? (
        <Card>
          <CardHead
            title="Attack library"
            meta="Each technique carries the mitigation it is meant to test"
          />
          <Table minWidth={860}>
            <thead>
              <tr>
                <Th className="w-[18rem]">Technique</Th>
                <Th className="w-[6.75rem]">Severity</Th>
                <Th>Description</Th>
                <Th className="w-[21rem]">Mitigation</Th>
              </tr>
            </thead>
            <tbody>
              {(attacks.data?.attacks ?? []).map((attack, index) => (
                <Tr key={attack.key} index={index}>
                  <Td>
                    <div className="text-sm text-ink">{attack.name}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Tag>{attack.category}</Tag>
                      <Tag>{attack.vector}</Tag>
                    </div>
                  </Td>
                  <Td>
                    <SeverityTag severity={attack.severity} />
                  </Td>
                  <Td>
                    <span className="text-xs leading-relaxed text-muted">
                      {attack.description}
                    </span>
                  </Td>
                  <Td>
                    <span className="text-xs leading-relaxed text-ink-soft">
                      {attack.mitigation}
                    </span>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}
    </div>
  );
}
