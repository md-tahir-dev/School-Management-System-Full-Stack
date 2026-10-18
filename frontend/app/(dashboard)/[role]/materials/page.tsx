"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { FileLink } from "@/components/diary/common";
import { MATERIAL_TYPES, MaterialForm } from "@/components/diary/material-form";
import { humanize } from "@/components/forms";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { ChildSwitcher } from "@/components/results/child-switcher";
import { StatusBadge } from "@/components/status-badge";
import { DataTable, type Column } from "@/components/tables/data-table";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { PageBoundary } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateLabel } from "@/lib/format";
import { useStudentScope, useSubjects } from "@/lib/queries";
import { isManager } from "@/lib/role-config";
import type { Material, Page } from "@/lib/types";

export default function MaterialsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const scope = useStudentScope();
  const subjects = useSubjects();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [subject, setSubject] = useState("");
  const [type, setType] = useState("");
  const [upload, setUpload] = useState(false);
  const [del, setDel] = useState<Material | null>(null);
  const isParent = user?.role === "parent";
  const canUpload = user?.role === "teacher" || isManager(user?.role);

  const list = useQuery({
    queryKey: ["materials", { page, q, subject, type, student: isParent ? scope.studentId : null }],
    queryFn: () => api<Page<Material>>("/materials", { query: { page, page_size: 10, q, subject_id: subject, type, student_id: isParent ? scope.studentId : undefined } }),
    enabled: !!user && (!isParent || !!scope.studentId),
    placeholderData: (p) => p,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/materials/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Material deleted"); qc.invalidateQueries({ queryKey: ["materials"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete material")),
  });
  if (!user) return null;

  const linkCls = "inline-flex min-h-11 items-center gap-1.5 text-sm font-medium text-primary hover:underline";
  const columns: Column<Material>[] = [
    { key: "title", header: "Title", cell: (m) => <div><div className="font-medium">{m.title}</div>{m.description && <div className="line-clamp-2 text-xs text-muted-foreground">{m.description}</div>}</div> },
    { key: "subject", header: "Subject", cell: (m) => m.subject_name ?? "-" },
    { key: "class", header: "Class", cell: (m) => `${m.class_name}${m.section_name ? ` ${m.section_name}` : ""}` },
    { key: "type", header: "Type", cell: (m) => <StatusBadge status={m.type} label={humanize(m.type)} tone="info" /> },
    { key: "author", header: "Added by", cell: (m) => <div>{m.author_name ?? "-"}<div className="text-xs text-muted-foreground">{dateLabel(m.created_at.slice(0, 10))}</div></div> },
    {
      key: "open", header: "Open", cell: (m) => (
        <div className="flex flex-wrap items-center gap-x-3">
          {m.file_url && <FileLink href={m.file_url} label="File" />}
          {m.external_link && <a href={m.external_link} target="_blank" rel="noopener noreferrer" className={linkCls}><ExternalLink className="h-4 w-4" aria-hidden />Link</a>}
          {m.can_edit && <Button variant="ghost" size="icon" aria-label={`Delete ${m.title}`} onClick={() => setDel(m)}><Trash2 className="h-4 w-4" /></Button>}
        </div>
      ),
    },
  ];

  return (
    <PageBoundary>
      <PageHeader title="Materials" description="Notes, past papers and reference material." />
      <DataTable
        columns={columns}
        rows={list.data?.items}
        rowKey={(m) => m.id}
        total={list.data?.total ?? 0}
        page={page}
        pageSize={10}
        onPageChange={setPage}
        onSearchChange={(v) => { setQ(v); setPage(1); }}
        searchPlaceholder="Search materials"
        isLoading={list.isLoading}
        isFetching={list.isFetching}
        error={list.error as Error | null}
        onRetry={() => list.refetch()}
        emptyTitle="No materials yet"
        filters={
          <>
            {isParent && <ChildSwitcher kids={scope.children} value={scope.studentId} onChange={(id) => { scope.select(id); setPage(1); }} />}
            <Select aria-label="Subject" value={subject} onChange={(e) => { setSubject(e.target.value); setPage(1); }}>
              <option value="">All subjects</option>
              {subjects.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
            <Select aria-label="Type" value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}>
              <option value="">All types</option>
              {MATERIAL_TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </Select>
          </>
        }
        actions={canUpload ? <Button onClick={() => setUpload(true)}><Upload className="h-4 w-4" aria-hidden />Upload material</Button> : undefined}
      />
      {canUpload && <MaterialForm open={upload} onClose={() => setUpload(false)} isTeacher={user.role === "teacher"} />}
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(null)} title="Delete material" description={`Delete "${del?.title}"?`} confirmLabel="Delete material" destructive onConfirm={async () => { await remove.mutateAsync(del!.id).catch(() => {}); }} />
    </PageBoundary>
  );
}
