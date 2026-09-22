import { notFound } from "next/navigation";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { isRole } from "@/lib/role-config";

export default function RoleLayout({ children, params }: { children: React.ReactNode; params: { role: string } }) {
  if (!isRole(params.role)) notFound();
  return <DashboardShell role={params.role}>{children}</DashboardShell>;
}
