"""Excel number formatting independent of Qt.

Implements Excel's custom number-format language: up to four sections
(positive; negative; zero; text) or conditional sections such as ``[>999]``,
colors, digit placeholders (``0 # ?``), grouping and scaling commas,
percentages, scientific notation, fractions, quoted and escaped literals,
``_x`` spacing, ``*x`` fill, ``@`` text, locale/currency tags like
``[$€-407]``, every date and time code, AM/PM, and elapsed ``[h] [m] [s]``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
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
_COLORS = {
    "black": "#000000",
    "blue": "#0000ff",
    "cyan": "#00ffff",
    "green": "#00ff00",
    "magenta": "#ff00ff",
    "red": "red",
    "white": "#ffffff",
    "yellow": "#ffff00",
}
# Excel's 56-entry default palette for [ColorN].
_PALETTE = (
    "#000000 #ffffff #ff0000 #00ff00 #0000ff #ffff00 #ff00ff #00ffff "
    "#800000 #008000 #000080 #808000 #800080 #008080 #c0c0c0 #808080 "
    "#9999ff #993366 #ffffcc #ccffff #660066 #ff8080 #0066cc #ccccff "
    "#000080 #ff00ff #ffff00 #00ffff #800080 #800000 #008080 #0000ff "
    "#00ccff #ccffff #ccffcc #ffff99 #99ccff #ff99cc #cc99ff #ffcc99 "
    "#3366ff #33cccc #99cc00 #ffcc00 #ff9900 #ff6600 #666699 #969696 "
    "#003366 #339966 #003300 #333300 #993300 #993366 #333399 #333333"
).split()
_CONDITION_RE = re.compile(r"^(<=|>=|<>|<|>|=)\s*(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)$")
_ERROR_PREFIX = "#"
_MONTHS = (
    "January February March April May June July August September October "
    "November December"
).split()
_DAYS = "Sunday Monday Tuesday Wednesday Thursday Friday Saturday".split()
_MAX_SERIAL = 2_958_465.999_988_426


# ------------------------------------------------------------------- tokens
@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    text: str = ""


@dataclass(slots=True)
class _Section:
    tokens: list[_Token]
    color: str | None
    condition: tuple[str, float] | None
    has_minus: bool


def _split_sections(format_code: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    index = 0
    quoted = False
    bracket = False
    while index < len(format_code):
        character = format_code[index]
        if character == "\\" and not quoted and index + 1 < len(format_code):
            current.append(format_code[index : index + 2])
            index += 2
            continue
        if character == '"' and not bracket:
            quoted = not quoted
        elif character == "[" and not quoted:
            bracket = True
        elif character == "]" and not quoted:
            bracket = False
        if character == ";" and not quoted and not bracket:
            sections.append("".join(current))
            current = []
        else:
            current.append(character)
        index += 1
    sections.append("".join(current))
    return sections


_DATE_LETTERS = set("yYmMdDhHsSeE")


def _tokenize(section: str) -> tuple[list[_Token], str | None, tuple[str, float] | None]:
    tokens: list[_Token] = []
    color: str | None = None
    condition: tuple[str, float] | None = None
    index = 0
    length = len(section)
    while index < length:
        character = section[index]
        if character == '"':
            end = section.find('"', index + 1)
            end = length if end == -1 else end
            tokens.append(_Token("literal", section[index + 1 : end]))
            index = end + 1
            continue
        if character == "\\" and index + 1 < length:
            tokens.append(_Token("literal", section[index + 1]))
            index += 2
            continue
        if character == "_" and index + 1 < length:
            tokens.append(_Token("literal", " "))
            index += 2
            continue
        if character == "*" and index + 1 < length:
            tokens.append(_Token("fill", section[index + 1]))
            index += 2
            continue
        if character == "[":
            end = section.find("]", index + 1)
            end = length if end == -1 else end
            content = section[index + 1 : end]
            lower = content.lower()
            index = end + 1
            if lower in _COLORS:
                color = _COLORS[lower]
                continue
            if lower.startswith("color") and lower[5:].isdigit():
                position = int(lower[5:])
                if 1 <= position <= 56:
                    color = _PALETTE[position - 1]
                continue
            match = _CONDITION_RE.match(content.strip())
            if match:
                condition = (match.group(1), float(match.group(2)))
                continue
            if content.startswith("$"):
                symbol = content[1:].split("-", 1)[0]
                if symbol:
                    tokens.append(_Token("literal", symbol))
                continue
            if lower in ("h", "hh", "m", "mm", "s", "ss") or re.fullmatch(r"(h+|m+|s+)", lower):
                tokens.append(_Token("elapsed", lower))
                continue
            continue
        if section[index : index + 7].lower() == "general":
            tokens.append(_Token("general"))
            index += 7
            continue
        upper5 = section[index : index + 5].upper()
        if upper5 == "AM/PM":
            tokens.append(_Token("ampm", section[index : index + 5]))
            index += 5
            continue
        if section[index : index + 3].upper() == "A/P":
            tokens.append(_Token("ampm", section[index : index + 3]))
            index += 3
            continue
        if character in "0#?":
            tokens.append(_Token("digit", character))
            index += 1
            continue
        if character == ".":
            tokens.append(_Token("point"))
            index += 1
            continue
        if character == ",":
            tokens.append(_Token("comma"))
            index += 1
            continue
        if character == "%":
            tokens.append(_Token("percent"))
            index += 1
            continue
        if character in "eE" and index + 1 < length and section[index + 1] in "+-":
            tokens.append(_Token("exponent", section[index : index + 2].upper()))
            index += 2
            continue
        if character == "/":
            tokens.append(_Token("slash"))
            index += 1
            continue
        if character == "@":
            tokens.append(_Token("at"))
            index += 1
            continue
        if character in _DATE_LETTERS:
            end = index
            while end < length and section[end].lower() == character.lower():
                end += 1
            tokens.append(_Token("date", section[index:end].lower()))
            index = end
            continue
        tokens.append(_Token("literal", character))
        index += 1
    return _resolve_minutes(tokens), color, condition


def _resolve_minutes(tokens: list[_Token]) -> list[_Token]:
    """Mark ``m``/``mm`` as minutes when they follow hours or precede seconds.

    A lone ``e`` (era year) without other date codes is literal text, so
    words such as ``Zero`` survive unquoted, as Excel's dialog accepts them.
    """
    real_dates = any(
        token.kind in ("date", "elapsed") and token.text[:1] != "e" for token in tokens
    )
    if not real_dates:
        tokens = [
            _Token("literal", token.text) if token.kind == "date" else token
            for token in tokens
        ]
    date_positions = [
        index for index, token in enumerate(tokens) if token.kind in ("date", "elapsed")
    ]
    resolved = list(tokens)
    for order, index in enumerate(date_positions):
        token = tokens[index]
        if token.kind != "date" or token.text not in ("m", "mm"):
            continue
        previous = tokens[date_positions[order - 1]] if order > 0 else None
        following = tokens[date_positions[order + 1]] if order + 1 < len(date_positions) else None
        after_hours = previous is not None and previous.text[:1] == "h"
        before_seconds = following is not None and following.text[:1] == "s"
        if after_hours or before_seconds:
            resolved[index] = _Token("minute", token.text)
    return resolved


def _parse(format_code: str) -> list[_Section]:
    cached = _CACHE.get(format_code)
    if cached is not None:
        return cached
    sections: list[_Section] = []
    for raw in _split_sections(format_code):
        tokens, color, condition = _tokenize(raw)
        has_minus = any(token.kind == "literal" and "-" in token.text for token in tokens)
        sections.append(_Section(tokens, color, condition, has_minus))
    if len(_CACHE) > 2048:
        _CACHE.clear()
    _CACHE[format_code] = sections
    return sections


_CACHE: dict[str, list[_Section]] = {}


def _is_date_section(section: _Section) -> bool:
    return any(token.kind in ("date", "minute", "elapsed", "ampm") for token in section.tokens)


def is_date_format(format_code: str) -> bool:
    """Return whether a number format displays a date or time."""
    code = _BUILTIN_FORMATS.get(format_code, format_code)
    if code == "General":
        return False
    return any(_is_date_section(section) for section in _parse(code)[:1])


# ------------------------------------------------------------- public entry
def format_value(value: Any, format_code: str = "General") -> FormattedValue:
    """Render a scalar using built-in or custom worksheet format syntax."""
    if value is None:
        return FormattedValue("")
    if isinstance(value, str) and value.startswith(_ERROR_PREFIX):
        return FormattedValue(value)
    selected_code = _BUILTIN_FORMATS.get(format_code, format_code or "General")
    legacy = _legacy_alias(value, format_code)
    if legacy is not None:
        return legacy
    if selected_code == "General":
        return FormattedValue(_general(value))
    if isinstance(value, bool):
        return FormattedValue("TRUE" if value else "FALSE")
    sections = _parse(selected_code)
    if isinstance(value, str):
        return _format_text(value, sections)
    numeric = _as_number(value)
    if numeric is None:
        return FormattedValue(_general(value))
    section, absolute = _choose_section(numeric, sections)
    if section is None or (
        _is_text_section(section)
        and not any(token.kind == "digit" for token in section.tokens)
    ):
        return FormattedValue(_general(value))
    if _is_date_section(section):
        rendered = _format_date(numeric, section)
        return FormattedValue(rendered, section.color)
    if absolute:
        numeric = abs(numeric)
    return FormattedValue(_format_number(numeric, section), section.color)


def format_number_text(value: Any, format_code: str) -> str | None:
    """Return TEXT()-style output, or ``None`` when the value cannot be formatted."""
    if isinstance(value, str):
        parsed = None
        from duddysheet.core.values import parse_number_text

        parsed = parse_number_text(value)
        if parsed is None:
            sections = _parse(format_code)
            return _format_text(value, sections).text
        value = parsed
    numeric = _as_number(value)
    if format_code.strip().lower() == "general" or not format_code:
        from duddysheet.core.values import to_text

        return to_text(value)
    if numeric is None:
        return None
    sections = _parse(format_code)
    section, absolute = _choose_section(numeric, sections)
    if section is None:
        return None
    if _is_date_section(section):
        if numeric < 0 or numeric > _MAX_SERIAL:
            return None
        return _format_date(numeric, section)
    return _format_number(abs(numeric) if absolute else numeric, section)


def _legacy_alias(value: Any, format_code: str) -> FormattedValue | None:
    """Named shortcut formats keep their established simplified renderings."""
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
    if format_code == "Accounting":
        converted = _as_number(value)
        if converted is None or isinstance(value, bool):
            return FormattedValue(_general(value))
        if converted == 0:
            return FormattedValue("$ -")
        rendered = f"$ {abs(converted):,.2f}"
        return FormattedValue(f"({rendered})" if converted < 0 else rendered)
    if format_code == "Text":
        return FormattedValue(_general(value))
    if format_code == "Scientific" and isinstance(value, str):
        return FormattedValue(value)
    return None


def _choose_section(value: float, sections: list[_Section]) -> tuple[_Section | None, bool]:
    """Pick the section for a number; the flag means render the absolute value."""
    if any(section.condition is not None for section in sections):
        numeric_sections = [section for section in sections if not _is_text_section(section)]
        for section in numeric_sections:
            if section.condition is not None and _condition_holds(value, section.condition):
                return section, False
        fallback = [section for section in numeric_sections if section.condition is None]
        if fallback:
            return fallback[0], False
        return (numeric_sections[-1] if numeric_sections else None), False
    numeric_sections = sections[:3]
    if len(sections) >= 4 or (len(sections) > 1 and _is_text_section(sections[-1])):
        numeric_sections = [section for section in sections[:3] if not _is_text_section(section)] or sections[:1]
    if value > 0 or len(numeric_sections) == 1:
        return numeric_sections[0], False
    if value < 0:
        return (numeric_sections[1], True) if len(numeric_sections) >= 2 else (numeric_sections[0], False)
    if len(numeric_sections) >= 3:
        return numeric_sections[2], False
    return numeric_sections[0], False


def _is_text_section(section: _Section) -> bool:
    return any(token.kind == "at" for token in section.tokens)


def _condition_holds(value: float, condition: tuple[str, float]) -> bool:
    operator, threshold = condition
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
        "=": value == threshold,
        "<>": value != threshold,
    }[operator]


def _format_text(value: str, sections: list[_Section]) -> FormattedValue:
    text_section = None
    if len(sections) >= 4:
        text_section = sections[3]
    elif any(_is_text_section(section) for section in sections):
        text_section = next(section for section in sections if _is_text_section(section))
    if text_section is None:
        return FormattedValue(value)
    rendered: list[str] = []
    for token in text_section.tokens:
        if token.kind == "at":
            rendered.append(value)
        elif token.kind == "literal":
            rendered.append(token.text)
        elif token.kind == "general":
            rendered.append(value)
    return FormattedValue("".join(rendered), text_section.color)


# ---------------------------------------------------------------- general
def _general(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return general_number(value)
    if isinstance(value, int):
        return general_number(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def general_number(value: float | int, width: int = 11) -> str:
    """Render a number as Excel's General format does in a cell ``width`` characters wide."""
    if isinstance(value, int) and not isinstance(value, bool):
        if len(str(value)) <= width:
            return str(value)
        value = float(value)
    if value == 0:
        return "0"
    if not math.isfinite(value):
        return "#NUM!"
    magnitude = abs(value)
    exponent = math.floor(math.log10(magnitude))
    sign_width = 1 if value < 0 else 0
    if exponent >= width - sign_width or exponent < -9:
        return _general_scientific(value, width)
    integer_digits = max(1, exponent + 1)
    decimals = max(0, min(width - sign_width - integer_digits - 1, 14 - exponent))
    rounded = round(value, decimals) if decimals else round(value)
    rendered = f"{rounded:.{decimals}f}"
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in ("0", "-0"):
        return _general_scientific(value, width)
    # Fifteen significant digits is Excel's display precision.
    significant = f"{value:.15g}"
    if "e" not in significant and len(significant) <= len(rendered):
        return significant
    return rendered


