"use client";

import { Select } from "@/components/ui/select";
import type { ChildSummary } from "@/lib/types";

/** Parent-only: shown when the parent has more than one child. Selection persists across pages. */
export function ChildSwitcher({ kids, value, onChange }: { kids: ChildSummary[]; value: string | undefined; onChange: (id: string) => void }) {
  if (kids.length < 2) return null;
  return (
    <Select aria-label="Switch child" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {kids.map((c) => (
        <option key={c.id} value={c.id}>{c.full_name} · {c.class_name}{c.section_name ? ` ${c.section_name}` : ""}</option>
      ))}
    </Select>
  );
}
