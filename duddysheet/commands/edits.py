"""Concrete reversible workbook edit commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from typing import Any

from duddysheet.commands.base import Command
from duddysheet.core.cell import Cell, CellFormat
from duddysheet.core.chart import ChartSpec
from duddysheet.core.conditional import FormatPatch
from duddysheet.core.data_tools import (
    DataValidation,
    FindOptions,
    SortKey,
    apply_filter,
    clear_filter,
    remove_duplicates,
    replace_matches,
    sort_range,
    text_to_columns,
)
from duddysheet.core.engine import FormulaEngine, RecalculationResult
from duddysheet.core.fill import fill_range
from duddysheet.core.operations import edit_structure
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, Reference, RangeReference
from duddysheet.core.sheet import Sheet
from duddysheet.core.sparkline import Sparkline
from duddysheet.core.translation import rename_formula_sheet, translate_formula_copy
from duddysheet.core.workbook import Workbook


@dataclass
class SetCellCommand(Command):
    """Set one cell through the formula engine."""

    engine: FormulaEngine
    sheet_name: str
    row: int
    column: int
    raw_input: Any
    cell_format: CellFormat | None = None
    previous: Cell | None = field(default=None, init=False)
    result: RecalculationResult | None = field(default=None, init=False)
    _captured: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return "Edit cell"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        self.sheet_name = sheet.name
        if not self._captured:
            self.previous = sheet.get_cell(self.row, self.column)
            self._captured = True
        self.result = self.engine.set_cell(
            self.sheet_name,
            self.row,
            self.column,
            self.raw_input,
            cell_format=self.cell_format,
        )

    def undo(self) -> None:
        if self.previous is None:
            raise RuntimeError("Command has not been executed")
        self.engine.set_cell(
            self.sheet_name,
            self.row,
            self.column,
            self.previous.raw_input,
            cell_format=self.previous.format,
        )

    def merge_with(self, newer: Command) -> bool:
        if not isinstance(newer, SetCellCommand):
            return False
        if (
            newer.engine is not self.engine
            or newer.sheet_name.casefold() != self.sheet_name.casefold()
            or newer.row != self.row
            or newer.column != self.column
        ):
            return False
        self.raw_input = newer.raw_input
        self.cell_format = newer.cell_format
        self.result = newer.result
        return True


@dataclass
class SetRangeCommand(Command):
    """Set a rectangular matrix as one undo step."""

    engine: FormulaEngine
    sheet_name: str
    start_row: int
    start_column: int
    values: tuple[tuple[Any, ...], ...]
    previous: dict[tuple[int, int], Cell] = field(default_factory=dict, init=False)
    _captured: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return "Edit range"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        self.sheet_name = sheet.name
        if not self._captured:
            self.previous = {
                (self.start_row + row_offset, self.start_column + column_offset): sheet.get_cell(
                    self.start_row + row_offset,
                    self.start_column + column_offset,
                )
                for row_offset, row_values in enumerate(self.values)
                for column_offset, _ in enumerate(row_values)
            }
            self._captured = True
        for row_offset, row_values in enumerate(self.values):
            for column_offset, value in enumerate(row_values):
                self.engine.set_cell(
                    self.sheet_name,
                    self.start_row + row_offset,
                    self.start_column + column_offset,
                    value,
                )

    def undo(self) -> None:
        for (row, column), cell in reversed(tuple(self.previous.items())):
            self.engine.set_cell(
                self.sheet_name,
                row,
                column,
                cell.raw_input,
                cell_format=cell.format,
            )


@dataclass
class SetFormatCommand(Command):
    """Apply a format patch to a rectangle as one reversible edit."""

    engine: FormulaEngine
    sheet_name: str
    start_row: int
    start_column: int
    end_row: int
    end_column: int
    patch: FormatPatch
    previous: dict[tuple[int, int], Cell] = field(default_factory=dict, init=False)
    _captured: bool = field(default=False, init=False)
    _previous_axis: tuple[dict[int, Any], dict[int, Any]] = field(
        default_factory=lambda: ({}, {}),
        init=False,
    )

    @property
    def description(self) -> str:
        return "Format cells"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        self.sheet_name = sheet.name
        minimum_row, maximum_row = sorted((self.start_row, self.end_row))
        minimum_column, maximum_column = sorted(
            (self.start_column, self.end_column)
        )
        whole_columns = minimum_row == 0 and maximum_row == MAX_ROWS - 1
        whole_rows = minimum_column == 0 and maximum_column == MAX_COLUMNS - 1
        if not self._captured:
            if whole_columns or whole_rows:
                # Whole rows/columns: store axis formats and touch only
                # populated cells, instead of allocating every coordinate.
                self.previous = {
                    coordinate: cell
                    for coordinate, cell in sheet.iter_unordered()
                    if minimum_row <= coordinate[0] <= maximum_row
                    and minimum_column <= coordinate[1] <= maximum_column
                }
            else:
                self.previous = {
                    (row, column): sheet.get_cell(row, column)
                    for row in range(minimum_row, maximum_row + 1)
                    for column in range(minimum_column, maximum_column + 1)
                }
            self._previous_axis = (dict(sheet.column_formats), dict(sheet.row_formats))
            self._captured = True
        if whole_columns:
            for column in range(minimum_column, maximum_column + 1):
                base = self._previous_axis[0].get(column, CellFormat())
                sheet.column_formats[column] = self.patch.apply(base)
            for row in list(sheet.row_formats):
                sheet.row_formats[row] = self.patch.apply(self._previous_axis[1][row])
        elif whole_rows:
            for row in range(minimum_row, maximum_row + 1):
                base = self._previous_axis[1].get(row, CellFormat())
                sheet.row_formats[row] = self.patch.apply(base)
        for (row, column), original in self.previous.items():
            current = sheet.get_cell(row, column)
            original_format = (
                original.format
                if not original.is_empty
                else sheet.effective_format(row, column)
            )
            sheet.put_cell(
                row,
                column,
                replace(current, format=self.patch.apply(original_format)),
            )

    def undo(self) -> None:
        if not self._captured:
            raise RuntimeError("Command has not been executed")
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        sheet.column_formats = dict(self._previous_axis[0])
        sheet.row_formats = dict(self._previous_axis[1])
        for (row, column), cell in self.previous.items():
            current = sheet.get_cell(row, column)
            sheet.put_cell(row, column, replace(current, format=cell.format))


@dataclass
class SetFreezePanesCommand(Command):
    """Set or clear a sheet's frozen-pane origin."""

    engine: FormulaEngine
    sheet_name: str
    freeze_panes: tuple[int, int] | None
    previous: tuple[int, int] | None = field(default=None, init=False)
    _captured: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return "Freeze panes" if self.freeze_panes is not None else "Unfreeze panes"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        self.sheet_name = sheet.name
        if not self._captured:
            self.previous = sheet.freeze_panes
            self._captured = True
        sheet.freeze_panes = self.freeze_panes

    def undo(self) -> None:
        if not self._captured:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.get_sheet(self.sheet_name).freeze_panes = self.previous


