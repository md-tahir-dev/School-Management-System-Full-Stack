"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, FileDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MarksEntry } from "@/components/results/marks-entry";
import { PublishDialog } from "@/components/results/publish-dialog";
import { SubjectsEditor } from "@/components/results/subjects-editor";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, apiBlob, saveBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtPct, num } from "@/lib/format";
import { useSections } from "@/lib/queries";
import type { ClassResultRow, Exam, ExamAnalytics, MarksProgressRow, Page } from "@/lib/types";
import { cn } from "@/lib/utils";
import { BarChart3, CheckCircle2, TrendingDown, TrendingUp, Users } from "lucide-react";

const PAGE_SIZE = 15;
type Tab = "progress" | "results" | "analytics" | "entry" | "subjects";

function Progress({ examId }: { examId: string }) {
  const q = useQuery({ queryKey: ["exam-progress", examId], queryFn: () => api<MarksProgressRow[]>(`/exams/${examId}/marks-progress`) });
  if (q.isLoading) return <ListSkeleton rows={5} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyState title="Nothing to track yet" hint="Add subjects and students to see entry progress." />;
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card"><div className="overflow-x-auto">
      <table className="w-full min-w-[30rem] text-left text-sm">
        <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr>{["Subject", "Section", "Entered", "Progress"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
        <tbody>
          {q.data.map((r) => {
            const pct = r.total ? (r.entered / r.total) * 100 : 0;
            const done = r.total > 0 && r.entered >= r.total;
            return (
              <tr key={`${r.subject_id}${r.section_id}`} className="border-b border-border/60 last:border-0">
                <td className="px-4 py-3 font-medium">{r.subject_name}</td><td className="px-4 py-3">{r.section_name ?? "-"}</td>
                <td className="px-4 py-3 tabular-nums">{r.entered} of {r.total} students</td>
                <td className="px-4 py-3"><div className="flex items-center gap-2"><div className="h-2 w-32 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={`${r.subject_name} ${r.section_name ?? ""} progress`}><div className={cn("h-full", done ? "bg-success" : "bg-warning")} style={{ width: `${pct}%` }} /></div>{done && <CheckCircle2 className="h-4 w-4 text-success" aria-label="Complete" />}</div></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div></div>
  );
}

function ResultsSheet({ exam }: { exam: Exam }) {
  const { user } = useAuth();
  const sections = useSections(exam.class_id);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [sectionId, setSectionId] = useState("");
  const query = useQuery({
    queryKey: ["exam-results", exam.id, { page, q, sectionId }],
    queryFn: ({ signal }) => api<Page<ClassResultRow>>(`/exams/${exam.id}/results`, { query: { page, page_size: PAGE_SIZE, q, section_id: sectionId }, signal }),
    placeholderData: keepPreviousData,
  });
  const [busy, setBusy] = useState<"csv" | "pdf" | null>(null);
  async function download(kind: "csv" | "pdf") {
    setBusy(kind);
    try {
      const blob = await apiBlob(kind === "csv" ? `/exams/${exam.id}/results/export` : `/exams/${exam.id}/results/pdf`, { section_id: sectionId, format: kind === "csv" ? "csv" : undefined });
      saveBlob(blob, `${exam.name}-results.${kind}`);
    } catch (e) { toast.error(e instanceof Error ? e.message : "Download failed"); }
    finally { setBusy(null); }
  }
  const columns: Column<ClassResultRow>[] = [
    { key: "rank", header: "Rank", cell: (r) => <span className="font-semibold tabular-nums">{r.rank ?? "-"}</span> },
    { key: "roll", header: "Roll no.", cell: (r) => r.roll_no },
    { key: "name", header: "Name", cell: (r) => r.result_id ? <Link className="font-medium text-primary hover:underline" href={`/${user?.role}/results/${r.result_id}`}>{r.full_name}</Link> : r.full_name },
    { key: "section", header: "Section", cell: (r) => r.section_name ?? "-" },
    { key: "total", header: "Total", cell: (r) => <span className="tabular-nums">{num(r.total_obtained)} / {num(r.total_possible)}</span> },
    { key: "pct", header: "%", cell: (r) => r.status === "complete" ? <span className="tabular-nums">{fmtPct(r.percentage)}</span> : "-" },
    { key: "grade", header: "Grade", cell: (r) => r.status === "complete" ? <span className="font-semibold">{r.grade}</span> : "-" },
    { key: "res", header: "Result", cell: (r) => r.status === "complete" ? <StatusBadge status={r.is_pass ? "pass" : "fail"} label={r.is_pass ? "Pass" : "Fail"} /> : <StatusBadge status="draft" label="Incomplete" /> },
  ];
  return (
    <DataTable columns={columns} rows={query.data?.items} rowKey={(r) => r.student_id} total={query.data?.total ?? 0} page={page} pageSize={PAGE_SIZE}
      onPageChange={setPage} onSearchChange={(v) => { setQ(v); setPage(1); }} searchPlaceholder="Search student"
      filters={<Select aria-label="Filter by section" value={sectionId} onChange={(e) => { setSectionId(e.target.value); setPage(1); }}><option value="">All sections</option>{sections.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>}
      actions={<>
        <Button variant="outline" size="sm" loading={busy === "csv"} onClick={() => download("csv")}><FileDown className="h-3.5 w-3.5" />CSV</Button>
        {user?.role === "admin" && <Button variant="outline" size="sm" loading={busy === "pdf"} onClick={() => download("pdf")}><Download className="h-3.5 w-3.5" />Download all cards (PDF)</Button>}
      </>}
      isLoading={query.isLoading} isFetching={query.isFetching} error={query.error} onRetry={() => query.refetch()}
      emptyTitle="No results yet" emptyHint="Results appear here as marks are entered." />
  );
}

function Analytics({ examId }: { examId: string }) {
  const q = useQuery({ queryKey: ["exam-analytics", examId], queryFn: () => api<ExamAnalytics>(`/exams/${examId}/analytics`) });
  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const a = q.data;
  if (!a) return null;
  const order = ["A+", "A", "B", "C", "D", "F"];
  const dist = order.map((g) => ({ grade: g, students: a.grade_distribution[g] ?? 0 }));
  const subj = a.subjects.map((s) => ({ name: s.subject_name, average: num(s.average_percentage), passRate: num(s.pass_rate) }));
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Class average" value={fmtPct(a.class_average)} icon={BarChart3} />
        <StatCard label="Highest" value={fmtPct(a.highest)} icon={TrendingUp} tone="success" />
        <StatCard label="Lowest" value={fmtPct(a.lowest)} icon={TrendingDown} tone="danger" />
        <StatCard label="Pass rate" value={fmtPct(a.pass_percent)} icon={CheckCircle2} tone="warning" hint={a.not_entered_count > 0 ? `${a.not_entered_count} not entered` : undefined} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Grade distribution</CardTitle></CardHeader><CardContent><div className="h-60" role="img" aria-label="Bar chart of students per grade"><ResponsiveContainer width="100%" height="100%"><BarChart data={dist} margin={{ left: -20, right: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="grade" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="students" fill="#1E40AF" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></CardContent></Card>
        <Card><CardHeader><CardTitle>Subject average vs pass rate</CardTitle></CardHeader><CardContent><div className="h-60" role="img" aria-label="Bar chart of subject average and pass rate"><ResponsiveContainer width="100%" height="100%"><BarChart data={subj} margin={{ left: -20, right: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} /><Tooltip formatter={(v) => `${num(v as number).toFixed(1)}%`} /><Legend /><Bar dataKey="average" name="Average %" fill="#38BDF8" radius={[4, 4, 0, 0]} /><Bar dataKey="passRate" name="Pass rate %" fill="#16A34A" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></CardContent></Card>
      </div>
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><Users className="h-4 w-4 text-primary" aria-hidden />Top 5 students</CardTitle></CardHeader>
        <CardContent>
          {a.top_students.length === 0 ? <p className="text-sm text-muted-foreground">No complete results yet.</p> : (
            <ol className="divide-y divide-border">{a.top_students.map((s) => <li key={s.student_id} className="flex items-center gap-3 py-2.5 text-sm"><span className="w-6 text-center font-bold tabular-nums">{s.rank ?? "-"}</span><span className="flex-1 font-medium">{s.full_name}<span className="ml-2 text-xs font-normal text-muted-foreground">Roll no. {s.roll_no}</span></span><span className="font-semibold tabular-nums">{fmtPct(s.percentage)}</span></li>)}</ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** F4/F6: exam detail page. Admin gets progress, entry, subjects, publish; CEO sees results + analytics read-only. */
export function ExamDetail({ examId }: { examId: string }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [tab, setTab] = useState<Tab>(isAdmin ? "progress" : "results");
  const [publish, setPublish] = useState<"publish" | "unpublish" | null>(null);
  const exam = useQuery({ queryKey: ["exam", examId], queryFn: () => api<Exam>(`/exams/${examId}`) });
  if (exam.isLoading) return <ListSkeleton rows={3} />;
  if (exam.error || !exam.data) return <ErrorState error={exam.error} onRetry={() => exam.refetch()} />;
  const e = exam.data;
  const tabs: { key: Tab; label: string }[] = [
    ...(isAdmin ? [{ key: "progress" as const, label: "Marks progress" }] : []),
    { key: "results", label: "Results" }, { key: "analytics", label: "Analytics" },
    ...(isAdmin ? [{ key: "entry" as const, label: "Enter marks" }, { key: "subjects" as const, label: "Subjects" }] : []),
  ];
  return (
    <>
      <Link href={`/${user?.role}/results`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />All exams</Link>
      <PageHeader title={e.name} description={`${e.class_name} · ${e.type}`}
        actions={<><StatusBadge status={e.is_published ? "published" : "draft"} />{isAdmin && <Button variant="outline" onClick={() => setPublish(e.is_published ? "unpublish" : "publish")}>{e.is_published ? "Unpublish" : "Publish"}</Button>}</>} />
      <Tabs label="Exam sections" tabs={tabs} value={tab} onChange={setTab} />
      {tab === "progress" && <Progress examId={e.id} />}
      {tab === "results" && <ResultsSheet exam={e} />}
      {tab === "analytics" && <Analytics examId={e.id} />}
      {tab === "entry" && <MarksEntry fixedExam={e} embedded />}
      {tab === "subjects" && <SubjectsEditor examId={e.id} locked={e.is_published} />}
      {publish && <PublishDialog exam={e} mode={publish} onClose={() => setPublish(null)} />}
    </>
  );
}
