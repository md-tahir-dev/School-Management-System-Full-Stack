"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PdfButton } from "@/components/fees/common";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { fmtMoney } from "@/lib/format";
import type { Page, Payment } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Payment list. `studentId` scopes it (own history, or one student's recent payments); `full` adds search + date filters. */
export function PaymentsTable({ studentId, full = false, pageSize = 10, extraColumns = [] }: { studentId?: string; full?: boolean; pageSize?: number; extraColumns?: Column<Payment>[] }) {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const query = useQuery({
    queryKey: ["fees-payments", { studentId, q, from, to, page, pageSize }],
    queryFn: () => api<Page<Payment>>("/fees/payments", { query: { page, page_size: pageSize, q: q || undefined, student_id: studentId, from: from || undefined, to: to || undefined } }),
    enabled: full || !!studentId,
  });
  const strike = (p: Payment) => cn("tabular-nums", p.voided_at && "line-through text-muted-foreground");
  const columns: Column<Payment>[] = [
    { key: "receipt", header: "Receipt", cell: (p) => <span className={strike(p)}>{p.receipt_no}</span> },
    { key: "date", header: "Date", cell: (p) => <span className={strike(p)}>{new Date(p.paid_at).toLocaleDateString()}</span> },
    ...(full ? [{ key: "student", header: "Student", cell: (p: Payment) => <span className={cn(p.voided_at && "line-through text-muted-foreground")}>{p.student_name}<span className="block text-xs text-muted-foreground">{p.roll_no} · {p.class_name}</span></span> }] : []),
    { key: "amount", header: "Amount", align: "right", cell: (p) => <span className={strike(p)}>{fmtMoney(p.amount)}</span> },
    { key: "method", header: "Method", cell: (p) => <span className="capitalize">{p.method}</span> },
    { key: "months", header: "Months", cell: (p) => p.allocations.map((a) => a.month.slice(0, 7)).join(", ") || "-" },
    { key: "status", header: "", cell: (p) => (p.voided_at ? <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800" title={p.void_reason ?? undefined}>VOID</span> : null) },
    ...extraColumns,
    { key: "pdf", header: "Receipt PDF", cell: (p) => <PdfButton path={`/fees/payments/${p.id}/pdf`} filename={`${p.receipt_no}.pdf`} /> },
  ];
  const reset = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => { set(e.target.value); setPage(1); };
  return (
    <DataTable columns={columns} rows={query.data?.items} rowKey={(p) => p.id} total={query.data?.total ?? 0} page={page} pageSize={pageSize} onPageChange={setPage}
      onSearchChange={full ? (v) => { setQ(v); setPage(1); } : undefined} searchPlaceholder="Receipt number"
      filters={full ? (
        <>
          <Input type="date" aria-label="From date" value={from} onChange={reset(setFrom)} className="w-auto" />
          <Input type="date" aria-label="To date" value={to} onChange={reset(setTo)} className="w-auto" />
        </>
      ) : undefined}
      isLoading={query.isLoading} isFetching={query.isFetching} error={query.error as Error | null} onRetry={() => query.refetch()} emptyTitle="No payments yet" />
  );
}