@dataclass
class _StructuralCommand(Command):
    engine: FormulaEngine
    sheet_name: str
    index: int
    count: int = 1
    snapshot: Workbook | None = field(default=None, init=False)

    axis = "row"
    delete = False

    @property
    def description(self) -> str:
        verb = "Delete" if self.delete else "Insert"
        noun = "columns" if self.axis == "column" else "rows"
        return f"{verb} {noun}"

    def do(self) -> None:
        if self.snapshot is None:
            self.snapshot = self.engine.workbook.copy()
        edit_structure(
            self.engine.workbook,
            self.sheet_name,
            axis=self.axis,
            index=self.index,
            count=self.count,
            delete=self.delete,
        )
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.snapshot is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.restore_from(self.snapshot)
        self.engine.rebuild_index()


class InsertRowsCommand(_StructuralCommand):
    """Insert rows and translate workbook references."""


class DeleteRowsCommand(_StructuralCommand):
    """Delete rows and translate workbook references."""

    delete = True


class InsertColumnsCommand(_StructuralCommand):
    """Insert columns and translate workbook references."""

    axis = "column"


class DeleteColumnsCommand(_StructuralCommand):
    """Delete columns and translate workbook references."""

    axis = "column"
    delete = True


@dataclass
class _WorkbookSnapshotCommand(Command):
    engine: FormulaEngine
    snapshot: Workbook | None = field(default=None, init=False)

    def _capture(self) -> None:
        if self.snapshot is None:
            self.snapshot = self.engine.workbook.copy()

    def _rebuild(self) -> None:
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.snapshot is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.restore_from(self.snapshot)
        self.engine.rebuild_index()


