import type { components } from "./api-types";

// Types come from FastAPI's OpenAPI schema (`npm run gen:api` regenerates lib/api-types.ts).
type Schemas = components["schemas"];

export type Role = Schemas["Role"];
export type User = Schemas["UserOut"];
export type TokenResponse = Schemas["TokenResponse"];
export type SchoolSettings = Schemas["SchoolSettingsOut"];
export type PublicConfig = Schemas["PublicConfig"];

/** Matches the backend `Page[T]` envelope used by every list endpoint. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ---- Phase 3 (attendance & results): all derived from the generated OpenAPI types ----------------
export type ClassOut = Schemas["ClassOut"];
export type SectionOut = Schemas["SectionOut"];
export type AcademicYear = Schemas["AcademicYearOut"];
export type Roster = Schemas["RosterOut"];
export type RosterStudent = Schemas["RosterStudent"];
export type BulkResult = Schemas["BulkAttendanceResult"];
export type AttendanceSummary = Schemas["AttendanceSummary"];
export type CalendarOut = Schemas["CalendarOut"];
export type ClassAttendanceReport = Schemas["ClassAttendanceReport"];
export type OverviewOut = Schemas["OverviewOut"];
export type LowAttendanceOut = Schemas["LowAttendanceOut"];
export type Holiday = Schemas["HolidayOut"];
export type TeacherRoster = Schemas["TeacherRosterOut"];
export type TeacherDetail = Schemas["TeacherDetail"];
export type Exam = Schemas["ExamOut"];
export type ExamSubject = Schemas["ExamSubjectOut"];
export type MarksSheet = Schemas["MarksSheetOut"];
export type StudentEntry = Schemas["StudentEntryOut"];
export type ResultOut = Schemas["ResultOut"];
export type ClassResultRow = Schemas["ClassResultRow"];
export type StudentResults = Schemas["StudentResultsOut"];
export type ExamAnalytics = Schemas["ExamAnalyticsOut"];
export type StudentListItem = Schemas["StudentListItem"];
export type StudentDetail = Schemas["StudentDetail"];
export type ChildSummary = Schemas["ChildSummary"];
export type ChildDashboard = Schemas["ChildDashboard"];
export type SubjectOut = Schemas["SubjectOut"];
export type ClassSubject = Schemas["ClassSubjectOut"];
export type FeeStructure = Schemas["FeeStructureOut"];
export type TeacherListItem = Schemas["TeacherListItem"];
export type TeacherCreated = Schemas["TeacherCreated"];
export type StudentCreated = Schemas["StudentCreated"];
export type GuardianLookup = Schemas["GuardianLookup"];
export type MetaOptions = Schemas["Options"];
export type AttendanceStatus = "present" | "absent" | "late" | "sick";
export type TeacherAttendanceStatus = "present" | "absent" | "late" | "leave";
export type ExamType = Exam["type"];

/** `/exams/{id}/marks-progress` is untyped in OpenAPI (plain list of dicts), so it is typed here. */
export interface MarksProgressRow {
  subject_id: string;
  subject_name: string;
  section_id: string | null;
  section_name: string | null;
  entered: number;
  total: number;
}
export interface LatestResultCard {
  exam_name: string;
  percentage: number;
  grade: string;
  rank: number | null;
  total_students: number | null;
  is_pass: boolean;
}
export interface AttendanceCardData {
  month_percentage: number;
  present: number;
  absent: number;
  late: number;
  sick: number;
  below_threshold: boolean;
}
export interface CeoDashboard {
  today_attendance_percent: number;
  unmarked_sections: number;
  class_pass_rates: { class_name: string; exam_name: string; pass_percent: number }[];
}
export type FeeMonthSummary = Schemas["FeeMonthSummary"];
export type LedgerOut = Schemas["LedgerOut"];
export type LedgerRow = Schemas["LedgerRow"];
export type PaymentIn = Schemas["PaymentIn"];
export type Payment = Schemas["PaymentOut"];
export type Defaulter = Schemas["DefaulterOut"];
export type FeeSummary = Schemas["FeeSummaryOut"];
export type ClassCollection = Schemas["ClassCollection"];
export type SalaryRecord = Schemas["SalaryRecordOut"];
export type SalaryGenerateResult = Schemas["GenerateOut"];
export type SalaryAdvance = Schemas["AdvanceOut"];

// ---- Timetable ----
export type Period = Schemas["PeriodOut"];
export type PeriodIn = Schemas["PeriodIn"];
export type CellIn = Schemas["CellIn"];
export type TimetableEntry = Schemas["EntryOut"];
export type Timetable = Schemas["TimetableOut"];
export type ClassTeacher = Schemas["ClassTeacherOut"];
export type ClassTeacherIn = Schemas["ClassTeacherIn"];

// ---- Diary & materials ----
export type DiaryEntry = Schemas["DiaryOut"];
export type DiaryIn = Schemas["DiaryIn"];
export type Submission = Schemas["SubmissionOut"];
export type SubmissionRow = Schemas["SubmissionRow"];
export type Material = Schemas["MaterialOut"];
export type MaterialType = Schemas["MaterialType"];

// ---- Announcements, calendar, notifications ----
export type Announcement = Schemas["AnnouncementOut"];
export type AnnouncementIn = Schemas["AnnouncementIn"];
export type EventOut = Schemas["EventOut"];
export type EventIn = Schemas["EventIn"];
export type CalendarItem = Schemas["CalendarItem"];
export type NotificationOut = Schemas["NotificationOut"];
export type Audience = Schemas["Audience"];
export type EventType = Schemas["EventType"];

// ---- Online tests ----
export type TestOut = Schemas["TestOut"];
export type TestIn = Schemas["TestIn"];
export type TestDetail = Schemas["TestDetailOut"];
export type MyTest = Schemas["MyTestOut"];
export type TestQuestion = Schemas["QuestionOut"];
export type QuestionIn = Schemas["QuestionIn"];
export type QuestionType = Schemas["QuestionType"];
export type AttemptView = Schemas["AttemptView"];
export type AttemptResult = Schemas["AttemptResult"];
export type AnswerResult = Schemas["AnswerResult"];
export type AttemptRow = Schemas["AttemptRow"];
