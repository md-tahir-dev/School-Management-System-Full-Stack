"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { ByStudentEntry } from "@/components/results/by-student-entry";
import { MarksGrid } from "@/components/results/marks-grid";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { EmptyState, ErrorState } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMyTeacher, useSections } from "@/lib/queries";
import type { Exam, ExamSubject, Page } from "@/lib/types";

/** Pickers shared by the teacher page and the admin "Enter marks" tab. Teachers only get assigned combinations. */
export function MarksEntry({ fixedExam, embedded }: { fixedExam?: Exam; embedded?: boolean }) {
  const { user } = useAuth();
  const isTeacher = user?.role === "teacher";
  const isAdmin = user?.role === "admin";
  const me = useMyTeacher();
  const exams = useQuery({
    queryKey: ["exams", "entry-picker"],
    queryFn: () => api<Page<Exam>>("/exams", { query: { page_size: 100 } }),
    select: (p) => p.items,
    enabled: !fixedExam,
  });
  const [examId, setExamId] = useState(fixedExam?.id ?? "");
  const exam = fixedExam ?? exams.data?.find((e) => e.id === examId);
  const [sectionId, setSectionId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [mode, setMode] = useState<"grid" | "student">("grid");

  const examSubjects = useQuery({
    queryKey: ["exam-subjects", exam?.id],
    queryFn: () => api<ExamSubject[]>(`/exams/${exam!.id}/subjects`),
    enabled: !!exam,
  });
  const allSections = useSections(isTeacher ? undefined : exam?.class_id);

  // Teacher assignments for this exam's class: (section, subject) pairs they may enter.
  const mine = useMemo(() => (me.data?.assignments ?? []).filter((a) => a.class_id === exam?.class_id), [me.data, exam?.class_id]);
  const sectionOptions = isTeacher
    ? [...new Map(mine.map((a) => [a.section_id ?? "", a.section_name ?? "All sections"])).entries()].map(([id, name]) => ({ id, name }))
    : (allSections.data ?? []).map((s) => ({ id: s.id, name: s.name }));
  const subjectOptions = isTeacher
    ? mine.filter((a) => (a.section_id ?? "") === sectionId).map((a) => ({ id: a.subject_id, name: a.subject_name })).filter((s) => examSubjects.data?.some((x) => x.subject_id === s.id))
    : (examSubjects.data ?? []).map((s) => ({ id: s.subject_id, name: s.subject_name }));

  useEffect(() => { setSectionId(""); setSubjectId(""); }, [exam?.id]);
  useEffect(() => { setSubjectId(""); }, [sectionId]);

  const ready = !!exam && sectionId !== "" && !!subjectId;
  return (
    <>
      {!embedded && <PageHeader title="Marks entry" description="Enter marks for the classes and subjects you teach." />}
      <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-3">
        {!fixedExam && (
          <Field label="Exam">
            {exams.error ? <ErrorState error={exams.error} /> : (
              <Select value={examId} onChange={(e) => setExamId(e.target.value)}>
                <option value="" disabled>Select exam</option>
                {exams.data?.map((e) => <option key={e.id} value={e.id}>{e.name} · {e.class_name}{e.is_published ? " (published)" : ""}</option>)}
              </Select>
            )}
          </Field>
        )}
        <Field label="Section"><Select value={sectionId} onChange={(e) => setSectionId(e.target.value)} disabled={!exam}><option value="" disabled>Select section</option>{sectionOptions.map((s) => <option key={s.id || "all"} value={s.id}>{s.name}</option>)}</Select></Field>
        <Field label="Subject"><Select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} disabled={sectionId === "" || !exam}><option value="" disabled>Select subject</option>{subjectOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
      </Card>

      {isTeacher && exam && !me.isLoading && mine.length === 0 && <EmptyState title="You aren't assigned to this exam's class" hint="Only your assigned class, section and subject combinations can be entered." />}

      {exam && (
        <>
          <Tabs label="Entry style" value={mode} onChange={setMode} tabs={[{ key: "grid", label: "Grid (by subject)" }, { key: "student", label: "By student" }]} />
          {mode === "grid" && (ready ? <MarksGrid key={`${exam.id}${sectionId}${subjectId}`} examId={exam.id} sectionId={sectionId} subjectId={subjectId} isAdmin={isAdmin} /> : <EmptyState title="Pick a section and subject to open the marks grid" />)}
          {mode === "student" && <ByStudentEntry key={exam.id} exam={exam} isAdmin={isAdmin} />}
        </>
      )}
      {!exam && <EmptyState title="Pick an exam to begin" />}
    </>
  );
}
