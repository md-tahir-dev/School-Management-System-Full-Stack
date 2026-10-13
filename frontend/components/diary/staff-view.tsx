"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import { useClasses, useMyTeacher, useSections } from "@/lib/queries";
import { isManager } from "@/lib/role-config";
import type { DiaryEntry, Role } from "@/lib/types";
import { FileLink } from "./common";
import { DayNav } from "./day-nav";
import { EntryForm, useClassSubjectOpts } from "./entry-form";
import { SubmissionsModal } from "./submissions-modal";

export function StaffDiary({ role, date, setDate }: { role: Role; date: string; setDate: (d: string) => void }) {
  const qc = useQueryClient();
  const isTeacher = role === "teacher";
  const canWrite = isTeacher || isManager(role);
  const me = useMyTeacher();
  const allClasses = useClasses();
  const assigns = useMemo(() => me.data?.assignments ?? [], [me.data]);

  const classes = useMemo(() => {
    if (!isTeacher) return (allClasses.data ?? []).map((c) => ({ id: c.id, name: c.name }));
    const m = new Map<string, string>();
    assigns.forEach((a) => m.set(a.class_id, a.class_name));
    return [...m].map(([id, name]) => ({ id, name }));
  }, [isTeacher, allClasses.data, assigns]);

  const [classId, setClassId] = useState("");
  const [sec, setSec] = useState("");
  const cid = classes.some((c) => c.id === classId) ? classId : classes[0]?.id ?? "";
  const secQ = useSections(cid || undefined);
  const sections = useMemo(() => {
    const all = secQ.data ?? [];
    if (!isTeacher) return all;
    const mine = assigns.filter((a) => a.class_id === cid);
    // An assignment without a section covers the whole class.
    return mine.some((a) => !a.section_id) ? all : all.filter((s) => mine.some((a) => a.section_id === s.id));
  }, [secQ.data, isTeacher, assigns, cid]);
  const sid = sections.some((s) => s.id === sec) ? sec : sections[0]?.id ?? "";
  const ready = !!cid && !secQ.isLoading;

  const mgrSubjects = useClassSubjectOpts(cid, !isTeacher);
  const subjects = useMemo(() => {
    if (!isTeacher) return mgrSubjects;
    const m = new Map<string, string>();
    assigns.filter((a) => a.class_id === cid && (!a.section_id || a.section_id === sid)).forEach((a) => m.set(a.subject_id, a.subject_name));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [isTeacher, mgrSubjects, assigns, cid, sid]);

  const q = useQuery({
    queryKey: ["diary", "staff", cid, sid, date],
    queryFn: () => api<DiaryEntry[]>("/diary", { query: { date, class_id: cid, section_id: sid || undefined } }),
    enabled: ready,
  });

  const [editing, setEditing] = useState<DiaryEntry | "new" | null>(null);
  const [subs, setSubs] = useState<DiaryEntry | null>(null);
  const [del, setDel] = useState<DiaryEntry | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/diary/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Entry deleted"); qc.invalidateQueries({ queryKey: ["diary"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete entry")),
  });

  // General notes first, then by subject.
  const sorted = [...(q.data ?? [])].sort((a, b) => (a.subject_name ? 1 : 0) - (b.subject_name ? 1 : 0) || (a.subject_name ?? "").localeCompare(b.subject_name ?? ""));
  const groups = sorted.reduce<[string, DiaryEntry[]][]>((acc, e) => {
    const k = e.subject_name ?? "General notes";
    const g = acc.find((x) => x[0] === k);
    if (g) g[1].push(e); else acc.push([k, [e]]);
    return acc;
  }, []);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <DayNav date={date} onChange={setDate} />
        <Select aria-label="Class" value={cid} onChange={(e) => { setClassId(e.target.value); setSec(""); }}>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        {sections.length > 0 && (
          <Select aria-label="Section" value={sid} onChange={(e) => setSec(e.target.value)}>
            {sections.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        )}
        {canWrite && <Button className="ml-auto" onClick={() => setEditing("new")} disabled={!ready}><Plus className="h-4 w-4" aria-hidden />New entry</Button>}
      </div>

      {me.isLoading || allClasses.isLoading || q.isLoading ? <ListSkeleton rows={3} /> : q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : !cid ? (
        <EmptyState title={isTeacher ? "No classes assigned to you" : "No classes yet"} />
      ) : !groups.length ? (
        <EmptyState title="No diary entries for this day" />
      ) : (
        <div className="space-y-6">
          {groups.map(([name, list]) => (
            <section key={name} aria-label={name} className="space-y-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-primary">{name}</h2>
              {list.map((e) => (
                <Card key={e.id}>
                  <CardHeader className="flex-row flex-wrap items-center gap-2">
                    <CardTitle>{e.title}</CardTitle>
                    {e.can_edit && (
                      <div className="ml-auto flex gap-1">
                        <Button variant="ghost" size="icon" aria-label={`Edit ${e.title}`} onClick={() => setEditing(e)}><Pencil className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" aria-label={`Delete ${e.title}`} onClick={() => setDel(e)}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    )}
                  </CardHeader>
                  <CardContent>
                    <p className="whitespace-pre-wrap text-sm">{e.body}</p>
                    {e.attachment_url && <FileLink href={e.attachment_url} />}
                    <p className="mt-2 text-xs text-muted-foreground">{e.author_name ? `By ${e.author_name}` : ""}{e.due_date ? ` · due ${dateLabel(e.due_date)}` : ""}</p>
                    {e.submission_required && (
                      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                        <span>{e.submission_count ?? 0} submitted</span>
                        <Button size="sm" variant="outline" onClick={() => setSubs(e)}>Submissions</Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </section>
          ))}
        </div>
      )}

      {canWrite && <EntryForm open={!!editing} onClose={() => setEditing(null)} classId={cid} sectionId={sid} date={date} entry={editing && editing !== "new" ? editing : undefined} subjects={subjects} />}
      <SubmissionsModal entry={subs} onClose={() => setSubs(null)} canEdit={!!subs?.can_edit} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title="Delete diary entry" description={`Delete "${del?.title}"? Student submissions for it are removed too.`} confirmLabel="Delete entry" destructive onConfirm={async () => { await remove.mutateAsync(del!.id).catch(() => {}); }} />
    </>
  );
}
