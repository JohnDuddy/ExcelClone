from __future__ import annotations

import math

import pytest

from duddysheet.core.errors import DIV_ZERO_ERROR, NUM_ERROR
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.workbook import Workbook


def evaluate(formula: str) -> object:
    return FormulaEvaluator(Workbook()).evaluate(formula)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=EFFECT(0.06,12)", (1 + 0.06 / 12) ** 12 - 1),
        ("=NOMINAL(EFFECT(0.06,12),12)", 0.06),
        ("=FVSCHEDULE(100,{0.05,0.04,0.03})", 100 * 1.05 * 1.04 * 1.03),
        ("=RRI(10,1000,2000)", 2 ** (1 / 10) - 1),
        ("=PDURATION(0.08,1000,2000)", math.log(2) / math.log(1.08)),
        ("=ISPMT(0.01,1,12,1000)", 1000 * 0.01 * (1 / 12 - 1)),
        ("=DOLLARDE(1.02,16)", 1.125),
        ("=DOLLARFR(1.125,16)", 1.02),
        ("=SYD(10000,1000,5,1)", 3000),
        ("=DDB(10000,1000,5,1)", 4000),
        (
            "=TBILLPRICE(DATE(2025,1,1),DATE(2025,7,1),0.05)",
            100 * (1 - 0.05 * 181 / 360),
        ),
    ],
)
def test_extended_financial_functions_match_known_values(
    formula: str,
    expected: float,
) -> None:
    assert evaluate(formula) == pytest.approx(expected)


def test_mirr_and_cumulative_loan_functions_are_internally_consistent() -> None:
    mirr_value = evaluate("=MIRR({-100,60,60},0.08,0.1)")
    cumulative_interest = evaluate("=CUMIPMT(0.01,12,1000,1,6,0)")
    cumulative_principal = evaluate("=CUMPRINC(0.01,12,1000,1,6,0)")
    six_payments = 6 * evaluate("=PMT(0.01,12,1000)")

    assert mirr_value == pytest.approx((60 * 1.1 + 60) ** 0.5 / 100**0.5 - 1)
    assert cumulative_interest + cumulative_principal == pytest.approx(six_payments)


def test_coupon_schedule_functions_share_one_consistent_schedule() -> None:
    base = "DATE(2025,2,15),DATE(2027,2,15),2"

    assert evaluate(f"=COUPNUM({base})") == 4
    assert evaluate(f"=COUPDAYBS({base})") == 0
    assert evaluate(f"=COUPDAYS({base})") == 180
    assert evaluate(f"=COUPDAYSNC({base})") == 180
    assert evaluate(f"=COUPPCD({base})") == evaluate("=DATE(2025,2,15)")
    assert evaluate(f"=COUPNCD({base})") == evaluate("=DATE(2025,8,15)")


def test_security_price_and_yield_round_trip() -> None:
    price_value = evaluate(
        "=PRICE(DATE(2025,3,15),DATE(2030,1,1),0.05,0.06,100,2,1)"
    )
    formula = (
        "=YIELD(DATE(2025,3,15),DATE(2030,1,1),"
        f"0.05,{price_value},100,2,1)"
    )

    assert evaluate(formula) == pytest.approx(0.06, abs=1e-8)


def test_security_duration_and_discount_functions_are_financially_ordered() -> None:
    duration = evaluate(
        "=DURATION(DATE(2025,1,1),DATE(2030,1,1),0.05,0.06,2)"
    )
    modified = evaluate(
        "=MDURATION(DATE(2025,1,1),DATE(2030,1,1),0.05,0.06,2)"
    )
    discount = evaluate("=DISC(DATE(2025,1,1),DATE(2025,7,1),97,100)")
    discounted_price = evaluate(
        f"=PRICEDISC(DATE(2025,1,1),DATE(2025,7,1),{discount},100)"
    )

    assert 0 < modified < duration < 5
    assert discounted_price == pytest.approx(97)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=EFFECT(0,12)", NUM_ERROR),
        ("=RRI(0,100,200)", NUM_ERROR),
        ("=PDURATION(0,100,200)", NUM_ERROR),
        ("=DOLLARDE(1.02,0)", DIV_ZERO_ERROR),
        ("=CUMIPMT(0,12,1000,1,6,0)", NUM_ERROR),
        ("=COUPNUM(DATE(2026,1,1),DATE(2025,1,1),2)", NUM_ERROR),
        ("=TBILLPRICE(DATE(2025,1,1),DATE(2026,2,1),0.05)", NUM_ERROR),
    ],
)
def test_extended_financial_functions_reject_invalid_domains(
    formula: str,
    expected: object,
) -> None:
    assert evaluate(formula) == expected


