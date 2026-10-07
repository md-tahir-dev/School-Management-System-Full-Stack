"use client";

import { MarkAttendance } from "@/components/attendance/mark-attendance";
import { OwnAttendance } from "@/components/attendance/own-attendance";
import { AttendanceReports } from "@/components/attendance/reports";
import { PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";

export default function AttendancePage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <PageBoundary>
      {user.role === "teacher" ? <MarkAttendance /> : user.role === "admin" || user.role === "ceo" ? <AttendanceReports /> : <OwnAttendance />}
    </PageBoundary>
  );
}
