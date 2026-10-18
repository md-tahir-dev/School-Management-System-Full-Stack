"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { humanize } from "@/components/forms";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { dateLabel, monthLabel, monthOf, shiftMonth, todayIn, WEEKDAYS } from "@/lib/format";
import type { CalendarItem, EventOut } from "@/lib/types";
import { cn } from "@/lib/utils";
import { shiftDay } from "@/components/diary/common";
import { EventForm } from "./event-form";

const COLORS: Record<string, string> = {
  holiday: "bg-red-100 text-red-800",
  exam: "bg-purple-100 text-purple-800",
  event: "bg-blue-100 text-blue-800",
  ptm: "bg-green-100 text-green-800",
  sports: "bg-orange-100 text-orange-800",
  other: "bg-slate-100 text-slate-700",
};
const colorOf = (i: CalendarItem) => COLORS[i.kind === "event" ? i.type : i.kind] ?? COLORS.other;
const labelOf = (i: CalendarItem) => (i.kind === "event" ? humanize(i.type) : humanize(i.kind));

/** Monday on or before the first of the month. */
function gridStart(month: string) {
  const first = `${month}-01`;
  const dow = (new Date(`${first}T00:00:00Z`).getUTCDay() + 6) % 7; // Mon=0
  return shiftDay(first, -dow);
}

export function MonthCalendar({ manager }: { manager: boolean }) {
  const today = todayIn();
  const [month, setMonth] = useState(monthOf(today));
  const [editing, setEditing] = useState<{ event?: EventOut; open: boolean }>({ open: false });

  const start = gridStart(month);
  const nextFirst = `${shiftMonth(month, 1)}-01`;
  const lastOfMonth = shiftDay(nextFirst, -1);
  const lastDow = (new Date(`${lastOfMonth}T00:00:00Z`).getUTCDay() + 6) % 7;
  const end = shiftDay(lastOfMonth, 6 - lastDow);
  const weeks = useMemo(() => {
    const out: string[][] = [];
    for (let d = start; d <= end; d = shiftDay(d, 7)) out.push(Array.from({ length: 7 }, (_, i) => shiftDay(d, i)));
    return out;
  }, [start, end]);

  const cal = useQuery({ queryKey: ["calendar", start, end], queryFn: () => api<CalendarItem[]>("/calendar", { query: { from: start, to: end } }) });
  const events = useQuery({
    queryKey: ["events", start, end],
    queryFn: () => api<EventOut[]>("/events", { query: { from: start, to: end } }),
    enabled: manager,
  });
  const items = cal.data ?? [];
  const on = (day: string) => items.filter((i) => i.start_date <= day && day <= i.end_date);
  const agenda = items.filter((i) => i.end_date >= `${month}-01` && i.start_date <= lastOfMonth).sort((a, b) => a.start_date.localeCompare(b.start_date));
  const openItem = (i: CalendarItem) => {
    if (!manager || i.kind !== "event") return;
    const ev = events.data?.find((e) => e.id === i.id);
    if (ev) setEditing({ event: ev, open: true });
  };
  const chip = (i: CalendarItem, day: string) => {
    const cls = cn("block w-full truncate rounded px-1.5 py-0.5 text-left text-xs font-medium", colorOf(i));
    const label = `${i.title} (${labelOf(i)})`;
    return manager && i.kind === "event"
      ? <button key={`${i.kind}${i.id}${day}`} type="button" className={cn(cls, "hover:opacity-80")} onClick={() => openItem(i)} aria-label={`Edit ${label}`}>{i.title}</button>
      : <span key={`${i.kind}${i.id}${day}`} className={cls} title={label}>{i.title}</span>;
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))}><ChevronLeft className="h-4 w-4" aria-hidden /></Button>
        <h2 className="min-w-40 text-center text-lg font-semibold" aria-live="polite">{monthLabel(month)}</h2>
        <Button variant="outline" size="icon" aria-label="Next month" onClick={() => setMonth(shiftMonth(month, 1))}><ChevronRight className="h-4 w-4" aria-hidden /></Button>
        <Button variant="outline" onClick={() => setMonth(monthOf(today))}>Today</Button>
        {manager && <Button className="ml-auto" onClick={() => setEditing({ open: true })}>Add event</Button>}
      </div>

      {cal.isLoading ? <ListSkeleton rows={5} /> : cal.isError ? <ErrorState error={cal.error} onRetry={() => cal.refetch()} /> : (
        <>
          <table className="mb-8 hidden w-full table-fixed border-collapse md:table" aria-label={`Calendar for ${monthLabel(month)}`}>
            <thead>
              <tr>{WEEKDAYS.map((d) => <th key={d.iso} scope="col" className="border border-border bg-muted px-2 py-1.5 text-xs font-semibold">{d.label}</th>)}</tr>
            </thead>
            <tbody>
              {weeks.map((w) => (
                <tr key={w[0]}>
                  {w.map((day) => (
                    <td key={day} className={cn("h-28 border border-border p-1 align-top", monthOf(day) !== month && "bg-muted/40 text-muted-foreground")}>
                      <span className={cn("mb-1 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs font-semibold", day === today && "bg-primary text-primary-foreground")} aria-label={dateLabel(day)}>{Number(day.slice(8))}</span>
                      <div className="space-y-0.5">{on(day).map((i) => chip(i, day))}</div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          <section aria-label="Agenda">
            <h3 className="mb-2 text-base font-semibold">Agenda</h3>
            {!agenda.length ? <EmptyState title="Nothing scheduled this month" /> : (
              <ul className="divide-y divide-border rounded-lg border border-border bg-card">
                {agenda.map((i) => (
                  <li key={`${i.kind}${i.id}`} className="flex min-h-11 items-center gap-3 px-4 py-2 text-sm">
                    <span className="w-32 shrink-0 tabular-nums text-muted-foreground">{dateLabel(i.start_date)}{i.end_date !== i.start_date && ` - ${dateLabel(i.end_date)}`}</span>
                    {manager && i.kind === "event"
                      ? <button type="button" className="min-w-0 flex-1 truncate text-left font-medium text-primary hover:underline" onClick={() => openItem(i)}>{i.title}</button>
                      : <span className="min-w-0 flex-1 truncate font-medium">{i.title}</span>}
                    <span className={cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold", colorOf(i))}>{labelOf(i)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
      {manager && <EventForm open={editing.open} event={editing.event} defaultDate={today.slice(0, 7) === month ? today : `${month}-01`} onClose={() => setEditing({ open: false })} />}
    </div>
  );
}
