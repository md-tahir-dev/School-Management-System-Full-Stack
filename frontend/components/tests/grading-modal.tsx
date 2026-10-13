"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { fmtMarks } from "@/lib/format";
import type { AttemptResult } from "@/lib/types";

export function GradingModal({ attemptId, testId, canGrade, onClose }: { attemptId: string | null; testId: string; canGrade: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["tests", "attempt", attemptId], queryFn: () => api<AttemptResult>(`/tests/attempts/${attemptId}/result`), enabled: !!attemptId });
  const [marks, setMarks] = useState<Record<string, string>>({});
  useEffect(() => {
    if (q.data) setMarks(Object.fromEntries(q.data.answers.map((a) => [a.question_id, a.marks_awarded != null ? String(Number(a.marks_awarded)) : ""])));
  }, [q.data]);
  const save = useMutation({
    mutationFn: () => api<AttemptResult>(`/tests/attempts/${attemptId}/grade`, { method: "PUT", body: { marks: Object.fromEntries(Object.entries(marks).filter(([, v]) => v !== "")) } }),
    onSuccess: () => { toast.success("Marks saved"); qc.invalidateQueries({ queryKey: ["tests"] }); onClose(); },
    onError: (e) => toast.error(errorText(e, "Couldn't save marks")),
  });
  const r = q.data;
  return (
    <Modal
      open={!!attemptId} onOpenChange={(o) => !o && onClose()} size="lg"
      title={r ? `${r.student_name}${r.roll_no ? ` (${r.roll_no})` : ""}` : "Attempt"}
      description={r ? `Score ${r.score != null ? fmtMarks(r.score) : "-"} / ${fmtMarks(r.total_marks)}` : undefined}
      footer={canGrade && r ? (<><Button variant="outline" onClick={onClose}>Close</Button><Button onClick={() => save.mutate()} loading={save.isPending}>Save marks</Button></>) : undefined}
    >
      {q.isLoading ? <ListSkeleton rows={3} /> : q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : (
        <ol className="max-h-[60vh] space-y-4 overflow-y-auto pr-1" data-test={testId}>
          {r?.answers.map((a, i) => (
            <li key={a.question_id} className="space-y-1 rounded-md border border-border p-3 text-sm">
              <p className="font-medium">{i + 1}. {a.text} <span className="font-normal text-muted-foreground">({fmtMarks(a.marks)} marks)</span></p>
              <p><span className="text-muted-foreground">Answer:</span> {a.answer || <em>No answer</em>}</p>
              {a.correct_answer && <p><span className="text-muted-foreground">Key:</span> {a.correct_answer}</p>}
              {a.type === "short" && canGrade ? (
                <label className="flex items-center gap-2">Marks
                  <Input type="number" min={0} max={Number(a.marks)} step={0.5} className="w-24" value={marks[a.question_id] ?? ""} onChange={(e) => setMarks((m) => ({ ...m, [a.question_id]: e.target.value }))} />
                  <span className="text-muted-foreground">/ {fmtMarks(a.marks)}</span>
                </label>
              ) : <p className="text-muted-foreground">Awarded: {a.marks_awarded != null ? fmtMarks(a.marks_awarded) : "-"}</p>}
            </li>
          ))}
        </ol>
      )}
    </Modal>
  );
}
