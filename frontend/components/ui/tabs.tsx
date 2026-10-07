"use client";

import { cn } from "@/lib/utils";

export interface TabDef<K extends string> {
  key: K;
  label: string;
}

/** Simple accessible tab bar; the parent decides which panel to render. */
export function Tabs<K extends string>({ tabs, value, onChange, label }: { tabs: TabDef<K>[]; value: K; onChange: (k: K) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          aria-selected={value === t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            "-mb-px shrink-0 border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors",
            value === t.key ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
