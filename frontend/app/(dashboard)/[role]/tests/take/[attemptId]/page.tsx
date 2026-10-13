"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtMarks } from "@/lib/format";
import type { AttemptResult, AttemptView } from "@/lib/types";

const mmss = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

function ResultView({ r, role }: { r: AttemptResult; role: string }) {
  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        <p className="text-lg font-semibold">{r.released && r.score != null ? `Score: ${fmtMarks(r.score)} / ${fmtMarks(r.total_marks)}` : "Submitted. Your teacher will release the results."}</p>
        {r.answers.length > 0 && (
          <ol className="space-y-3">
            {r.answers.map((a, i) => (
              <li key={a.question_id} className="space-y-1 rounded-md border border-border p-3 text-sm">
                <p className="font-medium">{i + 1}. {a.text}</p>
                <p><span className="text-muted-foreground">Your answer:</span> {a.answer || <em>No answer</em>}</p>
                {a.correct_answer && <p><span className="text-muted-foreground">Correct answer:</span> {a.correct_answer}</p>}
                <p className="text-muted-foreground">{a.marks_awarded != null ? fmtMarks(a.marks_awarded) : "-"} / {fmtMarks(a.marks)}</p>
              </li>
            ))}
          </ol>
        )}
        <Button asChild variant="outline"><Link href={`/${role}/tests`}>Back to tests</Link></Button>
      </CardContent>
    </Card>
  );
}

function Taker({ view, role }: { view: AttemptView; role: string }) {
  // Offset from the server clock so a wrong device clock doesn't shorten or lengthen the test.
  const [offset] = useState(() => Date.parse(view.server_now) - Date.now());
  const deadline = Date.parse(view.expires_at);
  const left = () => deadline - (Date.now() + offset);
  const [remaining, setRemaining] = useState(left);
  const [answers, setAnswers] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(view.answers).map(([k, v]) => [k, v ?? ""])));
  const [idx, setIdx] = useState(0);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [saved, setSaved] = useState<"" | "saving" | "saved" | "error">("");
  const dirty = useRef(new Set<string>());
  const latest = useRef(answers);
  const submitting = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  latest.current = answers;

  const flush = useCallback(async () => {
    if (!dirty.current.size || submitting.current) return;
    const ids = [...dirty.current];
    dirty.current.clear();
    setSaved("saving");
    try {
      await api(`/tests/attempts/${view.attempt_id}/answers`, { method: "PUT", body: { answers: ids.map((question_id) => ({ question_id, answer: latest.current[question_id] ?? "" })) } });
      setSaved("saved");
    } catch {
      ids.forEach((i) => dirty.current.add(i));
      setSaved("error");
    }
  }, [view.attempt_id]);

  const change = (qid: string, v: string) => {
    setAnswers((a) => ({ ...a, [qid]: v }));
    dirty.current.add(qid);
    clearTimeout(timer.current);
    timer.current = setTimeout(flush, 2000);
  };

  const submit = useCallback(async () => {
    if (submitting.current) return;
    submitting.current = true;
    clearTimeout(timer.current);
    try {
      const r = await api<AttemptResult>(`/tests/attempts/${view.attempt_id}/submit`, {
        method: "POST",
        body: { answers: view.questions.map((q) => ({ question_id: q.id, answer: latest.current[q.id] ?? "" })) },
      });
      setResult(r);
    } catch (e) {
      submitting.current = false;
      toast.error(errorText(e, "Couldn't submit. Try again."));
    }
  }, [view]);

  useEffect(() => {
    if (result) return;
    const t = setInterval(() => {
      const l = left();
      setRemaining(l);
      if (l <= 0) { toast.info("Time is up. Submitting your answers."); submit(); }
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, submit]);

  useEffect(() => {
    if (result) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [result]);

  const minutes = Math.ceil(remaining / 60000);
  const qs = view.questions;
  const shown = view.show_one_by_one ? qs.slice(idx, idx + 1) : qs;
  const answered = qs.filter((q) => (answers[q.id] ?? "").trim()).length;

  return (
    <>
      <PageHeader
        title={view.title}
        actions={result ? undefined : (
          <div className="text-right">
            <p className={`text-2xl font-bold tabular-nums ${remaining < 60000 ? "text-danger" : ""}`} aria-hidden>{mmss(remaining)}</p>
            <p className="sr-only" aria-live="polite">{minutes} {minutes === 1 ? "minute" : "minutes"} remaining</p>
          </div>
        )}
      />
      {result ? <ResultView r={result} role={role} /> : (
        <div className="space-y-4">
          {view.instructions && <p className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">{view.instructions}</p>}
          {shown.map((q) => {
            const n = qs.indexOf(q) + 1;
            const val = answers[q.id] ?? "";
            const opts = q.type === "tf" ? ["true", "false"] : q.options ?? [];
            return (
              <fieldset key={q.id} className="space-y-3 rounded-lg border border-border bg-card p-4">
                <legend className="px-1 text-sm font-semibold">Question {n} of {qs.length} <span className="font-normal text-muted-foreground">({fmtMarks(q.marks)} marks)</span></legend>
                <p className="whitespace-pre-wrap text-sm">{q.text}</p>
                {q.type === "short" ? (
                  <Textarea aria-label={`Answer to question ${n}`} rows={4} value={val} onChange={(e) => change(q.id, e.target.value)} onBlur={flush} />
                ) : (
                  <div className="space-y-1">
                    {opts.map((o) => (
                      <label key={o} className="flex min-h-11 items-center gap-3 text-sm">
                        <input type="radio" className="h-5 w-5" name={q.id} checked={val === o} onChange={() => { change(q.id, o); flush(); }} />
                        {q.type === "tf" ? (o === "true" ? "True" : "False") : o}
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            );
          })}
          <div className="flex flex-wrap items-center gap-2">
            {view.show_one_by_one && (
              <>
                <Button variant="outline" disabled={idx === 0} onClick={() => { flush(); setIdx(idx - 1); }}>Previous</Button>
                <Button variant="outline" disabled={idx === qs.length - 1} onClick={() => { flush(); setIdx(idx + 1); }}>Next</Button>
              </>
            )}
            <span className="text-sm text-muted-foreground" role="status">{answered}/{qs.length} answered{saved === "saving" ? " · saving..." : saved === "saved" ? " · saved" : saved === "error" ? " · couldn't save, will retry" : ""}</span>
            <Button className="ml-auto" onClick={() => setConfirm(true)}>Submit</Button>
          </div>
          <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Submit test" description={`You answered ${answered} of ${qs.length} questions. You can't change answers after submitting.`} confirmLabel="Submit test" onConfirm={submit} />
        </div>
      )}
    </>
  );
}

export default function TakeTestPage() {
  const { attemptId } = useParams<{ attemptId: string }>();
  const { user } = useAuth();
  const q = useQuery({
    queryKey: ["tests", "take", attemptId],
    queryFn: async () => {
      const view = await api<AttemptView>(`/tests/attempts/${attemptId}`);
      const result = view.status === "in_progress" ? null : await api<AttemptResult>(`/tests/attempts/${attemptId}/result`);
      return { view, result };
    },
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
  if (!user) return null;
  return (
    <PageBoundary>
      {q.isLoading ? <ListSkeleton rows={3} /> : q.error || !q.data ? <ErrorState error={q.error as Error} /> : q.data.result ? (
        <>
          <PageHeader title={q.data.view.title} />
          <ResultView r={q.data.result} role={user.role} />
        </>
      ) : <Taker view={q.data.view} role={user.role} />}
    </PageBoundary>
  );
}
