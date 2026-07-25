"""Text worksheet functions."""

from __future__ import annotations

import re
from typing import Any

from excelclone.core.errors import VALUE_ERROR, is_error
from excelclone.core.functions import register
from excelclone.core.functions.common import (
    first_error,
    flatten,
    number,
    rectangular,
    scalar,
    serial_datetime,
    text,
)


@register("CONCAT", min_args=1, argument_spec="text1, [text2], ...")
def concat(context: Any, *arguments: Any) -> Any:
    """Join text from scalars, arrays, and ranges."""
    values = flatten(context, *arguments)
    error = first_error(values)
    return error if error is not None else "".join(text(value) for value in values)


@register("CONCATENATE", min_args=1, argument_spec="text1, [text2], ...")
def concatenate(context: Any, *arguments: Any) -> Any:
    """Join text arguments for compatibility with older workbooks."""
    return concat(context, *arguments)


@register(
    "TEXTJOIN",
    min_args=3,
    argument_spec="delimiter, ignore_empty, text1, ...",
)
def textjoin(
    context: Any,
    delimiter: Any,
    ignore_empty: Any,
    *arguments: Any,
) -> Any:
    """Join values with a delimiter and optional blank suppression."""
    separator = text(scalar(context, delimiter))
    suppress_blanks = bool(scalar(context, ignore_empty))
    values = flatten(context, *arguments)
    error = first_error(values)
    if error is not None:
        return error
    selected = [text(value) for value in values if not suppress_blanks or text(value)]
    return separator.join(selected)


def _count(context: Any, value: Any, default: int = 1) -> Any:
    if value is None:
        return default
    converted = number(scalar(context, value))
    if is_error(converted) or converted < 0:
        return VALUE_ERROR
    return int(converted)


@register("LEFT", min_args=1, max_args=2, argument_spec="text, [num_chars]")
def left(context: Any, value: Any, count: Any = None) -> Any:
    """Return characters from the start of text."""
    selected_count = _count(context, count)
    return selected_count if is_error(selected_count) else text(scalar(context, value))[:selected_count]


@register("RIGHT", min_args=1, max_args=2, argument_spec="text, [num_chars]")
def right(context: Any, value: Any, count: Any = None) -> Any:
    """Return characters from the end of text."""
    selected_count = _count(context, count)
    if is_error(selected_count):
        return selected_count
    source = text(scalar(context, value))
    return source[len(source) - selected_count :] if selected_count else ""


@register("MID", min_args=3, max_args=3, argument_spec="text, start_num, num_chars")
def mid(context: Any, value: Any, start: Any, count: Any) -> Any:
    """Return characters from a one-based position."""
    start_value = number(scalar(context, start))
    count_value = _count(context, count)
    if is_error(start_value) or is_error(count_value) or start_value < 1:
        return VALUE_ERROR
    source = text(scalar(context, value))
    index = int(start_value) - 1
    return source[index : index + count_value]


@register("LEN", min_args=1, max_args=1, argument_spec="text")
def length(context: Any, value: Any) -> int:
    """Return the character count of text."""
    return len(text(scalar(context, value)))


def _find(
    context: Any,
    needle: Any,
    haystack: Any,
    start: Any,
    *,
    case_sensitive: bool,
    wildcard: bool,
) -> Any:
    search_text = text(scalar(context, needle))
    source = text(scalar(context, haystack))
    start_value = number(scalar(context, start))
    if is_error(start_value) or start_value < 1 or start_value > len(source) + 1:
        return VALUE_ERROR
    offset = int(start_value) - 1
    try:
        if wildcard:
            pattern = re.escape(search_text)
            pattern = pattern.replace(r"\*", ".*").replace(r"\?", ".")
            match = re.search(pattern, source[offset:], flags=re.IGNORECASE)
            return VALUE_ERROR if match is None else offset + match.start() + 1
        if not case_sensitive:
            search_text = search_text.casefold()
            source = source.casefold()
        return source.index(search_text, offset) + 1
    except ValueError:
        return VALUE_ERROR


@register("FIND", min_args=2, max_args=3, argument_spec="find_text, within_text, [start_num]")
def find(context: Any, needle: Any, haystack: Any, start: Any = 1) -> Any:
    """Find case-sensitive text and return its one-based position."""
    return _find(
        context,
        needle,
        haystack,
        start,
        case_sensitive=True,
        wildcard=False,
    )


