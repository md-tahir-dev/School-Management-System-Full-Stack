"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { humanize, useApiForm } from "@/components/forms";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { StudentFields, studentBody, studentValues } from "@/components/students/student-fields";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMetaOptions } from "@/lib/queries";
import type { StudentDetail } from "@/lib/types";

/** Profile, status, discount and photo. Admin edits; everyone else who can open the profile sees it read-only. */
export function StudentProfileTab({ student: s }: { student: StudentDetail }) {
  const { user } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const canEdit = user?.role === "admin";
  const statuses = useMetaOptions().data?.student_statuses ?? [];
  const form = useApiForm(studentValues(s));
  const [status, setStatus] = useState<string>(s.status);
  const [reason, setReason] = useState(s.status_reason ?? "");
  const [discount, setDiscount] = useState(String(Number(s.discount_percent)));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const photoRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    form.reset(studentValues(s));
    setStatus(s.status); setReason(s.status_reason ?? ""); setDiscount(String(Number(s.discount_percent)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the server copy changes
  }, [s]);

  const saved = (msg: string) => { toast.success(msg); qc.invalidateQueries({ queryKey: ["student", s.id] }); qc.invalidateQueries({ queryKey: ["students"] }); };
  const save = useMutation({
    mutationFn: () => api(`/students/${s.id}`, { method: "PUT", body: studentBody(form, { withCnic: false }) }),
    onSuccess: () => saved("Profile saved"),
    onError: (e) => { form.showErrors(e); toast.error(errorText(e, "Couldn't save")); },
  });
  const saveStatus = useMutation({
    mutationFn: () => api(`/students/${s.id}/status`, { method: "PUT", body: { status, reason } }),
    onSuccess: () => saved("Status changed"),
    onError: (e) => toast.error(errorText(e, "Couldn't change status")),
  });
  const saveDiscount = useMutation({
    mutationFn: () => api<{ recalculated_rows: number }>(`/students/${s.id}/discount`, { method: "PUT", body: { discount_percent: discount || "0" } }),
    onSuccess: (r) => saved(`Discount saved; ${r.recalculated_rows} unpaid month(s) recalculated`),
    onError: (e) => toast.error(errorText(e, "Couldn't change discount")),
  });
  const photo = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api(`/students/${s.id}/photo`, { method: "POST", body: fd }); },
    onSuccess: () => saved("Photo updated"),
    onError: (e) => toast.error(errorText(e, "Couldn't upload the photo")),
  });
  const remove = async () => {
    try {
      await api(`/students/${s.id}`, { method: "DELETE" });
      toast.success("Student removed");
      qc.invalidateQueries({ queryKey: ["students"] });
      router.push(`/${user?.role}/students`);
    } catch (e) { toast.error(errorText(e, "Couldn't remove")); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };

  return (
    <div className="space-y-5">
      {canEdit && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="flex items-center gap-3 p-4">
            {s.photo_url
              // eslint-disable-next-line @next/next/no-img-element -- uploaded photo served by the API
              ? <img src={s.photo_url} alt="" className="h-14 w-14 rounded-full object-cover" />
              : <span className="h-14 w-14 rounded-full bg-muted" aria-hidden />}
            <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Photo file" onChange={(e) => { const f = e.target.files?.[0]; if (f) photo.mutate(f); e.target.value = ""; }} />
            <Button variant="outline" size="sm" loading={photo.isPending} onClick={() => photoRef.current?.click()}><Camera className="h-4 w-4" />Change photo</Button>
          </Card>
          <Card className="space-y-2 p-4">
            <Field label="Status">
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>{statuses.map((x) => <option key={x} value={x}>{humanize(x)}</option>)}</Select>
            </Field>
            {status !== "active" && <Input aria-label="Reason" placeholder={status === "expelled" ? "Reason (required)" : "Reason (optional)"} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />}
            <Button size="sm" onClick={() => saveStatus.mutate()} loading={saveStatus.isPending} disabled={status === s.status && reason === (s.status_reason ?? "")}>Update status</Button>
          </Card>
          <Card className="space-y-2 p-4">
            <Field label="Fee discount (%)" hint="Recalculates unpaid months only."><Input type="number" min={0} max={100} step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} /></Field>
            <Button size="sm" onClick={() => saveDiscount.mutate()} loading={saveDiscount.isPending} disabled={Number(discount) === Number(s.discount_percent) || Number(discount) < 0 || Number(discount) > 100}>Save discount</Button>
          </Card>
        </div>
      )}
      <form onSubmit={submit} className="space-y-5">
        <fieldset disabled={!canEdit} className="space-y-5"><StudentFields form={form} cnicLocked /></fieldset>
        {canEdit && (
          <div className="flex justify-between gap-2">
            <Button type="button" variant="outline" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4 text-danger" />Remove student</Button>
            <Button type="submit" loading={save.isPending}>Save profile</Button>
          </div>
        )}
      </form>
      <ConfirmDialog open={confirmDelete} onOpenChange={setConfirmDelete} title={`Remove ${s.full_name}?`} description="They disappear from lists and rosters. Attendance, results and fee history are kept. To keep them visible, change the status instead." confirmLabel="Remove student" destructive onConfirm={remove} />
    </div>
  );
}
