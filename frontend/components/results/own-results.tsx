"use client";

import { PageHeader } from "@/components/page-header";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { StudentResultsTab } from "@/components/results/student-results-tab";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/ui/state-views";
import { useStudentScope } from "@/lib/queries";

export function OwnResults() {
  const scope = useStudentScope();
  return (
    <>
      <PageHeader title="Results" description={scope.child ? `${scope.child.full_name} · ${scope.child.class_name}${scope.child.section_name ? ` ${scope.child.section_name}` : ""}` : undefined}
        actions={scope.isParent ? <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /> : undefined} />
      {scope.isLoading ? <ListSkeleton rows={3} /> : scope.error ? <ErrorState error={scope.error} /> : !scope.studentId ? <EmptyState title="No student linked to this account" /> : <StudentResultsTab studentId={scope.studentId} />}
    </>
  );
}
