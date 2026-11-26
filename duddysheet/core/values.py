"""Excel's scalar coercion and comparison rules.

These primitives define how operators and functions convert between
numbers, text, logicals, blanks, and dates. They are shared by the evaluator
and the function library so that ``="10"+1``, ``=1&""``, and ``="a"<1`` agree
everywhere.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, time
from typing import Any

from dateutil import parser as date_parser

from duddysheet.core.errors import (
    DIV_ZERO_ERROR,
    NUM_ERROR,
    VALUE_ERROR,
    SpreadsheetError,
    is_error,
)

_PLAIN_NUMBER_RE = re.compile(
    r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.\d*)?(?:[eE][+-]?\d+)?$"
)
_DATE_HINT_RE = re.compile(
    r"[/:-]|\d\s*[ap]m?$|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
_MIXED_FRACTION_RE = re.compile(r"^([+-]?)(\d+)\s+(\d+)/(\d+)$")
_TIME_ONLY_RE = re.compile(
    r"^\d{1,2}(?::\d{1,2}(?::\d{1,2}(?:\.\d+)?)?)?\s*(?:[AaPp][Mm]?)?$"
)
_EPOCH = date(1899, 12, 31)
_MAX_FLOAT = 1.7976931348623157e308


def date_serial(value: date | datetime) -> float:
    """Convert a date or datetime to an Excel 1900-system serial."""
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
    serial = (day - _EPOCH).days
    if day >= date(1900, 3, 1):
        serial += 1
    return serial + fraction


def number_text(value: float | int) -> str:
    """Render a number the way Excel converts it to text: 15 significant digits."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        if abs(value) < 10**15:
            return str(value)
        value = float(value)
    if not math.isfinite(value):
        return NUM_ERROR.literal
    if value == 0:
        return "0"
    rounded = float(f"{value:.15g}")
    exponent = math.floor(math.log10(abs(rounded)))
    if exponent >= 15 or exponent < -9:
        mantissa, _, power = f"{rounded:.14E}".partition("E")
        mantissa = mantissa.rstrip("0").rstrip(".")
        sign = "-" if power.startswith("-") else "+"
        digits = power.lstrip("+-").lstrip("0") or "0"
        return f"{mantissa}E{sign}{digits.zfill(2)}"
    decimals = max(0, 14 - exponent)
    rendered = f"{rounded:.{decimals}f}"
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in ("-0", "") else rendered


