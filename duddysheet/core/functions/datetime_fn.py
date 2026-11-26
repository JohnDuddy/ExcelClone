"""Date and time worksheet functions."""

from __future__ import annotations

import calendar
import math
from datetime import date, datetime, timedelta
from typing import Any

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from duddysheet.core.errors import NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import (
    flatten,
    number,
    scalar,
    serial_datetime,
    text,
)


def _serial(value: date | datetime) -> float:
    converted = number(value)
    assert not is_error(converted)
    return float(converted)


@register("TODAY", max_args=0, volatile=True, argument_spec="")
def today(context: Any) -> float:
    """Return today's local date as an Excel serial."""
    return _serial(date.today())


@register("NOW", max_args=0, volatile=True, argument_spec="")
def now(context: Any) -> float:
    """Return the current local date and time as an Excel serial."""
    return _serial(datetime.now())


@register("DATE", min_args=3, max_args=3, argument_spec="year, month, day")
def date_function(context: Any, year: Any, month: Any, day: Any) -> Any:
    """Construct a date serial while allowing month and day overflow."""
    selected = [number(scalar(context, value)) for value in (year, month, day)]
    if any(is_error(value) for value in selected):
        return VALUE_ERROR
    year_value, month_value, day_value = (int(value) for value in selected)
    if 0 <= year_value <= 1899:
        year_value += 1900
    if year_value < 0 or year_value > 9999:
        return NUM_ERROR
    try:
        base = datetime(year_value, 1, 1) + relativedelta(months=month_value - 1)
        result = base + timedelta(days=day_value - 1)
    except (OverflowError, ValueError):
        return NUM_ERROR
    return _serial(result)


@register("TIME", min_args=3, max_args=3, argument_spec="hour, minute, second")
def time_function(context: Any, hour: Any, minute: Any, second: Any) -> Any:
    """Construct a fractional-day time serial."""
    selected = [number(scalar(context, value)) for value in (hour, minute, second)]
    if any(is_error(value) or value < 0 for value in selected):
        return NUM_ERROR
    total_seconds = sum(
        int(value) * factor for value, factor in zip(selected, (3600, 60, 1))
    )
    return (total_seconds % 86_400) / 86_400


def _parse_datetime(context: Any, value: Any) -> Any:
    selected = scalar(context, value)
    if isinstance(selected, (date, datetime)):
        return (
            selected
            if isinstance(selected, datetime)
            else datetime.combine(selected, datetime.min.time())
        )
    if isinstance(selected, (int, float)):
        return serial_datetime(selected)
    try:
        return date_parser.parse(text(selected))
    except (ValueError, OverflowError):
        return VALUE_ERROR


@register("DATEVALUE", min_args=1, max_args=1, argument_spec="date_text")
def datevalue(context: Any, value: Any) -> Any:
    """Convert date text into a whole-day serial."""
    selected = _parse_datetime(context, value)
    return selected if is_error(selected) else math.floor(_serial(selected))


@register("TIMEVALUE", min_args=1, max_args=1, argument_spec="time_text")
def timevalue(context: Any, value: Any) -> Any:
    """Convert time text into a fractional-day serial."""
    selected = _parse_datetime(context, value)
    if is_error(selected):
        return selected
    return (
        selected.hour * 3600
        + selected.minute * 60
        + selected.second
        + selected.microsecond / 1_000_000
    ) / 86_400


def _date_part(context: Any, value: Any, attribute: str) -> Any:
    selected = serial_datetime(scalar(context, value))
    return selected if is_error(selected) else getattr(selected, attribute)


@register("YEAR", min_args=1, max_args=1, argument_spec="serial_number")
def year(context: Any, value: Any) -> Any:
    """Return the year of a date serial."""
    return _date_part(context, value, "year")


@register("MONTH", min_args=1, max_args=1, argument_spec="serial_number")
def month(context: Any, value: Any) -> Any:
    """Return the month number of a date serial."""
    return _date_part(context, value, "month")


@register("DAY", min_args=1, max_args=1, argument_spec="serial_number")
def day(context: Any, value: Any) -> Any:
    """Return the day of month of a date serial."""
    return _date_part(context, value, "day")


