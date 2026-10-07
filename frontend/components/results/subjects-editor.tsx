"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, ApiError } from "@/lib/api";
import { fmtMarks, num } from "@/lib/format";
import type { ExamSubject } from "@/lib/types";

/** Editable total/passing marks per subject. Only usable while the exam is unpublished. */
export function SubjectsEditor({ examId, locked, onSaved }: { examId: string; locked: boolean; onSaved?: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["exam-subjects", examId], queryFn: () => api<ExamSubject[]>(`/exams/${examId}/subjects`) });
  const [rows, setRows] = useState<{ subject_id: string; subject_name: string; total: string; passing: string }[]>([]);
  useEffect(() => {
    if (q.data) setRows(q.data.map((s) => ({ subject_id: s.subject_id, subject_name: s.subject_name, total: fmtMarks(s.total_marks), passing: fmtMarks(s.passing_marks) })));
  }, [q.data]);

  const invalid = (r: (typeof rows)[number]) => !(num(r.total) > 0) || num(r.passing) < 0 || num(r.passing) > num(r.total);
  const hasError = rows.some(invalid);
  const done = () => { for (const k of ["exam-subjects", "exam-progress", "marks-sheet", "exam"]) qc.invalidateQueries({ queryKey: [k] }); onSaved?.(); };

  const save = useMutation({
    mutationFn: () => api<ExamSubject[]>(`/exams/${examId}/subjects`, { method: "PUT", body: rows.map((r) => ({ subject_id: r.subject_id, total_marks: num(r.total), passing_marks: num(r.passing) })) }),
    onSuccess: () => { toast.success("Exam subjects saved"); done(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't save"),
  });
  const reset = useMutation({
    mutationFn: () => api<ExamSubject[]>(`/exams/${examId}/subjects/reset`, { method: "POST" }),
    onSuccess: () => { toast.success("Reset from class defaults"); done(); },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Couldn't reset"),
  });

  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="space-y-3">
      {locked && <p role="status" className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">Published exams can't change marks structure. Unpublish first.</p>}
      <div className="overflow-hidden rounded-lg border border-border bg-card"><div className="overflow-x-auto">
        <table className="w-full min-w-[26rem] text-left text-sm">
          <thead className="border-b border-border bg-slate-50 text-muted-foreground"><tr><th scope="col" className="px-4 py-3 font-semibold">Subject</th><th scope="col" className="px-4 py-3 font-semibold">Total marks</th><th scope="col" className="px-4 py-3 font-semibold">Passing marks</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.subject_id} className="border-b border-border/60 last:border-0">
                <td className="px-4 py-2 font-medium">{r.subject_name}</td>
                <td className="px-4 py-2"><Input type="number" min={1} className="w-28" aria-label={`Total marks for ${r.subject_name}`} aria-invalid={invalid(r)} value={r.total} disabled={locked} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, total: e.target.value } : x)))} /></td>
                <td className="px-4 py-2"><Input type="number" min={0} className="w-28" aria-label={`Passing marks for ${r.subject_name}`} aria-invalid={invalid(r)} value={r.passing} disabled={locked} onChange={(e) => setRows((p) => p.map((x, j) => (j === i ? { ...x, passing: e.target.value } : x)))} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div></div>
      {hasError && <p className="text-sm text-danger" role="alert">Total must be above 0 and passing marks can't exceed the total.</p>}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={locked || hasError || rows.length === 0}>Save subjects</Button>
        <Button variant="outline" onClick={() => reset.mutate()} loading={reset.isPending} disabled={locked}><RotateCcw className="h-4 w-4" />Reset from class defaults</Button>
      </div>
    </div>
  );
}
