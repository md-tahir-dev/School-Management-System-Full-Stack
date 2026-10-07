"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, Printer } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { api, apiBlob, saveBlob } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtMarks, fmtPct } from "@/lib/format";
import type { PublicConfig, ResultOut } from "@/lib/types";
import { cn } from "@/lib/utils";

/** On-screen result card that mirrors the PDF. Print uses print-only CSS (see globals.css). */
export function ResultCardPage({ resultId }: { resultId: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const q = useQuery({ queryKey: ["result", resultId], queryFn: () => api<ResultOut>(`/results/${resultId}`) });
  const school = useQuery({ queryKey: ["public-config"], queryFn: () => api<PublicConfig>("/public/config", { auth: false }), staleTime: 5 * 60_000 });

  if (q.isLoading) return <ListSkeleton rows={6} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} title="This result isn't available" />;
  const r = q.data;
  const showRank = r.status === "complete" && r.rank !== null && r.is_pass;

  async function pdf() {
    setBusy(true);
    try { saveBlob(await apiBlob(`/results/${resultId}/pdf`), `${r.roll_no}-${r.exam_name}.pdf`); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Couldn't download the PDF"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div className="no-print">
        <button type="button" onClick={() => router.back()} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />Back</button>
        <PageHeader title="Result card" actions={<>
          <Button variant="outline" onClick={() => window.print()}><Printer className="h-4 w-4" />Print</Button>
          <Button onClick={pdf} loading={busy}><Download className="h-4 w-4" />Download PDF</Button>
        </>} />
        {!r.is_published && <p role="status" className="mb-4 rounded-md bg-amber-50 p-3 text-sm text-amber-900">Draft: this exam isn't published yet, so only staff can see this card.</p>}
      </div>

      <article className="relative mx-auto max-w-3xl overflow-hidden rounded-lg border border-border bg-card p-6 shadow-sm sm:p-10 print:border-0 print:shadow-none" aria-label={`Result card for ${r.student_name}`}>
        {!r.is_published && <span aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center text-8xl font-black uppercase text-slate-200/60 [transform:rotate(-30deg)]">Draft</span>}
        <header className="border-b-2 border-primary pb-4 text-center">
          {school.data?.logo_url
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={school.data.logo_url} alt="" className="mx-auto mb-2 h-16 w-16 object-contain" /> : null}
          <h2 className="text-2xl font-bold">{school.data?.school_name ?? "School"}</h2>
          {school.data?.slogan && <p className="text-sm italic text-muted-foreground">{school.data.slogan}</p>}
          <p className="mt-2 text-lg font-semibold uppercase tracking-wide text-primary">{r.exam_name} · Result card</p>
        </header>

        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          {([["Student", r.student_name], ["Roll no.", r.roll_no], ["Father", r.father_name ?? "-"], ["Class", r.class_name], ["Section", r.section_name ?? "-"], ["Academic year", r.academic_year_label]] as const).map(([k, v]) => (
            <div key={k}><dt className="text-xs text-muted-foreground">{k}</dt><dd className="font-semibold" dir="auto">{v}</dd></div>
          ))}
        </dl>

        <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[28rem] border-collapse text-left text-sm">
          <thead><tr className="bg-slate-100">{["Subject", "Total", "Passing", "Obtained", "Status"].map((h) => <th key={h} scope="col" className="border border-border px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
          <tbody>
            {r.subjects.map((s) => (
              <tr key={s.subject_id}>
                <td className="border border-border px-3 py-2 font-medium">{s.subject_name}</td>
                <td className="border border-border px-3 py-2 tabular-nums">{fmtMarks(s.total_marks)}</td>
                <td className="border border-border px-3 py-2 tabular-nums">{fmtMarks(s.passing_marks)}</td>
                <td className="border border-border px-3 py-2 tabular-nums">{s.is_absent ? "-" : fmtMarks(s.obtained_marks)}</td>
                <td className="border border-border px-3 py-2"><StatusBadge status={s.status === "AB" ? "absent" : s.status.toLowerCase()} label={s.status} /></td>
              </tr>
            ))}
          </tbody>
        </table></div>

        {r.status === "complete" ? (
          <div className="relative mt-5 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-4 text-sm sm:grid-cols-5">
            <div><p className="text-xs text-muted-foreground">Total marks</p><p className="font-bold tabular-nums">{fmtMarks(r.total_possible)}</p></div>
            <div><p className="text-xs text-muted-foreground">Obtained</p><p className="font-bold tabular-nums">{fmtMarks(r.total_obtained)}</p></div>
            <div><p className="text-xs text-muted-foreground">Percentage</p><p className="font-bold tabular-nums">{fmtPct(r.percentage)}</p></div>
            <div><p className="text-xs text-muted-foreground">Grade</p><p className="font-bold">{r.grade}</p></div>
            {showRank && <div><p className="text-xs text-muted-foreground">Position</p><p className="font-bold tabular-nums">{r.rank} of {r.total_ranked}</p></div>}
          </div>
        ) : <p className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">Marks for some subjects are still pending, so the overall result isn't available yet.</p>}

        {r.status === "complete" && (
          <div aria-label={r.is_pass ? "Passed" : "Failed"} className={cn("pointer-events-none mx-auto mt-6 w-fit rounded-lg border-4 px-8 py-1 text-4xl font-black tracking-widest opacity-70 [transform:rotate(-6deg)]", r.is_pass ? "border-green-600 text-green-600" : "border-red-600 text-red-600")}>
            {r.is_pass ? "PASS" : "FAIL"}
          </div>
        )}
        {r.remarks && <p className="mt-5 text-sm"><strong>Remarks:</strong> {r.remarks}</p>}
        <footer className="mt-12 grid grid-cols-2 gap-10 text-center text-xs text-muted-foreground">
          <div className="border-t border-slate-400 pt-1">Class teacher</div><div className="border-t border-slate-400 pt-1">Principal</div>
        </footer>
      </article>
      <p className="no-print mt-4 text-center text-xs text-muted-foreground">{user?.role === "ceo" ? "Read-only view." : ""}</p>
    </>
  );
}

