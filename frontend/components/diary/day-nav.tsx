"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { todayIn } from "@/lib/format";
import { shiftDay } from "./common";

export function DayNav({ date, onChange }: { date: string; onChange: (d: string) => void }) {
  return (
    <div className="flex items-center gap-1">
      <Button variant="outline" size="icon" aria-label="Previous day" onClick={() => onChange(shiftDay(date, -1))}><ChevronLeft className="h-4 w-4" /></Button>
      <Input type="date" aria-label="Date" value={date} onChange={(e) => e.target.value && onChange(e.target.value)} className="w-auto" />
      <Button variant="outline" size="icon" aria-label="Next day" onClick={() => onChange(shiftDay(date, 1))}><ChevronRight className="h-4 w-4" /></Button>
      <Button variant="outline" onClick={() => onChange(todayIn())}>Today</Button>
    </div>
  );
}
