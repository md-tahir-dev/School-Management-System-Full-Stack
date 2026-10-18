"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { AccessDenied, EmptyState, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMyTeacher } from "@/lib/queries";
import type { Page, StudentListItem, TeacherDetail } from "@/lib/types";

type Assignment = TeacherDetail["assignments"][number];
interface Group { key: string; class_id: string; section_id: string | null; name: string; subjects: string[] }

function groupAssignments(items: Assignment[]): Group[] {
  const m = new Map<string, Group>();
  for (const a of items) {
    const key = `${a.class_id}:${a.section_id ?? ""}`;
    const g = m.get(key) ?? { key, class_id: a.class_id, section_id: a.section_id, name: `${a.class_name}${a.section_name ? ` ${a.section_name}` : ""}`, subjects: [] };
    if (!g.subjects.includes(a.subject_name)) g.subjects.push(a.subject_name);
    m.set(key, g);
  }
  return Array.from(m.values());
}

function ClassCard({ g, role }: { g: Group; role: string }) {
  // ponytail: first 100 students only; paginate if a section ever exceeds that.
  const q = useQuery({
    queryKey: ["students", "roster", g.class_id, g.section_id],
    queryFn: () => api<Page<StudentListItem>>("/students", { query: { class_id: g.class_id, ...(g.section_id ? { section_id: g.section_id } : {}), page_size: 100 } }),
  });
  return (
    <Card className="p-4">
      <h2 className="text-lg font-semibold">{g.name}</h2>
      <p className="mb-3 text-sm text-muted-foreground">{g.subjects.join(", ")}</p>
      {q.isLoading ? <ListSkeleton rows={3} /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data?.items.length ? <p className="text-sm text-muted-foreground">No students.</p> : (
        <ul className="divide-y divide-border text-sm">
          {q.data.items.map((s) => (
            <li key={s.id}>
              <Link href={`/${role}/students/${s.id}`} className="flex min-h-[44px] items-center justify-between gap-3 rounded-md px-1 hover:bg-muted/60">
                <span className="font-medium">{s.full_name}</span><span className="text-muted-foreground">{s.roll_no}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function ClassesPage() {
  const { user } = useAuth();
  const me = useMyTeacher();
  if (!user) return null;
  if (user.role !== "teacher") return <AccessDenied />;
  const groups = groupAssignments(me.data?.assignments ?? []);
  return (
    <PageBoundary>
      <PageHeader title="My classes" />
      {me.isLoading ? <ListSkeleton rows={3} /> : me.error ? <ErrorState error={me.error} onRetry={() => me.refetch()} /> : groups.length === 0 ? <EmptyState title="No classes assigned yet" /> : (
        <div className="grid gap-4 lg:grid-cols-2">{groups.map((g) => <ClassCard key={g.key} g={g} role={user.role} />)}</div>
      )}
    </PageBoundary>
  );
}
