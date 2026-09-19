"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth, useResource } from "@/components/shell";
import {
  Button,
  Card,
  CardHead,
  Caveat,
  Empty,
  ErrorNote,
  PageTitle,
  Spinner,
  Table,
  Tag,
  Td,
  Th,
  Tr,
  formatDate,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";

interface ExpertProfile {
  id: string;
  user_id: string | null;
  display_name: string;
  disciplines: string[];
  title: string | null;
  organization: string | null;
  credentials: string | null;
  years_experience: number | null;
  notes: string | null;
  verified: boolean;
  verified_by: string | null;
  verified_at: string | null;
  active: boolean;
  created_at: string;
}

interface Discipline {
  key: string;
  label: string;
}

interface CoverageRow {
  discipline: string;
  label: string;
  datasets: Array<{ id: string; name: string }>;
  reviewers: Array<{ id: string; name: string; verified: boolean }>;
  verified_reviewers: number;
  covered: boolean;
}

interface Coverage {
  coverage: CoverageRow[];
  gaps: string[];
  datasets_with_no_declared_expertise: Array<{ id: string; name: string }>;
}

function ProfileForm({
  profile,
  disciplines,
  defaultName,
  onSaved,
}: {
  profile: ExpertProfile | null;
  disciplines: Discipline[];
  defaultName: string;
  onSaved: () => void;
}) {
  const [displayName, setDisplayName] = useState(profile?.display_name ?? defaultName);
  const [selected, setSelected] = useState<string[]>(profile?.disciplines ?? []);
  const [title, setTitle] = useState(profile?.title ?? "");
  const [organization, setOrganization] = useState(profile?.organization ?? "");
  const [credentials, setCredentials] = useState(profile?.credentials ?? "");
  const [years, setYears] = useState(profile?.years_experience?.toString() ?? "");
  const [custom, setCustom] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    setDisplayName(profile.display_name);
    setSelected(profile.disciplines);
    setTitle(profile.title ?? "");
    setOrganization(profile.organization ?? "");
    setCredentials(profile.credentials ?? "");
    setYears(profile.years_experience?.toString() ?? "");
  }, [profile]);

  const options = useMemo(() => {
    const keys = new Set(disciplines.map((d) => d.key));
    return [
      ...disciplines,
      ...selected.filter((s) => !keys.has(s)).map((s) => ({ key: s, label: s })),
    ];
  }, [disciplines, selected]);

  // Re-declaring the claim drops the verification that was made about it.
  const willLoseVerification =
    !!profile?.verified &&
    selected.slice().sort().join("|") !== profile.disciplines.slice().sort().join("|");

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.put("/expert-profiles/me", {
        display_name: displayName.trim() || defaultName,
        disciplines: selected,
        title: title.trim() || null,
        organization: organization.trim() || null,
        credentials: credentials.trim() || null,
        years_experience: years.trim() ? Number(years) : null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your profile.");
    } finally {
      setSaving(false);
    }
  };

  const field =
    "h-7 w-full border border-line bg-panel px-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-line-strong";

  return (
    <Card>
      <CardHead
        title="Your expertise"
        subtitle="What you are qualified to judge. Recorded against every review you file, because a judgement is evidence to the extent the judge was qualified to make it."
        action={
          <Button variant="primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : profile ? "Save changes" : "Create profile"}
          </Button>
        }
      />
      <div className="space-y-3 border-t border-line px-4 py-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="display-name" className="text-2xs uppercase tracking-wider text-faint">
              Name
            </label>
            <input
              id="display-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              className={`mt-1 ${field}`}
            />
          </div>
          <div>
            <label htmlFor="job-title" className="text-2xs uppercase tracking-wider text-faint">
              Role
            </label>
            <input
              id="job-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Contracting officer"
              className={`mt-1 ${field}`}
            />
          </div>
          <div>
            <label htmlFor="org" className="text-2xs uppercase tracking-wider text-faint">
              Organisation
            </label>
            <input
              id="org"
              value={organization}
              onChange={(event) => setOrganization(event.target.value)}
              className={`mt-1 ${field}`}
            />
          </div>
          <div>
            <label htmlFor="years" className="text-2xs uppercase tracking-wider text-faint">
              Years in the field
            </label>
            <input
              id="years"
              type="number"
              min={0}
              max={80}
              value={years}
              onChange={(event) => setYears(event.target.value)}
              className={`mt-1 ${field}`}
            />
          </div>
        </div>

        <div>
          <div className="text-2xs uppercase tracking-wider text-faint">Disciplines</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {options.map((option) => {
              const on = selected.includes(option.key);
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setSelected((current) =>
                      current.includes(option.key)
                        ? current.filter((k) => k !== option.key)
                        : [...current, option.key],
                    )
                  }
                  className={`h-7 shrink-0 whitespace-nowrap border px-2.5 text-sm transition-colors duration-150 ease-out ${
                    on
                      ? "border-line-strong bg-sunken text-ink"
                      : "border-line text-muted hover:border-line-strong hover:text-ink"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <input
              value={custom}
              onChange={(event) => setCustom(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                const slug = custom.trim().toLowerCase().replace(/\s+/g, "_");
                if (slug && !selected.includes(slug)) setSelected([...selected, slug]);
                setCustom("");
              }}
              placeholder="Add a discipline not listed…"
              aria-label="Add a discipline not listed"
              className="h-7 w-56 border border-line bg-panel px-2.5 text-sm text-ink outline-none placeholder:text-faint focus:border-line-strong"
            />
          </div>
        </div>

        <div>
          <label htmlFor="creds" className="text-2xs uppercase tracking-wider text-faint">
            Credentials
          </label>
          <textarea
            id="creds"
            value={credentials}
            onChange={(event) => setCredentials(event.target.value)}
            rows={2}
            placeholder="Certifications, clearances, warrants — whatever supports the claim."
            className="mt-1 w-full border border-line bg-panel px-2.5 py-2 text-sm leading-relaxed text-ink outline-none placeholder:text-faint focus:border-line-strong"
          />
        </div>

        {willLoseVerification ? (
          <Caveat>
            Changing your disciplines drops the verification on this profile. A verification is
            a statement about a specific claim; re-declaring the claim invalidates it, and
            someone else will need to vouch for the new one.
          </Caveat>
        ) : null}

        {error ? <ErrorNote message={error} /> : null}
      </div>
    </Card>
  );
}

export default function ExpertsPage() {
  const { session, can } = useAuth();
  const mine = useResource<ExpertProfile | null>(() => api.get("/expert-profiles/me"));
  const everyone = useResource<ExpertProfile[]>(() => api.get("/expert-profiles"));
  const disciplines = useResource<{ disciplines: Discipline[] }>(() => api.get("/disciplines"));
  const coverage = useResource<Coverage>(() => api.get("/expertise-coverage"));
  const [error, setError] = useState<string | null>(null);

  const labelFor = useCallback(
    (key: string) =>
      disciplines.data?.disciplines.find((d) => d.key === key)?.label ?? key.replace(/_/g, " "),
    [disciplines.data],
  );

  const verify = async (profile: ExpertProfile) => {
    setError(null);
    try {
      await api.post(`/expert-profiles/${profile.id}/verify`);
      everyone.reload();
      mine.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not verify this profile.");
    }
  };

  const canVerify = can("org:administer");
  const gaps = coverage.data?.coverage.filter((row) => !row.covered) ?? [];

  return (
    <div className="space-y-4">
      <PageTitle
        title="Experts"
        subtitle="Who can judge what, and where the programme has asked for a discipline nobody here holds."
      />

      {error ? <ErrorNote message={error} /> : null}

      {mine.loading ? (
        <Spinner label="Loading your profile" />
      ) : (
        <ProfileForm
          profile={mine.data ?? null}
          disciplines={disciplines.data?.disciplines ?? []}
          defaultName={session?.fullName ?? session?.email ?? ""}
          onSaved={() => {
            mine.reload();
            everyone.reload();
            coverage.reload();
          }}
        />
      )}

      {gaps.length ? (
        <Card>
          <CardHead
            title="Expertise gaps"
            subtitle="Datasets that ask for a discipline no active reviewer holds. Their results will sit in the queue until someone qualified exists."
          />
          <Table minWidth={620}>
            <thead>
              <tr>
                <Th>Discipline</Th>
                <Th>Asked for by</Th>
                <Th align="right">Reviewers</Th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((row, index) => (
                <Tr key={row.discipline} index={index}>
                  <Td>
                    <Tag tone="warn">{row.label}</Tag>
                  </Td>
                  <Td className="text-muted">
                    {row.datasets.map((dataset, i) => (
                      <span key={dataset.id}>
                        {i > 0 ? ", " : ""}
                        <Link
                          href={`/datasets/${dataset.id}`}
                          className="underline underline-offset-2"
                        >
                          {dataset.name}
                        </Link>
                      </span>
                    ))}
                  </Td>
                  <Td align="right" className="tnum text-fail">
                    0
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
      ) : null}

      <Card>
        <CardHead
          title="Reviewers"
          subtitle="Verification is somebody else vouching for a claim. Nobody verifies their own."
        />
        {everyone.loading ? (
          <Spinner label="Loading reviewers" />
        ) : everyone.error ? (
          <div className="p-3">
            <ErrorNote
              message={everyone.error}
              status={everyone.status}
              onRetry={everyone.reload}
            />
          </div>
        ) : (everyone.data ?? []).length === 0 ? (
          <Empty
            title="No expert profiles yet"
            detail="Until someone declares a discipline, every human review on this platform is recorded as an opinion rather than expert evidence."
          />
        ) : (
          <Table minWidth={820}>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Disciplines</Th>
                <Th>Role</Th>
                <Th align="right">Years</Th>
                <Th>Standing</Th>
                {canVerify ? <Th /> : null}
              </tr>
            </thead>
            <tbody>
              {(everyone.data ?? []).map((profile, index) => (
                <Tr key={profile.id} index={index}>
                  <Td>
                    <span className="text-ink">{profile.display_name}</span>
                    {profile.organization ? (
                      <div className="mt-0.5 text-xs text-faint">{profile.organization}</div>
                    ) : null}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {profile.disciplines.map((key) => (
                        <Tag key={key}>{labelFor(key)}</Tag>
                      ))}
                      {profile.disciplines.length === 0 ? (
                        <span className="text-xs text-faint">None declared</span>
                      ) : null}
                    </div>
                  </Td>
                  <Td className="text-muted">{profile.title ?? "—"}</Td>
                  <Td align="right" className="tnum text-muted">
                    {profile.years_experience ?? "—"}
                  </Td>
                  <Td>
                    {profile.verified ? (
                      <span
                        title={`Verified by ${profile.verified_by ?? "an administrator"} on ${formatDate(profile.verified_at)}`}
                      >
                        <Tag tone="strong">Verified</Tag>
                      </span>
                    ) : (
                      <Tag>Self-declared</Tag>
                    )}
                  </Td>
                  {canVerify ? (
                    <Td align="right">
                      {!profile.verified && profile.user_id !== session?.email ? (
                        <Button onClick={() => verify(profile)}>Verify</Button>
                      ) : null}
                    </Td>
                  ) : null}
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {coverage.data?.datasets_with_no_declared_expertise.length ? (
        <Caveat>
          {coverage.data.datasets_with_no_declared_expertise.length} dataset
          {coverage.data.datasets_with_no_declared_expertise.length === 1 ? "" : "s"} declare no
          required expertise. Reviews of their results record that no requirement was checked —
          which is a different statement from saying the reviewer was qualified.
        </Caveat>
      ) : null}
    </div>
  );
}