@register("HOUR", min_args=1, max_args=1, argument_spec="serial_number")
def hour(context: Any, value: Any) -> Any:
    """Return the hour of a time serial."""
    return _date_part(context, value, "hour")


@register("MINUTE", min_args=1, max_args=1, argument_spec="serial_number")
def minute(context: Any, value: Any) -> Any:
    """Return the minute of a time serial."""
    return _date_part(context, value, "minute")


@register("SECOND", min_args=1, max_args=1, argument_spec="serial_number")
def second(context: Any, value: Any) -> Any:
    """Return the second of a time serial."""
    return _date_part(context, value, "second")


@register("WEEKDAY", min_args=1, max_args=2, argument_spec="serial_number, [return_type]")
def weekday(context: Any, value: Any, return_type: Any = 1) -> Any:
    """Return a weekday number using a selected numbering convention."""
    selected = serial_datetime(scalar(context, value))
    selected_type = number(scalar(context, return_type))
    if is_error(selected) or is_error(selected_type):
        return VALUE_ERROR
    monday_zero = selected.weekday()
    selected_type = int(selected_type)
    if selected_type == 1:
        return (monday_zero + 1) % 7 + 1
    if selected_type == 2:
        return monday_zero + 1
    if selected_type == 3:
        return monday_zero
    if 11 <= selected_type <= 17:
        start = selected_type - 11
        return (monday_zero - start) % 7 + 1
    return NUM_ERROR


@register("WEEKNUM", min_args=1, max_args=2, argument_spec="serial_number, [return_type]")
def weeknum(context: Any, value: Any, return_type: Any = 1) -> Any:
    """Return a week number for a date serial."""
    selected = serial_datetime(scalar(context, value))
    selected_type = number(scalar(context, return_type))
    if is_error(selected) or is_error(selected_type):
        return VALUE_ERROR
    if int(selected_type) == 21:
        return selected.isocalendar().week
    start_monday = int(selected_type) == 2
    directive = "%W" if start_monday else "%U"
    return int(selected.strftime(directive)) + 1


def _shift_months(context: Any, start: Any, months: Any, *, end: bool) -> Any:
    selected = serial_datetime(scalar(context, start))
    month_count = number(scalar(context, months))
    if is_error(selected) or is_error(month_count):
        return VALUE_ERROR
    shifted = selected + relativedelta(months=int(month_count))
    if end:
        shifted = shifted.replace(
            day=calendar.monthrange(shifted.year, shifted.month)[1]
        )
    return math.floor(_serial(shifted))


@register("EOMONTH", min_args=2, max_args=2, argument_spec="start_date, months")
def eomonth(context: Any, start: Any, months: Any) -> Any:
    """Return the final day of a shifted month."""
    selected = serial_datetime(scalar(context, start))
    month_count = number(scalar(context, months))
    if is_error(selected) or is_error(month_count):
        return VALUE_ERROR
    first = selected.replace(day=1) + relativedelta(months=int(month_count) + 1)
    return math.floor(_serial(first - timedelta(days=1)))


@register("EDATE", min_args=2, max_args=2, argument_spec="start_date, months")
def edate(context: Any, start: Any, months: Any) -> Any:
    """Return a date shifted by whole months."""
    return _shift_months(context, start, months, end=False)


@register("DAYS", min_args=2, max_args=2, argument_spec="end_date, start_date")
def days(context: Any, end: Any, start: Any) -> Any:
    """Return whole days between two dates."""
    end_date = serial_datetime(scalar(context, end))
    start_date = serial_datetime(scalar(context, start))
    if is_error(end_date) or is_error(start_date):
        return VALUE_ERROR
    return (end_date.date() - start_date.date()).days