@register("SEARCH", min_args=2, max_args=3, argument_spec="find_text, within_text, [start_num]")
def search(context: Any, needle: Any, haystack: Any, start: Any = 1) -> Any:
    """Find case-insensitive wildcard text and return its position."""
    return _find(
        context,
        needle,
        haystack,
        start,
        case_sensitive=False,
        wildcard=True,
    )


@register(
    "SUBSTITUTE",
    min_args=3,
    max_args=4,
    argument_spec="text, old_text, new_text, [instance_num]",
)
def substitute(
    context: Any,
    source: Any,
    old: Any,
    new: Any,
    instance: Any = None,
) -> Any:
    """Replace matching text, optionally at one occurrence."""
    source_text = text(scalar(context, source))
    old_text = text(scalar(context, old))
    new_text = text(scalar(context, new))
    if instance is None:
        return source_text.replace(old_text, new_text)
    selected = number(scalar(context, instance))
    if is_error(selected) or selected < 1:
        return VALUE_ERROR
    occurrences = [match.start() for match in re.finditer(re.escape(old_text), source_text)]
    if int(selected) > len(occurrences):
        return source_text
    position = occurrences[int(selected) - 1]
    return source_text[:position] + new_text + source_text[position + len(old_text) :]


@register("REPLACE", min_args=4, max_args=4, argument_spec="old_text, start_num, num_chars, new_text")
def replace_function(
    context: Any,
    source: Any,
    start: Any,
    count: Any,
    new: Any,
) -> Any:
    """Replace a character span by position."""
    start_value = number(scalar(context, start))
    count_value = _count(context, count)
    if is_error(start_value) or is_error(count_value) or start_value < 1:
        return VALUE_ERROR
    source_text = text(scalar(context, source))
    index = int(start_value) - 1
    return source_text[:index] + text(scalar(context, new)) + source_text[index + count_value :]


@register("REPT", min_args=2, max_args=2, argument_spec="text, number_times")
def rept(context: Any, value: Any, count: Any) -> Any:
    """Repeat text a specified number of times."""
    selected = _count(context, count)
    if is_error(selected):
        return selected
    result = text(scalar(context, value)) * selected
    return VALUE_ERROR if len(result) > 32_767 else result


@register("TRIM", min_args=1, max_args=1, argument_spec="text")
def trim(context: Any, value: Any) -> str:
    """Remove leading, trailing, and repeated ASCII spaces."""
    return " ".join(text(scalar(context, value)).split())


@register("UPPER", min_args=1, max_args=1, argument_spec="text")
def upper(context: Any, value: Any) -> str:
    """Convert text to uppercase."""
    return text(scalar(context, value)).upper()


@register("LOWER", min_args=1, max_args=1, argument_spec="text")
def lower(context: Any, value: Any) -> str:
    """Convert text to lowercase."""
    return text(scalar(context, value)).lower()


@register("PROPER", min_args=1, max_args=1, argument_spec="text")
def proper(context: Any, value: Any) -> str:
    """Capitalize each word in text."""
    return re.sub(
        r"[A-Za-z]+(?:'[A-Za-z]+)?",
        lambda match: match.group(0)[0].upper() + match.group(0)[1:].lower(),
        text(scalar(context, value)),
    )


@register("TEXT", min_args=2, max_args=2, argument_spec="value, format_text")
def text_function(context: Any, value: Any, format_text: Any) -> Any:
    """Render a value with common worksheet number-format patterns."""
    selected = scalar(context, value)
    pattern = text(scalar(context, format_text))
    if any(token in pattern.lower() for token in ("yy", "mm", "dd", "hh", "ss")):
        converted_date = serial_datetime(selected)
        if is_error(converted_date):
            return converted_date
        replacements = {
            "yyyy": "%Y",
            "yy": "%y",
            "mmmm": "%B",
            "mmm": "%b",
            "mm": "%m",
            "dd": "%d",
            "hh": "%H",
            "ss": "%S",
        }
        rendered_pattern = pattern
        for source, target in replacements.items():
            rendered_pattern = rendered_pattern.replace(source, target)
        return converted_date.strftime(rendered_pattern)
    converted = number(selected)
    if is_error(converted):
        return converted
    if "%" in pattern:
        decimals = len(pattern.partition(".")[2].partition("%")[0]) if "." in pattern else 0
        return f"{converted * 100:.{decimals}f}%"
    decimals = len(pattern.partition(".")[2]) if "." in pattern else 0
    grouping = "," in pattern.partition(".")[0]
    return f"{converted:,.{decimals}f}" if grouping else f"{converted:.{decimals}f}"


