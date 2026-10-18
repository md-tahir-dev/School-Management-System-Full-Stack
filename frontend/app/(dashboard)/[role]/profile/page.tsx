"use client";

import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { Card } from "@/components/ui/card";
import { AccessDenied, EmptyState, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/components/forms";
import { dateLabel } from "@/lib/format";
import { useStudentScope } from "@/lib/queries";
import type { StudentDetail } from "@/lib/types";

function Section({ title, rows }: { title: string; rows: [string, string | null | undefined][] }) {
  return (
    <Card className="p-4">
      <h2 className="mb-3 font-semibold">{title}</h2>
      <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k}><dt className="text-muted-foreground">{k}</dt><dd className="font-medium">{v || "-"}</dd></div>
        ))}
      </dl>
    </Card>
  );
}

export default function ProfilePage() {
  const { user } = useAuth();
  const scope = useStudentScope();
  const ok = user?.role === "student" || user?.role === "parent";
  const q = useQuery({ queryKey: ["student", scope.studentId], queryFn: () => api<StudentDetail>(`/students/${scope.studentId}`), enabled: ok && !!scope.studentId });
  if (!user) return null;
  if (!ok) return <AccessDenied />;
  const s = q.data;
  const g = s?.guardian;
  return (
    <PageBoundary>
      <PageHeader title="Profile" actions={scope.isParent ? <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={scope.select} /> : undefined} />
      {scope.isLoading || q.isLoading ? <ListSkeleton rows={3} /> : scope.error || q.error ? <ErrorState error={scope.error ?? q.error} onRetry={() => q.refetch()} />
        : !scope.studentId || !s ? <EmptyState title="No student linked to this account" /> : (
          <div className="space-y-4">
            <Card className="flex items-center gap-4 p-4">
              {s.photo_url
                // eslint-disable-next-line @next/next/no-img-element -- uploaded photo served by the API
                ? <img src={s.photo_url} alt={`Photo of ${s.full_name}`} className="h-20 w-20 rounded-full object-cover" />
                : <span className="h-20 w-20 rounded-full bg-muted" aria-hidden />}
              <div>
                <h2 className="text-xl font-bold">{s.full_name}</h2>
                <p className="text-sm text-muted-foreground">Roll no. {s.roll_no} · {s.class_name}{s.section_name ? ` ${s.section_name}` : ""}</p>
                <div className="mt-2"><StatusBadge status={s.status} /></div>
              </div>
            </Card>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Personal" rows={[["Date of birth", s.dob ? dateLabel(s.dob) : null], ["Gender", s.gender && humanize(s.gender)], ["Religion", s.religion], ["Nationality", s.nationality], ["Blood group", s.blood_group], ["Address", [s.address, s.city].filter(Boolean).join(", ")]]} />
              <Section title="School" rows={[["Class", s.class_name], ["Section", s.section_name], ["Admission date", s.admission_date ? dateLabel(s.admission_date) : null], ["Previous school", s.previous_school]]} />
              <Section title="Father" rows={[["Name", g?.father_name], ["Phone", g?.father_phone], ["Occupation", g?.father_occupation]]} />
              <Section title="Mother" rows={[["Name", g?.mother_name], ["Phone", g?.mother_phone]]} />
              {(g?.guardian_name || g?.guardian_phone) && <Section title="Guardian" rows={[["Name", g?.guardian_name], ["Phone", g?.guardian_phone], ["Relation", g?.guardian_relation]]} />}
              <Section title="Emergency contact" rows={[["Name", s.emergency_name], ["Phone", s.emergency_phone]]} />
            </div>
          </div>
        )}
    </PageBoundary>
  );
}
