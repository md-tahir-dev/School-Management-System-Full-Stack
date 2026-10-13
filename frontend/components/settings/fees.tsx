"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useClasses, useSettings } from "@/lib/queries";
import type { FeeStructure } from "@/lib/types";

/** Monthly fee per class, plus the due day and late fine. New students' ledgers use these amounts. */
export function Fees() {
  const qc = useQueryClient();
  const classes = useClasses();
  const settings = useSettings();
  const fees = useQuery({ queryKey: ["fee-structures"], queryFn: () => api<FeeStructure[]>("/fee-structures") });
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [dueDay, setDueDay] = useState("10");
  const [fine, setFine] = useState("0");
  useEffect(() => { if (fees.data) setAmounts(Object.fromEntries(fees.data.map((f) => [f.class_id, String(Number(f.monthly_fee))]))); }, [fees.data]);
  useEffect(() => { if (settings.data) { setDueDay(String(settings.data.fee_due_day)); setFine(String(Number(settings.data.late_fine_amount))); } }, [settings.data]);

  const save = useMutation({
    mutationFn: async () => {
      const rows = Object.entries(amounts).filter(([, v]) => v.trim() !== "").map(([class_id, v]) => ({ class_id, monthly_fee: v }));
      await api("/fee-structures", { method: "PUT", body: rows });
      await api("/settings", { method: "PUT", body: { fee_due_day: Number(dueDay), late_fine_amount: fine || "0" } });
    },
    onSuccess: () => { toast.success("Fees saved"); qc.invalidateQueries({ queryKey: ["fee-structures"] }); qc.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't save fees")),
  });

  const loading = classes.isLoading || fees.isLoading || settings.isLoading;
  const error = classes.error ?? fees.error ?? settings.error;
  if (loading) return <ListSkeleton rows={4} />;
  if (error) return <ErrorState error={error} onRetry={() => { classes.refetch(); fees.refetch(); settings.refetch(); }} />;
  if (!classes.data?.length) return <EmptyState title="No classes yet" hint="Add classes first, then set their fees." />;
  const d = Number(dueDay);
  const valid = d >= 1 && d <= 28 && Number(fine) >= 0 && Object.values(amounts).every((v) => v === "" || Number(v) >= 0);
  return (
    <Card className="max-w-2xl space-y-5 p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Fee due day of month" hint="1 to 28."><Input type="number" min={1} max={28} value={dueDay} aria-invalid={d < 1 || d > 28} onChange={(e) => setDueDay(e.target.value)} /></Field>
        <Field label="Late fine (flat amount)"><Input type="number" min={0} step="0.01" value={fine} onChange={(e) => setFine(e.target.value)} /></Field>
      </div>
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Monthly fee per class</legend>
        <div className="divide-y divide-border rounded-md border border-border">
          {classes.data.map((c) => (
            <label key={c.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span>{c.name}</span>
              <Input className="w-36 text-right" type="number" min={0} step="0.01" placeholder="Not set" value={amounts[c.id] ?? ""} onChange={(e) => setAmounts((p) => ({ ...p, [c.id]: e.target.value }))} />
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Changes apply to students registered from now on; existing ledgers keep their amounts.</p>
      </fieldset>
      <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!valid}>Save fees</Button>
    </Card>
  );
}
