"use client";

import { MarksEntry } from "@/components/results/marks-entry";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";

export default function MarksPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role !== "teacher" && user.role !== "admin") return <AccessDenied />;
  return <PageBoundary><MarksEntry /></PageBoundary>;
}
