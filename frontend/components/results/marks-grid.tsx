"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useUnsavedWarning } from "@/hooks/use-unsaved-warning";
import { api, ApiError } from "@/lib/api";
import { fmtMarks, num } from "@/lib/format";
import { subjectStatus } from "@/lib/grading";
import type { MarksSheet } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Cell { value: string; absent: boolean }

/** F5 spreadsheet-style grid: one subject, one section. Tab/Enter/arrows move, Excel columns paste. */
export function MarksGrid({ examId, sectionId, subjectId, isAdmin }: { examId: string; sectionId: string; subjectId: string; isAdmin: boolean }) {
  const qc = useQueryClient();
  const key = ["marks-sheet", examId, sectionId, subjectId];
  const sheet = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => api<MarksSheet>(`/exams/${examId}/marks-sheet`, { query: { section_id: sectionId, subject_id: subjectId }, signal }),
  });
  const base = useMemo<Record<string, Cell>>(
    () => Object.fromEntries((sheet.data?.rows ?? []).map((r) => [r.student_id, { value: r.obtained_marks === null || r.obtained_marks === undefined ? "" : fmtMarks(r.obtained_marks), absent: r.is_absent }])),
    [sheet.data],
  );
  const [cells, setCells] = useState<Record<string, Cell>>({});
  const [reason, setReason] = useState("");
  useEffect(() => { setCells(base); }, [base]);

  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const rows = sheet.data?.rows ?? [];
  const locked = sheet.data?.is_locked ?? false; // teacher + published
  const total = rows[0] ? num(rows[0].total_marks) : 0;

  const errorFor = (c: Cell | undefined, totalMarks: number) => {
    if (!c || c.absent || c.value === "") return null;
    const n = Number(c.value);
    if (!Number.isFinite(n) || n < 0) return "Enter a number 0 or above";
    if (n > totalMarks) return `Can't be above ${fmtMarks(totalMarks)}`;
    return null;
  };
  const dirtyIds = rows.filter((r) => { const c = cells[r.student_id]; const b = base[r.student_id]; return c && b && (c.value !== b.value || c.absent !== b.absent); }).map((r) => r.student_id);
  const hasErrors = rows.some((r) => errorFor(cells[r.student_id], num(r.total_marks)));
  useUnsavedWarning(dirtyIds.length > 0);

  function setCell(id: string, patch: Partial<Cell>) { setCells((p) => ({ ...p, [id]: { value: "", absent: false, ...p[id], ...patch } })); }
  function focusRow(i: number) { const el = inputs.current[Math.max(0, Math.min(rows.length - 1, i))]; el?.focus(); el?.select(); }
  function onPaste(e: React.ClipboardEvent, start: number) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\n") && !text.includes("\t")) return; // single value: normal paste
    e.preventDefault();
    const lines = text.replace(/\r/g, "").split("\n").filter((l, i, a) => l.trim() !== "" || i < a.length - 1);
    setCells((p) => {
      const next = { ...p };
      lines.forEach((line, k) => { const row = rows[start + k]; if (row) next[row.student_id] = { value: (line.split("\t")[0] ?? "").trim(), absent: false }; });
      return next;
    });
    toast.message(`Pasted ${Math.min(lines.length, rows.length - start)} values`);
  }

  const save = useMutation({
    mutationFn: () => {
      const entries = dirtyIds.flatMap((id) => {
        const c = cells[id]!;
        if (!c.absent && c.value === "") return []; // a blank can't be saved; skip it
        return [{ student_id: id, subject_id: subjectId, obtained_marks: c.absent ? 0 : Number(c.value), is_absent: c.absent }];
      });
      return api<MarksSheet>(`/exams/${examId}/marks`, { method: "PUT", query: { section_id: sectionId, subject_id: subjectId }, body: { entries, reason: reason.trim() || null } });
    },
    onSuccess: (data) => {
      toast.success("Marks saved");
      qc.setQueryData(key, data);
      for (const k of ["exam-results", "exam-analytics", "exam-progress", "student-results", "student-entry", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save marks. Your edits are still here."),
  });

  if (sheet.isLoading) return <ListSkeleton rows={8} />;
  if (sheet.error) return <ErrorState error={sheet.error} onRetry={() => sheet.refetch()} />;
  if (rows.length === 0) return <EmptyState title="No students in this section" />;

  return (
    <div className="space-y-3">
      {locked && <p role="status" className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">This exam is published. Marks are read-only for teachers.</p>}
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead className="border-b border-border bg-slate-50 text-muted-foreground">
              <tr>
                <th scope="col" className="sticky left-0 z-10 bg-slate-50 px-4 py-3 font-semibold">Roll no.</th>
                <th scope="col" className="px-4 py-3 font-semibold">Name</th>
                <th scope="col" className="px-4 py-3 font-semibold">Obtained (/{fmtMarks(total)})</th>
                <th scope="col" className="px-4 py-3 font-semibold">Absent</th>
                <th scope="col" className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const c = cells[r.student_id] ?? { value: "", absent: false };
                const err = errorFor(c, num(r.total_marks));
                const dirty = dirtyIds.includes(r.student_id);
                const entered = c.absent || (c.value !== "" && !err);
                const status = entered ? subjectStatus({ total: num(r.total_marks), passing: num(r.passing_marks), obtained: c.absent ? 0 : Number(c.value), absent: c.absent }) : null;
                return (
                  <tr key={r.student_id} className={cn("border-b border-border/60 last:border-0", dirty && "bg-amber-50/70")}>
                    <td className={cn("sticky left-0 z-10 px-4 py-2 font-medium", dirty ? "bg-amber-50" : "bg-card")}>{r.roll_no}</td>
                    <td className="px-4 py-2">{r.full_name}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <Input
                          ref={(el) => { inputs.current[i] = el; }}
                          inputMode="decimal" className={cn("h-9 w-24", err && "border-danger")} aria-label={`Marks for ${r.full_name}`} aria-invalid={!!err}
                          aria-describedby={err ? `err-${r.student_id}` : undefined} value={c.absent ? "" : c.value} disabled={locked || c.absent}
                          onChange={(e) => setCell(r.student_id, { value: e.target.value })}
                          onPaste={(e) => onPaste(e, i)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === "ArrowDown") { e.preventDefault(); focusRow(i + 1); }
                            else if (e.key === "ArrowUp") { e.preventDefault(); focusRow(i - 1); }
                          }}
                        />
                        <span className="text-xs text-muted-foreground">/ {fmtMarks(r.total_marks)}</span>
                      </div>
                      {err && <p id={`err-${r.student_id}`} className="mt-1 text-xs text-danger">{err}</p>}
                    </td>
                    <td className="px-4 py-2"><input type="checkbox" className="h-5 w-5" aria-label={`${r.full_name} absent`} checked={c.absent} disabled={locked} onChange={(e) => setCell(r.student_id, { absent: e.target.checked })} /></td>
                    <td className="px-4 py-2">{status ? <StatusBadge status={status === "AB" ? "absent" : status} label={status} /> : <span className="text-muted-foreground">-</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {isAdmin && (
        <div className="max-w-md">
          <label className="flex flex-col gap-1.5 text-sm"><span className="font-medium">Reason for change</span>
            <Input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="Required if the exam is already published" />
          </label>
        </div>
      )}
      <div className="flex items-center gap-3">
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={locked || dirtyIds.length === 0 || hasErrors}>Save changes{dirtyIds.length ? ` (${dirtyIds.length})` : ""}</Button>
        {hasErrors && <p className="text-sm text-danger" role="alert">Fix the highlighted marks to save.</p>}
      </div>
    </div>
  );
}
