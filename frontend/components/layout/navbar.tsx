"use client";

import { ChevronDown, KeyRound, LogOut, Menu } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { NotificationBell } from "@/components/notifications/bell";
import { ROLE_CONFIG } from "@/lib/role-config";
import type { User } from "@/lib/types";
import { initials } from "@/lib/utils";

interface NavbarProps {
  user: User;
  title: string;
  onOpenMenu: () => void;
  onSignOut: () => void;
}

export function Navbar({ user, title, onOpenMenu, onSignOut }: NavbarProps) {
  const displayName = user.full_name || user.username;
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border bg-card px-4 sm:px-6">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onOpenMenu} aria-label="Open menu">
        <Menu className="h-5 w-5" />
      </Button>
      <h2 className="min-w-0 flex-1 truncate text-lg font-semibold">{title}</h2>

      <NotificationBell role={user.role} />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-md py-1 pl-1 pr-2 hover:bg-muted"
            aria-label="Account menu"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
              {initials(displayName, user.username)}
            </span>
            <span className="hidden text-left sm:block">
              <span className="block max-w-40 truncate text-sm font-semibold leading-tight">{displayName}</span>
              <span className="block text-xs leading-tight text-muted-foreground">{ROLE_CONFIG[user.role].label}</span>
            </span>
            <ChevronDown className="hidden h-4 w-4 text-muted-foreground sm:block" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>
            <p className="truncate text-sm font-semibold">{displayName}</p>
            <p className="truncate text-xs text-muted-foreground">@{user.username}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/change-password">
              <KeyRound className="h-4 w-4" aria-hidden />
              Change password
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onSignOut}>
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
