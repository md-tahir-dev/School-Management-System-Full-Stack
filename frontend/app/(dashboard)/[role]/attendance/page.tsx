"use client";

import { MarkAttendance } from "@/components/attendance/mark-attendance";
import { OwnAttendance } from "@/components/attendance/own-attendance";
import { AttendanceReports } from "@/components/attendance/reports";
import { PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";

export default function AttendancePage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <PageBoundary>
      {user.role === "teacher" ? <MarkAttendance /> : isSchoolWide(user.role) ? <AttendanceReports /> : <OwnAttendance />}
    </PageBoundary>
  );
}
