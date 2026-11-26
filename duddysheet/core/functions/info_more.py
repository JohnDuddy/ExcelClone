"""Excel information functions that inspect cells, sheets, and the environment."""

from __future__ import annotations

import math
from typing import Any

from duddysheet.core.errors import NA_ERROR, REF_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions.common import number, scalar, text

INFO = "Information"


def _areas(value: Any) -> tuple[Any, ...] | None:
    return getattr(value, "areas", None)


def _first_cell(context: Any, value: Any) -> Any:
    from duddysheet.core.refs import CellReference

    areas = _areas(value)
    if not areas:
        return None
    area = areas[0]
    reference = area if isinstance(area, CellReference) else area.start
    sheet_name = reference.sheet or context.sheet_name
    try:
        sheet = context.evaluator.workbook.get_sheet(sheet_name)
    except KeyError:
        return None
    return sheet, reference


def _integer(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, str) or value is None:
        return VALUE_ERROR if value is not None else 0
    converted = number(value)
    if is_error(converted):
        return converted
    return math.trunc(converted)


@register(
    "ISEVEN",
    min_args=1,
    max_args=1,
    argument_spec="number",
    lift=lift_all,
    category=INFO,
)
def iseven(context: Any, value: Any) -> Any:
    """Return TRUE when a number is even."""
    converted = _integer(scalar(context, value))
    return converted if is_error(converted) else converted % 2 == 0


@register(
    "ISODD",
    min_args=1,
    max_args=1,
    argument_spec="number",
    lift=lift_all,
    category=INFO,
)
def isodd(context: Any, value: Any) -> Any:
    """Return TRUE when a number is odd."""
    converted = _integer(scalar(context, value))
    return converted if is_error(converted) else converted % 2 == 1


@register(
    "ISNONTEXT",
    min_args=1,
    max_args=1,
    argument_spec="value",
    lift=lift_all,
    accepts_errors=True,
    category=INFO,
)
def isnontext(context: Any, value: Any) -> Any:
    """Return TRUE when a value is not text, including blanks and errors."""
    return not isinstance(scalar(context, value), str)


@register(
    "ISREF",
    min_args=1,
    max_args=1,
    argument_spec="value",
    accepts_errors=True,
    category=INFO,
)
def isref(context: Any, value: Any) -> Any:
    """Return TRUE when a value is a reference."""
    return bool(_areas(value))


@register(
    "ISFORMULA",
    min_args=1,
    max_args=1,
    argument_spec="reference",
    lift=lift_all,
    category=INFO,
)
def isformula(context: Any, reference: Any) -> Any:
    """Return TRUE when a referenced cell contains a formula."""
    located = _first_cell(context, reference)
    if located is None:
        return VALUE_ERROR if not _areas(reference) else REF_ERROR
    sheet, cell_reference = located
    cell = sheet.get_cell(cell_reference.row, cell_reference.column)
    if cell.is_spill:
        return True
    return cell.is_formula


@register(
    "FORMULATEXT",
    min_args=1,
    max_args=1,
    argument_spec="reference",
    lift=lift_all,
    category=INFO,
)
def formulatext(context: Any, reference: Any) -> Any:
    """Return the formula in a referenced cell as text."""
    located = _first_cell(context, reference)
    if located is None:
        return NA_ERROR if not _areas(reference) else REF_ERROR
    sheet, cell_reference = located
    cell = sheet.get_cell(cell_reference.row, cell_reference.column)
    return cell.raw_input if cell.is_formula else NA_ERROR


@register("SHEET", min_args=0, max_args=1, argument_spec="[value]", category=INFO)
def sheet_function(context: Any, value: Any = None) -> Any:
    """Return the sheet number of a reference or sheet name."""
    workbook = context.evaluator.workbook
    if value is None:
        return workbook.index_of(context.sheet_name) + 1
    areas = _areas(value)
    if areas:
        sheet_name = areas[0].sheet or context.sheet_name
    else:
        selected = scalar(context, value)
        if is_error(selected):
            return selected
        if not isinstance(selected, str):
            return NA_ERROR
        sheet_name = selected
    try:
        return workbook.index_of(sheet_name) + 1
    except (KeyError, ValueError):
        return NA_ERROR


