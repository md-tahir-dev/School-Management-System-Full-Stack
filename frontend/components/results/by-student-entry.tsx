"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useUnsavedWarning } from "@/hooks/use-unsaved-warning";
import { useDebounce } from "@/hooks/use-debounce";
import { api, ApiError } from "@/lib/api";
import { fmtMarks, fmtPct, num } from "@/lib/format";
import { subjectStatus, summarize } from "@/lib/grading";
import { useSettings } from "@/lib/queries";
import type { Exam, Page, StudentEntry, StudentListItem } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Cell { value: string; absent: boolean }

/** Live totals/percentage/grade come from lib/grading.ts (mirror of the server rules); the server stays the source of truth. */
export function ByStudentEntry({ exam, isAdmin }: { exam: Exam; isAdmin: boolean }) {
  const qc = useQueryClient();
  const settings = useSettings();
  const [search, setSearch] = useState("");
  const q = useDebounce(search, 300);
  const [studentId, setStudentId] = useState<string | null>(null);

  const students = useQuery({
    queryKey: ["students-pick", exam.class_id, q],
    queryFn: ({ signal }) => api<Page<StudentListItem>>("/students", { query: { class_id: exam.class_id, q, page_size: 8, status: "active" }, signal }),
    placeholderData: keepPreviousData,
  });
  const entry = useQuery({
    queryKey: ["student-entry", exam.id, studentId],
    queryFn: ({ signal }) => api<StudentEntry>(`/exams/${exam.id}/students/${studentId}/entry`, { signal }),
    enabled: !!studentId,
  });

  const base = useMemo<Record<string, Cell>>(
    () => Object.fromEntries((entry.data?.subjects ?? []).map((s) => [s.subject_id, { value: s.obtained_marks === null || s.obtained_marks === undefined ? "" : fmtMarks(s.obtained_marks), absent: s.is_absent }])),
    [entry.data],
  );
  const [cells, setCells] = useState<Record<string, Cell>>({});
  const [reason, setReason] = useState("");
  useEffect(() => setCells(base), [base]);

  const subjects = entry.data?.subjects ?? [];
  const errorFor = (c: Cell | undefined, total: number) => (!c || c.absent || c.value === "" ? null : !Number.isFinite(Number(c.value)) || Number(c.value) < 0 ? "Enter a number 0 or above" : Number(c.value) > total ? `Can't be above ${fmtMarks(total)}` : null);
  const dirty = subjects.filter((s) => { const c = cells[s.subject_id]; const b = base[s.subject_id]; return c && b && (c.value !== b.value || c.absent !== b.absent); });
  const hasErrors = subjects.some((s) => errorFor(cells[s.subject_id], num(s.total_marks)));
  useUnsavedWarning(dirty.length > 0);

  const entered = subjects.filter((s) => { const c = cells[s.subject_id]; return c && (c.absent || (c.value !== "" && !errorFor(c, num(s.total_marks)))); });
  const complete = entered.length === subjects.length && subjects.length > 0;
  const live = summarize(entered.map((s) => { const c = cells[s.subject_id]!; return { total: num(s.total_marks), passing: num(s.passing_marks), obtained: c.absent ? 0 : Number(c.value), absent: c.absent }; }), settings.data?.fail_if_any_subject_failed ?? true);

  const save = useMutation({
    mutationFn: () => api<StudentEntry>(`/exams/${exam.id}/students/${studentId}/entry`, {
      method: "PUT",
      body: { subjects: dirty.filter((s) => { const c = cells[s.subject_id]!; return c.absent || c.value !== ""; }).map((s) => { const c = cells[s.subject_id]!; return { student_id: studentId, subject_id: s.subject_id, obtained_marks: c.absent ? 0 : Number(c.value), is_absent: c.absent }; }), reason: reason.trim() || null },
    }),
    onSuccess: (data) => {
      toast.success("Marks saved");
      qc.setQueryData(["student-entry", exam.id, studentId], data);
      for (const k of ["exam-results", "exam-analytics", "exam-progress", "marks-sheet", "student-results", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save marks"),
  });

  const locked = exam.is_published && !isAdmin;
  return (
    <div className="grid gap-5 lg:grid-cols-[18rem_1fr]">
      <div className="space-y-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input className="pl-9" placeholder="Search name" aria-label="Search student by name" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {students.isLoading ? <ListSkeleton rows={4} /> : (
          <ul className="space-y-1.5">
            {students.data?.items.map((s) => (
              <li key={s.id}>
                <button type="button" onClick={() => setStudentId(s.id)} aria-pressed={studentId === s.id}
                  className={cn("w-full rounded-md border border-border bg-card px-3 py-2.5 text-left text-sm hover:bg-muted", studentId === s.id && "border-primary bg-blue-50")}>
                  <span className="block font-medium">{s.full_name}</span>
                  <span className="text-xs text-muted-foreground">Roll no. {s.roll_no}{s.section_name ? ` · ${s.section_name}` : ""}</span>
                </button>
              </li>
            ))}
            {students.data?.items.length === 0 && <li className="p-2 text-sm text-muted-foreground">No students found.</li>}
          </ul>
        )}
      </div>

      <div>
        {!studentId ? <p className="rounded-lg border border-dashed border-border bg-card p-10 text-center text-sm text-muted-foreground">Pick a student to enter all subjects at once.</p>
          : entry.isLoading ? <ListSkeleton rows={5} /> : entry.error ? <ErrorState error={entry.error} onRetry={() => entry.refetch()} /> : entry.data && (
          <div className="space-y-4">
            <div><h3 className="text-lg font-semibold">{entry.data.full_name}</h3><p className="text-sm text-muted-foreground">Roll no. {entry.data.roll_no}</p></div>
            <div className="overflow-hidden rounded-lg border border-border bg-card"><div className="overflow-x-auto">
              <table className="w-full min-w-[30rem] text-left text-sm">
                <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr>{["Subject", "Obtained", "Absent", "Status"].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr></thead>
                <tbody>
                  {subjects.map((s) => {
                    const c = cells[s.subject_id] ?? { value: "", absent: false };
                    const err = errorFor(c, num(s.total_marks));
                    const ok = c.absent || (c.value !== "" && !err);
                    const st = ok ? subjectStatus({ total: num(s.total_marks), passing: num(s.passing_marks), obtained: c.absent ? 0 : Number(c.value), absent: c.absent }) : null;
                    return (
                      <tr key={s.subject_id} className="border-b border-border/60 last:border-0">
                        <td className="px-4 py-2 font-medium">{s.subject_name}<span className="block text-xs font-normal text-muted-foreground">Pass at {fmtMarks(s.passing_marks)}</span></td>
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <Input inputMode="decimal" className={cn("h-9 w-24", err && "border-danger")} aria-label={`${s.subject_name} marks`} aria-invalid={!!err} disabled={locked || c.absent} value={c.absent ? "" : c.value}
                              onChange={(e) => setCells((p) => ({ ...p, [s.subject_id]: { value: e.target.value, absent: false } }))} />
                            <span className="text-xs text-muted-foreground">/ {fmtMarks(s.total_marks)}</span>
                          </div>
                          {err && <p className="mt-1 text-xs text-danger">{err}</p>}
                        </td>
                        <td className="px-4 py-2"><input type="checkbox" className="h-5 w-5" aria-label={`${s.subject_name} absent`} disabled={locked} checked={c.absent} onChange={(e) => setCells((p) => ({ ...p, [s.subject_id]: { value: "", absent: e.target.checked } }))} /></td>
                        <td className="px-4 py-2">{st ? <StatusBadge status={st === "AB" ? "absent" : st} label={st} /> : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div></div>

            <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-4" aria-live="polite">
              <div><p className="text-xs text-muted-foreground">Total</p><p className="text-lg font-bold tabular-nums">{fmtMarks(live.totalObtained)} / {fmtMarks(live.totalPossible)}</p></div>
              <div><p className="text-xs text-muted-foreground">Percentage</p><p className="text-lg font-bold tabular-nums">{complete ? fmtPct(live.percentage) : "-"}</p></div>
              <div><p className="text-xs text-muted-foreground">Grade</p><p className="text-lg font-bold">{complete ? live.grade : "-"}</p></div>
              <div><p className="text-xs text-muted-foreground">Result</p>{complete ? <StatusBadge status={live.isPass ? "pass" : "fail"} label={live.isPass ? "Pass" : "Fail"} /> : <p className="text-sm text-muted-foreground">Incomplete</p>}</div>
            </div>
            {isAdmin && <Input className="max-w-md" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required if the exam is already published)" aria-label="Reason for change" />}
            <Button onClick={() => save.mutate()} loading={save.isPending} disabled={locked || dirty.length === 0 || hasErrors}>Save changes{dirty.length ? ` (${dirty.length})` : ""}</Button>
          </div>
        )}
      </div>
    </div>
  );
}
