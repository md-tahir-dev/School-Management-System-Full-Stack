from datetime import date
from decimal import Decimal

import pytest

from app.services.fees import academic_year_months, due_date_for, ledger_amounts
from app.utils.money import discount_amount, money
from app.utils.validators import (
    normalize_phone,
    student_dob,
    teacher_dob,
    validate_blood_group,
    validate_cnic,
    validate_dob,
)


@pytest.mark.parametrize("value", ["35202-1234567-1", "00000-0000000-0"])
def test_cnic_valid(value):
    assert validate_cnic(value) == value


@pytest.mark.parametrize(
    "value", ["3520212345671", "35202-123456-1", "35202-12345678-1", "3520-1234567-1", "abcde-1234567-1", "", " "]
)
def test_cnic_invalid(value):
    with pytest.raises(ValueError):
        validate_cnic(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("03001234567", "0300-1234567"), ("0300-1234567", "0300-1234567"), ("  03451234567 ", "0345-1234567")],
)
def test_phone_is_normalized(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "value", ["0200-1234567", "030012345", "0300-12345678", "+923001234567", "0300 1234567", "03001234A67", ""]
)
def test_phone_invalid(value):
    with pytest.raises(ValueError):
        normalize_phone(value)


def test_blood_group():
    assert validate_blood_group("ab+") == "AB+"
    for good in ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"):
        assert validate_blood_group(good) == good
    for bad in ("C+", "A", "O", "AB", ""):
        with pytest.raises(ValueError):
            validate_blood_group(bad)


TODAY = date(2026, 9, 21)


def test_dob_must_be_in_the_past():
    with pytest.raises(ValueError, match="past"):
        validate_dob(TODAY, today=TODAY)
    with pytest.raises(ValueError, match="past"):
        validate_dob(date(2030, 1, 1), today=TODAY)
    assert validate_dob(date(2000, 1, 1), today=TODAY)


@pytest.mark.parametrize(
    ("dob", "ok"),
    [
        (date(2023, 9, 21), True),  # turns exactly 3 today
        (date(2023, 9, 22), False),  # turns 3 tomorrow
        (date(2001, 9, 21), True),  # exactly 25
        (date(2000, 9, 21), False),  # 26
    ],
)
def test_student_age_edges(dob, ok, monkeypatch):
    from app.utils import validators

    class FakeDate(date):
        @classmethod
        def today(cls):
            return TODAY

    monkeypatch.setattr(validators, "date", FakeDate)
    if ok:
        assert student_dob(dob) == dob
    else:
        with pytest.raises(ValueError):
            student_dob(dob)


def test_teacher_age_range():
    assert teacher_dob(date(1990, 1, 1))
    with pytest.raises(ValueError):
        teacher_dob(date(2015, 1, 1))


# ------------------------------------------------------------------- money
def test_money_rounds_half_up_and_never_uses_floats():
    assert money("10.005") == Decimal("10.01")
    assert money(Decimal("2.675")) == Decimal("2.68")
    assert discount_amount(Decimal("2000"), Decimal("50")) == Decimal("1000.00")
    assert discount_amount(Decimal("1000"), Decimal("33.33")) == Decimal("333.30")
    assert discount_amount(Decimal("999"), Decimal("12.5")) == Decimal("124.88")  # 124.875 rounds up


def test_ledger_amounts():
    assert ledger_amounts(Decimal("2000"), Decimal("50")) == (Decimal("1000.00"), Decimal("1000.00"))
    assert ledger_amounts(Decimal("2000"), Decimal("0")) == (Decimal("0.00"), Decimal("2000.00"))
    assert ledger_amounts(Decimal("2000"), Decimal("100")) == (Decimal("2000.00"), Decimal("0.00"))
    # an already-applied fine stays in the total
    assert ledger_amounts(Decimal("2000"), Decimal("10"), Decimal("200")) == (Decimal("200.00"), Decimal("2000.00"))


def test_academic_year_months_span_twelve_months_across_new_year():
    months = academic_year_months(date(2026, 4, 1))
    assert len(months) == 12
    assert months[0] == date(2026, 4, 1) and months[8] == date(2026, 12, 1)
    assert months[9] == date(2027, 1, 1) and months[-1] == date(2027, 3, 1)
    assert all(m.day == 1 for m in months)


def test_due_date_uses_fee_due_day_of_each_month():
    assert due_date_for(date(2027, 2, 1), 28) == date(2027, 2, 28)
    assert due_date_for(date(2026, 4, 1), 10) == date(2026, 4, 10)
