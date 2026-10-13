/** Decimals arrive from the API as strings ("89.47"). */
export function num(v: string | number | null | undefined): number {
  const n = typeof v === "number" ? v : Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export const fmtPct = (v: string | number | null | undefined) => `${num(v).toFixed(2)}%`;
export const fmtMarks = (v: string | number | null | undefined) => String(Number(num(v).toFixed(2)));

/** Today's date (YYYY-MM-DD) in the school's timezone. The server stays the authority; this only seeds inputs. */
export function todayIn(timeZone = "Asia/Karachi"): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export const monthOf = (date: string) => date.slice(0, 7);

export function shiftMonth(month: string, delta: number): string {
  const [y = 0, m = 1] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function monthLabel(month: string): string {
  const [y = 0, m = 1] = month.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, 1)));
}

export function dateLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${iso}T00:00:00Z`));
}

export const WEEKDAYS = [
  { iso: 1, label: "Mon" }, { iso: 2, label: "Tue" }, { iso: 3, label: "Wed" }, { iso: 4, label: "Thu" },
  { iso: 5, label: "Fri" }, { iso: 6, label: "Sat" }, { iso: 7, label: "Sun" },
];

export const fmtMoney = (v: string | number | null | undefined) => num(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

/** "Whole school" or "Class 1 A" for an announcement target. */
export const targetLabel = (a: { class_name: string | null; section_name: string | null }) =>
  a.class_name ? `${a.class_name}${a.section_name ? ` ${a.section_name}` : ""}` : "Whole school";
