"""Shared formula-function coercion, criteria, matrix, and date helpers."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from duddysheet.core.errors import VALUE_ERROR, SpreadsheetError, is_error
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.values import parse_number_text, to_text


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
        if not value.strip() and blank_as_zero:
            return 0
        parsed = parse_number_text(value)
        return VALUE_ERROR if parsed is None else parsed
    return VALUE_ERROR


def numeric_values(
    context: Any,
    *arguments: Any,
    ignore_non_numeric: bool = True,
) -> list[int | float] | SpreadsheetError:
    """Collect numbers with Excel's aggregate rules.

    Values inside references and arrays count only when they are numbers or
    dates; logicals, text, and blanks there are skipped. Arguments typed
    directly are coerced, so ``SUM("3", TRUE)`` is 4 and ``SUM("x")`` is
    #VALUE!. Errors anywhere propagate.
    """
    del ignore_non_numeric  # retained for callers; Excel's rules are uniform
    result: list[int | float] = []
    for argument in arguments:
        if is_collection(argument):
            for value in context.values(argument):
                if is_error(value):
                    return value
                if isinstance(value, bool) or value is None or isinstance(value, str):
                    continue
                if isinstance(value, (int, float)):
                    result.append(value)
                elif isinstance(value, (date, datetime)):
                    result.append(_date_to_serial(value))
            continue
        value = context.scalar(argument)
        converted = number(value)
        if is_error(converted):
            return converted
        result.append(converted)
    return result


def is_collection(value: Any) -> bool:
    """Return whether a function argument is a reference or array."""
    return isinstance(value, tuple) or hasattr(value, "areas")


def a_values(context: Any, *arguments: Any) -> list[int | float] | SpreadsheetError:
    """Collect values for the A-suffixed functions (AVERAGEA, MAXA, ...).

    In references, text counts as 0 and logicals as 1 or 0; blanks are skipped.
    """
    result: list[int | float] = []
    for argument in arguments:
        if is_collection(argument):
            for value in context.values(argument):
                if is_error(value):
                    return value
                if value is None:
                    continue
                if isinstance(value, bool):
                    result.append(int(value))
                elif isinstance(value, str):
                    result.append(0)
                elif isinstance(value, (int, float)):
                    result.append(value)
                elif isinstance(value, (date, datetime)):
                    result.append(_date_to_serial(value))
            continue
        converted = number(context.scalar(argument))
        if is_error(converted):
            return converted
        result.append(converted)
    return result


def text(value: Any) -> str:
    """Coerce a scalar to text with Excel's 15-significant-digit General rule."""
    return to_text(value)


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
    to_matrix = getattr(context, "matrix", None)
    if to_matrix is not None:
        areas = getattr(value, "areas", None)
        if areas and len(areas) > 1:
            value = type(value)((areas[0],))
        return to_matrix(value)
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


_CRITERION_RE = re.compile(r"^(<=|>=|<>|=|<|>)(.*)$", re.DOTALL)


def parse_criterion(criterion: Any) -> tuple[str, Any, bool]:
    """Split a criterion into (operator, typed operand, uses_wildcards)."""
    if is_error(criterion):
        return "=", criterion, False
    if criterion is None:
        return "=", 0, False
    if not isinstance(criterion, str):
        return "=", criterion, False
    match = _CRITERION_RE.match(criterion)
    operator, operand_text = match.groups() if match else ("=", criterion)
    if operand_text == "":
        return operator, "", False
    upper = operand_text.strip().upper()
    if upper in ("TRUE", "FALSE"):
        return operator, upper == "TRUE", False
    if upper.startswith("#"):
        from duddysheet.core.errors import ERRORS_BY_LITERAL

        if upper in ERRORS_BY_LITERAL:
            return operator, ERRORS_BY_LITERAL[upper], False
    parsed = parse_number_text(operand_text)
    if parsed is not None:
        return operator, parsed, False
    wildcard = operator in ("=", "<>") and any(
        character in operand_text for character in "*?"
    )
    return operator, operand_text, wildcard


def _wildcard_pattern(operand: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(operand):
        character = operand[index]
        if character == "~" and index + 1 < len(operand) and operand[index + 1] in "*?~":
            parts.append(re.escape(operand[index + 1]))
            index += 2
            continue
        if character == "*":
            parts.append(".*")
        elif character == "?":
            parts.append(".")
        else:
            parts.append(re.escape(character))
        index += 1
    return re.compile("".join(parts), re.IGNORECASE | re.DOTALL)


def _ordering(operator: str, difference: int) -> bool:
    if operator == "=":
        return difference == 0
    if operator == "<>":
        return difference != 0
    if operator == "<":
        return difference < 0
    if operator == ">":
        return difference > 0
    if operator == "<=":
        return difference <= 0
    return difference >= 0


def criteria_match(value: Any, criterion: Any) -> bool:
    """Apply an Excel criterion as COUNTIF, SUMIF, and AVERAGEIF do.

    Blank cells match only ``""``, ``"="``, and not-equal criteria; numeric
    criteria match numbers and numeric text; wildcards apply only to text;
    logical criteria match only logicals.
    """
    operator, operand, wildcard = parse_criterion(criterion)
    if isinstance(operand, SpreadsheetError):
        if operator == "=":
            return value == operand
        if operator == "<>":
            return value != operand
        return False
    if is_error(value):
        return operator == "<>"
    if isinstance(value, (date, datetime)):
        value = _date_to_serial(value)
    if operand == "" and isinstance(operand, str):
        blank = value is None or value == ""
        if operator == "=":
            return blank
        if operator == "<>":
            return not blank
        return False
    if value is None:
        return operator == "<>"
    if wildcard:
        if not isinstance(value, str):
            return operator == "<>"
        matched = _wildcard_pattern(operand).fullmatch(value) is not None
        return matched if operator == "=" else not matched
    if isinstance(operand, bool):
        if not isinstance(value, bool):
            return operator == "<>"
        return _ordering(operator, int(value) - int(operand))
    if isinstance(operand, (int, float)):
        if isinstance(value, bool):
            return operator == "<>"
        if isinstance(value, str):
            if operator not in ("=", "<>"):
                return False
            parsed = parse_number_text(value)
            if parsed is None:
                return operator == "<>"
            value = parsed
        left, right = float(value), float(operand)
        return _ordering(operator, (left > right) - (left < right))
    if not isinstance(value, str):
        return operator == "<>"
    left_text, right_text = value.casefold(), str(operand).casefold()
    return _ordering(operator, (left_text > right_text) - (left_text < right_text))


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
