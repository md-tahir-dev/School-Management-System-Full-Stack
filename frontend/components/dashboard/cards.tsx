"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, FileText, Trophy } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Donut } from "@/components/charts/donut";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { StatCard } from "@/components/stat-card";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/state-views";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtPct, num } from "@/lib/format";
import { useStudentScope } from "@/lib/queries";
import type { AttendanceCardData, CeoDashboard, ChildDashboard, LatestResultCard } from "@/lib/types";
import { cn } from "@/lib/utils";

export function LatestResultCardView({ data, href, loading }: { data: LatestResultCard | null | undefined; href: string; loading?: boolean }) {
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4 text-primary" aria-hidden />Latest result</CardTitle></CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-20" /> : !data ? (
          <p className="text-sm text-muted-foreground">No published results yet.</p>
        ) : (
          <Link href={href} className="block rounded-md hover:bg-muted/60">
            <p className="text-sm text-muted-foreground">{data.exam_name}</p>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="text-3xl font-bold tabular-nums">{fmtPct(data.percentage)}</span>
              <span className="rounded-md bg-blue-100 px-2 py-0.5 text-lg font-bold text-primary">{data.grade}</span>
              <StatusBadge status={data.is_pass ? "pass" : "fail"} label={data.is_pass ? "Pass" : "Fail"} />
            </div>
            {data.is_pass && data.rank ? <p className="mt-2 flex items-center gap-1.5 text-sm"><Trophy className="h-4 w-4 text-amber-600" aria-hidden />Position {data.rank} of {data.total_students}</p> : null}
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

export function AttendanceCardView({ data, href, loading }: { data: AttendanceCardData | null | undefined; href: string; loading?: boolean }) {
  return (
    <Card className={cn(data?.below_threshold && "border-red-300")}>
      <CardHeader><CardTitle className="flex items-center gap-2"><CalendarCheck className="h-4 w-4 text-primary" aria-hidden />Attendance this month</CardTitle></CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-20" /> : !data ? (
          <p className="text-sm text-muted-foreground">No attendance recorded yet.</p>
        ) : (
          <Link href={href} className="flex items-center gap-4 rounded-md hover:bg-muted/60">
            <Donut value={data.month_percentage} warn={data.below_threshold} size={80} stroke={9} />
            <div className="text-sm">
              <p className={cn("text-2xl font-bold tabular-nums", data.below_threshold && "text-danger")}>{fmtPct(data.month_percentage)}</p>
              <p className="text-muted-foreground">P {data.present} · A {data.absent} · L {data.late} · S {data.sick}</p>
              {data.below_threshold ? <p className="mt-1 font-semibold text-danger">Below the school threshold</p> : null}
            </div>
          </Link>
        )}
      </CardContent>
    </Card>
  );
}

/** Parent (with child switcher) and Student dashboards share this block. */
export function FamilyDashboardCards() {
  const { user } = useAuth();
  const scope = useStudentScope();
  const isParent = user?.role === "parent";
  const q = useQuery({
    queryKey: ["dashboard", user?.role, scope.studentId],
    queryFn: () => (isParent ? api<ChildDashboard>(`/parent/children/${scope.studentId}/dashboard`) : api<ChildDashboard>("/student/dashboard")),
    enabled: !!scope.studentId,
  });
  if (!user) return null;
  if (scope.error) return <ErrorState error={scope.error} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const loading = scope.isLoading || q.isLoading;
  const d = q.data;
  return (
    <section className="mb-8" aria-label="Academic summary">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">{d?.child.full_name ?? scope.child?.full_name ?? "Academic summary"}</h2>
        {isParent && <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} />}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <LatestResultCardView loading={loading} data={d?.latest_result as LatestResultCard | null | undefined} href={`/${user.role}/results`} />
        <AttendanceCardView loading={loading} data={d?.attendance as AttendanceCardData | null | undefined} href={`/${user.role}/attendance`} />
      </div>
    </section>
  );
}

export function CeoDashboardCards() {
  const q = useQuery({ queryKey: ["dashboard", "ceo"], queryFn: () => api<CeoDashboard>("/ceo/dashboard") });
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  const bars = (d?.class_pass_rates ?? []).map((c) => ({ name: c.class_name, pass: c.pass_percent, exam: c.exam_name }));
  return (
    <section className="mb-8 space-y-4" aria-label="School overview">
      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard label="Attendance today" value={d ? fmtPct(d.today_attendance_percent) : undefined} icon={CalendarCheck} tone="success" loading={q.isLoading} />
        <StatCard label="Sections not yet marked today" value={d?.unmarked_sections} icon={CalendarCheck} tone={d && d.unmarked_sections > 0 ? "danger" : "primary"} loading={q.isLoading} />
      </div>
      <Card>
        <CardHeader><CardTitle>Pass % by class (latest published exam)</CardTitle></CardHeader>
        <CardContent>
          {q.isLoading ? <Skeleton className="h-56" /> : bars.length === 0 ? <p className="text-sm text-muted-foreground">No published exams yet.</p> : (
            <div className="h-56" role="img" aria-label="Bar chart of pass percentage per class">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bars} margin={{ left: -16, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => `${num(v as number).toFixed(1)}%`} />
                  <Bar dataKey="pass" fill="#16A34A" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
