"use client";

import { useState } from "react";
import { FamilyDiary } from "@/components/diary/family-view";
import { StaffDiary } from "@/components/diary/staff-view";
import { PageHeader } from "@/components/page-header";
import { PageBoundary } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { todayIn } from "@/lib/format";

export default function DiaryPage() {
  const { user } = useAuth();
  const [date, setDate] = useState(() => todayIn());
  if (!user) return null;
  const family = user.role === "student" || user.role === "parent";
  return (
    <PageBoundary>
      <PageHeader title="Diary" description="Daily homework and class notes." />
      {family ? <FamilyDiary date={date} setDate={setDate} isParent={user.role === "parent"} /> : <StaffDiary role={user.role} date={date} setDate={setDate} />}
    </PageBoundary>
  );
}
