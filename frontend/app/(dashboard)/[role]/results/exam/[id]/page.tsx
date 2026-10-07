"use client";

import { ExamDetail } from "@/components/results/exam-detail";
import { AccessDenied, PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";

export default function ExamPage({ params }: { params: { id: string } }) {
  const { user } = useAuth();
  if (!user) return null;
  if (user.role !== "admin" && user.role !== "ceo") return <AccessDenied />;
  return <PageBoundary><ExamDetail examId={params.id} /></PageBoundary>;
}
