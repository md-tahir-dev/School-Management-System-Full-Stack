"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { AnnouncementForm } from "@/components/announcements/form";
import { ConfirmDialog } from "@/components/modals/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, ListSkeleton, PageBoundary } from "@/components/ui/state-views";
import { api, errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/components/forms";
import { targetLabel } from "@/lib/format";
import { isManager } from "@/lib/role-config";
import type { Announcement, Page } from "@/lib/types";

const PAGE_SIZE = 10;
export default function AnnouncementsPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Announcement | null>(null);

  const q = useQuery({
    queryKey: ["announcements", page],
    queryFn: () => api<Page<Announcement>>("/announcements", { query: { page, page_size: PAGE_SIZE } }),
    enabled: !!user,
  });
  const del = useMutation({
    mutationFn: (id: string) => api(`/announcements/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Announcement deleted"); qc.invalidateQueries({ queryKey: ["announcements"] }); },
    onError: (e) => toast.error(errorText(e, "Couldn't delete announcement")),
  });
  if (!user) return null;
  const canPost = isManager(user.role) || user.role === "teacher";
  const items = q.data?.items ?? [];

  return (
    <PageBoundary>
      <PageHeader
        title="Announcements"
        description="News and notices from the school."
        actions={canPost ? <Button onClick={() => setCreating(true)}>New announcement</Button> : undefined}
      />
      {q.isLoading ? <ListSkeleton rows={4} /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !items.length ? (
        <EmptyState title="No announcements yet" />
      ) : (
        <ul className="space-y-3">
          {items.map((a) => (
            <li key={a.id}>
              <article className={`rounded-lg border bg-card p-4 ${a.priority === "important" ? "border-warning bg-amber-50" : "border-border"}`}>
                <div className="flex flex-wrap items-start gap-2">
                  <h2 className="min-w-0 flex-1 text-base font-semibold">{a.title}</h2>
                  {a.priority === "important" && <StatusBadge status="important" tone="warning" />}
                  {a.can_edit && (
                    <Button variant="ghost" size="icon" aria-label={`Delete announcement ${a.title}`} onClick={() => setDeleting(a)}>
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </Button>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {targetLabel(a)} · {humanize(a.audience)} · {a.author_name ?? "School"} · {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(a.created_at))}
                </p>
                <p className="mt-3 whitespace-pre-line text-sm">{a.message}</p>
              </article>
            </li>
          ))}
        </ul>
      )}
      {q.data && q.data.pages > 1 && (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-between">
          <Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-sm text-muted-foreground">Page {page} of {q.data.pages}</span>
          <Button variant="outline" disabled={page >= q.data.pages} onClick={() => setPage(page + 1)}>Next</Button>
        </nav>
      )}
      <AnnouncementForm open={creating} onClose={() => setCreating(false)} role={user.role} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete announcement"
        description={`"${deleting?.title ?? ""}" will be removed for everyone.`}
        confirmLabel="Delete announcement"
        destructive
        onConfirm={async () => { await del.mutateAsync(deleting!.id).catch(() => {}); }}
      />
    </PageBoundary>
  );
}
