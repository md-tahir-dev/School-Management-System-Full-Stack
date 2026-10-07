"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Modal } from "@/components/modals/modal";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SubjectsEditor } from "@/components/results/subjects-editor";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel } from "@/lib/format";
import { useAcademicYears, useClasses, useSettings } from "@/lib/queries";
import type { Exam, ExamType, Page } from "@/lib/types";
import { PublishDialog } from "@/components/results/publish-dialog";

const PAGE_SIZE = 15;
export const EXAM_TYPES: ExamType[] = ["1st Term", "Mid Term", "Final Term", "Unit Test"];

function CreateExam({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (e: Exam) => void }) {
  const classes = useClasses();
  const years = useAcademicYears();
  const settings = useSettings();
  const [form, setForm] = useState({ name: "", type: "Mid Term" as ExamType, class_id: "", academic_year_id: "", start_date: "", end_date: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const yearId = form.academic_year_id || settings.data?.current_academic_year_id || "";
  const create = useMutation({
    mutationFn: () => api<Exam>("/exams", { method: "POST", body: { ...form, academic_year_id: yearId, start_date: form.start_date || null, end_date: form.end_date || null } }),
    onSuccess: (e) => { toast.success("Exam created. Review its subjects next."); onCreated(e); },
    onError: (e) => { if (e instanceof ApiError) { setFieldErrors(e.fields ?? {}); toast.error(e.message); } },
  });
  const ok = form.name.trim() && form.class_id && yearId;
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Create exam" description="Subjects are copied from the class defaults; you can edit them for this exam next."
      footer={<><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => create.mutate()} loading={create.isPending} disabled={!ok}>Create exam</Button></>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2"><Field label="Name"><Input value={form.name} aria-invalid={!!fieldErrors.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Mid Term 2026" /></Field>{fieldErrors.name && <p className="mt-1 text-xs text-danger">{fieldErrors.name}</p>}</div>
        <Field label="Type"><Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as ExamType })}>{EXAM_TYPES.map((t) => <option key={t}>{t}</option>)}</Select></Field>
        <Field label="Class"><Select value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}><option value="" disabled>Select class</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Academic year"><Select value={yearId} onChange={(e) => setForm({ ...form, academic_year_id: e.target.value })}><option value="" disabled>Select year</option>{years.data?.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}</Select></Field>
        <div />
        <Field label="Start date (optional)"><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
        <Field label="End date (optional)"><Input type="date" min={form.start_date} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

/** F4 (Admin) and CEO read-only: exam list with filters, publish/unpublish and delete. */
export function ExamsList() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";
  const classes = useClasses();
  const years = useAcademicYears();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [f, setF] = useState({ class_id: "", academic_year_id: "", type: "", published: "" });
  const [creating, setCreating] = useState(false);
  const [subjectsFor, setSubjectsFor] = useState<Exam | null>(null);
  const [toDelete, setToDelete] = useState<Exam | null>(null);
  const [publishing, setPublishing] = useState<{ exam: Exam; mode: "publish" | "unpublish" } | null>(null);

  const query = useQuery({
    queryKey: ["exams", { page, q, ...f }],
    queryFn: ({ signal }) => api<Page<Exam>>("/exams", { query: { page, page_size: PAGE_SIZE, q, class_id: f.class_id, academic_year_id: f.academic_year_id, type: f.type, published: f.published }, signal }),
    placeholderData: keepPreviousData,
  });
  const del = useMutation({
    mutationFn: (id: string) => api<void>(`/exams/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Exam deleted"); qc.invalidateQueries({ queryKey: ["exams"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't delete"),
  });
  const set = (k: keyof typeof f, v: string) => { setF((p) => ({ ...p, [k]: v })); setPage(1); };

  const columns: Column<Exam>[] = [
    { key: "name", header: "Exam", cell: (e) => <Link className="font-medium text-primary hover:underline" href={`/${user?.role}/results/exam/${e.id}`}>{e.name}</Link> },
    { key: "class", header: "Class", cell: (e) => e.class_name },
    { key: "type", header: "Type", cell: (e) => e.type },
    { key: "dates", header: "Dates", cell: (e) => <span className="text-muted-foreground">{e.start_date ? `${dateLabel(e.start_date)}${e.end_date ? ` – ${dateLabel(e.end_date)}` : ""}` : "-"}</span> },
    { key: "status", header: "Status", cell: (e) => <StatusBadge status={e.is_published ? "published" : "draft"} /> },
    {
      key: "actions", header: "", align: "right",
      cell: (e) => (
        <div className="flex justify-end gap-1.5">
          <Button size="sm" variant="outline" asChild><Link href={`/${user?.role}/results/exam/${e.id}`}>{isAdmin ? "Manage" : "View"}</Link></Button>
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setPublishing({ exam: e, mode: e.is_published ? "unpublish" : "publish" })}>{e.is_published ? "Unpublish" : "Publish"}</Button>}
          {isAdmin && !e.is_published && <Button size="sm" variant="ghost" className="text-danger" onClick={() => setToDelete(e)}>Delete</Button>}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Exams" description={isAdmin ? "Create exams, track marks entry, publish results." : "Published exam results across the school."}
        actions={isAdmin ? <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />Create exam</Button> : undefined} />
      <DataTable columns={columns} rows={query.data?.items} rowKey={(e) => e.id} total={query.data?.total ?? 0} page={page} pageSize={PAGE_SIZE}
        onPageChange={setPage} onSearchChange={(v) => { setQ(v); setPage(1); }} searchPlaceholder="Search exams"
        filters={<>
          <Select aria-label="Filter by class" value={f.class_id} onChange={(e) => set("class_id", e.target.value)}><option value="">All classes</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Select aria-label="Filter by year" value={f.academic_year_id} onChange={(e) => set("academic_year_id", e.target.value)}><option value="">All years</option>{years.data?.map((y) => <option key={y.id} value={y.id}>{y.label}</option>)}</Select>
          <Select aria-label="Filter by type" value={f.type} onChange={(e) => set("type", e.target.value)}><option value="">All types</option>{EXAM_TYPES.map((t) => <option key={t}>{t}</option>)}</Select>
          <Select aria-label="Filter by status" value={f.published} onChange={(e) => set("published", e.target.value)}><option value="">Any status</option><option value="true">Published</option><option value="false">Draft</option></Select>
        </>}
        isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()}
        emptyTitle="No exams match" emptyHint={isAdmin ? "Create the first exam to start entering marks." : "Try different filters."} />

      {isAdmin && <CreateExam key={String(creating)} open={creating} onOpenChange={setCreating} onCreated={(e) => { setCreating(false); setSubjectsFor(e); qc.invalidateQueries({ queryKey: ["exams"] }); }} />}
      <Modal open={!!subjectsFor} onOpenChange={(o) => !o && setSubjectsFor(null)} title={`Subjects for ${subjectsFor?.name ?? ""}`} description="Set total and passing marks for this exam only." size="lg">
        {subjectsFor && <SubjectsEditor examId={subjectsFor.id} locked={false} onSaved={() => setSubjectsFor(null)} />}
      </Modal>
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title="Delete this exam?" description={`"${toDelete?.name}" will be removed. Exams that already have marks can't be deleted; unpublish them instead.`} confirmLabel="Delete exam" destructive onConfirm={async () => { if (toDelete) await del.mutateAsync(toDelete.id).catch(() => undefined); }} />
      {publishing && <PublishDialog exam={publishing.exam} mode={publishing.mode} onClose={() => setPublishing(null)} />}
    </>
  );
}
