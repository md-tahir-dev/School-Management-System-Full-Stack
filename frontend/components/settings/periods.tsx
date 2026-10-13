"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import type { Period } from "@/lib/types";

const hm = (t: string) => t.slice(0, 5);
const blank = { name: "", start_time: "", end_time: "", sort_order: "0", is_break: false };

export function Periods() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["periods"], queryFn: () => api<Period[]>("/periods") });
  const [form, setForm] = useState(blank);
  const [editId, setEditId] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Period | null>(null);
  const done = () => { qc.invalidateQueries({ queryKey: ["periods"] }); qc.invalidateQueries({ queryKey: ["timetable"] }); };
  const save = useMutation({
    mutationFn: () => api(editId ? `/periods/${editId}` : "/periods", { method: editId ? "PUT" : "POST", body: { ...form, name: form.name.trim(), sort_order: Number(form.sort_order) || 0 } }),
    onSuccess: () => { toast.success(editId ? "Period updated" : "Period added"); setForm(blank); setEditId(null); done(); },
    onError: (e) => toast.error(errorText(e, "Couldn't save period")), // 409 when a period with lectures becomes a break
  });
  const del = useMutation({
    mutationFn: (id: string) => api<void>(`/periods/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Period deleted"); done(); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete period")),
  });
  const set = (k: keyof typeof blank, v: string | boolean) => setForm((p) => ({ ...p, [k]: v }));
  const rows = [...(q.data ?? [])].sort((a, b) => a.sort_order - b.sort_order || a.start_time.localeCompare(b.start_time));
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-[1fr_8rem_8rem_6rem_auto_auto] lg:items-end">
        <Field label="Name"><Input value={form.name} maxLength={64} placeholder="e.g. Period 1" onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Start"><Input type="time" value={form.start_time} onChange={(e) => set("start_time", e.target.value)} /></Field>
        <Field label="End"><Input type="time" value={form.end_time} onChange={(e) => set("end_time", e.target.value)} /></Field>
        <Field label="Order"><Input type="number" min={0} value={form.sort_order} onChange={(e) => set("sort_order", e.target.value)} /></Field>
        <label className="flex min-h-[44px] items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4" checked={form.is_break} onChange={(e) => set("is_break", e.target.checked)} />Break</label>
        <div className="flex gap-2">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!form.name.trim() || !form.start_time || !form.end_time}>
            {editId ? "Save" : <><Plus className="h-4 w-4" />Add period</>}
          </Button>
          {editId && <Button variant="outline" onClick={() => { setEditId(null); setForm(blank); }}>Cancel</Button>}
        </div>
      </Card>
      {q.isLoading ? <ListSkeleton rows={4} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !rows.length ? <EmptyState title="No periods yet" hint="Add the bell schedule above." /> : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {rows.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="flex-1 font-medium">{p.name}{p.is_break && <span className="ml-2 text-xs text-muted-foreground">(break)</span>}</span>
              <span className="tabular-nums text-muted-foreground">{hm(p.start_time)} - {hm(p.end_time)}</span>
              <Button variant="ghost" size="icon" aria-label={`Edit ${p.name}`} onClick={() => { setEditId(p.id); setForm({ name: p.name, start_time: hm(p.start_time), end_time: hm(p.end_time), sort_order: String(p.sort_order), is_break: p.is_break }); }}><Pencil className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" aria-label={`Delete ${p.name}`} onClick={() => setToDelete(p)}><Trash2 className="h-4 w-4 text-danger" /></Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title={`Delete ${toDelete?.name ?? "period"}?`} description="All lectures scheduled in this period will be removed from every timetable." confirmLabel="Delete period" destructive onConfirm={async () => { if (toDelete) await del.mutateAsync(toDelete.id).catch(() => undefined); }} />
    </div>
  );
}
