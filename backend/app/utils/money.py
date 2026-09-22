from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """Two decimal places, half-up (never floats)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def discount_amount(base_fee: Decimal, percent: Decimal) -> Decimal:
    return money(Decimal(base_fee) * Decimal(percent) / Decimal(100))