def _general_scientific(value: float, width: int) -> str:
    sign = "-" if value < 0 else ""
    exponent = math.floor(math.log10(abs(value)))
    exponent_text = f"E{'+' if exponent >= 0 else '-'}{abs(exponent):02d}"
    available = width - len(sign) - len(exponent_text) - 2
    decimals = max(0, min(available, 14))
    mantissa = abs(value) / 10**exponent
    rounded = round(mantissa, decimals)
    if rounded >= 10:
        rounded /= 10
        exponent += 1
        exponent_text = f"E{'+' if exponent >= 0 else '-'}{abs(exponent):02d}"
    rendered = f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")
    return f"{sign}{rendered}{exponent_text}"


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


# ------------------------------------------------------------------ numbers
def _round_half_away(value: float, decimals: int) -> float:
    """Round halves away from zero on Excel's 15-significant-digit value."""
    if not math.isfinite(value):
        return value
    quantum = Decimal(1).scaleb(-decimals)
    rounded = Decimal(f"{value:.15g}").quantize(quantum, rounding=ROUND_HALF_UP)
    return float(rounded)


def _group(digits: str) -> str:
    head = digits.lstrip(" ")
    padding = digits[: len(digits) - len(head)]
    if not head.isdigit():
        return digits
    groups: list[str] = []
    while len(head) > 3:
        groups.insert(0, head[-3:])
        head = head[:-3]
    groups.insert(0, head)
    return padding + ",".join(groups)


