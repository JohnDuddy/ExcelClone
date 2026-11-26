"""XLSX translation of notes, protection, outlines, axis formats, and conditional rules.

Kept apart from the core reader and writer so each Excel feature's mapping
to openpyxl lives in one place.
"""

from __future__ import annotations

from typing import Any

from openpyxl.comments import Comment
from openpyxl.formatting.rule import (
    CellIsRule,
    ColorScaleRule,
    DataBarRule,
    FormulaRule,
    IconSetRule,
    Rule,
)
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter
from openpyxl.workbook.protection import WorkbookProtection

from duddysheet.core.cell import CellFormat, Note, SheetProtection
from duddysheet.core.conditional import ConditionalRule, FormatPatch
from duddysheet.core.protection import PROTECTION_OPTIONS, stored_from_xlsx, xlsx_attributes
from duddysheet.core.refs import CellReference, RangeReference, parse_a1

_OPERATORS = {
    "equal": "equal",
    "not_equal": "notEqual",
    "greater": "greaterThan",
    "less": "lessThan",
    "greater_equal": "greaterThanOrEqual",
    "less_equal": "lessThanOrEqual",
    "between": "between",
    "not_between": "notBetween",
}
_PROTECTION_XLSX = {
    "select_locked_cells": "selectLockedCells",
    "select_unlocked_cells": "selectUnlockedCells",
    "format_cells": "formatCells",
    "format_columns": "formatColumns",
    "format_rows": "formatRows",
    "insert_columns": "insertColumns",
    "insert_rows": "insertRows",
    "insert_hyperlinks": "insertHyperlinks",
    "delete_columns": "deleteColumns",
    "delete_rows": "deleteRows",
    "sort": "sort",
    "auto_filter": "autoFilter",
    "edit_objects": "objects",
}


def _argb(color: str) -> str:
    return "FF" + color.lstrip("#").upper()[-6:]


# ----------------------------------------------------------------- writing
def write_cell_extras(target: Any, cell_format: CellFormat) -> None:
    """Add the format attributes the base writer does not set."""
    if cell_format.strikethrough:
        font = target.font.copy(strike=True)
        target.font = font
    if cell_format.indent or cell_format.text_rotation or cell_format.shrink_to_fit:
        alignment = target.alignment
        target.alignment = Alignment(
            horizontal=alignment.horizontal,
            vertical=alignment.vertical,
            wrap_text=alignment.wrap_text,
            indent=cell_format.indent,
            text_rotation=cell_format.text_rotation % 256,
            shrink_to_fit=cell_format.shrink_to_fit,
        )
    if not cell_format.locked or cell_format.formula_hidden:
        target.protection = Protection(
            locked=cell_format.locked,
            hidden=cell_format.formula_hidden,
        )


def _dimension_style(dimension: Any, cell_format: CellFormat) -> None:
    dimension.number_format = cell_format.number_format
    dimension.font = Font(
        name=cell_format.font_family,
        size=cell_format.font_size,
        bold=cell_format.bold,
        italic=cell_format.italic,
        underline="single" if cell_format.underline else None,
        strike=cell_format.strikethrough,
        color=_argb(cell_format.font_color),
    )
    if cell_format.fill_color:
        dimension.fill = PatternFill(fill_type="solid", fgColor=_argb(cell_format.fill_color))


