"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { Exam, ExamAnalytics } from "@/lib/types";

/** F4: publish shows how many results are incomplete and what will happen; unpublish needs a reason. */
export function PublishDialog({ exam, mode, onClose }: { exam: Exam; mode: "publish" | "unpublish"; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const analytics = useQuery({ queryKey: ["exam-analytics", exam.id], queryFn: () => api<ExamAnalytics>(`/exams/${exam.id}/analytics`), enabled: mode === "publish" });
  const incomplete = analytics.data ? Math.max(0, analytics.data.total_students - analytics.data.complete_count) : null;

  const run = useMutation({
    mutationFn: () => api<Exam>(`/exams/${exam.id}/${mode}`, { method: "POST", body: mode === "unpublish" ? { reason: reason.trim() } : undefined }),
    onSuccess: () => {
      toast.success(mode === "publish" ? "Results published. Students and parents were notified." : "Results unpublished and hidden again.");
      for (const k of ["exams", "exam", "exam-results", "exam-analytics", "student-results", "dashboard"]) qc.invalidateQueries({ queryKey: [k] });
      onClose();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Something went wrong"),
  });

  return (
    <Modal open onOpenChange={(o) => !o && onClose()} title={mode === "publish" ? `Publish ${exam.name}?` : `Unpublish ${exam.name}?`}
      footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button variant={mode === "publish" ? "default" : "destructive"} loading={run.isPending} disabled={mode === "unpublish" && reason.trim().length < 3} onClick={() => run.mutate()}>{mode === "publish" ? "Publish results" : "Unpublish"}</Button></>}>
      {mode === "publish" ? (
        <div className="space-y-3 text-sm">
          {analytics.isLoading ? <Skeleton className="h-10" /> : incomplete !== null && (
            <p className={incomplete > 0 ? "rounded-md bg-amber-50 p-3 text-amber-900" : "rounded-md bg-green-50 p-3 text-green-900"}>
              {incomplete > 0 ? `${incomplete} student${incomplete === 1 ? "" : "s"} still have incomplete marks. They stay as drafts with no grade or rank.` : "Every student's result is complete."}
            </p>
          )}
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Ranks are recalculated one final time.</li>
            <li>Students, parents and the CEO can see the results.</li>
            <li>Students and their parents get a notification.</li>
            <li>Teachers can no longer edit marks; admin edits need a reason.</li>
          </ul>
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <p className="text-muted-foreground">Students, parents and the CEO will no longer see these results. The change is logged.</p>
          <Field label="Reason (required)"><Input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Marks correction needed" /></Field>
        </div>
      )}
    </Modal>
  );
}
