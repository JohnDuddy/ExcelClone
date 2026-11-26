"""International workday, ISO week, and 360-day calendar functions."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from duddysheet.core.errors import NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import lift_all, lift_positions, register
from duddysheet.core.functions.common import (
    flatten,
    number,
    scalar,
    serial_datetime,
)
from duddysheet.core.values import date_serial

DATE = "Date & Time"
_WEEKEND_CODES = {
    1: (5, 6),
    2: (6, 0),
    3: (0, 1),
    4: (1, 2),
    5: (2, 3),
    6: (3, 4),
    7: (4, 5),
    11: (6,),
    12: (0,),
    13: (1,),
    14: (2,),
    15: (3,),
    16: (4,),
    17: (5,),
}


def _date_argument(context: Any, value: Any) -> Any:
    selected = scalar(context, value)
    if is_error(selected):
        return selected
    serial = number(selected)
    if not is_error(serial) and serial < 0:
        return NUM_ERROR
    converted = serial_datetime(selected)
    if is_error(converted):
        return converted
    return converted.date()


def _weekend_days(context: Any, weekend: Any) -> Any:
    """Return Python weekday numbers (Monday 0) treated as weekend days."""
    if weekend is None:
        return frozenset((5, 6))
    selected = scalar(context, weekend)
    if is_error(selected):
        return selected
    if isinstance(selected, str):
        if len(selected) != 7 or any(character not in "01" for character in selected):
            return VALUE_ERROR
        if selected == "1111111":
            return VALUE_ERROR
        return frozenset(index for index, character in enumerate(selected) if character == "1")
    code = number(selected)
    if is_error(code):
        return code
    days = _WEEKEND_CODES.get(math.trunc(code))
    if days is None:
        return NUM_ERROR
    return frozenset(days)


def _holidays(context: Any, holidays: Any) -> Any:
    if holidays is None:
        return frozenset()
    dates: set[date] = set()
    for value in flatten(context, holidays):
        if value is None:
            continue
        if is_error(value):
            return value
        converted = serial_datetime(value)
        if is_error(converted):
            return VALUE_ERROR
        dates.add(converted.date())
    return frozenset(dates)


@register(
    "NETWORKDAYS.INTL",
    min_args=2,
    max_args=4,
    argument_spec="start_date, end_date, [weekend], [holidays]",
    lift=lift_positions(0, 1),
    category=DATE,
)
def networkdays_intl(
    context: Any,
    start: Any,
    end: Any,
    weekend: Any = None,
    holidays: Any = None,
) -> Any:
    """Count whole workdays between two dates with a custom weekend."""
    first = _date_argument(context, start)
    last = _date_argument(context, end)
    weekend_days = _weekend_days(context, weekend)
    holiday_set = _holidays(context, holidays)
    for item in (first, last, weekend_days, holiday_set):
        if is_error(item):
            return item
    sign = 1 if last >= first else -1
    low, high = (first, last) if sign == 1 else (last, first)
    total_days = (high - low).days + 1
    full_weeks, remainder = divmod(total_days, 7)
    count = full_weeks * (7 - len(weekend_days))
    for offset in range(remainder):
        if (low + timedelta(days=full_weeks * 7 + offset)).weekday() not in weekend_days:
            count += 1
    for holiday in holiday_set:
        if low <= holiday <= high and holiday.weekday() not in weekend_days:
            count -= 1
    return sign * count


@register(
    "WORKDAY.INTL",
    min_args=2,
    max_args=4,
    argument_spec="start_date, days, [weekend], [holidays]",
    lift=lift_positions(0, 1),
    category=DATE,
)
def workday_intl(
    context: Any,
    start: Any,
    days: Any,
    weekend: Any = None,
    holidays: Any = None,
) -> Any:
    """Return the date a number of workdays away with a custom weekend."""
    current = _date_argument(context, start)
    offset = number(scalar(context, days))
    weekend_days = _weekend_days(context, weekend)
    holiday_set = _holidays(context, holidays)
    for item in (current, offset, weekend_days, holiday_set):
        if is_error(item):
            return item
    remaining = abs(math.trunc(offset))
    step = 1 if offset >= 0 else -1
    guard = 0
    while remaining:
        current += timedelta(days=step)
        guard += 1
        if guard > 10_000_000:
            return NUM_ERROR
        if current.weekday() not in weekend_days and current not in holiday_set:
            remaining -= 1
    if current.year < 1900 or current.year > 9999:
        return NUM_ERROR
    return math.floor(date_serial(current))


@register(
    "ISOWEEKNUM",
    min_args=1,
    max_args=1,
    argument_spec="date",
    lift=lift_all,
    category=DATE,
)
def isoweeknum(context: Any, value: Any) -> Any:
    """Return the ISO 8601 week number of the year for a date."""
    selected = _date_argument(context, value)
    if is_error(selected):
        return selected
    return selected.isocalendar()[1]


@register(
    "DAYS360",
    min_args=2,
    max_args=3,
    argument_spec="start_date, end_date, [method]",
    lift=lift_all,
    category=DATE,
)
def days360(context: Any, start: Any, end: Any, method: Any = False) -> Any:
    """Count days between dates on a 360-day year (US NASD or European)."""
    first = _date_argument(context, start)
    last = _date_argument(context, end)
    if is_error(first):
        return first
    if is_error(last):
        return last
    european = bool(scalar(context, method)) if method is not None else False
    start_day, end_day = first.day, last.day
    if european:
        start_day = min(start_day, 30)
        end_day = min(end_day, 30)
    else:
        start_is_last_feb = first.month == 2 and (first + timedelta(days=1)).month == 3
        if start_is_last_feb or start_day == 31:
            start_day = 30
        if end_day == 31 and start_day >= 30:
            end_day = 30
    return (last.year - first.year) * 360 + (last.month - first.month) * 30 + end_day - start_day
