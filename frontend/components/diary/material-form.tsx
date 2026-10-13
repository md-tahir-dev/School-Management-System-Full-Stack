"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { api, errorText } from "@/lib/api";
import { useClasses, useMyTeacher, useSections } from "@/lib/queries";
import type { Material } from "@/lib/types";
import { FileInput, TextAreaField } from "./common";
import { useClassSubjectOpts } from "./entry-form";

export const MATERIAL_TYPES = ["notes", "past_paper", "assignment", "reference"] as const;
const INIT = { title: "", type: "notes", class_id: "", section_id: "", subject_id: "", external_link: "", description: "" };

export function MaterialForm({ open, onClose, isTeacher }: { open: boolean; onClose: () => void; isTeacher: boolean }) {
  const qc = useQueryClient();
  const form = useApiForm(INIT);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const me = useMyTeacher();
  const allClasses = useClasses();
  const assigns = me.data?.assignments;
  const cid = form.values.class_id ?? "";
  const sections = useSections(cid || undefined);
  const classOpts = useMemo(() => {
    if (!isTeacher) return (allClasses.data ?? []).map((c) => ({ value: c.id, label: c.name }));
    const m = new Map<string, string>();
    (assigns ?? []).forEach((a) => m.set(a.class_id, a.class_name));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [isTeacher, allClasses.data, assigns]);
  const mgrSubjects = useClassSubjectOpts(cid, !isTeacher);
  const subjectOpts = useMemo(() => {
    if (!isTeacher) return mgrSubjects;
    const m = new Map<string, string>();
    (assigns ?? []).filter((a) => a.class_id === cid && (!a.section_id || !form.values.section_id || a.section_id === form.values.section_id)).forEach((a) => m.set(a.subject_id, a.subject_name));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [isTeacher, mgrSubjects, assigns, cid, form.values.section_id]);

  const val = (k: string) => form.values[k] ?? "";
  const { reset } = form;
  useEffect(() => { if (open) { reset(INIT); setFile(null); setFileKey((k) => k + 1); } }, [open, reset]);

  const save = useMutation({
    mutationFn: () => {
      const v = val;
      const fd = new FormData();
      fd.append("title", v("title").trim());
      fd.append("type", v("type"));
      fd.append("class_id", v("class_id"));
      for (const k of ["section_id", "subject_id", "description", "external_link"] as const) if (v(k).trim()) fd.append(k, v(k).trim());
      if (file) fd.append("file", file);
      return api<Material>("/materials", { method: "POST", body: fd });
    },
    onSuccess: () => { toast.success("Material uploaded"); qc.invalidateQueries({ queryKey: ["materials"] }); onClose(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't upload material")); },
  });

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="Upload material"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!val("title").trim() || !val("class_id") || (!file && !val("external_link").trim()) || (isTeacher && !val("subject_id"))}>Upload</Button>
        </>
      }
    >
      <div className="space-y-4">
        <TextField form={form} name="title" label="Title" maxLength={200} />
        <SelectField form={form} name="type" label="Type" options={[...MATERIAL_TYPES]} />
        <SelectField form={form} name="class_id" label="Class" options={classOpts} onValue={() => { form.set("section_id", ""); form.set("subject_id", ""); }} />
        {!!sections.data?.length && <SelectField form={form} name="section_id" label="Section" placeholder="All sections" options={sections.data.map((s) => ({ value: s.id, label: s.name }))} />}
        <SelectField form={form} name="subject_id" label={isTeacher ? "Subject" : "Subject (optional)"} options={subjectOpts} />
        <TextAreaField label="Description (optional)" rows={3} value={val("description")} onChange={(v) => form.set("description", v)} error={form.errors.description} />
        <FileInput key={fileKey} label="File" onFile={setFile} hint="PDF, Word, Excel, PowerPoint or image, up to 10 MB." />
        <TextField form={form} name="external_link" label="Or link (optional)" type="url" placeholder="https://" />
      </div>
    </Modal>
  );
}
