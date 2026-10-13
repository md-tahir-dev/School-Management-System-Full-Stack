"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { api, errorText } from "@/lib/api";
import type { ClassSubject, DiaryEntry } from "@/lib/types";
import { FileInput, TextAreaField } from "./common";

export interface SubjectOpt { value: string; label: string }

/** Create/edit dialog. `subjects` is the allowed list for this class/section (teacher: their own). */
export function EntryForm({ open, onClose, classId, sectionId, date, entry, subjects }: {
  open: boolean; onClose: () => void; classId: string; sectionId: string; date: string; entry?: DiaryEntry; subjects: SubjectOpt[];
}) {
  const qc = useQueryClient();
  const form = useApiForm({ subject_id: "", title: "", body: "", required: "", due_date: "" });
  const [file, setFile] = useState<File | null>(null);
  const [removeFile, setRemoveFile] = useState(false);
  const val = (k: string) => form.values[k] ?? "";
  const { reset } = form;
  useEffect(() => {
    if (!open) return;
    reset({ subject_id: entry?.subject_id ?? "", title: entry?.title ?? "", body: entry?.body ?? "", required: entry?.submission_required ? "1" : "", due_date: entry?.due_date ?? "" });
    setFile(null);
    setRemoveFile(false);
  }, [open, entry, reset]);

  const save = useMutation({
    mutationFn: async () => {
      const v = (k: string) => form.values[k] ?? "";
      const body = {
        class_id: classId, section_id: sectionId || null, subject_id: v("subject_id") || null, date,
        title: v("title").trim(), body: v("body").trim(), submission_required: !!v("required"), due_date: v("required") && v("due_date") ? v("due_date") : null,
      };
      const saved = await api<DiaryEntry>(entry ? `/diary/${entry.id}` : "/diary", { method: entry ? "PUT" : "POST", body });
      if (file || (removeFile && entry?.attachment_url)) {
        const fd = new FormData();
        if (file) fd.append("file", file);
        await api(`/diary/${saved.id}/attachment`, { method: "PUT", body: fd });
      }
    },
    onSuccess: () => { toast.success(entry ? "Entry updated" : "Entry added"); qc.invalidateQueries({ queryKey: ["diary"] }); onClose(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't save entry")); },
  });

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title={entry ? "Edit diary entry" : "New diary entry"}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!val("title").trim() || !val("body").trim()}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        <SelectField form={form} name="subject_id" label="Subject" placeholder="General note (class teacher)" options={subjects} />
        <TextField form={form} name="title" label="Title" maxLength={200} />
        <TextAreaField label="Details" value={val("body")} onChange={(v) => form.set("body", v)} error={form.errors.body} />
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={!!form.values.required} onChange={(e) => form.set("required", e.target.checked ? "1" : "")} />
          Students must submit work
        </label>
        {form.values.required && <TextField form={form} name="due_date" label="Due date" type="date" />}
        <FileInput label="Attachment (optional)" onFile={setFile} hint="PDF, Word, Excel, PowerPoint or image, up to 10 MB." />
        {entry?.attachment_url && !file && (
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4" checked={removeFile} onChange={(e) => setRemoveFile(e.target.checked)} />
            Remove current attachment
          </label>
        )}
      </div>
    </Modal>
  );
}

/** Subjects of a class for managers. */
export function useClassSubjectOpts(classId: string, enabled: boolean): SubjectOpt[] {
  const q = useQuery({ queryKey: ["class-subjects", classId], queryFn: () => api<ClassSubject[]>(`/classes/${classId}/subjects`), enabled: enabled && !!classId });
  return q.data?.map((s) => ({ value: s.subject_id, label: s.subject_name })) ?? [];
}