def _format_number(value: float, section: _Section) -> str:
    tokens = [token for token in section.tokens if token.kind != "fill"]
    if any(token.kind == "general" for token in tokens):
        rendered: list[str] = []
        for token in tokens:
            if token.kind == "general":
                rendered.append(general_number(value))
            elif token.kind == "literal":
                rendered.append(token.text)
        return "".join(rendered)
    digit_tokens = [token for token in tokens if token.kind == "digit"]
    percent_count = sum(token.kind == "percent" for token in tokens)
    value = value * 100**percent_count
    if any(token.kind == "exponent" for token in tokens):
        return _format_scientific(value, tokens)
    if any(token.kind == "slash" for token in tokens) and digit_tokens:
        return _format_fraction(value, tokens)
    # Trailing commas (after the last digit placeholder) scale by thousands.
    last_digit = max((index for index, token in enumerate(tokens) if token.kind == "digit"), default=-1)
    scale_commas = 0
    grouping = False
    point_index = next((index for index, token in enumerate(tokens) if token.kind == "point"), None)
    for index, token in enumerate(tokens):
        if token.kind != "comma":
            continue
        following_digit = any(
            later.kind == "digit" for later in tokens[index + 1 : point_index if point_index is not None else len(tokens)]
        )
        preceding_digit = any(earlier.kind == "digit" for earlier in tokens[:index])
        if preceding_digit and following_digit and (point_index is None or index < point_index):
            grouping = True
        elif preceding_digit and (index > last_digit or (point_index is not None and index == point_index - 1)):
            scale_commas += 1
    value = value / 1000**scale_commas
    if point_index is None:
        integer_tokens = digit_tokens
        fraction_tokens: list[_Token] = []
    else:
        integer_tokens = [token for token in tokens[:point_index] if token.kind == "digit"]
        fraction_tokens = [token for token in tokens[point_index + 1 :] if token.kind == "digit"]
    decimals = len(fraction_tokens)
    rounded = _round_half_away(value, decimals)
    negative = rounded < 0
    magnitude = abs(rounded)
    integer_part = int(math.floor(magnitude + 1e-12)) if decimals else int(round(magnitude))
    fraction_digits = ""
    if decimals:
        fraction_value = round((magnitude - integer_part) * 10**decimals)
        if fraction_value >= 10**decimals:
            integer_part += 1
            fraction_value -= 10**decimals
        fraction_digits = str(fraction_value).zfill(decimals)
    integer_text = _integer_digits(integer_part, integer_tokens)
    if grouping and integer_text.strip():
        integer_text = _group(integer_text)
    fraction_text = _fraction_digits(fraction_digits, fraction_tokens)
    output: list[str] = []
    integer_emitted = False
    fraction_position = 0
    seen_point = False
    integer_placeholders_left = len(integer_tokens)
    for token in tokens:
        if token.kind == "digit":
            if not seen_point:
                integer_placeholders_left -= 1
                if not integer_emitted:
                    # Emit every integer digit at the first placeholder, except
                    # those reserved for placeholders separated by literals.
                    reserved = integer_placeholders_left
                    head = integer_text[: max(0, len(integer_text) - reserved)] if reserved else integer_text
                    output.append(head)
                    integer_text = integer_text[len(head) :]
                    integer_emitted = True
                else:
                    output.append(integer_text[:1])
                    integer_text = integer_text[1:]
            else:
                output.append(fraction_text[fraction_position : fraction_position + 1])
                fraction_position += 1
        elif token.kind == "point":
            seen_point = True
            output.append(".")
        elif token.kind == "literal":
            output.append(token.text)
        elif token.kind == "percent":
            output.append("%")
        elif token.kind == "at":
            continue
    rendered = "".join(output)
    if negative and magnitude > 0:
        rendered = "-" + rendered
    return rendered


