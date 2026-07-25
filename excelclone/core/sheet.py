"""Sparse spreadsheet sheet model."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from excelclone.core.cell import EMPTY_CELL, Cell, CellFormat
from excelclone.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference

_UNSET = object()


class Sheet:
    """A sparse Excel-sized grid whose reads do not allocate cells."""

    __slots__ = (
        "_cells",
        "name",
        "row_heights",
        "column_widths",
        "hidden_rows",
        "hidden_columns",
        "filtered_rows",
        "auto_filter",
        "data_validations",
        "charts",
        "merged_ranges",
        "conditional_formats",
        "freeze_panes",
        "tab_color",
        "visible",
    )

    def __init__(self, name: str) -> None:
        if not name:
            raise ValueError("Sheet name cannot be empty")
        self.name = name
        self._cells: dict[tuple[int, int], Cell] = {}
        self.row_heights: dict[int, float] = {}
        self.column_widths: dict[int, float] = {}
        self.hidden_rows: set[int] = set()
        self.hidden_columns: set[int] = set()
        self.filtered_rows: set[int] = set()
        self.auto_filter: Any = None
        self.data_validations: list[Any] = []
        self.charts: list[Any] = []
        self.merged_ranges: list[RangeReference] = []
        self.conditional_formats: list[Any] = []
        self.freeze_panes: tuple[int, int] | None = None
        self.tab_color: str | None = None
        self.visible = True

    @property
    def populated_count(self) -> int:
        """Return the count of allocated cells."""
        return len(self._cells)

    @property
    def used_range(self) -> RangeReference | None:
        """Return the minimum bounding range of allocated cells."""
        if not self._cells:
            return None
        rows = [coordinate[0] for coordinate in self._cells]
        columns = [coordinate[1] for coordinate in self._cells]
        return RangeReference(
            CellReference(min(rows), min(columns), sheet=self.name),
            CellReference(max(rows), max(columns), sheet=self.name),
        )

    def get_cell(self, row: int, column: int) -> Cell:
        """Return a cell without allocating a blank coordinate."""
        self._validate_coordinate(row, column)
        return self._cells.get((row, column), EMPTY_CELL)

    def set_cell(
        self,
        row: int,
        column: int,
        raw_input: Any,
        *,
        cached_value: Any = _UNSET,
        cell_format: CellFormat | None = None,
        error: str | None = None,
    ) -> Cell:
        """Replace a coordinate and return its previous immutable cell."""
        self._validate_coordinate(row, column)
        if cached_value is _UNSET:
            cached_value = (
                None
                if isinstance(raw_input, str) and raw_input.startswith("=")
                else raw_input
            )
        cell = Cell(
            raw_input=raw_input,
            cached_value=cached_value,
            format=cell_format if cell_format is not None else CellFormat(),
            error=error,
        )
        return self.put_cell(row, column, cell)

    def put_cell(self, row: int, column: int, cell: Cell) -> Cell:
        """Store an immutable cell value and return the prior value."""
        self._validate_coordinate(row, column)
        previous = self._cells.get((row, column), EMPTY_CELL)
        if cell.is_empty:
            self._cells.pop((row, column), None)
        else:
            self._cells[(row, column)] = cell
        return previous

    def update_cache(
        self,
        row: int,
        column: int,
        value: Any,
        *,
        error: str | None = None,
    ) -> Cell:
        """Replace a cell's calculated state without changing its input or format."""
        current = self.get_cell(row, column)
        return self.put_cell(
            row,
            column,
            replace(current, cached_value=value, error=error),
        )

    def clear_cell(self, row: int, column: int) -> Cell:
        """Remove a coordinate and return its previous cell."""
        self._validate_coordinate(row, column)
        return self._cells.pop((row, column), EMPTY_CELL)

    def iter_populated(self) -> Iterator[tuple[tuple[int, int], Cell]]:
        """Iterate allocated cells in deterministic row-major order."""
        for coordinate in sorted(self._cells):
            yield coordinate, self._cells[coordinate]

    def copy(self, *, name: str | None = None) -> Sheet:
        """Create an independent sheet with identical cells and metadata."""
        duplicate = Sheet(name if name is not None else self.name)
        duplicate._cells = self._cells.copy()
        duplicate.row_heights = self.row_heights.copy()
        duplicate.column_widths = self.column_widths.copy()
        duplicate.hidden_rows = self.hidden_rows.copy()
        duplicate.hidden_columns = self.hidden_columns.copy()
        duplicate.filtered_rows = self.filtered_rows.copy()
        duplicate.auto_filter = self.auto_filter
        duplicate.data_validations = list(self.data_validations)
        duplicate.charts = list(self.charts)
        duplicate.merged_ranges = list(self.merged_ranges)
        duplicate.conditional_formats = list(self.conditional_formats)
        duplicate.freeze_panes = self.freeze_panes
        duplicate.tab_color = self.tab_color
        duplicate.visible = self.visible
        return duplicate

    def restore_from(self, snapshot: Sheet) -> None:
        """Replace this sheet's data and metadata from a snapshot."""
        restored = snapshot.copy(name=self.name)
        self._cells = restored._cells
        self.row_heights = restored.row_heights
        self.column_widths = restored.column_widths
        self.hidden_rows = restored.hidden_rows
        self.hidden_columns = restored.hidden_columns
        self.filtered_rows = restored.filtered_rows
        self.auto_filter = restored.auto_filter
        self.data_validations = restored.data_validations
        self.charts = restored.charts
        self.merged_ranges = restored.merged_ranges
        self.conditional_formats = restored.conditional_formats
        self.freeze_panes = restored.freeze_panes
        self.tab_color = restored.tab_color
        self.visible = restored.visible

    @staticmethod
    def _validate_coordinate(row: int, column: int) -> None:
        if not 0 <= row < MAX_ROWS or not 0 <= column < MAX_COLUMNS:
            raise IndexError(
                f"Cell coordinate ({row}, {column}) is outside the spreadsheet"
            )
