"use client";

import { MonthCalendar } from "@/components/calendar/month";
import { PageHeader } from "@/components/page-header";
import { PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isManager } from "@/lib/role-config";

export default function CalendarPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <PageBoundary>
      <PageHeader title="Calendar" description="Holidays, exams and school events." />
      <MonthCalendar manager={isManager(user.role)} />
    </PageBoundary>
  );
}
