"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { SelectField, TextField, useApiForm } from "@/components/forms";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { Modal } from "@/components/modals/modal";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errorText } from "@/lib/api";
import type { EventIn, EventOut } from "@/lib/types";

const blank = (date: string) => ({ title: "", description: "", start_date: date, end_date: "", type: "event", audience: "all" });

/** Managers only: add (event undefined) or edit/delete an event. */
export function EventForm({ open, onClose, event, defaultDate }: { open: boolean; onClose: () => void; event?: EventOut; defaultDate: string }) {
  const qc = useQueryClient();
  const form = useApiForm(blank(defaultDate));
  const [confirmDelete, setConfirmDelete] = useState(false);
  const { reset } = form;
  useEffect(() => {
    if (!open) return;
    reset(event
      ? { title: event.title, description: event.description ?? "", start_date: event.start_date, end_date: event.end_date !== event.start_date ? event.end_date : "", type: event.type, audience: event.audience }
      : blank(defaultDate));
  }, [open, event, defaultDate, reset]);
  const v = (k: string) => form.values[k] ?? "";
  const done = () => { qc.invalidateQueries({ queryKey: ["calendar"] }); qc.invalidateQueries({ queryKey: ["events"] }); onClose(); };

  const save = useMutation({
    mutationFn: () => {
      const body = { title: v("title").trim(), description: v("description").trim() || null, start_date: v("start_date"), end_date: v("end_date") || null, type: v("type"), audience: v("audience") } as EventIn;
      return api(event ? `/events/${event.id}` : "/events", { method: event ? "PUT" : "POST", body });
    },
    onSuccess: () => { toast.success(event ? "Event updated" : "Event added"); done(); },
    onError: (e) => { if (!form.showErrors(e)) toast.error(errorText(e, "Couldn't save event")); },
  });
  const del = useMutation({
    mutationFn: () => api(`/events/${event!.id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Event deleted"); done(); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete event")),
  });

  return (
    <>
      <Modal
        open={open}
        onOpenChange={(o) => !o && onClose()}
        title={event ? "Edit event" : "Add event"}
        footer={
          <>
            {event && <Button variant="destructive" className="sm:mr-auto" onClick={() => setConfirmDelete(true)}>Delete</Button>}
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!v("title").trim() || !v("start_date")}>Save</Button>
          </>
        }
      >
        <div className="space-y-4">
          <TextField form={form} name="title" label="Title" maxLength={200} />
          <div className="flex flex-col gap-1.5 text-sm">
            <label htmlFor="ev-desc" className="font-medium">Description (optional)</label>
            <Textarea id="ev-desc" rows={3} value={v("description")} onChange={(e) => form.set("description", e.target.value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField form={form} name="start_date" label="Start date" type="date" />
            <TextField form={form} name="end_date" label="End date (optional)" type="date" min={v("start_date") || undefined} />
            <SelectField form={form} name="type" label="Type" options={["event", "ptm", "exam", "sports", "other"]} />
            <SelectField form={form} name="audience" label="Audience" options={["all", "teachers", "students", "parents"]} />
          </div>
        </div>
      </Modal>
      <ConfirmDialog open={confirmDelete} onOpenChange={setConfirmDelete} title="Delete event" description={`"${event?.title ?? ""}" will be removed from the calendar.`} confirmLabel="Delete event" destructive onConfirm={async () => { await del.mutateAsync().catch(() => {}); }} />
    </>
  );
}