def to_text(value: Any) -> str:
    """Coerce a scalar to text using Excel's General conversion."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return number_text(value)
    if isinstance(value, (date, datetime)):
        return number_text(date_serial(value))
    if isinstance(value, SpreadsheetError):
        return value.literal
    return str(value)


def parse_number_text(source: str) -> int | float | None:
    """Parse text the way Excel coerces it in arithmetic, or return ``None``.

    Accepts plain and grouped numbers, currency symbols, percentages,
    accounting parentheses, mixed fractions, and date or time text.
    """
    text = source.strip()
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    sign = ""
    if text[:1] in "+-":
        sign, text = text[0], text[1:].strip()
    if text[:1] in "$£€¥":
        text = text[1:].strip()
        if not sign and text[:1] in "+-":
            sign, text = text[0], text[1:].strip()
    candidate = sign + text
    result: int | float | None = None
    if candidate and _PLAIN_NUMBER_RE.match(candidate) and any(
        character.isdigit() for character in candidate
    ):
        normalized = candidate.replace(",", "")
        try:
            result = (
                float(normalized)
                if any(character in normalized for character in ".eE")
                else int(normalized)
            )
        except ValueError:
            result = None
    if result is None:
        fraction = _MIXED_FRACTION_RE.match(candidate)
        if fraction and int(fraction.group(4)):
            whole = int(fraction.group(2)) + int(fraction.group(3)) / int(
                fraction.group(4)
            )
            result = -whole if fraction.group(1) == "-" else whole
    if result is None and not percent and not negative:
        result = parse_date_text(source)
    if result is None:
        return None
    if percent:
        result = result / 100
    return -result if negative else result


def parse_date_text(source: str) -> float | None:
    """Return the serial of date or time text, or ``None`` when it is not one."""
    text = source.strip()
    if not text or not _DATE_HINT_RE.search(text):
        return None
    try:
        parsed = date_parser.parse(
            text,
            default=datetime.combine(date.today(), time()),
        )
    except (ValueError, OverflowError):
        return None
    if _TIME_ONLY_RE.match(text):
        return (
            parsed.hour * 3600
            + parsed.minute * 60
            + parsed.second
            + parsed.microsecond / 1_000_000
        ) / 86_400
    if parsed.year < 1900 or parsed.year > 9999:
        return None
    return date_serial(parsed)


def to_number(value: Any) -> int | float | SpreadsheetError:
    """Coerce a scalar for arithmetic: blanks are 0 and numeric text converts."""
    if isinstance(value, SpreadsheetError):
        return value
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (date, datetime)):
        return date_serial(value)
    if isinstance(value, str):
        parsed = parse_number_text(value)
        return VALUE_ERROR if parsed is None else parsed
    return VALUE_ERROR


def _type_rank(value: Any) -> int:
    if isinstance(value, bool):
        return 2
    if isinstance(value, str):
        return 1
    return 0


def _blank_for(other: Any) -> Any:
    if isinstance(other, bool):
        return False
    if isinstance(other, str):
        return ""
    return 0


def compare(left: Any, right: Any, operator: str) -> bool | SpreadsheetError:
    """Compare two scalars with Excel's ordering: numbers < text < logicals."""
    if is_error(left):
        return left
    if is_error(right):
        return right
    if left is None and right is None:
        left = right = 0
    elif left is None:
        left = _blank_for(right)
    elif right is None:
        right = _blank_for(left)
    if isinstance(left, (date, datetime)):
        left = date_serial(left)
    if isinstance(right, (date, datetime)):
        right = date_serial(right)
    left_rank = _type_rank(left)
    right_rank = _type_rank(right)
    if left_rank != right_rank:
        ordering = (left_rank > right_rank) - (left_rank < right_rank)
    elif left_rank == 1:
        folded_left = left.casefold()
        folded_right = right.casefold()
        ordering = (folded_left > folded_right) - (folded_left < folded_right)
    else:
        numeric_left = float(left)
        numeric_right = float(right)
        ordering = (numeric_left > numeric_right) - (numeric_left < numeric_right)
    if operator == "=":
        return ordering == 0
    if operator == "<>":
        return ordering != 0
    if operator == "<":
        return ordering < 0
    if operator == ">":
        return ordering > 0
    if operator == "<=":
        return ordering <= 0
    return ordering >= 0


def arithmetic(operator: str, left: Any, right: Any) -> Any:
    """Apply an arithmetic, concatenation, or comparison operator to scalars."""
    left_type = type(left)
    right_type = type(right)
    if (left_type is int or left_type is float) and (right_type is int or right_type is float):
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        elif operator == "/":
            if right == 0:
                return DIV_ZERO_ERROR
            result = left / right
        else:
            result = None
        if result is not None:
            if result.__class__ is float and not math.isfinite(result):
                return NUM_ERROR
            return result
    if is_error(left):
        return left
    if is_error(right):
        return right
    if operator == "&":
        return to_text(left) + to_text(right)
    if operator in ("=", "<>", "<", ">", "<=", ">="):
        return compare(left, right, operator)
    left_number = to_number(left)
    if is_error(left_number):
        return left_number
    right_number = to_number(right)
    if is_error(right_number):
        return right_number
    try:
        if operator == "+":
            result = left_number + right_number
        elif operator == "-":
            result = left_number - right_number
        elif operator == "*":
            result = left_number * right_number
        elif operator == "/":
            if right_number == 0:
                return DIV_ZERO_ERROR
            result = left_number / right_number
        elif operator == "^":
            if left_number == 0 and right_number == 0:
                return NUM_ERROR
            if left_number == 0 and right_number < 0:
                return DIV_ZERO_ERROR
            if left_number < 0 and not float(right_number).is_integer():
                reciprocal = 1 / right_number
                if abs(reciprocal - round(reciprocal)) > 1e-9 or round(reciprocal) % 2 == 0:
                    return NUM_ERROR
                result = -(abs(left_number) ** right_number)
            else:
                result = left_number**right_number
            if isinstance(result, complex):
                return NUM_ERROR
        else:
            return VALUE_ERROR
    except OverflowError:
        return NUM_ERROR
    except ZeroDivisionError:
        return DIV_ZERO_ERROR
    if isinstance(result, float) and not math.isfinite(result):
        return NUM_ERROR
    if isinstance(result, int) and abs(result) > _MAX_FLOAT:
        return NUM_ERROR
    return result