@dataclass
class SortRangeCommand(_WorkbookSnapshotCommand):
    """Sort one rectangle as an atomic command."""

    sheet_name: str
    target: RangeReference
    keys: tuple[SortKey, ...]
    has_header: bool = False

    @property
    def description(self) -> str:
        return "Sort range"

    def do(self) -> None:
        self._capture()
        sort_range(
            self.engine.workbook,
            self.sheet_name,
            self.target,
            self.keys,
            has_header=self.has_header,
        )
        self._rebuild()


@dataclass
class ApplyFilterCommand(_WorkbookSnapshotCommand):
    """Apply a value-list filter as an atomic command."""

    sheet_name: str
    target: RangeReference
    column: int
    allowed_values: frozenset[Any]
    has_header: bool = True

    @property
    def description(self) -> str:
        return "Apply filter"

    def do(self) -> None:
        self._capture()
        apply_filter(
            self.engine.workbook.get_sheet(self.sheet_name),
            self.target,
            column=self.column,
            allowed_values=self.allowed_values,
            has_header=self.has_header,
        )


@dataclass
class ClearFilterCommand(_WorkbookSnapshotCommand):
    """Clear filter-generated hidden rows."""

    sheet_name: str

    @property
    def description(self) -> str:
        return "Clear filter"

    def do(self) -> None:
        self._capture()
        clear_filter(self.engine.workbook.get_sheet(self.sheet_name))


@dataclass
class AddValidationCommand(_WorkbookSnapshotCommand):
    """Append one data-validation rule."""

    sheet_name: str
    validation: DataValidation

    @property
    def description(self) -> str:
        return "Add validation"

    def do(self) -> None:
        self._capture()
        self.engine.workbook.get_sheet(self.sheet_name).data_validations.append(
            self.validation
        )


@dataclass
class AddChartCommand(_WorkbookSnapshotCommand):
    """Attach a chart specification to a sheet."""

    sheet_name: str
    chart: ChartSpec

    @property
    def description(self) -> str:
        return "Add chart"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if any(
            isinstance(item, ChartSpec) and item.chart_id == self.chart.chart_id
            for item in sheet.charts
        ):
            raise ValueError(f"Chart ID already exists: {self.chart.chart_id}")
        sheet.charts.append(self.chart)


@dataclass
class UpdateChartCommand(_WorkbookSnapshotCommand):
    """Replace an existing chart specification by ID."""

    sheet_name: str
    chart: ChartSpec

    @property
    def description(self) -> str:
        return "Update chart"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        for index, item in enumerate(sheet.charts):
            if (
                isinstance(item, ChartSpec)
                and item.chart_id == self.chart.chart_id
            ):
                sheet.charts[index] = self.chart
                return
        raise KeyError(f"Unknown chart ID: {self.chart.chart_id}")


@dataclass
class RemoveChartCommand(_WorkbookSnapshotCommand):
    """Remove a sheet chart by ID."""

    sheet_name: str
    chart_id: str

    @property
    def description(self) -> str:
        return "Remove chart"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        retained = [
            item
            for item in sheet.charts
            if not isinstance(item, ChartSpec) or item.chart_id != self.chart_id
        ]
        if len(retained) == len(sheet.charts):
            raise KeyError(f"Unknown chart ID: {self.chart_id}")
        sheet.charts = retained


@dataclass
class AddSparklinesCommand(_WorkbookSnapshotCommand):
    """Place sparklines in cells, replacing any already in those cells."""

    sheet_name: str
    sparklines: tuple[Sparkline, ...]

    @property
    def description(self) -> str:
        return "Insert sparklines"

    def do(self) -> None:
        if not self.sparklines:
            raise ValueError("No sparklines to insert")
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        occupied = {(item.row, item.column) for item in self.sparklines}
        sheet.sparklines = [
            item
            for item in sheet.sparklines
            if (getattr(item, "row", None), getattr(item, "column", None))
            not in occupied
        ] + list(self.sparklines)


