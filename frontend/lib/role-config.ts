import {
  Banknote,
  BookOpen,
  CalendarCheck,
  CalendarDays,
  CalendarClock,
  ClipboardList,
  FileText,
  GraduationCap,
  LayoutDashboard,
  LineChart,
  NotebookPen,
  Megaphone,
  PenLine,
  Receipt,
  School,
  Settings,
  UserCog,
  UserRound,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import type { Role } from "./types";

export const ROLES: readonly Role[] = ["ceo", "admin", "headmaster", "teacher", "student", "parent"] as const;

// Mirror SCHOOL_WIDE / MANAGERS in backend/app/core/permissions.py. UX only; the API enforces.
/** Sees the whole school (no class/child scoping). */
export const isSchoolWide = (role?: Role | null) => role === "admin" || role === "ceo" || role === "headmaster";
/** Can change settings, attendance, exams/results, fees and salary. */
export const isManager = (role?: Role | null) => role === "admin" || role === "headmaster";

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
      { label: "Finance reports", path: "fees", icon: LineChart },
      { label: "Teachers", path: "teachers", icon: UserCog },
      { label: "Students", path: "students", icon: GraduationCap },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "Tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "Results", path: "results", icon: FileText },
      { label: "Announcements", path: "announcements", icon: Megaphone },
    ],
  },
  admin: {
    label: "Admin",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Students", path: "students", icon: GraduationCap },
      { label: "Teachers", path: "teachers", icon: UserCog },
      { label: "Fees", path: "fees", icon: Receipt },
      { label: "Salary", path: "salary", icon: Banknote },
      { label: "Results", path: "results", icon: FileText },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "Tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "Announcements", path: "announcements", icon: Megaphone },
      { label: "Users", path: "users", icon: Users },
      { label: "Settings", path: "settings", icon: Settings },
    ],
  },
  headmaster: {
    label: "Headmaster",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Students", path: "students", icon: GraduationCap },
      { label: "Teachers", path: "teachers", icon: UserCog },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "Tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "Results", path: "results", icon: FileText },
      { label: "Fees", path: "fees", icon: Receipt },
      { label: "Salary", path: "salary", icon: Banknote },
      { label: "Users", path: "users", icon: Users },
      { label: "Settings", path: "settings", icon: Settings },
      { label: "Announcements", path: "announcements", icon: Megaphone },
    ],
  },
  teacher: {
    label: "Teacher",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "My classes", path: "classes", icon: School },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "Marks entry", path: "marks", icon: PenLine },
      { label: "Tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "My salary", path: "salary", icon: Wallet },
      { label: "Announcements", path: "announcements", icon: Megaphone },
    ],
  },
  student: {
    label: "Student",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Profile", path: "profile", icon: UserRound },
      { label: "My results", path: "results", icon: FileText },
      { label: "Fees", path: "fees", icon: Receipt },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "My tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "Announcements", path: "announcements", icon: Megaphone },
    ],
  },
  parent: {
    label: "Parent",
    nav: [
      { label: "Dashboard", path: "", icon: LayoutDashboard },
      { label: "Profile", path: "profile", icon: UserRound },
      { label: "Results", path: "results", icon: FileText },
      { label: "Fees", path: "fees", icon: Receipt },
      { label: "Attendance", path: "attendance", icon: CalendarCheck },
      { label: "Timetable", path: "timetable", icon: CalendarClock },
      { label: "Diary", path: "diary", icon: NotebookPen },
      { label: "Calendar", path: "calendar", icon: CalendarDays },
      { label: "Tests", path: "tests", icon: ClipboardList },
      { label: "Materials", path: "materials", icon: BookOpen },
      { label: "Announcements", path: "announcements", icon: Megaphone },
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
