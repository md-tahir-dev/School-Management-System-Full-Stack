"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import type { Timetable, TimetableEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
/** JS getDay() (0 = Sunday) -> API weekday (1 = Mon .. 7 = Sun). */
export const todayWeekday = () => new Date().getDay() || 7;
export const hm = (t: string) => t.slice(0, 5);

/** Own week: teacher, student, or a parent's child (studentId). */
export function useMyTimetable(studentId?: string, enabled = true) {
  return useQuery({
    queryKey: ["timetable", "me", studentId ?? null],
    queryFn: () => api<Timetable>("/timetable/me", { query: studentId ? { student_id: studentId } : undefined }),
    enabled,
  });
}

export function TimetableGrid({ data, cell, onCellClick }: { data: Timetable; cell: (e: TimetableEntry) => ReactNode; onCellClick?: (weekday: number, periodId: string, entry?: TimetableEntry) => void }) {
  const periods = [...data.periods].sort((a, b) => a.sort_order - b.sort_order || a.start_time.localeCompare(b.start_time));
  const days = data.entries.some((e) => e.weekday === 7) ? 7 : 6;
  const today = todayWeekday();
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="p-2 text-left font-medium text-muted-foreground">Period</th>
            {DAYS.slice(0, days).map((d, i) => (
              <th key={d} scope="col" className={cn("p-2 text-left font-medium", i + 1 === today && "bg-primary/10 text-primary")}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {periods.map((p) => (
            <tr key={p.id} className="border-b border-border last:border-0">
              <th scope="row" className="whitespace-nowrap p-2 text-left font-medium">
                {p.name}<div className="text-xs font-normal tabular-nums text-muted-foreground">{hm(p.start_time)} - {hm(p.end_time)}</div>
              </th>
              {p.is_break ? (
                <td colSpan={days} className="bg-muted p-2 text-center text-muted-foreground">Break</td>
              ) : (
                DAYS.slice(0, days).map((_, i) => {
                  const wd = i + 1;
                  // Section-specific lecture wins over a whole-class one in the same slot.
                  const slot = data.entries.filter((e) => e.weekday === wd && e.period_id === p.id);
                  const entry = slot.find((e) => e.section_id) ?? slot[0];
                  return (
                    <td key={wd} className={cn("p-0 align-top", wd === today && "bg-primary/5")}>
                      {onCellClick ? (
                        <button type="button" className="min-h-[56px] w-full p-2 text-left hover:bg-muted/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" aria-label={`${DAYS[i]} ${p.name}${entry ? "" : " (empty)"}`} onClick={() => onCellClick(wd, p.id, entry)}>
                          {entry ? cell(entry) : <span className="text-muted-foreground">+</span>}
                        </button>
                      ) : (
                        <div className="min-h-[56px] p-2">{entry && cell(entry)}</div>
                      )}
                    </td>
                  );
                })
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
