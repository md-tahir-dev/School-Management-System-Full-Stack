"use client";

import { useQuery } from "@tanstack/react-query";
import { NotebookPen } from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { todayIn } from "@/lib/format";
import { useStudentScope } from "@/lib/queries";
import type { DiaryEntry } from "@/lib/types";

/** Student and parent dashboards. */
export function TodaysDiary() {
  const { user } = useAuth();
  const scope = useStudentScope();
  const date = todayIn();
  const q = useQuery({
    queryKey: ["diary", "family", scope.studentId, date],
    queryFn: () => api<DiaryEntry[]>("/diary", { query: { date, student_id: user?.role === "parent" ? scope.studentId : undefined } }),
    enabled: !!scope.studentId,
  });
  if (!scope.studentId) return null;
  const items = q.data ?? [];
  return (
    <Card className="mb-8">
      <CardHeader><CardTitle className="flex items-center gap-2"><NotebookPen className="h-4 w-4 text-primary" aria-hidden />Today&apos;s diary</CardTitle></CardHeader>
      <CardContent>
        {q.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : !items.length ? (
          <p className="text-sm text-muted-foreground">No diary entries today.</p>
        ) : (
          <Link href={`/${user?.role}/diary`} className="block rounded-md hover:bg-muted/60">
            <p className="text-2xl font-bold tabular-nums">{items.length} {items.length === 1 ? "entry" : "entries"}</p>
            <ul className="mt-1 list-disc pl-5 text-sm text-muted-foreground">
              {items.slice(0, 4).map((e) => <li key={e.id}>{e.subject_name ? `${e.subject_name}: ` : ""}{e.title}</li>)}
            </ul>
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
