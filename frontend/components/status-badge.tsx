import { cn, capitalize } from "@/lib/utils";

type Tone = "success" | "danger" | "warning" | "info" | "neutral";

// Text uses the 800 shade of each hue on a 100 tint so small badge text stays above 4.5:1.
const TONE_CLASSES: Record<Tone, { badge: string; dot: string }> = {
  success: { badge: "bg-green-100 text-green-800", dot: "bg-success" },
  danger: { badge: "bg-red-100 text-red-800", dot: "bg-danger" },
  warning: { badge: "bg-amber-100 text-amber-800", dot: "bg-warning" },
  info: { badge: "bg-blue-100 text-blue-800", dot: "bg-primary" },
  neutral: { badge: "bg-slate-100 text-slate-700", dot: "bg-slate-400" },
};

// Paid/Pass/Present = green, Unpaid/Fail/Absent = red, Late = amber (design system).
const STATUS_TONE: Record<string, Tone> = {
  paid: "success", pass: "success", present: "success", active: "success", graded: "success", published: "success",
  unpaid: "danger", fail: "danger", absent: "danger", inactive: "danger", expired: "danger", locked: "danger",
  late: "warning", partial: "warning", pending: "warning", submitted: "warning", draft: "warning",
  sick: "info", closed: "neutral",
};

export function StatusBadge({ status, label, tone, className }: { status: string; label?: string; tone?: Tone; className?: string }) {
  const resolved = tone ?? STATUS_TONE[status.toLowerCase()] ?? "neutral";
  const classes = TONE_CLASSES[resolved];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold", classes.badge, className)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", classes.dot)} aria-hidden />
      {label ?? capitalize(status)}
    </span>
  );
}
