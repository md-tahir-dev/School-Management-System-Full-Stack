"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Navbar } from "@/components/layout/navbar";
import { Sidebar } from "@/components/layout/sidebar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { findNavItem } from "@/lib/role-config";
import type { PublicConfig, Role } from "@/lib/types";

function FullPageSkeleton() {
  return (
    <div className="min-h-screen bg-background" aria-busy="true" aria-label="Loading">
      <div className="fixed inset-y-0 left-0 hidden w-64 bg-sidebar lg:block" />
      <div className="lg:pl-64">
        <div className="h-16 border-b border-border bg-card" />
        <div className="space-y-4 p-6">
          <Skeleton className="h-8 w-56" />
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        </div>
      </div>
    </div>
  );
}

/** Client-side guard + chrome. The real enforcement is the API; this keeps people in their own area. */
export function DashboardShell({ role, children }: { role: Role; children: ReactNode }) {
  const { user, status, logout, retry } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  const { data: config } = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api<PublicConfig>("/public/config", { auth: false }),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (status === "authenticated" && user) {
      if (user.must_change_password) router.replace("/change-password");
      else if (user.role !== role) router.replace(`/${user.role}`);
    }
  }, [status, user, role, router, pathname]);

  if (status === "error") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <h1 className="text-xl font-bold">We can't reach the server</h1>
        <p className="max-w-sm text-sm text-muted-foreground">Check your connection and try again. You haven't been signed out.</p>
        <Button onClick={retry}>Try again</Button>
      </div>
    );
  }

  if (status !== "authenticated" || !user || user.role !== role || user.must_change_password) {
    return <FullPageSkeleton />;
  }

  const title = findNavItem(role, pathname)?.label ?? "Dashboard";
  const signOut = async () => {
    await logout();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <Sidebar
        role={role}
        schoolName={config?.school_name ?? "School"}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onSignOut={signOut}
      />
      <div className="lg:pl-64">
        <Navbar user={user} title={title} onOpenMenu={() => setMenuOpen(true)} onSignOut={signOut} />
        <main id="main" className="mx-auto max-w-7xl p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
