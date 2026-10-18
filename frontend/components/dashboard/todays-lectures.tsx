"use client";

import { CalendarClock } from "lucide-react";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { hm, todayWeekday, useMyTimetable } from "@/components/timetable/grid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { useStudentScope } from "@/lib/queries";

/** Teacher and student/parent dashboards. Hidden until periods exist. */
export function TodaysLectures() {
  const { user } = useAuth();
  const scope = useStudentScope(); // inert for teachers
  const isTeacher = user?.role === "teacher";
  const q = useMyTimetable(scope.studentId, isTeacher || !!scope.studentId);
  if (!q.data?.periods.length) return null;
  const today = todayWeekday();
  const periods = [...q.data.periods].sort((a, b) => a.sort_order - b.sort_order || a.start_time.localeCompare(b.start_time));
  return (
    <Card className="mb-8">
      <CardHeader className="flex-row flex-wrap items-center gap-3">
        <CardTitle className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-primary" aria-hidden />Today&apos;s lectures</CardTitle>
        {user?.role === "parent" && <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} />}
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border text-sm">
          {periods.map((p) => {
            const e = q.data!.entries.find((x) => x.weekday === today && x.period_id === p.id);
            return (
              <li key={p.id} className="flex items-center gap-3 py-2">
                <span className="w-28 shrink-0 tabular-nums text-muted-foreground">{hm(p.start_time)} - {hm(p.end_time)}</span>
                {p.is_break ? <span className="text-muted-foreground">Break</span> : e ? (
                  <span><span className="font-medium">{e.subject_name}</span> <span className="text-muted-foreground">{isTeacher ? `${e.class_name}${e.section_name ? ` ${e.section_name}` : ""}` : e.teacher_name}{e.room ? ` · ${e.room}` : ""}</span></span>
                ) : <span className="text-muted-foreground">Free</span>}
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
