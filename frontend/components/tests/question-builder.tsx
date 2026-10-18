"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, errorText } from "@/lib/api";
import type { QuestionType, TestDetail } from "@/lib/types";

interface Q { key: number; type: QuestionType; text: string; options: string[]; correct: string; marks: string; model: string }
let seq = 0;
const fresh = (type: QuestionType): Q => ({ key: ++seq, type, text: "", options: type === "mcq" ? ["", ""] : [], correct: type === "tf" ? "true" : "", marks: "1", model: "" });
const TYPE_LABEL: Record<QuestionType, string> = { mcq: "Multiple choice", tf: "True / False", short: "Short answer" };

export function QuestionBuilder({ test, editable }: { test: TestDetail; editable: boolean }) {
  const qc = useQueryClient();
  const [qs, setQs] = useState<Q[]>([]);
  const [errs, setErrs] = useState<Record<string, string>>({});
  useEffect(() => {
    setQs(test.questions.map((q) => ({ key: ++seq, type: q.type, text: q.text, options: q.options ?? [], correct: q.correct_answer ?? "", marks: String(Number(q.marks)), model: q.model_answer ?? "" })));
  }, [test]);

  const patch = (i: number, p: Partial<Q>) => setQs((l) => l.map((q, j) => (j === i ? { ...q, ...p } : q)));
  const move = (i: number, d: number) => setQs((l) => { const n = [...l]; [n[i], n[i + d]] = [n[i + d]!, n[i]!]; return n; });

  const save = useMutation({
    mutationFn: () => api<TestDetail>(`/tests/${test.id}/questions`, {
      method: "PUT",
      body: { questions: qs.map((q) => ({
        type: q.type, text: q.text.trim(), marks: q.marks,
        options: q.type === "mcq" ? q.options.map((o) => o.trim()) : null,
        correct_answer: q.correct.trim() || null, model_answer: q.model.trim() || null,
      })) },
    }),
    onSuccess: () => { setErrs({}); toast.success("Questions saved"); qc.invalidateQueries({ queryKey: ["tests"] }); },
    onError: (e) => { setErrs(e instanceof ApiError ? e.fields ?? {} : {}); toast.error(errorText(e, "Couldn't save questions")); },
  });
  const total = qs.reduce((s, q) => s + (Number(q.marks) || 0), 0);
  const bad = qs.some((q) => !q.text.trim() || !(Number(q.marks) > 0) || (q.type === "mcq" && (q.options.some((o) => !o.trim()) || !q.options.includes(q.correct))));

  return (
    <div className="space-y-4">
      {!qs.length && <p className="text-sm text-muted-foreground">No questions yet.</p>}
      {qs.map((q, i) => {
        const err = Object.entries(errs).filter(([k]) => k.startsWith(`questions.${i}`)).map(([, v]) => v).join(" ");
        return (
          <fieldset key={q.key} disabled={!editable} className="space-y-3 rounded-lg border border-border bg-card p-4">
            <legend className="px-1 text-sm font-semibold">Question {i + 1} · {TYPE_LABEL[q.type]}</legend>
            <Textarea aria-label={`Question ${i + 1} text`} rows={2} value={q.text} onChange={(e) => patch(i, { text: e.target.value })} />
            {q.type === "mcq" && (
              <div role="radiogroup" aria-label={`Correct option for question ${i + 1}`} className="space-y-2">
                {q.options.map((o, k) => (
                  <div key={k} className="flex items-center gap-2">
                    <input type="radio" className="h-5 w-5" aria-label={`Mark option ${k + 1} correct`} checked={!!o && q.correct === o} onChange={() => patch(i, { correct: o })} />
                    <Input aria-label={`Option ${k + 1}`} value={o} onChange={(e) => patch(i, { options: q.options.map((x, y) => (y === k ? e.target.value : x)), correct: q.correct === o ? e.target.value : q.correct })} />
                    {editable && q.options.length > 2 && (
                      <Button type="button" variant="ghost" size="icon" aria-label={`Remove option ${k + 1}`} onClick={() => patch(i, { options: q.options.filter((_, y) => y !== k), correct: q.correct === o ? "" : q.correct })}><Trash2 className="h-4 w-4" /></Button>
                    )}
                  </div>
                ))}
                {editable && <Button type="button" size="sm" variant="outline" onClick={() => patch(i, { options: [...q.options, ""] })}>Add option</Button>}
              </div>
            )}
            {q.type === "tf" && (
              <div role="radiogroup" aria-label={`Correct answer for question ${i + 1}`} className="flex gap-4">
                {["true", "false"].map((v) => (
                  <label key={v} className="flex min-h-11 items-center gap-2 text-sm"><input type="radio" className="h-5 w-5" checked={q.correct === v} onChange={() => patch(i, { correct: v })} />{v === "true" ? "True" : "False"}</label>
                ))}
              </div>
            )}
            {q.type === "short" && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Input aria-label={`Exact answer for auto-marking, question ${i + 1} (optional)`} placeholder="Exact answer for auto-marking (optional)" value={q.correct} onChange={(e) => patch(i, { correct: e.target.value })} />
                <Input aria-label={`Model answer, question ${i + 1} (optional)`} placeholder="Model answer for the grader (optional)" value={q.model} onChange={(e) => patch(i, { model: e.target.value })} />
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-sm">Marks
                <Input type="number" min={0.5} step={0.5} className="w-24" value={q.marks} onChange={(e) => patch(i, { marks: e.target.value })} />
              </label>
              {editable && (
                <div className="ml-auto flex gap-1">
                  <Button type="button" variant="ghost" size="icon" aria-label={`Move question ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="h-4 w-4" /></Button>
                  <Button type="button" variant="ghost" size="icon" aria-label={`Move question ${i + 1} down`} disabled={i === qs.length - 1} onClick={() => move(i, 1)}><ArrowDown className="h-4 w-4" /></Button>
                  <Button type="button" variant="ghost" size="icon" aria-label={`Delete question ${i + 1}`} onClick={() => setQs((l) => l.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
                </div>
              )}
            </div>
            {err && <p role="alert" className="text-xs text-danger">{err}</p>}
          </fieldset>
        );
      })}
      {editable ? (
        <div className="flex flex-wrap items-center gap-2">
          {(["mcq", "tf", "short"] as const).map((t) => <Button key={t} type="button" variant="outline" onClick={() => setQs((l) => [...l, fresh(t)])}><Plus className="h-4 w-4" aria-hidden />{TYPE_LABEL[t]}</Button>)}
          <span className="ml-auto text-sm text-muted-foreground">Total {total} marks</span>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={bad}>Save questions</Button>
        </div>
      ) : <p className="text-sm text-muted-foreground">Questions are locked once a test is published. Total {total} marks.</p>}
    </div>
  );
}
