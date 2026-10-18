"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useSubjects } from "@/lib/queries";
import type { SubjectOut } from "@/lib/types";

export function Subjects() {
  const qc = useQueryClient();
  const subjects = useSubjects();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const [toDelete, setToDelete] = useState<SubjectOut | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["subjects"] });
  const add = useMutation({
    mutationFn: () => api("/subjects", { method: "POST", body: { name: name.trim() } }),
    onSuccess: () => { toast.success("Subject added"); setName(""); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't add")),
  });
  const rename = useMutation({
    mutationFn: (s: { id: string; name: string }) => api(`/subjects/${s.id}`, { method: "PUT", body: { name: s.name.trim() } }),
    onSuccess: () => { toast.success("Subject renamed"); setEditing(null); refresh(); qc.invalidateQueries({ queryKey: ["class-subjects"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't rename")),
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/subjects/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Subject deleted"); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete")), // 409 explains which classes use it
  });
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 sm:grid-cols-[1fr_auto] sm:items-end">
        <Field label="New subject"><Input value={name} maxLength={100} placeholder="e.g. Computer Science" onChange={(e) => setName(e.target.value)} /></Field>
        <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />Add subject</Button>
      </Card>
      {subjects.isLoading ? <ListSkeleton rows={4} /> : subjects.error ? <ErrorState error={subjects.error} onRetry={() => subjects.refetch()} /> : !subjects.data?.length ? <EmptyState title="No subjects yet" /> : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-card">
          {subjects.data.map((s) => (
            <li key={s.id} className="flex items-center gap-2 px-4 py-2 text-sm">
              {editing?.id === s.id ? (
                <>
                  <Input autoFocus aria-label="Subject name" className="flex-1" value={editing.name} maxLength={100} onChange={(e) => setEditing({ id: s.id, name: e.target.value })} />
                  <Button size="icon" variant="ghost" aria-label="Save name" loading={rename.isPending} disabled={!editing.name.trim()} onClick={() => rename.mutate(editing)}><Check className="h-4 w-4" /></Button>
                </>
              ) : (
                <>
                  <span className="flex-1 font-medium">{s.name}</span>
                  <Button size="icon" variant="ghost" aria-label={`Rename ${s.name}`} onClick={() => setEditing({ id: s.id, name: s.name })}><Pencil className="h-4 w-4" /></Button>
                </>
              )}
              <Button size="icon" variant="ghost" aria-label={`Delete ${s.name}`} onClick={() => setToDelete(s)}><Trash2 className="h-4 w-4 text-danger" /></Button>
            </li>
          ))}
        </ul>
      )}
      <ConfirmDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)} title="Delete this subject?" description={`${toDelete?.name ?? ""} will be removed. Subjects still used by a class can't be deleted.`} confirmLabel="Delete subject" destructive onConfirm={async () => { if (toDelete) await del.mutateAsync(toDelete.id).catch(() => undefined); }} />
    </div>
  );
}
