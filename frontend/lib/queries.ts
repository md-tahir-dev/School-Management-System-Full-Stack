"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { AcademicYear, ChildSummary, ClassOut, Page, SchoolSettings, SectionOut, TeacherDetail } from "./types";

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => api<SchoolSettings>("/settings"), staleTime: 5 * 60_000 });
}

export function useClasses() {
  return useQuery({
    queryKey: ["classes"],
    queryFn: () => api<Page<ClassOut>>("/classes", { query: { page_size: 100 } }),
    select: (p) => p.items,
    staleTime: 5 * 60_000,
  });
}

export function useSections(classId: string | undefined) {
  return useQuery({
    queryKey: ["sections", classId],
    queryFn: () => api<Page<SectionOut>>(`/classes/${classId}/sections`, { query: { page_size: 100 } }),
    select: (p) => p.items,
    enabled: !!classId,
    staleTime: 5 * 60_000,
  });
}

export function useAcademicYears(enabled = true) {
  return useQuery({
    queryKey: ["academic-years"],
    queryFn: () => api<Page<AcademicYear>>("/academic-years", { query: { page_size: 100 } }),
    select: (p) => p.items,
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useMyTeacher() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["teacher-me"],
    queryFn: () => api<TeacherDetail>("/teachers/me"),
    enabled: user?.role === "teacher",
    staleTime: 5 * 60_000,
  });
}

/**
 * Which student a Student/Parent is looking at. Students see themselves; parents get the child list
 * from /parent/children and a switcher (selection is remembered for the browser tab).
 */
export function useStudentScope() {
  const { user } = useAuth();
  const isParent = user?.role === "parent";
  const isStudent = user?.role === "student";

  const children = useQuery({
    queryKey: ["parent-children"],
    queryFn: () => api<Page<ChildSummary>>("/parent/children", { query: { page_size: 50 } }),
    select: (p) => p.items,
    enabled: isParent,
    placeholderData: keepPreviousData,
  });
  const own = useQuery({
    queryKey: ["student-dashboard"],
    queryFn: () => api<{ child: ChildSummary }>("/student/dashboard"),
    select: (d) => d.child,
    enabled: isStudent,
  });

  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    setPicked(sessionStorage.getItem("sms_child"));
  }, []);
  const select = useCallback((id: string) => {
    setPicked(id);
    sessionStorage.setItem("sms_child", id);
  }, []);

  if (isStudent) {
    return { studentId: own.data?.id, child: own.data, children: own.data ? [own.data] : [], select, isLoading: own.isLoading, error: own.error as Error | null, isParent };
  }
  const list = children.data ?? [];
  const child = list.find((c) => c.id === picked) ?? list[0];
  return { studentId: child?.id, child, children: list, select, isLoading: children.isLoading, error: children.error as Error | null, isParent };
}
