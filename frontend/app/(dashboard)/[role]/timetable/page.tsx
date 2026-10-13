"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { PageHeader } from "@/components/page-header";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { CellDialog, type CellTarget } from "@/components/timetable/cell-dialog";
import { TimetableGrid, useMyTimetable } from "@/components/timetable/grid";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useClasses, useSections, useStudentScope } from "@/lib/queries";
import { isManager, isSchoolWide } from "@/lib/role-config";
import type { Timetable, TimetableEntry } from "@/lib/types";

function View({ q, cell, onCellClick }: { q: { data?: Timetable; isLoading: boolean; error: Error | null; refetch: () => void }; cell: (e: TimetableEntry) => React.ReactNode; onCellClick?: (wd: number, pid: string, e?: TimetableEntry) => void }) {
  if (q.isLoading) return <ListSkeleton rows={6} />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data?.periods.length) return <EmptyState title="No periods configured" hint="Periods are set up under Settings." />;
  return <TimetableGrid data={q.data} cell={cell} onCellClick={onCellClick} />;
}

const Lecture = ({ e, second }: { e: TimetableEntry; second: string }) => (
  <div>
    <div className="font-medium">{e.subject_name}</div>
    <div className="text-xs text-muted-foreground">{second}{e.room ? ` · ${e.room}` : ""}</div>
  </div>
);

/** Admin/headmaster edit, CEO read-only. */
function ClassTimetable({ canEdit }: { canEdit: boolean }) {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [sec, setSec] = useState("");
  const cid = classId || classes.data?.[0]?.id || "";
  const sections = useSections(cid || undefined);
  const hasSections = !!sections.data?.length;
  const sid = hasSections ? (sections.data!.some((s) => s.id === sec) ? sec : sections.data![0]!.id) : "";
  const [target, setTarget] = useState<CellTarget | null>(null);
  const q = useQuery({
    queryKey: ["timetable", "class", cid, sid],
    queryFn: () => api<Timetable>("/timetable", { query: { class_id: cid, section_id: sid || undefined } }),
    enabled: !!cid && !sections.isLoading,
  });
  const clsName = classes.data?.find((c) => c.id === cid)?.name ?? "";
  const secName = sections.data?.find((s) => s.id === sid)?.name;
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        <Select aria-label="Class" value={cid} onChange={(e) => { setClassId(e.target.value); setSec(""); }}>
          {classes.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        {hasSections && (
          <Select aria-label="Section" value={sid} onChange={(e) => setSec(e.target.value)}>
            {sections.data!.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        )}
      </div>
      {!cid ? <EmptyState title="No classes yet" /> : (
        <View
          q={q}
          cell={(e) => <Lecture e={e} second={e.teacher_name} />}
          onCellClick={canEdit ? (weekday, periodId, entry) => setTarget({ classId: cid, sectionId: sid || null, weekday, periodId, entry, label: `${clsName}${secName ? ` ${secName}` : ""}` }) : undefined}
        />
      )}
      {canEdit && <CellDialog target={target} onClose={() => setTarget(null)} />}
    </>
  );
}

function OwnTimetable({ role }: { role: string }) {
  const scope = useStudentScope();
  const isTeacher = role === "teacher";
  const q = useMyTimetable(scope.studentId, isTeacher || !!scope.studentId);
  return (
    <>
      {role === "parent" && <div className="mb-4"><ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /></div>}
      {!isTeacher && scope.error ? <ErrorState error={scope.error} /> : (
        <View q={q} cell={(e) => <Lecture e={e} second={isTeacher ? `${e.class_name}${e.section_name ? ` ${e.section_name}` : ""}` : e.teacher_name} />} />
      )}
    </>
  );
}

export default function TimetablePage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <PageBoundary>
      <PageHeader title="Timetable" description="Weekly lectures by period." />
      {isSchoolWide(user.role) ? <ClassTimetable canEdit={isManager(user.role)} /> : <OwnTimetable role={user.role} />}
    </PageBoundary>
  );
}
