"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Camera, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { humanize, useApiForm } from "@/components/forms";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { AssignmentsEditor, assignmentsBody, profileValues, SALARY_KEYS, SalaryFields, TeacherProfileFields, type Assignment } from "@/components/teachers/teacher-fields";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { AccessDenied, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api, ApiError, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";
import type { TeacherDetail } from "@/lib/types";
import { initials } from "@/lib/utils";

type Tab = "profile" | "assignments" | "salary";

/** Admin edits; CEO and Headmaster see the same screens read-only (a disabled fieldset). */
export default function TeacherProfile({ params }: { params: { id: string } }) {
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const canEdit = user?.role === "admin";
  const allowed = isSchoolWide(user?.role);
  const [tab, setTab] = useState<Tab>("profile");
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [confirm, setConfirm] = useState<"delete" | "force" | null>(null);
  const [soleMessage, setSoleMessage] = useState("");
  const photoRef = useRef<HTMLInputElement>(null);
  const profile = useApiForm(profileValues());
  const salary = useApiForm(Object.fromEntries(SALARY_KEYS.map((k) => [k, "0"])));

  const q = useQuery({ queryKey: ["teacher", params.id], queryFn: () => api<TeacherDetail>(`/teachers/${params.id}`), enabled: allowed });
  const t = q.data;
  useEffect(() => {
    if (!t) return;
    profile.reset(profileValues(t));
    salary.reset(Object.fromEntries(SALARY_KEYS.map((k) => [k, String(Number(t.salary_structure?.[k] ?? 0))])));
    setAssignments(t.assignments.map((a) => ({ class_id: a.class_id, section_id: a.section_id ?? "", subject_id: a.subject_id })));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the server copy changes
  }, [t]);

  const saved = (msg: string) => { toast.success(msg); qc.invalidateQueries({ queryKey: ["teacher", params.id] }); qc.invalidateQueries({ queryKey: ["teachers"] }); };
  const saveProfile = useMutation({
    mutationFn: () => api(`/teachers/${params.id}`, { method: "PUT", body: profile.values }),
    onSuccess: () => saved("Profile saved"),
    onError: (e) => { profile.showErrors(e); toast.error(errorText(e, "Couldn't save")); },
  });
  const saveAssignments = useMutation({
    mutationFn: () => api(`/teachers/${params.id}/assignments`, { method: "PUT", body: assignmentsBody(assignments) }),
    onSuccess: () => saved("Assignments saved"),
    onError: (e) => toast.error(errorText(e, "Couldn't save assignments")),
  });
  const saveSalary = useMutation({
    mutationFn: () => api(`/teachers/${params.id}/salary-structure`, { method: "PUT", body: Object.fromEntries(SALARY_KEYS.map((k) => [k, salary.values[k] || "0"])) }),
    onSuccess: () => saved("Salary saved"),
    onError: (e) => { salary.showErrors(e); toast.error(errorText(e, "Couldn't save salary")); },
  });
  const photo = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api(`/teachers/${params.id}/photo`, { method: "POST", body: fd }); },
    onSuccess: () => saved("Photo updated"),
    onError: (e) => toast.error(errorText(e, "Couldn't upload the photo")),
  });
  const remove = async (force: boolean) => {
    try {
      await api(`/teachers/${params.id}`, { method: "DELETE", query: { force } });
      toast.success("Teacher removed");
      qc.invalidateQueries({ queryKey: ["teachers"] });
      router.push(`/${user?.role}/teachers`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "SOLE_TEACHER") { setSoleMessage(e.message); setConfirm("force"); return; }
      toast.error(errorText(e, "Couldn't remove"));
    }
  };

  if (user && !allowed) return <AccessDenied />;
  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error || !t) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const onSubmit = (m: { mutate: () => void }) => (e: FormEvent) => { e.preventDefault(); m.mutate(); };

  return (
    <PageBoundary>
      <Link href={`/${user?.role}/teachers`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />All teachers</Link>
      <PageHeader title={t.full_name} description={`${t.employee_id}${t.designation ? ` · ${humanize(t.designation)}` : ""}`}
        actions={canEdit ? <Button variant="outline" onClick={() => setConfirm("delete")}><Trash2 className="h-4 w-4 text-danger" />Remove</Button> : undefined} />
      <div className="mb-5 flex items-center gap-4">
        {t.photo_url
          // eslint-disable-next-line @next/next/no-img-element -- uploaded photo served by the API
          ? <img src={t.photo_url} alt="" className="h-16 w-16 rounded-full object-cover" />
          : <span className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-lg font-bold text-primary">{initials(t.full_name)}</span>}
        {canEdit && <>
          <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Photo file" onChange={(e) => { const f = e.target.files?.[0]; if (f) photo.mutate(f); e.target.value = ""; }} />
          <Button variant="outline" size="sm" loading={photo.isPending} onClick={() => photoRef.current?.click()}><Camera className="h-4 w-4" />Change photo</Button>
        </>}
      </div>
      <Tabs label="Teacher sections" value={tab} onChange={setTab} tabs={[{ key: "profile", label: "Profile" }, { key: "assignments", label: "Assignments" }, { key: "salary", label: "Salary" }]} />
      {tab === "profile" && (
        <form onSubmit={onSubmit(saveProfile)} className="space-y-5">
          <fieldset disabled={!canEdit} className="space-y-5"><TeacherProfileFields form={profile} /></fieldset>
          {canEdit && <div className="flex justify-end"><Button type="submit" loading={saveProfile.isPending}>Save profile</Button></div>}
        </form>
      )}
      {tab === "assignments" && (
        <div className="space-y-4">
          <AssignmentsEditor value={assignments} onChange={setAssignments} disabled={!canEdit} />
          {canEdit && <div className="flex justify-end"><Button onClick={() => saveAssignments.mutate()} loading={saveAssignments.isPending}>Save assignments</Button></div>}
        </div>
      )}
      {tab === "salary" && (
        <form onSubmit={onSubmit(saveSalary)} className="space-y-4">
          <fieldset disabled={!canEdit}><SalaryFields form={salary} prefix="" /></fieldset>
          {canEdit && <div className="flex justify-end"><Button type="submit" loading={saveSalary.isPending}>Save salary</Button></div>}
        </form>
      )}
      <ConfirmDialog open={confirm === "delete"} onOpenChange={(o) => !o && setConfirm((c) => (c === "delete" ? null : c))} title={`Remove ${t.full_name}?`} description="Their login is disabled and they disappear from lists. Past attendance and marks are kept." confirmLabel="Remove teacher" destructive onConfirm={() => remove(false)} />
      <ConfirmDialog open={confirm === "force"} onOpenChange={(o) => !o && setConfirm((c) => (c === "force" ? null : c))} title="They're the only teacher for some classes" description={`${soleMessage.split(" Assign")[0]} Those class subjects will have no teacher until you assign one.`} confirmLabel="Remove anyway" destructive onConfirm={() => remove(true)} />
    </PageBoundary>
  );
}
