"""Excel financial functions for maturity-paying, odd-period, and French-depreciation cases."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from duddysheet.core.errors import NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions.common import number, scalar
from duddysheet.core.functions.finance_fn import (
    _coupon_shift,
    _days_between,
    _financial_date,
    _validated_basis,
    _validated_frequency,
    _year_fraction,
)

FINANCE = "Financial"


def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


def _year_basis(basis: int) -> float:
    return 365.0 if basis in (1, 3) else 360.0


def _dates(context: Any, *values: Any) -> Any:
    converted = [_financial_date(context, value) for value in values]
    for item in converted:
        if is_error(item):
            return VALUE_ERROR
    return converted


def _numbers(context: Any, *values: Any) -> Any:
    converted = [_num(context, value) for value in values]
    for item in converted:
        if is_error(item):
            return VALUE_ERROR
    return converted


@register(
    "ACCRINTM",
    min_args=4,
    max_args=5,
    argument_spec="issue, settlement, rate, par, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def accrintm(
    context: Any,
    issue: Any,
    settlement: Any,
    rate: Any,
    par: Any,
    basis: Any = 0,
) -> Any:
    """Return the accrued interest for a security that pays interest at maturity."""
    dates = _dates(context, issue, settlement)
    values = _numbers(context, rate, par)
    basis_value = _validated_basis(context, 0 if basis is None else basis)
    for item in (dates, values, basis_value):
        if is_error(item):
            return item
    (issue_date, settlement_date), (rate_value, par_value) = dates, values
    if rate_value <= 0 or par_value <= 0 or issue_date >= settlement_date:
        return NUM_ERROR
    return par_value * rate_value * _year_fraction(issue_date, settlement_date, basis_value)


def _maturity_terms(context: Any, settlement: Any, maturity: Any, issue: Any, basis: Any) -> Any:
    dates = _dates(context, settlement, maturity, issue)
    basis_value = _validated_basis(context, 0 if basis is None else basis)
    if is_error(dates):
        return dates
    if is_error(basis_value):
        return basis_value
    settlement_date, maturity_date, issue_date = dates
    if settlement_date >= maturity_date or issue_date >= settlement_date:
        return NUM_ERROR
    year = _year_basis(basis_value)
    dim = _days_between(issue_date, maturity_date, basis_value) / year
    dsm = _days_between(settlement_date, maturity_date, basis_value) / year
    accrued = _days_between(issue_date, settlement_date, basis_value) / year
    return dim, dsm, accrued


@register(
    "PRICEMAT",
    min_args=5,
    max_args=6,
    argument_spec="settlement, maturity, issue, rate, yld, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def pricemat(
    context: Any,
    settlement: Any,
    maturity: Any,
    issue: Any,
    rate: Any,
    yld: Any,
    basis: Any = 0,
) -> Any:
    """Return the price per $100 of a security that pays interest at maturity."""
    terms = _maturity_terms(context, settlement, maturity, issue, basis)
    values = _numbers(context, rate, yld)
    if is_error(terms):
        return terms
    if is_error(values):
        return values
    dim, dsm, accrued = terms
    rate_value, yield_value = values
    if rate_value < 0 or yield_value < 0:
        return NUM_ERROR
    return (100 + dim * rate_value * 100) / (1 + dsm * yield_value) - accrued * rate_value * 100


@register(
    "YIELDMAT",
    min_args=5,
    max_args=6,
    argument_spec="settlement, maturity, issue, rate, pr, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def yieldmat(
    context: Any,
    settlement: Any,
    maturity: Any,
    issue: Any,
    rate: Any,
    price: Any,
    basis: Any = 0,
) -> Any:
    """Return the annual yield of a security that pays interest at maturity."""
    terms = _maturity_terms(context, settlement, maturity, issue, basis)
    values = _numbers(context, rate, price)
    if is_error(terms):
        return terms
    if is_error(values):
        return values
    dim, dsm, accrued = terms
    rate_value, price_value = values
    if rate_value < 0 or price_value <= 0:
        return NUM_ERROR
    numerator = (1 + dim * rate_value) - (price_value / 100 + accrued * rate_value)
    denominator = price_value / 100 + accrued * rate_value
    return numerator / denominator / dsm


def _depreciation_inputs(
    context: Any,
    cost: Any,
    purchased: Any,
    first_period: Any,
    salvage: Any,
    period: Any,
    rate: Any,
    basis: Any,
) -> Any:
    values = _numbers(context, cost, salvage, period, rate)
    dates = _dates(context, purchased, first_period)
    basis_value = _validated_basis(context, 0 if basis is None else basis)
    for item in (values, dates, basis_value):
        if is_error(item):
            return item
    cost_value, salvage_value, period_value, rate_value = values
    purchase_date, first_date = dates
    if (
        cost_value < 0
        or salvage_value < 0
        or salvage_value > cost_value
        or period_value < 0
        or rate_value <= 0
        or basis_value == 2
        or first_date < purchase_date
    ):
        return NUM_ERROR
    fraction = _year_fraction(purchase_date, first_date, basis_value)
    return cost_value, salvage_value, math.trunc(period_value), rate_value, fraction


@register(
    "AMORLINC",
    min_args=6,
    max_args=7,
    argument_spec="cost, date_purchased, first_period, salvage, period, rate, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def amorlinc(
    context: Any,
    cost: Any,
    purchased: Any,
    first_period: Any,
    salvage: Any,
    period: Any,
    rate: Any,
    basis: Any = 0,
) -> Any:
    """Return French linear depreciation for an accounting period."""
    inputs = _depreciation_inputs(context, cost, purchased, first_period, salvage, period, rate, basis)
    if is_error(inputs):
        return inputs
    cost_value, salvage_value, period_value, rate_value, fraction = inputs
    one_rate = cost_value * rate_value
    first_rate = fraction * rate_value * cost_value
    full_periods = int((cost_value - salvage_value - first_rate) / one_rate)
    if period_value == 0:
        return first_rate
    if period_value <= full_periods:
        return one_rate
    if period_value == full_periods + 1:
        return cost_value - salvage_value - one_rate * full_periods - first_rate
    return 0.0


@register(
    "AMORDEGRC",
    min_args=6,
    max_args=7,
    argument_spec="cost, date_purchased, first_period, salvage, period, rate, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def amordegrc(
    context: Any,
    cost: Any,
    purchased: Any,
    first_period: Any,
    salvage: Any,
    period: Any,
    rate: Any,
    basis: Any = 0,
) -> Any:
    """Return French declining depreciation using a life-based coefficient."""
    inputs = _depreciation_inputs(context, cost, purchased, first_period, salvage, period, rate, basis)
    if is_error(inputs):
        return inputs
    cost_value, salvage_value, period_value, rate_value, fraction = inputs
    life = 1 / rate_value
    if life < 3:
        coefficient = 1.0
    elif life < 5:
        coefficient = 1.5
    elif life <= 6:
        coefficient = 2.0
    else:
        coefficient = 2.5
    rate_value *= coefficient
    depreciation = float(round(fraction * rate_value * cost_value))
    cost_value -= depreciation
    rest = cost_value - salvage_value
    for index in range(period_value):
        depreciation = float(round(rate_value * cost_value))
        rest -= depreciation
        if rest < 0:
            return float(round(cost_value * 0.5)) if period_value - index <= 1 else 0.0
        cost_value -= depreciation
    return depreciation


# ---------------------------------------------------------- odd periods
def _period_length(start: date, end: date, frequency: int, basis: int) -> float:
    if basis in (0, 2, 4):
        return 360 / frequency
    if basis == 3:
        return 365 / frequency
    return float((end - start).days)


def _odd_inputs(
    context: Any,
    dates: tuple[Any, ...],
    numbers: tuple[Any, ...],
    frequency: Any,
    basis: Any,
) -> Any:
    converted_dates = _dates(context, *dates)
    converted_numbers = _numbers(context, *numbers)
    frequency_value = _validated_frequency(context, frequency)
    basis_value = _validated_basis(context, 0 if basis is None else basis)
    for item in (converted_dates, converted_numbers, frequency_value, basis_value):
        if is_error(item):
            return item
    return converted_dates, converted_numbers, frequency_value, basis_value


def _oddf_price(
    settlement: date,
    maturity: date,
    issue: date,
    first_coupon: date,
    rate: float,
    yld: float,
    redemption: float,
    frequency: int,
    basis: int,
) -> float:
    months = 12 // frequency
    coupon = 100 * rate / frequency
    # Quasi-coupon periods counting back from the first coupon to before issue.
    boundaries = [first_coupon]
    while boundaries[-1] > issue:
        boundaries.append(_coupon_shift(first_coupon, -months * len(boundaries)))
    boundaries.reverse()
    odd_coupon = 0.0
    accrued = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        normal = _period_length(start, end, frequency, basis)
        counted_start = max(start, issue)
        odd_coupon += _days_between(counted_start, end, basis) / normal
        if settlement > counted_start:
            accrued += _days_between(counted_start, min(settlement, end), basis) / normal
    # Time from settlement to the first coupon, in coupon periods.
    periods_to_first = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        if end <= settlement:
            continue
        normal = _period_length(start, end, frequency, basis)
        periods_to_first += _days_between(max(start, settlement), end, basis) / normal
    regular = 0
    current = first_coupon
    while current < maturity:
        regular += 1
        current = _coupon_shift(first_coupon, months * regular)
    discount = 1 + yld / frequency
    present = coupon * odd_coupon / discount**periods_to_first
    for index in range(1, regular + 1):
        present += coupon / discount ** (periods_to_first + index)
    present += redemption / discount ** (periods_to_first + regular)
    return present - coupon * accrued


def _oddl_terms(
    settlement: date,
    maturity: date,
    last_interest: date,
    frequency: int,
    basis: int,
) -> tuple[float, float, float]:
    months = 12 // frequency
    boundaries = [last_interest]
    while boundaries[-1] < maturity:
        boundaries.append(_coupon_shift(last_interest, months * len(boundaries)))
    counted = accrued = remaining = 0.0
    for start, end in zip(boundaries, boundaries[1:]):
        normal = _period_length(start, end, frequency, basis)
        stop = min(end, maturity)
        counted += _days_between(start, stop, basis) / normal
        if settlement > start:
            accrued += _days_between(start, min(settlement, stop), basis) / normal
        if settlement < stop:
            remaining += _days_between(max(start, settlement), stop, basis) / normal
    return counted, accrued, remaining


def _solve_yield(price_function: Any, target: float) -> Any:
    low, high = -0.99, 1.0
    for _ in range(200):
        if price_function(high) < target:
            break
        high *= 2
        if high > 1e6:
            return NUM_ERROR
    f_low = price_function(low) - target
    for _ in range(300):
        middle = (low + high) / 2
        f_middle = price_function(middle) - target
        if abs(f_middle) < 1e-12 or high - low < 1e-14:
            return middle
        if (f_middle > 0) == (f_low > 0):
            low, f_low = middle, f_middle
        else:
            high = middle
    return (low + high) / 2


@register(
    "ODDFPRICE",
    min_args=8,
    max_args=9,
    argument_spec="settlement, maturity, issue, first_coupon, rate, yld, redemption, frequency, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def oddfprice(
    context: Any,
    settlement: Any,
    maturity: Any,
    issue: Any,
    first_coupon: Any,
    rate: Any,
    yld: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the price per $100 of a security with an odd first period."""
    inputs = _odd_inputs(
        context,
        (settlement, maturity, issue, first_coupon),
        (rate, yld, redemption),
        frequency,
        basis,
    )
    if is_error(inputs):
        return inputs
    (settle, mature, issued, first), (rate_value, yield_value, redeem), frequency_value, basis_value = inputs
    if not issued < settle < first < mature or rate_value < 0 or yield_value < 0 or redeem <= 0:
        return NUM_ERROR
    return _oddf_price(settle, mature, issued, first, rate_value, yield_value, redeem, frequency_value, basis_value)


