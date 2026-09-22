import { Hourglass } from "lucide-react";
import { notFound } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { isRole, ROLE_CONFIG } from "@/lib/role-config";

const PHASES: Record<number, string> = {
  2: "students, teachers, classes and settings",
  3: "attendance and results",
  4: "fees and salary",
  5: "online tests and study materials",
  6: "dashboards, announcements and notifications",
};

/** Sidebar entries whose feature is built in a later phase land here instead of a 404. */
export default function ComingSoon({ params }: { params: { role: string; slug: string[] } }) {
  if (!isRole(params.role)) notFound();
  const item = ROLE_CONFIG[params.role].nav.find((n) => n.path === params.slug[0]);
  if (!item || item.phase === undefined) notFound();

  return (
    <>
      <PageHeader title={item.label} />
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-700">
          <Hourglass className="h-5 w-5" aria-hidden />
        </span>
        <h2 className="text-lg font-semibold">{item.label} isn't available yet</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          This section is built in phase {item.phase} of the rollout, together with {PHASES[item.phase] ?? "related features"}.
        </p>
      </Card>
    </>
  );
}