@dataclass
class ClearSparklinesCommand(_WorkbookSnapshotCommand):
    """Remove every sparkline whose cell lies inside a range."""

    sheet_name: str
    target: Reference

    @property
    def description(self) -> str:
        return "Clear sparklines"

    def do(self) -> None:
        target = (
            self.target
            if isinstance(self.target, RangeReference)
            else RangeReference(self.target, self.target)
        )
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        retained = [
            item
            for item in sheet.sparklines
            if not (
                isinstance(item, Sparkline)
                and target.contains(item.row, item.column)
            )
        ]
        if len(retained) == len(sheet.sparklines):
            raise ValueError("The selection contains no sparklines")
        sheet.sparklines = retained


@dataclass
class FillRangeCommand(_WorkbookSnapshotCommand):
    """Fill a target range from a source pattern."""

    sheet_name: str
    source: Reference
    target: Reference

    @property
    def description(self) -> str:
        return "Fill range"

    def do(self) -> None:
        self._capture()
        fill_range(
            self.engine.workbook.get_sheet(self.sheet_name),
            self.source,
            self.target,
        )
        self._rebuild()


@dataclass
class PasteCellsCommand(_WorkbookSnapshotCommand):
    """Paste a rich cell matrix with Excel's Paste Special options."""

    sheet_name: str
    start_row: int
    start_column: int
    cells: tuple[tuple[Cell, ...], ...]
    source_origin: tuple[int, int]
    mode: str = "all"
    transpose: bool = False
    operation: str = "none"
    skip_blanks: bool = False
    source_sheet: str | None = None
    column_widths: tuple[float | None, ...] = ()

    MODES = (
        "all",
        "values",
        "formulas",
        "formats",
        "values_number_formats",
        "formulas_number_formats",
        "all_except_borders",
        "column_widths",
        "link",
    )
    OPERATIONS = ("none", "add", "subtract", "multiply", "divide")

    @property
    def description(self) -> str:
        return "Paste cells" if self.mode == "all" else "Paste special"

    def do(self) -> None:
        if self.mode not in self.MODES:
            raise ValueError(f"Unknown paste mode: {self.mode!r}")
        if self.operation not in self.OPERATIONS:
            raise ValueError(f"Unknown paste operation: {self.operation!r}")
        self._capture()
        matrix = (
            tuple(tuple(row[index] for row in self.cells) for index in range(len(self.cells[0])))
            if self.transpose
            else self.cells
        )
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if self.mode == "column_widths":
            for offset, width in enumerate(self.column_widths):
                if width is not None:
                    sheet.column_widths[self.start_column + offset] = width
            self._rebuild()
            return
        for row_offset, row_cells in enumerate(matrix):
            for column_offset, source in enumerate(row_cells):
                if self.skip_blanks and source.raw_input in (None, "") and source.cached_value in (None, ""):
                    continue
                row = self.start_row + row_offset
                column = self.start_column + column_offset
                current = sheet.get_cell(row, column)
                source_row, source_column = (
                    (
                        self.source_origin[0] + column_offset,
                        self.source_origin[1] + row_offset,
                    )
                    if self.transpose
                    else (
                        self.source_origin[0] + row_offset,
                        self.source_origin[1] + column_offset,
                    )
                )
                selected = self._pasted_cell(source, current, row, column, source_row, source_column)
                if self.operation != "none" and self.mode not in ("formats",):
                    selected = _combine_operation(current, selected, self.operation)
                sheet.put_cell(row, column, selected)
        self._rebuild()

    def _pasted_cell(
        self,
        source: Cell,
        current: Cell,
        row: int,
        column: int,
        source_row: int,
        source_column: int,
    ) -> Cell:
        mode = self.mode
        if mode == "formats":
            return replace(current, format=source.format)
        if mode == "link":
            from duddysheet.core.refs import CellReference, quote_sheet_name

            reference = CellReference(source_row, source_column).to_a1(include_sheet=False)
            if self.source_sheet and self.source_sheet.casefold() != self.sheet_name.casefold():
                reference = f"{quote_sheet_name(self.source_sheet)}!{reference}"
            return Cell(raw_input="=" + reference, format=current.format, hyperlink=current.hyperlink)
        if mode in ("values", "values_number_formats"):
            value = None if source.error is not None else source.display_value
            number_format = source.format.number_format if mode == "values_number_formats" else current.format.number_format
            return Cell(
                raw_input=value,
                cached_value=value,
                format=replace(current.format, number_format=number_format),
                hyperlink=current.hyperlink,
            )
        raw = source.raw_input
        if source.is_formula:
            raw = translate_formula_copy(
                source.raw_input,
                rows=row - source_row,
                columns=column - source_column,
            )
        if mode in ("all", "all_except_borders"):
            cell_format = source.format
            if mode == "all_except_borders":
                cell_format = replace(
                    source.format,
                    left_border=current.format.left_border,
                    right_border=current.format.right_border,
                    top_border=current.format.top_border,
                    bottom_border=current.format.bottom_border,
                )
        elif mode == "formulas_number_formats":
            cell_format = replace(current.format, number_format=source.format.number_format)
        else:
            cell_format = current.format
        return Cell(
            raw_input=raw,
            cached_value=None if isinstance(raw, str) and raw.startswith("=") else raw,
            format=cell_format,
            error=None,
            hyperlink=source.hyperlink if mode == "all" else current.hyperlink,
        )


