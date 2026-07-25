"""Spreadsheet-oriented QTableView behavior and clipboard integration."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QMimeData,
    QModelIndex,
    QItemSelection,
    QItemSelectionModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTableView

from excelclone.commands.edits import FillRangeCommand, PasteCellsCommand, SetRangeCommand
from excelclone.core.cell import Cell
from excelclone.core.clipboard import (
    RICH_CELL_MIME,
    decode_cell_matrix,
    encode_cell_matrix,
)
from excelclone.core.refs import CellReference, RangeReference
from excelclone.ui.grid_model import GridModel


class GridView(QTableView):
    """Virtualized spreadsheet view with keyboard and TSV clipboard behavior."""

    currentCellChanged = Signal(QModelIndex)
    selectionSummaryChanged = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("spreadsheetGrid")
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setDefaultSectionSize(96)
        self.zoom_percent = 100
        self._applied_hidden_rows: set[int] = set()
        self._applied_hidden_columns: set[int] = set()

    def setModel(self, model: GridModel) -> None:
        super().setModel(model)
        self.selectionModel().currentChanged.connect(
            lambda current, previous: self.currentCellChanged.emit(current)
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        key = event.key()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self.copy_selection()
                return
            if key == Qt.Key.Key_V:
                self.paste_clipboard()
                return
            if key == Qt.Key.Key_Z:
                self.grid_model.history.undo()
                return
            if key == Qt.Key.Key_Y:
                self.grid_model.history.redo()
                return
            if key == Qt.Key.Key_Enter:
                self.fill_selection_with_current()
                return
            if key == Qt.Key.Key_D:
                self.fill_down()
                return
            if key == Qt.Key.Key_R:
                self.fill_right()
                return
        if key == Qt.Key.Key_Delete:
            self.clear_selection_contents()
            return
        if key == Qt.Key.Key_F2 and self.currentIndex().isValid():
            self.edit(self.currentIndex())
            return
        super().keyPressEvent(event)

    def selectionChanged(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        super().selectionChanged(selected, deselected)
        values: list[float] = []
        count = 0
        for index in self.selectedIndexes()[:10_000]:
            raw = self.grid_model.sheet.get_cell(index.row(), index.column()).display_value
            if raw is not None:
                count += 1
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                values.append(float(raw))
        if values:
            summary = (
                f"Average: {sum(values) / len(values):g}   "
                f"Count: {count}   Sum: {sum(values):g}"
            )
        else:
            summary = f"Count: {count}"
        self.selectionSummaryChanged.emit(summary)

    @property
    def grid_model(self) -> GridModel:
        model = self.model()
        if not isinstance(model, GridModel):
            raise RuntimeError("GridView requires GridModel")
        return model

    def copy_selection(self) -> None:
        """Copy the selected bounding rectangle as TSV."""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        rows = [index.row() for index in indexes]
        columns = [index.column() for index in indexes]
        minimum_row, maximum_row = min(rows), max(rows)
        minimum_column, maximum_column = min(columns), max(columns)
        selected = {(index.row(), index.column()) for index in indexes}
        lines: list[str] = []
        for row in range(minimum_row, maximum_row + 1):
            fields = [
                (
                    self.grid_model.data(
                        self.grid_model.index(row, column),
                        Qt.ItemDataRole.DisplayRole,
                    )
                    or ""
                )
                if (row, column) in selected
                else ""
                for column in range(minimum_column, maximum_column + 1)
            ]
            lines.append("\t".join(str(field) for field in fields))
        cells = tuple(
            tuple(
                (
                    self.grid_model.sheet.get_cell(row, column)
                    if (row, column) in selected
                    else Cell()
                )
                for column in range(minimum_column, maximum_column + 1)
            )
            for row in range(minimum_row, maximum_row + 1)
        )
        mime = QMimeData()
        mime.setText("\n".join(lines))
        mime.setData(
            RICH_CELL_MIME,
            encode_cell_matrix(cells, (minimum_row, minimum_column)),
        )
        QApplication.clipboard().setMimeData(mime)

    def paste_clipboard(self) -> None:
        """Paste TSV text at the current cell as one command."""
        current = self.currentIndex()
        if not current.isValid():
            return
        mime = QApplication.clipboard().mimeData()
        if mime.hasFormat(RICH_CELL_MIME):
            try:
                cells, origin = decode_cell_matrix(bytes(mime.data(RICH_CELL_MIME)))
            except (ValueError, TypeError):
                pass
            else:
                self.grid_model.history.execute(
                    PasteCellsCommand(
                        self.grid_model.engine,
                        self.grid_model.active_sheet_name,
                        current.row(),
                        current.column(),
                        cells,
                        origin,
                    )
                )
                self.grid_model.refresh()
                return
        text = QApplication.clipboard().text().replace("\r\n", "\n").replace("\r", "\n")
        if text.endswith("\n"):
            text = text[:-1]
        values = tuple(tuple(field for field in line.split("\t")) for line in text.split("\n"))
        if not values:
            return
        self.grid_model.history.execute(
            SetRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                current.row(),
                current.column(),
                values,
            )
        )
        self.grid_model.refresh()

    def clear_selection_contents(self) -> None:
        """Clear selected cells as one range command when rectangular."""
        indexes = self.selectedIndexes()
        if not indexes:
            return
        rows = [index.row() for index in indexes]
        columns = [index.column() for index in indexes]
        minimum_row, maximum_row = min(rows), max(rows)
        minimum_column, maximum_column = min(columns), max(columns)
        values = tuple(
            tuple(None for _ in range(minimum_column, maximum_column + 1))
            for _ in range(minimum_row, maximum_row + 1)
        )
        self.grid_model.history.execute(
            SetRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                minimum_row,
                minimum_column,
                values,
            )
        )
        self.grid_model.refresh()

    def fill_selection_with_current(self) -> None:
        """Fill every selected cell with the current cell's raw input."""
        indexes = self.selectedIndexes()
        current = self.currentIndex()
        if not indexes or not current.isValid():
            return
        raw = self.grid_model.sheet.get_cell(current.row(), current.column()).raw_input
        bounds = self.selection_bounds()
        if bounds is None:
            return
        minimum_row, minimum_column, maximum_row, maximum_column = bounds
        values = tuple(
            tuple(
                raw
                for _ in range(minimum_column, maximum_column + 1)
            )
            for _ in range(minimum_row, maximum_row + 1)
        )
        self.grid_model.history.execute(
            SetRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                minimum_row,
                minimum_column,
                values,
            )
        )

    def fill_down(self) -> None:
        """Fill selected columns downward from their top row."""
        bounds = self.selection_bounds()
        if bounds is None or bounds[0] == bounds[2]:
            return
        source = RangeReference(
            CellReference(bounds[0], bounds[1]),
            CellReference(bounds[0], bounds[3]),
        )
        target = RangeReference(
            CellReference(bounds[0], bounds[1]),
            CellReference(bounds[2], bounds[3]),
        )
        self.grid_model.history.execute(
            FillRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                source,
                target,
            )
        )

    def fill_right(self) -> None:
        """Fill selected rows rightward from their left column."""
        bounds = self.selection_bounds()
        if bounds is None or bounds[1] == bounds[3]:
            return
        source = RangeReference(
            CellReference(bounds[0], bounds[1]),
            CellReference(bounds[2], bounds[1]),
        )
        target = RangeReference(
            CellReference(bounds[0], bounds[1]),
            CellReference(bounds[2], bounds[3]),
        )
        self.grid_model.history.execute(
            FillRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                source,
                target,
            )
        )

    def selection_bounds(self) -> tuple[int, int, int, int] | None:
        """Return the bounding rectangle of selected cells."""
        indexes = self.selectedIndexes()
        if not indexes:
            current = self.currentIndex()
            indexes = [current] if current.isValid() else []
        if not indexes:
            return None
        rows = [index.row() for index in indexes]
        columns = [index.column() for index in indexes]
        return min(rows), min(columns), max(rows), max(columns)

    def set_zoom(self, percent: int) -> None:
        """Set a clamped spreadsheet zoom from 25 through 400 percent."""
        self.zoom_percent = max(25, min(400, int(percent)))
        scale = self.zoom_percent / 100
        self.verticalHeader().setDefaultSectionSize(max(8, round(22 * scale)))
        self.horizontalHeader().setDefaultSectionSize(max(24, round(96 * scale)))
        font = QFont(self.font())
        base_size = self.property("baseFontSize")
        if base_size is None:
            base_size = max(1.0, self.font().pointSizeF())
            self.setProperty("baseFontSize", base_size)
        font.setPointSizeF(float(base_size) * scale)
        self.setFont(font)

    def sync_sheet_metadata(self) -> None:
        """Apply sparse dimensions, hidden axes, and merged spans to the view."""
        sheet = self.grid_model.sheet
        for row in self._applied_hidden_rows - sheet.hidden_rows:
            self.setRowHidden(row, False)
        for row in sheet.hidden_rows:
            self.setRowHidden(row, True)
        self._applied_hidden_rows = set(sheet.hidden_rows)
        for column in self._applied_hidden_columns - sheet.hidden_columns:
            self.setColumnHidden(column, False)
        for column in sheet.hidden_columns:
            self.setColumnHidden(column, True)
        self._applied_hidden_columns = set(sheet.hidden_columns)
        for row, height in sheet.row_heights.items():
            self.setRowHeight(row, max(1, round(height * 4 / 3)))
        for column, width in sheet.column_widths.items():
            self.setColumnWidth(column, max(1, round(width * 7)))
        self.clearSpans()
        for merged in sheet.merged_ranges:
            self.setSpan(
                merged.min_row,
                merged.min_column,
                merged.max_row - merged.min_row + 1,
                merged.max_column - merged.min_column + 1,
            )
