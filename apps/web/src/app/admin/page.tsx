"use client";

import { useCallback, useState } from "react";

import { Choice, Field, FormActions } from "@/components/forms";
import { SlideOver, useAuth, useResource } from "@/components/shell";
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

interface Membership {
  id: string;
  organization_id: string;
  project_id: string | null;
  role: string;
}
interface Account {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  identity_provider: string;
  has_local_password: boolean;
  memberships: Membership[];
  created_at: string;
}
interface Organization {
  id: string;
  name: string;
}
interface Vocabularies {
  roles: string[];
}

const roleLabel = (role: string) => role.replace(/_/g, " ");

function NewAccount({
  organizations,
  roles,
  onClose,
  onCreated,
}: {
  organizations: Organization[];
  roles: string[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState(organizations[0]?.id ?? "");
  const [role, setRole] = useState("read_only");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.post("/users", {
        email: email.trim(),
        full_name: fullName.trim() || null,
        password,
        organization_id: organizationId || null,
        role: organizationId ? role : null,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create this account.");
      setSaving(false);
    }
  };

  return (
    <SlideOver open onClose={onClose} label="New account">
      <div className="space-y-3.5 p-4">
        <div>
          <h2 className="text-lg text-ink">New account</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            A local account with a password. Federated sign-in is configured at the deployment,
            not here.
          </p>
        </div>

        <Field
          id="new-email"
          label="Email"
          value={email}
          onChange={setEmail}
          type="email"
          required
          placeholder="name@organisation.mil"
          help="Must be a full address. The login endpoint requires one so air-gapped installs can use internal domains."
        />
        <Field id="new-name" label="Full name" value={fullName} onChange={setFullName} />
        <Field
          id="new-password"
          label="Initial password"
          value={password}
          onChange={setPassword}
          type="password"
          required
          help="At least 12 characters. The shipped default is refused — it is published in the repository, so it is not a credential."
        />

        <Choice
          id="new-org"
          label="Organisation"
          value={organizationId}
          onChange={setOrganizationId}
          options={organizations.map((o) => ({ value: o.id, label: o.name }))}
        />
        <Choice
          id="new-role"
          label="Role"
          value={role}
          onChange={setRole}
          options={roles.map((r) => ({ value: r, label: roleLabel(r) }))}
          help="Granted now rather than later: an account that can do nothing is one somebody grants too much to in a hurry."
        />

        <FormActions
          onSubmit={create}
          onCancel={onClose}
          submitting={saving}
          disabled={!email.trim() || !password}
          error={error}
          submitLabel="Create account"
          busyLabel="Creating…"
        />
      </div>
    </SlideOver>
  );
}

function ResetPassword({
  account,
  onClose,
  onDone,
}: {
  account: Account;
  onClose: () => void;
  onDone: () => void;
}) {
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const reset = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = await api.post<{ note?: string }>(`/users/${account.id}/password`, {
        new_password: password,
      });
      setNote(body.note ?? "Done.");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset this password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SlideOver open onClose={onClose} label="Reset password">
      <div className="space-y-3.5 p-4">
        <div>
          <h2 className="text-lg text-ink">Reset password</h2>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            For <span className="text-ink">{account.email}</span>. This is recorded as an
            administrator acting on someone else, which is a different entry from someone
            changing their own.
          </p>
        </div>

        {note ? (
          <Caveat>{note}</Caveat>
        ) : (
          <>
            <Field
              id="reset-password"
              label="New password"
              value={password}
              onChange={setPassword}
              type="password"
              required
            />
            <FormActions
              onSubmit={reset}
              onCancel={onClose}
              submitting={saving}
              disabled={!password}
              error={error}
              submitLabel="Reset password"
              busyLabel="Resetting…"
            />
          </>
        )}
      </div>
    </SlideOver>
  );
}

function MyPassword() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const change = async () => {
    setSaving(true);
    setError(null);
    try {
      const body = await api.post<{ note?: string }>("/users/me/password", {
        current_password: current,
        new_password: next,
      });
      setNote(body.note ?? "Changed.");
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change your password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHead
        title="Your password"
        subtitle="Changing your own requires the current one, administrator or not."
      />
      <div className="space-y-3 border-t border-line px-4 py-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            id="cur-pw"
            label="Current password"
            value={current}
            onChange={setCurrent}
            type="password"
          />
          <Field
            id="new-pw"
            label="New password"
            value={next}
            onChange={setNext}
            type="password"
          />
        </div>
        {note ? <Caveat>{note}</Caveat> : null}
        <FormActions
          onSubmit={change}
          submitting={saving}
          disabled={!current || !next}
          error={error}
          submitLabel="Change password"
          busyLabel="Changing…"
        />
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const { can, session } = useAuth();
  const users = useResource<Account[]>(() => api.get("/users"));
  const orgs = useResource<Organization[]>(() => api.get("/organizations"));
  const vocab = useResource<Vocabularies>(() => api.get("/vocabularies"));

  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<Account | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = can("org:administer");

  const toggleActive = useCallback(
    async (account: Account) => {
      setError(null);
      try {
        await api.patch(`/users/${account.id}`, { is_active: !account.is_active });
        users.reload();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not update this account.");
      }
    },
    [users],
  );

  return (
    <div className="space-y-4">
      <PageTitle
        title="Administration"
        subtitle="Local accounts and access. Accounts are deactivated, never deleted — the audit chain names the actor on every recorded action."
        action={
          isAdmin ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              New account
            </Button>
          ) : null
        }
      />

      <MyPassword />

      {!isAdmin ? (
        <Caveat>
          You can change your own password above. Managing other accounts needs the
          <span className="font-mono"> org:administer </span> permission.
        </Caveat>
      ) : (
        <>
          {error ? <ErrorNote message={error} /> : null}
          {users.error ? (
            <ErrorNote
              message={users.error}
              status={users.status}
              onRetry={users.reload}
            />
          ) : null}

          <Card>
            <CardHead
              title="Accounts"
              subtitle="Deactivated accounts stay listed. One that disappears is one nobody remembers to review."
            />
            {users.loading ? (
              <Spinner label="Loading accounts" />
            ) : (users.data ?? []).length === 0 ? (
              <Empty title="No accounts" />
            ) : (
              <Table minWidth={900}>
                <thead>
                  <tr>
                    <Th>Account</Th>
                    <Th>Access</Th>
                    <Th>Sign-in</Th>
                    <Th>Created</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {(users.data ?? []).map((account, index) => {
                    const self = account.email === session?.email;
                    return (
                      <Tr key={account.id} index={index}>
                        <Td>
                          <span className={account.is_active ? "text-ink" : "text-faint"}>
                            {account.full_name ?? account.email}
                          </span>
                          <div className="mt-0.5 text-xs text-faint">{account.email}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {account.is_active ? null : <Tag tone="warn">Deactivated</Tag>}
                            {self ? <Tag>You</Tag> : null}
                          </div>
                        </Td>
                        <Td>
                          <div className="flex flex-wrap gap-1">
                            {account.memberships.map((m) => (
                              <Tag key={m.id} tone={m.role === "org_admin" ? "strong" : "quiet"}>
                                {roleLabel(m.role)}
                              </Tag>
                            ))}
                            {account.memberships.length === 0 ? (
                              <span className="text-xs text-faint">No grants</span>
                            ) : null}
                          </div>
                        </Td>
                        <Td className="text-muted">
                          {account.identity_provider}
                          {account.has_local_password ? null : (
                            <div
                              className="mt-0.5 text-2xs text-faint"
                              title="Federated accounts have no local password and cannot be given one."
                            >
                              no local password
                            </div>
                          )}
                        </Td>
                        <Td className="text-muted">{formatDate(account.created_at)}</Td>
                        <Td align="right">
                          <div className="flex justify-end gap-1.5">
                            {account.has_local_password && !self ? (
                              <Button onClick={() => setResetting(account)}>Reset password</Button>
                            ) : null}
                            {!self ? (
                              <Button onClick={() => void toggleActive(account)}>
                                {account.is_active ? "Deactivate" : "Reactivate"}
                              </Button>
                            ) : null}
                          </div>
                        </Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Card>

          <Caveat>
            The last active administrator cannot be deactivated and their grant cannot be
            revoked, and nobody can deactivate themselves. Both are how someone locks everybody
            out of their own deployment. A password change does not end sessions already issued —
            rotate <span className="font-mono">AEGIS_SECRET_KEY</span> for that.
          </Caveat>
        </>
      )}

      {creating ? (
        <NewAccount
          organizations={orgs.data ?? []}
          roles={vocab.data?.roles ?? []}
          onClose={() => setCreating(false)}
          onCreated={users.reload}
        />
      ) : null}

      {resetting ? (
        <ResetPassword
          account={resetting}
          onClose={() => setResetting(null)}
          onDone={users.reload}
        />
      ) : null}
    </div>
  );
}
