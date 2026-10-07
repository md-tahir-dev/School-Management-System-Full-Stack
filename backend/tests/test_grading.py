"""Pure unit tests for app/services/grading.py (Part C3)."""

import uuid
from decimal import Decimal

import pytest

from app.services.grading import (
    SubjectMark,
    grade_for,
    is_complete,
    is_overall_pass,
    percentage,
    round2,
    subject_status,
    summarize,
)


def mark(obtained, total=100, passing=40, absent=False):
    return SubjectMark(uuid.uuid4(), Decimal(total), Decimal(passing), Decimal(obtained), absent)


@pytest.mark.parametrize(
    "raw,rounded,grade",
    [
        ("89.995", "90.00", "A+"),  # rounds up across the boundary; grade uses the ROUNDED value
        ("49.995", "50.00", "D"),
        ("49.994", "49.99", "F"),
        ("90", "90.00", "A+"),
        ("80", "80.00", "A"),
        ("70", "70.00", "B"),
        ("60", "60.00", "C"),
        ("50", "50.00", "D"),
        ("0", "0.00", "F"),
    ],
)
def test_grade_boundaries(raw, rounded, grade):
    assert str(round2(Decimal(raw))) == rounded
    assert grade_for(Decimal(raw)) == grade


def test_subject_status_pass_fail_absent():
    assert subject_status(mark(40)) == "Pass"
    assert subject_status(mark(39)) == "Fail"
    assert subject_status(mark(0, absent=True)) == "AB"


def test_fail_rule_changes_overall_result_for_same_marks():
    marks = [mark(95), mark(30)]  # 62.5% overall but one failed subject
    pct = percentage(marks)
    assert pct == Decimal("62.50")
    assert is_overall_pass(marks, pct, fail_if_any_subject_failed=True) is False
    assert is_overall_pass(marks, pct, fail_if_any_subject_failed=False) is True


def test_percentage_below_50_always_fails():
    marks = [mark(45, passing=10), mark(45, passing=10)]
    assert is_overall_pass(marks, percentage(marks), fail_if_any_subject_failed=False) is False


def test_absent_counts_as_zero_and_failure():
    s = summarize([mark(80), mark(0, absent=True)], fail_if_any_subject_failed=True)
    assert s.percentage == Decimal("40.00") and s.is_pass is False
    assert "AB" in s.subject_statuses.values()


def test_complete_only_when_every_subject_entered():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert is_complete({a}, {a, b}) is False
    assert is_complete({a, b}, {a, b}) is True
    assert is_complete(set(), set()) is False
