"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api, errorText } from "@/lib/api";
import type { NotificationOut, Page, Role } from "@/lib/types";
import { cn } from "@/lib/utils";

const when = (iso: string) => new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso));

/** Radix dropdown gives Escape, arrow-key navigation and focus return to the bell for free. */
export function NotificationBell({ role }: { role: Role }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const count = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    select: (d) => d.count,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => api<Page<NotificationOut>>("/notifications", { query: { page_size: 10 } }),
    select: (p) => p.items,
    enabled: open,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const readOne = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: refresh,
    onError: (e) => toast.error(errorText(e, "Couldn't update notification")),
  });
  const readAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: refresh,
    onError: (e) => toast.error(errorText(e, "Couldn't mark notifications read")),
  });

  const unread = count.data ?? 0;
  const items = list.data ?? [];
  const open1 = (n: NotificationOut) => {
    if (!n.is_read) readOne.mutate(n.id);
    if (n.link) router.push(`/${role}/${n.link.replace(/^\//, "")}`);
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span aria-hidden className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold leading-none text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 max-w-[calc(100vw-1rem)]">
        <DropdownMenuLabel className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">Notifications</p>
          <Button variant="ghost" size="sm" disabled={!unread || readAll.isPending} onClick={() => readAll.mutate()}>Mark all read</Button>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <div className="max-h-96 overflow-y-auto">
          {list.isLoading ? (
            <p className="px-2.5 py-3 text-sm text-muted-foreground">Loading...</p>
          ) : list.isError ? (
            <p role="alert" className="px-2.5 py-3 text-sm text-danger">Couldn&apos;t load notifications.</p>
          ) : !items.length ? (
            <p className="px-2.5 py-3 text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            items.map((n) => (
              <DropdownMenuItem key={n.id} onSelect={() => open1(n)} className="min-h-11 flex-col items-start gap-0.5">
                <span className={cn("text-sm", n.is_read ? "text-muted-foreground" : "font-bold")}>
                  {!n.is_read && <span className="sr-only">Unread: </span>}
                  {n.message}
                </span>
                <span className="text-xs text-muted-foreground">{when(n.created_at)}</span>
              </DropdownMenuItem>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
