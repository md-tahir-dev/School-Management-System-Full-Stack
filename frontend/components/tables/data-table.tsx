"use client";

import { AlertCircle, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  className?: string;
  align?: "left" | "right";
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  /** Server-side pagination: the parent owns page state and refetches. */
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  /** Server-side search. Called after the user pauses typing. Omit to hide the search box. */
  onSearchChange?: (q: string) => void;
  searchPlaceholder?: string;
  /** Extra filter controls (selects, date pickers) rendered next to the search box. */
  filters?: ReactNode;
  actions?: ReactNode;
  isLoading?: boolean;
  isFetching?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  total,
  page,
  pageSize,
  onPageChange,
  onSearchChange,
  searchPlaceholder = "Search",
  filters,
  actions,
  isLoading,
  isFetching,
  error,
  onRetry,
  emptyTitle = "Nothing here yet",
  emptyHint,
}: DataTableProps<T>) {
  const [search, setSearch] = useState("");
  const debounced = useDebounce(search, 350);
  const lastSent = useRef("");

  useEffect(() => {
    if (debounced !== lastSent.current) {
      lastSent.current = debounced;
      onSearchChange?.(debounced.trim());
    }
  }, [debounced, onSearchChange]);

  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  const showSkeleton = isLoading && !rows;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {(onSearchChange || filters || actions) && (
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center">
          {onSearchChange && (
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="pl-9"
              />
            </div>
          )}
          {filters ? <div className="flex flex-wrap items-center gap-2">{filters}</div> : null}
          {actions ? <div className="flex items-center gap-2 sm:ml-auto">{actions}</div> : null}
        </div>
      )}

      <div className={cn("overflow-x-auto transition-opacity", isFetching && !isLoading && "opacity-60")}>
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead className="border-b border-border bg-slate-50 text-muted-foreground">
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={cn("px-4 py-3 font-semibold", c.align === "right" && "text-right", c.className)}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {showSkeleton &&
              Array.from({ length: Math.min(pageSize, 8) }).map((_, i) => (
                <tr key={i} className="border-b border-border/60 last:border-0">
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3.5">
                      <Skeleton className="h-4 w-full max-w-[10rem]" />
                    </td>
                  ))}
                </tr>
              ))}
            {!showSkeleton &&
              rows?.map((row) => (
                <tr key={rowKey(row)} className="border-b border-border/60 last:border-0 odd:bg-card even:bg-slate-50/70">
                  {columns.map((c) => (
                    <td key={c.key} className={cn("px-4 py-3", c.align === "right" && "text-right", c.className)}>
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>

        {error && (
          <div className="flex flex-col items-center gap-3 px-4 py-12 text-center" role="alert">
            <AlertCircle className="h-8 w-8 text-danger" aria-hidden />
            <div>
              <p className="font-semibold">We couldn't load this list</p>
              <p className="text-sm text-muted-foreground">{error.message}</p>
            </div>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry}>
                Try again
              </Button>
            )}
          </div>
        )}

        {!error && !isLoading && rows && rows.length === 0 && (
          <div className="px-4 py-12 text-center">
            <p className="font-semibold">{emptyTitle}</p>
            {emptyHint ? <p className="mt-1 text-sm text-muted-foreground">{emptyHint}</p> : null}
          </div>
        )}
      </div>

      <div className="flex flex-col items-center justify-between gap-3 border-t border-border px-4 py-3 text-sm sm:flex-row">
        <p className="text-muted-foreground" aria-live="polite">
          {total === 0 ? "No results" : `Showing ${from}-${to} of ${total}`}
        </p>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => onPageChange(page - 1)} disabled={page <= 1}>
            <ChevronLeft className="h-4 w-4" aria-hidden />
            Previous
          </Button>
          <span className="min-w-20 text-center tabular-nums text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button variant="outline" size="sm" onClick={() => onPageChange(page + 1)} disabled={page >= pages}>
            Next
            <ChevronRight className="h-4 w-4" aria-hidden />
          </Button>
        </div>
      </div>
    </div>
  );
}
