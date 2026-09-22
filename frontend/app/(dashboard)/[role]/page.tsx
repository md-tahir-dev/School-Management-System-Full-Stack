"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, GraduationCap, ShieldCheck, Users, UserCog } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { navHref, ROLE_CONFIG } from "@/lib/role-config";
import type { Page, User } from "@/lib/types";
import { greeting } from "@/lib/utils";

function useAccountCount(role?: string) {
  return useQuery({
    queryKey: ["users-count", role ?? "all"],
    queryFn: () => api<Page<User>>("/users", { query: { page_size: 1, role, is_active: true } }),
    select: (page) => page.total,
  });
}

function AccountStats() {
  const all = useAccountCount();
  const teachers = useAccountCount("teacher");
  const students = useAccountCount("student");
  return (
    <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard label="Active accounts" value={all.data} icon={Users} loading={all.isLoading} />
      <StatCard label="Teacher accounts" value={teachers.data} icon={UserCog} tone="success" loading={teachers.isLoading} />
      <StatCard label="Student accounts" value={students.data} icon={GraduationCap} tone="warning" loading={students.isLoading} />
    </div>
  );
}

export default function DashboardHome() {
  const { user } = useAuth();
  if (!user) return null;
  const canSeeAccounts = user.role === "admin" || user.role === "ceo";
  const nav = ROLE_CONFIG[user.role].nav.filter((n) => n.path !== "");
  const firstName = (user.full_name || user.username).split(" ")[0];

  return (
    <>
      <PageHeader
        title={`${greeting()}, ${firstName}`}
        description="Live figures and shortcuts for your area appear here as each part of the system comes online."
      />
      {canSeeAccounts && <AccountStats />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden />
            Your workspace
          </CardTitle>
          <CardDescription>What you'll find in the {ROLE_CONFIG[user.role].label.toLowerCase()} portal.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-border">
            {nav.map((item) => {
              const Icon = item.icon;
              const ready = item.phase === undefined;
              return (
                <li key={item.path} className="flex items-center gap-3 py-3">
                  <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
                  {ready ? (
                    <Link href={navHref(user.role, item)} className="font-medium text-primary hover:underline">
                      {item.label}
                    </Link>
                  ) : (
                    <span className="font-medium">{item.label}</span>
                  )}
                  <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    {ready ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden /> Available
                      </>
                    ) : (
                      <>
                        <Clock className="h-3.5 w-3.5" aria-hidden /> Coming in phase {item.phase}
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </>
  );
}
