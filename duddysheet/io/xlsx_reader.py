"""OpenPyXL-to-domain XLSX reader with explicit loss warnings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula
from openpyxl.styles.colors import COLOR_INDEX

from duddysheet.core.cell import BorderStyle, CellFormat, Hyperlink
from duddysheet.core.data_tools import DataValidation, apply_filter
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import CellReference, parse_a1
from duddysheet.core.tokenizer import FormulaSyntaxError
from duddysheet.core.workbook import Workbook
from duddysheet.io.formula_compat import from_xlsx_formula
from duddysheet.io.xlsx_features import (
    read_cell_extras,
    read_sheet_extras,
    read_workbook_extras,
)


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
    read_workbook_extras(package, workbook)
    calculation = getattr(package, "calculation", None)
    if calculation is not None:
        workbook.calculation_mode = {
            "manual": "manual",
            "autoNoTable": "automatic_except_tables",
        }.get(getattr(calculation, "calcMode", None) or "auto", "automatic")
        workbook.iterative_calculation = bool(getattr(calculation, "iterate", False))
        if getattr(calculation, "iterateCount", None):
            workbook.max_iterations = int(calculation.iterateCount)
        if getattr(calculation, "iterateDelta", None):
            workbook.max_change = float(calculation.iterateDelta)
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


def _array_formula_cells(worksheet: Any) -> set[tuple[int, int]]:
    """Cells covered by array formulas other than their anchors (spill results)."""
    covered: set[tuple[int, int]] = set()
    for cell in worksheet._cells.values():
        value = getattr(cell, "value", None)
        if not isinstance(value, ArrayFormula) or not value.ref:
            continue
        try:
            reference = parse_a1(value.ref)
        except ValueError:
            continue
        if isinstance(reference, CellReference):
            continue
        for item in reference:
            if (item.row, item.column) != (cell.row - 1, cell.column - 1):
                covered.add((item.row, item.column))
    return covered


def _read_data_tables(worksheet: Any, sheet: Any) -> None:
    """Recreate What-If data tables from dataTable formulas."""
    from duddysheet.core.data_table import DataTableSpec, table_formula

    for cell in list(worksheet._cells.values()):
        value = getattr(cell, "value", None)
        if not isinstance(value, DataTableFormula):
            continue
        try:
            area = parse_a1(value.ref)
        except ValueError:
            continue
        if isinstance(area, CellReference):
            top = bottom = area.row
            left = right = area.column
        else:
            top, left, bottom, right = area.min_row, area.min_column, area.max_row, area.max_column

        def address(text: Any) -> tuple[str, int, int] | None:
            if not text:
                return None
            reference = parse_a1(str(text))
            return (sheet.name, reference.row, reference.column) if isinstance(reference, CellReference) else None

        two = str(value.dt2D) in ("1", "True", "true")
        row_flag = str(value.dtr) in ("1", "True", "true")
        if two:
            spec = DataTableSpec(top - 1, left - 1, bottom, right, address(value.r1), address(value.r2))
        elif row_flag:
            spec = DataTableSpec(top - 1, left - 1, bottom, right, address(value.r1), None)
        else:
            spec = DataTableSpec(top - 1, left - 1, bottom, right, None, address(value.r1))
        sheet.data_tables.append(spec)
        formula = table_formula(spec, sheet.name)
        for row in range(top, bottom + 1):
            for column in range(left, right + 1):
                sheet.set_cell(row, column, formula, cell_format=sheet.get_cell(row, column).format)


def _read_worksheet(worksheet: Any, sheet: Any, warnings: list[str]) -> None:
    spill_results = _array_formula_cells(worksheet)
    for cell in worksheet._cells.values():
        if isinstance(cell, MergedCell):
            continue
        cell_format = read_cell_extras(cell, _read_cell_format(cell))
        hyperlink = _read_hyperlink(cell)
        value = cell.value
        if (cell.row - 1, cell.column - 1) in spill_results:
            # Excel caches spilled values; the anchor formula recreates them.
            value = None
        if value is None and cell_format.is_default and hyperlink is None:
            continue
        if isinstance(value, DataTableFormula):
            continue
        if isinstance(value, ArrayFormula):
            value = value.text if value.text.startswith("=") else "=" + value.text
        if isinstance(value, str) and value.startswith("="):
            value = from_xlsx_formula(value)
        sheet.set_cell(
            cell.row - 1,
            cell.column - 1,
            value,
            cell_format=cell_format,
            hyperlink=hyperlink,
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
            f"PivotTables on sheet {worksheet.title!r} were imported as values. "
            "Use Insert > PivotTable to rebuild them as refreshable PivotTables."
        )
    read_sheet_extras(worksheet, sheet, warnings)
    _read_data_tables(worksheet, sheet)
    _read_validations(worksheet, sheet, warnings)
    _read_filter(worksheet, sheet, warnings)


def _read_hyperlink(cell: Any) -> Hyperlink | None:
    source = cell.hyperlink
    if source is None:
        return None
    location = getattr(source, "location", None)
    tooltip = getattr(source, "tooltip", None)
    if location:
        return Hyperlink(str(location).removeprefix("#"), True, tooltip)
    target = getattr(source, "target", None)
    if not target:
        return None
    text = str(target)
    if text.startswith("#"):
        return Hyperlink(text[1:], True, tooltip)
    return Hyperlink(text, False, tooltip)


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
    if side is None:
        return BorderStyle()
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
    comment = getattr(defined_name, "comment", None) or ""
    try:
        reference = parse_a1(text)
        workbook.define_name(defined_name.name, reference, scope=scope, comment=comment)
        return
    except ValueError:
        pass
    try:
        workbook.define_name(
            defined_name.name,
            "=" + from_xlsx_formula(text),
            scope=scope,
            comment=comment,
        )
    except ValueError:
        warnings.append(
            f"Defined name {defined_name.name!r} uses an unsupported formula and was dropped."
        )


def _read_validations(
    worksheet: Any,
    sheet: Any,
    warnings: list[str],
) -> None:
    kind_names = {
        "whole": "whole_number",
        "decimal": "decimal",
        "date": "date",
        "textLength": "text_length",
        "list": "list",
        "custom": "custom",
    }
    operators = {
        "equal": "equal",
        "notEqual": "not_equal",
        "greaterThan": "greater_than",
        "greaterThanOrEqual": "greater_equal",
        "lessThan": "less_than",
        "lessThanOrEqual": "less_equal",
        "between": "between",
        "notBetween": "not_between",
    }
    for source in worksheet.data_validations.dataValidation:
        kind = kind_names.get(source.type)
        if kind is None:
            warnings.append(
                f"Unsupported validation type {source.type!r} on "
                f"sheet {worksheet.title!r} was dropped."
            )
            continue
        values: tuple[Any, ...] = ()
        formula: str | None = None
        if kind == "list":
            text = str(source.formula1 or "")
            if text.startswith('"') and text.endswith('"'):
                values = tuple(text[1:-1].split(","))
            else:
                warnings.append(
                    f"Range-based validation list on sheet "
                    f"{worksheet.title!r} was dropped."
                )
                continue
        elif kind == "custom":
            formula = "=" + str(source.formula1 or "").removeprefix("=")
        else:
            values = tuple(
                _parse_validation_scalar(value)
                for value in (source.formula1, source.formula2)
                if value is not None
            )
        for target in source.sqref.ranges:
            sheet.data_validations.append(
                DataValidation(
                    parse_a1(str(target)),
                    kind,
                    operators.get(source.operator, "between"),
                    values,
                    formula,
                    bool(source.allow_blank),
                    source.prompt or "",
                    source.error
                    or "The value does not satisfy this cell's validation rule.",
                )
            )


def _read_filter(
    worksheet: Any,
    sheet: Any,
    warnings: list[str],
) -> None:
    reference = worksheet.auto_filter.ref
    columns = worksheet.auto_filter.filterColumn
    if not reference or not columns:
        return
    if len(columns) > 1:
        warnings.append(
            f"Only the first autofilter column on sheet "
            f"{worksheet.title!r} was imported."
        )
    target = parse_a1(reference)
    if not hasattr(target, "min_column"):
        return
    source = columns[0]
    values = {
        _parse_validation_scalar(value)
        for value in source.filters.filter
    }
    apply_filter(
        sheet,
        target,
        column=target.min_column + int(source.colId),
        allowed_values=values,
        has_header=True,
    )


def _parse_validation_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    upper = value.upper()
    if upper in ("TRUE", "FALSE"):
        return upper == "TRUE"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