def write_sheet_extras(source: Any, worksheet: Any) -> None:
    """Write notes, outlines, axis formats, protection, and conditional rules."""
    threads = getattr(source, "comments", {}) or {}
    for (row, column), note in source.notes.items():
        if (row, column) in threads:
            continue  # Excel keeps one comment per cell; the thread wins.
        comment = Comment(note.text, note.author or "Author")
        comment.width = 200
        comment.height = 100
        worksheet.cell(row=row + 1, column=column + 1).comment = comment
    if threads:
        from duddysheet.io.xlsx_comments import legacy_comment

        for (row, column), thread in threads.items():
            worksheet.cell(row=row + 1, column=column + 1).comment = legacy_comment(source.name, row, column, thread)
    for row, level in source.row_outline.items():
        worksheet.row_dimensions[row + 1].outlineLevel = level
    for column, level in source.column_outline.items():
        worksheet.column_dimensions[get_column_letter(column + 1)].outlineLevel = level
    for column, cell_format in source.column_formats.items():
        _dimension_style(worksheet.column_dimensions[get_column_letter(column + 1)], cell_format)
    for row, cell_format in source.row_formats.items():
        _dimension_style(worksheet.row_dimensions[row + 1], cell_format)
    if source.default_column_width:
        worksheet.sheet_format.defaultColWidth = source.default_column_width
    if source.default_row_height:
        worksheet.sheet_format.defaultRowHeight = source.default_row_height
    protection = source.protection
    if isinstance(protection, SheetProtection):
        worksheet.protection.sheet = True
        for name, attribute in _PROTECTION_XLSX.items():
            allowed = getattr(protection, name)
            # In XLSX these flags mean "this action is locked".
            setattr(worksheet.protection, attribute, not allowed)
        for attribute, value in xlsx_attributes(protection.password_hash).items():
            setattr(worksheet.protection, attribute, value)
    for table in source.tables:
        write_table(source, worksheet, table)
    for rule in source.conditional_formats:
        if isinstance(rule, ConditionalRule):
            converted = _conditional_to_xlsx(rule)
            if converted is not None:
                worksheet.conditional_formatting.add(rule.range.to_a1(), converted)


def write_workbook_extras(workbook: Any, package: Any) -> None:
    """Write workbook structure protection."""
    if workbook.structure_protected:
        security = WorkbookProtection(lockStructure=True)
        attributes = xlsx_attributes(workbook.structure_password_hash)
        if "hashValue" in attributes:
            security.workbookAlgorithmName = attributes["algorithmName"]
            security.workbookHashValue = attributes["hashValue"]
            security.workbookSaltValue = attributes["saltValue"]
            security.workbookSpinCount = attributes["spinCount"]
        elif "password" in attributes:
            security.workbookPassword = attributes["password"]
        package.security = security


def _differential(patch: FormatPatch) -> DifferentialStyle:
    font = None
    if patch.bold is not None or patch.italic is not None or patch.font_color is not None:
        font = Font(
            bold=patch.bold,
            italic=patch.italic,
            color=_argb(patch.font_color) if patch.font_color else None,
        )
    fill = (
        PatternFill(bgColor=_argb(patch.fill_color), fill_type="solid")
        if patch.fill_color
        else None
    )
    return DifferentialStyle(font=font, fill=fill)


def _conditional_to_xlsx(rule: ConditionalRule) -> Any:
    if rule.kind == "color_scale":
        colors = [_argb(color) for color in rule.colors]
        if len(colors) >= 3:
            return ColorScaleRule(
                start_type="min",
                start_color=colors[0],
                mid_type="percentile",
                mid_value=50,
                mid_color=colors[1],
                end_type="max",
                end_color=colors[2],
            )
        return ColorScaleRule(start_type="min", start_color=colors[0], end_type="max", end_color=colors[-1])
    if rule.kind == "data_bar":
        return DataBarRule(start_type="min", end_type="max", color=_argb(rule.colors[0] if rule.colors else "#638ec6"))
    if rule.kind == "icon_set":
        return IconSetRule("3TrafficLights1", "percent", [0, 33, 67])
    style = _differential(rule.format_patch)
    if rule.kind == "cell_value":
        operator = _OPERATORS.get(rule.operator)
        if operator is None:
            return None
        values = [_formula_value(value) for value in rule.values]
        return CellIsRule(operator=operator, formula=values, font=style.font, fill=style.fill)
    if rule.kind == "formula" and rule.formula:
        return FormulaRule(formula=[rule.formula.removeprefix("=")], font=style.font, fill=style.fill)
    if rule.kind == "top_bottom":
        xlsx_rule = Rule(type="top10", dxf=style, rank=rule.rank, percent=rule.percent, bottom=not rule.above)
        return xlsx_rule
    if rule.kind == "above_average":
        return Rule(type="aboveAverage", dxf=style, aboveAverage=rule.above)
    if rule.kind == "duplicate":
        return Rule(type="duplicateValues", dxf=style)
    return None


