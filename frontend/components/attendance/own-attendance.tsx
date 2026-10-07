"use client";

import { PageHeader } from "@/components/page-header";
import { StudentAttendanceTab } from "@/components/attendance/student-attendance-tab";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useStudentScope } from "@/lib/queries";

/** Student and Parent portals: the same attendance tab, scoped to self / the selected child. */
export function OwnAttendance() {
  const scope = useStudentScope();
  return (
    <>
      <PageHeader title="Attendance" description={scope.child ? `${scope.child.full_name} · ${scope.child.class_name}${scope.child.section_name ? ` ${scope.child.section_name}` : ""}` : undefined}
        actions={scope.isParent ? <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /> : undefined} />
      {scope.isLoading ? <ListSkeleton rows={3} /> : scope.error ? <ErrorState error={scope.error} /> : !scope.studentId ? <EmptyState title="No student linked to this account" /> : <StudentAttendanceTab studentId={scope.studentId} />}
    </>
  );
}
