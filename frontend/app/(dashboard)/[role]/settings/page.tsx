"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { AccessDenied, EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, WEEKDAYS } from "@/lib/format";
import { useSettings } from "@/lib/queries";
import type { Holiday, Page } from "@/lib/types";

function Holidays() {
  const qc = useQueryClient();
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [date, setDate] = useState("");
  const [name, setName] = useState("");
  const [toDelete, setToDelete] = useState<Holiday | null>(null);
  const q = useQuery({ queryKey: ["holidays", year], queryFn: () => api<Page<Holiday>>("/holidays", { query: { year, page_size: 100 } }) });
  const add = useMutation({
    mutationFn: () => api<Holiday>("/holidays", { method: "POST", body: { date, name: name.trim() } }),
    onSuccess: () => { toast.success("Holiday added"); setDate(""); setName(""); qc.invalidateQueries({ queryKey: ["holidays"] }); qc.invalidateQueries({ queryKey: ["attendance-roster"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't add"),
  });
  const del = useMutation({
    mutationFn: (id: string) => api<void>(`/holidays/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Holiday removed"); qc.invalidateQueries({ queryKey: ["holidays"] }); qc.invalidateQueries({ queryKey: ["attendance-roster"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't remove"),
  });
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-[10rem_1fr_auto] sm:items-end">
        <Field label="Date"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Name"><Input value={name} maxLength={150} placeholder="e.g. Independence Day" onChange={(e) => setName(e.target.value)} /></Field>
        <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!date || !name.trim()}><Plus className="h-4 w-4" />Add holiday</Button>
      </Card>
      <Field label="Year"><Input type="number" className="w-28" value={year} onChange={(e) => setYear(e.target.value)} /></Field>
      {q.isLoading ? <ListSkeleton rows={4} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data?.items.length === 0 ? <EmptyState title={`No holidays in ${year}`} /> : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {q.data?.items.map((h) => (
            <li key={h.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <span className="w-32 font-medium tabular-nums">{dateLabel(h.date)}</span><span className="flex-1">{h.name}</span>
              <Button variant="ghost" size="icon" aria-label={`Delete ${h.name}`} onClick={() => setToDelete(h)}><Trash2 className="h-4 w-4 text-danger" /></Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title="Remove this holiday?" description={`${toDelete?.name ?? ""} will become a normal school day.`} confirmLabel="Remove holiday" destructive onConfirm={async () => { if (toDelete) await del.mutateAsync(toDelete.id).catch(() => undefined); }} />
    </div>
  );
}

function Rules() {
  const qc = useQueryClient();
  const s = useSettings();
  const [off, setOff] = useState<number[]>([]);
  const [threshold, setThreshold] = useState("75");
  const [backdate, setBackdate] = useState("7");
  const [failRule, setFailRule] = useState(true);
  useEffect(() => {
    if (s.data) { setOff(s.data.weekly_off_days); setThreshold(String(s.data.attendance_alert_threshold)); setBackdate(String(s.data.backdate_limit_days)); setFailRule(s.data.fail_if_any_subject_failed); }
  }, [s.data]);
  const save = useMutation({
    mutationFn: () => api("/settings", { method: "PUT", body: { weekly_off_days: off, attendance_alert_threshold: Number(threshold), backdate_limit_days: Number(backdate), fail_if_any_subject_failed: failRule } }),
    onSuccess: () => { toast.success("Settings saved"); qc.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save"),
  });
  if (s.isLoading) return <ListSkeleton rows={3} />;
  if (s.error) return <ErrorState error={s.error} onRetry={() => s.refetch()} />;
  const t = Number(threshold), b = Number(backdate);
  const valid = t >= 1 && t <= 100 && b >= 0 && b <= 365;
  return (
    <Card className="max-w-2xl space-y-5 p-5">
      <fieldset><legend className="mb-2 text-sm font-medium">Weekly off days</legend>
        <div className="flex flex-wrap gap-2">
          {WEEKDAYS.map((d) => (
            <label key={d.iso} className="flex min-h-[44px] cursor-pointer items-center gap-2 rounded-md border border-border px-3 text-sm has-[:checked]:border-primary has-[:checked]:bg-blue-50">
              <input type="checkbox" checked={off.includes(d.iso)} onChange={(e) => setOff((p) => (e.target.checked ? [...p, d.iso] : p.filter((x) => x !== d.iso)))} />{d.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Attendance alert threshold (%)" hint="Students below this get the warning banner."><Input type="number" min={1} max={100} value={threshold} aria-invalid={t < 1 || t > 100} onChange={(e) => setThreshold(e.target.value)} /></Field>
        <Field label="Teacher backdate limit (days)" hint="Admins have no limit."><Input type="number" min={0} max={365} value={backdate} aria-invalid={b < 0 || b > 365} onChange={(e) => setBackdate(e.target.value)} /></Field>
      </div>
      <Field label="Overall result rule"><Select value={failRule ? "yes" : "no"} onChange={(e) => setFailRule(e.target.value === "yes")}>
        <option value="yes">Fail if any subject is failed</option><option value="no">Pass on overall percentage (50%+) only</option></Select></Field>
      <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!valid}>Save settings</Button>
    </Card>
  );
}

/** Phase 3 settings only: attendance rules, result rule, holidays. Classes/sections/subjects/years remain with the earlier Settings work. */
export default function SettingsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"rules" | "holidays">("rules");
  if (user && user.role !== "admin") return <AccessDenied />;
  return (
    <>
      <PageHeader title="Settings" description="Attendance and result rules, and the school holiday calendar." />
      <Tabs label="Settings sections" value={tab} onChange={setTab} tabs={[{ key: "rules", label: "Attendance & results" }, { key: "holidays", label: "Holidays" }]} />
      {tab === "rules" ? <Rules /> : <Holidays />}
    </>
  );
}
