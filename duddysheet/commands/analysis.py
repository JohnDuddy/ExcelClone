"""Undoable commands for Excel Tables, PivotTables, and What-If data tables."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable

from duddysheet.commands.edits import _WorkbookSnapshotCommand
from duddysheet.core.data_table import DataTableSpec, table_formula
from duddysheet.core.pivot import PivotSpec, render_pivot
from duddysheet.core.tables import (
    create_table,
    expand_for_entry,
    find_table,
    make_calculated_column,
    rename_table_references,
    table_at,
    validate_table_name,
)


class WorkbookMutationCommand(_WorkbookSnapshotCommand):
    """Snapshot command that runs one workbook mutation; undo restores the snapshot."""

    def __init__(self, engine: Any, description: str, mutate: Callable[[], Any]) -> None:
        self.engine = engine
        self.snapshot = None
        self._description = description
        self._mutate = mutate
        self.result: Any = None

    @property
    def description(self) -> str:
        return self._description

    def do(self) -> None:
        self._capture()
        try:
            self.result = self._mutate()
        except Exception:
            self.engine.workbook.restore_from(self.snapshot)
            self.engine.rebuild_index()
            raise
        self._rebuild()


# ------------------------------------------------------------------ tables
@dataclass
class CreateTableCommand(_WorkbookSnapshotCommand):
    """Format as Table / Ctrl+T."""

    sheet_name: str
    area: tuple[int, int, int, int]
    has_headers: bool = True
    style: str = "TableStyleMedium2"
    name: str | None = None

    @property
    def description(self) -> str:
        return "Create table"

    def do(self) -> None:
        self._capture()
        try:
            create_table(
                self.engine.workbook,
                self.sheet_name,
                self.area,
                has_headers=self.has_headers,
                name=self.name,
                style=self.style,
            )
        except Exception:
            self.engine.workbook.restore_from(self.snapshot)
            raise
        self._rebuild()


@dataclass
class TableEntryCommand(_WorkbookSnapshotCommand):
    """Type into a table: auto-expand and create calculated columns like Excel."""

    sheet_name: str
    row: int
    column: int
    value: Any
    # Like SetCellCommand; None tells the grid to refresh everything.
    result: Any = field(default=None, init=False)

    @property
    def description(self) -> str:
        return "Typing in table"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        try:
            self.engine.set_cell(self.sheet_name, self.row, self.column, self.value)
        except Exception:
            self.engine.workbook.restore_from(self.snapshot)
            self.engine.rebuild_index()
            raise
        expand_for_entry(sheet, self.row, self.column)
        table = table_at(sheet, self.row, self.column)
        if table is not None:
            make_calculated_column(sheet, table, self.row, self.column)
        self._rebuild()


def rename_table(workbook: Any, old: str, new: str) -> None:
    """Rename a table and every structured reference to it."""
    found = find_table(workbook, old)
    if found is None:
        raise ValueError(f"There is no table named {old!r}.")
    validate_table_name(workbook, new, current=old)
    sheet, table = found
    sheet.tables = [replace(item, name=new) if item.name == table.name else item for item in sheet.tables]
    for formula_sheet in workbook:
        for (row, column), cell in tuple(formula_sheet.iter_populated()):
            if cell.is_formula and "[" in cell.raw_input:
                rewritten = rename_table_references(cell.raw_input, old, new)
                if rewritten != cell.raw_input:
                    formula_sheet.put_cell(row, column, replace(cell, raw_input=rewritten, cached_value=None))


# ------------------------------------------------------------------ pivots
def add_pivot(workbook: Any, sheet_name: str, spec: PivotSpec) -> PivotSpec:
    sheet = workbook.get_sheet(sheet_name)
    sheet.pivots.append(spec)
    return render_pivot(workbook, sheet_name, spec)


def update_pivot(workbook: Any, sheet_name: str, spec: PivotSpec) -> PivotSpec:
    sheet = workbook.get_sheet(sheet_name)
    previous = next((pivot for pivot in sheet.pivots if pivot.name == spec.name), None)
    if previous is not None:
        spec = replace(spec, extent=previous.extent)
    sheet.pivots = [spec if pivot.name == spec.name else pivot for pivot in sheet.pivots]
    return render_pivot(workbook, sheet_name, spec)


def refresh_pivots(workbook: Any, name: str | None = None) -> int:
    """Recompute one PivotTable (by name) or every PivotTable; return the count."""
    count = 0
    for sheet in workbook:
        for spec in list(sheet.pivots):
            if name is None or spec.name == name:
                render_pivot(workbook, sheet.name, spec)
                count += 1
    return count


def delete_pivot(workbook: Any, sheet_name: str, name: str) -> None:
    sheet = workbook.get_sheet(sheet_name)
    for spec in sheet.pivots:
        if spec.name == name and spec.extent is not None:
            top, left, bottom, right = spec.extent
            for row in range(top, bottom + 1):
                for column in range(left, right + 1):
                    sheet.clear_cell(row, column)
    sheet.pivots = [spec for spec in sheet.pivots if spec.name != name]


# ------------------------------------------------------------- data tables
def create_data_table(workbook: Any, sheet_name: str, spec: DataTableSpec) -> None:
    """Write a data table's {=TABLE()} interior and register it."""
    sheet = workbook.get_sheet(sheet_name)
    if spec.bottom <= spec.top or spec.right <= spec.left:
        raise ValueError("Select a range with the formula and the input values, at least two rows and two columns.")
    if spec.row_input is None and spec.column_input is None:
        raise ValueError("Enter a row input cell, a column input cell, or both.")
    top, left, bottom, right = spec.interior
    for existing in sheet.data_tables:
        if not (existing.bottom < spec.top or existing.top > spec.bottom or existing.right < spec.left or existing.left > spec.right):
            raise ValueError("Data tables can't overlap.")
    formula = table_formula(spec, sheet.name)
    sheet.data_tables.append(spec)
    for row in range(top, bottom + 1):
        for column in range(left, right + 1):
            sheet.set_cell(row, column, formula, cell_format=sheet.get_cell(row, column).format)


def delete_data_table(workbook: Any, sheet_name: str, spec: DataTableSpec) -> None:
    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = spec.interior
    for row in range(top, bottom + 1):
        for column in range(left, right + 1):
            sheet.clear_cell(row, column)
    sheet.data_tables = [item for item in sheet.data_tables if item != spec]
