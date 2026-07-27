"""Shared formula-function coercion, criteria, matrix, and date helpers."""

from __future__ import annotations

import fnmatch
import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from duddysheet.core.errors import VALUE_ERROR, SpreadsheetError, is_error
from duddysheet.core.refs import CellReference, RangeReference


def scalar(context: Any, value: Any) -> Any:
    """Resolve a function argument to one scalar."""
    return context.scalar(value)


def flatten(context: Any, *arguments: Any) -> list[Any]:
    """Flatten function arguments while preserving blanks and errors."""
    values: list[Any] = []
    for argument in arguments:
        values.extend(context.values(argument))
    return values


def first_error(values: list[Any] | tuple[Any, ...]) -> SpreadsheetError | None:
    """Return the first spreadsheet error in a sequence."""
    return next((value for value in values if is_error(value)), None)


def number(value: Any, *, blank_as_zero: bool = True) -> int | float | SpreadsheetError:
    """Coerce a scalar to an Excel-style number."""
    if is_error(value):
        return value
    if value is None:
        return 0 if blank_as_zero else VALUE_ERROR
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (date, datetime)):
        return _date_to_serial(value)
    if isinstance(value, str):
        normalized = value.strip().replace(",", "")
        if not normalized and blank_as_zero:
            return 0
        try:
            return (
                float(normalized)
                if any(character in normalized for character in ".eE")
                else int(normalized)
            )
        except ValueError:
            return VALUE_ERROR
    return VALUE_ERROR


def numeric_values(
    context: Any,
    *arguments: Any,
    ignore_non_numeric: bool = True,
) -> list[int | float] | SpreadsheetError:
    """Flatten arguments and collect numeric values."""
    values = flatten(context, *arguments)
    error = first_error(values)
    if error is not None:
        return error
    result: list[int | float] = []
    for value in values:
        converted = number(value)
        if is_error(converted):
            if ignore_non_numeric:
                continue
            return converted
        result.append(converted)
    return result


def text(value: Any) -> str:
    """Coerce a scalar to general-display text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def truthy(value: Any) -> bool | SpreadsheetError:
    """Coerce a scalar to logical truth."""
    if is_error(value):
        return value
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        upper = value.strip().upper()
        if upper == "TRUE":
            return True
        if upper == "FALSE":
            return False
    return VALUE_ERROR


def matrix(context: Any, value: Any) -> list[list[Any]]:
    """Convert a scalar, array, or first reference area to a rectangular matrix."""
    if isinstance(value, tuple):
        if value and all(isinstance(row, tuple) for row in value):
            return [list(row) for row in value]
        return [list(value)]
    areas = getattr(value, "areas", None)
    if areas:
        area = areas[0]
        if isinstance(area, CellReference):
            return [[context.scalar(value)]]
        if isinstance(area, RangeReference):
            values = context.values(value)
            width = area.max_column - area.min_column + 1
            return [
                values[index : index + width]
                for index in range(0, len(values), width)
            ]
    return [[context.scalar(value)]]


def rectangular(rows: list[list[Any]]) -> tuple[tuple[Any, ...], ...]:
    """Freeze a matrix as the evaluator's dynamic-array value."""
    return tuple(tuple(row) for row in rows)


def criteria_match(value: Any, criterion: Any) -> bool:
    """Apply an Excel-style comparison or wildcard criterion."""
    if is_error(value) or is_error(criterion):
        return False
    if not isinstance(criterion, str):
        return _equal(value, criterion)
    match = re.match(r"^(<=|>=|<>|=|<|>)(.*)$", criterion)
    if match:
        operator, operand_text = match.groups()
        operand: Any = operand_text
        converted = number(operand_text)
        if not is_error(converted):
            operand = converted
        return _compare(value, operand, operator)
    if any(character in criterion for character in "*?"):
        escaped = criterion.replace("~*", "[*]").replace("~?", "[?]")
        return fnmatch.fnmatchcase(text(value).casefold(), escaped.casefold())
    return _equal(value, criterion)


def _equal(left: Any, right: Any) -> bool:
    left_number = number(left)
    right_number = number(right)
    if not is_error(left_number) and not is_error(right_number):
        return float(left_number) == float(right_number)
    return text(left).casefold() == text(right).casefold()


def _compare(left: Any, right: Any, operator: str) -> bool:
    left_number = number(left)
    right_number = number(right)
    if not is_error(left_number) and not is_error(right_number):
        normalized_left: Any = float(left_number)
        normalized_right: Any = float(right_number)
    else:
        normalized_left = text(left).casefold()
        normalized_right = text(right).casefold()
    if operator == "=":
        return normalized_left == normalized_right
    if operator == "<>":
        return normalized_left != normalized_right
    if operator == "<":
        return normalized_left < normalized_right
    if operator == ">":
        return normalized_left > normalized_right
    if operator == "<=":
        return normalized_left <= normalized_right
    return normalized_left >= normalized_right


def round_away(value: float, digits: int = 0) -> float:
    """Round halves away from zero, matching worksheet ROUND."""
    factor = 10**digits
    scaled = value * factor
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    return rounded / factor


def serial_datetime(value: Any) -> datetime | SpreadsheetError:
    """Convert a date, datetime, or serial number into a datetime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time())
    converted = number(value)
    if is_error(converted):
        return converted
    serial = float(converted)
    whole_days = math.floor(serial)
    fraction = serial - whole_days
    adjusted_days = whole_days - 1 if whole_days >= 60 else whole_days
    return datetime(1899, 12, 31) + timedelta(
        days=adjusted_days,
        seconds=fraction * 86_400,
    )


def clean_number(value: float) -> int | float:
    """Return integral floating results as integers."""
    return int(value) if float(value).is_integer() else value


def _date_to_serial(value: date | datetime) -> float:
    if isinstance(value, datetime):
        day = value.date()
        fraction = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        ) / 86_400
    else:
        day = value
        fraction = 0.0
    serial = (day - date(1899, 12, 31)).days
    if day >= date(1900, 3, 1):
        serial += 1
    return serial + fraction
