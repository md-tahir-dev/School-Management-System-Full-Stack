"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { StudentAttendanceTab } from "@/components/attendance/student-attendance-tab";
import { StudentResultsTab } from "@/components/results/student-results-tab";
import { StudentProfileTab } from "@/components/students/student-profile-tab";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card } from "@/components/ui/card";
import { Tabs } from "@/components/ui/tabs";
import { AccessDenied, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";
import { fmtPct } from "@/lib/format";
import type { StudentDetail } from "@/lib/types";

/** Profile header card plus Profile, Attendance and Results tabs. */
export default function StudentProfile({ params }: { params: { id: string } }) {
  const { user } = useAuth();
  const [tab, setTab] = useState<"profile" | "attendance" | "results">("attendance");
  const allowed = isSchoolWide(user?.role) || user?.role === "teacher";
  const q = useQuery({ queryKey: ["student", params.id], queryFn: () => api<StudentDetail>(`/students/${params.id}`), enabled: allowed });
  if (user && !allowed) return <AccessDenied />;
  if (q.isLoading) return <ListSkeleton rows={3} />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data;
  return (
    <PageBoundary>
      <Link href={`/${user?.role}/students`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"><ArrowLeft className="h-4 w-4" />All students</Link>
      <PageHeader title={s.full_name} description={`Roll no. ${s.roll_no} · ${s.class_name}${s.section_name ? ` · ${s.section_name}` : ""}`} actions={<StatusBadge status={s.status} />} />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:max-w-md">
        <Card className="p-4"><p className="text-2xl font-bold tabular-nums">{s.attendance_percentage === null || s.attendance_percentage === undefined ? "-" : fmtPct(s.attendance_percentage)}</p><p className="text-sm text-muted-foreground">Attendance</p></Card>
        <Card className="p-4"><p className="text-2xl font-bold">{s.latest_result_grade ?? "-"}</p><p className="text-sm text-muted-foreground">Latest grade</p></Card>
      </div>
      <Tabs label="Student sections" value={tab} onChange={setTab} tabs={[{ key: "attendance", label: "Attendance" }, { key: "results", label: "Results" }, { key: "profile", label: "Profile" }]} />
      {tab === "profile" ? <StudentProfileTab student={s} /> : tab === "attendance" ? <StudentAttendanceTab studentId={s.id} /> : <StudentResultsTab studentId={s.id} />}
    </PageBoundary>
  );
}
