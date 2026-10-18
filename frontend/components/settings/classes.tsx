"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useClasses, useSections, useSubjects } from "@/lib/queries";
import type { ClassOut, ClassSubject, ClassTeacher, Page, TeacherListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type Pending = { kind: "class" | "section"; id: string; name: string } | null;

/** Sections of one class: add, delete. */
function Sections({ klass, onDelete }: { klass: ClassOut; onDelete: (p: Pending) => void }) {
  const qc = useQueryClient();
  const sections = useSections(klass.id);
  const [name, setName] = useState("");
  const add = useMutation({
    mutationFn: () => api(`/classes/${klass.id}/sections`, { method: "POST", body: { name: name.trim() } }),
    onSuccess: () => { setName(""); qc.invalidateQueries({ queryKey: ["sections", klass.id] }); qc.invalidateQueries({ queryKey: ["classes"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't add section")),
  });
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold">Sections</h4>
      <div className="mb-2 flex flex-wrap gap-2">
        {sections.data?.map((s) => (
          <span key={s.id} className="inline-flex items-center gap-1 rounded-full border border-border py-1 pl-3 pr-1 text-sm">
            {s.name} <span className="text-xs text-muted-foreground">({s.student_count})</span>
            <button type="button" aria-label={`Delete section ${s.name}`} className="rounded-full p-1 hover:bg-muted" onClick={() => onDelete({ kind: "section", id: s.id, name: `${klass.name} ${s.name}` })}><X className="h-3.5 w-3.5" /></button>
          </span>
        ))}
        {sections.data?.length === 0 && <span className="text-sm text-muted-foreground">No sections. Students can still be placed in the class.</span>}
      </div>
      <div className="flex gap-2">
        <Input aria-label="New section name" className="w-32" placeholder="e.g. C" value={name} maxLength={32} onChange={(e) => setName(e.target.value)} />
        <Button variant="outline" size="sm" onClick={() => add.mutate()} loading={add.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />Add section</Button>
      </div>
    </div>
  );
}

/** One class-teacher select per section (or per class when it has no sections). */
function ClassTeachers({ klass }: { klass: ClassOut }) {
  const qc = useQueryClient();
  const sections = useSections(klass.id);
  const teachers = useQuery({ queryKey: ["teachers-pick"], queryFn: () => api<Page<TeacherListItem>>("/teachers", { query: { page_size: 100 } }), select: (p) => p.items });
  const assigned = useQuery({ queryKey: ["class-teachers"], queryFn: () => api<ClassTeacher[]>("/class-teachers") });
  const set = useMutation({
    mutationFn: (v: { section_id: string | null; teacher_id: string | null }) => api("/class-teachers", { method: "PUT", body: { class_id: klass.id, ...v } }),
    onSuccess: () => { toast.success("Class teacher saved"); qc.invalidateQueries({ queryKey: ["class-teachers"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't save class teacher")),
  });
  if (!sections.data) return null;
  const targets: { id: string | null; label: string }[] = sections.data.length ? sections.data.map((s) => ({ id: s.id, label: `Section ${s.name}` })) : [{ id: null, label: klass.name }];
  return (
    <div className="lg:col-span-2">
      <h4 className="mb-2 text-sm font-semibold">Class teacher</h4>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {targets.map((t) => (
          <Field key={t.id ?? "class"} label={t.label}>
            <Select
              value={assigned.data?.find((a) => a.class_id === klass.id && a.section_id === t.id)?.teacher_id ?? ""}
              disabled={set.isPending || assigned.isLoading}
              onChange={(e) => set.mutate({ section_id: t.id, teacher_id: e.target.value || null })}
            >
              <option value="">No class teacher</option>
              {teachers.data?.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}
            </Select>
          </Field>
        ))}
      </div>
    </div>
  );
}

type Row = { subject_id: string; total: string; passing: string };

/** The subjects taught in a class, with total and passing marks. Saved as a whole list. */
function ClassSubjects({ klass }: { klass: ClassOut }) {
  const qc = useQueryClient();
  const all = useSubjects();
  const q = useQuery({ queryKey: ["class-subjects", klass.id], queryFn: () => api<ClassSubject[]>(`/classes/${klass.id}/subjects`) });
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => { if (q.data) setRows(q.data.map((r) => ({ subject_id: r.subject_id, total: String(Number(r.total_marks)), passing: String(Number(r.passing_marks)) }))); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api(`/classes/${klass.id}/subjects`, { method: "PUT", body: rows.map((r) => ({ subject_id: r.subject_id, total_marks: r.total, passing_marks: r.passing })) }),
    onSuccess: () => { toast.success(`${klass.name} subjects saved`); qc.invalidateQueries({ queryKey: ["class-subjects", klass.id] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't save subjects")),
  });
  const unused = all.data?.filter((s) => !rows.some((r) => r.subject_id === s.id)) ?? [];
  const nameOf = (id: string) => all.data?.find((s) => s.id === id)?.name ?? "";
  const valid = rows.every((r) => Number(r.total) > 0 && Number(r.passing) >= 0 && Number(r.passing) <= Number(r.total));
  if (q.isLoading) return <ListSkeleton rows={2} />;
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold">Subjects and marks</h4>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={r.subject_id} className="grid grid-cols-[1fr_5.5rem_5.5rem_auto] items-center gap-2 text-sm">
            <span className="truncate">{nameOf(r.subject_id)}</span>
            <Input aria-label={`${nameOf(r.subject_id)} total marks`} type="number" min={1} value={r.total} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, total: e.target.value } : x)))} />
            <Input aria-label={`${nameOf(r.subject_id)} passing marks`} type="number" min={0} value={r.passing} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, passing: e.target.value } : x)))} />
            <Button size="icon" variant="ghost" aria-label={`Remove ${nameOf(r.subject_id)}`} onClick={() => setRows((p) => p.filter((_, j) => j !== i))}><X className="h-4 w-4" /></Button>
          </div>
        ))}
        {rows.length > 0 && <p className="text-xs text-muted-foreground">Columns: total marks, passing marks.</p>}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Select aria-label="Add a subject" value="" onChange={(e) => e.target.value && setRows((p) => [...p, { subject_id: e.target.value, total: "100", passing: "40" }])} disabled={!unused.length}>
          <option value="">{unused.length ? "Add a subject..." : "All subjects added"}</option>
          {unused.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
        <Button size="sm" onClick={() => save.mutate()} loading={save.isPending} disabled={!valid}>Save subjects</Button>
      </div>
    </div>
  );
}

