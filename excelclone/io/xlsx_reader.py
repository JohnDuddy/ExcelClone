"""OpenPyXL-to-domain XLSX reader with explicit loss warnings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles.colors import COLOR_INDEX

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import CellReference, parse_a1
from excelclone.core.tokenizer import FormulaSyntaxError
from excelclone.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class WorkbookLoadResult:
    """Loaded workbook and user-visible dropped-feature warnings."""

    workbook: Workbook
    warnings: tuple[str, ...]


def read_xlsx(path: str | Path) -> WorkbookLoadResult:
    """Read the supported XLSX subset without silently dropping other content."""
    source = Path(path)
    warnings: list[str] = []
    if source.suffix.lower() == ".xlsm":
        warnings.append("VBA macros are not supported and were dropped.")
    package = load_workbook(
        source,
        data_only=False,
        read_only=False,
        keep_vba=False,
        keep_links=False,
    )
    workbook = Workbook(create_default=False)
    for worksheet in package.worksheets:
        sheet = workbook.add_sheet(worksheet.title)
        _read_worksheet(worksheet, sheet, warnings)

    if not len(workbook):
        package.close()
        raise ValueError("XLSX workbook contains no worksheets")
    workbook.active_sheet = min(package.index(package.active), len(workbook) - 1)
    _read_defined_names(package, workbook, warnings)
    if getattr(package, "_external_links", None):
        warnings.append("External workbook links are not supported and were dropped.")
    package.close()

    try:
        FormulaEngine(workbook).recalculate()
    except (FormulaSyntaxError, ValueError) as error:
        warnings.append(
            "One or more formulas use unsupported syntax and could not be "
            f"recalculated: {error}"
        )
    return WorkbookLoadResult(workbook, tuple(dict.fromkeys(warnings)))


def _read_worksheet(worksheet: Any, sheet: Any, warnings: list[str]) -> None:
    for cell in worksheet._cells.values():
        if isinstance(cell, MergedCell):
            continue
        cell_format = _read_cell_format(cell)
        if cell.value is None and cell_format.is_default:
            continue
        sheet.set_cell(
            cell.row - 1,
            cell.column - 1,
            cell.value,
            cell_format=cell_format,
        )
        if cell.comment is not None:
            warnings.append(
                f"Comments on sheet {worksheet.title!r} are not supported and were dropped."
            )
        if cell.hyperlink is not None:
            warnings.append(
                f"Hyperlinks on sheet {worksheet.title!r} are not supported and were dropped."
            )

    for index, dimension in worksheet.row_dimensions.items():
        row = int(index) - 1
        if dimension.height is not None:
            sheet.row_heights[row] = float(dimension.height)
        if dimension.hidden:
            sheet.hidden_rows.add(row)
    for label, dimension in worksheet.column_dimensions.items():
        reference = parse_a1(f"{label}1")
        if not isinstance(reference, CellReference):
            continue
        column = reference.column
        if dimension.width is not None:
            sheet.column_widths[column] = float(dimension.width)
        if dimension.hidden:
            sheet.hidden_columns.add(column)

    sheet.merged_ranges = [
        parse_a1(str(merged)) for merged in worksheet.merged_cells.ranges
    ]
    if worksheet.freeze_panes:
        reference = parse_a1(str(worksheet.freeze_panes))
        if isinstance(reference, CellReference):
            sheet.freeze_panes = (reference.row, reference.column)
    sheet.visible = worksheet.sheet_state == "visible"
    if worksheet.sheet_state == "veryHidden":
        warnings.append(
            f"Very-hidden sheet {worksheet.title!r} was imported as hidden."
        )
    sheet.tab_color = _read_color(worksheet.sheet_properties.tabColor, None)

    if getattr(worksheet, "_charts", None):
        warnings.append(
            f"Charts on sheet {worksheet.title!r} are not supported and were dropped."
        )
    if getattr(worksheet, "_images", None):
        warnings.append(
            f"Images on sheet {worksheet.title!r} are not supported and were dropped."
        )
    if getattr(worksheet, "_pivots", None):
        warnings.append(
            f"Pivot tables on sheet {worksheet.title!r} are not supported and were dropped."
        )
    if worksheet.tables:
        warnings.append(
            f"Structured tables on sheet {worksheet.title!r} were imported as cells."
        )
    if len(worksheet.conditional_formatting):
        warnings.append(
            f"XLSX conditional formatting on sheet {worksheet.title!r} was dropped."
        )
    if worksheet.data_validations.count:
        warnings.append(
            f"Data validation on sheet {worksheet.title!r} was dropped."
        )


def _read_cell_format(cell: Any) -> CellFormat:
    if not cell.has_style:
        return CellFormat()
    return CellFormat(
        number_format=cell.number_format or "General",
        font_family=cell.font.name or "Aptos",
        font_size=float(cell.font.sz or 11),
        bold=bool(cell.font.bold),
        italic=bool(cell.font.italic),
        underline=bool(cell.font.underline),
        font_color=_read_color(cell.font.color, "#000000") or "#000000",
        fill_color=(
            _read_color(cell.fill.fgColor, None)
            if cell.fill.fill_type == "solid"
            else None
        ),
        horizontal_alignment=cell.alignment.horizontal or "general",
        vertical_alignment=cell.alignment.vertical or "bottom",
        wrap_text=bool(cell.alignment.wrap_text),
        left_border=_read_border(cell.border.left),
        right_border=_read_border(cell.border.right),
        top_border=_read_border(cell.border.top),
        bottom_border=_read_border(cell.border.bottom),
    )


def _read_border(side: Any) -> BorderStyle:
    return BorderStyle(
        side.style or "none",
        _read_color(side.color, "#000000") or "#000000",
    )


def _read_color(color: Any, default: str | None) -> str | None:
    if color is None:
        return default
    kind = getattr(color, "type", None)
    if kind == "rgb":
        value = getattr(color, "rgb", None)
        if isinstance(value, str) and len(value) >= 6:
            return "#" + value[-6:].lower()
    if kind == "indexed":
        index = getattr(color, "indexed", None)
        if isinstance(index, int) and 0 <= index < len(COLOR_INDEX):
            return "#" + COLOR_INDEX[index][-6:].lower()
    return default


def _read_defined_names(
    package: Any,
    workbook: Workbook,
    warnings: list[str],
) -> None:
    for defined_name in package.defined_names.values():
        _read_defined_name(defined_name, workbook, None, warnings)
    for worksheet in package.worksheets:
        for defined_name in worksheet.defined_names.values():
            _read_defined_name(defined_name, workbook, worksheet.title, warnings)


def _read_defined_name(
    defined_name: Any,
    workbook: Workbook,
    scope: str | None,
    warnings: list[str],
) -> None:
    text = defined_name.attr_text
    if not text or defined_name.name.startswith("_xlnm."):
        return
    try:
        reference = parse_a1(text)
        workbook.define_name(defined_name.name, reference, scope=scope)
    except ValueError:
        warnings.append(
            f"Defined name {defined_name.name!r} is not a simple cell range and was dropped."
        )
