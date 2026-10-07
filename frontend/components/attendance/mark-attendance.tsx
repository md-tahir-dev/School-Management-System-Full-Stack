"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, MessageSquare, Pencil } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Segmented, STUDENT_OPTIONS } from "@/components/attendance/segmented";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useUnsavedWarning } from "@/hooks/use-unsaved-warning";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, todayIn } from "@/lib/format";
import { useClasses, useMyTeacher, useSections, useSettings } from "@/lib/queries";
import type { AttendanceStatus, BulkResult, Holiday, Page, Roster } from "@/lib/types";
import { cn, initials } from "@/lib/utils";

interface Row { status: AttendanceStatus | null; remarks: string }
type Draft = Record<string, Row>;

function toDraft(r: Roster): Draft {
  return Object.fromEntries(r.students.map((s) => [s.student_id, { status: (s.status as AttendanceStatus | null) ?? null, remarks: s.remarks ?? "" }]));
}

/** F1: teacher (and admin) daily attendance marking. */
export function MarkAttendance() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const settings = useSettings();
  const isTeacher = user?.role === "teacher";
  const today = todayIn(settings.data?.timezone);

  // Teachers only see their assigned class-section pairs; admins pick any.
  const me = useMyTeacher();
  const classes = useClasses();
  const pairs = useMemo(() => {
    const seen = new Map<string, { class_id: string; class_name: string; section_id: string | null; section_name: string | null }>();
    for (const a of me.data?.assignments ?? []) seen.set(`${a.class_id}|${a.section_id}`, a);
    return [...seen.values()];
  }, [me.data]);

  const [classId, setClassId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [date, setDate] = useState("");
  const sections = useSections(isTeacher ? undefined : classId || undefined);

  useEffect(() => { if (!date && settings.data) setDate(today); }, [date, today, settings.data]);
  useEffect(() => {
    if (isTeacher && !classId && pairs[0]) { setClassId(pairs[0].class_id); setSectionId(pairs[0].section_id ?? ""); }
  }, [isTeacher, pairs, classId]);

  const teacherSections = pairs.filter((p) => p.class_id === classId);
  const sectionOptions = isTeacher ? teacherSections.map((p) => ({ id: p.section_id ?? "", name: p.section_name ?? "-" })) : (sections.data ?? []).map((s) => ({ id: s.id, name: s.name }));
  const classOptions = isTeacher ? [...new Map(pairs.map((p) => [p.class_id, p.class_name])).entries()].map(([id, name]) => ({ id, name })) : (classes.data ?? []).map((c) => ({ id: c.id, name: c.name }));

  const year = date.slice(0, 4);
  const holidays = useQuery({
    queryKey: ["holidays", year],
    queryFn: () => api<Page<Holiday>>("/holidays", { query: { year, page_size: 100 } }),
    enabled: !!year,
  });
  const holidayOnDate = holidays.data?.items.find((h) => h.date === date);

  const rosterKey = ["attendance-roster", classId, sectionId, date];
  const roster = useQuery({
    queryKey: rosterKey,
    queryFn: ({ signal }) => api<Roster>("/attendance", { query: { class_id: classId, section_id: sectionId, date }, signal }),
    enabled: !!classId && !!sectionId && !!date,
  });

  const [draft, setDraft] = useState<Draft>({});
  const [serverSnapshot, setServerSnapshot] = useState<Draft>({});
  useEffect(() => {
    if (roster.data) { const d = toDraft(roster.data); setDraft(d); setServerSnapshot(d); }
  }, [roster.data]);

  const dirtyCount = useMemo(
    () => Object.keys(draft).filter((id) => draft[id]?.status !== serverSnapshot[id]?.status || draft[id]?.remarks !== serverSnapshot[id]?.remarks).length,
    [draft, serverSnapshot],
  );
  useUnsavedWarning(dirtyCount > 0);

  const counts = useMemo(() => {
    const c = { present: 0, absent: 0, late: 0, sick: 0, unmarked: 0 };
    for (const r of Object.values(draft)) { if (r.status) c[r.status] += 1; else c.unmarked += 1; }
    return c;
  }, [draft]);

  const [remarkOpen, setRemarkOpen] = useState<Set<string>>(new Set());
  const alreadySaved = !!roster.data?.students.some((s) => s.status);
  const locked = !roster.data?.is_editable || !!holidayOnDate || roster.data?.is_holiday;

  function setRow(id: string, patch: Partial<Row>) {
    setDraft((d) => ({ ...d, [id]: { status: null, remarks: "", ...d[id], ...patch } }));
  }
  function markAllPresent() {
    setDraft((d) => Object.fromEntries(Object.entries(d).map(([id, r]) => [id, { ...r, status: "present" as const }])));
  }

  const save = useMutation({
    mutationFn: () => {
      const records = Object.entries(draft).filter(([, r]) => r.status).map(([student_id, r]) => ({ student_id, status: r.status!, remarks: r.remarks.trim() || null }));
      return api<BulkResult>("/attendance/bulk", { method: "POST", body: { class_id: classId, section_id: sectionId, date, records } });
    },
    onSuccess: (res) => {
      toast.success(`Attendance saved (${res.saved} students)`);
      setServerSnapshot(draft);
      for (const key of ["attendance-roster", "student-attendance", "dashboard", "attendance-report"]) qc.invalidateQueries({ queryKey: [key] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save attendance. Your changes are still here."),
  });

  const noAssignments = isTeacher && !me.isLoading && pairs.length === 0;

  return (
    <>
      <PageHeader title="Mark attendance" description="Pick a class and date, mark everyone present, then change the exceptions." />
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-3">
        <Field label="Class">
          <Select value={classId} onChange={(e) => { setClassId(e.target.value); setSectionId(""); }}>
            <option value="" disabled>Select class</option>
            {classOptions.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        <Field label="Section">
          <Select value={sectionId} onChange={(e) => setSectionId(e.target.value)} disabled={!classId}>
            <option value="" disabled>Select section</option>
            {sectionOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
        <Field label="Date" hint={holidayOnDate ? undefined : "Future dates are not allowed."}>
          <Input type="date" value={date} max={today} onChange={(e) => setDate(e.target.value)} aria-invalid={!!holidayOnDate} />
        </Field>
      </Card>

      {noAssignments && <EmptyState title="No classes assigned yet" hint="Ask the administrator to assign you to a class and section." />}
      {(holidayOnDate || roster.data?.is_holiday) && (
        <div role="status" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {dateLabel(date)} is a holiday{(holidayOnDate?.name ?? roster.data?.holiday_name) ? ` (${holidayOnDate?.name ?? roster.data?.holiday_name})` : ""}. Attendance can't be marked.
        </div>
      )}
      {roster.data && !roster.data.is_editable && !roster.data.is_holiday && !holidayOnDate && (
        <div role="status" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">This date can't be edited (weekly off day or past the backdate limit).</div>
      )}

      {roster.isLoading && <ListSkeleton />}
      {roster.error && <ErrorState error={roster.error} onRetry={() => roster.refetch()} />}
      {roster.data && roster.data.students.length === 0 && <EmptyState title="No active students in this section on this date" />}

      {roster.data && roster.data.students.length > 0 && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={markAllPresent} disabled={locked}><CheckCheck className="h-4 w-4" />Mark all present</Button>
            {alreadySaved && <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-800"><Pencil className="h-3 w-3" />Editing saved attendance</span>}
          </div>
          <ul className="space-y-2 pb-28">
            {roster.data.students.map((s) => {
              const row = draft[s.student_id];
              const open = remarkOpen.has(s.student_id) || !!row?.remarks;
              return (
                <li key={s.student_id} className={cn("rounded-lg border border-border bg-card p-3", row && row.status !== serverSnapshot[s.student_id]?.status && "border-primary/50")}>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      {s.photo_url
                        // eslint-disable-next-line @next/next/no-img-element
                        ? <img src={s.photo_url} alt="" className="h-10 w-10 shrink-0 rounded-full object-cover" />
                        : <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-primary">{initials(s.full_name)}</span>}
                      <div className="min-w-0">
                        <p className="truncate font-medium">{s.full_name}</p>
                        <p className="text-xs text-muted-foreground">Roll no. {s.roll_no}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Segmented label={`Attendance for ${s.full_name}`} options={STUDENT_OPTIONS} value={row?.status ?? null} onChange={(v) => setRow(s.student_id, { status: v })} disabled={locked} />
                      <Button variant="ghost" size="icon" className="h-11 w-11" aria-label={`Remarks for ${s.full_name}`} aria-expanded={open} onClick={() => setRemarkOpen((p) => new Set(p).add(s.student_id))}>
                        <MessageSquare className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {open && (
                    <Input className="mt-2 h-11" placeholder="Remarks (optional)" aria-label={`Remarks for ${s.full_name}`} maxLength={500} value={row?.remarks ?? ""} disabled={locked} onChange={(e) => setRow(s.student_id, { remarks: e.target.value })} />
                  )}
                </li>
              );
            })}
          </ul>

          <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-card/95 px-4 py-3 backdrop-blur lg:left-64">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-3">
              <p className="text-sm font-semibold tabular-nums" aria-live="polite">
                P {counts.present} · A {counts.absent} · L {counts.late} · S {counts.sick}
                {counts.unmarked > 0 && <span className="ml-2 font-normal text-muted-foreground">{counts.unmarked} unmarked</span>}
              </p>
              <Button size="lg" className="min-h-[44px]" onClick={() => save.mutate()} loading={save.isPending} disabled={locked || dirtyCount === 0 || counts.present + counts.absent + counts.late + counts.sick === 0}>
                Save{dirtyCount > 0 ? ` (${dirtyCount})` : ""}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
