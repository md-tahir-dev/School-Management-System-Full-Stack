import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const TONES = {
  primary: "bg-blue-100 text-primary",
  success: "bg-green-100 text-green-700",
  warning: "bg-amber-100 text-amber-700",
  danger: "bg-red-100 text-red-700",
} as const;

interface StatCardProps {
  label: string;
  value: string | number | undefined;
  icon: LucideIcon;
  tone?: keyof typeof TONES;
  hint?: string;
  loading?: boolean;
}

export function StatCard({ label, value, icon: Icon, tone = "primary", hint, loading }: StatCardProps) {
  return (
    <Card className="flex items-center gap-4 p-5">
      <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-lg", TONES[tone])}>
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <div className="min-w-0">
        {loading ? <Skeleton className="h-7 w-16" /> : <p className="text-2xl font-bold leading-none tabular-nums">{value ?? "-"}</p>}
        <p className="mt-1.5 truncate text-sm text-muted-foreground">{label}</p>
        {hint ? <p className="truncate text-xs text-muted-foreground/80">{hint}</p> : null}
      </div>
    </Card>
  );
}