@pytest.mark.parametrize("basis", range(5))
def test_security_functions_support_every_documented_day_count_basis(
    basis: int,
) -> None:
    price = evaluate(
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),"
        f"0.045,0.052,100,2,{basis})"
    )
    duration = evaluate(
        "=DURATION(DATE(2025,3,17),DATE(2031,2,28),"
        f"0.045,0.052,2,{basis})"
    )

    assert isinstance(price, float)
    assert isinstance(duration, float)
    assert 0 < price < 200
    assert 0 < duration < 6


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=MIRR({1,2,3},0.1,0.1)", NUM_ERROR),
        ("=NOMINAL(0.05,0)", NUM_ERROR),
        ("=FVSCHEDULE(100,{0,-1,0.5})", 0),
        ("=CUMPRINC(0.01,12,1000,1,6,2)", NUM_ERROR),
        ("=DB(100,0,5,1)", 100),
        ("=DB(1000,100,5,7)", NUM_ERROR),
        ("=DDB(1000,100,0,1)", NUM_ERROR),
        ("=VDB(1000,100,5,2,1)", NUM_ERROR),
        ("=DOLLARFR(1.25,-16)", NUM_ERROR),
        ("=PRICE(DATE(2030,1,1),DATE(2025,1,1),0.05,0.06,100,2)", NUM_ERROR),
        ("=YIELD(DATE(2025,1,1),DATE(2030,1,1),0.05,-1,100,2)", NUM_ERROR),
        ("=RECEIVED(DATE(2025,1,1),DATE(2025,7,1),100,3)", NUM_ERROR),
        ("=PRICEDISC(DATE(2025,1,1),DATE(2025,7,1),3,100)", NUM_ERROR),
        ("=TBILLYIELD(DATE(2025,7,1),DATE(2025,1,1),97)", NUM_ERROR),
        ("=COUPNUM(DATE(2025,1,1),DATE(2030,1,1),3)", NUM_ERROR),
    ],
)
def test_additional_financial_domain_boundaries(
    formula: str,
    expected: object,
) -> None:
    assert evaluate(formula) == expected


def test_depreciation_switches_and_accrual_modes_are_calculated() -> None:
    switched = evaluate("=VDB(10000,1000,5,1.5,3.5,2,FALSE)")
    declining_only = evaluate("=VDB(10000,1000,5,1.5,3.5,2,TRUE)")
    from_issue = evaluate(
        "=ACCRINT(DATE(2025,1,1),DATE(2025,7,1),"
        "DATE(2026,1,1),0.06,1000,2,1,TRUE)"
    )
    from_first_coupon = evaluate(
        "=ACCRINT(DATE(2025,1,1),DATE(2025,7,1),"
        "DATE(2026,1,1),0.06,1000,2,1,FALSE)"
    )

    assert switched > 0
    assert declining_only > 0
    assert from_issue > from_first_coupon > 0


def test_actual_coupon_days_match_excel_for_month_end_schedule() -> None:
    next_coupon = evaluate(
        "=COUPNCD(DATE(2025,3,15),DATE(2030,2,28),2,1)"
    )

    assert next_coupon == evaluate("=DATE(2025,8,31)")
    assert evaluate(
        "=COUPDAYS(DATE(2025,3,17),DATE(2030,2,28),2,1)"
    ) == 181


@pytest.mark.parametrize(
    ("basis", "expected"),
    [
        (0, 96.452974461369),
        (1, 96.45249994057353),
        (2, 96.452974461369),
        (3, 96.45267541698135),
        (4, 96.45554711431258),
    ],
)
def test_price_matches_excel_for_every_day_count_basis(
    basis: int,
    expected: float,
) -> None:
    value = evaluate(
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),"
        f"0.045,0.052,100,2,{basis})"
    )

    assert value == pytest.approx(expected)


def test_vdb_matches_excel_for_fractional_switching_periods() -> None:
    value = evaluate("=VDB(100000,10000,7,1.5,4.25,1.5,FALSE)")

    assert value == pytest.approx(33981.8788302493)
