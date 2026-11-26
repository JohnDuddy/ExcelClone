"""Sparse spreadsheet sheet model."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from duddysheet.core.cell import EMPTY_CELL, Cell, CellFormat, Hyperlink
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference

_UNSET = object()
_DEFAULT_FORMAT = CellFormat()


class Sheet:
    """A sparse Excel-sized grid whose reads do not allocate cells."""

    __slots__ = (
        "_cells",
        "_extent",
        "name",
        "row_heights",
        "column_widths",
        "hidden_rows",
        "hidden_columns",
        "filtered_rows",
        "auto_filter",
        "data_validations",
        "charts",
        "sparklines",
        "merged_ranges",
        "conditional_formats",
        "freeze_panes",
        "tab_color",
        "visible",
        "page_setup",
        "notes",
        "row_outline",
        "column_outline",
        "protection",
        "default_column_width",
        "default_row_height",
        "column_formats",
        "row_formats",
        "tables",
        "pivots",
        "data_tables",
        "slicers",
        "solver",
        "drawings",
        "comments",
    )

    def __init__(self, name: str) -> None:
        if not name:
            raise ValueError("Sheet name cannot be empty")
        self.name = name
        self._cells: dict[tuple[int, int], Cell] = {}
        #: Cached (max_row, max_column) of allocated cells; ``None`` when stale.
        self._extent: tuple[int, int] | None = (-1, -1)
        self.row_heights: dict[int, float] = {}
        self.column_widths: dict[int, float] = {}
        self.hidden_rows: set[int] = set()
        self.hidden_columns: set[int] = set()
        self.filtered_rows: set[int] = set()
        self.auto_filter: Any = None
        self.data_validations: list[Any] = []
        self.charts: list[Any] = []
        self.sparklines: list[Any] = []
        self.merged_ranges: list[RangeReference] = []
        self.conditional_formats: list[Any] = []
        self.freeze_panes: tuple[int, int] | None = None
        self.tab_color: str | None = None
        self.visible = True
        #: Optional print layout; ``None`` means the application default.
        self.page_setup: Any = None
        #: Cell notes keyed by (row, column).
        self.notes: dict[tuple[int, int], Any] = {}
        #: Outline (group) levels 1..7 keyed by row or column index.
        self.row_outline: dict[int, int] = {}
        self.column_outline: dict[int, int] = {}
        #: Active ``SheetProtection`` or ``None`` when the sheet is unprotected.
        self.protection: Any = None
        self.default_column_width: float | None = None
        self.default_row_height: float | None = None
        #: Formats applied to whole columns or rows; empty cells there show
        #: them, and newly entered cells inherit them, as in Excel.
        self.column_formats: dict[int, CellFormat] = {}
        self.row_formats: dict[int, CellFormat] = {}
        #: Excel Tables (``TableSpec``), PivotTables (``PivotSpec``), and
        #: What-If data tables (``DataTableSpec``) anchored on this sheet.
        self.tables: list[Any] = []
        self.pivots: list[Any] = []
        self.data_tables: list[Any] = []
        self.slicers: list[Any] = []
        self.solver: Any = None
        self.drawings: list[Any] = []
        self.comments: dict[tuple[int, int], Any] = {}

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

    @property
    def extent(self) -> tuple[int, int]:
        """Return the largest allocated (row, column), or (-1, -1) when empty."""
        if self._extent is None:
            max_row = max_column = -1
            for row, column in self._cells:
                if row > max_row:
                    max_row = row
                if column > max_column:
                    max_column = column
            self._extent = (max_row, max_column)
        return self._extent

    def cell_block(
        self,
        min_row: int,
        min_column: int,
        max_row: int,
        max_column: int,
    ) -> list[list[Cell]]:
        """Return a dense row-major block of cells without allocating blanks."""
        get = self._cells.get
        columns = range(min_column, max_column + 1)
        return [
            [get((row, column), EMPTY_CELL) for column in columns]
            for row in range(min_row, max_row + 1)
        ]

    def effective_format(self, row: int, column: int) -> CellFormat:
        """Return the format a cell shows: its own, else its row's, else its column's."""
        cell = self._cells.get((row, column))
        if cell is not None:
            return cell.format
        if self.row_formats:
            row_format = self.row_formats.get(row)
            if row_format is not None:
                return row_format
        if self.column_formats:
            column_format = self.column_formats.get(column)
            if column_format is not None:
                return column_format
        return _DEFAULT_FORMAT

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
        hyperlink: Hyperlink | None = None,
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
            hyperlink=hyperlink,
        )
        return self.put_cell(row, column, cell)

    def put_cell(self, row: int, column: int, cell: Cell) -> Cell:
        """Store an immutable cell value and return the prior value."""
        self._validate_coordinate(row, column)
        previous = self._cells.get((row, column), EMPTY_CELL)
        if cell.is_empty:
            if self._cells.pop((row, column), None) is not None:
                self._shrink_extent(row, column)
        else:
            self._cells[(row, column)] = cell
            if self._extent is not None:
                max_row, max_column = self._extent
                if row > max_row or column > max_column:
                    self._extent = (max(row, max_row), max(column, max_column))
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
        return self.put_cell(row, column, current.with_result(value, error))

    def clear_cell(self, row: int, column: int) -> Cell:
        """Remove a coordinate and return its previous cell."""
        self._validate_coordinate(row, column)
        previous = self._cells.pop((row, column), EMPTY_CELL)
        if previous is not EMPTY_CELL:
            self._shrink_extent(row, column)
        return previous

    def iter_unordered(self) -> Iterator[tuple[tuple[int, int], Cell]]:
        """Iterate allocated cells without sorting (fast scans)."""
        return iter(list(self._cells.items()))

    def value_rows(self, top: int, left: int, bottom: int, right: int) -> list[list[Any]]:
        """Return a block's displayed values row by row (None for blanks and errors).

        This reads the sparse store directly, which keeps large summaries
        (a PivotTable over 100,000 rows) fast.
        """
        self._validate_coordinate(top, left)
        self._validate_coordinate(bottom, right)
        cells = self._cells
        empty = EMPTY_CELL
        rows: list[list[Any]] = []
        columns = range(left, right + 1)
        for row in range(top, bottom + 1):
            values = []
            for column in columns:
                cell = cells.get((row, column), empty)
                values.append(None if cell.error is not None else cell.display_value)
            rows.append(values)
        return rows

    def iter_populated(self) -> Iterator[tuple[tuple[int, int], Cell]]:
        """Iterate allocated cells in deterministic row-major order."""
        for coordinate in sorted(self._cells):
            yield coordinate, self._cells[coordinate]

    def copy(self, *, name: str | None = None) -> Sheet:
        """Create an independent sheet with identical cells and metadata."""
        duplicate = Sheet(name if name is not None else self.name)
        duplicate._cells = self._cells.copy()
        duplicate._extent = self._extent
        duplicate.row_heights = self.row_heights.copy()
        duplicate.column_widths = self.column_widths.copy()
        duplicate.hidden_rows = self.hidden_rows.copy()
        duplicate.hidden_columns = self.hidden_columns.copy()
        duplicate.filtered_rows = self.filtered_rows.copy()
        duplicate.auto_filter = self.auto_filter
        duplicate.data_validations = list(self.data_validations)
        duplicate.charts = list(self.charts)
        duplicate.sparklines = list(self.sparklines)
        duplicate.merged_ranges = list(self.merged_ranges)
        duplicate.conditional_formats = list(self.conditional_formats)
        duplicate.freeze_panes = self.freeze_panes
        duplicate.tab_color = self.tab_color
        duplicate.visible = self.visible
        duplicate.page_setup = self.page_setup
        duplicate.notes = self.notes.copy()
        duplicate.row_outline = self.row_outline.copy()
        duplicate.column_outline = self.column_outline.copy()
        duplicate.protection = self.protection
        duplicate.default_column_width = self.default_column_width
        duplicate.default_row_height = self.default_row_height
        duplicate.column_formats = self.column_formats.copy()
        duplicate.row_formats = self.row_formats.copy()
        duplicate.tables = list(self.tables)
        duplicate.pivots = list(self.pivots)
        duplicate.data_tables = list(self.data_tables)
        duplicate.slicers = list(self.slicers)
        duplicate.solver = self.solver
        duplicate.drawings = list(self.drawings)
        duplicate.comments = dict(self.comments)
        return duplicate

    def restore_from(self, snapshot: Sheet) -> None:
        """Replace this sheet's data and metadata from a snapshot."""
        restored = snapshot.copy(name=self.name)
        self._cells = restored._cells
        self._extent = None
        self.row_heights = restored.row_heights
        self.column_widths = restored.column_widths
        self.hidden_rows = restored.hidden_rows
        self.hidden_columns = restored.hidden_columns
        self.filtered_rows = restored.filtered_rows
        self.auto_filter = restored.auto_filter
        self.data_validations = restored.data_validations
        self.charts = restored.charts
        self.sparklines = restored.sparklines
        self.merged_ranges = restored.merged_ranges
        self.conditional_formats = restored.conditional_formats
        self.freeze_panes = restored.freeze_panes
        self.tab_color = restored.tab_color
        self.visible = restored.visible
        self.page_setup = restored.page_setup
        self.notes = restored.notes
        self.row_outline = restored.row_outline
        self.column_outline = restored.column_outline
        self.protection = restored.protection
        self.default_column_width = restored.default_column_width
        self.default_row_height = restored.default_row_height
        self.column_formats = restored.column_formats
        self.row_formats = restored.row_formats
        self.tables = restored.tables
        self.pivots = restored.pivots
        self.data_tables = restored.data_tables
        self.slicers = restored.slicers
        self.solver = restored.solver
        self.drawings = restored.drawings
        self.comments = restored.comments

    def _shrink_extent(self, row: int, column: int) -> None:
        """Invalidate the cached extent only when a boundary cell was removed."""
        if self._extent is not None and (
            row >= self._extent[0] or column >= self._extent[1]
        ):
            self._extent = None

    @staticmethod
    def _validate_coordinate(row: int, column: int) -> None:
        if not 0 <= row < MAX_ROWS or not 0 <= column < MAX_COLUMNS:
            raise IndexError(
                f"Cell coordinate ({row}, {column}) is outside the spreadsheet"
            )
