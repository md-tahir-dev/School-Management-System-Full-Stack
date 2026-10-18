"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { humanize } from "@/components/forms";
import { PageHeader } from "@/components/page-header";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { AccessDenied } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMetaOptions } from "@/lib/queries";
import { isSchoolWide } from "@/lib/role-config";
import type { Page, TeacherListItem } from "@/lib/types";
import { initials } from "@/lib/utils";

const PAGE_SIZE = 15;

export default function TeachersPage() {
  const { user } = useAuth();
  const opts = useMetaOptions();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [designation, setDesignation] = useState("");
  const allowed = isSchoolWide(user?.role);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["teachers", { page, q, designation }],
    queryFn: ({ signal }) => api<Page<TeacherListItem>>("/teachers", { query: { page, page_size: PAGE_SIZE, q, designation }, signal }),
    placeholderData: keepPreviousData,
    enabled: allowed,
  });
  const onSearch = useCallback((v: string) => { setQ(v); setPage(1); }, []);

  if (user && !allowed) return <AccessDenied />;
  const columns: Column<TeacherListItem>[] = [
    { key: "name", header: "Teacher", cell: (t) => (
      <Link href={`/${user?.role}/teachers/${t.id}`} className="flex items-center gap-3 hover:underline">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-primary">{initials(t.full_name)}</span>
        <span className="font-medium text-primary">{t.full_name}</span>
      </Link>) },
    { key: "emp", header: "Employee ID", cell: (t) => t.employee_id },
    { key: "designation", header: "Designation", cell: (t) => (t.designation ? humanize(t.designation) : "-") },
    { key: "subjects", header: "Subjects", cell: (t) => t.subjects.join(", ") || "-" },
    { key: "classes", header: "Classes", cell: (t) => t.classes.join(", ") || "-" },
    { key: "phone", header: "Phone", cell: (t) => t.phone ?? "-" },
  ];
  return (
    <>
      <PageHeader title="Teachers" description="Faculty profiles, teaching assignments and salary structure."
        actions={user?.role === "admin" ? <Button asChild><Link href={`/${user.role}/teachers/new`}><UserPlus className="h-4 w-4" />Register teacher</Link></Button> : undefined} />
      <DataTable columns={columns} rows={data?.items} rowKey={(t) => t.id} total={data?.total ?? 0} page={page} pageSize={PAGE_SIZE} onPageChange={setPage}
        onSearchChange={onSearch} searchPlaceholder="Search by name, employee ID or phone"
        filters={<Select aria-label="Filter by designation" value={designation} onChange={(e) => { setDesignation(e.target.value); setPage(1); }}><option value="">All designations</option>{opts.data?.designations.map((d) => <option key={d} value={d}>{humanize(d)}</option>)}</Select>}
        isLoading={isLoading} isFetching={isFetching} error={error} onRetry={() => refetch()} emptyTitle="No teachers match" emptyHint="Try a different name or designation." />
    </>
  );
}