def _integer_digits(value: int, tokens: list[_Token]) -> str:
    digits = str(value)
    if not tokens:
        return "" if value == 0 else digits
    if value == 0:
        digits = ""
    placeholders = [token.text for token in tokens]
    width = len(placeholders)
    if len(digits) < width:
        missing = placeholders[: width - len(digits)]
        prefix = "".join("0" if mark == "0" else " " if mark == "?" else "" for mark in missing)
        digits = prefix + digits
    if not digits.strip() and value == 0 and "0" not in placeholders:
        return digits
    return digits


def _fraction_digits(digits: str, tokens: list[_Token]) -> str:
    characters = list(digits)
    for index in range(len(characters) - 1, -1, -1):
        mark = tokens[index].text
        if characters[index] != "0" or mark == "0":
            break
        characters[index] = " " if mark == "?" else ""
    return "".join(character if character else "\0" for character in characters).replace("\0", "")


def _format_scientific(value: float, tokens: list[_Token]) -> str:
    exponent_index = next(index for index, token in enumerate(tokens) if token.kind == "exponent")
    mantissa_tokens = tokens[:exponent_index]
    exponent_tokens = tokens[exponent_index + 1 :]
    point_index = next((index for index, token in enumerate(mantissa_tokens) if token.kind == "point"), None)
    integer_tokens = [
        token for token in (mantissa_tokens if point_index is None else mantissa_tokens[:point_index]) if token.kind == "digit"
    ]
    fraction_tokens = [] if point_index is None else [token for token in mantissa_tokens[point_index + 1 :] if token.kind == "digit"]
    exponent_digits = [token for token in exponent_tokens if token.kind == "digit"]
    sign_mode = tokens[exponent_index].text
    negative = value < 0
    magnitude = abs(value)
    integer_width = max(1, len(integer_tokens))
    if magnitude == 0:
        exponent = 0
        mantissa = 0.0
    else:
        exponent = math.floor(math.log10(magnitude))
        if integer_width > 1 and any(token.text == "#" for token in integer_tokens):
            exponent -= exponent % integer_width
        else:
            exponent -= integer_width - 1
        mantissa = magnitude / 10**exponent
        rounded = _round_half_away(mantissa, len(fraction_tokens))
        if rounded >= 10**integer_width:
            exponent += integer_width if any(token.text == "#" for token in integer_tokens) and integer_width > 1 else 1
            mantissa = magnitude / 10**exponent
    mantissa = _round_half_away(mantissa, len(fraction_tokens))
    integer_part = int(math.floor(mantissa + 1e-12))
    fraction_value = round((mantissa - integer_part) * 10 ** len(fraction_tokens)) if fraction_tokens else 0
    integer_text = _integer_digits(integer_part, integer_tokens) or ("0" if not integer_tokens else "")
    fraction_text = _fraction_digits(str(fraction_value).zfill(len(fraction_tokens)), fraction_tokens) if fraction_tokens else ""
    exponent_text = str(abs(exponent)).zfill(len(exponent_digits) or 1)
    exponent_sign = "-" if exponent < 0 else ("+" if sign_mode.endswith("+") else "")
    first_digit = next(
        (index for index, token in enumerate(mantissa_tokens) if token.kind == "digit"),
        0,
    )
    prefix = "".join(
        token.text for token in mantissa_tokens[:first_digit] if token.kind == "literal"
    )
    rendered = prefix + integer_text + ("." + fraction_text if point_index is not None else "")
    rendered += "E" + exponent_sign + exponent_text
    suffix = "".join(token.text for token in exponent_tokens if token.kind == "literal")
    return ("-" if negative else "") + rendered + suffix


