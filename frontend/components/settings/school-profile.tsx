"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useSettings } from "@/lib/queries";
import type { BrandingKind } from "@/lib/types";

const FIELDS = [
  { key: "name", label: "School name", max: 150 },
  { key: "slogan", label: "Tagline", max: 255 },
  { key: "phone", label: "Phone", max: 32 },
  { key: "email", label: "Email", max: 150 },
  { key: "website", label: "Website", max: 200 },
  { key: "address", label: "Address", max: 1000 },
] as const;
type Key = (typeof FIELDS)[number]["key"];

/** White-label branding: name, tagline and logo appear on the login page, sidebar, tab title and result cards. */
export function SchoolProfile() {
  const qc = useQueryClient();
  const s = useSettings();
  const [form, setForm] = useState<Record<Key, string>>({ name: "", slogan: "", phone: "", email: "", website: "", address: "" });
  useEffect(() => {
    if (s.data) setForm({ name: s.data.name, slogan: s.data.slogan ?? "", phone: s.data.phone ?? "", email: s.data.email ?? "", website: s.data.website ?? "", address: s.data.address ?? "" });
  }, [s.data]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["public-config"] }); };

  const save = useMutation({
    // Optional fields are cleared with null; "" would fail the email validator.
    mutationFn: () => api("/settings", { method: "PUT", body: Object.fromEntries(FIELDS.map((f) => [f.key, f.key === "name" ? form.name.trim() : form[f.key].trim() || null])) }),
    onSuccess: () => { toast.success("School profile saved"); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't save")),
  });

  if (s.isLoading) return <ListSkeleton rows={4} />;
  if (s.error) return <ErrorState error={s.error} onRetry={() => s.refetch()} />;
  return (
    <Card className="max-w-2xl space-y-5 p-5">
      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Branding</h3>
        <BrandingUploader kind="logo" label="Logo" hint="PNG, JPEG or WebP, up to 2 MB. Square works best." url={s.data?.logo_url} onDone={refresh} />
        <BrandingUploader kind="favicon" label="Favicon" hint="Square PNG, at least 64×64, up to 2 MB. Shown in the browser tab." url={s.data?.favicon_url} onDone={refresh} />
        <BrandingUploader kind="login_image" label="Login page image" hint="Wide photo, e.g. the school building. Up to 5 MB." url={s.data?.login_image_url} onDone={refresh} wide />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <div key={f.key} className={f.key === "address" || f.key === "name" ? "sm:col-span-2" : undefined}>
            <Field label={f.label}>
              <Input value={form[f.key]} maxLength={f.max} type={f.key === "email" ? "email" : "text"} aria-invalid={f.key === "name" && form.name.trim().length < 2}
                onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))} />
            </Field>
          </div>
        ))}
      </div>
      <Button onClick={() => save.mutate()} loading={save.isPending} disabled={form.name.trim().length < 2}>Save profile</Button>
    </Card>
  );
}

function BrandingUploader({ kind, label, hint, url, onDone, wide }: { kind: BrandingKind; label: string; hint: string; url?: string | null; onDone: () => void; wide?: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api(`/settings/branding/${kind}`, { method: "POST", body: fd }); },
    onSuccess: () => { toast.success(`${label} updated`); onDone(); },
    onError: (e) => toast.error(errorText(e, `Couldn't upload the ${label.toLowerCase()}`)),
  });
  const remove = useMutation({
    mutationFn: () => api(`/settings/branding/${kind}`, { method: "DELETE" }),
    onSuccess: () => { toast.success(`${label} removed`); onDone(); },
    onError: (e) => toast.error(errorText(e, `Couldn't remove the ${label.toLowerCase()}`)),
  });
  const busy = upload.isPending || remove.isPending;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-3 sm:flex-row sm:items-center">
      <div className={`flex shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted ${wide ? "h-24 w-full sm:w-44" : "h-16 w-16"}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {url ? <img src={url} alt={`${label} preview`} className={wide ? "h-full w-full object-cover" : "h-full w-full object-contain"} /> : <span className="px-2 text-center text-xs text-muted-foreground">Default</span>}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label={`${label} file`}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="min-h-11" loading={upload.isPending} disabled={busy} onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" />{url ? "Replace" : "Upload"}</Button>
          {url ? <Button variant="outline" size="sm" className="min-h-11" loading={remove.isPending} disabled={busy} onClick={() => remove.mutate()}><Trash2 className="h-4 w-4" />Remove</Button> : null}
        </div>
      </div>
    </div>
  );
}
