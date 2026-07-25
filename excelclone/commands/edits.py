"""Concrete reversible workbook edit commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from typing import Any

from excelclone.commands.base import Command
from excelclone.core.cell import Cell, CellFormat
from excelclone.core.conditional import FormatPatch
from excelclone.core.engine import FormulaEngine, RecalculationResult
from excelclone.core.sheet import Sheet


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
        if not self._captured:
            self.previous = {
                (row, column): sheet.get_cell(row, column)
                for row in range(minimum_row, maximum_row + 1)
                for column in range(minimum_column, maximum_column + 1)
            }
            self._captured = True
        for (row, column), original in self.previous.items():
            current = sheet.get_cell(row, column)
            sheet.put_cell(
                row,
                column,
                replace(current, format=self.patch.apply(original.format)),
            )

    def undo(self) -> None:
        if not self._captured:
            raise RuntimeError("Command has not been executed")
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
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
        self.engine.workbook.rename_sheet(selected.name, self.new_name)
        self.engine.rebuild_index()

    def undo(self) -> None:
        if self.old_name is None:
            raise RuntimeError("Command has not been executed")
        self.engine.workbook.rename_sheet(self.new_name, self.old_name)
        self.engine.rebuild_index()