def _formula_value(value: Any) -> str:
    if isinstance(value, str):
        return value.removeprefix("=") if value.startswith("=") else '"' + value.replace('"', '""') + '"'
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


# ----------------------------------------------------------------- reading
def read_cell_extras(cell: Any, base: CellFormat) -> CellFormat:
    """Return ``base`` with the XLSX attributes the base reader ignores."""
    if not cell.has_style:
        return base
    from dataclasses import replace

    alignment = cell.alignment
    protection = cell.protection
    return replace(
        base,
        strikethrough=bool(cell.font.strike),
        indent=int(alignment.indent or 0),
        text_rotation=int(alignment.text_rotation or 0),
        shrink_to_fit=bool(alignment.shrink_to_fit),
        locked=True if protection is None or protection.locked is None else bool(protection.locked),
        formula_hidden=bool(protection.hidden) if protection is not None else False,
    )


def _dimension_format(dimension: Any) -> CellFormat | None:
    if not getattr(dimension, "customFormat", False) and dimension.style_id == 0:
        return None
    font = dimension.font
    fill = dimension.fill
    from duddysheet.io.xlsx_reader import _read_color

    return CellFormat(
        number_format=dimension.number_format or "General",
        font_family=font.name or "Aptos",
        font_size=float(font.sz or 11),
        bold=bool(font.b),
        italic=bool(font.i),
        underline=bool(font.u),
        strikethrough=bool(font.strike),
        font_color=_read_color(font.color, "#000000") or "#000000",
        fill_color=_read_color(fill.fgColor, None) if fill.fill_type == "solid" else None,
    )


def read_sheet_extras(worksheet: Any, sheet: Any, warnings: list[str]) -> None:
    """Read notes, outlines, axis formats, protection, and conditional rules."""
    for cell in worksheet._cells.values():
        comment = getattr(cell, "comment", None)
        if comment is not None and comment.text:
            author = comment.author or ""
            text = comment.text
            prefix = f"{author}:\n"
            if author and text.startswith(prefix):
                text = text[len(prefix) :]
            sheet.notes[(cell.row - 1, cell.column - 1)] = Note(text, author)
    for index, dimension in worksheet.row_dimensions.items():
        if dimension.outlineLevel:
            sheet.row_outline[int(index) - 1] = int(dimension.outlineLevel)
        cell_format = _dimension_format(dimension)
        if cell_format is not None and cell_format != CellFormat():
            sheet.row_formats[int(index) - 1] = cell_format
    for label, dimension in worksheet.column_dimensions.items():
        reference = parse_a1(f"{label}1")
        if not isinstance(reference, CellReference):
            continue
        first = reference.column
        last = (dimension.max or first + 1) - 1 if dimension.max else first
        for column in range(first, max(first, last) + 1):
            if dimension.outlineLevel:
                sheet.column_outline[column] = int(dimension.outlineLevel)
            cell_format = _dimension_format(dimension)
            if cell_format is not None and cell_format != CellFormat():
                sheet.column_formats[column] = cell_format
    protection = worksheet.protection
    if protection is not None and protection.sheet:
        values = {
            name: not bool(getattr(protection, attribute))
            for name, attribute in _PROTECTION_XLSX.items()
        }
        stored = stored_from_xlsx(
            protection.algorithmName,
            protection.hashValue,
            protection.saltValue,
            protection.spinCount,
            protection.password,
        )
        sheet.protection = SheetProtection(password_hash=stored, **{
            name: values[name] for name in PROTECTION_OPTIONS
        })
    for table in worksheet.tables.values():
        spec = read_table(sheet, table)
        if spec is not None:
            sheet.tables.append(spec)
    for conditional in worksheet.conditional_formatting:
        for xlsx_rule in conditional.rules:
            for area in str(conditional.sqref).split():
                rule = _conditional_from_xlsx(area, xlsx_rule)
                if rule is None:
                    warnings.append(
                        f"A {xlsx_rule.type!r} conditional format on sheet "
                        f"{worksheet.title!r} is not supported and was dropped."
                    )
                else:
                    sheet.conditional_formats.append(rule)


