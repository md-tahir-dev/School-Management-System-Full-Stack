import {
  Banknote,
  BookOpen,
  CalendarCheck,
  ClipboardList,
  FileText,
  GraduationCap,
  LayoutDashboard,
  LineChart,
  Megaphone,
  PenLine,
  Receipt,
  School,
  Settings,
  UserCog,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import type { Role } from "./types";

export const ROLES: readonly Role[] = ["ceo", "admin", "teacher", "student", "parent"] as const;

export function isRole(value: string | undefined | null): value is Role {
  return !!value && (ROLES as readonly string[]).includes(value);
}

export interface NavItem {
  label: string;
  /** Path below `/{role}`; "" is the dashboard. */
  path: string;
  icon: LucideIcon;
  /** Build phase that delivers the page. Omitted = available now. */
  phase?: number;
}

interface RoleConfig {
  label: string;
  nav: NavItem[];
}

// ONE source of truth for every role's sidebar. Backend permissions live in app/core/permissions.py.
export const ROLE_CONFIG: Record<Role, RoleConfig> = {
  ceo: {
    label: "CEO",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Finance reports", path: "finance", icon: LineChart, phase: 4 },
      { label: "Staff", path: "staff", icon: UserCog, phase: 2 },
      { label: "Students", path: "students", icon: GraduationCap, phase: 2 },
      { label: "Attendance", path: "attendance", icon: CalendarCheck, phase: 3 },
      { label: "Results", path: "results", icon: FileText, phase: 3 },
    ],
  },
  admin: {
    label: "Admin",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Students", path: "students", icon: GraduationCap, phase: 2 },
      { label: "Teachers", path: "teachers", icon: UserCog, phase: 2 },
      { label: "Fees", path: "fees", icon: Receipt, phase: 4 },
      { label: "Salary", path: "salary", icon: Banknote, phase: 4 },
      { label: "Results", path: "results", icon: FileText, phase: 3 },
      { label: "Attendance", path: "attendance", icon: CalendarCheck, phase: 3 },
      { label: "Announcements", path: "announcements", icon: Megaphone, phase: 6 },
      { label: "Users", path: "users", icon: Users },
      { label: "Settings", path: "settings", icon: Settings, phase: 2 },
    ],
  },
  teacher: {
    label: "Teacher",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "My classes", path: "classes", icon: School, phase: 2 },
      { label: "Attendance", path: "attendance", icon: CalendarCheck, phase: 3 },
      { label: "Marks entry", path: "marks", icon: PenLine, phase: 3 },
      { label: "Tests", path: "tests", icon: ClipboardList, phase: 5 },
      { label: "Materials", path: "materials", icon: BookOpen, phase: 5 },
      { label: "My salary", path: "salary", icon: Wallet, phase: 4 },
    ],
  },
  student: {
    label: "Student",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "My results", path: "results", icon: FileText, phase: 3 },
      { label: "Fees", path: "fees", icon: Receipt, phase: 4 },
      { label: "Attendance", path: "attendance", icon: CalendarCheck, phase: 3 },
      { label: "My tests", path: "tests", icon: ClipboardList, phase: 5 },
      { label: "Materials", path: "materials", icon: BookOpen, phase: 5 },
    ],
  },
  parent: {
    label: "Parent",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Results", path: "results", icon: FileText, phase: 3 },
      { label: "Fees", path: "fees", icon: Receipt, phase: 4 },
      { label: "Attendance", path: "attendance", icon: CalendarCheck, phase: 3 },
      { label: "Materials", path: "materials", icon: BookOpen, phase: 5 },
      { label: "Announcements", path: "announcements", icon: Megaphone, phase: 6 },
    ],
  },
};

export function navHref(role: Role, item: NavItem) {
  return item.path ? `/${role}/${item.path}` : `/${role}`;
}

/** Finds the nav item for a pathname like /admin/users (used for the navbar title). */
export function findNavItem(role: Role, pathname: string): NavItem | undefined {
  const [, , first] = pathname.split("/");
  return ROLE_CONFIG[role].nav.find((n) => n.path === (first ?? ""));
}
