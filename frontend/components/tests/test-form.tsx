"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { TextAreaField } from "@/components/diary/common";
import { useClassSubjectOpts } from "@/components/diary/entry-form";
import { Button } from "@/components/ui/button";
import { api, errorText } from "@/lib/api";
import { useClasses, useMyTeacher, useSections } from "@/lib/queries";
import type { Role, TestDetail, TestOut } from "@/lib/types";

const pad = (n: number) => String(n).padStart(2, "0");
/** ISO -> value for <input type="datetime-local"> in the browser's timezone. */
export function toLocalInput(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
/** datetime-local value -> ISO with explicit timezone (UTC instant). */
const toIso = (v: string) => (v ? new Date(v).toISOString() : "");

export function whenLabel(iso: string | null | undefined) {
  return iso ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso)) : "-";
}

const blank = { title: "", class_id: "", section_id: "", subject_id: "", instructions: "", time_limit_min: "30", start_at: "", end_at: "", one_by_one: "" };

export function TestForm({ role, test, readOnly, onSaved }: { role: Role; test?: TestOut; readOnly?: boolean; onSaved?: (t: TestDetail) => void }) {
  const qc = useQueryClient();
  const isTeacher = role === "teacher";
  const form = useApiForm(blank);
  const { reset } = form;
  useEffect(() => {
    reset(test ? {
      title: test.title, class_id: test.class_id, section_id: test.section_id ?? "", subject_id: test.subject_id, instructions: test.instructions ?? "",
      time_limit_min: String(test.time_limit_min), start_at: toLocalInput(test.start_at), end_at: toLocalInput(test.end_at), one_by_one: test.show_one_by_one ? "1" : "",
    } : blank);
  }, [test, reset]);

  const me = useMyTeacher();
  const allClasses = useClasses();
  const assigns = useMemo(() => me.data?.assignments ?? [], [me.data]);
  const cid = form.values.class_id ?? "";
  const sid = form.values.section_id ?? "";
  const classes = useMemo(() => {
    if (!isTeacher) return (allClasses.data ?? []).map((c) => ({ value: c.id, label: c.name }));
    const m = new Map<string, string>();
    assigns.forEach((a) => m.set(a.class_id, a.class_name));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [isTeacher, allClasses.data, assigns]);
  const secQ = useSections(cid || undefined);
  const sections = useMemo(() => {
    const all = secQ.data ?? [];
    if (!isTeacher) return all;
    const mine = assigns.filter((a) => a.class_id === cid);
    return mine.some((a) => !a.section_id) ? all : all.filter((s) => mine.some((a) => a.section_id === s.id));
  }, [secQ.data, isTeacher, assigns, cid]);
  const mgrSubjects = useClassSubjectOpts(cid, !isTeacher);
  const subjects = useMemo(() => {
    if (!isTeacher) return mgrSubjects;
    const m = new Map<string, string>();
    assigns.filter((a) => a.class_id === cid && (!a.section_id || !sid || a.section_id === sid)).forEach((a) => m.set(a.subject_id, a.subject_name));
    return [...m].map(([value, label]) => ({ value, label }));
  }, [isTeacher, mgrSubjects, assigns, cid, sid]);

  const save = useMutation({
    mutationFn: () => {
      const v = { ...blank, ...form.values };
      const body = {
        title: v.title.trim(), subject_id: v.subject_id, class_id: v.class_id, section_id: v.section_id || null,
        instructions: v.instructions.trim() || null, time_limit_min: Number(v.time_limit_min),
        start_at: toIso(v.start_at), end_at: toIso(v.end_at), show_one_by_one: !!v.one_by_one,
      };
      return api<TestDetail>(test ? `/tests/${test.id}` : "/tests", { method: test ? "PUT" : "POST", body });
    },
    onSuccess: (t) => { toast.success(test ? "Test updated" : "Test created"); qc.invalidateQueries({ queryKey: ["tests"] }); onSaved?.(t); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't save test")); },
  });

  const v = { ...blank, ...form.values };
  const ok = v.title.trim() && v.class_id && v.subject_id && v.start_at && v.end_at && Number(v.time_limit_min) > 0;
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <fieldset disabled={readOnly} className="space-y-4">
        <TextField form={form} name="title" label="Title" maxLength={200} />
        <div className="grid gap-4 sm:grid-cols-3">
          <SelectField form={form} name="class_id" label="Class" options={classes} onValue={() => { form.set("section_id", ""); form.set("subject_id", ""); }} />
          <SelectField form={form} name="section_id" label="Section" placeholder={isTeacher && sections.length ? "Select section" : "Whole class"} options={sections.map((s) => ({ value: s.id, label: s.name }))} />
          <SelectField form={form} name="subject_id" label="Subject" options={subjects} />
        </div>
        <TextAreaField label="Instructions (optional)" rows={3} value={v.instructions} onChange={(x) => form.set("instructions", x)} error={form.errors.instructions} />
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField form={form} name="time_limit_min" label="Time limit (minutes)" type="number" min={1} max={600} />
          <TextField form={form} name="start_at" label="Opens" type="datetime-local" />
          <TextField form={form} name="end_at" label="Closes" type="datetime-local" />
        </div>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4" checked={!!v.one_by_one} onChange={(e) => form.set("one_by_one", e.target.checked ? "1" : "")} />
          Show one question at a time
        </label>
      </fieldset>
      {!readOnly && <Button type="submit" loading={save.isPending} disabled={!ok}>{test ? "Save changes" : "Create test"}</Button>}
    </form>
  );
}
