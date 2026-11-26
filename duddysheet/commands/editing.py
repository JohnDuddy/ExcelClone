"""Undoable commands for Excel's editing, visibility, outline, and protection actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duddysheet.commands.edits import _WorkbookSnapshotCommand
from duddysheet.core.cell import Note, SheetProtection
from duddysheet.core.editing import Rect, clear_ranges, move_cells, shift_cells


@dataclass
class MoveCellsCommand(_WorkbookSnapshotCommand):
    """Cut-and-paste: move cells and re-point the formulas that referenced them."""

    source_sheet: str
    source: Rect
    target_sheet: str
    target_row: int
    target_column: int

    @property
    def description(self) -> str:
        return "Move cells"

    def do(self) -> None:
        self._capture()
        move_cells(
            self.engine.workbook,
            self.source_sheet,
            self.source,
            self.target_sheet,
            self.target_row,
            self.target_column,
        )
        self._rebuild()


@dataclass
class ShiftCellsCommand(_WorkbookSnapshotCommand):
    """Insert or delete cells, shifting neighbors down/right or up/left."""

    sheet_name: str
    area: Rect
    direction: str

    @property
    def description(self) -> str:
        return "Insert cells" if self.direction in ("down", "right") else "Delete cells"

    def do(self) -> None:
        self._capture()
        shift_cells(self.engine.workbook, self.sheet_name, self.area, direction=self.direction)
        self._rebuild()


@dataclass
class ClearRangesCommand(_WorkbookSnapshotCommand):
    """Clear contents, formats, notes, hyperlinks, or all of a selection."""

    sheet_name: str
    ranges: tuple[Rect, ...]
    kind: str = "contents"

    @property
    def description(self) -> str:
        return {
            "all": "Clear all",
            "contents": "Clear contents",
            "formats": "Clear formats",
            "notes": "Clear notes",
            "hyperlinks": "Clear hyperlinks",
        }.get(self.kind, "Clear")

    def do(self) -> None:
        self._capture()
        clear_ranges(self.engine.workbook, self.sheet_name, list(self.ranges), kind=self.kind)
        self._rebuild()


@dataclass
class SetNoteCommand(_WorkbookSnapshotCommand):
    """Add, edit, or delete the note on one cell."""

    sheet_name: str
    row: int
    column: int
    note: Note | None

    @property
    def description(self) -> str:
        return "Delete note" if self.note is None else "Edit note"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        if self.note is None or not self.note.text.strip():
            sheet.notes.pop((self.row, self.column), None)
        else:
            sheet.notes[(self.row, self.column)] = self.note


@dataclass
class SetHiddenCommand(_WorkbookSnapshotCommand):
    """Hide or unhide rows or columns."""

    sheet_name: str
    axis: str
    indexes: tuple[int, ...]
    hidden: bool

    @property
    def description(self) -> str:
        noun = "rows" if self.axis == "row" else "columns"
        return f"{'Hide' if self.hidden else 'Unhide'} {noun}"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        target: set[int] = sheet.hidden_rows if self.axis == "row" else sheet.hidden_columns
        if self.hidden:
            target.update(self.indexes)
        else:
            target.difference_update(self.indexes)
            if self.axis == "row":
                sheet.filtered_rows.difference_update(self.indexes)


@dataclass
class OutlineCommand(_WorkbookSnapshotCommand):
    """Group (indent) or ungroup rows or columns in the outline."""

    sheet_name: str
    axis: str
    first: int
    last: int
    group: bool

    @property
    def description(self) -> str:
        return "Group" if self.group else "Ungroup"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        levels = sheet.row_outline if self.axis == "row" else sheet.column_outline
        for index in range(self.first, self.last + 1):
            level = levels.get(index, 0) + (1 if self.group else -1)
            level = max(0, min(7, level))
            if level:
                levels[index] = level
            else:
                levels.pop(index, None)


@dataclass
class CollapseOutlineCommand(_WorkbookSnapshotCommand):
    """Show only outline levels up to ``level`` by hiding deeper rows/columns."""

    sheet_name: str
    axis: str
    level: int
    indexes: tuple[int, ...] | None = None
    expand: bool | None = None

    @property
    def description(self) -> str:
        return "Change outline level"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        levels = sheet.row_outline if self.axis == "row" else sheet.column_outline
        hidden: set[int] = sheet.hidden_rows if self.axis == "row" else sheet.hidden_columns
        if self.indexes is not None:
            if self.expand:
                hidden.difference_update(self.indexes)
            else:
                hidden.update(self.indexes)
            return
        for index, depth in levels.items():
            if depth >= self.level:
                hidden.add(index)
            else:
                hidden.discard(index)


@dataclass
class SetProtectionCommand(_WorkbookSnapshotCommand):
    """Protect or unprotect a worksheet."""

    sheet_name: str
    protection: SheetProtection | None

    @property
    def description(self) -> str:
        return "Unprotect sheet" if self.protection is None else "Protect sheet"

    def do(self) -> None:
        self._capture()
        sheet = self.engine.workbook.get_sheet(self.sheet_name)
        sheet.protection = self.protection


@dataclass
class SetWorkbookOptionCommand(_WorkbookSnapshotCommand):
    """Change a workbook option such as calculation mode or structure protection."""

    name: str
    value: Any

    @property
    def description(self) -> str:
        return "Change workbook option"

    def do(self) -> None:
        self._capture()
        setattr(self.engine.workbook, self.name, self.value)
        self._rebuild()