def _combine_operation(current: Cell, pasted: Cell, operation: str) -> Cell:
    """Combine a pasted value with the destination using Add/Subtract/Multiply/Divide."""
    symbol = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}[operation]
    incoming = pasted.raw_input
    if isinstance(incoming, str) and incoming.startswith("="):
        incoming_text = "(" + incoming[1:] + ")"
        incoming_number = None
    elif isinstance(incoming, (int, float)) and not isinstance(incoming, bool):
        incoming_text = repr(incoming) if isinstance(incoming, float) else str(incoming)
        incoming_number = incoming
    elif incoming in (None, ""):
        incoming_text = "0"
        incoming_number = 0
    else:
        return pasted
    existing = current.raw_input
    if current.is_formula:
        return replace(pasted, raw_input=f"=({existing[1:]}){symbol}{incoming_text}", cached_value=None)
    if isinstance(existing, (int, float)) and not isinstance(existing, bool) or existing in (None, ""):
        base = existing if existing not in (None, "") else 0
        if incoming_number is None:
            return replace(pasted, raw_input=f"={base}{symbol}{incoming_text}", cached_value=None)
        if operation == "add":
            result = base + incoming_number
        elif operation == "subtract":
            result = base - incoming_number
        elif operation == "multiply":
            result = base * incoming_number
        else:
            if incoming_number == 0:
                return replace(pasted, raw_input="=" + f"{base}/0", cached_value=None)
            result = base / incoming_number
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return replace(pasted, raw_input=result, cached_value=result)
    return replace(pasted, raw_input=existing, cached_value=existing)


@dataclass
class ReplaceAllCommand(_WorkbookSnapshotCommand):
    """Replace all matches in a workbook or sheet."""

    options: FindOptions
    sheet_name: str | None = None
    replaced_count: int = field(default=0, init=False)

    @property
    def description(self) -> str:
        return "Replace all"

    def do(self) -> None:
        self._capture()
        self.replaced_count = replace_matches(
            self.engine.workbook,
            self.options,
            sheet_name=self.sheet_name,
        )
        self._rebuild()


@dataclass
class RemoveDuplicatesCommand(_WorkbookSnapshotCommand):
    """Remove duplicate range rows as one edit."""

    sheet_name: str
    target: RangeReference
    key_columns: tuple[int, ...]
    has_header: bool = True
    removed_count: int = field(default=0, init=False)

    @property
    def description(self) -> str:
        return "Remove duplicates"

    def do(self) -> None:
        self._capture()
        self.removed_count = remove_duplicates(
            self.engine.workbook.get_sheet(self.sheet_name),
            self.target,
            key_columns=self.key_columns,
            has_header=self.has_header,
        )
        self._rebuild()


@dataclass
class TextToColumnsCommand(_WorkbookSnapshotCommand):
    """Split delimited text into adjacent columns."""

    sheet_name: str
    target: RangeReference
    delimiter: str = ","
    output_columns: int = field(default=0, init=False)

    @property
    def description(self) -> str:
        return "Text to columns"

    def do(self) -> None:
        self._capture()
        self.output_columns = text_to_columns(
            self.engine.workbook.get_sheet(self.sheet_name),
            self.target,
            delimiter=self.delimiter,
        )
        self._rebuild()


