"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { Donut } from "@/components/charts/donut";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/state-views";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { dateLabel, fmtPct, monthLabel, monthOf, num, shiftMonth, todayIn } from "@/lib/format";
import { useSettings } from "@/lib/queries";
import type { AttendanceSummary, CalendarOut } from "@/lib/types";
import { cn } from "@/lib/utils";

const DAY_STYLE: Record<string, string> = {
  present: "bg-green-100 text-green-800 border-green-300",
  absent: "bg-red-100 text-red-800 border-red-300",
  late: "bg-amber-100 text-amber-800 border-amber-300",
  sick: "bg-blue-100 text-blue-800 border-blue-300",
  holiday: "bg-slate-200 text-slate-600 border-slate-300",
  off: "bg-slate-100 text-slate-500 border-slate-200",
};
const LEGEND = [
  ["present", "Present"], ["absent", "Absent"], ["late", "Late"], ["sick", "Sick"], ["holiday", "Holiday"], ["off", "Weekly off"],
] as const;

function Calendar({ data, loading }: { data?: CalendarOut; loading: boolean }) {
  const [picked, setPicked] = useState<string | null>(null);
  const first = data?.days[0]?.date;
  const lead = first ? (new Date(`${first}T00:00:00Z`).getUTCDay() + 6) % 7 : 0; // Monday first
  const pickedDay = data?.days.find((d) => d.date === picked);
  return (
    <div>
      <div className="grid grid-cols-7 gap-1.5 text-center text-xs font-semibold text-muted-foreground" aria-hidden>
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d}>{d}</div>)}
      </div>
      <div className="mt-1.5 grid grid-cols-7 gap-1.5">
        {loading && !data
          ? Array.from({ length: 35 }).map((_, i) => <Skeleton key={i} className="h-11" />)
          : <>
              {Array.from({ length: lead }).map((_, i) => <div key={`b${i}`} />)}
              {data?.days.map((d) => {
                const status = d.status ?? "none";
                const text = d.holiday_name ? `${d.holiday_name} (holiday)` : d.status ? d.status : "Not marked";
                return (
                  <button
                    key={d.date}
                    type="button"
                    onClick={() => setPicked(d.date)}
                    title={`${dateLabel(d.date)}: ${text}`}
                    aria-label={`${dateLabel(d.date)}: ${text}`}
                    className={cn(
                      "flex h-11 items-center justify-center rounded-md border text-sm font-semibold tabular-nums",
                      DAY_STYLE[status] ?? "border-border bg-card text-muted-foreground",
                      picked === d.date && "ring-2 ring-ring",
                    )}
                  >
                    {Number(d.date.slice(8))}
                  </button>
                );
              })}
            </>}
      </div>
      <p className="mt-3 min-h-5 text-sm" aria-live="polite">
        {pickedDay ? <><strong>{dateLabel(pickedDay.date)}:</strong> {pickedDay.holiday_name ?? (pickedDay.status ? pickedDay.status[0]!.toUpperCase() + pickedDay.status.slice(1) : "Not marked")}</> : <span className="text-muted-foreground">Tap a day for details.</span>}
      </p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {LEGEND.map(([k, label]) => (
          <li key={k} className="flex items-center gap-1.5"><span className={cn("h-3 w-3 rounded-sm border", DAY_STYLE[k])} />{label}</li>
        ))}
      </ul>
    </div>
  );
}

/** F3: attendance tab used by the student profile (staff) and by the Parent and Student portals. */
export function StudentAttendanceTab({ studentId }: { studentId: string }) {
  const settings = useSettings();
  const [month, setMonth] = useState<string | null>(null);
  const [mode, setMode] = useState<"month" | "year">("month");
  const current = month ?? monthOf(todayIn(settings.data?.timezone));
  const thisMonth = monthOf(todayIn(settings.data?.timezone));

  const summary = useQuery({
    queryKey: ["student-attendance", studentId, "summary", current],
    queryFn: ({ signal }) => api<AttendanceSummary>(`/students/${studentId}/attendance/summary`, { query: { month: current }, signal }),
    placeholderData: keepPreviousData,
    enabled: !!settings.data,
  });
  const calendar = useQuery({
    queryKey: ["student-attendance", studentId, "calendar", current],
    queryFn: ({ signal }) => api<CalendarOut>(`/students/${studentId}/attendance/calendar`, { query: { month: current }, signal }),
    placeholderData: keepPreviousData,
    enabled: !!settings.data,
  });

  const s = summary.data;
  const pct = useMemo(() => (s ? num(mode === "month" ? s.month_percentage : s.year_percentage) : 0), [s, mode]);
  const threshold = settings.data?.attendance_alert_threshold ?? 75;

  if (summary.error) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  return (
    <div className="space-y-5">
      {s?.below_threshold && (
        <div role="alert" className="flex items-start gap-3 rounded-lg border border-red-300 bg-red-50 p-4 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
          <p className="text-sm"><strong>Attendance is below {threshold}%.</strong> Regular attendance matters for results. Please contact the school if there is a reason for the absences.</p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {([["Days present", s?.present, "text-green-700"], ["Absent", s?.absent, "text-red-700"], ["Late", s?.late, "text-amber-700"], ["Sick", s?.sick, "text-blue-700"]] as const).map(([label, v, tone]) => (
            <Card key={label} className="p-4">
              {summary.isLoading ? <Skeleton className="h-8 w-12" /> : <p className={cn("text-3xl font-bold tabular-nums", tone)}>{v ?? 0}</p>}
              <p className="mt-1 text-sm text-muted-foreground">{label}</p>
            </Card>
          ))}
        </div>
        <Card className="flex items-center gap-4 p-4">
          <Donut value={pct} warn={!!s?.below_threshold} />
          <div>
            <p className="text-2xl font-bold tabular-nums">{fmtPct(pct)}</p>
            <p className="text-sm text-muted-foreground">Attendance {mode === "month" ? monthLabel(current) : "this year"}</p>
            <div role="group" aria-label="Percentage period" className="mt-2 inline-flex overflow-hidden rounded-md border border-border text-xs font-semibold">
              {(["month", "year"] as const).map((m) => (
                <button key={m} type="button" aria-pressed={mode === m} onClick={() => setMode(m)}
                  className={cn("px-3 py-1.5", mode === m ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
                  {m === "month" ? "Month" : "Year"}
                </button>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card className="p-4 sm:p-5">
        <div className="mb-4 flex items-center justify-between">
          <Button variant="outline" size="icon" aria-label="Previous month" onClick={() => setMonth(shiftMonth(current, -1))}><ChevronLeft className="h-4 w-4" /></Button>
          <h3 className="font-semibold">{monthLabel(current)}</h3>
          <Button variant="outline" size="icon" aria-label="Next month" disabled={current >= thisMonth} onClick={() => setMonth(shiftMonth(current, 1))}><ChevronRight className="h-4 w-4" /></Button>
        </div>
        {calendar.error ? <ErrorState error={calendar.error} onRetry={() => calendar.refetch()} /> : <Calendar data={calendar.data} loading={calendar.isLoading} />}
      </Card>
    </div>
  );
}
