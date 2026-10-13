"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";
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

const columns: Column<User>[] = [
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
  { key: "last_login", header: "Last sign-in", cell: (u) => <span className="text-muted-foreground">{formatDateTime(u.last_login)}</span> },
];

export default function UsersPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"" | Role>("");

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
      <PageHeader title="Users" description="Everyone who can sign in to the system." />
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
