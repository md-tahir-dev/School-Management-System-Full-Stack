"use client";

import { ExamDetail } from "@/components/results/exam-detail";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isSchoolWide } from "@/lib/role-config";

export default function ExamPage({ params }: { params: { id: string } }) {
  const { user } = useAuth();
  if (!user) return null;
  if (!isSchoolWide(user.role)) return <AccessDenied />;
  return <PageBoundary><ExamDetail examId={params.id} /></PageBoundary>;
}
