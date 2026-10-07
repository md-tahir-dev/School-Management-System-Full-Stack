"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Select } from "@/components/ui/select";
import { AccessDenied } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useClasses } from "@/lib/queries";
import type { Page, StudentListItem } from "@/lib/types";
import { initials } from "@/lib/utils";

const PAGE_SIZE = 15;

/** Read-only list (server-side search, filter and pagination). Opens the profile with Attendance and Results tabs. */
export default function StudentsPage() {
  const { user } = useAuth();
  const classes = useClasses();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [classId, setClassId] = useState("");
  const allowed = user?.role === "admin" || user?.role === "ceo" || user?.role === "teacher";

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["students", { page, q, classId }],
    queryFn: ({ signal }) => api<Page<StudentListItem>>("/students", { query: { page, page_size: PAGE_SIZE, q, class_id: classId }, signal }),
    placeholderData: keepPreviousData,
    enabled: allowed,
  });
  const onSearch = useCallback((v: string) => { setQ(v); setPage(1); }, []);

  if (user && !allowed) return <AccessDenied />;
  const columns: Column<StudentListItem>[] = [
    { key: "name", header: "Student", cell: (s) => (
      <Link href={`/${user?.role}/students/${s.id}`} className="flex items-center gap-3 hover:underline">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-primary">{initials(s.full_name)}</span>
        <span className="font-medium text-primary">{s.full_name}</span>
      </Link>) },
    { key: "roll", header: "Roll no.", cell: (s) => s.roll_no },
    { key: "class", header: "Class", cell: (s) => `${s.class_name}${s.section_name ? ` · ${s.section_name}` : ""}` },
    { key: "father", header: "Father", cell: (s) => s.father_name ?? "-" },
    { key: "status", header: "Status", cell: (s) => <StatusBadge status={s.status} /> },
  ];
  return (
    <>
      <PageHeader title="Students" description="Open a student to see attendance and results." />
      <DataTable columns={columns} rows={data?.items} rowKey={(s) => s.id} total={data?.total ?? 0} page={page} pageSize={PAGE_SIZE} onPageChange={setPage}
        onSearchChange={onSearch} searchPlaceholder="Search by name or roll no."
        filters={<Select aria-label="Filter by class" value={classId} onChange={(e) => { setClassId(e.target.value); setPage(1); }}><option value="">All classes</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>}
        isLoading={isLoading} isFetching={isFetching} error={error} onRetry={() => refetch()} emptyTitle="No students match" emptyHint="Try a different name or class." />
    </>
  );
}