def read_workbook_extras(package: Any, workbook: Any) -> None:
    """Read workbook structure protection."""
    security = getattr(package, "security", None)
    if security is None or not security.lockStructure:
        return
    workbook.structure_protected = True
    workbook.structure_password_hash = stored_from_xlsx(
        security.workbookAlgorithmName,
        security.workbookHashValue,
        security.workbookSaltValue,
        security.workbookSpinCount,
        security.workbookPassword,
    )


def _patch_from_dxf(dxf: Any) -> FormatPatch:
    from duddysheet.io.xlsx_reader import _read_color

    if dxf is None:
        return FormatPatch()
    font = dxf.font
    fill = dxf.fill
    fill_color = None
    if fill is not None:
        fill_color = _read_color(fill.bgColor, None) or _read_color(fill.fgColor, None)
    return FormatPatch(
        bold=bool(font.b) if font is not None and font.b is not None else None,
        italic=bool(font.i) if font is not None and font.i is not None else None,
        font_color=_read_color(font.color, None) if font is not None else None,
        fill_color=fill_color,
    )


def _conditional_from_xlsx(area: str, xlsx_rule: Any) -> ConditionalRule | None:
    try:
        reference = parse_a1(area)
    except ValueError:
        return None
    if isinstance(reference, CellReference):
        reference = RangeReference(reference, reference)
    patch = _patch_from_dxf(xlsx_rule.dxf)
    kind = xlsx_rule.type
    stop = bool(xlsx_rule.stopIfTrue)
    if kind == "cellIs":
        operator = next((key for key, value in _OPERATORS.items() if value == xlsx_rule.operator), None)
        if operator is None:
            return None
        values = tuple(_parse_formula_value(item) for item in xlsx_rule.formula)
        return ConditionalRule(reference, "cell_value", operator, values, patch, stop_if_true=stop)
    if kind == "expression" and xlsx_rule.formula:
        return ConditionalRule(reference, "formula", formula="=" + xlsx_rule.formula[0], format_patch=patch, stop_if_true=stop)
    if kind == "top10":
        return ConditionalRule(
            reference,
            "top_bottom",
            format_patch=patch,
            rank=int(xlsx_rule.rank or 10),
            percent=bool(xlsx_rule.percent),
            above=not bool(xlsx_rule.bottom),
            stop_if_true=stop,
        )
    if kind == "aboveAverage":
        above = xlsx_rule.aboveAverage is None or bool(xlsx_rule.aboveAverage)
        return ConditionalRule(reference, "above_average", format_patch=patch, above=above, stop_if_true=stop)
    if kind == "duplicateValues":
        return ConditionalRule(reference, "duplicate", format_patch=patch, stop_if_true=stop)
    if kind == "colorScale" and xlsx_rule.colorScale is not None:
        from duddysheet.io.xlsx_reader import _read_color

        colors = tuple(
            _read_color(color, "#ffffff") or "#ffffff" for color in xlsx_rule.colorScale.color
        )
        return ConditionalRule(reference, "color_scale", colors=colors)
    if kind == "dataBar" and xlsx_rule.dataBar is not None:
        from duddysheet.io.xlsx_reader import _read_color

        color = _read_color(xlsx_rule.dataBar.color, "#638ec6") or "#638ec6"
        return ConditionalRule(reference, "data_bar", colors=(color,))
    if kind == "iconSet":
        return ConditionalRule(reference, "icon_set")
    return None


def _parse_formula_value(value: str) -> Any:
    text = str(value)
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('""', '"')
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return "=" + text


# ------------------------------------------------------------------ tables
_TOTALS_TO_XLSX = {
    "sum": "sum",
    "average": "average",
    "count": "countNums",
    "count_numbers": "countNums",
    "max": "max",
    "min": "min",
    "stddev": "stdDev",
    "var": "var",
}
_TOTALS_FROM_XLSX = {
    "sum": "sum",
    "average": "average",
    "count": "count",
    "countNums": "count_numbers",
    "max": "max",
    "min": "min",
    "stdDev": "stddev",
    "var": "var",
}


