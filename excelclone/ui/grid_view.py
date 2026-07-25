"""Spreadsheet-oriented QTableView behavior and clipboard integration."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QModelIndex, QItemSelection, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTableView

from excelclone.commands.edits import SetRangeCommand
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
        QApplication.clipboard().setText("\n".join(lines))

    def paste_clipboard(self) -> None:
        """Paste TSV text at the current cell as one command."""
        current = self.currentIndex()
        if not current.isValid():
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
        for index in indexes:
            self.grid_model.setData(index, "" if raw is None else str(raw))

