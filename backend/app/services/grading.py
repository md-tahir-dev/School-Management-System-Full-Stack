"""Pure grading/result-calculation functions (Part C3 of the Phase 3 spec).

No I/O and no SQLAlchemy here on purpose: these are unit tested directly, and the frontend's
"by student" live-entry view is expected to mirror this logic exactly, so keeping it side-effect-free
and dependency-free makes it easy to port or keep in lockstep.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class SubjectMark:
    subject_id: object  # uuid.UUID, kept generic so this module has zero framework imports
    total_marks: Decimal
    passing_marks: Decimal
    obtained_marks: Decimal
    is_absent: bool = False


def round2(value: Decimal) -> Decimal:
    """Half-up to 2 decimal places. Never use float rounding on marks/percentages."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def subject_is_pass(mark: SubjectMark) -> bool:
    """Pass if obtained >= passing and not absent. An absent subject is never a pass."""
    if mark.is_absent:
        return False
    return mark.obtained_marks >= mark.passing_marks


def subject_status(mark: SubjectMark) -> str:
    """'AB' for absent, else 'Pass' / 'Fail'."""
    if mark.is_absent:
        return "AB"
    return "Pass" if subject_is_pass(mark) else "Fail"


def total_obtained(marks: list[SubjectMark]) -> Decimal:
    return sum((m.obtained_marks for m in marks), Decimal(0))


def total_possible(marks: list[SubjectMark]) -> Decimal:
    return sum((m.total_marks for m in marks), Decimal(0))


def percentage(marks: list[SubjectMark]) -> Decimal:
    """obtained / possible * 100, rounded half-up to 2dp. 0 if there is nothing to divide by."""
    possible = total_possible(marks)
    if possible == 0:
        return Decimal("0.00")
    return round2(total_obtained(marks) / possible * 100)


def grade_for(pct: Decimal) -> str:
    """Grade is derived from the ALREADY-ROUNDED percentage, so the displayed grade always matches the
    displayed percentage (89.994 rounds to 89.99 -> F is never possible for a rounded 90.00, etc.)."""
    pct = round2(pct)
    if pct >= 90:
        return "A+"
    if pct >= 80:
        return "A"
    if pct >= 70:
        return "B"
    if pct >= 60:
        return "C"
    if pct >= 50:
        return "D"
    return "F"


def is_overall_pass(marks: list[SubjectMark], pct: Decimal, *, fail_if_any_subject_failed: bool) -> bool:
    """percentage >= 50 AND, if the school rule is on, no failed (or absent) subject."""
    if pct < 50:
        return False
    if fail_if_any_subject_failed and any(not subject_is_pass(m) for m in marks):
        return False
    return True


def is_complete(entered_subject_ids: set, required_subject_ids: set) -> bool:
    """A result is 'complete' only once every exam_subjects row has a matching result_items row."""
    return required_subject_ids.issubset(entered_subject_ids) and bool(required_subject_ids)


@dataclass(frozen=True)
class ResultSummary:
    total_obtained: Decimal
    total_possible: Decimal
    percentage: Decimal
    grade: str
    is_pass: bool
    subject_statuses: dict  # subject_id -> "Pass" | "Fail" | "AB"


def summarize(marks: list[SubjectMark], *, fail_if_any_subject_failed: bool) -> ResultSummary:
    pct = percentage(marks)
    return ResultSummary(
        total_obtained=round2(total_obtained(marks)),
        total_possible=round2(total_possible(marks)),
        percentage=pct,
        grade=grade_for(pct),
        is_pass=is_overall_pass(marks, pct, fail_if_any_subject_failed=fail_if_any_subject_failed),
        subject_statuses={m.subject_id: subject_status(m) for m in marks},
    )