@register(
    "ODDFYIELD",
    min_args=8,
    max_args=9,
    argument_spec="settlement, maturity, issue, first_coupon, rate, pr, redemption, frequency, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def oddfyield(
    context: Any,
    settlement: Any,
    maturity: Any,
    issue: Any,
    first_coupon: Any,
    rate: Any,
    price: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the yield of a security with an odd first period."""
    inputs = _odd_inputs(
        context,
        (settlement, maturity, issue, first_coupon),
        (rate, price, redemption),
        frequency,
        basis,
    )
    if is_error(inputs):
        return inputs
    (settle, mature, issued, first), (rate_value, price_value, redeem), frequency_value, basis_value = inputs
    if not issued < settle < first < mature or rate_value < 0 or price_value <= 0 or redeem <= 0:
        return NUM_ERROR
    return _solve_yield(
        lambda y: _oddf_price(settle, mature, issued, first, rate_value, y, redeem, frequency_value, basis_value),
        price_value,
    )


@register(
    "ODDLPRICE",
    min_args=7,
    max_args=8,
    argument_spec="settlement, maturity, last_interest, rate, yld, redemption, frequency, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def oddlprice(
    context: Any,
    settlement: Any,
    maturity: Any,
    last_interest: Any,
    rate: Any,
    yld: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the price per $100 of a security with an odd last period."""
    inputs = _odd_inputs(
        context,
        (settlement, maturity, last_interest),
        (rate, yld, redemption),
        frequency,
        basis,
    )
    if is_error(inputs):
        return inputs
    (settle, mature, last), (rate_value, yield_value, redeem), frequency_value, basis_value = inputs
    if not last < settle < mature or rate_value < 0 or yield_value < 0 or redeem <= 0:
        return NUM_ERROR
    counted, accrued, remaining = _oddl_terms(settle, mature, last, frequency_value, basis_value)
    coupon = 100 * rate_value / frequency_value
    return (redeem + counted * coupon) / (1 + remaining * yield_value / frequency_value) - accrued * coupon


@register(
    "ODDLYIELD",
    min_args=7,
    max_args=8,
    argument_spec="settlement, maturity, last_interest, rate, pr, redemption, frequency, [basis]",
    lift=lift_all,
    category=FINANCE,
)
def oddlyield(
    context: Any,
    settlement: Any,
    maturity: Any,
    last_interest: Any,
    rate: Any,
    price: Any,
    redemption: Any,
    frequency: Any,
    basis: Any = 0,
) -> Any:
    """Return the yield of a security with an odd last period."""
    inputs = _odd_inputs(
        context,
        (settlement, maturity, last_interest),
        (rate, price, redemption),
        frequency,
        basis,
    )
    if is_error(inputs):
        return inputs
    (settle, mature, last), (rate_value, price_value, redeem), frequency_value, basis_value = inputs
    if not last < settle < mature or rate_value < 0 or price_value <= 0 or redeem <= 0:
        return NUM_ERROR
    counted, accrued, remaining = _oddl_terms(settle, mature, last, frequency_value, basis_value)
    coupon = 100 * rate_value / frequency_value
    dirty = price_value + accrued * coupon
    if remaining == 0:
        return NUM_ERROR
    return (redeem + counted * coupon - dirty) / dirty * frequency_value / remaining
