"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { currentMonth, PdfButton } from "@/components/fees/common";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { Tabs } from "@/components/ui/tabs";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, fmtMoney, monthLabel, num } from "@/lib/format";
import { isManager, isSchoolWide } from "@/lib/role-config";
import type { Page, SalaryAdvance, SalaryGenerateResult, SalaryRecord, TeacherListItem } from "@/lib/types";

const rowCols = (extra: Column<SalaryRecord>[], withName: boolean): Column<SalaryRecord>[] => [
  ...(withName ? [{ key: "t", header: "Teacher", cell: (r: SalaryRecord) => <>{r.teacher_name}<span className="block text-xs text-muted-foreground">{r.employee_id}</span></> }] : []),
  { key: "m", header: "Month", cell: (r) => monthLabel(r.month.slice(0, 7)) },
  { key: "g", header: "Gross", align: "right", cell: (r) => fmtMoney(r.gross) },
  { key: "d", header: "Absent days", align: "right", cell: (r) => r.absent_days },
  { key: "ad", header: "Absence deduction", align: "right", cell: (r) => fmtMoney(r.absence_deduction) },
  { key: "av", header: "Advance", align: "right", cell: (r) => fmtMoney(r.advance_deduction) },
  { key: "n", header: "Net", align: "right", cell: (r) => <span className="font-semibold tabular-nums">{fmtMoney(r.net)}</span> },
  { key: "s", header: "Status", cell: (r) => <StatusBadge status={r.status} label={r.status === "paid" && r.paid_date ? `Paid ${dateLabel(r.paid_date)}` : undefined} /> },
  ...extra,
];
const payslip = (r: SalaryRecord) => <PdfButton path={`/salary/${r.id}/pdf`} filename={`payslip-${r.employee_id}-${r.month.slice(0, 7)}.pdf`} label="Payslip" />;
const none = (rows: unknown[] | undefined) => ({ total: rows?.length ?? 0, page: 1, pageSize: Math.max(rows?.length ?? 0, 1), onPageChange: () => {} });

function MySalary() {
  const q = useQuery({ queryKey: ["salary", "me"], queryFn: () => api<SalaryRecord[]>("/salary/me") });
  return (
    <>
      <PageHeader title="My salary" description="Your monthly payslips." />
      <DataTable columns={rowCols([{ key: "p", header: "", cell: payslip }], false)} rows={q.data} rowKey={(r) => r.id} {...none(q.data)} isLoading={q.isLoading} error={q.error as Error | null} onRetry={() => q.refetch()} emptyTitle="No salary records yet" />
    </>
  );
}

