"use client";

import { useEffect, useState } from "react";
import {
  assignUserRoles,
  createAccessUser,
  createSecret,
  fetchAccessPermissions,
  fetchAccessRoles,
  fetchAccessUsers,
  fetchSecrets,
  revokeSecret,
} from "@/lib/api";
import type {
  PermissionPublic,
  RolePublic,
  SecretReference,
  UserPublic,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ActionButton, SectionCard } from "../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export default function AccessPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [roles, setRoles] = useState<RolePublic[]>([]);
  const [permissions, setPermissions] = useState<PermissionPublic[]>([]);
  const [secrets, setSecrets] = useState<SecretReference[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function load() {
    Promise.all([
      fetchAccessUsers(),
      fetchAccessRoles(),
      fetchAccessPermissions(),
      fetchSecrets(),
    ])
      .then(([u, r, p, s]) => {
        setUsers(u);
        setRoles(r);
        setPermissions(p);
        setSecrets(s);
        setState({ kind: "ok" });
      })
      .catch((err: unknown) => {
        setState({
          kind: "error",
          message:
            err instanceof Error ? err.message : "Failed to load access data",
        });
      });
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      {(error || done) && (
        <p
          className={
            error
              ? "rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300"
              : "rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-300"
          }
        >
          {error ?? done}
        </p>
      )}

      {state.kind === "loading" ? (
        <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
      ) : state.kind === "error" ? (
        <p className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
          {state.message}
        </p>
      ) : (
        <>
          <CreateUserPanel
            roles={roles}
            onCreated={(msg) => {
              setDone(msg);
              load();
            }}
            onError={(msg) => setError(msg)}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <UsersPanel
              users={users}
              roles={roles}
              onAssign={async (userId, roleIds) => {
                await assignUserRoles(userId, roleIds);
                setDone("Roles updated.");
                load();
              }}
            />
            <RolesPanel roles={roles} permissions={permissions} />
          </div>

          <SecretsPanel
            secrets={secrets}
            onRevoke={async (id) => {
              await revokeSecret(id);
              setDone("Secret revoked; value remains encrypted at rest.");
              load();
            }}
            onCreate={async (input) => {
              await createSecret(input);
              setDone("Secret stored encrypted; only a reference is shown.");
              load();
            }}
          />
        </>
      )}
    </div>
  );
}

// ── create user ─────────────────────────────────────────────────────────────

