"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";

import { useResource } from "@/components/shell";
import {
  Button,
  Caveat,
  Card,
  Empty,
  ErrorNote,
  PageTitle,
  Table,
  TableSkeleton,
  Tabs,
  Tag,
  Td,
  Th,
  Tr,
} from "@/components/ui";
import { api } from "@/lib/api";

interface ModelRecord {
  passed: number;
  failed: number;
  warned: number;
  unresolved: number;
  confident_wrong: number;
  unsure_wrong: number;
  confidence_unknown_wrong: number;
  outcome: "failed" | "passed" | "not_evaluated";
}

interface CaptureTask {
  scenario_id: string;
  key: string;
  title: string;
  task: string | null;
  knowledge_area: string | null;
  required_expertise: string[];
  viewer_is_qualified: boolean;
  model: ModelRecord;
  traces: number;
  qualified_traces: number;
  traced_by_me: boolean;
}

interface CaptureTasks {
  confident_at: number;
  has_profile: boolean;
  tasks: CaptureTask[];
  total: number;
}

function ModelCell({ model }: { model: ModelRecord }) {
  if (model.outcome === "not_evaluated") {
    return (
      <span className="whitespace-nowrap text-xs text-faint" title="The model has not been judged on this problem.">
        Not evaluated
      </span>
    );
  }
  if (model.outcome === "passed") {
    return <span className="whitespace-nowrap text-xs text-muted">Right {model.passed + model.warned}×</span>;
  }
  return (
    <div>
      <span className="tnum whitespace-nowrap text-sm text-fail">Wrong {model.failed}×</span>
      <div className="mt-0.5 text-2xs text-faint">
        {model.confident_wrong ? `${model.confident_wrong} confidently` : null}
        {model.confident_wrong && (model.unsure_wrong || model.confidence_unknown_wrong) ? " · " : null}
        {model.unsure_wrong ? `${model.unsure_wrong} unsure` : null}
        {model.unsure_wrong && model.confidence_unknown_wrong ? " · " : null}
        {model.confidence_unknown_wrong ? `${model.confidence_unknown_wrong} unknown` : null}
      </div>
    </div>
  );
}

export default function CapturePage({
  searchParams,
}: {
  searchParams: Promise<{ area?: string }>;
}) {
  const { area } = use(searchParams);
  const router = useRouter();
  const [scope, setScope] = useState("mine");

  const query = new URLSearchParams({ scope });
  if (area !== undefined) query.set("knowledge_area", area);
  const tasks = useResource(
    () => api.get<CaptureTasks>(`/capture/tasks?${query.toString()}`),
    [scope, area],
  );
  const data = tasks.data;
  const disciplines = useResource(
    () => api.get<{ disciplines: Array<{ key: string; label: string }> }>("/disciplines"),
    [],
  );
  const labelFor = (key: string) =>
    disciplines.data?.disciplines.find((d) => d.key === key)?.label ?? key.replace(/_/g, " ");

  return (
    <div className="space-y-4">
      <PageTitle
        title="Capture"
        subtitle="Problems to work, step by step, in your own words. The ones the model got wrong and nobody qualified has solved come first — that is the data a lab cannot get anywhere else."
      />

      {data && !data.has_profile ? (
        <Card>
          <div className="px-4 py-3">
            <p className="text-sm text-ink">You have not declared any expertise.</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
              A reasoning trace is delivered as expert data only when its author is qualified for
              the problem. Without a profile your traces are recorded and kept, and they are not
              delivered.
            </p>
            <div className="mt-2.5">
              <Link href="/experts">
                <Button variant="primary">Declare your expertise</Button>
              </Link>
            </div>
          </div>
        </Card>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Tabs
          tabs={[
            { key: "mine", label: "I can qualify on" },
            { key: "all", label: "Everything" },
          ]}
          active={scope}
          onChange={setScope}
        />
        {area !== undefined ? (
          <Tag tone="strong" onClear={() => router.push("/capture")} title="Clear the area filter">
            {area || "Not declared"}
          </Tag>
        ) : null}
      </div>

      {tasks.error ? (
        <ErrorNote message={tasks.error} status={tasks.status} onRetry={tasks.reload} />
      ) : null}

      <Card>
        {tasks.loading && !data ? (
          <TableSkeleton rows={6} cols={5} />
        ) : tasks.error ? null : (data?.tasks ?? []).length === 0 ? (
          <Empty
            title={scope === "mine" ? "Nothing here you can qualify on" : "No problems to work"}
            detail={
              scope === "mine"
                ? "No approved problem asks for a discipline on your profile. Everything shows the rest, and a trace there is still recorded, as an opinion."
                : "Problems come from the Library and from project scenarios. Approve some, run the model against them, and the ones it gets wrong land here first."
            }
          />
        ) : (
          <Table minWidth={980}>
            <thead>
              <tr>
                <Th>Problem</Th>
                <Th>Knowledge area</Th>
                <Th>Model</Th>
                <Th>Needs</Th>
                <Th align="right">Expert traces</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {(data?.tasks ?? []).map((task, index) => (
                <Tr
                  key={task.scenario_id}
                  index={index}
                  onClick={() => router.push(`/capture/${task.scenario_id}`)}
                >
                  <Td>
                    <span className="text-ink">{task.title}</span>
                    {task.task ? <div className="mt-0.5 text-xs text-muted">{task.task}</div> : null}
                  </Td>
                  <Td className="text-muted">
                    {task.knowledge_area ?? <span className="text-xs text-faint">Not declared</span>}
                  </Td>
                  <Td>
                    <ModelCell model={task.model} />
                  </Td>
                  <Td>
                    {task.required_expertise.length ? (
                      <div className="flex flex-wrap gap-1">
                        {task.required_expertise.map((key) => (
                          <Tag key={key} tone={task.viewer_is_qualified ? "strong" : "quiet"}>
                            {labelFor(key)}
                          </Tag>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-faint">Not declared</span>
                    )}
                  </Td>
                  <Td align="right" className="tnum">
                    <span className={task.qualified_traces ? "text-ink" : "text-faint"}>
                      {task.qualified_traces}
                    </span>
                    {task.traces > task.qualified_traces ? (
                      <div className="mt-0.5 text-2xs text-faint">
                        +{task.traces - task.qualified_traces} uncounted
                      </div>
                    ) : null}
                    {task.traced_by_me ? (
                      <div className="mt-0.5 text-2xs text-faint">incl. yours</div>
                    ) : null}
                  </Td>
                  <Td align="right">
                    <span className="whitespace-nowrap text-xs text-muted">Solve →</span>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {data && data.total > data.tasks.length ? (
        <p className="text-xs text-muted">
          Showing the first {data.tasks.length} of {data.total}.
        </p>
      ) : null}

      <Caveat>
        Order is fixed, not scored: problems the model failed with no qualified trace, then
        problems nobody has run the model on, then problems it got right. Within each, the most
        confidently wrong first.
      </Caveat>
    </div>
  );
}
