"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PdfButton } from "@/components/fees/common";
import { PaymentsTable } from "@/components/fees/payments-table";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { Modal } from "@/components/modals/modal";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, errorText } from "@/lib/api";
import { dateLabel, fmtMoney, monthLabel, num } from "@/lib/format";
import { useDebounce } from "@/hooks/use-debounce";
import type { LedgerOut, LedgerRow, Page, Payment, StudentListItem } from "@/lib/types";

export type PickedStudent = { id: string; name: string };

const LEDGER_COLS: Column<LedgerRow>[] = [
  { key: "month", header: "Month", cell: (r) => monthLabel(r.month.slice(0, 7)) },
  { key: "base", header: "Fee", align: "right", cell: (r) => fmtMoney(r.base_fee) },
  { key: "discount", header: "Discount", align: "right", cell: (r) => fmtMoney(r.discount) },
  { key: "fine", header: "Fine", align: "right", cell: (r) => fmtMoney(r.fine) },
  { key: "total", header: "Payable", align: "right", cell: (r) => fmtMoney(r.total_payable) },
  { key: "paid", header: "Paid", align: "right", cell: (r) => fmtMoney(r.paid_amount) },
  { key: "due", header: "Due date", cell: (r) => dateLabel(r.due_date) },
  { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
];

function StudentSearch({ onPick }: { onPick: (s: PickedStudent) => void }) {
  const [text, setText] = useState("");
  const q = useDebounce(text.trim(), 350);
  const res = useQuery({ queryKey: ["students-search", q], queryFn: () => api<Page<StudentListItem>>("/students", { query: { q, page_size: 8 } }), enabled: q.length >= 2 });
  return (
    <div className="mb-5">
      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search student by name or roll number" aria-label="Search student" className="pl-9" />
      </div>
      {q.length >= 2 && (
        <ul className="mt-2 max-w-md divide-y divide-border rounded-lg border border-border bg-card" aria-label="Matching students">
          {res.isLoading ? <li className="p-3 text-sm text-muted-foreground">Searching...</li> : res.error ? <li className="p-3 text-sm text-danger">{errorText(res.error, "Search failed")}</li> : res.data?.items.length === 0 ? <li className="p-3 text-sm text-muted-foreground">No students found.</li> : res.data?.items.map((s) => (
            <li key={s.id}>
              <button type="button" className="flex min-h-11 w-full flex-col px-3 py-2 text-left text-sm hover:bg-muted/60" onClick={() => { onPick({ id: s.id, name: s.full_name }); setText(""); }}>
                <span className="font-medium">{s.full_name}</span><span className="text-xs text-muted-foreground">{s.roll_no}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VoidModal({ payment, onClose, onDone }: { payment: Payment | null; onClose: () => void; onDone: () => void }) {
  const form = useApiForm({ reason: "" });
  const m = useMutation({
    mutationFn: () => api<Payment>(`/fees/payments/${payment!.id}/void`, { method: "POST", body: { reason: form.values.reason } }),
    onSuccess: () => { toast.success("Payment voided"); form.reset({ reason: "" }); onDone(); onClose(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't void the payment")); },
  });
  return (
    <Modal open={!!payment} onOpenChange={(o) => !o && !m.isPending && onClose()} title="Void payment" size="sm"
      description={payment ? `Receipt ${payment.receipt_no} for ${fmtMoney(payment.amount)} will be reversed.` : undefined}
      footer={<><Button variant="outline" onClick={onClose} disabled={m.isPending}>Cancel</Button><Button variant="destructive" loading={m.isPending} onClick={() => m.mutate()}>Void payment</Button></>}>
      <TextField form={form} name="reason" label="Reason" hint="3 to 255 characters" maxLength={255} />
    </Modal>
  );
}

export function CollectTab({ student, onPick }: { student: PickedStudent | null; onPick: (s: PickedStudent | null) => void }) {
  const qc = useQueryClient();
  const form = useApiForm({ amount: "", method: "cash", note: "" });
  const [receipt, setReceipt] = useState<Payment | null>(null);
  const [voiding, setVoiding] = useState<Payment | null>(null);
  const ledger = useQuery({ queryKey: ["ledger", student?.id], queryFn: () => api<LedgerOut>(`/students/${student!.id}/ledger`), enabled: !!student });
  // Prefill what is due up to and including this month, not the whole year's balance.
  const thisMonth = new Date().toISOString().slice(0, 7);
  const dueNow = ledger.data?.items
    .filter((r) => r.month.slice(0, 7) <= thisMonth)
    .reduce((sum, r) => sum + num(r.total_payable) - num(r.paid_amount), 0);
  const balance = dueNow === undefined ? undefined : dueNow.toFixed(2);
  const { reset } = form;
  useEffect(() => { setReceipt(null); reset({ amount: balance && num(balance) > 0 ? String(num(balance)) : "", method: "cash", note: "" }); }, [student?.id, balance, reset]);

  const refresh = () => ["ledger", "fees-payments", "fees-defaulters", "fees-summary"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const pay = useMutation({
    mutationFn: () => api<Payment>("/fees/payments", { method: "POST", body: { student_id: student!.id, amount: form.values.amount, method: form.values.method, note: form.values.note || null } }),
    onSuccess: (p) => { setReceipt(p); toast.success(`Payment recorded: ${p.receipt_no}`); refresh(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't record the payment")); },
  });
  const voidCol: Column<Payment> = { key: "void", header: "", cell: (p) => (p.voided_at ? null : <Button size="sm" variant="outline" onClick={() => setVoiding(p)}>Void</Button>) };

  return (
    <>
      <StudentSearch onPick={onPick} />
      {!student ? <p className="text-sm text-muted-foreground">Search for a student to see their ledger and collect a payment.</p> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold">{student.name}</h2>
            <Button variant="ghost" size="sm" onClick={() => onPick(null)}>Clear</Button>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([["Total payable", ledger.data?.totals.total_payable], ["Paid", ledger.data?.totals.paid_amount], ["Balance", ledger.data?.totals.balance]] as const).map(([l, v]) => (
              <Card key={l} className="p-4"><p className="text-2xl font-bold tabular-nums">{v === undefined ? "-" : fmtMoney(v)}</p><p className="text-sm text-muted-foreground">{l}</p></Card>
            ))}
          </div>
          <DataTable columns={LEDGER_COLS} rows={ledger.data?.items} rowKey={(r) => r.id} total={ledger.data?.items.length ?? 0} page={1} pageSize={Math.max(ledger.data?.items.length ?? 0, 1)} onPageChange={() => {}}
            isLoading={ledger.isLoading} error={ledger.error as Error | null} onRetry={() => ledger.refetch()} emptyTitle="No fee records yet" />
          <Card className="p-4">
            <h3 className="mb-3 font-semibold">Collect payment</h3>
            <form className="grid gap-4 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); pay.mutate(); }}>
              <TextField form={form} name="amount" label="Amount" inputMode="decimal" />
              <SelectField form={form} name="method" label="Method" options={["cash", "bank", "online", "cheque"]} />
              <TextField form={form} name="note" label="Note (optional)" />
              <div className="sm:col-span-3"><Button type="submit" loading={pay.isPending}>Record payment</Button></div>
            </form>
            {receipt && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-green-300 bg-green-50 p-3 text-sm" role="status">
                <div>
                  <p className="font-semibold">Receipt {receipt.receipt_no}: {fmtMoney(receipt.amount)} ({receipt.method})</p>
                  <p className="text-muted-foreground">{receipt.allocations.map((a) => `${monthLabel(a.month.slice(0, 7))}: ${fmtMoney(a.amount)}`).join(" · ")}</p>
                </div>
                <PdfButton path={`/fees/payments/${receipt.id}/pdf`} filename={`${receipt.receipt_no}.pdf`} label="Print receipt" />
              </div>
            )}
          </Card>
          <div>
            <h3 className="mb-2 font-semibold">Recent payments</h3>
            <PaymentsTable studentId={student.id} pageSize={5} extraColumns={[voidCol]} />
          </div>
        </div>
      )}
      <VoidModal payment={voiding} onClose={() => setVoiding(null)} onDone={refresh} />
    </>
  );
}
