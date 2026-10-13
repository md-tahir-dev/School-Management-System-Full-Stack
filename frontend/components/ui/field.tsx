import type { ReactNode } from "react";

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <label className="flex flex-col gap-1.5">
        <span className="font-medium">{label}</span>
        {children}
      </label>
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}
