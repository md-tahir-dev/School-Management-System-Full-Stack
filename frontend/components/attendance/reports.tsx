"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Flag } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Segmented, TEACHER_OPTIONS } from "@/components/attendance/segmented";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useUnsavedWarning } from "@/hooks/use-unsaved-warning";
import { api, apiBlob, ApiError, saveBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isManager } from "@/lib/role-config";
import { fmtPct, num, todayIn } from "@/lib/format";
import { useClasses, useSections, useSettings } from "@/lib/queries";
import type { BulkResult, ClassAttendanceReport, LowAttendanceOut, OverviewOut, TeacherAttendanceStatus, TeacherRoster } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CalendarCheck, Users, UserX } from "lucide-react";

type Tab = "overview" | "class" | "low" | "teachers";

function Overview({ today }: { today: string }) {
  const [date, setDate] = useState(today);
  const q = useQuery({
    queryKey: ["attendance-report", "overview", date],
    queryFn: ({ signal }) => api<OverviewOut>("/reports/attendance/overview", { query: { date }, signal }),
  });
  return (
    <div className="space-y-4">
      <Field label="Date"><Input type="date" className="w-48" value={date} max={today} onChange={(e) => setDate(e.target.value)} /></Field>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="School present %" value={q.data ? fmtPct(q.data.school_present_percent) : undefined} icon={CalendarCheck} tone="success" loading={q.isLoading} />
            <StatCard label="Absent students" value={q.data?.absent_count} icon={UserX} tone="danger" loading={q.isLoading} />
            <StatCard label="Sections not yet marked" value={q.data?.unmarked_sections} icon={Flag} tone={q.data && q.data.unmarked_sections > 0 ? "warning" : "primary"} loading={q.isLoading} />
          </div>
          {q.isLoading ? <ListSkeleton rows={5} /> : (
            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[32rem] text-left text-sm">
                  <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr>{["Class", "Section", "Present %", "Absent", "Status"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
                  <tbody>
                    {q.data?.sections.map((s) => (
                      <tr key={`${s.class_id}${s.section_id}`} className={cn("border-b border-border/60 last:border-0", !s.marked && "bg-red-50")}>
                        <td className="px-4 py-3 font-medium">{s.class_name}</td>
                        <td className="px-4 py-3">{s.section_name ?? "-"}</td>
                        <td className="px-4 py-3 tabular-nums">{s.marked ? fmtPct(s.present_percent) : "-"}</td>
                        <td className="px-4 py-3 tabular-nums">{s.marked ? s.absent_count : "-"}</td>
                        <td className="px-4 py-3">{s.marked ? <span className="text-green-700">Marked</span> : <span className="inline-flex items-center gap-1 font-semibold text-danger"><Flag className="h-3.5 w-3.5" aria-hidden />Not marked</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {q.data?.sections.length === 0 && <EmptyState title="No sections yet" />}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ClassReport({ today, threshold }: { today: string; threshold: number }) {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const sections = useSections(classId || undefined);
  const [from, setFrom] = useState(`${today.slice(0, 8)}01`);
  const [to, setTo] = useState(today);
  const params = { class_id: classId, section_id: sectionId, from, to };
  const q = useQuery({
    queryKey: ["attendance-report", "class", params],
    queryFn: ({ signal }) => api<ClassAttendanceReport>("/reports/attendance/class", { query: params, signal }),
    enabled: !!classId && !!sectionId && !!from && !!to,
  });
  async function exportCsv() {
    try { saveBlob(await apiBlob("/reports/attendance/class", { ...params, format: "csv" }), `attendance-${from}-${to}.csv`); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Export failed"); }
  }
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Class"><Select value={classId} onChange={(e) => { setClassId(e.target.value); setSectionId(""); }}><option value="" disabled>Select class</option>{classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Section"><Select value={sectionId} onChange={(e) => setSectionId(e.target.value)} disabled={!classId}><option value="" disabled>Select section</option>{sections.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
        <Field label="From"><Input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} /></Field>
      </Card>
      {!classId || !sectionId ? <EmptyState title="Choose a class and section" /> : q.isLoading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border p-3">
            <p className="text-sm text-muted-foreground">{q.data?.rows.length ?? 0} students, lowest attendance first. Red rows are below {threshold}%.</p>
            <Button variant="outline" size="sm" onClick={exportCsv}><Download className="h-3.5 w-3.5" />Export CSV</Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr>{["Roll no.", "Name", "Present", "Absent", "Late", "Sick", "%"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
              <tbody>
                {q.data?.rows.map((r) => (
                  <tr key={r.student_id} className={cn("border-b border-border/60 last:border-0", num(r.percentage) < threshold && "bg-red-50 text-red-900")}>
                    <td className="px-4 py-3">{r.roll_no}</td><td className="px-4 py-3 font-medium">{r.full_name}</td>
                    <td className="px-4 py-3 tabular-nums">{r.present}</td><td className="px-4 py-3 tabular-nums">{r.absent}</td>
                    <td className="px-4 py-3 tabular-nums">{r.late}</td><td className="px-4 py-3 tabular-nums">{r.sick}</td>
                    <td className="px-4 py-3 font-semibold tabular-nums">{fmtPct(r.percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {q.data?.rows.length === 0 && <EmptyState title="No attendance recorded in this range" />}
        </div>
      )}
    </div>
  );
}

function LowAttendance({ defaultThreshold }: { defaultThreshold: number }) {
  const [threshold, setThreshold] = useState(String(defaultThreshold));
  const t = Math.min(100, Math.max(1, Number(threshold) || defaultThreshold));
  const q = useQuery({
    queryKey: ["attendance-report", "low", t],
    queryFn: ({ signal }) => api<LowAttendanceOut>("/reports/attendance/low", { query: { threshold: t }, signal }),
  });
  return (
    <div className="space-y-4">
      <Field label="Show students below (%)"><Input type="number" min={1} max={100} className="w-32" value={threshold} onChange={(e) => setThreshold(e.target.value)} /></Field>
      {q.isLoading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data?.students.length === 0 ? <EmptyState title="Nobody is below this threshold" /> : (
        <div className="overflow-hidden rounded-lg border border-border bg-card"><div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr>{["Student", "Class", "Attendance", "Parent phone"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
            <tbody>
              {q.data?.students.map((s) => (
                <tr key={s.student_id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-3"><p className="font-medium">{s.full_name}</p><p className="text-xs text-muted-foreground">Roll no. {s.roll_no}</p></td>
                  <td className="px-4 py-3">{s.class_name}{s.section_name ? ` · ${s.section_name}` : ""}</td>
                  <td className="px-4 py-3 font-semibold tabular-nums text-danger">{fmtPct(s.percentage)}</td>
                  <td className="px-4 py-3">{s.guardian_phone ? <a className="text-primary hover:underline" href={`tel:${s.guardian_phone}`}>{s.guardian_phone}</a> : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
    </div>
  );
}

function TeacherAttendance({ today, canEdit }: { today: string; canEdit: boolean }) {
  const qc = useQueryClient();
  const [date, setDate] = useState(today);
  const q = useQuery({
    queryKey: ["teacher-attendance", date],
    queryFn: ({ signal }) => api<TeacherRoster>("/teacher-attendance", { query: { date }, signal }),
  });
  const [draft, setDraft] = useState<Record<string, TeacherAttendanceStatus | null>>({});
  const [snap, setSnap] = useState<Record<string, TeacherAttendanceStatus | null>>({});
  useEffect(() => {
    if (q.data) { const d = Object.fromEntries(q.data.teachers.map((t) => [t.teacher_id, (t.status as TeacherAttendanceStatus | null) ?? null])); setDraft(d); setSnap(d); }
  }, [q.data]);
  const dirty = useMemo(() => Object.keys(draft).filter((id) => draft[id] !== snap[id]).length, [draft, snap]);
  useUnsavedWarning(dirty > 0);
  const save = useMutation({
    mutationFn: () => api<BulkResult>("/teacher-attendance/bulk", { method: "POST", body: { date, records: Object.entries(draft).filter(([, s]) => s).map(([teacher_id, status]) => ({ teacher_id, status })) } }),
    onSuccess: (r) => { toast.success(`Teacher attendance saved (${r.saved})`); setSnap(draft); qc.invalidateQueries({ queryKey: ["teacher-attendance"] }); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save"),
  });
  const editable = canEdit && !!q.data?.is_editable;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Date"><Input type="date" className="w-48" value={date} max={today} onChange={(e) => setDate(e.target.value)} /></Field>
        {canEdit && <Button className="min-h-[44px]" onClick={() => save.mutate()} loading={save.isPending} disabled={!editable || dirty === 0}>Save{dirty ? ` (${dirty})` : ""}</Button>}
        {!canEdit && <p className="pb-2 text-sm text-muted-foreground">Read-only view.</p>}
      </div>
      {q.isLoading ? <ListSkeleton /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.data && !q.data.is_editable && canEdit ? (
        <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">This date can't be edited (holiday, weekly off, or in the future).</div>
      ) : null}
      {q.data?.teachers.length === 0 && <EmptyState title="No active teachers" />}
      <ul className="space-y-2">
        {q.data?.teachers.map((t) => (
          <li key={t.teacher_id} className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:flex-row sm:items-center sm:justify-between">
            <div><p className="font-medium">{t.full_name}</p><p className="text-xs text-muted-foreground">{t.employee_id}</p></div>
            <Segmented label={`Attendance for ${t.full_name}`} options={TEACHER_OPTIONS} value={draft[t.teacher_id] ?? null} onChange={(v) => setDraft((d) => ({ ...d, [t.teacher_id]: v }))} disabled={!editable} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** F2: Admin/CEO reports. CEO gets read-only teacher attendance; there are no edit controls for CEO. */
export function AttendanceReports() {
  const { user } = useAuth();
  const settings = useSettings();
  const [tab, setTab] = useState<Tab>("overview");
  const today = todayIn(settings.data?.timezone);
  const threshold = settings.data?.attendance_alert_threshold ?? 75;
  if (!settings.data) return <ListSkeleton rows={3} />;
  return (
    <>
      <PageHeader title="Attendance" description="School-wide attendance, reports, and teacher attendance." />
      <Tabs label="Attendance sections" value={tab} onChange={setTab} tabs={[
        { key: "overview", label: "Overview" }, { key: "class", label: "Class report" }, { key: "low", label: "Low attendance" }, { key: "teachers", label: "Teacher attendance" },
      ]} />
      {tab === "overview" && <Overview today={today} />}
      {tab === "class" && <ClassReport today={today} threshold={threshold} />}
      {tab === "low" && <LowAttendance defaultThreshold={threshold} />}
      {tab === "teachers" && <TeacherAttendance today={today} canEdit={isManager(user?.role)} />}
    </>
  );
}
