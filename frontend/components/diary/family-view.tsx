"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import { useStudentScope } from "@/lib/queries";
import type { DiaryEntry, Submission } from "@/lib/types";
import { FileInput, FileLink, TextAreaField } from "./common";
import { DayNav } from "./day-nav";

function SubmitForm({ entry, canSubmit }: { entry: DiaryEntry; canSubmit: boolean }) {
  const qc = useQueryClient();
  const s = entry.my_submission;
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const send = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      if (note.trim()) fd.append("note", note.trim());
      if (file) fd.append("file", file);
      return api<Submission>(`/diary/${entry.id}/submission`, { method: "POST", body: fd });
    },
    onSuccess: () => { toast.success("Work submitted"); setNote(""); setFile(null); setFileKey((k) => k + 1); qc.invalidateQueries({ queryKey: ["diary"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't submit")),
  });
  return (
    <div className="mt-3 space-y-3 rounded-md border border-border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Submission</span>
        {!s ? <StatusBadge status="pending" label="Not submitted" /> : (
          <>
            <StatusBadge status="submitted" />
            {s.late && <StatusBadge status="late" />}
            {s.checked && <StatusBadge status="graded" label="Checked" />}
          </>
        )}
      </div>
      {s?.note && <p className="whitespace-pre-wrap">{s.note}</p>}
      {s?.file_url && <FileLink href={s.file_url} label="Submitted file" />}
      {s?.remarks && <p><span className="font-medium">Teacher remarks:</span> {s.remarks}</p>}
      {canSubmit && !s?.checked && (
        <form onSubmit={(e) => { e.preventDefault(); send.mutate(); }} className="space-y-3">
          <TextAreaField label="Note (optional)" rows={3} value={note} onChange={setNote} />
          <FileInput key={fileKey} label="File (optional)" onFile={setFile} hint="PDF, Word, Excel, PowerPoint or image, up to 10 MB." />
          <Button type="submit" loading={send.isPending} disabled={!note.trim() && !file}>{s ? "Resubmit" : "Submit work"}</Button>
        </form>
      )}
    </div>
  );
}

export function FamilyDiary({ date, setDate, isParent }: { date: string; setDate: (d: string) => void; isParent: boolean }) {
  const scope = useStudentScope();
  const q = useQuery({
    queryKey: ["diary", "family", scope.studentId, date],
    queryFn: () => api<DiaryEntry[]>("/diary", { query: { date, student_id: isParent ? scope.studentId : undefined } }),
    enabled: !!scope.studentId,
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <DayNav date={date} onChange={setDate} />
        {isParent && <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} />}
      </div>
      {scope.error ? <ErrorState error={scope.error} /> : q.isLoading || scope.isLoading ? <ListSkeleton rows={3} /> : q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : !q.data?.length ? (
        <EmptyState title="No diary entries for this day" />
      ) : (
        <div className="space-y-4">
          {[...q.data].sort((a, b) => (a.subject_name ?? "").localeCompare(b.subject_name ?? "")).map((e) => (
            <Card key={e.id}>
              <CardHeader>
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">{e.subject_name ?? "Class note"}</p>
                <CardTitle>{e.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap text-sm">{e.body}</p>
                {e.attachment_url && <FileLink href={e.attachment_url} />}
                {e.due_date && <p className="mt-2 text-sm text-muted-foreground">Due {dateLabel(e.due_date)}</p>}
                {e.submission_required && <SubmitForm entry={e} canSubmit={!isParent} />}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