function Advances({ month, manager }: { month: string; manager: boolean }) {
  const qc = useQueryClient();
  const form = useApiForm({ teacher_id: "", amount: "", month, note: "" });
  const [del, setDel] = useState<SalaryAdvance | null>(null);
  const teachers = useQuery({ queryKey: ["teachers-all"], queryFn: () => api<Page<TeacherListItem>>("/teachers", { query: { page_size: 100 } }), enabled: manager });
  const list = useQuery({ queryKey: ["salary-advances", month], queryFn: () => api<SalaryAdvance[]>("/salary/advances", { query: { month: `${month}-01` } }) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["salary-advances"] }); qc.invalidateQueries({ queryKey: ["salary"] }); };
  const add = useMutation({
    mutationFn: () => api("/salary/advances", { method: "POST", body: { teacher_id: form.values.teacher_id, amount: form.values.amount, month: `${form.values.month}-01`, note: form.values.note || null } }),
    onSuccess: () => { toast.success("Advance added"); form.set("amount", ""); form.set("note", ""); refresh(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't add the advance")); },
  });
  const cols: Column<SalaryAdvance>[] = [
    { key: "t", header: "Teacher", cell: (a) => a.teacher_name },
    { key: "a", header: "Amount", align: "right", cell: (a) => fmtMoney(a.amount) },
    { key: "n", header: "Note", cell: (a) => a.note ?? "-" },
    ...(manager ? [{ key: "x", header: "", cell: (a: SalaryAdvance) => <Button size="sm" variant="outline" onClick={() => setDel(a)}>Delete</Button> }] : []),
  ];
  return (
    <div className="space-y-5">
      {manager && (
        <Card className="p-4">
          <h3 className="mb-3 font-semibold">Add advance</h3>
          <form className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <SelectField form={form} name="teacher_id" label="Teacher" options={(teachers.data?.items ?? []).map((t) => ({ value: t.id, label: `${t.full_name} (${t.employee_id})` }))} />
            <TextField form={form} name="amount" label="Amount" inputMode="decimal" />
            <TextField form={form} name="month" label="Month" type="month" />
            <TextField form={form} name="note" label="Note (optional)" />
            <div className="sm:col-span-2 lg:col-span-4"><Button type="submit" loading={add.isPending}>Add advance</Button></div>
          </form>
        </Card>
      )}
      <DataTable columns={cols} rows={list.data} rowKey={(a) => a.id} {...none(list.data)} isLoading={list.isLoading} error={list.error as Error | null} onRetry={() => list.refetch()} emptyTitle="No advances for this month" />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title="Delete advance" destructive confirmLabel="Delete advance"
        description={del ? `Remove the ${fmtMoney(del.amount)} advance for ${del.teacher_name}? Regenerate salary to update the deduction.` : ""}
        onConfirm={async () => { try { await api(`/salary/advances/${del!.id}`, { method: "DELETE" }); toast.success("Advance deleted"); refresh(); } catch (e) { toast.error(errorText(e, "Couldn't delete")); throw e; } }} />
    </div>
  );
}

function Payroll({ manager }: { manager: boolean }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"records" | "advances">("records");
  const [month, setMonth] = useState(currentMonth());
  const [result, setResult] = useState<SalaryGenerateResult | null>(null);
  const q = useQuery({ queryKey: ["salary", month], queryFn: () => api<SalaryRecord[]>("/salary", { query: { month: `${month}-01` } }), enabled: !!month });
  const gen = useMutation({
    mutationFn: () => api<SalaryGenerateResult>("/salary/generate", { method: "POST", body: { month: `${month}-01` } }),
    onSuccess: (r) => { setResult(r); qc.invalidateQueries({ queryKey: ["salary"] }); toast.success("Salary generated"); },
    onError: (e) => toast.error(errorText(e, "Couldn't generate salary")),
  });
  const pay = useMutation({
    mutationFn: (id: string) => api<SalaryRecord>(`/salary/${id}/pay`, { method: "POST", body: {} }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["salary"] }); toast.success("Marked as paid"); },
    onError: (e) => toast.error(errorText(e, "Couldn't mark as paid")),
  });
  const sum = (k: "gross" | "absence_deduction" | "advance_deduction" | "net") => (q.data ?? []).reduce((a, r) => a + num(r[k]), 0);
  const cols = rowCols([{ key: "x", header: "", cell: (r) => (
    <div className="flex gap-2">
      {manager && r.status === "unpaid" && <Button size="sm" loading={pay.isPending && pay.variables === r.id} onClick={() => pay.mutate(r.id)}>Mark paid</Button>}
      {payslip(r)}
    </div>) }], true);
  return (
    <>
      <PageHeader title="Salary" description={manager ? "Generate monthly salary, record payment and manage advances." : "Salary overview (read-only)."} />
      <Tabs tabs={[{ key: "records", label: "Salary" }, { key: "advances", label: "Advances" }]} value={tab} onChange={setTab} label="Salary sections" />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5 text-sm"><label htmlFor="sal-month" className="font-medium">Month</label><Input id="sal-month" type="month" value={month} onChange={(e) => { setMonth(e.target.value); setResult(null); }} /></div>
        {manager && tab === "records" && <Button loading={gen.isPending} disabled={!month} onClick={() => gen.mutate()}>Generate / recalculate</Button>}
      </div>
      {tab === "advances" ? <Advances month={month} manager={manager} /> : (
        <div className="space-y-4">
          {result && (
            <div className="rounded-md border border-border bg-card p-3 text-sm" role="status">
              <p>Created {result.created}, recalculated {result.recalculated}, skipped (already paid) {result.skipped_paid}.</p>
              {result.without_structure.length > 0 && <p className="mt-1 text-danger">No salary structure for: {result.without_structure.join(", ")}</p>}
            </div>
          )}
          <DataTable columns={cols} rows={q.data} rowKey={(r) => r.id} {...none(q.data)} isLoading={q.isLoading} error={q.error as Error | null} onRetry={() => q.refetch()} emptyTitle="No salary records" emptyHint={manager ? "Press Generate to create this month's records." : undefined} />
          {q.data && q.data.length > 0 && (
            <p className="text-sm font-semibold tabular-nums">Totals: gross {fmtMoney(sum("gross"))} · absence {fmtMoney(sum("absence_deduction"))} · advances {fmtMoney(sum("advance_deduction"))} · net {fmtMoney(sum("net"))}</p>
          )}
        </div>
      )}
    </>
  );
}

export default function SalaryPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "teacher") return <PageBoundary><MySalary /></PageBoundary>;
  if (!isSchoolWide(user.role)) return <AccessDenied />;
  return <PageBoundary><Payroll manager={isManager(user.role)} /></PageBoundary>;
}
