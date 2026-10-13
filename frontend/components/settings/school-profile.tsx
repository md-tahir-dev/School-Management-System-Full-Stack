"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
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
  const fileRef = useRef<HTMLInputElement>(null);
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
  const upload = useMutation({
    mutationFn: (file: File) => { const fd = new FormData(); fd.append("file", file); return api("/settings/logo", { method: "POST", body: fd }); },
    onSuccess: () => { toast.success("Logo updated"); refresh(); },
    onError: (e) => toast.error(errorText(e, "Couldn't upload the logo")),
  });

  if (s.isLoading) return <ListSkeleton rows={4} />;
  if (s.error) return <ErrorState error={s.error} onRetry={() => s.refetch()} />;
  return (
    <Card className="max-w-2xl space-y-5 p-5">
      <div className="flex items-center gap-4">
        <BrandMark logoUrl={s.data?.logo_url} className="h-16 w-16" />
        <div className="space-y-1">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" aria-label="Logo file"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
          <Button variant="outline" size="sm" loading={upload.isPending} onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" />Upload logo</Button>
          <p className="text-xs text-muted-foreground">PNG, JPEG or WebP, up to 2 MB. Square works best.</p>
        </div>
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
