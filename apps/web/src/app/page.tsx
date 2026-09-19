"use client";

import Link from "next/link";

import { SeverityTag } from "@/components/status";
import { useAuth, useResource } from "@/components/shell";
import {
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Figure,
  Table,
  TableSkeleton,
  Td,
  Th,
  Tr,
  formatPercent,
  greeting,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Overview, Severity } from "@/lib/types";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export default function PortfolioPage() {
  const { session } = useAuth();
  const { data, error, loading } = useResource<Overview>(() => api.get<Overview>("/dashboard"));

  const firstName = (session?.fullName ?? session?.email ?? "").split(/[\s@]/)[0];

  return (
    <div className="space-y-5">
      {/* The one line of serif in the product. It makes the portfolio read as
          a place you arrive, not a report you were handed. */}
      <div className="animate-rise py-3 text-center">
        <h1 className="font-serif text-4xl text-ink">
          {greeting()}
          {firstName ? (
            <>
              , <span className="text-faint">{firstName}</span>
            </>
          ) : null}
        </h1>
        <p className="mt-1.5 text-sm text-muted">
          {loading
            ? "Loading the portfolio…"
            : data
              ? summarise(data)
              : "Nothing to report."}
        </p>
      </div>

      {error ? <ErrorNote message={error} /> : null}

      {loading ? (
        <Card>
          <TableSkeleton rows={5} cols={5} />
        </Card>
      ) : data ? (
        <>
          <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
            {[
              { label: "Projects", value: data.counts.projects },
              { label: "Systems", value: data.counts.systems },
              { label: "Campaigns", value: data.counts.campaigns },
              { label: "Executions", value: data.counts.executions },
              {
                label: "Failures",
                value: data.counts.failures,
                tone: data.counts.failures > 0 ? ("fail" as const) : undefined,
              },
              {
                label: "Awaiting review",
                value: data.counts.awaiting_human_review,
                tone:
                  data.counts.awaiting_human_review > 0 ? ("warn" as const) : undefined,
              },
            ].map((stat, index) => (
              <div
                key={stat.label}
                className="stagger bg-panel px-4 py-3.5"
                style={{ ["--stagger-delay" as string]: `${index * 30}ms` }}
              >
                <Figure
                  label={stat.label}
                  countTo={stat.value ?? 0}
                  tone={stat.tone}
                  size="sm"
                />
              </div>
            ))}
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHead title="Projects" meta={`${data.projects.length} under evaluation`} />
              {data.projects.length === 0 ? (
                <Empty
                  title="No projects yet"
                  detail="A project pairs an AI capability with the mission it is intended for."
                />
              ) : (
                <Table minWidth={560}>
                  <thead>
                    <tr>
                      <Th>Project</Th>
                      <Th>Marking</Th>
                      <Th>Impact</Th>
                      <Th align="right">Open</Th>
                      <Th align="right">Critical</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.projects.map((project, index) => (
                      <Tr key={project.id} index={index}>
                        <Td>
                          <Link
                            href={`/projects/${project.id}`}
                            className="link-underline text-ink"
                          >
                            {project.name}
                          </Link>
                        </Td>
                        <Td className="text-xs text-muted">{project.classification}</Td>
                        <Td className="text-xs text-muted">{project.impact_level ?? "—"}</Td>
                        <Td align="right" className="tnum">
                          {project.open_findings}
                        </Td>
                        <Td align="right" className="tnum">
                          {project.critical_findings > 0 ? (
                            <span className="text-fail">{project.critical_findings}</span>
                          ) : (
                            <span className="text-faint">0</span>
                          )}
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Card>

            <div className="space-y-4">
              <Card>
                <CardHead title="Evidence coverage" />
                <div className="px-4 pb-4">
                  <Figure
                    label="Complete chain"
                    value={
                      <span>
                        {data.evidence_coverage.projects_with_complete_chain}
                        <span className="text-xl text-faint">
                          {" / "}
                          {data.evidence_coverage.projects}
                        </span>
                      </span>
                    }
                    note={
                      data.evidence_coverage.ratio !== null
                        ? formatPercent(data.evidence_coverage.ratio)
                        : undefined
                    }
                  />
                  <div className="mt-3">
                    <Caveat>{data.evidence_coverage.definition}</Caveat>
                  </div>
                </div>
              </Card>

              <Card>
                <CardHead title="Open findings" meta="Unresolved, portfolio-wide" />
                <div>
                  {SEVERITIES.map((severity, index) => {
                    const count = data.findings[severity] ?? 0;
                    const total = SEVERITIES.reduce(
                      (sum, s) => sum + (data.findings[s] ?? 0),
                      0,
                    );
                    const width = total > 0 ? (count / total) * 100 : 0;
                    return (
                      <div
                        key={severity}
                        className="stagger flex items-center gap-3 border-t border-line px-4 py-2"
                        style={{ ["--stagger-delay" as string]: `${index * 30}ms` }}
                      >
                        <span className="w-16">
                          <SeverityTag severity={severity} />
                        </span>
                        <span className="h-px flex-1 bg-line">
                          <span
                            className="block h-px bg-ink transition-[width] duration-500 ease-out"
                            style={{ width: `${width}%` }}
                          />
                        </span>
                        <span className="tnum w-6 text-right text-sm">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </Card>

              <Card>
                <CardHead title="Risks" />
                <div className="grid grid-cols-3 divide-x divide-line border-t border-line">
                  {[
                    { label: "Total", value: data.risks.total },
                    { label: "Open", value: data.risks.open },
                    { label: "Accepted", value: data.risks.accepted },
                  ].map((item) => (
                    <div key={item.label} className="px-4 py-3">
                      <Figure label={item.label} countTo={item.value} size="sm" />
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function summarise(data: Overview): string {
  const critical = data.findings.critical ?? 0;
  const awaiting = data.counts.awaiting_human_review ?? 0;
  if (critical > 0) {
    return `${critical} unresolved critical finding${critical === 1 ? "" : "s"} across ${data.counts.projects} project${data.counts.projects === 1 ? "" : "s"}.`;
  }
  if (awaiting > 0) {
    return `${awaiting} result${awaiting === 1 ? "" : "s"} awaiting human review.`;
  }
  return "Nothing needs your attention right now.";
}
