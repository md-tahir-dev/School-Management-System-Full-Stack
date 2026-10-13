"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { api, errorText } from "@/lib/api";
import type { ClassSubject, Page, TeacherListItem, TimetableEntry } from "@/lib/types";

export interface CellTarget { classId: string; sectionId: string | null; weekday: number; periodId: string; entry?: TimetableEntry; label: string }

export function CellDialog({ target, onClose }: { target: CellTarget | null; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useApiForm({ subject_id: "", teacher_id: "", room: "" });
  const subjects = useQuery({ queryKey: ["class-subjects", target?.classId], queryFn: () => api<ClassSubject[]>(`/classes/${target!.classId}/subjects`), enabled: !!target });
  const teachers = useQuery({ queryKey: ["teachers-pick"], queryFn: () => api<Page<TeacherListItem>>("/teachers", { query: { page_size: 100 } }), select: (p) => p.items, enabled: !!target });
  const { reset } = form;
  useEffect(() => {
    if (target) reset({ subject_id: target.entry?.subject_id ?? "", teacher_id: target.entry?.teacher_id ?? "", room: target.entry?.room ?? "" });
  }, [target, reset]);
  const done = (msg: string) => { toast.success(msg); qc.invalidateQueries({ queryKey: ["timetable"] }); onClose(); };
  const save = useMutation({
    mutationFn: () => api("/timetable/cell", { method: "PUT", body: { class_id: target!.classId, section_id: target!.sectionId, weekday: target!.weekday, period_id: target!.periodId, subject_id: form.values.subject_id, teacher_id: form.values.teacher_id, room: (form.values.room ?? "").trim() || null } }),
    onSuccess: () => done("Lecture saved"),
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't save lecture")); },
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/timetable/cell/${target!.entry!.id}`, { method: "DELETE" }),
    onSuccess: () => done("Lecture removed"),
    onError: (e) => toast.error(errorText(e, "Couldn't remove lecture")),
  });
  return (
    <Modal
      open={!!target}
      onOpenChange={(o) => !o && onClose()}
      title="Lecture"
      description={target?.label}
      footer={
        <>
          {target?.entry && <Button variant="destructive" onClick={() => remove.mutate()} loading={remove.isPending}>Remove</Button>}
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!form.values.subject_id || !form.values.teacher_id}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <SelectField form={form} name="subject_id" label="Subject" placeholder="Select subject..." options={subjects.data?.map((s) => ({ value: s.subject_id, label: s.subject_name })) ?? []} />
        <SelectField form={form} name="teacher_id" label="Teacher" placeholder="Select teacher..." options={teachers.data?.map((t) => ({ value: t.id, label: t.full_name })) ?? []} />
        <TextField form={form} name="room" label="Room (optional)" maxLength={32} />
      </div>
    </Modal>
  );
}
