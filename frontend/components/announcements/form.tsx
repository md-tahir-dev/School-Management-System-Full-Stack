"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errorText } from "@/lib/api";
import { useClasses, useMyTeacher, useSections } from "@/lib/queries";
import type { Announcement, AnnouncementIn, Role } from "@/lib/types";

const EMPTY = { title: "", message: "", audience: "all", priority: "normal", class_id: "", section_id: "" };

export function AnnouncementForm({ open, onClose, role }: { open: boolean; onClose: () => void; role: Role }) {
  const qc = useQueryClient();
  const teacher = role === "teacher";
  const form = useApiForm(EMPTY);
  const { reset } = form;
  useEffect(() => { if (open) reset(EMPTY); }, [open, reset]);

  const me = useMyTeacher();
  const classes = useClasses();
  const classId = form.values.class_id ?? "";
  const sections = useSections(teacher ? undefined : classId || undefined);

  // Teachers: only the classes/sections they are assigned to.
  const pairs = useMemo(() => {
    const seen = new Map<string, { class_id: string; class_name: string; section_id: string | null; section_name: string | null }>();
    for (const a of me.data?.assignments ?? []) seen.set(`${a.class_id}/${a.section_id}`, a);
    return [...seen.values()];
  }, [me.data]);
  const classOpts = teacher
    ? [...new Map(pairs.map((p) => [p.class_id, p.class_name])).entries()].map(([value, label]) => ({ value, label }))
    : (classes.data ?? []).map((c) => ({ value: c.id, label: c.name }));
  const sectionOpts = teacher
    ? pairs.filter((p) => p.class_id === classId && p.section_id).map((p) => ({ value: p.section_id as string, label: p.section_name ?? "" }))
    : (sections.data ?? []).map((s) => ({ value: s.id, label: s.name }));
  const audiences = teacher ? ["all", "students", "parents"] : ["all", "teachers", "students", "parents"];
  const v = (k: string) => form.values[k] ?? "";

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: v("title").trim(), message: v("message").trim(), audience: v("audience"), priority: v("priority"),
        class_id: v("class_id") || null, section_id: v("class_id") && v("section_id") ? v("section_id") : null,
      } as AnnouncementIn;
      return api<Announcement>("/announcements", { method: "POST", body });
    },
    onSuccess: () => { toast.success("Announcement posted"); qc.invalidateQueries({ queryKey: ["announcements"] }); onClose(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't post announcement")); },
  });

  return (
    <Modal
      open={open}
      onOpenChange={(o) => !o && onClose()}
      title="New announcement"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!v("title").trim() || !v("message").trim() || (teacher && !classId)}>Post</Button>
        </>
      }
    >
      <div className="space-y-4">
        <TextField form={form} name="title" label="Title" maxLength={200} />
        <div className="flex flex-col gap-1.5 text-sm">
          <label htmlFor="ann-message" className="font-medium">Message</label>
          <Textarea id="ann-message" rows={5} value={v("message")} aria-invalid={!!form.errors.message} onChange={(e) => form.set("message", e.target.value)} />
          {form.errors.message && <span className="text-xs text-danger" role="alert">{form.errors.message}</span>}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField form={form} name="audience" label="Audience" options={audiences} placeholder="Everyone" />
          <SelectField form={form} name="priority" label="Priority" options={["normal", "important"]} />
          <SelectField form={form} name="class_id" label="Class" options={classOpts} placeholder={teacher ? "Select class..." : "Whole school"} onValue={() => form.set("section_id", "")} />
          {classId && (sectionOpts.length > 0 || teacher) && (
            <SelectField form={form} name="section_id" label="Section" options={sectionOpts} placeholder={teacher ? "Select section..." : "All sections"} />
          )}
        </div>
      </div>
    </Modal>
  );
}
