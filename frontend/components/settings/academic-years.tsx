"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import { useAcademicYears } from "@/lib/queries";

export function AcademicYears() {
  const qc = useQueryClient();
  const years = useAcademicYears();
  const [label, setLabel] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["academic-years"] }); qc.invalidateQueries({ queryKey: ["settings"] }); };
  const add = useMutation({
    mutationFn: () => api("/academic-years", { method: "POST", body: { label: label.trim(), start_date: start, end_date: end } }),
    onSuccess: () => { toast.success("Academic year added"); setLabel(""); setStart(""); setEnd(""); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't add")),
  });
  const makeCurrent = useMutation({
    mutationFn: (id: string) => api(`/academic-years/${id}/set-current`, { method: "POST" }),
    onSuccess: () => { toast.success("Current year changed"); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't change")),
  });
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-[8rem_10rem_10rem_auto] sm:items-end">
        <Field label="Label"><Input value={label} maxLength={32} placeholder="2026-27" onChange={(e) => setLabel(e.target.value)} /></Field>
        <Field label="Starts"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="Ends"><Input type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} /></Field>
        <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!label.trim() || !start || !end || end <= start}><Plus className="h-4 w-4" />Add year</Button>
      </Card>
      {years.isLoading ? <ListSkeleton rows={3} /> : years.error ? <ErrorState error={years.error} onRetry={() => years.refetch()} /> : !years.data?.length ? <EmptyState title="No academic years yet" /> : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {years.data.map((y) => (
            <li key={y.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
              <span className="w-24 font-semibold">{y.label}</span>
              <span className="flex-1 text-muted-foreground">{dateLabel(y.start_date)} to {dateLabel(y.end_date)}</span>
              {y.is_current
                ? <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-primary">Current</span>
                : <Button variant="outline" size="sm" loading={makeCurrent.isPending && makeCurrent.variables === y.id} onClick={() => makeCurrent.mutate(y.id)}>Make current</Button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
