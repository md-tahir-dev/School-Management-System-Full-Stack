"use client";

import { cn } from "@/lib/utils";

export interface SegOption<V extends string> {
  value: V;
  label: string;
  short: string;
  active: string; // classes applied when selected
}

export const STUDENT_OPTIONS: SegOption<"present" | "absent" | "late" | "sick">[] = [
  { value: "present", label: "Present", short: "P", active: "bg-green-600 text-white border-green-600" },
  { value: "absent", label: "Absent", short: "A", active: "bg-red-600 text-white border-red-600" },
  { value: "late", label: "Late", short: "L", active: "bg-amber-500 text-slate-900 border-amber-500" },
  { value: "sick", label: "Sick", short: "S", active: "bg-blue-600 text-white border-blue-600" },
];

export const TEACHER_OPTIONS: SegOption<"present" | "absent" | "late" | "leave">[] = [
  { value: "present", label: "Present", short: "P", active: "bg-green-600 text-white border-green-600" },
  { value: "absent", label: "Absent", short: "A", active: "bg-red-600 text-white border-red-600" },
  { value: "late", label: "Late", short: "L", active: "bg-amber-500 text-slate-900 border-amber-500" },
  { value: "leave", label: "Leave", short: "Lv", active: "bg-blue-600 text-white border-blue-600" },
];

/** Radio-group semantics: arrow keys move + select, Tab enters/leaves the group. 44px tap targets. */
export function Segmented<V extends string>({
  options, value, onChange, label, disabled,
}: { options: SegOption<V>[]; value: V | null; onChange: (v: V) => void; label: string; disabled?: boolean }) {
  function onKey(e: React.KeyboardEvent, index: number) {
    if (disabled) return;
    const dir = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = options[(index + dir + options.length) % options.length];
    if (next) onChange(next.value);
  }
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-lg border border-border bg-card">
      {options.map((o, i) => {
        const selected = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={o.label}
            disabled={disabled}
            tabIndex={selected || (value === null && i === 0) ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "min-h-[44px] min-w-[44px] border-r border-border px-3 text-sm font-bold transition-colors last:border-r-0 disabled:opacity-60 sm:min-w-[72px]",
              selected ? o.active : "text-foreground hover:bg-muted",
            )}
          >
            <span className="sm:hidden">{o.short}</span>
            <span className="hidden sm:inline">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