@dataclass
class MergeCellsCommand(_WorkbookSnapshotCommand):
    """Merge a rectangle while retaining its upper-left cell."""

    sheet_name: str
    target: RangeReference

    @property
    def description(self) -> str:
        return "Merge cells"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if any(_ranges_overlap(self.target, item) for item in sheet.merged_ranges):
            raise ValueError("Merge range overlaps an existing merge")
        for row in range(self.target.min_row, self.target.max_row + 1):
            for column in range(
                self.target.min_column,
                self.target.max_column + 1,
            ):
                if (row, column) != (
                    self.target.min_row,
                    self.target.min_column,
                ):
                    sheet.clear_cell(row, column)
        sheet.merged_ranges.append(self.target)
        self._rebuild()


@dataclass
class SetRowHeightCommand(_WorkbookSnapshotCommand):
    """Set selected row heights."""

    sheet_name: str
    rows: tuple[int, ...]
    height: float

    @property
    def description(self) -> str:
        return "Set row height"

    def do(self) -> None:
        if self.height <= 0:
            raise ValueError("Row height must be positive")
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        for row in self.rows:
            sheet.row_heights[row] = self.height


@dataclass
class SetColumnWidthCommand(_WorkbookSnapshotCommand):
    """Set selected column widths."""

    sheet_name: str
    columns: tuple[int, ...]
    width: float

    @property
    def description(self) -> str:
        return "Set column width"

    def do(self) -> None:
        if self.width <= 0:
            raise ValueError("Column width must be positive")
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        for column in self.columns:
            sheet.column_widths[column] = self.width


@dataclass
class MoveSheetCommand(Command):
    """Move one sheet tab and restore its old index on undo."""

    engine: FormulaEngine
    old_index: int
    new_index: int

    @property
    def description(self) -> str:
        return "Move sheet"

    def do(self) -> None:
        self.engine.workbook.move_sheet(self.old_index, self.new_index)

    def undo(self) -> None:
        self.engine.workbook.move_sheet(self.new_index, self.old_index)


@dataclass
class DuplicateSheetCommand(Command):
    """Duplicate a sheet and remove the duplicate on undo."""

    engine: FormulaEngine
    identifier: str | int
    name: str | None = None
    duplicate: Sheet | None = field(default=None, init=False)
    index: int | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Duplicate sheet"

    def do(self) -> None:
        if self.duplicate is None:
            self.duplicate = self.engine.workbook.duplicate_sheet(
                self.identifier,
                name=self.name,
            )
            self.index = self.engine.workbook.index_of(self.duplicate.name)
        else:
            self.engine.workbook.restore_sheet(self.duplicate, index=self.index)
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.duplicate is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.delete_sheet(self.duplicate.name)
        self.engine.rebuild_index()


@dataclass
class SetSheetVisibilityCommand(Command):
    """Hide or unhide a sheet."""

    engine: FormulaEngine
    sheet_name: str
    visible: bool
    previous: bool | None = field(default=None, init=False)
    previous_active: str | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Unhide sheet" if self.visible else "Hide sheet"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if not self.visible and sum(item.visible for item in self.engine.workbook) <= 1:
            raise ValueError("A workbook must contain one visible sheet")
        if self.previous is None:
            self.previous = sheet.visible
            self.previous_active = self.engine.workbook.active_sheet.name
        sheet.visible = self.visible
        if not self.visible and self.engine.workbook.active_sheet is sheet:
            self.engine.workbook.active_sheet = next(
                item for item in self.engine.workbook if item.visible
            )

    def undo(self) -> None:
        if self.previous is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.get_sheet(self.sheet_name).visible = self.previous
        if self.previous_active is not None:
            self.engine.workbook.active_sheet = self.previous_active


@dataclass
class SetSheetTabColorCommand(Command):
    """Set a sheet tab color."""

    engine: FormulaEngine
    sheet_name: str
    color: str | None
    previous: str | None = field(default=None, init=False)
    _captured: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return "Set tab color"

    def do(self) -> None:
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if not self._captured:
            self.previous = sheet.tab_color
            self._captured = True
        sheet.tab_color = self.color

    def undo(self) -> None:
        if not self._captured:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.get_sheet(self.sheet_name).tab_color = self.previous


