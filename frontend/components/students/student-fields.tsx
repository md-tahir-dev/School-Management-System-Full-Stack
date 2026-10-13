"use client";

import { FormSection, SelectField, TextField, type ApiForm } from "@/components/forms";
import { useClasses, useMetaOptions, useSections } from "@/lib/queries";
import type { StudentDetail } from "@/lib/types";

export const STUDENT_KEYS = [
  "full_name", "dob", "gender", "religion", "nationality", "blood_group", "class_id", "section_id",
  "admission_date", "previous_school", "address", "city", "emergency_name", "emergency_phone",
] as const;
export const GUARDIAN_KEYS = [
  "father_name", "father_cnic", "father_phone", "father_occupation", "mother_name", "mother_cnic", "mother_phone",
  "guardian_name", "guardian_phone", "guardian_relation",
] as const;

export function studentValues(s?: StudentDetail): Record<string, string> {
  const own = STUDENT_KEYS.map((k) => [k, (s?.[k] as string | null | undefined) ?? ""]);
  const guardian = GUARDIAN_KEYS.map((k) => [`guardian.${k}`, s?.guardian?.[k] ?? ""]);
  return Object.fromEntries([...own, ...guardian]);
}

/** Student fields as the API body: own fields plus a nested `guardian` (father CNIC excluded on edit, it is the identity key). */
export function studentBody(form: ApiForm, { withCnic }: { withCnic: boolean }) {
  const own = Object.fromEntries(STUDENT_KEYS.map((k) => [k, form.values[k] ?? ""]));
  const guardian = form.pick("guardian");
  if (!withCnic) delete guardian.father_cnic;
  return { ...own, guardian };
}

export function StudentFields({ form, cnicLocked = false, guardianNote }: { form: ApiForm; cnicLocked?: boolean; guardianNote?: React.ReactNode }) {
  const opts = useMetaOptions().data;
  const classes = useClasses();
  const sections = useSections(form.values.class_id || undefined);
  return (
    <>
      <FormSection title="Student">
        <TextField form={form} name="full_name" label="Full name" required minLength={2} maxLength={150} />
        <TextField form={form} name="dob" label="Date of birth" type="date" required />
        <SelectField form={form} name="gender" label="Gender" options={opts?.genders ?? []} required />
        <SelectField form={form} name="blood_group" label="Blood group" options={opts?.blood_groups ?? []} placeholder="Unknown" />
        <TextField form={form} name="religion" label="Religion" maxLength={64} />
        <TextField form={form} name="nationality" label="Nationality" maxLength={64} />
      </FormSection>
      <FormSection title="Admission">
        <SelectField form={form} name="class_id" label="Class" required options={classes.data?.map((c) => ({ value: c.id, label: c.name })) ?? []} onValue={() => form.set("section_id", "")} />
        <SelectField form={form} name="section_id" label="Section" placeholder="No section" disabled={!form.values.class_id} options={sections.data?.map((s) => ({ value: s.id, label: s.name })) ?? []} />
        <TextField form={form} name="admission_date" label="Admission date" type="date" />
        <TextField form={form} name="previous_school" label="Previous school" maxLength={200} />
      </FormSection>
      <FormSection title="Father / guardian">
        {guardianNote ? <div className="sm:col-span-2 lg:col-span-3">{guardianNote}</div> : null}
        <TextField form={form} name="guardian.father_cnic" label="Father's CNIC" placeholder="00000-0000000-0" pattern="\d{5}-\d{7}-\d" required disabled={cnicLocked} hint={cnicLocked ? "Identifies the family; can't be changed." : "Siblings share one guardian and one parent login."} />
        <TextField form={form} name="guardian.father_name" label="Father's name" required minLength={2} maxLength={150} />
        <TextField form={form} name="guardian.father_phone" label="Father's mobile" placeholder="03XX-XXXXXXX" required />
        <TextField form={form} name="guardian.father_occupation" label="Father's occupation" maxLength={100} />
        <TextField form={form} name="guardian.mother_name" label="Mother's name" maxLength={150} />
        <TextField form={form} name="guardian.mother_cnic" label="Mother's CNIC" placeholder="00000-0000000-0" pattern="\d{5}-\d{7}-\d" />
        <TextField form={form} name="guardian.mother_phone" label="Mother's mobile" placeholder="03XX-XXXXXXX" />
        <TextField form={form} name="guardian.guardian_name" label="Other guardian" maxLength={150} />
        <TextField form={form} name="guardian.guardian_relation" label="Relation" maxLength={64} />
        <TextField form={form} name="guardian.guardian_phone" label="Guardian's mobile" placeholder="03XX-XXXXXXX" />
      </FormSection>
      <FormSection title="Address & emergency">
        <TextField form={form} name="address" label="Address" maxLength={1000} className="sm:col-span-2" />
        <TextField form={form} name="city" label="City" maxLength={100} />
        <TextField form={form} name="emergency_name" label="Emergency contact" maxLength={150} />
        <TextField form={form} name="emergency_phone" label="Emergency mobile" placeholder="03XX-XXXXXXX" />
      </FormSection>
    </>
  );
}