@register("SHEETS", min_args=0, max_args=1, argument_spec="[reference]", category=INFO)
def sheets_function(context: Any, reference: Any = None) -> Any:
    """Return the number of sheets in a reference, or in the workbook."""
    workbook = context.evaluator.workbook
    if reference is None:
        return len(workbook)
    areas = _areas(reference)
    if not areas:
        return VALUE_ERROR
    return len({(area.sheet or context.sheet_name).casefold() for area in areas})


def _format_code(number_format: str) -> str:
    """Return CELL("format") codes for a number format."""
    code = number_format.strip()
    lower = code.lower()
    if code in ("General", ""):
        return "G"
    negative_parens = "(" in code.split(";")[1] if ";" in code else False
    suffix = "-" if "[red]" in lower else ""
    suffix += "()" if negative_parens else ""
    if any(token in lower for token in ("d", "y")) and "0" not in lower:
        if "mmm" in lower and "y" in lower and "d" in lower:
            return "D1"
        if "mmm" in lower and "d" in lower:
            return "D2"
        if "mmm" in lower:
            return "D3"
        return "D4"
    if "h" in lower or "s" in lower:
        if "am/pm" in lower:
            return "D7" if "s" in lower else "D6"
        return "D8" if "s" in lower else "D9"
    decimals = sum(character == "0" for character in code.split(".")[1].split(";")[0]) if "." in code else 0
    if "%" in code:
        return f"P{decimals}{suffix}"
    if "e+" in lower:
        return f"S{decimals}{suffix}"
    if "$" in code:
        return f"C{decimals}{suffix}"
    if "," in code:
        return f",{decimals}{suffix}"
    return f"F{decimals}{suffix}"


@register(
    "CELL",
    min_args=1,
    max_args=2,
    argument_spec="info_type, [reference]",
    category=INFO,
)
def cell_function(context: Any, info_type: Any, reference: Any = None) -> Any:
    """Return formatting, location, or contents information about a cell."""
    from duddysheet.core.refs import CellReference, index_to_column, quote_sheet_name

    kind = text(scalar(context, info_type)).strip().lower()
    if reference is None:
        sheet = context.evaluator.workbook.get_sheet(context.sheet_name)
        cell_reference = CellReference(context.origin[0], context.origin[1])
    else:
        located = _first_cell(context, reference)
        if located is None:
            return VALUE_ERROR
        sheet, cell_reference = located
    row, column = cell_reference.row, cell_reference.column
    cell = sheet.get_cell(row, column)
    value = cell.display_value
    if cell.error is not None:
        from duddysheet.core.errors import error_from_literal

        value = error_from_literal(cell.error)
    if kind == "address":
        return f"${index_to_column(column)}${row + 1}"
    if kind == "col":
        return column + 1
    if kind == "row":
        return row + 1
    if kind == "contents":
        return 0 if value is None else value
    if kind == "type":
        if cell.raw_input is None and cell.cached_value is None:
            return "b"
        return "l" if isinstance(value, str) else "v"
    if kind == "prefix":
        if not isinstance(value, str):
            return ""
        alignment = cell.format.horizontal_alignment
        return {"left": "'", "right": '"', "center": "^", "fill": "\\"}.get(alignment, "'")
    if kind == "format":
        return _format_code(cell.format.number_format)
    if kind == "color":
        return 1 if "[red]" in cell.format.number_format.lower() else 0
    if kind == "parentheses":
        parts = cell.format.number_format.split(";")
        return 1 if parts and "(" in parts[0] else 0
    if kind == "width":
        width = sheet.column_widths.get(column)
        characters = 8 if width is None else max(0, round(width / 7.5))
        return characters
    if kind == "protect":
        return 1 if getattr(cell.format, "locked", True) else 0
    if kind == "filename":
        return f"[Book1]{sheet.name}"
    if kind == "sheetname":
        return quote_sheet_name(sheet.name)
    return VALUE_ERROR


@register("INFO", min_args=1, max_args=1, argument_spec="type_text", category=INFO)
def info_function(context: Any, type_text: Any) -> Any:
    """Return information about the current operating environment."""
    kind = text(scalar(context, type_text)).strip().lower()
    workbook = context.evaluator.workbook
    if kind == "directory":
        from pathlib import Path

        return str(Path.home()) + "\\"
    if kind == "numfile":
        return len(workbook)
    if kind == "origin":
        return "$A:$A$1"
    if kind == "osversion":
        return "Windows (64-bit) NT 10.00"
    if kind == "recalc":
        return "Automatic"
    if kind == "release":
        return "16.0"
    if kind == "system":
        return "pcdos"
    return VALUE_ERROR