function CreateUserPanel({
  roles,
  onCreated,
  onError,
}: {
  roles: RolePublic[];
  onCreated: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <SectionCard title="Create user">
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          type="email"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="display name"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="initial password"
          type="password"
          autoComplete="new-password"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          <option value="">
            {roles.length > 0 ? "select role…" : "no roles available"}
          </option>
          {roles.map((r) => (
            <option key={r.id} value={r.code}>
              {r.name}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-2">
        <ActionButton
          busy={busy}
          disabled={!email.trim() || !displayName.trim() || !password}
          onClick={async () => {
            setBusy(true);
            try {
              await createAccessUser({
                email: email.trim(),
                display_name: displayName.trim(),
                password,
                roles: role ? [role] : undefined,
              });
              setEmail("");
              setDisplayName("");
              setPassword("");
              setRole("");
              onCreated(`User ${email.trim()} created.`);
            } catch (err: unknown) {
              onError(err instanceof Error ? err.message : "User creation failed");
            } finally {
              setBusy(false);
            }
          }}
        >
          Create user
        </ActionButton>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Passwords are stored hashed (PBKDF2) — never plaintext. Logins are
          rate-limited and recorded as security events.
        </p>
      </div>
    </SectionCard>
  );
}

// ── users + role assignment ─────────────────────────────────────────────────

function UsersPanel({
  users,
  roles,
  onAssign,
}: {
  users: UserPublic[];
  roles: RolePublic[];
  onAssign: (userId: string, roleIds: string[]) => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});

  async function assign(user: UserPublic) {
    const code = picked[user.id];
    if (!code) return;
    setBusy(user.id);
    try {
      await onAssign(user.id, [code]);
    } finally {
      setBusy(null);
    }
  }

  return (
    <SectionCard title="Users">
      {users.length === 0 ? (
        <p className="text-sm text-zinc-500">No users yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {users.map((u) => (
            <li key={u.id} className="py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {u.display_name}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {u.email}
                  </p>
                </div>
                <StatusBadge
                  status={u.status === "active" ? "active" : "suspended"}
                />
              </div>
              <div className="mt-1 flex items-center gap-2">
                <select
                  value={picked[u.id] ?? ""}
                  onChange={(e) =>
                    setPicked((prev) => ({ ...prev, [u.id]: e.target.value }))
                  }
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                >
                  <option value="">assign role…</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
                <ActionButton
                  busy={busy === u.id}
                  disabled={!picked[u.id]}
                  onClick={() => assign(u)}
                >
                  Assign
                </ActionButton>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

// ── roles + permissions ─────────────────────────────────────────────────────

function RolesPanel({
  roles,
  permissions,
}: {
  roles: RolePublic[];
  permissions: PermissionPublic[];
}) {
  return (
    <SectionCard title="Roles & permissions">
      {roles.length === 0 ? (
        <p className="text-sm text-zinc-500">No roles seeded.</p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {roles.map((r) => (
            <li key={r.id} className="py-2">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {r.name}
                  <span className="ml-2 font-mono text-xs text-zinc-400">
                    {r.code}
                  </span>
                </p>
                <StatusBadge status={r.builtin ? "active" : "created"} />
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {r.scope}
                {r.description ? ` · ${r.description}` : ""}
              </p>
            </li>
          ))}
        </ul>
      )}

      {permissions.length > 0 && (
        <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Permissions
          </p>
          <div className="flex flex-wrap gap-1">
            {permissions.map((p) => (
              <span
                key={p.id}
                className="rounded-full border border-zinc-200 px-2 py-0.5 font-mono text-[10px] text-zinc-600 dark:border-zinc-800 dark:text-zinc-400"
              >
                {p.code}
              </span>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

// ── secrets (references only — values never rendered) ───────────────────────

function SecretsPanel({
  secrets,
  onRevoke,
  onCreate,
}: {
  secrets: SecretReference[];
  onRevoke: (id: string) => Promise<void>;
  onCreate: (input: {
    name: string;
    plaintext: string;
    kind?: string;
    rotation_days?: number;
  }) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [plaintext, setPlaintext] = useState("");
  const [kind, setKind] = useState("api_key");
  const [rotationDays, setRotationDays] = useState("90");
  const [busy, setBusy] = useState<string | null>(null);

  return (
    <SectionCard
      title="Secrets (references only)"
      action={
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          values are never returned or rendered here
        </span>
      }
    >
      <div className="grid gap-2 sm:grid-cols-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="name (e.g. mailgun_api_key)"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 sm:col-span-2"
        />
        <input
          value={plaintext}
          onChange={(e) => setPlaintext(e.target.value)}
          placeholder="plaintext (encrypted at rest)"
          type="password"
          autoComplete="off"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        />
        <div className="flex items-center gap-2">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          >
            <option value="api_key">api key</option>
            <option value="password">password</option>
            <option value="token">token</option>
          </select>
          <input
            type="number"
            value={rotationDays}
            onChange={(e) => setRotationDays(e.target.value)}
            placeholder="rotation days"
            className="w-20 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </div>
      </div>
      <div className="mt-2">
        <ActionButton
          busy={busy === "create"}
          disabled={!name.trim() || !plaintext}
          onClick={async () => {
            setBusy("create");
            try {
              await onCreate({
                name: name.trim(),
                plaintext,
                kind,
                rotation_days: Number(rotationDays) || undefined,
              });
              setName("");
              setPlaintext("");
            } finally {
              setBusy(null);
            }
          }}
        >
          Store secret
        </ActionButton>
      </div>

      {secrets.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">No secrets stored.</p>
      ) : (
        <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-800">
          {secrets.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center justify-between gap-2 py-2"
            >
              <div>
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {s.name}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {s.kind} · key {s.key_id.slice(0, 8)}… · hint{" "}
                  <span className="font-mono">{s.mask_hint ?? "—"}</span>
                  {s.rotation_due_at
                    ? ` · rotation due ${new Date(s.rotation_due_at).toLocaleDateString()}`
                    : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge
                  status={
                    s.status === "active"
                      ? "active"
                      : s.status === "revoked"
                        ? "revoked"
                        : "suspended"
                  }
                />
                {s.status === "active" && (
                  <ActionButton
                    busy={busy === s.id}
                    onClick={async () => {
                      setBusy(s.id);
                      try {
                        await onRevoke(s.id);
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    Revoke
                  </ActionButton>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}