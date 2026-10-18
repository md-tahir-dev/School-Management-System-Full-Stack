"use client";

import { MarksEntry } from "@/components/results/marks-entry";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isManager } from "@/lib/role-config";

export default function MarksPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role !== "teacher" && !isManager(user.role)) return <AccessDenied />;
  return <PageBoundary><MarksEntry /></PageBoundary>;
}
