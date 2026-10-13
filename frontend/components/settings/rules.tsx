"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, ApiError } from "@/lib/api";
import { WEEKDAYS } from "@/lib/format";
import { useSettings } from "@/lib/queries";

export function Rules() {
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
