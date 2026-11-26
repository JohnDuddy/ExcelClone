"""Financial worksheet functions."""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime
from typing import Any, Callable

from dateutil.relativedelta import relativedelta

from duddysheet.core.errors import DIV_ZERO_ERROR, NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import (
    flatten,
    number,
    numeric_values,
    scalar,
    serial_datetime,
)


def _number(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


def _payment(rate: float, periods: float, present: float, future: float, due: float) -> Any:
    if periods == 0:
        return NUM_ERROR
    if rate == 0:
        return -(present + future) / periods
    factor = (1 + rate) ** periods
    denominator = (1 + rate * due) * (factor - 1)
    if denominator == 0:
        return DIV_ZERO_ERROR
    return -(rate * (future + present * factor)) / denominator


@register("PMT", min_args=3, max_args=5, argument_spec="rate, nper, pv, [fv], [type]")
def pmt(
    context: Any,
    rate: Any,
    periods: Any,
    present: Any,
    future: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the periodic payment for a fixed-rate annuity."""
    values = [_number(context, value) for value in (rate, periods, present, future, due)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    return _payment(*values)


def _balance_before_period(
    rate: float,
    period: int,
    payment: float,
    present: float,
    due: int,
) -> float:
    balance = present
    for current in range(1, period):
        if due:
            balance += payment
        balance += balance * rate
        if not due:
            balance += payment
    return balance


@register("IPMT", min_args=4, max_args=6, argument_spec="rate, per, nper, pv, [fv], [type]")
def ipmt(
    context: Any,
    rate: Any,
    period: Any,
    periods: Any,
    present: Any,
    future: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the interest portion of one annuity payment."""
    values = [_number(context, value) for value in (rate, period, periods, present, future, due)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, period_value, periods_value, present_value, future_value, due_value = values
    if period_value < 1 or period_value > periods_value:
        return NUM_ERROR
    payment = _payment(rate_value, periods_value, present_value, future_value, due_value)
    if is_error(payment):
        return payment
    if due_value and int(period_value) == 1:
        return 0
    balance = _balance_before_period(
        rate_value,
        int(period_value),
        payment,
        present_value,
        int(due_value),
    )
    if due_value:
        balance += payment
    return -balance * rate_value


@register("PPMT", min_args=4, max_args=6, argument_spec="rate, per, nper, pv, [fv], [type]")
def ppmt(
    context: Any,
    rate: Any,
    period: Any,
    periods: Any,
    present: Any,
    future: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the principal portion of one annuity payment."""
    payment = pmt(context, rate, periods, present, future, due)
    interest = ipmt(context, rate, period, periods, present, future, due)
    if is_error(payment):
        return payment
    if is_error(interest):
        return interest
    return payment - interest


@register("PV", min_args=3, max_args=5, argument_spec="rate, nper, pmt, [fv], [type]")
def pv(
    context: Any,
    rate: Any,
    periods: Any,
    payment: Any,
    future: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the present value of a fixed-rate annuity."""
    values = [_number(context, value) for value in (rate, periods, payment, future, due)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, periods_value, payment_value, future_value, due_value = values
    if rate_value == 0:
        return -future_value - payment_value * periods_value
    factor = (1 + rate_value) ** periods_value
    return -(
        future_value
        + payment_value * (1 + rate_value * due_value) * (factor - 1) / rate_value
    ) / factor


@register("FV", min_args=3, max_args=5, argument_spec="rate, nper, pmt, [pv], [type]")
def fv(
    context: Any,
    rate: Any,
    periods: Any,
    payment: Any,
    present: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the future value of a fixed-rate annuity."""
    values = [_number(context, value) for value in (rate, periods, payment, present, due)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, periods_value, payment_value, present_value, due_value = values
    if rate_value == 0:
        return -(present_value + payment_value * periods_value)
    factor = (1 + rate_value) ** periods_value
    return -(
        present_value * factor
        + payment_value * (1 + rate_value * due_value) * (factor - 1) / rate_value
    )


@register("NPV", min_args=2, argument_spec="rate, value1, [value2], ...")
def npv(context: Any, rate: Any, *cash_flows: Any) -> Any:
    """Return net present value with first cash flow at period one."""
    rate_value = _number(context, rate)
    values = numeric_values(context, *cash_flows, ignore_non_numeric=False)
    if is_error(rate_value) or is_error(values):
        return VALUE_ERROR
    if rate_value == -1:
        return DIV_ZERO_ERROR
    return sum(value / (1 + rate_value) ** period for period, value in enumerate(values, 1))


def _solve_rate(
    function: Callable[[float], float],
    *,
    guess: float,
) -> float | None:
    value = guess
    for _ in range(100):
        try:
            result = function(value)
            step = max(1e-7, abs(value) * 1e-6)
            derivative = (function(value + step) - result) / step
            if abs(derivative) < 1e-14:
                break
            next_value = value - result / derivative
            if next_value <= -0.999999:
                next_value = (value - 0.999999) / 2
            if abs(next_value - value) < 1e-10:
                return next_value
            value = next_value
        except (ArithmeticError, ValueError, OverflowError):
            break
    lower, upper = -0.9999, 10.0
    try:
        lower_value, upper_value = function(lower), function(upper)
        if lower_value * upper_value > 0:
            return None
        for _ in range(200):
            midpoint = (lower + upper) / 2
            midpoint_value = function(midpoint)
            if abs(midpoint_value) < 1e-9:
                return midpoint
            if lower_value * midpoint_value <= 0:
                upper = midpoint
            else:
                lower, lower_value = midpoint, midpoint_value
        return (lower + upper) / 2
    except (ArithmeticError, ValueError, OverflowError):
        return None


@register("IRR", min_args=1, max_args=2, argument_spec="values, [guess]")
def irr(context: Any, values: Any, guess: Any = 0.1) -> Any:
    """Return the internal rate of return for periodic cash flows."""
    cash_flows = numeric_values(context, values, ignore_non_numeric=False)
    guess_value = _number(context, guess)
    if is_error(cash_flows) or is_error(guess_value):
        return VALUE_ERROR
    if not any(value > 0 for value in cash_flows) or not any(value < 0 for value in cash_flows):
        return NUM_ERROR
    solved = _solve_rate(
        lambda rate: sum(
            value / (1 + rate) ** period
            for period, value in enumerate(cash_flows)
        ),
        guess=guess_value,
    )
    return NUM_ERROR if solved is None else solved


@register("XNPV", min_args=3, max_args=3, argument_spec="rate, values, dates")
def xnpv(context: Any, rate: Any, values: Any, dates: Any) -> Any:
    """Return net present value for irregularly dated cash flows."""
    rate_value = _number(context, rate)
    cash_flows = numeric_values(context, values, ignore_non_numeric=False)
    date_values = [serial_datetime(value) for value in flatten(context, dates)]
    if (
        is_error(rate_value)
        or is_error(cash_flows)
        or any(is_error(value) for value in date_values)
        or len(cash_flows) != len(date_values)
        or rate_value <= -1
    ):
        return VALUE_ERROR
    first_date = date_values[0]
    return sum(
        cash_flow / (1 + rate_value) ** ((date_value - first_date).days / 365)
        for cash_flow, date_value in zip(cash_flows, date_values)
    )


@register("XIRR", min_args=2, max_args=3, argument_spec="values, dates, [guess]")
def xirr(context: Any, values: Any, dates: Any, guess: Any = 0.1) -> Any:
    """Return internal rate of return for irregularly dated cash flows."""
    cash_flows = numeric_values(context, values, ignore_non_numeric=False)
    date_values = [serial_datetime(value) for value in flatten(context, dates)]
    guess_value = _number(context, guess)
    if (
        is_error(cash_flows)
        or is_error(guess_value)
        or any(is_error(value) for value in date_values)
        or len(cash_flows) != len(date_values)
        or not cash_flows
    ):
        return VALUE_ERROR
    first_date = date_values[0]
    solved = _solve_rate(
        lambda rate: sum(
            cash_flow / (1 + rate) ** ((date_value - first_date).days / 365)
            for cash_flow, date_value in zip(cash_flows, date_values)
        ),
        guess=guess_value,
    )
    return NUM_ERROR if solved is None else solved


@register("RATE", min_args=3, max_args=6, argument_spec="nper, pmt, pv, [fv], [type], [guess]")
def rate(
    context: Any,
    periods: Any,
    payment: Any,
    present: Any,
    future: Any = 0,
    due: Any = 0,
    guess: Any = 0.1,
) -> Any:
    """Return the interest rate per annuity period."""
    values = [_number(context, value) for value in (periods, payment, present, future, due, guess)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    periods_value, payment_value, present_value, future_value, due_value, guess_value = values
    if payment_value == 0 and present_value == 0 and future_value == 0:
        return NUM_ERROR

    def balance(rate_value: float) -> float:
        if abs(rate_value) < 1e-12:
            return present_value + payment_value * periods_value + future_value
        factor = (1 + rate_value) ** periods_value
        return (
            present_value * factor
            + payment_value * (1 + rate_value * due_value) * (factor - 1) / rate_value
            + future_value
        )

    solved = _solve_rate(balance, guess=guess_value)
    return NUM_ERROR if solved is None else solved


@register("NPER", min_args=3, max_args=5, argument_spec="rate, pmt, pv, [fv], [type]")
def nper(
    context: Any,
    rate: Any,
    payment: Any,
    present: Any,
    future: Any = 0,
    due: Any = 0,
) -> Any:
    """Return the number of annuity periods."""
    values = [_number(context, value) for value in (rate, payment, present, future, due)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, payment_value, present_value, future_value, due_value = values
    if rate_value == 0:
        return DIV_ZERO_ERROR if payment_value == 0 else -(present_value + future_value) / payment_value
    numerator = payment_value * (1 + rate_value * due_value) - future_value * rate_value
    denominator = present_value * rate_value + payment_value * (1 + rate_value * due_value)
    if denominator == 0 or rate_value <= -1:
        return NUM_ERROR
    ratio = numerator / denominator
    if ratio <= 0:
        return NUM_ERROR
    return math.log(ratio) / math.log(1 + rate_value)


@register("SLN", min_args=3, max_args=3, argument_spec="cost, salvage, life")
def sln(context: Any, cost: Any, salvage: Any, life: Any) -> Any:
    """Return straight-line depreciation for one period."""
    values = [_number(context, value) for value in (cost, salvage, life)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    cost_value, salvage_value, life_value = values
    return DIV_ZERO_ERROR if life_value == 0 else (cost_value - salvage_value) / life_value


@register("MIRR", min_args=3, max_args=3, argument_spec="values, finance_rate, reinvest_rate")
def mirr(context: Any, values: Any, finance_rate: Any, reinvest_rate: Any) -> Any:
    """Return the modified internal rate of return for periodic cash flows."""
    cash_flows = numeric_values(context, values, ignore_non_numeric=False)
    finance = _number(context, finance_rate)
    reinvest = _number(context, reinvest_rate)
    if (
        is_error(cash_flows)
        or is_error(finance)
        or is_error(reinvest)
        or len(cash_flows) < 2
        or finance <= -1
        or reinvest <= -1
    ):
        return NUM_ERROR
    if not any(value > 0 for value in cash_flows) or not any(value < 0 for value in cash_flows):
        # Excel divides by the discounted negative (or positive) flows.
        return DIV_ZERO_ERROR
    periods = len(cash_flows) - 1
    positive_future = sum(
        value * (1 + reinvest) ** (periods - period)
        for period, value in enumerate(cash_flows)
        if value > 0
    )
    negative_present = -sum(
        value / (1 + finance) ** period
        for period, value in enumerate(cash_flows)
        if value < 0
    )
    return (positive_future / negative_present) ** (1 / periods) - 1


@register("RRI", min_args=3, max_args=3, argument_spec="nper, pv, fv")
def rri(context: Any, periods: Any, present: Any, future: Any) -> Any:
    """Return the equivalent interest rate for an investment's growth."""
    values = [_number(context, value) for value in (periods, present, future)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    periods_value, present_value, future_value = values
    if periods_value <= 0 or present_value == 0 or future_value / present_value < 0:
        return NUM_ERROR
    return (future_value / present_value) ** (1 / periods_value) - 1


@register("PDURATION", min_args=3, max_args=3, argument_spec="rate, pv, fv")
def pduration(context: Any, rate: Any, present: Any, future: Any) -> Any:
    """Return periods required for an investment to reach a target value."""
    values = [_number(context, value) for value in (rate, present, future)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, present_value, future_value = values
    if rate_value <= 0 or present_value <= 0 or future_value <= 0:
        return NUM_ERROR
    return math.log(future_value / present_value) / math.log1p(rate_value)


@register("ISPMT", min_args=4, max_args=4, argument_spec="rate, per, nper, pv")
def ispmt(context: Any, rate: Any, period: Any, periods: Any, present: Any) -> Any:
    """Return simple interest paid during one investment period."""
    values = [_number(context, value) for value in (rate, period, periods, present)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, period_value, periods_value, present_value = values
    if periods_value == 0:
        return DIV_ZERO_ERROR
    return present_value * rate_value * (period_value / periods_value - 1)


@register("EFFECT", min_args=2, max_args=2, argument_spec="nominal_rate, npery")
def effect(context: Any, nominal_rate: Any, periods: Any) -> Any:
    """Return the effective annual rate from a nominal annual rate."""
    rate_value = _number(context, nominal_rate)
    periods_value = _number(context, periods)
    if is_error(rate_value) or is_error(periods_value):
        return VALUE_ERROR
    periods_value = int(periods_value)
    if rate_value <= 0 or periods_value < 1:
        return NUM_ERROR
    return (1 + rate_value / periods_value) ** periods_value - 1


@register("NOMINAL", min_args=2, max_args=2, argument_spec="effect_rate, npery")
def nominal(context: Any, effective_rate: Any, periods: Any) -> Any:
    """Return the nominal annual rate from an effective annual rate."""
    rate_value = _number(context, effective_rate)
    periods_value = _number(context, periods)
    if is_error(rate_value) or is_error(periods_value):
        return VALUE_ERROR
    periods_value = int(periods_value)
    if rate_value <= 0 or periods_value < 1:
        return NUM_ERROR
    return periods_value * ((1 + rate_value) ** (1 / periods_value) - 1)


@register("FVSCHEDULE", min_args=2, max_args=2, argument_spec="principal, schedule")
def fvschedule(context: Any, principal: Any, schedule: Any) -> Any:
    """Return future value after applying a series of compound rates."""
    principal_value = _number(context, principal)
    rates = numeric_values(context, schedule, ignore_non_numeric=False)
    if is_error(principal_value) or is_error(rates):
        return VALUE_ERROR
    result = principal_value
    for rate_value in rates:
        result *= 1 + rate_value
    return result


@register(
    "CUMIPMT",
    min_args=6,
    max_args=6,
    argument_spec="rate, nper, pv, start_period, end_period, type",
)
def cumipmt(
    context: Any,
    rate: Any,
    periods: Any,
    present: Any,
    start_period: Any,
    end_period: Any,
    due: Any,
) -> Any:
    """Return cumulative loan interest between two payment periods."""
    values = [
        _number(context, value)
        for value in (rate, periods, present, start_period, end_period, due)
    ]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, periods_value, present_value, start_value, end_value, due_value = values
    if (
        rate_value <= 0
        or periods_value <= 0
        or present_value <= 0
        or start_value < 1
        or end_value < start_value
        or end_value > periods_value
        or due_value not in (0, 1)
    ):
        return NUM_ERROR
    return sum(
        ipmt(
            context,
            rate_value,
            period,
            periods_value,
            present_value,
            0,
            due_value,
        )
        for period in range(int(start_value), int(end_value) + 1)
    )


@register(
    "CUMPRINC",
    min_args=6,
    max_args=6,
    argument_spec="rate, nper, pv, start_period, end_period, type",
)
def cumprinc(
    context: Any,
    rate: Any,
    periods: Any,
    present: Any,
    start_period: Any,
    end_period: Any,
    due: Any,
) -> Any:
    """Return cumulative loan principal between two payment periods."""
    values = [
        _number(context, value)
        for value in (rate, periods, present, start_period, end_period, due)
    ]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, periods_value, present_value, start_value, end_value, due_value = values
    if (
        rate_value <= 0
        or periods_value <= 0
        or present_value <= 0
        or start_value < 1
        or end_value < start_value
        or end_value > periods_value
        or due_value not in (0, 1)
    ):
        return NUM_ERROR
    return sum(
        ppmt(
            context,
            rate_value,
            period,
            periods_value,
            present_value,
            0,
            due_value,
        )
        for period in range(int(start_value), int(end_value) + 1)
    )


@register("SYD", min_args=4, max_args=4, argument_spec="cost, salvage, life, per")
def syd(context: Any, cost: Any, salvage: Any, life: Any, period: Any) -> Any:
    """Return sum-of-years-digits depreciation for one period."""
    values = [_number(context, value) for value in (cost, salvage, life, period)]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    cost_value, salvage_value, life_value, period_value = values
    if life_value <= 0 or period_value < 1 or period_value > life_value:
        return NUM_ERROR
    return (
        (cost_value - salvage_value)
        * (life_value - period_value + 1)
        * 2
        / (life_value * (life_value + 1))
    )


@register("DB", min_args=4, max_args=5, argument_spec="cost, salvage, life, period, [month]")
def db(
    context: Any,
    cost: Any,
    salvage: Any,
    life: Any,
    period: Any,
    month: Any = 12,
) -> Any:
    """Return fixed-declining-balance depreciation for one period."""
    values = [
        _number(context, value) for value in (cost, salvage, life, period, month)
    ]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    cost_value, salvage_value, life_value, period_value, month_value = values
    period_value = int(period_value)
    if (
        cost_value < 0
        or salvage_value < 0
        or life_value <= 0
        or period_value < 1
        or period_value > int(life_value) + 1
        or not 1 <= month_value <= 12
        or cost_value == 0
    ):
        return NUM_ERROR
    if salvage_value == 0:
        depreciation_rate = 1.0
    else:
        depreciation_rate = round(
            1 - (salvage_value / cost_value) ** (1 / life_value),
            3,
        )
    book_value = cost_value
    depreciation = 0.0
    for current in range(1, period_value + 1):
        if current == 1:
            depreciation = book_value * depreciation_rate * month_value / 12
        elif current == int(life_value) + 1:
            depreciation = book_value * depreciation_rate * (12 - month_value) / 12
        else:
            depreciation = book_value * depreciation_rate
        depreciation = min(depreciation, max(0.0, book_value - salvage_value))
        book_value -= depreciation
    return depreciation


def _ddb_periods(
    cost: float,
    salvage: float,
    life: float,
    end_period: int,
    factor: float,
    *,
    no_switch: bool,
) -> list[float]:
    book_value = cost
    result: list[float] = []
    for period in range(end_period):
        declining = book_value * factor / life
        if no_switch:
            depreciation = declining
        else:
            remaining_periods = max(life - period, 1)
            straight_line = max(0.0, book_value - salvage) / remaining_periods
            depreciation = max(declining, straight_line)
        depreciation = min(depreciation, max(0.0, book_value - salvage))
        result.append(depreciation)
        book_value -= depreciation
    return result


def _ddb_value(
    cost: float,
    salvage: float,
    life: float,
    period: float,
    factor: float,
) -> float:
    """Return Excel's declining-balance depreciation for one period."""
    rate = factor / life
    if rate >= 1:
        rate = 1.0
        old_value = cost if period == 1 else 0.0
    else:
        old_value = cost * (1 - rate) ** (period - 1)
    new_value = cost * (1 - rate) ** period
    depreciation = (
        old_value - salvage
        if new_value < salvage
        else old_value - new_value
    )
    return max(0.0, depreciation)


def _vdb_intermediate(
    cost: float,
    salvage: float,
    life: float,
    remaining_life: float,
    periods: float,
    factor: float,
) -> float:
    """Apply Excel's declining-to-straight-line switching calculation."""
    period_count = int(math.ceil(periods))
    depreciable_value = cost - salvage
    straight_line = 0.0
    switched = False
    total = 0.0
    for period in range(1, period_count + 1):
        if not switched:
            declining = _ddb_value(cost, salvage, life, period, factor)
            straight_line = depreciable_value / (remaining_life - (period - 1))
            if straight_line > declining:
                term = straight_line
                switched = True
            else:
                term = declining
                depreciable_value -= declining
        else:
            term = straight_line
        if period == period_count:
            term *= periods + 1 - period_count
        total += term
    return total


@register("DDB", min_args=4, max_args=5, argument_spec="cost, salvage, life, period, [factor]")
def ddb(
    context: Any,
    cost: Any,
    salvage: Any,
    life: Any,
    period: Any,
    factor: Any = 2,
) -> Any:
    """Return double-declining or factor-based depreciation for one period."""
    values = [
        _number(context, value) for value in (cost, salvage, life, period, factor)
    ]
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    cost_value, salvage_value, life_value, period_value, factor_value = values
    if (
        cost_value < 0
        or salvage_value < 0
        or life_value <= 0
        or period_value < 1
        or factor_value <= 0
    ):
        return NUM_ERROR
    periods = _ddb_periods(
        cost_value,
        salvage_value,
        life_value,
        int(math.ceil(period_value)),
        factor_value,
        no_switch=True,
    )
    return periods[-1]


@register(
    "VDB",
    min_args=5,
    max_args=7,
    argument_spec="cost, salvage, life, start_period, end_period, [factor], [no_switch]",
)
def vdb(
    context: Any,
    cost: Any,
    salvage: Any,
    life: Any,
    start_period: Any,
    end_period: Any,
    factor: Any = 2,
    no_switch: Any = False,
) -> Any:
    """Return declining-balance depreciation over a period interval."""
    values = [
        _number(context, value)
        for value in (cost, salvage, life, start_period, end_period, factor)
    ]
    no_switch_value = scalar(context, no_switch)
    if any(is_error(value) for value in values) or is_error(no_switch_value):
        return VALUE_ERROR
    cost_value, salvage_value, life_value, start_value, end_value, factor_value = values
    if (
        cost_value < 0
        or salvage_value < 0
        or salvage_value > cost_value
        or life_value <= 0
        or start_value < 0
        or end_value < start_value
        or end_value > life_value
        or factor_value <= 0
    ):
        return NUM_ERROR
    start_period = math.floor(start_value)
    end_period = math.ceil(end_value)
    if bool(no_switch_value):
        total = 0.0
        for period in range(start_period + 1, end_period + 1):
            term = _ddb_value(
                cost_value,
                salvage_value,
                life_value,
                period,
                factor_value,
            )
            if period == start_period + 1:
                term *= min(end_value, start_period + 1) - start_value
            elif period == end_period:
                term *= end_value + 1 - end_period
            total += term
        return total

    value_at_start = cost_value - _vdb_intermediate(
        cost_value,
        salvage_value,
        life_value,
        life_value,
        start_value,
        factor_value,
    )
    return _vdb_intermediate(
        value_at_start,
        salvage_value,
        life_value,
        life_value - start_value,
        end_value - start_value,
        factor_value,
    )


@register("DOLLARDE", min_args=2, max_args=2, argument_spec="fractional_dollar, fraction")
def dollarde(context: Any, fractional_dollar: Any, fraction: Any) -> Any:
    """Convert a fractional dollar quotation to a decimal value."""
    dollar_value = _number(context, fractional_dollar)
    fraction_value = _number(context, fraction)
    if is_error(dollar_value) or is_error(fraction_value):
        return VALUE_ERROR
    fraction_value = int(fraction_value)
    if fraction_value < 0:
        return NUM_ERROR
    if fraction_value == 0:
        return DIV_ZERO_ERROR
    scale = 10 ** math.ceil(math.log10(fraction_value))
    whole = math.trunc(dollar_value)
    fractional = abs(dollar_value - whole)
    return whole + math.copysign(fractional * scale / fraction_value, dollar_value)


@register("DOLLARFR", min_args=2, max_args=2, argument_spec="decimal_dollar, fraction")
def dollarfr(context: Any, decimal_dollar: Any, fraction: Any) -> Any:
    """Convert a decimal dollar value to a fractional quotation."""
    dollar_value = _number(context, decimal_dollar)
    fraction_value = _number(context, fraction)
    if is_error(dollar_value) or is_error(fraction_value):
        return VALUE_ERROR
    fraction_value = int(fraction_value)
    if fraction_value < 0:
        return NUM_ERROR
    if fraction_value == 0:
        return DIV_ZERO_ERROR
    scale = 10 ** math.ceil(math.log10(fraction_value))
    whole = math.trunc(dollar_value)
    fractional = abs(dollar_value - whole)
    return whole + math.copysign(fractional * fraction_value / scale, dollar_value)


def _financial_date(context: Any, value: Any) -> date | Any:
    converted = serial_datetime(scalar(context, value))
    return converted if is_error(converted) else converted.date()


def _date_serial(value: date) -> float:
    converted = number(value)
    assert not is_error(converted)
    return float(converted)


def _validated_basis(context: Any, value: Any) -> int | Any:
    converted = _number(context, value)
    if is_error(converted):
        return VALUE_ERROR
    basis = int(converted)
    return basis if 0 <= basis <= 4 else NUM_ERROR


def _days_30_360(start: date, end: date, *, european: bool) -> int:
    start_day = start.day
    end_day = end.day
    if european:
        start_day = min(start_day, 30)
        end_day = min(end_day, 30)
    else:
        start_is_february_end = (
            start.month == 2
            and start.day == calendar.monthrange(start.year, start.month)[1]
        )
        end_is_february_end = (
            end.month == 2
            and end.day == calendar.monthrange(end.year, end.month)[1]
        )
        if start_day == 31 or start_is_february_end:
            start_day = 30
        if end_day == 31 and start_day >= 30:
            end_day = 30
        if end_is_february_end and start_is_february_end:
            end_day = 30
    return (
        (end.year - start.year) * 360
        + (end.month - start.month) * 30
        + end_day
        - start_day
    )


def _days_between(start: date, end: date, basis: int) -> int:
    if basis == 0:
        return _days_30_360(start, end, european=False)
    if basis == 4:
        return _days_30_360(start, end, european=True)
    return (end - start).days


def _year_fraction(start: date, end: date, basis: int) -> float:
    if basis in (0, 2, 4):
        return _days_between(start, end, basis) / 360
    if basis == 3:
        return _days_between(start, end, basis) / 365
    if start == end:
        return 0.0
    direction = 1 if end > start else -1
    left, right = (start, end) if direction > 0 else (end, start)
    total = 0.0
    current = left
    while current < right:
        boundary = min(right, date(current.year + 1, 1, 1))
        denominator = 366 if calendar.isleap(current.year) else 365
        total += (boundary - current).days / denominator
        current = boundary
    return total * direction


def _validated_security_dates(
    context: Any,
    settlement: Any,
    maturity: Any,
    basis: Any,
) -> tuple[date, date, int] | Any:
    settlement_date = _financial_date(context, settlement)
    maturity_date = _financial_date(context, maturity)
    basis_value = _validated_basis(context, basis)
    if (
        is_error(settlement_date)
        or is_error(maturity_date)
        or is_error(basis_value)
    ):
        return VALUE_ERROR if basis_value is not NUM_ERROR else NUM_ERROR
    if settlement_date >= maturity_date:
        return NUM_ERROR
    return settlement_date, maturity_date, basis_value


def _validated_frequency(context: Any, value: Any) -> int | Any:
    converted = _number(context, value)
    if is_error(converted):
        return VALUE_ERROR
    frequency = int(converted)
    return frequency if frequency in (1, 2, 4) else NUM_ERROR


def _is_month_end(value: date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def _coupon_shift(maturity: date, months: int) -> date:
    shifted = maturity + relativedelta(months=months)
    if _is_month_end(maturity):
        return shifted.replace(day=calendar.monthrange(shifted.year, shifted.month)[1])
    return shifted


def _coupon_schedule(
    settlement: date,
    maturity: date,
    frequency: int,
) -> tuple[date, date, int]:
    months = 12 // frequency
    count = 0
    next_coupon = maturity
    while next_coupon > settlement:
        count += 1
        previous_coupon = _coupon_shift(maturity, -months * count)
        if previous_coupon <= settlement:
            return previous_coupon, next_coupon, count
        next_coupon = previous_coupon
    return settlement, _coupon_shift(settlement, months), 0


def _coupon_metrics(
    settlement: date,
    maturity: date,
    frequency: int,
    basis: int,
) -> tuple[date, date, int, float, float, float]:
    previous_coupon, next_coupon, count = _coupon_schedule(
        settlement,
        maturity,
        frequency,
    )
    period_days = float(_days_between(previous_coupon, next_coupon, basis))
    if basis in (0, 2, 4):
        period_days = 360 / frequency
    elif basis == 3:
        period_days = 365 / frequency
    accrued_days = float(_days_between(previous_coupon, settlement, basis))
    remaining_days = float(_days_between(settlement, next_coupon, basis))
    return (
        previous_coupon,
        next_coupon,
        count,
        period_days,
        accrued_days,
        remaining_days,
    )


def _security_price(
    settlement: date,
    maturity: date,
    coupon_rate: float,
    yield_rate: float,
    redemption: float,
    frequency: int,
    basis: int,
) -> float:
    _, _, count, period_days, accrued_days, remaining_days = _coupon_metrics(
        settlement,
        maturity,
        frequency,
        basis,
    )
    coupon = 100 * coupon_rate / frequency
    fraction_to_next = (
        remaining_days / period_days
        if basis == 1
        else 1 - accrued_days / period_days
    )
    periodic_yield = yield_rate / frequency
    dirty_price = sum(
        coupon / (1 + periodic_yield) ** (index - 1 + fraction_to_next)
        for index in range(1, count + 1)
    )
    dirty_price += redemption / (
        1 + periodic_yield
    ) ** (count - 1 + fraction_to_next)
    return dirty_price - coupon * accrued_days / period_days


def _security_arguments(
    context: Any,
    settlement: Any,
    maturity: Any,
    coupon_rate: Any,
    yield_rate: Any,
    redemption: Any,
    frequency: Any,
    basis: Any,
) -> tuple[date, date, float, float, float, int, int] | Any:
    dates = _validated_security_dates(context, settlement, maturity, basis)
    frequency_value = _validated_frequency(context, frequency)
    values = [
        _number(context, value)
        for value in (coupon_rate, yield_rate, redemption)
    ]
    if is_error(dates) or is_error(frequency_value):
        return NUM_ERROR if dates is NUM_ERROR or frequency_value is NUM_ERROR else VALUE_ERROR
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, yield_value, redemption_value = values
    if rate_value < 0 or yield_value < 0 or redemption_value <= 0:
        return NUM_ERROR
    settlement_date, maturity_date, basis_value = dates
    return (
        settlement_date,
        maturity_date,
        rate_value,
        yield_value,
        redemption_value,
        frequency_value,
        basis_value,
    )


@register(
    "PRICE",
    min_args=6,
    max_args=7,
    argument_spec="settlement, maturity, rate, yld, redemption, frequency, [basis]",
)
def price(
    context: Any,
    settlement: Any,
    maturity: Any,
    coupon_rate: Any,
    yield_rate: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return a coupon-bearing security's price per 100 face value."""
    values = _security_arguments(
        context,
        settlement,
        maturity,
        coupon_rate,
        yield_rate,
        redemption,
        frequency,
        basis,
    )
    if is_error(values):
        return values
    return _security_price(*values)


@register(
    "YIELD",
    min_args=6,
    max_args=7,
    argument_spec="settlement, maturity, rate, pr, redemption, frequency, [basis]",
)
def yield_function(
    context: Any,
    settlement: Any,
    maturity: Any,
    coupon_rate: Any,
    security_price: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the annual yield of a coupon-bearing security."""
    dates = _validated_security_dates(context, settlement, maturity, basis)
    frequency_value = _validated_frequency(context, frequency)
    values = [
        _number(context, value)
        for value in (coupon_rate, security_price, redemption)
    ]
    if is_error(dates) or is_error(frequency_value):
        return NUM_ERROR if dates is NUM_ERROR or frequency_value is NUM_ERROR else VALUE_ERROR
    if any(is_error(value) for value in values):
        return VALUE_ERROR
    rate_value, price_value, redemption_value = values
    if rate_value < 0 or price_value <= 0 or redemption_value <= 0:
        return NUM_ERROR
    settlement_date, maturity_date, basis_value = dates
    solved = _solve_rate(
        lambda candidate: _security_price(
            settlement_date,
            maturity_date,
            rate_value,
            candidate,
            redemption_value,
            frequency_value,
            basis_value,
        )
        - price_value,
        guess=0.05,
    )
    return NUM_ERROR if solved is None or solved < 0 else solved


def _duration_value(
    settlement: date,
    maturity: date,
    coupon_rate: float,
    yield_rate: float,
    frequency: int,
    basis: int,
) -> float:
    _, _, count, period_days, accrued_days, remaining_days = _coupon_metrics(
        settlement,
        maturity,
        frequency,
        basis,
    )
    fraction_to_next = (
        remaining_days / period_days
        if basis == 1
        else 1 - accrued_days / period_days
    )
    coupon = 100 * coupon_rate / frequency
    periodic_yield = yield_rate / frequency
    present_values: list[tuple[float, float]] = []
    for index in range(1, count + 1):
        periods = index - 1 + fraction_to_next
        cash_flow = coupon + (100 if index == count else 0)
        present_value = cash_flow / (1 + periodic_yield) ** periods
        present_values.append((periods / frequency, present_value))
    denominator = sum(value for _, value in present_values)
    return sum(time * value for time, value in present_values) / denominator


@register(
    "DURATION",
    min_args=5,
    max_args=6,
    argument_spec="settlement, maturity, coupon, yld, frequency, [basis]",
)
def duration(
    context: Any,
    settlement: Any,
    maturity: Any,
    coupon_rate: Any,
    yield_rate: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return Macaulay duration in years for a coupon-bearing security."""
    values = _security_arguments(
        context,
        settlement,
        maturity,
        coupon_rate,
        yield_rate,
        100,
        frequency,
        basis,
    )
    if is_error(values):
        return values
    settlement_date, maturity_date, rate_value, yield_value, _, frequency_value, basis_value = values
    return _duration_value(
        settlement_date,
        maturity_date,
        rate_value,
        yield_value,
        frequency_value,
        basis_value,
    )


@register(
    "MDURATION",
    min_args=5,
    max_args=6,
    argument_spec="settlement, maturity, coupon, yld, frequency, [basis]",
)
def mduration(
    context: Any,
    settlement: Any,
    maturity: Any,
    coupon_rate: Any,
    yield_rate: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return modified duration in years for a coupon-bearing security."""
    frequency_value = _validated_frequency(context, frequency)
    yield_value = _number(context, yield_rate)
    result = duration(
        context,
        settlement,
        maturity,
        coupon_rate,
        yield_rate,
        frequency,
        basis,
    )
    if is_error(result):
        return result
    return result / (1 + yield_value / frequency_value)


@register(
    "ACCRINT",
    min_args=6,
    max_args=8,
    argument_spec=(
        "issue, first_interest, settlement, rate, par, frequency, "
        "[basis], [calc_method]"
    ),
)
def accrint(
    context: Any,
    issue: Any,
    first_interest: Any,
    settlement: Any,
    rate: Any,
    par: Any,
    frequency: Any,
    basis: Any = 0,
    calc_method: Any = True,
) -> Any:
    """Return accrued interest for a periodic coupon security."""
    issue_date = _financial_date(context, issue)
    first_date = _financial_date(context, first_interest)
    settlement_date = _financial_date(context, settlement)
    rate_value = _number(context, rate)
    par_value = _number(context, par)
    frequency_value = _validated_frequency(context, frequency)
    basis_value = _validated_basis(context, basis)
    if any(
        is_error(value)
        for value in (
            issue_date,
            first_date,
            settlement_date,
            rate_value,
            par_value,
            frequency_value,
            basis_value,
        )
    ):
        return VALUE_ERROR
    if (
        issue_date >= settlement_date
        or first_date <= issue_date
        or rate_value <= 0
        or par_value <= 0
    ):
        return NUM_ERROR
    # Excel accrues from the issue date in every case it was checked against,
    # whatever calc_method says, so calc_method is accepted and ignored.
    scalar(context, calc_method)
    periods = _accrual_periods(issue_date, first_date, settlement_date, frequency_value, basis_value)
    return par_value * rate_value / frequency_value * periods


def _accrual_periods(issue: date, first: date, settlement: date, frequency: int, basis: int) -> float:
    """Count coupon periods from issue to settlement the way Excel's ACCRINT does.

    Coupon dates step from the first interest date. Each period contributes
    its accrued days over a normal period length; a whole period before the
    first interest date counts as exactly one. Excel measures a period after
    the first interest date against the length of the period before it
    (actual/actual) or against 360 or 365 divided by the frequency.
    """
    months = 12 // frequency
    boundaries = [first]
    while boundaries[0] > issue:
        boundaries.insert(0, _coupon_shift(first, -months * len(boundaries)))
    step = 1
    while boundaries[-1] < settlement:
        boundaries.append(_coupon_shift(first, months * step))
        step += 1
    normal = {0: 360 / frequency, 2: 360 / frequency, 3: 365 / frequency, 4: 360 / frequency}
    total = 0.0
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        low, high = max(issue, start), min(settlement, end)
        if high <= low:
            continue
        accrued = _days_between(low, high, basis)
        if end <= first:
            if (low, high) == (start, end):
                total += 1
                continue
            if basis == 1:
                length = (end - start).days
            elif basis == 4:
                length = _days_between(start, end, 4)
            else:
                length = normal[basis]
        elif basis == 1:
            length = (start - boundaries[index - 1]).days
        else:
            length = normal[basis]
        total += accrued / length
    return total


def _discount_security_values(
    context: Any,
    settlement: Any,
    maturity: Any,
    first_value: Any,
    second_value: Any,
    basis: Any,
) -> tuple[date, date, float, float, int, float] | Any:
    dates = _validated_security_dates(context, settlement, maturity, basis)
    left_value = _number(context, first_value)
    right_value = _number(context, second_value)
    if is_error(dates):
        return dates
    if is_error(left_value) or is_error(right_value):
        return VALUE_ERROR
    if left_value <= 0 or right_value <= 0:
        return NUM_ERROR
    settlement_date, maturity_date, basis_value = dates
    fraction = _year_fraction(settlement_date, maturity_date, basis_value)
    if fraction <= 0:
        return NUM_ERROR
    return (
        settlement_date,
        maturity_date,
        left_value,
        right_value,
        basis_value,
        fraction,
    )


@register("DISC", min_args=4, max_args=5, argument_spec="settlement, maturity, pr, redemption, [basis]")
def disc(
    context: Any,
    settlement: Any,
    maturity: Any,
    security_price: Any,
    redemption: Any,
    basis: Any = 0,
) -> Any:
    """Return the discount rate of a security."""
    values = _discount_security_values(
        context, settlement, maturity, security_price, redemption, basis
    )
    if is_error(values):
        return values
    _, _, price_value, redemption_value, _, fraction = values
    return (redemption_value - price_value) / redemption_value / fraction


@register(
    "INTRATE",
    min_args=4,
    max_args=5,
    argument_spec="settlement, maturity, investment, redemption, [basis]",
)
def intrate(
    context: Any,
    settlement: Any,
    maturity: Any,
    investment: Any,
    redemption: Any,
    basis: Any = 0,
) -> Any:
    """Return the interest rate for a fully invested security."""
    values = _discount_security_values(
        context, settlement, maturity, investment, redemption, basis
    )
    if is_error(values):
        return values
    _, _, investment_value, redemption_value, _, fraction = values
    return (redemption_value - investment_value) / investment_value / fraction


@register(
    "RECEIVED",
    min_args=4,
    max_args=5,
    argument_spec="settlement, maturity, investment, discount, [basis]",
)
def received(
    context: Any,
    settlement: Any,
    maturity: Any,
    investment: Any,
    discount: Any,
    basis: Any = 0,
) -> Any:
    """Return the amount received at maturity for a discounted security."""
    values = _discount_security_values(
        context, settlement, maturity, investment, discount, basis
    )
    if is_error(values):
        return values
    _, _, investment_value, discount_value, _, fraction = values
    denominator = 1 - discount_value * fraction
    return NUM_ERROR if denominator <= 0 else investment_value / denominator


@register(
    "PRICEDISC",
    min_args=4,
    max_args=5,
    argument_spec="settlement, maturity, discount, redemption, [basis]",
)
def pricedisc(
    context: Any,
    settlement: Any,
    maturity: Any,
    discount: Any,
    redemption: Any,
    basis: Any = 0,
) -> Any:
    """Return price per 100 face value for a discounted security."""
    values = _discount_security_values(
        context, settlement, maturity, discount, redemption, basis
    )
    if is_error(values):
        return values
    _, _, discount_value, redemption_value, _, fraction = values
    # Excel returns a negative price for a very large discount.
    return redemption_value * (1 - discount_value * fraction)


@register(
    "YIELDDISC",
    min_args=4,
    max_args=5,
    argument_spec="settlement, maturity, pr, redemption, [basis]",
)
def yielddisc(
    context: Any,
    settlement: Any,
    maturity: Any,
    security_price: Any,
    redemption: Any,
    basis: Any = 0,
) -> Any:
    """Return annual yield for a discounted security."""
    values = _discount_security_values(
        context, settlement, maturity, security_price, redemption, basis
    )
    if is_error(values):
        return values
    _, _, price_value, redemption_value, _, fraction = values
    return (redemption_value - price_value) / price_value / fraction


def _treasury_values(
    context: Any,
    settlement: Any,
    maturity: Any,
    value: Any,
) -> tuple[int, float] | Any:
    settlement_date = _financial_date(context, settlement)
    maturity_date = _financial_date(context, maturity)
    selected_value = _number(context, value)
    if (
        is_error(settlement_date)
        or is_error(maturity_date)
        or is_error(selected_value)
    ):
        return VALUE_ERROR
    days = (maturity_date - settlement_date).days
    if days <= 0 or days > 365 or selected_value <= 0:
        return NUM_ERROR
    return days, selected_value


@register("TBILLPRICE", min_args=3, max_args=3, argument_spec="settlement, maturity, discount")
def tbillprice(
    context: Any,
    settlement: Any,
    maturity: Any,
    discount: Any,
) -> Any:
    """Return a Treasury bill's price per 100 face value."""
    values = _treasury_values(context, settlement, maturity, discount)
    if is_error(values):
        return values
    days, discount_value = values
    result = 100 * (1 - discount_value * days / 360)
    return NUM_ERROR if result <= 0 else result


@register("TBILLYIELD", min_args=3, max_args=3, argument_spec="settlement, maturity, pr")
def tbillyield(
    context: Any,
    settlement: Any,
    maturity: Any,
    security_price: Any,
) -> Any:
    """Return a Treasury bill's annualized yield."""
    values = _treasury_values(context, settlement, maturity, security_price)
    if is_error(values):
        return values
    days, price_value = values
    return (100 - price_value) / price_value * 360 / days


@register("TBILLEQ", min_args=3, max_args=3, argument_spec="settlement, maturity, discount")
def tbilleq(
    context: Any,
    settlement: Any,
    maturity: Any,
    discount: Any,
) -> Any:
    """Return a Treasury bill's bond-equivalent yield."""
    values = _treasury_values(context, settlement, maturity, discount)
    if is_error(values):
        return values
    days, discount_value = values
    denominator = 360 - discount_value * days
    return NUM_ERROR if denominator <= 0 else 365 * discount_value / denominator


def _coupon_inputs(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any,
) -> tuple[date, date, int, int] | Any:
    dates = _validated_security_dates(context, settlement, maturity, basis)
    frequency_value = _validated_frequency(context, frequency)
    if is_error(dates) or is_error(frequency_value):
        return NUM_ERROR if dates is NUM_ERROR or frequency_value is NUM_ERROR else VALUE_ERROR
    settlement_date, maturity_date, basis_value = dates
    return settlement_date, maturity_date, frequency_value, basis_value


@register(
    "COUPDAYBS",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def coupdaybs(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return days from the previous coupon date to settlement."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, basis_value = values
    return _coupon_metrics(
        settlement_date, maturity_date, frequency_value, basis_value
    )[4]


@register(
    "COUPDAYS",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def coupdays(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return days in the coupon period containing settlement."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, basis_value = values
    metrics = _coupon_metrics(
        settlement_date, maturity_date, frequency_value, basis_value
    )
    if basis_value == 1:
        previous_coupon = metrics[0]
        nominal_next = previous_coupon + relativedelta(
            months=12 // frequency_value
        )
        return float((nominal_next - previous_coupon).days)
    return metrics[3]


@register(
    "COUPDAYSNC",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def coupdaysnc(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return days from settlement to the next coupon date."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, basis_value = values
    return _coupon_metrics(
        settlement_date, maturity_date, frequency_value, basis_value
    )[5]


@register(
    "COUPNCD",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def coupncd(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the next coupon date as an Excel serial."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, basis_value = values
    next_coupon = _coupon_metrics(
        settlement_date, maturity_date, frequency_value, basis_value
    )[1]
    return _date_serial(next_coupon)


@register(
    "COUPNUM",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def coupnum(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return coupon payments from settlement through maturity."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, _ = values
    return _coupon_schedule(settlement_date, maturity_date, frequency_value)[2]


@register(
    "COUPPCD",
    min_args=3,
    max_args=4,
    argument_spec="settlement, maturity, frequency, [basis]",
)
def couppcd(
    context: Any,
    settlement: Any,
    maturity: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the previous coupon date as an Excel serial."""
    values = _coupon_inputs(context, settlement, maturity, frequency, basis)
    if is_error(values):
        return values
    settlement_date, maturity_date, frequency_value, basis_value = values
    previous_coupon = _coupon_metrics(
        settlement_date, maturity_date, frequency_value, basis_value
    )[0]
    return _date_serial(previous_coupon)
