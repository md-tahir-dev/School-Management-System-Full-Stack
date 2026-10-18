"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { StatCard } from "@/components/stat-card";
import { DataTable, type Column } from "@/components/tables/data-table";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { currentMonth } from "@/components/fees/common";
import { Banknote, Hourglass, Receipt, TrendingUp, TriangleAlert } from "lucide-react";
import { api } from "@/lib/api";
import { dateLabel, fmtMoney } from "@/lib/format";
import { useClasses } from "@/lib/queries";
import type { ClassCollection, Defaulter, FeeSummary, Page } from "@/lib/types";
import type { PickedStudent } from "@/components/fees/collect";

export function DefaultersTab({ onCollect }: { onCollect?: (s: PickedStudent) => void }) {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [classId, setClassId] = useState("");
  const classes = useClasses();
  const query = useQuery({ queryKey: ["fees-defaulters", { page, q, classId }], queryFn: () => api<Page<Defaulter>>("/fees/defaulters", { query: { page, page_size: 10, q: q || undefined, class_id: classId || undefined } }) });
  const columns: Column<Defaulter>[] = [
    { key: "name", header: "Student", cell: (d) => <>{d.full_name}<span className="block text-xs text-muted-foreground">{d.roll_no}</span></> },
    { key: "class", header: "Class", cell: (d) => `${d.class_name}${d.section_name ? ` - ${d.section_name}` : ""}` },
    { key: "phone", header: "Father phone", cell: (d) => d.father_phone ?? "-" },
    { key: "months", header: "Months due", align: "right", cell: (d) => d.months_due },
    { key: "amount", header: "Amount due", align: "right", cell: (d) => <span className="tabular-nums font-semibold">{fmtMoney(d.amount_due)}</span> },
    { key: "oldest", header: "Oldest due", cell: (d) => dateLabel(d.oldest_due_date) },
    ...(onCollect ? [{ key: "go", header: "", cell: (d: Defaulter) => <Button size="sm" onClick={() => onCollect({ id: d.student_id, name: d.full_name })}>Collect</Button> }] : []),
  ];
  return (
    <DataTable columns={columns} rows={query.data?.items} rowKey={(d) => d.student_id} total={query.data?.total ?? 0} page={page} pageSize={10} onPageChange={setPage}
      onSearchChange={(v) => { setQ(v); setPage(1); }} searchPlaceholder="Search name or roll no"
      filters={<Select aria-label="Class" value={classId} onChange={(e) => { setClassId(e.target.value); setPage(1); }}><option value="">All classes</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>}
      isLoading={query.isLoading} isFetching={query.isFetching} error={query.error as Error | null} onRetry={() => query.refetch()} emptyTitle="No defaulters" />
  );
}

const CLASS_COLS: Column<ClassCollection>[] = [
  { key: "c", header: "Class", cell: (c) => c.class_name },
  { key: "b", header: "Billed", align: "right", cell: (c) => fmtMoney(c.billed) },
  { key: "p", header: "Collected", align: "right", cell: (c) => fmtMoney(c.collected) },
  { key: "o", header: "Outstanding", align: "right", cell: (c) => fmtMoney(c.outstanding) },
];

export function SummaryTab() {
  const [month, setMonth] = useState(currentMonth());
  const q = useQuery({ queryKey: ["fees-summary", month], queryFn: () => api<FeeSummary>("/fees/summary", { query: { month: `${month}-01` } }), enabled: !!month });
  const d = q.data;
  return (
    <div className="space-y-5">
      <div className="flex max-w-xs flex-col gap-1.5 text-sm"><label htmlFor="sum-month" className="font-medium">Month</label><Input id="sum-month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></div>
      {q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard label="Billed" value={d && fmtMoney(d.billed)} icon={Receipt} loading={q.isLoading} />
            <StatCard label="Collected" value={d && fmtMoney(d.collected)} icon={Banknote} tone="success" loading={q.isLoading} />
            <StatCard label="Outstanding" value={d && fmtMoney(d.outstanding)} icon={Hourglass} tone="warning" loading={q.isLoading} />
            <StatCard label="Received this month" value={d && fmtMoney(d.received_in_month)} icon={TrendingUp} tone="success" loading={q.isLoading} />
            <StatCard label="Overdue total" value={d && fmtMoney(d.overdue_total)} icon={TriangleAlert} tone="danger" loading={q.isLoading} />
          </div>
          {q.isLoading ? <ListSkeleton rows={4} /> : <DataTable columns={CLASS_COLS} rows={d?.by_class} rowKey={(c) => c.class_name} total={d?.by_class.length ?? 0} page={1} pageSize={Math.max(d?.by_class.length ?? 0, 1)} onPageChange={() => {}} emptyTitle="No data for this month" />}
        </>
      )}
    </div>
  );
}
