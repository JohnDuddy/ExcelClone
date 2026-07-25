"""Excel-style number formatting independent of Qt."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from typing import Any


@dataclass(frozen=True, slots=True)
class FormattedValue:
    """Rendered cell text and an optional format-driven foreground color."""

    text: str
    color: str | None = None


_BUILTIN_FORMATS = {
    "General": "General",
    "Number": "#,##0.00",
    "Currency": "$#,##0.00;-$#,##0.00",
    "Accounting": "$ #,##0.00;$ (#,##0.00);$ -",
    "Percentage": "0.00%",
    "Fraction": "# ?/?",
    "Scientific": "0.00E+00",
    "Date": "m/d/yyyy",
    "Time": "h:mm:ss",
    "Text": "@",
}
_COLOR_RE = re.compile(r"^\[([A-Za-z]+)\]")
_QUOTED_RE = re.compile(r'"((?:[^"]|"")*)"')
_PLACEHOLDER_RE = re.compile(
    r"(?:[0#?]+(?:,[0#?]+)*(?:\.[0#?]*)?|\.[0#?]+),*%?"
)
_ERROR_PREFIX = "#"


def format_value(value: Any, format_code: str = "General") -> FormattedValue:
    """Render a scalar using built-in or custom worksheet format syntax."""
    if value is None:
        return FormattedValue("")
    if isinstance(value, str) and value.startswith(_ERROR_PREFIX):
        return FormattedValue(value)

    selected_code = _BUILTIN_FORMATS.get(format_code, format_code or "General")
    if selected_code == "General":
        return FormattedValue(_general(value))
    if format_code == "Fraction":
        converted = _as_number(value)
        if converted is None:
            return FormattedValue(_general(value))
        fraction = Fraction(converted).limit_denominator(100)
        whole = math.trunc(fraction.numerator / fraction.denominator)
        remainder = abs(fraction.numerator - whole * fraction.denominator)
        sign = "-" if converted < 0 and whole == 0 else ""
        rendered = (
            f"{whole} {remainder}/{fraction.denominator}"
            if whole and remainder
            else f"{sign}{remainder}/{fraction.denominator}"
            if remainder
            else str(whole)
        )
        return FormattedValue(rendered)
    if format_code == "Scientific":
        converted = _as_number(value)
        return FormattedValue(
            _general(value) if converted is None else f"{converted:.2E}"
        )
    if format_code == "Accounting":
        converted = _as_number(value)
        if converted is None:
            return FormattedValue(_general(value))
        if converted == 0:
            return FormattedValue("$ -")
        rendered = f"$ {abs(converted):,.2f}"
        return FormattedValue(f"({rendered})" if converted < 0 else rendered)
    if format_code == "Text":
        return FormattedValue(_general(value))
    if _looks_like_date_or_time(selected_code):
        rendered = _format_date_or_time(value, selected_code)
        if rendered is not None:
            return FormattedValue(rendered)

    section, color, use_absolute = _select_section(value, selected_code)
    if isinstance(value, str):
        return FormattedValue(_format_text_section(value, section), color)
    converted = _as_number(value)
    if converted is None:
        return FormattedValue(_general(value), color)
    return FormattedValue(
        _format_numeric_section(abs(converted) if use_absolute else converted, section),
        color,
    )


def _general(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.15g}"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        day = value.date()
        fraction = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        ) / 86_400
        serial = (day - date(1899, 12, 31)).days
        return serial + (1 if day >= date(1900, 3, 1) else 0) + fraction
    if isinstance(value, date):
        serial = (value - date(1899, 12, 31)).days
        return float(serial + (1 if value >= date(1900, 3, 1) else 0))
    return None


def _split_sections(format_code: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    quoted = False
    for character in format_code:
        if character == '"':
            quoted = not quoted
            current.append(character)
        elif character == ";" and not quoted:
            sections.append("".join(current))
            current = []
        else:
            current.append(character)
    sections.append("".join(current))
    return sections[:4]


def _select_section(value: Any, format_code: str) -> tuple[str, str | None, bool]:
    sections = _split_sections(format_code)
    if isinstance(value, str):
        selected = sections[3] if len(sections) >= 4 else "@"
        index = 3
    else:
        converted = _as_number(value) or 0
        if converted > 0:
            index = 0
        elif converted < 0:
            index = 1 if len(sections) >= 2 else 0
        else:
            index = 2 if len(sections) >= 3 else 0
        selected = sections[min(index, len(sections) - 1)]
    color_match = _COLOR_RE.match(selected)
    color = color_match.group(1).lower() if color_match else None
    if color_match:
        selected = selected[color_match.end() :]
    return selected, color, index == 1 and len(sections) >= 2


def _format_text_section(value: str, section: str) -> str:
    if "@" not in section:
        return value
    return _literal_text(section).replace("@", value)


def _format_numeric_section(value: float, section: str) -> str:
    placeholder = _PLACEHOLDER_RE.search(section)
    if placeholder is None:
        return _literal_text(section)

    pattern = placeholder.group(0)
    prefix = _literal_text(section[: placeholder.start()])
    suffix = _literal_text(section[placeholder.end() :])
    percent = pattern.endswith("%")
    if percent:
        pattern = pattern[:-1]
        value *= 100
        suffix = "%" + suffix

    trailing_commas = len(pattern) - len(pattern.rstrip(","))
    if trailing_commas:
        value /= 1000**trailing_commas
        pattern = pattern[:-trailing_commas]

    integer_pattern, dot, decimal_pattern = pattern.partition(".")
    grouping = "," in integer_pattern
    integer_placeholders = integer_pattern.replace(",", "")
    decimal_count = len(decimal_pattern)
    rendered = (
        f"{value:,.{decimal_count}f}"
        if grouping
        else f"{value:.{decimal_count}f}"
    )
    integer_text, rendered_dot, decimal_text = rendered.partition(".")

    minimum_integer_digits = integer_placeholders.count("0")
    sign = ""
    if integer_text.startswith("-"):
        sign, integer_text = "-", integer_text[1:]
    if len(integer_text.replace(",", "")) < minimum_integer_digits:
        integer_text = integer_text.zfill(
            minimum_integer_digits + integer_text.count(",")
        )
    if integer_text == "0" and "0" not in integer_placeholders:
        integer_text = " " * integer_placeholders.count("?")

    integer_width = len(integer_placeholders)
    if "?" in integer_placeholders and len(integer_text) < integer_width:
        integer_text = " " * (integer_width - len(integer_text)) + integer_text

    if decimal_pattern:
        decimal_characters = list(decimal_text)
        for index in range(len(decimal_characters) - 1, -1, -1):
            placeholder_character = decimal_pattern[index]
            if placeholder_character == "0":
                break
            if decimal_characters[index] != "0":
                break
            decimal_characters[index] = " " if placeholder_character == "?" else ""
        decimal_text = "".join(decimal_characters)
        if not decimal_text and all(character == "#" for character in decimal_pattern):
            rendered_dot = ""
    else:
        rendered_dot = ""
        decimal_text = ""

    return prefix + sign + integer_text + rendered_dot + decimal_text + suffix


def _literal_text(section: str) -> str:
    def replace_quoted(match: re.Match[str]) -> str:
        return match.group(1).replace('""', '"')

    rendered = _QUOTED_RE.sub(replace_quoted, section)
    rendered = re.sub(r"\\(.)", r"\1", rendered)
    rendered = rendered.replace("_", "").replace("*", "")
    return rendered


def _looks_like_date_or_time(format_code: str) -> bool:
    stripped = _QUOTED_RE.sub("", format_code).lower()
    stripped = re.sub(r"\[[^\]]+\]", "", stripped)
    return bool(
        re.search(r"(?:y{2,4}|d{1,4}|h{1,2}|s{1,2}|am/pm)", stripped)
        or (
            "m" in stripped
            and any(separator in stripped for separator in ("/", "-", ":"))
        )
    )


def _format_date_or_time(value: Any, format_code: str) -> str | None:
    converted = _as_number(value)
    if converted is None:
        return None
    lower = format_code.lower()
    if converted == 60 and any(token in lower for token in ("d", "y")):
        return _format_fake_leap_day(lower)
    whole_days = math.floor(converted)
    fraction = converted - whole_days
    adjusted_days = whole_days - 1 if whole_days >= 60 else whole_days
    moment = datetime(1899, 12, 31) + timedelta(
        days=adjusted_days,
        seconds=round(fraction * 86_400),
    )

    month_abbreviation = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )[moment.month - 1]
    presets = {
        "m/d/yyyy": f"{moment.month}/{moment.day}/{moment.year:04d}",
        "mm/dd/yyyy": f"{moment.month:02d}/{moment.day:02d}/{moment.year:04d}",
        "mm/dd/yy": f"{moment.month:02d}/{moment.day:02d}/{moment.year % 100:02d}",
        "d-mmm-yy": f"{moment.day}-{month_abbreviation}-{moment.year % 100:02d}",
        "yyyy-mm-dd": moment.strftime("%Y-%m-%d"),
        "mmm-yy": f"{month_abbreviation}-{moment.year % 100:02d}",
        "m/d": f"{moment.month}/{moment.day}",
        "h:mm am/pm": moment.strftime("%I:%M %p").lstrip("0"),
        "h:mm:ss": f"{moment.hour}:{moment.minute:02d}:{moment.second:02d}",
        "hh:mm:ss": moment.strftime("%H:%M:%S"),
    }
    if lower in presets:
        return presets[lower]
    if "am/pm" in lower:
        return moment.strftime("%I:%M %p").lstrip("0")
    if "h" in lower or "s" in lower:
        return moment.strftime("%H:%M:%S")
    return f"{moment.month}/{moment.day}/{moment.year:04d}"


def _format_fake_leap_day(format_code: str) -> str:
    if format_code == "yyyy-mm-dd":
        return "1900-02-29"
    if format_code == "mm/dd/yyyy":
        return "02/29/1900"
    if format_code == "mm/dd/yy":
        return "02/29/00"
    if format_code == "d-mmm-yy":
        return "29-Feb-00"
    return "2/29/1900"
