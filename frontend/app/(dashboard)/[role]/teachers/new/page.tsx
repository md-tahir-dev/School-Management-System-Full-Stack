"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApiForm } from "@/components/forms";
import { CredentialsModal } from "@/components/modals/credentials-modal";
import { PageHeader } from "@/components/page-header";
import { AssignmentsEditor, assignmentsBody, profileValues, SALARY_KEYS, SalaryFields, TeacherProfileFields, type Assignment } from "@/components/teachers/teacher-fields";
import { Button } from "@/components/ui/button";
import { AccessDenied } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TeacherCreated } from "@/lib/types";

export default function NewTeacherPage() {
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const form = useApiForm({ ...profileValues(), "salary.basic": "", "salary.house": "0", "salary.transport": "0", "salary.medical": "0" });
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [created, setCreated] = useState<TeacherCreated | null>(null);

  const register = useMutation({
    mutationFn: () => {
      const { values, pick } = form;
      const profile = Object.fromEntries(Object.entries(values).filter(([k]) => !k.startsWith("salary.")));
      const salary = Object.fromEntries(SALARY_KEYS.map((k) => [k, pick("salary")[k] || "0"]));
      return api<TeacherCreated>("/teachers", { method: "POST", body: { ...profile, salary, assignments: assignmentsBody(assignments) } });
    },
    onSuccess: (res) => { qc.invalidateQueries({ queryKey: ["teachers"] }); setCreated(res); },
    onError: (e) => { form.showErrors(e); toast.error(errorText(e, "Couldn't register the teacher")); },
  });

  if (user && user.role !== "admin") return <AccessDenied />;
  const submit = (e: FormEvent) => { e.preventDefault(); register.mutate(); };
  const assignmentError = Object.entries(form.errors).find(([k, v]) => k.startsWith("assignments") && v)?.[1];
  return (
    <>
      <Link href={`/${user?.role}/teachers`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />All teachers</Link>
      <PageHeader title="Register teacher" description="Creates the profile, a login with a temporary password, the salary structure and teaching assignments in one step." />
      <form onSubmit={submit} className="space-y-5">
        <TeacherProfileFields form={form} />
        <SalaryFields form={form} />
        <AssignmentsEditor value={assignments} onChange={setAssignments} error={assignmentError} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>Cancel</Button>
          <Button type="submit" loading={register.isPending}>Register teacher</Button>
        </div>
      </form>
      {created && (
        <CredentialsModal credentials={[{ label: created.teacher.full_name, ...created.credentials.teacher }]}
          onDone={() => router.push(`/${user?.role}/teachers/${created.teacher.id}`)} />
      )}
    </>
  );
}
