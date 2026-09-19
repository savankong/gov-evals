"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { SlideOver, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  Key,
  PageTitle,
  Spinner,
  Table,
  Tabs,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface QueueItem {
  result_id: string;
  run_id: string;
  campaign_id: string;
  project_id: string;
  project_name: string;
  evaluation: string;
  domain: string | null;
  system_version: string | null;
  scenario_title: string | null;
  prompt: string | null;
  response: string | null;
  rubric: string | null;
  expected_behavior: string[];
  prohibited_behavior: string[];
  required_expertise: string[];
  viewer_is_qualified: boolean;
  review_count: number;
  qualified_review_count: number;
  required_reviews: number;
  created_at: string;
}

interface QueueSummary {
  pending_total: number;
  pending_for_me: number;
  pending_outside_my_expertise: number;
  pending_with_no_declared_expertise: number;
  has_profile: boolean;
  my_disciplines: string[];
  profile_verified: boolean;
}

interface Discipline {
  key: string;
  label: string;
}

const VERDICTS = [
  { key: "pass", label: "Pass", hint: "1" },
  { key: "warning", label: "Warning", hint: "2" },
  { key: "fail", label: "Fail", hint: "3" },
] as const;

/** A 0–1 rating rendered as a labelled slider with the value shown. */
function Rating({
  label,
  help,
  value,
  onChange,
}: {
  label: string;
  help: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label className="text-2xs uppercase tracking-wider text-faint">{label}</label>
        <span className="tnum text-sm text-ink">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-1.5 w-full accent-[rgb(var(--accent))]"
        aria-label={label}
      />
      <p className="mt-1 text-xs leading-relaxed text-muted">{help}</p>
    </div>
  );
}