@register("DATEDIF", min_args=3, max_args=3, argument_spec="start_date, end_date, unit")
def datedif(context: Any, start: Any, end: Any, unit: Any) -> Any:
    """Return a completed date interval in a selected unit."""
    start_date = serial_datetime(scalar(context, start))
    end_date = serial_datetime(scalar(context, end))
    selected_unit = text(scalar(context, unit)).upper()
    if is_error(start_date) or is_error(end_date):
        return VALUE_ERROR
    if end_date < start_date:
        return NUM_ERROR
    delta = relativedelta(end_date.date(), start_date.date())
    if selected_unit == "Y":
        return delta.years
    if selected_unit == "M":
        return delta.years * 12 + delta.months
    if selected_unit == "D":
        return (end_date.date() - start_date.date()).days
    if selected_unit == "YM":
        return delta.months
    if selected_unit == "MD":
        return delta.days
    if selected_unit == "YD":
        anniversary = start_date.replace(year=end_date.year)
        if anniversary > end_date:
            anniversary = anniversary.replace(year=end_date.year - 1)
        return (end_date.date() - anniversary.date()).days
    return NUM_ERROR


def _holiday_dates(context: Any, holidays: Any) -> set[date]:
    if holidays is None:
        return set()
    selected: set[date] = set()
    for value in flatten(context, holidays):
        if value is None or value == "":
            continue
        converted = serial_datetime(value)
        if is_error(converted):
            # Excel rejects a holiday that is not a date.
            return VALUE_ERROR
        selected.add(converted.date())
    return selected


@register(
    "NETWORKDAYS",
    min_args=2,
    max_args=3,
    argument_spec="start_date, end_date, [holidays]",
)
def networkdays(
    context: Any,
    start: Any,
    end: Any,
    holidays: Any = None,
) -> Any:
    """Count weekdays between inclusive dates excluding holidays."""
    start_date = serial_datetime(scalar(context, start))
    end_date = serial_datetime(scalar(context, end))
    if is_error(start_date) or is_error(end_date):
        return VALUE_ERROR
    sign = 1 if end_date >= start_date else -1
    holiday_set = _holiday_dates(context, holidays)
    if is_error(holiday_set):
        return holiday_set
    current = start_date.date()
    target = end_date.date()
    count_value = 0
    while True:
        if current.weekday() < 5 and current not in holiday_set:
            count_value += sign
        if current == target:
            break
        current += timedelta(days=sign)
    return count_value


@register(
    "WORKDAY",
    min_args=2,
    max_args=3,
    argument_spec="start_date, days, [holidays]",
)
def workday(
    context: Any,
    start: Any,
    day_count: Any,
    holidays: Any = None,
) -> Any:
    """Shift a date by a number of working days."""
    selected = serial_datetime(scalar(context, start))
    count_value = number(scalar(context, day_count))
    if is_error(selected) or is_error(count_value):
        return VALUE_ERROR
    remaining = abs(int(count_value))
    direction = 1 if count_value >= 0 else -1
    current = selected.date()
    holiday_set = _holiday_dates(context, holidays)
    if is_error(holiday_set):
        return holiday_set
    while remaining:
        current += timedelta(days=direction)
        if current.weekday() < 5 and current not in holiday_set:
            remaining -= 1
    return math.floor(_serial(current))


@register("YEARFRAC", min_args=2, max_args=3, argument_spec="start_date, end_date, [basis]")
def yearfrac(context: Any, start: Any, end: Any, basis: Any = 0) -> Any:
    """Return the fraction of a year between dates."""
    start_date = serial_datetime(scalar(context, start))
    end_date = serial_datetime(scalar(context, end))
    selected_basis = number(scalar(context, basis))
    if is_error(start_date) or is_error(end_date) or is_error(selected_basis):
        return VALUE_ERROR
    day_difference = (end_date.date() - start_date.date()).days
    basis_value = int(selected_basis)
    if basis_value == 0:
        d1 = min(start_date.day, 30)
        d2 = min(end_date.day, 30) if d1 == 30 else end_date.day
        return (
            (end_date.year - start_date.year) * 360
            + (end_date.month - start_date.month) * 30
            + d2
            - d1
        ) / 360
    if basis_value == 2:
        return day_difference / 360
    if basis_value == 3:
        return day_difference / 365
    if basis_value == 4:
        return day_difference / 360
    if basis_value == 1:
        years = range(start_date.year, end_date.year + 1)
        average_days = sum(366 if calendar.isleap(year_value) else 365 for year_value in years) / len(list(years))
        return day_difference / average_days
    return NUM_ERROR
