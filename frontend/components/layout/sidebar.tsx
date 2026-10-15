"use client";

import { LogOut, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { BrandMark } from "@/components/brand-mark";
import { cn } from "@/lib/utils";
import { navHref, ROLE_CONFIG } from "@/lib/role-config";
import type { Role } from "@/lib/types";

interface SidebarProps {
  role: Role;
  schoolName: string;
  logoUrl?: string | null;
  open: boolean;
  onClose: () => void;
  onSignOut: () => void;
}

function NavList({ role, onNavigate }: { role: Role; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
      {ROLE_CONFIG[role].nav.map((item) => {
        const href = navHref(role, item);
        const active = item.path === "" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
        const Icon = item.icon;
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md border-l-[3px] px-3 py-2.5 text-sm font-medium transition-colors",
              active
                ? "border-secondary bg-white/10 text-white"
                : "border-transparent text-sidebar-foreground/75 hover:bg-white/5 hover:text-white",
            )}
          >
            <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
            <span className="truncate">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarBody({ role, schoolName, logoUrl, onNavigate, onSignOut, onClose }: Omit<SidebarProps, "open"> & { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 shrink-0 items-center gap-3 border-b border-white/10 px-5">
        <BrandMark logoUrl={logoUrl} className="h-9 w-9 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-bold text-white">{schoolName}</p>
          <p className="text-xs text-sidebar-foreground/60">{ROLE_CONFIG[role].label} portal</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-10 w-10 items-center justify-center rounded-md text-sidebar-foreground/70 hover:bg-white/10 lg:hidden"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <NavList role={role} onNavigate={onNavigate} />
      <div className="border-t border-white/10 p-3">
        <button
          type="button"
          onClick={onSignOut}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium text-sidebar-foreground/75 hover:bg-white/5 hover:text-white"
        >
          <LogOut className="h-[18px] w-[18px]" aria-hidden />
          Sign out
        </button>
      </div>
    </div>
  );
}

export function Sidebar(props: SidebarProps) {
  const { open, onClose } = props;
  const pathname = usePathname();

  // close the drawer after navigating; lock body scroll while it's open
  useEffect(() => onClose(), [pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const drawer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    drawer.current?.querySelector<HTMLElement>("a,button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab" || !drawer.current) return;
      // keep Tab inside the drawer
      const f = drawer.current.querySelectorAll<HTMLElement>("a[href],button");
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">
        <SidebarBody {...props} />
      </aside>
      {open && (
        <div ref={drawer} className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 animate-fade-in bg-slate-900/50" onClick={onClose} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85%] animate-drawer-in">
            <SidebarBody {...props} onNavigate={onClose} />
          </aside>
        </div>
      )}
    </>
  );
}