export function Classes() {
  const qc = useQueryClient();
  const classes = useClasses();
  const [name, setName] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const add = useMutation({
    mutationFn: () => api("/classes", { method: "POST", body: { name: name.trim(), order: classes.data?.length ?? 0 } }),
    onSuccess: () => { toast.success("Class added"); setName(""); qc.invalidateQueries({ queryKey: ["classes"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't add class")),
  });
  const del = useMutation({
    mutationFn: (p: NonNullable<Pending>) => api(p.kind === "class" ? `/classes/${p.id}` : `/sections/${p.id}`, { method: "DELETE" }),
    onSuccess: (_, p) => { toast.success(`${p.kind === "class" ? "Class" : "Section"} deleted`); qc.invalidateQueries({ queryKey: ["classes"] }); qc.invalidateQueries({ queryKey: ["sections"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete")), // 409 when students are enrolled
  });
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <Field label="New class"><Input value={name} maxLength={64} placeholder="e.g. Class 4" onChange={(e) => setName(e.target.value)} /></Field>
        <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />Add class</Button>
      </Card>
      {classes.isLoading ? <ListSkeleton rows={4} /> : classes.error ? <ErrorState error={classes.error} onRetry={() => classes.refetch()} /> : !classes.data?.length ? <EmptyState title="No classes yet" hint="Add your first class above." /> : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {classes.data.map((c) => (
            <li key={c.id}>
              <div className="flex items-center gap-2 px-4 py-2">
                <button type="button" aria-expanded={open === c.id} className="flex min-h-[44px] flex-1 items-center gap-2 text-left text-sm" onClick={() => setOpen(open === c.id ? null : c.id)}>
                  <ChevronDown className={cn("h-4 w-4 transition-transform", open === c.id && "rotate-180")} aria-hidden />
                  <span className="font-semibold">{c.name}</span>
                  <span className="text-muted-foreground">{c.section_count} sections · {c.student_count} students</span>
                </button>
                <Button size="icon" variant="ghost" aria-label={`Delete ${c.name}`} onClick={() => setPending({ kind: "class", id: c.id, name: c.name })}><Trash2 className="h-4 w-4 text-danger" /></Button>
              </div>
              {open === c.id && (
                <div className="grid gap-6 border-t border-border bg-muted/30 px-4 py-4 lg:grid-cols-2">
                  <Sections klass={c} onDelete={setPending} />
                  <ClassSubjects klass={c} />
                  <ClassTeachers klass={c} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!pending} onOpenChange={(o) => !o && setPending(null)} title={`Delete ${pending?.name ?? ""}?`} description="This can't be undone. Classes and sections with students can't be deleted." confirmLabel={`Delete ${pending?.kind ?? ""}`} destructive onConfirm={async () => { if (pending) await del.mutateAsync(pending).catch(() => undefined); }} />
    </div>
  );
}
