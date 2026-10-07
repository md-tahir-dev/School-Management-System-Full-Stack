/**
 * Client mirror of backend/app/services/grading.py, used ONLY for the live preview in the
 * "By student" marks entry. The server remains the source of truth and recalculates on save.
 * Keep the two in lockstep (grade table, half-up rounding, overall-pass rule).
 */
export interface SubjectMark {
  total: number;
  passing: number;
  obtained: number;
  absent: boolean;
}

/** Half-up to 2dp. Works on integer hundredths to dodge binary float surprises (e.g. 1.005). */
export function round2(value: number): number {
  return Math.floor(value * 100 + 0.5 + 1e-9) / 100;
}

export function subjectStatus(m: SubjectMark): "Pass" | "Fail" | "AB" {
  if (m.absent) return "AB";
  return m.obtained >= m.passing ? "Pass" : "Fail";
}

export function gradeFor(pct: number): string {
  const p = round2(pct);
  if (p >= 90) return "A+";
  if (p >= 80) return "A";
  if (p >= 70) return "B";
  if (p >= 60) return "C";
  if (p >= 50) return "D";
  return "F";
}

export interface Summary {
  totalObtained: number;
  totalPossible: number;
  percentage: number;
  grade: string;
  isPass: boolean;
}

export function summarize(marks: SubjectMark[], failIfAnySubjectFailed: boolean): Summary {
  const totalObtained = marks.reduce((s, m) => s + (m.absent ? 0 : m.obtained), 0);
  const totalPossible = marks.reduce((s, m) => s + m.total, 0);
  const percentage = totalPossible === 0 ? 0 : round2((totalObtained / totalPossible) * 100);
  const anyFailed = marks.some((m) => subjectStatus(m) !== "Pass");
  const isPass = percentage >= 50 && !(failIfAnySubjectFailed && anyFailed);
  return { totalObtained: round2(totalObtained), totalPossible: round2(totalPossible), percentage, grade: gradeFor(percentage), isPass };
}
