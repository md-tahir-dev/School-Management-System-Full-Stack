"use client";

import { ExamsList } from "@/components/results/exams-list";
import { OwnResults } from "@/components/results/own-results";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";

export default function ResultsPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "teacher") return <AccessDenied />;
  return <PageBoundary>{user.role === "admin" || user.role === "ceo" ? <ExamsList /> : <OwnResults />}</PageBoundary>;
}
