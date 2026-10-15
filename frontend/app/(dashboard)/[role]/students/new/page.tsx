"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormSection, TextField, useApiForm } from "@/components/forms";
import { CredentialsModal, type ShownCredential } from "@/components/modals/credentials-modal";
import { PageHeader } from "@/components/page-header";
import { GUARDIAN_KEYS, StudentFields, studentBody, studentValues } from "@/components/students/student-fields";
import { Button } from "@/components/ui/button";
import { AccessDenied } from "@/components/ui/state-views";
import { useDebounce } from "@/hooks/use-debounce";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cnicSchema } from "@/lib/schemas/common";
import type { GuardianLookup, StudentCreated } from "@/lib/types";

export default function NewStudentPage() {
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const form = useApiForm({ ...studentValues(), admission_date: new Date().toISOString().slice(0, 10), discount_percent: "0" });
  const [studentLogin, setStudentLogin] = useState(false);
  const [done, setDone] = useState<{ id: string; creds: ShownCredential[]; note?: string } | null>(null);

  // "Existing guardian found": siblings reuse one guardian record and one parent login.
  const cnic = useDebounce(form.values["guardian.father_cnic"] ?? "");
  const lookup = useQuery({
    queryKey: ["guardian-lookup", cnic],
    queryFn: () => api<GuardianLookup>("/students/guardian-lookup", { query: { father_cnic: cnic } }),
    enabled: cnicSchema.safeParse(cnic).success,
  });
  const found = lookup.data?.found ? lookup.data : null;
  useEffect(() => {
    if (!found?.guardian) return;
    for (const k of GUARDIAN_KEYS) {
      const v = found.guardian[k];
      if (v && !form.values[`guardian.${k}`]) form.set(`guardian.${k}`, v);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- prefill once per lookup result
  }, [found]);

  const register = useMutation({
    mutationFn: () => api<StudentCreated>("/students", { method: "POST", body: { ...studentBody(form, { withCnic: true }), discount_percent: form.values.discount_percent || "0", create_student_login: studentLogin } }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["students"] });
      qc.invalidateQueries({ queryKey: ["classes"] });
      res.warnings.forEach((w) => toast.warning(w));
      const { parent, student } = res.credentials;
      const creds: ShownCredential[] = [];
      if (parent) creds.push({ label: "Parent", ...parent });
      if (student) creds.push({ label: res.student.full_name, ...student });
      const note = "They must change the password at first sign-in." + (parent ? "" : " The family already has a parent login; this child was added to it.");
      if (creds.length) setDone({ id: res.student.id, creds, note });
      else { toast.success(`${res.student.full_name} registered (roll no. ${res.student.roll_no})`); router.push(`/${user?.role}/students/${res.student.id}`); }
    },
    onError: (e) => { form.showErrors(e); toast.error(errorText(e, "Couldn't register the student")); },
  });

  if (user && user.role !== "admin") return <AccessDenied />;
  const submit = (e: FormEvent) => { e.preventDefault(); register.mutate(); };
  const guardianNote = found ? (
    <div className="flex gap-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
      <Users className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p><span className="font-semibold">Existing guardian found.</span> {found.children.length ? `Already linked: ${found.children.join(", ")}. ` : ""}This student will be added to the same family and parent login.</p>
    </div>
  ) : null;
  return (
    <>
      <Link href={`/${user?.role}/students`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />All students</Link>
      <PageHeader title="Register student" description="Assigns a roll number, links the guardian and parent login, and creates the year's fee ledger." />
      <form onSubmit={submit} className="space-y-5">
        <StudentFields form={form} guardianNote={guardianNote} />
        <FormSection title="Fees & login">
          <TextField form={form} name="discount_percent" label="Fee discount (%)" type="number" min={0} max={100} step="0.01" />
          <label className="flex min-h-[44px] items-center gap-2 self-end text-sm">
            <input type="checkbox" checked={studentLogin} onChange={(e) => setStudentLogin(e.target.checked)} />Create a login for the student too
          </label>
        </FormSection>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
          <Button type="submit" loading={register.isPending}>Register student</Button>
        </div>
      </form>
      {done && <CredentialsModal credentials={done.creds} note={done.note} onDone={() => router.push(`/${user?.role}/students/${done.id}`)} />}
    </>
  );
}
