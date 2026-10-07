"use client";

import { AlertCircle } from "lucide-react";
import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ErrorState({ error, onRetry, title = "We couldn't load this" }: { error: Error | null; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card px-4 py-12 text-center">
      <AlertCircle className="h-8 w-8 text-danger" aria-hidden />
      <div>
        <p className="font-semibold">{title}</p>
        {error ? <p className="text-sm text-muted-foreground">{error.message}</p> : null}
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-card px-4 py-12 text-center">
      <p className="font-semibold">{title}</p>
      {hint ? <p className="mt-1 text-sm text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

export function AccessDenied() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-xl font-bold">You don't have access to this page</h1>
      <p className="mt-1 text-sm text-muted-foreground">Ask the school administrator if you think this is a mistake.</p>
    </div>
  );
}

/** Page-level error boundary so one broken widget never blanks the whole portal. */
export class PageBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) return <ErrorState error={this.state.error} title="Something went wrong on this page" onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