function ReviewPanel({
  item,
  disciplines,
  summary,
  onClose,
  onSubmitted,
}: {
  item: QueueItem | null;
  disciplines: Discipline[];
  summary: QueueSummary | null;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [verdict, setVerdict] = useState<string | null>(null);
  const [confidence, setConfidence] = useState(0.7);
  const [familiarity, setFamiliarity] = useState(0.7);
  const [expertise, setExpertise] = useState("");
  const [comments, setComments] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState(() => Date.now());

  const labelFor = useCallback(
    (key: string) => disciplines.find((d) => d.key === key)?.label ?? key.replace(/_/g, " "),
    [disciplines],
  );

  // Which discipline this reviewer can file under: what they hold that this
  // item actually asks for.
  const filingOptions = useMemo(() => {
    const held = summary?.my_disciplines ?? [];
    const wanted = item?.required_expertise ?? [];
    const overlap = held.filter((d) => wanted.includes(d));
    return (overlap.length ? overlap : held).map((key) => ({
      value: key,
      label: labelFor(key),
    }));
  }, [summary, item, labelFor]);

  useEffect(() => {
    setVerdict(null);
    setComments("");
    setConfidence(0.7);
    setFamiliarity(0.7);
    setError(null);
    setStartedAt(Date.now());
    setExpertise(filingOptions[0]?.value ?? "");
    // Reset per item, not per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.result_id]);

  useEffect(() => {
    if (!item) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "TEXTAREA" || target?.tagName === "INPUT") return;
      const match = VERDICTS.find((v) => v.hint === event.key);
      if (match) {
        event.preventDefault();
        setVerdict(match.key);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item]);

  if (!item) return null;

  const submit = async () => {
    if (!verdict) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/results/${item.result_id}/reviews`, {
        status: verdict,
        comments: comments.trim() || null,
        confidence,
        familiarity,
        expertise: expertise || null,
        time_spent_seconds: Math.max(1, Math.round((Date.now() - startedAt) / 1000)),
      });
      onSubmitted();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit this review.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SlideOver
      open
      onClose={onClose}
      label="Review this result"
      footer={<span>{item.project_name}</span>}
    >
      <div className="space-y-4 p-4">
        <div>
          <h2 className="text-lg text-ink">{item.scenario_title ?? item.evaluation}</h2>
          <p className="mt-0.5 text-xs text-muted">
            {item.evaluation}
            {item.system_version ? ` · ${item.system_version}` : ""}
          </p>
        </div>

        {!item.viewer_is_qualified ? (
          <div className="border border-warn/40 bg-warn/5 px-3 py-2.5">
            <p className="text-sm text-ink">This is outside your declared expertise.</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              It needs{" "}
              {item.required_expertise.map((key) => labelFor(key)).join(", ") ||
                "an expertise nobody has declared"}
              . You can still leave a review and it will be kept in the record — it will be
              labelled as an opinion rather than expert evidence, and will not satisfy an
              evaluation that requires the discipline.
            </p>
          </div>
        ) : null}

        <section>
          <div className="text-2xs uppercase tracking-wider text-faint">Request</div>
          <pre className="mt-1 whitespace-pre-wrap border border-line bg-sunken px-3 py-2 font-mono text-xs leading-relaxed text-ink-soft">
            {item.prompt ?? "— not recorded —"}
          </pre>
        </section>

        <section>
          <div className="text-2xs uppercase tracking-wider text-faint">Response</div>
          <pre className="mt-1 whitespace-pre-wrap border border-line bg-sunken px-3 py-2 font-mono text-xs leading-relaxed text-ink">
            {item.response ?? "— not recorded —"}
          </pre>
        </section>

        {item.rubric ? (
          <section>
            <div className="text-2xs uppercase tracking-wider text-faint">Rubric</div>
            <p className="mt-1 text-xs leading-relaxed text-muted">{item.rubric}</p>
          </section>
        ) : null}

        {item.expected_behavior.length ? (
          <section>
            <div className="text-2xs uppercase tracking-wider text-faint">Expected</div>
            <ul className="mt-1 space-y-0.5">
              {item.expected_behavior.map((line) => (
                <li key={line} className="text-xs leading-relaxed text-muted">
                  — {line}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {item.prohibited_behavior.length ? (
          <section>
            <div className="text-2xs uppercase tracking-wider text-faint">Prohibited</div>
            <ul className="mt-1 space-y-0.5">
              {item.prohibited_behavior.map((line) => (
                <li key={line} className="text-xs leading-relaxed text-muted">
                  — {line}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="border-t border-line pt-4">
          <div className="text-2xs uppercase tracking-wider text-faint">Your judgement</div>
          <div className="mt-1.5 flex gap-1.5">
            {VERDICTS.map((option) => (
              <button
                key={option.key}
                type="button"
                aria-pressed={verdict === option.key}
                onClick={() => setVerdict(option.key)}
                className={`inline-flex h-8 flex-1 items-center justify-center gap-1.5 border px-2.5 text-sm transition-colors duration-150 ease-out ${
                  verdict === option.key
                    ? "border-line-strong bg-sunken text-ink"
                    : "border-line text-muted hover:border-line-strong hover:text-ink"
                }`}
              >
                {option.label}
                <Key>{option.hint}</Key>
              </button>
            ))}
          </div>
        </div>

        {filingOptions.length ? (
          <div>
            <label
              htmlFor="filing-expertise"
              className="text-2xs uppercase tracking-wider text-faint"
            >
              Judging as
            </label>
            <select
              id="filing-expertise"
              value={expertise}
              onChange={(event) => setExpertise(event.target.value)}
              className="mt-1 h-7 w-full appearance-none border border-line bg-panel px-2.5 text-sm text-ink outline-none hover:border-line-strong"
            >
              {filingOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <Rating
          label="Confidence"
          help="How sure you are of this judgement. Recorded so the platform can tell over-reliance from under-reliance later, not to weight your score."
          value={confidence}
          onChange={setConfidence}
        />
        <Rating
          label="Familiarity with this case"
          help="Holding the credential in general is not the same as knowing this particular case. Say so if you do not."
          value={familiarity}
          onChange={setFamiliarity}
        />

        <div>
          <label htmlFor="review-comments" className="text-2xs uppercase tracking-wider text-faint">
            What is wrong, or right, and why
          </label>
          <textarea
            id="review-comments"
            value={comments}
            onChange={(event) => setComments(event.target.value)}
            rows={4}
            placeholder="The reasoning is what makes this evidence rather than a vote."
            className="mt-1 w-full border border-line bg-panel px-2.5 py-2 text-sm leading-relaxed text-ink outline-none placeholder:text-faint focus:border-line-strong"
          />
        </div>

        {error ? <ErrorNote message={error} /> : null}

        <div className="flex items-center gap-2 pb-2">
          <Button variant="primary" onClick={submit} disabled={!verdict || submitting}>
            {submitting ? "Submitting…" : "Submit review"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </SlideOver>
  );
}

export default function ReviewQueuePage() {
  const [scope, setScope] = useState("mine");
  const [active, setActive] = useState<QueueItem | null>(null);

  const summary = useResource<QueueSummary>(() => api.get("/review-queue/summary"));
  const queue = useResource<QueueItem[]>(
    () => api.get(`/review-queue?scope=${scope}`),
    [scope],
  );
  const disciplines = useResource<{ disciplines: Discipline[] }>(() => api.get("/disciplines"));

  const labelFor = useCallback(
    (key: string) =>
      disciplines.data?.disciplines.find((d) => d.key === key)?.label ?? key.replace(/_/g, " "),
    [disciplines.data],
  );

  const reload = () => {
    queue.reload();
    summary.reload();
  };

  const s = summary.data;

  return (
    <div className="space-y-4">
      <PageTitle
        title="Review queue"
        subtitle="Results held open until a qualified person judges them. Nothing here has passed or failed yet."
      />

      {summary.error ? (
        <ErrorNote
          message={summary.error}
          status={summary.status}
          onRetry={summary.reload}
        />
      ) : null}

      {s && !s.has_profile ? (
        <Card>
          <div className="px-4 py-3">
            <p className="text-sm text-ink">You have not declared any expertise.</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
              The platform records who judged an output and on what authority, because a human
              judgement is evidence to the extent the judge was qualified to make it. Until you
              declare a discipline, your reviews are recorded as opinions and do not satisfy an
              evaluation that requires expertise.
            </p>
            <div className="mt-2.5">
              <Link href="/experts">
                <Button variant="primary">Declare your expertise</Button>
              </Link>
            </div>
          </div>
        </Card>
      ) : null}

      {s ? (
        <div className="grid gap-px border border-line bg-line sm:grid-cols-4">
          {[
            ["For me", s.pending_for_me],
            ["Outside my expertise", s.pending_outside_my_expertise],
            ["No expertise declared", s.pending_with_no_declared_expertise],
            ["Pending in total", s.pending_total],
          ].map(([label, value]) => (
            <div key={String(label)} className="bg-panel px-4 py-3">
              <div className="text-2xs uppercase tracking-wider text-faint">{label}</div>
              <div className="tnum mt-0.5 text-2xl text-ink">{String(value)}</div>
            </div>
          ))}
        </div>
      ) : null}

      {s?.has_profile && !s.profile_verified ? (
        <Caveat>
          Your expertise is self-declared and has not been verified by anyone else. Your reviews
          count, and the record says they rest on an unverified claim.
        </Caveat>
      ) : null}

      <Tabs
        tabs={[
          { key: "mine", label: "My expertise", count: s?.pending_for_me },
          { key: "unqualified", label: "Outside it", count: s?.pending_outside_my_expertise },
          { key: "all", label: "Everything", count: s?.pending_total },
        ]}
        active={scope}
        onChange={setScope}
      />

      {queue.error ? (
        <ErrorNote
          message={queue.error}
          status={queue.status}
          onRetry={queue.reload}
        />
      ) : null}

      <Card>
        {queue.loading ? (
          <Spinner label="Loading queue" />
        ) : queue.error ? null : (queue.data ?? []).length === 0 ? (
          <Empty
            title={scope === "mine" ? "Nothing waiting on you" : "Nothing in this queue"}
            detail={
              scope === "mine"
                ? "No result is currently held open for a discipline you hold. An empty queue is not the same as a system that passed — check the campaign for what is still unevaluated."
                : undefined
            }
          />
        ) : (
          <Table minWidth={900}>
            <thead>
              <tr>
                <Th>Case</Th>
                <Th>Evaluation</Th>
                <Th>System</Th>
                <Th>Needs</Th>
                <Th align="right">Reviews</Th>
                <Th>Waiting since</Th>
              </tr>
            </thead>
            <tbody>
              {(queue.data ?? []).map((item, index) => (
                <Tr key={item.result_id} index={index} onClick={() => setActive(item)}>
                  <Td>
                    <span className="text-ink">
                      {item.scenario_title ?? "Untitled case"}
                    </span>
                    <div className="mt-0.5 text-xs text-faint">{item.project_name}</div>
                  </Td>
                  <Td className="text-muted">
                    {item.evaluation}
                    {item.domain ? (
                      <div className="mt-0.5">
                        <Tag>{item.domain.replace(/_/g, " ")}</Tag>
                      </div>
                    ) : null}
                  </Td>
                  <Td className="text-muted">{item.system_version ?? "—"}</Td>
                  <Td>
                    {item.required_expertise.length ? (
                      <div className="flex flex-wrap gap-1">
                        {item.required_expertise.map((key) => (
                          <Tag key={key} tone={item.viewer_is_qualified ? "strong" : "quiet"}>
                            {labelFor(key)}
                          </Tag>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-faint">Not declared</span>
                    )}
                  </Td>
                  <Td align="right" className="tnum">
                    <span className={item.qualified_review_count ? "text-ink" : "text-faint"}>
                      {item.qualified_review_count}
                    </span>
                    <span className="text-faint">/{item.required_reviews}</span>
                    {item.review_count > item.qualified_review_count ? (
                      <div
                        className="mt-0.5 text-2xs text-faint"
                        title="Submitted by reviewers without the required expertise, so they do not count towards the requirement."
                      >
                        +{item.review_count - item.qualified_review_count} uncounted
                      </div>
                    ) : null}
                  </Td>
                  <Td className="text-muted">{formatDate(item.created_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Caveat>
        A result stays <span className="font-mono">pending_human</span> until the number of
        counted reviews the evaluation asks for has been submitted. It never resolves to a pass
        by waiting, and a review from outside the required discipline does not move it.
      </Caveat>

      <ReviewPanel
        item={active}
        disciplines={disciplines.data?.disciplines ?? []}
        summary={s ?? null}
        onClose={() => setActive(null)}
        onSubmitted={reload}
      />
    </div>
  );
}
