"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { FormSection, humanize, SelectField, TextField, type ApiForm } from "@/components/forms";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { useClasses, useMetaOptions, useSections } from "@/lib/queries";
import type { ClassSubject, TeacherDetail } from "@/lib/types";

/** Profile keys shared by create (POST) and edit (PUT). */
export const PROFILE_KEYS = [
  "full_name", "father_name", "dob", "gender", "cnic", "phone", "emergency_contact", "blood_group", "religion",
  "designation", "qualification", "joining_date", "employment_type", "address", "city",
] as const;

export function profileValues(t?: TeacherDetail): Record<string, string> {
  return Object.fromEntries(PROFILE_KEYS.map((k) => [k, (t?.[k] as string | null | undefined) ?? ""]));
}

export function TeacherProfileFields({ form }: { form: ApiForm }) {
  const opts = useMetaOptions().data;
  return (
    <>
      <FormSection title="Personal">
        <TextField form={form} name="full_name" label="Full name" required minLength={2} maxLength={150} />
        <TextField form={form} name="father_name" label="Father's name" maxLength={150} />
        <TextField form={form} name="dob" label="Date of birth" type="date" />
        <SelectField form={form} name="gender" label="Gender" options={opts?.genders ?? []} required />
        <TextField form={form} name="cnic" label="CNIC" placeholder="00000-0000000-0" pattern="\d{5}-\d{7}-\d" required />
        <SelectField form={form} name="blood_group" label="Blood group" options={opts?.blood_groups ?? []} placeholder="Unknown" />
        <TextField form={form} name="religion" label="Religion" maxLength={64} />
      </FormSection>
      <FormSection title="Contact">
        <TextField form={form} name="phone" label="Mobile" placeholder="03XX-XXXXXXX" required />
        <TextField form={form} name="emergency_contact" label="Emergency contact" placeholder="03XX-XXXXXXX" />
        <TextField form={form} name="city" label="City" maxLength={100} />
        <TextField form={form} name="address" label="Address" maxLength={1000} className="sm:col-span-2 lg:col-span-3" />
      </FormSection>
      <FormSection title="Employment">
        <SelectField form={form} name="designation" label="Designation" options={opts?.designations ?? []} required />
        <SelectField form={form} name="qualification" label="Qualification" options={opts?.qualifications ?? []} required />
        <SelectField form={form} name="employment_type" label="Employment type" options={opts?.employment_types ?? []} required />
        <TextField form={form} name="joining_date" label="Joining date" type="date" required />
      </FormSection>
    </>
  );
}

export const SALARY_KEYS = ["basic", "house", "transport", "medical"] as const;

/** Salary components; gross is always computed by the server. */
export function SalaryFields({ form, prefix = "salary." }: { form: ApiForm; prefix?: string }) {
  const total = SALARY_KEYS.reduce((sum, k) => sum + (Number(form.values[prefix + k]) || 0), 0);
  return (
    <FormSection title="Monthly salary">
      {SALARY_KEYS.map((k) => (
        <TextField key={k} form={form} name={prefix + k} label={k === "basic" ? "Basic" : `${humanize(k)} allowance`} type="number" min={0} step="0.01" required={k === "basic"} />
      ))}
      <p className="self-end pb-2 text-sm text-muted-foreground">Gross: <span className="font-semibold tabular-nums text-foreground">{total.toLocaleString()}</span></p>
    </FormSection>
  );
}

export interface Assignment { class_id: string; section_id: string; subject_id: string }

function AssignmentRow({ value, onChange, onRemove, disabled }: { value: Assignment; onChange: (a: Assignment) => void; onRemove: () => void; disabled?: boolean }) {
  const classes = useClasses();
  const sections = useSections(value.class_id || undefined);
  const subjects = useQuery({
    queryKey: ["class-subjects", value.class_id],
    queryFn: () => api<ClassSubject[]>(`/classes/${value.class_id}/subjects`),
    enabled: !!value.class_id,
  });
  return (
    <div className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2">
      <Select aria-label="Class" value={value.class_id} disabled={disabled} onChange={(e) => onChange({ class_id: e.target.value, section_id: "", subject_id: "" })}>
        <option value="">Class...</option>
        {classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </Select>
      <Select aria-label="Section" value={value.section_id} disabled={disabled || !value.class_id} onChange={(e) => onChange({ ...value, section_id: e.target.value })}>
        <option value="">All sections</option>
        {sections.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </Select>
      <Select aria-label="Subject" value={value.subject_id} disabled={disabled || !value.class_id} onChange={(e) => onChange({ ...value, subject_id: e.target.value })}>
        <option value="">{value.class_id && subjects.data?.length === 0 ? "Class has no subjects" : "Subject..."}</option>
        {subjects.data?.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.subject_name}</option>)}
      </Select>
      {!disabled && <Button size="icon" variant="ghost" aria-label="Remove assignment" onClick={onRemove}><X className="h-4 w-4" /></Button>}
    </div>
  );
}

/** Which class/section/subject a teacher teaches. Drives teacher scoping for students, attendance and marks. */
export function AssignmentsEditor({ value, onChange, disabled, error }: { value: Assignment[]; onChange: (v: Assignment[]) => void; disabled?: boolean; error?: string }) {
  return (
    <fieldset className="rounded-lg border border-border bg-card p-4 sm:p-5">
      <legend className="px-1 text-sm font-semibold">Teaching assignments</legend>
      <div className="space-y-2">
        {value.map((a, i) => (
          <AssignmentRow key={i} value={a} disabled={disabled} onChange={(next) => onChange(value.map((x, j) => (j === i ? next : x)))} onRemove={() => onChange(value.filter((_, j) => j !== i))} />
        ))}
        {value.length === 0 && <p className="text-sm text-muted-foreground">No classes assigned. The teacher won&apos;t see any students until assigned.</p>}
        {error ? <p className="text-xs text-danger" role="alert">{error}</p> : null}
      </div>
      {!disabled && <Button variant="outline" size="sm" className="mt-3" onClick={() => onChange([...value, { class_id: "", section_id: "", subject_id: "" }])}><Plus className="h-4 w-4" />Add assignment</Button>}
    </fieldset>
  );
}

export const assignmentsBody = (rows: Assignment[]) =>
  rows.filter((a) => a.class_id && a.subject_id).map((a) => ({ class_id: a.class_id, section_id: a.section_id || null, subject_id: a.subject_id }));
