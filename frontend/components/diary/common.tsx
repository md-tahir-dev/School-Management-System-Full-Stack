"use client";

import { Paperclip } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { downloadFile, errorText } from "@/lib/api";

export const FILE_ACCEPT = ".pdf,.docx,.xlsx,.pptx,image/png,image/jpeg,image/webp";

export function shiftDay(iso: string, delta: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

/** Uploaded files need the bearer token, so this fetches and saves instead of linking. */
export function FileLink({ href, label = "Attachment" }: { href: string; label?: string }) {
  const [busy, setBusy] = useState(false);
  const download = async () => {
    setBusy(true);
    try {
      await downloadFile(href);
    } catch (e) {
      toast.error(errorText(e, "Couldn't download the file"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <button type="button" onClick={download} disabled={busy} aria-busy={busy} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-primary hover:underline disabled:opacity-60">
      <Paperclip className="h-4 w-4" aria-hidden />{label}
    </button>
  );
}

/** Labelled plain file input. */
export function FileInput({ label, onFile, hint }: { label: string; onFile: (f: File | null) => void; hint?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <label htmlFor={id} className="font-medium">{label}</label>
      <input id={id} type="file" accept={FILE_ACCEPT} onChange={(e) => onFile(e.target.files?.[0] ?? null)} className="text-sm file:mr-3 file:min-h-10 file:rounded-md file:border file:border-border file:bg-muted file:px-3 file:text-sm" />
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

export function TextAreaField({ label, value, onChange, error, rows = 4 }: { label: string; value: string; onChange: (v: string) => void; error?: string; rows?: number }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <label htmlFor={id} className="font-medium">{label}</label>
      <Textarea id={id} rows={rows} value={value} aria-invalid={!!error} onChange={(e) => onChange(e.target.value)} />
      {error && <span className="text-xs text-danger" role="alert">{error}</span>}
    </div>
  );
}
