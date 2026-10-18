"use client";

import { useState } from "react";
import { PageHeader } from "@/components/page-header";
import { AcademicYears } from "@/components/settings/academic-years";
import { Classes } from "@/components/settings/classes";
import { Fees } from "@/components/settings/fees";
import { Holidays } from "@/components/settings/holidays";
import { Periods } from "@/components/settings/periods";
import { Rules } from "@/components/settings/rules";
import { SchoolProfile } from "@/components/settings/school-profile";
import { Subjects } from "@/components/settings/subjects";
import { Tabs } from "@/components/ui/tabs";
import { AccessDenied } from "@/components/ui/state-views";
import { useAuth } from "@/lib/auth";
import { isManager } from "@/lib/role-config";

const TABS = [
  { key: "profile", label: "School profile", Panel: SchoolProfile },
  { key: "years", label: "Academic years", Panel: AcademicYears },
  { key: "classes", label: "Classes & sections", Panel: Classes },
  { key: "subjects", label: "Subjects", Panel: Subjects },
  { key: "periods", label: "Periods", Panel: Periods },
  { key: "fees", label: "Fees", Panel: Fees },
  { key: "rules", label: "Attendance & results", Panel: Rules },
  { key: "holidays", label: "Holidays", Panel: Holidays },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export default function SettingsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<TabKey>("profile");
  if (user && !isManager(user.role)) return <AccessDenied />;
  const { Panel } = TABS.find((t) => t.key === tab)!;
  return (
    <>
      <PageHeader title="Settings" description="School profile and branding, academic structure, fees, and attendance rules." />
      <Tabs label="Settings sections" value={tab} onChange={setTab} tabs={TABS.map(({ key, label }) => ({ key, label }))} />
      <Panel />
    </>
  );
}
