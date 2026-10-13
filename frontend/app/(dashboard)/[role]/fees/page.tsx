"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Card } from "@/components/ui/card";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, fmtMoney, monthLabel } from "@/lib/format";
import { useStudentScope } from "@/lib/queries";
import type { LedgerOut, LedgerRow } from "@/lib/types";
import { useState } from "react";
import { CollectTab, type PickedStudent } from "@/components/fees/collect";
import { DefaultersTab, SummaryTab } from "@/components/fees/defaulters-summary";
import { PaymentsTable } from "@/components/fees/payments-table";
import { Tabs } from "@/components/ui/tabs";
import { isManager, isSchoolWide } from "@/lib/role-config";

const money = (r: LedgerRow, k: "base_fee" | "discount" | "fine" | "total_payable" | "paid_amount") => <span className="tabular-nums">{fmtMoney(r[k])}</span>;
const COLUMNS: Column<LedgerRow>[] = [
  { key: "month", header: "Month", cell: (r) => monthLabel(r.month.slice(0, 7)) },
  { key: "base", header: "Fee", align: "right", cell: (r) => money(r, "base_fee") },
  { key: "discount", header: "Discount", align: "right", cell: (r) => money(r, "discount") },
  { key: "fine", header: "Fine", align: "right", cell: (r) => money(r, "fine") },
  { key: "total", header: "Payable", align: "right", cell: (r) => money(r, "total_payable") },
  { key: "paid", header: "Paid", align: "right", cell: (r) => money(r, "paid_amount") },
  { key: "due", header: "Due date", cell: (r) => dateLabel(r.due_date) },
  { key: "status", header: "Status", cell: (r) => <StatusBadge status={r.status} /> },
  { key: "receipt", header: "Receipt", cell: (r) => r.receipt_no ?? "-" },
];

function OwnFees() {
  const scope = useStudentScope();
  const q = useQuery({ queryKey: ["ledger", scope.studentId], queryFn: () => api<LedgerOut>(`/students/${scope.studentId}/ledger`), enabled: !!scope.studentId });
  const t = q.data?.totals;
  const totals: [string, string | undefined][] = [["Total payable", t?.total_payable], ["Paid", t?.paid_amount], ["Balance", t?.balance]];
  return (
    <>
      <PageHeader title="Fees" description={scope.child?.full_name}
        actions={scope.isParent ? <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /> : undefined} />
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {totals.map(([label, v]) => (
          <Card key={label} className="p-4"><p className="text-2xl font-bold tabular-nums">{v === undefined ? "-" : fmtMoney(v)}</p><p className="text-sm text-muted-foreground">{label}</p></Card>
        ))}
      </div>
      <DataTable columns={COLUMNS} rows={q.data?.items} rowKey={(r) => r.id} total={q.data?.items.length ?? 0} page={1} pageSize={Math.max(q.data?.items.length ?? 0, 1)} onPageChange={() => {}}
        isLoading={scope.isLoading || q.isLoading} error={(scope.error ?? q.error) as Error | null} onRetry={() => q.refetch()} emptyTitle="No fee records yet" />
      <h2 className="mb-2 mt-6 text-lg font-semibold">Payments</h2>
      <PaymentsTable studentId={scope.studentId} />
    </>
  );
}

type Tab = "collect" | "payments" | "defaulters" | "summary";

function StaffFees({ manager }: { manager: boolean }) {
  const [tab, setTab] = useState<Tab>(manager ? "collect" : "payments");
  const [student, setStudent] = useState<PickedStudent | null>(null);
  const tabs: { key: Tab; label: string }[] = [
    ...(manager ? [{ key: "collect" as const, label: "Collect" }] : []),
    { key: "payments", label: "Payments" }, { key: "defaulters", label: "Defaulters" }, { key: "summary", label: "Summary" },
  ];
  return (
    <>
      <PageHeader title="Fees" description={manager ? "Collect payments, track defaulters and review collection." : "Fee collection overview (read-only)."} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} label="Fees sections" />
      {tab === "collect" && <CollectTab student={student} onPick={setStudent} />}
      {tab === "payments" && <PaymentsTable full />}
      {tab === "defaulters" && <DefaultersTab onCollect={manager ? (s) => { setStudent(s); setTab("collect"); } : undefined} />}
      {tab === "summary" && <SummaryTab />}
    </>
  );
}

export default function FeesPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "student" || user.role === "parent") return <PageBoundary><OwnFees /></PageBoundary>;
  if (!isSchoolWide(user.role)) return <AccessDenied />;
  return <PageBoundary><StaffFees manager={isManager(user.role)} /></PageBoundary>;
}