@register("VALUE", min_args=1, max_args=1, argument_spec="text")
def value(context: Any, source: Any) -> Any:
    """Convert numeric text into a number."""
    source_text = text(scalar(context, source)).strip()
    percentage = source_text.endswith("%")
    normalized = re.sub(r"[$£€,\s]", "", source_text.removesuffix("%"))
    converted = number(normalized)
    if is_error(converted):
        converted_date = serial_datetime(source_text)
        return converted_date if is_error(converted_date) else VALUE_ERROR
    return converted / 100 if percentage else converted


@register(
    "NUMBERVALUE",
    min_args=1,
    max_args=3,
    argument_spec="text, [decimal_separator], [group_separator]",
)
def numbervalue(
    context: Any,
    source: Any,
    decimal_separator: Any = ".",
    group_separator: Any = ",",
) -> Any:
    """Convert locale-formatted numeric text into a number."""
    source_text = text(scalar(context, source))
    decimal = text(scalar(context, decimal_separator))
    grouping = text(scalar(context, group_separator))
    normalized = source_text.replace(grouping, "").replace(decimal, ".")
    return number(normalized)


@register("CHAR", min_args=1, max_args=1, argument_spec="number")
def char(context: Any, value: Any) -> Any:
    """Return the character represented by a code from 1 through 255."""
    converted = number(scalar(context, value))
    if is_error(converted) or not 1 <= converted <= 255:
        return VALUE_ERROR
    return chr(int(converted))


@register("CODE", min_args=1, max_args=1, argument_spec="text")
def code(context: Any, value: Any) -> Any:
    """Return the code of the first character in text."""
    source = text(scalar(context, value))
    return VALUE_ERROR if not source else ord(source[0])


@register("EXACT", min_args=2, max_args=2, argument_spec="text1, text2")
def exact(context: Any, left_value: Any, right_value: Any) -> bool:
    """Compare two text values case-sensitively."""
    return text(scalar(context, left_value)) == text(scalar(context, right_value))


@register(
    "TEXTSPLIT",
    min_args=2,
    max_args=3,
    argument_spec="text, col_delimiter, [row_delimiter]",
)
def textsplit(
    context: Any,
    source: Any,
    column_delimiter: Any,
    row_delimiter: Any = None,
) -> Any:
    """Split text into a dynamic row-and-column array."""
    source_text = text(scalar(context, source))
    column_text = text(scalar(context, column_delimiter))
    if not column_text:
        return VALUE_ERROR
    row_text = None if row_delimiter is None else text(scalar(context, row_delimiter))
    rows = source_text.split(row_text) if row_text else [source_text]
    split_rows = [row.split(column_text) for row in rows]
    width = max(len(row) for row in split_rows)
    return rectangular([row + [""] * (width - len(row)) for row in split_rows])


def _text_before_after(
    context: Any,
    source: Any,
    delimiter: Any,
    instance: Any,
    *,
    before: bool,
) -> Any:
    source_text = text(scalar(context, source))
    delimiter_text = text(scalar(context, delimiter))
    selected = number(scalar(context, instance))
    if not delimiter_text or is_error(selected) or selected == 0:
        return VALUE_ERROR
    positions = [match.start() for match in re.finditer(re.escape(delimiter_text), source_text)]
    index = int(selected) - 1 if selected > 0 else len(positions) + int(selected)
    if not 0 <= index < len(positions):
        return VALUE_ERROR
    position = positions[index]
    return source_text[:position] if before else source_text[position + len(delimiter_text) :]


@register("TEXTBEFORE", min_args=2, max_args=3, argument_spec="text, delimiter, [instance_num]")
def textbefore(context: Any, source: Any, delimiter: Any, instance: Any = 1) -> Any:
    """Return text before a selected delimiter occurrence."""
    return _text_before_after(context, source, delimiter, instance, before=True)


@register("TEXTAFTER", min_args=2, max_args=3, argument_spec="text, delimiter, [instance_num]")
def textafter(context: Any, source: Any, delimiter: Any, instance: Any = 1) -> Any:
    """Return text after a selected delimiter occurrence."""
    return _text_before_after(context, source, delimiter, instance, before=False)
