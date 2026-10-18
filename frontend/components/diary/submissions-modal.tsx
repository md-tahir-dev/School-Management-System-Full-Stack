"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Modal } from "@/components/modals/modal";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import type { DiaryEntry, Submission, SubmissionRow } from "@/lib/types";
import { FileLink } from "./common";

function Row({ row, canEdit, entryId }: { row: SubmissionRow; canEdit: boolean; entryId: string }) {
  const qc = useQueryClient();
  const s = row.submission;
  const [remarks, setRemarks] = useState(s?.remarks ?? "");
  useEffect(() => setRemarks(s?.remarks ?? ""), [s?.remarks]);
  const save = useMutation({
    mutationFn: (checked: boolean) => api<Submission>(`/diary/submissions/${s!.id}`, { method: "PUT", body: { checked, remarks: remarks.trim() || null } }),
    onSuccess: () => { toast.success("Saved"); qc.invalidateQueries({ queryKey: ["diary-submissions", entryId] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't save")),
  });
  return (
    <li className="space-y-2 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{row.full_name}</span>
        <span className="text-muted-foreground">{row.roll_no}</span>
        {!s ? <StatusBadge status="pending" label="Not submitted" /> : (
          <>
            <StatusBadge status="submitted" />
            {s.late && <StatusBadge status="late" />}
            {s.checked && <StatusBadge status="graded" label="Checked" />}
          </>
        )}
      </div>
      {s && (
        <>
          <p className="text-xs text-muted-foreground">Submitted {new Date(s.submitted_at).toLocaleString()}</p>
          {s.note && <p className="whitespace-pre-wrap">{s.note}</p>}
          {s.file_url && <FileLink href={s.file_url} label="Submitted file" />}
          {canEdit && (
            <div className="flex flex-wrap items-center gap-2">
              <Input aria-label={`Remarks for ${row.full_name}`} placeholder="Remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="min-w-0 flex-1" />
              <Button size="sm" variant={s.checked ? "outline" : "default"} loading={save.isPending} onClick={() => save.mutate(!s.checked)}>{s.checked ? "Mark unchecked" : "Mark checked"}</Button>
              {s.checked && <Button size="sm" variant="outline" onClick={() => save.mutate(true)} disabled={save.isPending}>Save remarks</Button>}
            </div>
          )}
        </>
      )}
    </li>
  );
}

export function SubmissionsModal({ entry, onClose, canEdit }: { entry: DiaryEntry | null; onClose: () => void; canEdit: boolean }) {
  const q = useQuery({ queryKey: ["diary-submissions", entry?.id], queryFn: () => api<SubmissionRow[]>(`/diary/${entry!.id}/submissions`), enabled: !!entry });
  return (
    <Modal open={!!entry} onOpenChange={(o) => !o && onClose()} title="Submissions" description={entry ? `${entry.title}${entry.due_date ? ` · due ${dateLabel(entry.due_date)}` : ""}` : undefined} size="lg">
      {q.isLoading ? <ListSkeleton rows={4} /> : q.error ? <ErrorState error={q.error as Error} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="No students in this class" /> : (
        <ul className="max-h-[60vh] divide-y divide-border overflow-y-auto">
          {q.data.map((r) => <Row key={r.student_id} row={r} canEdit={canEdit} entryId={entry!.id} />)}
        </ul>
      )}
    </Modal>
  );
}
