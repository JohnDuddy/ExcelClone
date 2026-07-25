"""Financial worksheet functions."""

from __future__ import annotations

import math
from typing import Any, Callable

from excelclone.core.errors import DIV_ZERO_ERROR, NUM_ERROR, VALUE_ERROR, is_error
from excelclone.core.functions import register
from excelclone.core.functions.common import (
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
        return DIV_ZERO_ERROR
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
    if is_error(rate_value) or is_error(values) or rate_value == -1:
        return VALUE_ERROR
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
    cash_flows = (payment_value, present_value, future_value)
    if all(value >= 0 for value in cash_flows) or all(
        value <= 0 for value in cash_flows
    ):
        return NUM_ERROR
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
