"use client";

import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, apiBlob, saveBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtPct, num } from "@/lib/format";
import type { StudentResults } from "@/lib/types";

/** F6: Results tab (student profile, Student portal, Parent portal). */
export function StudentResultsTab({ studentId }: { studentId: string }) {
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ["student-results", studentId],
    queryFn: ({ signal }) => api<StudentResults>(`/students/${studentId}/results`, { signal }),
  });

  if (q.isLoading) return <ListSkeleton rows={4} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const results = q.data?.results ?? [];
  if (results.length === 0) return <EmptyState title="No results yet" hint="Published exam results will appear here." />;
  const trend = (q.data?.trend ?? []).map((t) => ({ name: t.exam_name, percentage: num(t.percentage), grade: t.grade }));

  async function pdf(resultId: string, name: string) {
    try {
      saveBlob(await apiBlob(`/results/${resultId}/pdf`), `${name}.pdf`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't download the PDF");
    }
  }

  return (
    <div className="space-y-5">
      {trend.length > 1 && (
        <Card>
          <CardHeader><CardTitle>Progress across exams</CardTitle></CardHeader>
          <CardContent>
            <div className="h-56" role="img" aria-label="Line chart of percentage per exam">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ left: -16, right: 12, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v) => `${num(v as number).toFixed(2)}%`} />
                  <Line type="monotone" dataKey="percentage" stroke="#1E40AF" strokeWidth={2.5} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="border-b border-border bg-slate-50 text-muted-foreground">
              <tr>{["Exam", "Percentage", "Grade", "Rank", "Result", ""].map((h) => <th key={h} scope="col" className="px-4 py-3 font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.result_id ?? r.exam_id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-3 font-medium">
                    {r.result_id ? <Link className="text-primary hover:underline" href={`/${user?.role}/results/${r.result_id}`}>{r.exam_name}</Link> : r.exam_name}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{fmtPct(r.percentage)}</td>
                  <td className="px-4 py-3 font-semibold">{r.grade}</td>
                  <td className="px-4 py-3 tabular-nums">{r.rank ?? "-"}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.is_pass ? "pass" : "fail"} label={r.is_pass ? "Pass" : "Fail"} /></td>
                  <td className="px-4 py-3 text-right">
                    {r.result_id ? <Button size="sm" variant="outline" onClick={() => pdf(r.result_id!, r.exam_name ?? "result")}><Download className="h-3.5 w-3.5" />PDF</Button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
