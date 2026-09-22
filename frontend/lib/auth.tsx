"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  changePasswordRequest,
  loginRequest,
  logoutRequest,
  refreshSession,
  setSessionExpiredHandler,
} from "./api";
import type { User } from "./types";

type Status = "loading" | "authenticated" | "unauthenticated" | "error";

interface AuthContextValue {
  user: User | null;
  status: Status;
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<User>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [attempt, setAttempt] = useState(0);

  // Restore the session from the refresh cookie on every full page load.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    refreshSession()
      .then(async (session) => {
        if (cancelled) return;
        if (session) {
          setUser(session.user);
          setStatus("authenticated");
        } else {
          setUser(null);
          setStatus("unauthenticated");
          // Clear a stale role cookie so route gating doesn't think we're signed in.
          await logoutRequest().catch(() => undefined);
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("error"); // network/server problem: don't sign the user out
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // The API client calls this when a refresh fails mid-session.
  useEffect(() => {
    setSessionExpiredHandler(() => {
      setUser(null);
      setStatus("unauthenticated");
      queryClient.clear();
      void logoutRequest().catch(() => undefined);
    });
    return () => setSessionExpiredHandler(null);
  }, [queryClient]);

  const login = useCallback(async (username: string, password: string) => {
    const session = await loginRequest(username, password);
    setUser(session.user);
    setStatus("authenticated");
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setUser(null);
      setStatus("unauthenticated");
      queryClient.clear();
    }
  }, [queryClient]);

  const changePassword = useCallback(async (current: string, next: string) => {
    const session = await changePasswordRequest(current, next);
    setUser(session.user);
    return session.user;
  }, []);

  const value = useMemo(
    () => ({ user, status, login, logout, changePassword, retry: () => setAttempt((n) => n + 1) }),
    [user, status, login, logout, changePassword],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