def _ranges_overlap(left: RangeReference, right: RangeReference) -> bool:
    return not (
        left.max_row < right.min_row
        or right.max_row < left.min_row
        or left.max_column < right.min_column
        or right.max_column < left.min_column
    )


@dataclass
class AddSheetCommand(Command):
    """Add a sheet and remove it on undo."""

    engine: FormulaEngine
    name: str | None = None
    index: int | None = None
    sheet: Sheet | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Add sheet"

    def do(self) -> None:
        if self.sheet is None:
            self.sheet = self.engine.workbook.add_sheet(self.name, index=self.index)
            self.index = self.engine.workbook.index_of(self.sheet.name)
        else:
            self.engine.workbook.restore_sheet(self.sheet, index=self.index)
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.sheet is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.delete_sheet(self.sheet.name)
        self.engine.rebuild_index()


@dataclass
class DeleteSheetCommand(Command):
    """Delete and later restore a sheet with all of its data."""

    engine: FormulaEngine
    identifier: str | int
    sheet: Sheet | None = field(default=None, init=False)
    index: int | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Delete sheet"

    def do(self) -> None:
        selected = (
            self.sheet
            if self.sheet is not None
            else self.engine.workbook.get_sheet(self.identifier)
        )
        self.index = self.engine.workbook.index_of(selected.name)
        self.sheet = self.engine.workbook.delete_sheet(selected.name)
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.sheet is None or self.index is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.restore_sheet(self.sheet, index=self.index)
        self.engine.rebuild_index()


@dataclass
class RenameSheetCommand(Command):
    """Rename a sheet and reverse the name change."""

    engine: FormulaEngine
    identifier: str | int
    new_name: str
    old_name: str | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Rename sheet"

    def do(self) -> None:
        selected = self.engine.workbook.get_sheet(
            self.old_name if self.old_name is not None else self.identifier
        )
        if self.old_name is None:
            self.old_name = selected.name
        _rename_formula_sheet_references(
            self.engine.workbook,
            selected.name,
            self.new_name,
        )
        self.engine.workbook.rename_sheet(selected.name, self.new_name)
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.old_name is None:
            raise RuntimeError("Command has not been executed")
        _rename_formula_sheet_references(
            self.engine.workbook,
            self.new_name,
            self.old_name,
        )
        self.engine.workbook.rename_sheet(self.new_name, self.old_name)
        self.engine.rebuild_index()


def _rename_formula_sheet_references(
    workbook: Workbook,
    old_name: str,
    new_name: str,
) -> None:
    for sheet in workbook:
        for (row, column), cell in tuple(sheet.iter_populated()):
            if cell.is_formula:
                sheet.put_cell(
                    row,
                    column,
                    replace(
                        cell,
                        raw_input=rename_formula_sheet(
                            cell.raw_input,
                            old_name,
                            new_name,
                        ),
                        cached_value=None,
                        error=None,
                    ),
                )
        renamed_charts: list[Any] = []
        for chart in sheet.charts:
            if not isinstance(chart, ChartSpec):
                renamed_charts.append(chart)
                continue
            source_range = chart.source_range
            if (
                source_range.sheet is not None
                and source_range.sheet.casefold() == old_name.casefold()
            ):
                source_range = RangeReference(
                    replace(source_range.start, sheet=new_name),
                    replace(source_range.end, sheet=new_name),
                    whole_row=source_range.whole_row,
                    whole_column=source_range.whole_column,
                )
            renamed_charts.append(
                replace(
                    chart,
                    sheet_name=(
                        new_name
                        if chart.sheet_name.casefold() == old_name.casefold()
                        else chart.sheet_name
                    ),
                    source_range=source_range,
                )
            )
        sheet.charts = renamed_charts
        renamed_sparklines: list[Any] = []
        for sparkline in sheet.sparklines:
            data_range = getattr(sparkline, "data_range", None)
            if (
                isinstance(sparkline, Sparkline)
                and data_range is not None
                and data_range.sheet is not None
                and data_range.sheet.casefold() == old_name.casefold()
            ):
                sparkline = replace(
                    sparkline,
                    data_range=RangeReference(
                        replace(data_range.start, sheet=new_name),
                        replace(data_range.end, sheet=new_name),
                    ),
                )
            renamed_sparklines.append(sparkline)
        sheet.sparklines = renamed_sparklines