def write_table(source: Any, worksheet: Any, table: Any) -> None:
    """Write an Excel Table with style, banding, totals, and calculated columns."""
    from openpyxl.worksheet.filters import AutoFilter
    from openpyxl.worksheet.table import Table, TableColumn, TableStyleInfo

    from duddysheet.core.tables import qualify_structured
    from duddysheet.io.formula_compat import to_xlsx_formula

    reference = RangeReference(
        CellReference(table.top, table.left),
        CellReference(table.bottom, table.right),
    ).to_a1()
    xlsx_table = Table(displayName=table.name, name=table.name, ref=reference)
    xlsx_table.tableStyleInfo = TableStyleInfo(
        name=table.style,
        showFirstColumn=table.first_column,
        showLastColumn=table.last_column,
        showRowStripes=table.banded_rows,
        showColumnStripes=table.banded_columns,
    )
    columns = []
    calculated = dict((key.casefold(), value) for key, value in table.calculated)
    for index, name in enumerate(table.columns, start=1):
        column = TableColumn(id=index, name=name)
        function = table.total_function(name)
        if table.show_totals:
            if function in _TOTALS_TO_XLSX:
                column.totalsRowFunction = _TOTALS_TO_XLSX[function]
            elif index == 1:
                column.totalsRowLabel = "Total"
        formula = calculated.get(name.casefold())
        if formula:
            from openpyxl.worksheet.table import TableFormula

            column.calculatedColumnFormula = TableFormula(
                attr_text=to_xlsx_formula(qualify_structured(formula, table.name))[1:]
            )
        columns.append(column)
    xlsx_table.tableColumns = columns
    if table.show_totals:
        xlsx_table.totalsRowCount = 1
    if table.filter_button:
        filter_bottom = table.bottom - (1 if table.show_totals else 0)
        xlsx_table.autoFilter = AutoFilter(
            ref=RangeReference(
                CellReference(table.top, table.left),
                CellReference(filter_bottom, table.right),
            ).to_a1()
        )
    worksheet.add_table(xlsx_table)


def read_table(sheet: Any, xlsx_table: Any) -> Any:
    """Return a ``TableSpec`` for an XLSX table."""
    from duddysheet.core.tables import TableSpec, header_names
    from duddysheet.io.formula_compat import from_xlsx_formula

    try:
        reference = parse_a1(xlsx_table.ref)
    except ValueError:
        return None
    if isinstance(reference, CellReference):
        return None
    style = xlsx_table.tableStyleInfo
    columns = tuple(column.name for column in xlsx_table.tableColumns) or header_names(
        sheet, reference.min_row, reference.min_column, reference.max_column
    )
    totals = tuple(
        (column.name, _TOTALS_FROM_XLSX[column.totalsRowFunction])
        for column in xlsx_table.tableColumns
        if column.totalsRowFunction in _TOTALS_FROM_XLSX
    )
    calculated = tuple(
        (column.name, from_xlsx_formula("=" + str(column.calculatedColumnFormula.attr_text if hasattr(column.calculatedColumnFormula, "attr_text") else column.calculatedColumnFormula)))
        for column in xlsx_table.tableColumns
        if column.calculatedColumnFormula
    )
    return TableSpec(
        name=xlsx_table.displayName or xlsx_table.name,
        top=reference.min_row,
        left=reference.min_column,
        bottom=reference.max_row,
        right=reference.max_column,
        columns=columns,
        style=(style.name if style is not None and style.name else "TableStyleMedium2"),
        show_totals=bool(xlsx_table.totalsRowCount),
        banded_rows=bool(style.showRowStripes) if style is not None else True,
        banded_columns=bool(style.showColumnStripes) if style is not None else False,
        first_column=bool(style.showFirstColumn) if style is not None else False,
        last_column=bool(style.showLastColumn) if style is not None else False,
        filter_button=xlsx_table.autoFilter is not None,
        totals=totals,
        calculated=calculated,
    )