def _format_fraction(value: float, tokens: list[_Token]) -> str:
    slash = next(index for index, token in enumerate(tokens) if token.kind == "slash")
    before = tokens[:slash]
    after = tokens[slash + 1 :]
    # Numerator: the digit run immediately before the slash.
    numerator_end = len(before)
    numerator_start = numerator_end
    while numerator_start > 0 and before[numerator_start - 1].kind == "digit":
        numerator_start -= 1
    numerator_tokens = before[numerator_start:numerator_end]
    whole_tokens = [token for token in before[:numerator_start] if token.kind == "digit"]
    leading_literals = "".join(token.text for token in before[:numerator_start] if token.kind == "literal")
    denominator_tokens: list[_Token] = []
    fixed_denominator = ""
    index = 0
    while index < len(after) and after[index].kind == "digit":
        denominator_tokens.append(after[index])
        index += 1
    if not denominator_tokens:
        while index < len(after) and after[index].kind == "literal" and after[index].text.isdigit():
            fixed_denominator += after[index].text
            index += 1
    trailing = "".join(token.text for token in after[index:] if token.kind == "literal")
    negative = value < 0
    magnitude = abs(value)
    if whole_tokens:
        whole = int(math.floor(magnitude))
        remainder = magnitude - whole
    else:
        whole = 0
        remainder = magnitude
    if fixed_denominator:
        denominator = int(fixed_denominator)
        numerator = int(round(remainder * denominator))
    else:
        limit = 10 ** max(1, len(denominator_tokens)) - 1
        fraction = Fraction(remainder).limit_denominator(limit)
        numerator, denominator = fraction.numerator, fraction.denominator
    if whole_tokens and numerator == denominator and numerator:
        whole += 1
        numerator = 0
    numerator_width = len(numerator_tokens)
    denominator_width = len(denominator_tokens) or len(fixed_denominator)
    if numerator == 0 and whole_tokens:
        blank = " " * (len(leading_literals) + numerator_width + 1 + denominator_width)
        return ("-" if negative and whole else "") + str(whole) + blank + trailing
    whole_text = ""
    if whole_tokens:
        whole_text = str(whole) if whole else ("0" if all(token.text == "0" for token in whole_tokens) else "")
    numerator_text = str(numerator).rjust(numerator_width, " ") if numerator_width else str(numerator)
    denominator_text = str(denominator).ljust(denominator_width, " ")
    if fixed_denominator:
        denominator_text = fixed_denominator
    rendered = f"{whole_text}{leading_literals}{numerator_text}/{denominator_text}{trailing}"
    return ("-" if negative else "") + rendered


