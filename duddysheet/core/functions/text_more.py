"""Excel text functions beyond the core string set."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from duddysheet.core.errors import NA_ERROR, VALUE_ERROR, SpreadsheetError, is_error
from duddysheet.core.functions import lift_all, lift_positions, register
from duddysheet.core.functions.common import flatten, number, round_away, scalar, text

TEXT = "Text"


def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


_NONPRINTING = {*range(0, 32), 127, 129, 141, 143, 144, 157}


@register("CLEAN", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=TEXT)
def clean(context: Any, value: Any) -> Any:
    """Remove nonprinting characters from text."""
    return "".join(
        character for character in text(scalar(context, value)) if ord(character) not in _NONPRINTING
    )


@register("T", min_args=1, max_args=1, argument_spec="value", lift=lift_all, category=TEXT)
def t_function(context: Any, value: Any) -> Any:
    """Return text unchanged and any other value as empty text."""
    selected = scalar(context, value)
    if is_error(selected):
        return selected
    return selected if isinstance(selected, str) else ""


@register("UNICHAR", min_args=1, max_args=1, argument_spec="number", lift=lift_all, category=TEXT)
def unichar(context: Any, value: Any) -> Any:
    """Return the Unicode character for a code point."""
    code = _num(context, value)
    if is_error(code):
        return code
    code = math.trunc(code)
    if not 1 <= code <= 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        return VALUE_ERROR
    return chr(code)


@register("UNICODE", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=TEXT)
def unicode_function(context: Any, value: Any) -> Any:
    """Return the code point of the first character of text."""
    source = text(scalar(context, value))
    return VALUE_ERROR if not source else ord(source[0])


def _grouped(value: float, decimals: int, commas: bool) -> str:
    rounded = round_away(abs(value), decimals)
    if decimals < 0:
        decimals = 0
    rendered = f"{rounded:,.{decimals}f}" if commas else f"{rounded:.{decimals}f}"
    return rendered


@register(
    "DOLLAR",
    min_args=1,
    max_args=2,
    argument_spec="number, [decimals]",
    lift=lift_all,
    category=TEXT,
)
def dollar(context: Any, value: Any, decimals: Any = 2) -> Any:
    """Convert a number to currency text."""
    amount = _num(context, value)
    places = _num(context, 2 if decimals is None else decimals)
    if is_error(amount):
        return amount
    if is_error(places):
        return places
    places = math.trunc(places)
    if places > 127:
        return VALUE_ERROR
    rendered = "$" + _grouped(amount, places, True)
    negative = round_away(amount, places) < 0
    return f"({rendered})" if negative else rendered


@register(
    "FIXED",
    min_args=1,
    max_args=3,
    argument_spec="number, [decimals], [no_commas]",
    lift=lift_all,
    category=TEXT,
)
def fixed(context: Any, value: Any, decimals: Any = 2, no_commas: Any = False) -> Any:
    """Format a number as text with a fixed number of decimals."""
    amount = _num(context, value)
    places = _num(context, 2 if decimals is None else decimals)
    if is_error(amount):
        return amount
    if is_error(places):
        return places
    places = math.trunc(places)
    if places > 127:
        return VALUE_ERROR
    omit = bool(scalar(context, no_commas)) if no_commas is not None else False
    rendered = _grouped(amount, places, not omit)
    return "-" + rendered if round_away(amount, places) < 0 else rendered


def _value_text(value: Any, strict: bool) -> str:
    if isinstance(value, SpreadsheetError):
        return value.literal
    if isinstance(value, str):
        return '"' + value.replace('"', '""') + '"' if strict else value
    if value is None:
        return ""
    return text(value)


@register(
    "VALUETOTEXT",
    min_args=1,
    max_args=2,
    argument_spec="value, [format]",
    lift=lift_positions(0),
    accepts_errors=True,
    category=TEXT,
)
def valuetotext(context: Any, value: Any, format_code: Any = 0) -> Any:
    """Return text from any value, quoting strings in strict format."""
    mode = _num(context, 0 if format_code is None else format_code)
    if is_error(mode) or math.trunc(mode) not in (0, 1):
        return VALUE_ERROR
    return _value_text(scalar(context, value), math.trunc(mode) == 1)


@register(
    "ARRAYTOTEXT",
    min_args=1,
    max_args=2,
    argument_spec="array, [format]",
    accepts_errors=True,
    category=TEXT,
)
def arraytotext(context: Any, array: Any, format_code: Any = 0) -> Any:
    """Return an array as text, concise or in strict array-constant form."""
    mode = _num(context, 0 if format_code is None else format_code)
    if is_error(mode) or math.trunc(mode) not in (0, 1):
        return VALUE_ERROR
    rows = context.matrix(array)
    if math.trunc(mode) == 0:
        return ", ".join(_value_text(item, False) for row in rows for item in row)
    return "{" + ";".join(",".join(_value_text(item, True) for item in row) for row in rows) + "}"


def _regex_flags(context: Any, case_sensitivity: Any) -> Any:
    mode = _num(context, 0 if case_sensitivity is None else case_sensitivity)
    if is_error(mode) or math.trunc(mode) not in (0, 1):
        return VALUE_ERROR
    return re.IGNORECASE if math.trunc(mode) == 1 else 0


def _compile(pattern: str, flags: int) -> Any:
    try:
        return re.compile(pattern, flags)
    except re.error:
        return VALUE_ERROR


@register(
    "REGEXTEST",
    min_args=2,
    max_args=3,
    argument_spec="text, pattern, [case_sensitivity]",
    lift=lift_positions(0, 1),
    category=TEXT,
)
def regextest(context: Any, value: Any, pattern: Any, case_sensitivity: Any = 0) -> Any:
    """Return whether text matches a regular expression."""
    flags = _regex_flags(context, case_sensitivity)
    if is_error(flags):
        return flags
    compiled = _compile(text(scalar(context, pattern)), flags)
    if is_error(compiled):
        return compiled
    return compiled.search(text(scalar(context, value))) is not None


@register(
    "REGEXEXTRACT",
    min_args=2,
    max_args=4,
    argument_spec="text, pattern, [return_mode], [case_sensitivity]",
    lift=lift_positions(0, 1),
    category=TEXT,
)
def regexextract(
    context: Any,
    value: Any,
    pattern: Any,
    return_mode: Any = 0,
    case_sensitivity: Any = 0,
) -> Any:
    """Extract the first match, all matches, or capture groups of a regular expression."""
    flags = _regex_flags(context, case_sensitivity)
    mode = _num(context, 0 if return_mode is None else return_mode)
    if is_error(flags):
        return flags
    if is_error(mode) or math.trunc(mode) not in (0, 1, 2):
        return VALUE_ERROR
    compiled = _compile(text(scalar(context, pattern)), flags)
    if is_error(compiled):
        return compiled
    source = text(scalar(context, value))
    mode = math.trunc(mode)
    if mode == 0:
        match = compiled.search(source)
        return NA_ERROR if match is None else match.group(0)
    if mode == 1:
        matches = [match.group(0) for match in compiled.finditer(source)]
        return NA_ERROR if not matches else tuple((item,) for item in matches)
    match = compiled.search(source)
    if match is None:
        return NA_ERROR
    groups = match.groups() or (match.group(0),)
    return (tuple("" if group is None else group for group in groups),)


@register(
    "REGEXREPLACE",
    min_args=3,
    max_args=5,
    argument_spec="text, pattern, replacement, [occurrence], [case_sensitivity]",
    lift=lift_positions(0, 1, 2),
    category=TEXT,
)
def regexreplace(
    context: Any,
    value: Any,
    pattern: Any,
    replacement: Any,
    occurrence: Any = 0,
    case_sensitivity: Any = 0,
) -> Any:
    """Replace regular-expression matches; occurrence 0 replaces every match."""
    flags = _regex_flags(context, case_sensitivity)
    which = _num(context, 0 if occurrence is None else occurrence)
    if is_error(flags):
        return flags
    if is_error(which):
        return which
    compiled = _compile(text(scalar(context, pattern)), flags)
    if is_error(compiled):
        return compiled
    source = text(scalar(context, value))
    template = re.sub(r"\$(\d+)", r"\\g<\1>", text(scalar(context, replacement)))
    which = math.trunc(which)
    if which == 0:
        try:
            return compiled.sub(template, source)
        except (re.error, IndexError):
            return VALUE_ERROR
    matches = list(compiled.finditer(source))
    if not matches:
        return source
    index = which - 1 if which > 0 else len(matches) + which
    if not 0 <= index < len(matches):
        return source
    match = matches[index]
    try:
        replaced = match.expand(template)
    except (re.error, IndexError):
        return VALUE_ERROR
    return source[: match.start()] + replaced + source[match.end() :]


# Byte-oriented variants behave like their character versions outside DBCS locales.
def _alias(name: str, target: str, arguments: str, lift: Any) -> None:
    from duddysheet.core.functions import FUNCTION_REGISTRY

    original = FUNCTION_REGISTRY[target]

    def implementation(context: Any, *values: Any) -> Any:
        return original.implementation(context, *values)

    implementation.__doc__ = (
        f"Byte-counting version of {target}; identical for single-byte languages."
    )
    register(
        name,
        min_args=original.min_args,
        max_args=original.max_args,
        argument_spec=arguments,
        lift=lift,
        category=TEXT,
    )(implementation)


_alias("LEFTB", "LEFT", "text, [num_bytes]", lift_all)
_alias("RIGHTB", "RIGHT", "text, [num_bytes]", lift_all)
_alias("MIDB", "MID", "text, start_num, num_bytes", lift_all)
_alias("LENB", "LEN", "text", lift_all)
_alias("FINDB", "FIND", "find_text, within_text, [start_num]", lift_all)
_alias("SEARCHB", "SEARCH", "find_text, within_text, [start_num]", lift_all)
_alias("REPLACEB", "REPLACE", "old_text, start_num, num_bytes, new_text", lift_all)


@register("ASC", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=TEXT)
def asc(context: Any, value: Any) -> Any:
    """Change full-width characters to half-width characters."""
    source = text(scalar(context, value))
    return "".join(
        unicodedata.normalize("NFKC", character) if 0xFF01 <= ord(character) <= 0xFF5E or character == "\u3000" else character
        for character in source
    )


@register("DBCS", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=TEXT)
def dbcs(context: Any, value: Any) -> Any:
    """Change half-width characters to full-width characters."""
    source = text(scalar(context, value))
    converted: list[str] = []
    for character in source:
        code = ord(character)
        if character == " ":
            converted.append("\u3000")
        elif 0x21 <= code <= 0x7E:
            converted.append(chr(code + 0xFEE0))
        else:
            converted.append(character)
    return "".join(converted)


@register("JIS", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=TEXT)
def jis(context: Any, value: Any) -> Any:
    """Change half-width characters to full-width characters."""
    return dbcs(context, value)


@register("PHONETIC", min_args=1, max_args=1, argument_spec="reference", category=TEXT)
def phonetic(context: Any, reference: Any) -> Any:
    """Return the phonetic (furigana) text of a reference; plain text otherwise."""
    return "".join(text(value) for value in flatten(context, reference) if isinstance(value, str))


_THAI_DIGITS = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_THAI_PLACES = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]


def _thai_number(value: int) -> str:
    if value == 0:
        return ""
    millions, remainder = divmod(value, 1_000_000)
    prefix = _thai_number(millions) + "ล้าน" if millions else ""
    digits = str(remainder).zfill(6)[-6:]
    words: list[str] = []
    length = len(digits)
    for index, character in enumerate(digits):
        digit = int(character)
        place = length - index - 1
        if digit == 0:
            continue
        if place == 1 and digit == 1:
            words.append("สิบ")
        elif place == 1 and digit == 2:
            words.append("ยี่สิบ")
        elif place == 0 and digit == 1 and (remainder > 9 or millions):
            words.append("เอ็ด")
        else:
            words.append(_THAI_DIGITS[digit] + _THAI_PLACES[place])
    return prefix + "".join(words)


@register("BAHTTEXT", min_args=1, max_args=1, argument_spec="number", lift=lift_all, category=TEXT)
def bahttext(context: Any, value: Any) -> Any:
    """Convert a number to Thai text and add a suffix of Baht."""
    amount = _num(context, value)
    if is_error(amount):
        return amount
    negative = amount < 0
    satang_total = int(round_away(abs(amount), 2) * 100 + 0.5)
    baht, satang = divmod(satang_total, 100)
    parts: list[str] = []
    if baht:
        parts.append(_thai_number(baht) + "บาท")
    if satang:
        parts.append(_thai_number(satang) + "สตางค์")
    else:
        parts.append(("" if baht else "ศูนย์บาท") + "ถ้วน")
    rendered = "".join(parts)
    return ("ลบ" + rendered) if negative else rendered

