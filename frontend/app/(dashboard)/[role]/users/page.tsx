"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { CredentialsModal, type ShownCredential } from "@/components/modals/credentials-modal";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isManager, isSchoolWide } from "@/lib/role-config";
import type { Page, Role, User } from "@/lib/types";
import { capitalize, formatDateTime, initials } from "@/lib/utils";

const PAGE_SIZE = 15;
const ROLE_FILTERS: { value: "" | Role; label: string }[] = [
  { value: "", label: "All roles" },
  { value: "admin", label: "Admin" },
  { value: "ceo", label: "CEO" },
  { value: "headmaster", label: "Headmaster" },
  { value: "teacher", label: "Teacher" },
  { value: "student", label: "Student" },
  { value: "parent", label: "Parent" },
];

const NEW_ROLES = [{ value: "admin", label: "Admin" }, { value: "ceo", label: "CEO" }, { value: "headmaster", label: "Headmaster" }, { value: "teacher", label: "Teacher" }, { value: "student", label: "Student" }];
// A headmaster may only manage these (the API returns 404 for the rest).
const HEADMASTER_CAN = ["teacher", "student", "parent"];
type Creds = { username: string; temp_password: string; must_change_password?: boolean };
const EMPTY = { username: "", full_name: "", role: "" };

function AddUserDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (c: Creds) => void }) {
  const form = useApiForm(EMPTY);
  const create = useMutation({
    mutationFn: () => api<Creds>("/users", { method: "POST", body: form.values }),
    onSuccess: (c) => { form.reset(EMPTY); onCreated(c); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't create the user")); },
  });
  const profileRole = form.values.role === "teacher" || form.values.role === "student" ? form.values.role : null;
  return (
    <Modal open={open} onOpenChange={(o) => !o && !create.isPending && onClose()} title="Add user"
      description="Admin, CEO and headmaster logins are created here. Teacher and student logins are created with their profile."
      footer={profileRole ? <Button variant="outline" className="w-full sm:w-auto" onClick={onClose}>Close</Button> : <><Button variant="outline" className="w-full sm:w-auto" onClick={onClose} disabled={create.isPending}>Cancel</Button><Button className="w-full sm:w-auto" loading={create.isPending} onClick={() => create.mutate()}>Create user</Button></>}>
      <form className="grid grid-cols-1 gap-4" onSubmit={(e) => { e.preventDefault(); if (!profileRole) create.mutate(); }}>
        <SelectField form={form} name="role" label="Role" options={NEW_ROLES} placeholder="Select a role" />
        {profileRole ? (
          <div className="flex flex-col gap-3 rounded-md border border-border bg-muted/40 p-3 text-sm">
            <p>
              {profileRole === "teacher" ? "A teacher's login is created when you register the teacher." : "A student's login is created when you register the student. Parent logins are created automatically at the same time."}
            </p>
            <Button asChild className="w-full sm:w-auto"><Link href={`/admin/${profileRole}s/new`}>Register {profileRole}</Link></Button>
          </div>
        ) : (
          <>
            <TextField form={form} name="username" label="Username" autoCapitalize="none" autoComplete="off" />
            <TextField form={form} name="full_name" label="Full name" />
          </>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

function EditUserDialog({ u, onClose }: { u: User | null; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useApiForm({ username: "", full_name: "" });
  const { reset } = form;
  useEffect(() => { if (u) reset({ username: u.username, full_name: u.full_name ?? "" }); }, [u, reset]);
  const save = useMutation({
    mutationFn: () => api(`/users/${u!.id}`, { method: "PUT", body: form.values }),
    onSuccess: () => { toast.success("User updated"); qc.invalidateQueries({ queryKey: ["users"] }); onClose(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't update the user")); },
  });
  return (
    <Modal open={!!u} onOpenChange={(o) => !o && !save.isPending && onClose()} title="Edit user"
      footer={<><Button variant="outline" className="w-full sm:w-auto" onClick={onClose} disabled={save.isPending}>Cancel</Button><Button className="w-full sm:w-auto" loading={save.isPending} onClick={() => save.mutate()}>Save</Button></>}>
      <form className="grid grid-cols-1 gap-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <TextField form={form} name="full_name" label="Full name" />
        <TextField form={form} name="username" label="Username" autoCapitalize="none" autoComplete="off" />
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

const PW_MODES = [{ value: "generate", label: "Generate a one-time password" }, { value: "set", label: "Set password" }];

function PasswordDialog({ u, onClose, onDone }: { u: User | null; onClose: () => void; onDone: (u: User, c: Creds) => void }) {
  const qc = useQueryClient();
  const form = useApiForm({ mode: "generate", password: "", confirm: "" });
  const { reset } = form;
  useEffect(() => { if (u) reset({ mode: "generate", password: "", confirm: "" }); }, [u, reset]);
  const setting = form.values.mode === "set";
  const save = useMutation({
    mutationFn: () => api<Creds>(`/users/${u!.id}/reset-password`, { method: "POST", body: setting ? { password: form.values.password } : undefined }),
    onSuccess: (c) => { qc.invalidateQueries({ queryKey: ["users"] }); onDone(u!, c); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't change the password")); },
  });
  const submit = () => {
    if (setting && form.values.password !== form.values.confirm) { form.showErrors({ fields: { confirm: "Passwords don't match" } }); return; }
    save.mutate();
  };
  return (
    <Modal open={!!u} onOpenChange={(o) => !o && !save.isPending && onClose()} title={`Password for ${u?.username ?? ""}`}
      description={setting ? "The user can sign in with this password straight away." : "A random password is shown once and the user must change it at next sign-in."}
      footer={<><Button variant="outline" className="w-full sm:w-auto" onClick={onClose} disabled={save.isPending}>Cancel</Button><Button className="w-full sm:w-auto" loading={save.isPending} onClick={submit}>{setting ? "Set password" : "Generate password"}</Button></>}>
      <form className="grid grid-cols-1 gap-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <SelectField form={form} name="mode" label="Action" options={PW_MODES} />
        {setting && (
          <>
            <TextField form={form} name="password" type="password" label="New password" autoComplete="new-password" hint="At least 8 characters, with a letter and a digit." />
            <TextField form={form} name="confirm" type="password" label="Confirm password" autoComplete="new-password" />
          </>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

function RowActions({ u, canEdit, onEdit, onPassword }: { u: User; canEdit: boolean; onEdit: (u: User) => void; onPassword: (u: User) => void }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => api(`/users/${u.id}/${u.is_active ? "deactivate" : "activate"}`, { method: "PUT" }),
    onSuccess: () => { toast.success(u.is_active ? "User deactivated" : "User activated"); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't update the user")),
  });
  return (
    <div className="flex flex-wrap justify-end gap-2">
      {canEdit && <Button size="sm" variant="outline" onClick={() => onEdit(u)}>Edit</Button>}
      <Button size="sm" variant="outline" onClick={() => onPassword(u)}>Password</Button>
      <Button size="sm" variant="outline" loading={toggle.isPending} onClick={() => toggle.mutate()}>{u.is_active ? "Deactivate" : "Activate"}</Button>
    </div>
  );
}

const baseColumns: Column<User>[] = [
  {
    key: "name",
    header: "Name",
    cell: (u) => (
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-primary">
          {initials(u.full_name, u.username)}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium">{u.full_name || u.username}</p>
          <p className="truncate text-xs text-muted-foreground">@{u.username}</p>
        </div>
      </div>
    ),
  },
  { key: "role", header: "Role", cell: (u) => <StatusBadge status={u.role} label={capitalize(u.role)} tone="info" /> },
  {
    key: "status",
    header: "Status",
    cell: (u) => <StatusBadge status={u.is_active ? "active" : "inactive"} />,
  },
  { key: "last_login", header: "Last sign-in", className: "hidden sm:table-cell", cell: (u) => <span className="text-muted-foreground">{formatDateTime(u.last_login)}</span> },
];

export default function UsersPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"" | Role>("");
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [pwFor, setPwFor] = useState<User | null>(null);
  const [shown, setShown] = useState<ShownCredential[] | null>(null);
  const [note, setNote] = useState<string | undefined>();
  const manager = isManager(user?.role);
  const isAdmin = user?.role === "admin";
  const columns: Column<User>[] = manager
    ? [...baseColumns, {
        key: "actions", header: "", className: "text-right",
        cell: (u) => (user?.role === "headmaster" && !HEADMASTER_CAN.includes(u.role) ? null : <RowActions u={u} canEdit={isAdmin} onEdit={setEditing} onPassword={setPwFor} />),
      }]
    : baseColumns;

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["users", { page, q, role }],
    queryFn: ({ signal }) => api<Page<User>>("/users", { query: { page, page_size: PAGE_SIZE, q, role }, signal }),
    placeholderData: keepPreviousData,
    enabled: isSchoolWide(user?.role),
  });

  const onSearch = useCallback((value: string) => {
    setQ(value);
    setPage(1);
  }, []);

  if (user && !isSchoolWide(user.role)) {
    return (
      <div className="py-16 text-center">
        <h1 className="text-xl font-bold">You don't have access to this page</h1>
        <p className="mt-1 text-sm text-muted-foreground">Ask the school administrator if you think this is a mistake.</p>
      </div>
    );
  }

  return (
    <>
      <PageHeader title="Users" description="Everyone who can sign in to the system."
        actions={isAdmin ? <Button onClick={() => setAdding(true)}>Add user</Button> : undefined} />
      <AddUserDialog open={adding} onClose={() => setAdding(false)}
        onCreated={(c) => { setAdding(false); setNote("The user must change this password at next sign-in."); setShown([{ label: "New user", ...c }]); qc.invalidateQueries({ queryKey: ["users"] }); }} />
      <EditUserDialog u={editing} onClose={() => setEditing(null)} />
      <PasswordDialog u={pwFor} onClose={() => setPwFor(null)}
        onDone={(u, c) => { setPwFor(null); setNote(c.must_change_password ? "The user must change this password at next sign-in." : "The user can sign in with this password straight away."); setShown([{ label: u.full_name || u.username, ...c }]); }} />
      {shown && <CredentialsModal credentials={shown} note={note} onDone={() => { setShown(null); setNote(undefined); }} />}
      <DataTable
        columns={columns}
        rows={data?.items}
        rowKey={(u) => u.id}
        total={data?.total ?? 0}
        page={page}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
        onSearchChange={onSearch}
        searchPlaceholder="Search by name or username"
        filters={
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value as "" | Role);
              setPage(1);
            }}
            aria-label="Filter by role"
            className="h-10 rounded-md border border-border bg-card px-3 text-sm"
          >
            {ROLE_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        }
        isLoading={isLoading}
        isFetching={isFetching}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No users match"
        emptyHint="Try a different name or role."
      />
    </>
  );
}