# -------------------------------------------------------------- dates/times
def _serial_parts(serial: float) -> tuple[int, int, int, int, float]:
    """Return (year, month, day, weekday_sunday0, seconds_of_day) honoring 1900 leap bug."""
    days = math.floor(serial)
    seconds = (serial - days) * 86_400
    weekday = (days + 6) % 7
    if days == 60:
        return 1900, 2, 29, weekday, seconds
    if days == 0:
        return 1900, 1, 0, weekday, seconds
    adjusted = days - 1 if days > 60 else days
    moment = date(1899, 12, 31) + timedelta(days=adjusted)
    return moment.year, moment.month, moment.day, weekday, seconds


def _format_date(serial: float, section: _Section) -> str:
    if serial < 0 or serial > _MAX_SERIAL:
        return "#" * 8
    tokens = section.tokens
    subsecond_digits = 0
    for index, token in enumerate(tokens):
        if token.kind == "point" and index > 0 and tokens[index - 1].kind == "date" and tokens[index - 1].text.startswith("s"):
            count = 0
            for later in tokens[index + 1 :]:
                if later.kind == "digit" and later.text == "0":
                    count += 1
                else:
                    break
            subsecond_digits = count
    # Round to the displayed precision, as Excel does.
    unit = 86_400 * 10**subsecond_digits
    rounded = round(serial * unit) / unit
    year, month, day, weekday, seconds = _serial_parts(rounded)
    total_seconds = round(seconds * 10**subsecond_digits) / 10**subsecond_digits
    hour = int(total_seconds // 3600)
    minute = int((total_seconds % 3600) // 60)
    second = int(total_seconds % 60)
    fraction = total_seconds - math.floor(total_seconds)
    twelve_hour = any(token.kind == "ampm" for token in tokens)
    output: list[str] = []
    skip_digits = 0
    for index, token in enumerate(tokens):
        if skip_digits and token.kind == "digit":
            skip_digits -= 1
            continue
        kind, code = token.kind, token.text
        if kind == "date":
            letter = code[0]
            if letter == "y" or letter == "e":
                output.append(f"{year % 100:02d}" if len(code) <= 2 and letter == "y" else str(year))
            elif letter == "m":
                if len(code) == 1:
                    output.append(str(month))
                elif len(code) == 2:
                    output.append(f"{month:02d}")
                elif len(code) == 3:
                    output.append(_MONTHS[month - 1][:3])
                elif len(code) == 5:
                    output.append(_MONTHS[month - 1][0])
                else:
                    output.append(_MONTHS[month - 1])
            elif letter == "d":
                if len(code) == 1:
                    output.append(str(day))
                elif len(code) == 2:
                    output.append(f"{day:02d}")
                elif len(code) == 3:
                    output.append(_DAYS[weekday][:3])
                else:
                    output.append(_DAYS[weekday])
            elif letter == "h":
                shown = hour % 12 or 12 if twelve_hour else hour
                output.append(f"{shown:02d}" if len(code) >= 2 else str(shown))
            elif letter == "s":
                output.append(f"{second:02d}" if len(code) >= 2 else str(second))
        elif kind == "minute":
            output.append(f"{minute:02d}" if len(code) >= 2 else str(minute))
        elif kind == "elapsed":
            letter = code[0]
            total = rounded * 86_400
            if letter == "h":
                amount = int(total // 3600)
            elif letter == "m":
                amount = int(total // 60)
            else:
                amount = int(round(total))
            output.append(str(amount).zfill(len(code)))
        elif kind == "ampm":
            morning = hour < 12
            if code.upper() == "AM/PM":
                output.append("AM" if morning else "PM")
            else:
                marker = "A" if morning else "P"
                output.append(marker if code[0].isupper() else marker.lower())
        elif kind == "point":
            previous = tokens[index - 1] if index else None
            if previous is not None and previous.kind == "date" and previous.text.startswith("s") and subsecond_digits:
                output.append("." + str(round(fraction * 10**subsecond_digits)).zfill(subsecond_digits)[:subsecond_digits])
                skip_digits = subsecond_digits
            else:
                output.append(".")
        elif kind == "literal":
            output.append(code)
        elif kind == "digit":
            output.append(code if code != "#" else "")
        elif kind == "comma":
            output.append(",")
        elif kind == "slash":
            output.append("/")
        elif kind == "percent":
            output.append("%")
    return "".join(output)


def _format_fake_leap_day(format_code: str) -> str:
    """Render Excel's fictitious 1900-02-29 with a date format (kept for callers)."""
    return _format_date(60, _parse(format_code)[0])
