"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { GradingModal } from "@/components/tests/grading-modal";
import { QuestionBuilder } from "@/components/tests/question-builder";
import { TestForm, whenLabel } from "@/components/tests/test-form";
import { Button } from "@/components/ui/button";
import { ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { Tabs } from "@/components/ui/tabs";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtMarks } from "@/lib/format";
import type { AttemptRow, TestDetail } from "@/lib/types";

type Action = "publish" | "close" | "release" | "delete";
const COPY: Record<Action, [string, string, string]> = {
  publish: ["Publish test", "Students in the class will be able to start it during the open window. Questions can no longer be edited.", "Publish"],
  close: ["Close test", "No new attempts or answers will be accepted.", "Close test"],
  release: ["Release results", "Students and parents will see scores and answers.", "Release results"],
  delete: ["Delete test", "This permanently removes the test.", "Delete test"],
};

function Attempts({ test, canGrade }: { test: TestDetail; canGrade: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["tests", test.id, "attempts"], queryFn: () => api<AttemptRow[]>(`/tests/${test.id}/attempts`) });
  const cols: Column<AttemptRow>[] = [
    { key: "s", header: "Student", cell: (a) => <button type="button" className="min-h-11 text-left font-medium text-primary hover:underline" onClick={() => setOpen(a.attempt_id)}>{a.student_name}</button> },
    { key: "r", header: "Roll no", cell: (a) => a.roll_no ?? "-" },
    { key: "st", header: "Status", cell: (a) => <StatusBadge status={a.status} label={a.needs_grading ? "Needs grading" : a.status === "in_progress" ? "In progress" : undefined} tone={a.needs_grading ? "warning" : undefined} /> },
    { key: "t", header: "Submitted", cell: (a) => whenLabel(a.submitted_at) },
    { key: "sc", header: "Score", align: "right", cell: (a) => (a.score != null ? `${fmtMarks(a.score)} / ${fmtMarks(test.total_marks)}` : "-") },
  ];
  const rows = q.data ?? [];
  return (
    <>
      <DataTable columns={cols} rows={rows} rowKey={(a) => a.attempt_id} total={rows.length} page={1} pageSize={Math.max(rows.length, 1)} onPageChange={() => {}} isLoading={q.isLoading} error={q.error as Error | null} onRetry={() => q.refetch()} emptyTitle="No attempts yet" />
      <GradingModal attemptId={open} testId={test.id} canGrade={canGrade} onClose={() => setOpen(null)} />
    </>
  );
}

export default function TestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"details" | "questions" | "attempts">("details");
  const [confirm, setConfirm] = useState<Action | null>(null);
  const q = useQuery({ queryKey: ["tests", id], queryFn: () => api<TestDetail>(`/tests/${id}`) });
  const act = useMutation({
    mutationFn: (a: Action): Promise<unknown> => (a === "delete" ? api<void>(`/tests/${id}`, { method: "DELETE" }) : api<TestDetail>(`/tests/${id}/${a}`, { method: "POST" })),
    onSuccess: (_, a) => {
      toast.success(`${COPY[a][2]} done`);
      qc.invalidateQueries({ queryKey: ["tests"] });
      if (a === "delete") router.push(`/${user?.role}/tests`);
    },
    onError: (e) => toast.error(errorText(e, "Action failed")),
  });
  if (!user) return null;
  const t = q.data;
  const draft = t?.status === "draft";
  const canEdit = !!t?.can_edit;
  const actions = t && canEdit ? (
    <>
      {draft && <Button onClick={() => setConfirm("publish")}>Publish</Button>}
      {t.status === "published" && <Button variant="outline" onClick={() => setConfirm("close")}>Close</Button>}
      {t.status !== "draft" && !t.results_released && <Button variant="outline" onClick={() => setConfirm("release")}>Release results</Button>}
      {(draft || t.attempt_count === 0) && <Button variant="destructive" onClick={() => setConfirm("delete")}>Delete</Button>}
    </>
  ) : undefined;
  return (
    <PageBoundary>
      {q.isLoading ? <ListSkeleton rows={4} /> : q.error || !t ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : (
        <>
          <PageHeader title={t.title} description={`${t.class_name}${t.section_name ? ` - ${t.section_name}` : ""} · ${t.subject_name} · ${fmtMarks(t.total_marks)} marks${t.results_released ? " · results released" : ""}`} actions={<><StatusBadge status={t.status} />{actions}</>} />
          <Tabs label="Test sections" value={tab} onChange={setTab} tabs={[{ key: "details", label: "Details" }, { key: "questions", label: `Questions (${t.question_count})` }, { key: "attempts", label: `Attempts (${t.attempt_count})` }]} />
          {tab === "details" && <TestForm role={user.role} test={t} readOnly={!draft || !canEdit} />}
          {tab === "questions" && <QuestionBuilder test={t} editable={draft && canEdit} />}
          {tab === "attempts" && <Attempts test={t} canGrade={canEdit} />}
          {confirm && (
            <ConfirmDialog open onOpenChange={(o) => !o && setConfirm(null)} title={COPY[confirm][0]} description={COPY[confirm][1]} confirmLabel={COPY[confirm][2]} destructive={confirm === "delete"} onConfirm={async () => { await act.mutateAsync(confirm).catch(() => {}); }} />
          )}
        </>
      )}
    </PageBoundary>
  );
}
