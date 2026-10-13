"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Megaphone } from "lucide-react";
import Link from "next/link";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel, targetLabel, todayIn } from "@/lib/format";
import type { Announcement, CalendarItem, Page } from "@/lib/types";

const addDays = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

export function LatestAnnouncements() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["announcements", "latest"], queryFn: () => api<Page<Announcement>>("/announcements", { query: { page_size: 3 } }), select: (p) => p.items });
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Megaphone className="h-4 w-4 text-primary" aria-hidden />Latest announcements</CardTitle></CardHeader>
      <CardContent>
        {q.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : q.isError ? <p className="text-sm text-danger">Couldn&apos;t load announcements.</p> : !q.data?.length ? (
          <p className="text-sm text-muted-foreground">No announcements yet.</p>
        ) : (
          <ul className="space-y-3">
            {q.data.map((a) => (
              <li key={a.id}>
                <p className="flex items-center gap-2 text-sm font-semibold">{a.title}{a.priority === "important" && <StatusBadge status="important" tone="warning" />}</p>
                <p className="text-xs text-muted-foreground">{targetLabel(a)} · {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(a.created_at))}</p>
                <p className="line-clamp-2 whitespace-pre-line text-sm">{a.message}</p>
              </li>
            ))}
          </ul>
        )}
        <Link href={`/${user?.role}/announcements`} className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline">View all</Link>
      </CardContent>
    </Card>
  );
}

export function UpcomingCard() {
  const { user } = useAuth();
  const from = todayIn();
  const to = addDays(from, 14);
  const q = useQuery({ queryKey: ["calendar", "upcoming", from], queryFn: () => api<CalendarItem[]>("/calendar", { query: { from, to } }) });
  const items = [...(q.data ?? [])].sort((a, b) => a.start_date.localeCompare(b.start_date)).slice(0, 6);
  return (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-primary" aria-hidden />Upcoming</CardTitle></CardHeader>
      <CardContent>
        {q.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : q.isError ? <p className="text-sm text-danger">Couldn&apos;t load the calendar.</p> : !items.length ? (
          <p className="text-sm text-muted-foreground">Nothing in the next 14 days.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {items.map((i) => (
              <li key={`${i.kind}${i.id}`} className="flex gap-3">
                <span className="w-24 shrink-0 text-muted-foreground">{dateLabel(i.start_date < from ? from : i.start_date)}</span>
                <span className="font-medium">{i.title}</span>
              </li>
            ))}
          </ul>
        )}
        <Link href={`/${user?.role}/calendar`} className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-primary hover:underline">Open calendar</Link>
      </CardContent>
    </Card>
  );
}
