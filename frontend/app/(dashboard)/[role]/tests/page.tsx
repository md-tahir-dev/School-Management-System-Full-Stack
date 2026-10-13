"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { Modal } from "@/components/modals/modal";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { TestForm, whenLabel } from "@/components/tests/test-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtMarks } from "@/lib/format";
import { useClasses, useStudentScope } from "@/lib/queries";
import { isManager } from "@/lib/role-config";
import type { MyTest, Page, Role, TestOut } from "@/lib/types";

const PAGE_SIZE = 10;

function StaffTests({ role }: { role: Role }) {
  const router = useRouter();
  const classes = useClasses();
  const [page, setPage] = useState(1);
  const [classId, setClassId] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const canWrite = role === "teacher" || isManager(role);
  const q = useQuery({
    queryKey: ["tests", "list", page, classId, status],
    queryFn: () => api<Page<TestOut>>("/tests", { query: { page, page_size: PAGE_SIZE, class_id: classId || undefined, status: status || undefined } }),
  });
  const cols: Column<TestOut>[] = [
    { key: "title", header: "Test", cell: (t) => <Link href={`/${role}/tests/${t.id}`} className="font-medium text-primary hover:underline">{t.title}</Link> },
    { key: "class", header: "Class", cell: (t) => `${t.class_name}${t.section_name ? ` - ${t.section_name}` : ""}` },
    { key: "subject", header: "Subject", cell: (t) => t.subject_name },
    { key: "opens", header: "Opens", cell: (t) => whenLabel(t.start_at) },
    { key: "q", header: "Questions", cell: (t) => `${t.question_count} (${fmtMarks(t.total_marks)} marks)` },
    { key: "status", header: "Status", cell: (t) => <StatusBadge status={t.status} /> },
  ];
  return (
    <>
      <PageHeader title="Tests" description="Online tests with automatic marking for objective questions." actions={canWrite ? <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" aria-hidden />New test</Button> : undefined} />
      <DataTable
        columns={cols} rows={q.data?.items} rowKey={(t) => t.id} total={q.data?.total ?? 0} page={page} pageSize={PAGE_SIZE} onPageChange={setPage}
        isLoading={q.isLoading} isFetching={q.isFetching} error={q.error as Error | null} onRetry={() => q.refetch()} emptyTitle="No tests yet"
        filters={
          <>
            <Select aria-label="Filter by class" value={classId} onChange={(e) => { setClassId(e.target.value); setPage(1); }}>
              <option value="">All classes</option>
              {(classes.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
            <Select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="published">Published</option>
              <option value="closed">Closed</option>
            </Select>
          </>
        }
      />
      <Modal open={creating} onOpenChange={setCreating} title="New test" size="lg">
        {creating && <TestForm role={role} onSaved={(t) => router.push(`/${role}/tests/${t.id}`)} />}
      </Modal>
    </>
  );
}

function TestCard({ t, role, isParent }: { t: MyTest; role: Role; isParent: boolean }) {
  const now = Date.now();
  const start = t.start_at ? Date.parse(t.start_at) : 0;
  const end = t.end_at ? Date.parse(t.end_at) : Infinity;
  const open = t.status === "published" && start <= now && now <= end;
  const done = t.attempt_status && t.attempt_status !== "in_progress";
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center gap-2">
        <CardTitle>{t.title}</CardTitle>
        {t.attempt_status && <StatusBadge status={t.attempt_status} label={t.attempt_status === "in_progress" ? "In progress" : undefined} className="ml-auto" />}
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">{t.subject_name} · {t.time_limit_min} min · {fmtMarks(t.total_marks)} marks</p>
        <p>Opens {whenLabel(t.start_at)} · closes {whenLabel(t.end_at)}</p>
        {t.results_released && t.score != null && <p className="font-semibold">Score: {fmtMarks(t.score)} / {fmtMarks(t.total_marks)}</p>}
        {!isParent && t.attempt_id && (open && !done ? (
          <Button asChild><Link href={`/${role}/tests/take/${t.attempt_id}`}>Resume</Link></Button>
        ) : t.results_released && done ? (
          <Button asChild variant="outline"><Link href={`/${role}/tests/take/${t.attempt_id}`}>View result</Link></Button>
        ) : null)}
        {!isParent && !t.attempt_id && open && <StartButton id={t.id} role={role} />}
      </CardContent>
    </Card>
  );
}

function StartButton({ id, role }: { id: string; role: Role }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  return (
    <>
      <Button
        loading={busy}
        onClick={async () => {
          setBusy(true); setErr("");
          try { const a = await api<{ attempt_id: string }>(`/tests/${id}/start`, { method: "POST" }); router.push(`/${role}/tests/take/${a.attempt_id}`); }
          catch (e) { setErr(e instanceof Error ? e.message : "Couldn't start"); setBusy(false); }
        }}
      >Start</Button>
      {err && <p role="alert" className="text-xs text-danger">{err}</p>}
    </>
  );
}

function FamilyTests({ role }: { role: Role }) {
  const isParent = role === "parent";
  const scope = useStudentScope();
  const q = useQuery({
    queryKey: ["tests", "me", scope.studentId],
    queryFn: () => api<MyTest[]>("/tests/me", { query: { student_id: isParent ? scope.studentId : undefined } }),
    enabled: !!scope.studentId,
  });
  const now = Date.now();
  const all = q.data ?? [];
  const isDone = (t: MyTest) => (t.attempt_status && t.attempt_status !== "in_progress") || t.status === "closed" || (t.end_at ? Date.parse(t.end_at) < now : false);
  const groups: [string, MyTest[]][] = [
    ["Open now", all.filter((t) => !isDone(t) && t.start_at && Date.parse(t.start_at) <= now)],
    ["Upcoming", all.filter((t) => !isDone(t) && !(t.start_at && Date.parse(t.start_at) <= now))],
    ["Done", all.filter(isDone)],
  ];
  return (
    <>
      <PageHeader title={isParent ? "Tests" : "My tests"} actions={isParent ? <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /> : undefined} />
      {scope.error ? <ErrorState error={scope.error} /> : q.isLoading || scope.isLoading ? <ListSkeleton rows={3} /> : q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : !all.length ? (
        <EmptyState title="No tests yet" />
      ) : (
        <div className="space-y-6">
          {groups.filter(([, l]) => l.length).map(([name, list]) => (
            <section key={name} aria-label={name} className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">{name}</h2>
              <div className="grid gap-3 md:grid-cols-2">{list.map((t) => <TestCard key={t.id} t={t} role={role} isParent={isParent} />)}</div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

export default function TestsPage() {
  const { user } = useAuth();
  if (!user) return null;
  const family = user.role === "student" || user.role === "parent";
  return <PageBoundary>{family ? <FamilyTests role={user.role} /> : <StaffTests role={user.role} />}</PageBoundary>;
}
