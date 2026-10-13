"use client";

import { ExamsList } from "@/components/results/exams-list";
import { OwnResults } from "@/components/results/own-results";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";

export default function ResultsPage() {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role === "teacher") return <AccessDenied />;
  return <PageBoundary>{isSchoolWide(user.role) ? <ExamsList /> : <OwnResults />}</PageBoundary>;
}
