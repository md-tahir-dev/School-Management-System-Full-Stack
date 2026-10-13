"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, ApiError } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import type { Holiday, Page } from "@/lib/types";

export function Holidays() {
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
