"""Domain-to-OpenPyXL XLSX writer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook as OpenPyxlWorkbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation as OpenPyxlValidation

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.core.data_tools import AutoFilter, DataValidation
from excelclone.core.workbook import Workbook


def write_xlsx(workbook: Workbook, path: str | Path) -> Path:
    """Write all supported workbook features to a standards-based XLSX file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    package = OpenPyxlWorkbook()
    package.remove(package.active)
    for source_sheet in workbook:
        worksheet = package.create_sheet(source_sheet.name)
        _write_worksheet(source_sheet, worksheet)
    package.active = workbook.active_sheet_index
    package.calculation.fullCalcOnLoad = True
    package.calculation.forceFullCalc = True
    package.calculation.calcMode = "auto"
    _write_defined_names(workbook, package)
    package.save(destination)
    package.close()
    return destination


def _write_worksheet(source: Any, worksheet: Any) -> None:
    for (row, column), source_cell in source.iter_populated():
        target = worksheet.cell(row=row + 1, column=column + 1)
        target.value = (
            source_cell.raw_input
            if source_cell.is_formula
            else source_cell.display_value
        )
        _write_cell_format(target, source_cell.format)

    for row, height in source.row_heights.items():
        worksheet.row_dimensions[row + 1].height = height
    for column, width in source.column_widths.items():
        worksheet.column_dimensions[get_column_letter(column + 1)].width = width
    for row in source.hidden_rows:
        worksheet.row_dimensions[row + 1].hidden = True
    for column in source.hidden_columns:
        worksheet.column_dimensions[get_column_letter(column + 1)].hidden = True
    for merged in source.merged_ranges:
        worksheet.merge_cells(merged.to_a1())
    if source.freeze_panes is not None:
        row, column = source.freeze_panes
        worksheet.freeze_panes = worksheet.cell(row=row + 1, column=column + 1)
    worksheet.sheet_state = "visible" if source.visible else "hidden"
    if source.tab_color:
        worksheet.sheet_properties.tabColor = _argb(source.tab_color)
    _write_validations(source, worksheet)
    _write_filter(source, worksheet)


def _write_cell_format(cell: Any, cell_format: CellFormat) -> None:
    if cell_format.is_default:
        return
    cell.number_format = cell_format.number_format
    cell.font = Font(
        name=cell_format.font_family,
        size=cell_format.font_size,
        bold=cell_format.bold,
        italic=cell_format.italic,
        underline="single" if cell_format.underline else None,
        color=_argb(cell_format.font_color),
    )
    if cell_format.fill_color:
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor=_argb(cell_format.fill_color),
        )
    cell.alignment = Alignment(
        horizontal=(
            None
            if cell_format.horizontal_alignment == "general"
            else cell_format.horizontal_alignment
        ),
        vertical=cell_format.vertical_alignment,
        wrap_text=cell_format.wrap_text,
    )
    cell.border = Border(
        left=_write_border(cell_format.left_border),
        right=_write_border(cell_format.right_border),
        top=_write_border(cell_format.top_border),
        bottom=_write_border(cell_format.bottom_border),
    )


def _write_border(border: BorderStyle) -> Side:
    if border.style == "none":
        return Side()
    return Side(style=border.style, color=_argb(border.color))


def _write_defined_names(workbook: Workbook, package: Any) -> None:
    for item in workbook.defined_names:
        defined_name = DefinedName(item.name, attr_text=item.reference.to_a1())
        if item.scope is None:
            package.defined_names.add(defined_name)
        else:
            package[item.scope].defined_names.add(defined_name)


def _write_validations(source: Any, worksheet: Any) -> None:
    type_names = {
        "whole_number": "whole",
        "decimal": "decimal",
        "date": "date",
        "text_length": "textLength",
        "list": "list",
        "custom": "custom",
    }
    operators = {
        "equal": "equal",
        "not_equal": "notEqual",
        "greater_than": "greaterThan",
        "greater_equal": "greaterThanOrEqual",
        "less_than": "lessThan",
        "less_equal": "lessThanOrEqual",
        "between": "between",
        "not_between": "notBetween",
    }
    for validation in source.data_validations:
        if not isinstance(validation, DataValidation):
            continue
        formula1: Any = None
        formula2: Any = None
        if validation.kind == "list":
            formula1 = '"' + ",".join(str(value) for value in validation.values) + '"'
        elif validation.kind == "custom":
            formula1 = (validation.formula or "").removeprefix("=")
        elif validation.values:
            formula1 = validation.values[0]
            formula2 = validation.values[1] if len(validation.values) > 1 else None
        rule = OpenPyxlValidation(
            type=type_names.get(validation.kind, "custom"),
            operator=operators.get(validation.operator),
            formula1=formula1,
            formula2=formula2,
            allow_blank=validation.allow_blank,
            prompt=validation.input_message or None,
            error=validation.error_message or None,
        )
        worksheet.add_data_validation(rule)
        rule.add(validation.range.to_a1())


def _write_filter(source: Any, worksheet: Any) -> None:
    auto_filter = source.auto_filter
    if not isinstance(auto_filter, AutoFilter):
        return
    worksheet.auto_filter.ref = auto_filter.range.to_a1()
    column_offset = auto_filter.column - auto_filter.range.min_column
    worksheet.auto_filter.add_filter_column(
        column_offset,
        [str(value) for value in auto_filter.allowed_values],
    )


def _argb(color: str) -> str:
    normalized = color.lstrip("#")
    return normalized.upper() if len(normalized) == 8 else "FF" + normalized.upper()
