import { cn } from "@/lib/utils";

/** Small SVG donut used for attendance %. `tone` follows the design system (green / amber / red). */
export function Donut({ value, size = 96, stroke = 10, label, warn }: { value: number; size?: number; stroke?: number; label?: string; warn?: boolean }) {
  const clamped = Math.max(0, Math.min(100, value));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = warn ? "stroke-danger" : clamped >= 90 ? "stroke-success" : "stroke-warning";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${label ?? "Attendance"} ${clamped.toFixed(1)} percent`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} className="stroke-slate-200" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * clamped) / 100} className={cn("transition-all", color)}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-sm font-bold tabular-nums">{clamped.toFixed(0)}%</span>
    </div>
  );
}
