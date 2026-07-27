"""Spreadsheet-oriented QTableView behavior and clipboard integration."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QMimeData,
    QModelIndex,
    QItemSelection,
    QItemSelectionModel,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTableView

from duddysheet.commands.edits import FillRangeCommand, PasteCellsCommand, SetRangeCommand
from duddysheet.core.cell import Cell
from duddysheet.core.clipboard import (
    RICH_CELL_MIME,
    decode_cell_matrix,
    encode_cell_matrix,
)
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.ui.grid_model import GridModel


class GridView(QTableView):
    """Virtualized spreadsheet view with keyboard and TSV clipboard behavior."""

    currentCellChanged = Signal(QModelIndex)
    selectionSummaryChanged = Signal(str)
    externalHyperlinkRequested = Signal(str)
    internalHyperlinkRequested = Signal(str)

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
        self._fill_handle_rect = QRect()
        self._fill_drag_source: tuple[int, int, int, int] | None = None
        self._fill_drag_target: QModelIndex | None = None
        self._frozen_rows = self._create_frozen_view(
            "frozenRows",
            "border: 0; border-bottom: 2px solid #557063;",
        )
        self._frozen_columns = self._create_frozen_view(
            "frozenColumns",
            "border: 0; border-right: 2px solid #557063;",
        )
        self._frozen_corner = self._create_frozen_view(
            "frozenCorner",
            "border: 0; border-right: 2px solid #557063;"
            "border-bottom: 2px solid #557063;",
        )
        self.horizontalScrollBar().valueChanged.connect(
            self._sync_horizontal_frozen_scroll
        )
        self.verticalScrollBar().valueChanged.connect(
            self._sync_vertical_frozen_scroll
        )
        self.clicked.connect(self.activate_hyperlink)

    def setModel(self, model: GridModel) -> None:
        super().setModel(model)
        for overlay in self._frozen_views:
            overlay.setModel(model)
            overlay.setSelectionModel(self.selectionModel())
        self.selectionModel().currentChanged.connect(
            lambda current, previous: self.currentCellChanged.emit(current)
        )

    def setItemDelegate(self, delegate: Any) -> None:
        super().setItemDelegate(delegate)
        if hasattr(self, "_frozen_rows"):
            for overlay in self._frozen_views:
                overlay.setItemDelegate(delegate)

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
        self.viewport().update()

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

    def activate_hyperlink(self, index: QModelIndex) -> bool:
        """Emit the appropriate activation request for a linked cell."""
        if not index.isValid():
            return False
        hyperlink = self.grid_model.sheet.get_cell(
            index.row(),
            index.column(),
        ).hyperlink
        if hyperlink is None:
            return False
        if hyperlink.internal:
            self.internalHyperlinkRequested.emit(hyperlink.target)
        else:
            self.externalHyperlinkRequested.emit(hyperlink.target)
        return True

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
        for overlay in self._frozen_views:
            overlay.verticalHeader().setDefaultSectionSize(
                self.verticalHeader().defaultSectionSize()
            )
            overlay.horizontalHeader().setDefaultSectionSize(
                self.horizontalHeader().defaultSectionSize()
            )
            overlay.setFont(font)
        self._sync_frozen_views()

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
        self._sync_frozen_views()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the Excel-style fill handle and active drag outline."""
        super().paintEvent(event)
        self._fill_handle_rect = QRect()
        bounds = self.selection_bounds()
        if bounds is None:
            return
        lower_right = self.visualRect(
            self.grid_model.index(bounds[2], bounds[3])
        )
        if lower_right.isValid() and lower_right.intersects(self.viewport().rect()):
            self._fill_handle_rect = QRect(
                lower_right.right() - 3,
                lower_right.bottom() - 3,
                7,
                7,
            )
        painter = QPainter(self.viewport())
        if not self._fill_handle_rect.isNull():
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(QBrush(QColor("#217346")))
            painter.drawRect(self._fill_handle_rect)
        if self._fill_drag_source is not None and self._fill_drag_target is not None:
            preview = self._fill_preview_rect(
                self._fill_drag_source,
                self._fill_drag_target.row(),
                self._fill_drag_target.column(),
            )
            if preview is not None:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#217346"), 2, Qt.PenStyle.DashLine))
                painter.drawRect(preview.adjusted(1, 1, -1, -1))
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._fill_handle_rect.isNull()
            and self._fill_handle_rect.contains(event.position().toPoint())
        ):
            self._fill_drag_source = self.selection_bounds()
            self._fill_drag_target = None
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._fill_drag_source is not None:
            target = self.indexAt(event.position().toPoint())
            if target.isValid():
                self._fill_drag_target = target
                self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._fill_drag_source is not None:
            target = self.indexAt(event.position().toPoint())
            source = self._fill_drag_source
            self._fill_drag_source = None
            self._fill_drag_target = None
            if target.isValid():
                self.fill_drag_to(target.row(), target.column(), source)
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_frozen_views()

    def fill_drag_to(
        self,
        row: int,
        column: int,
        source_bounds: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """Extend the selected source along one axis through a fill command."""
        bounds = source_bounds or self.selection_bounds()
        if bounds is None:
            return False
        min_row, min_column, max_row, max_column = bounds
        vertical_extension = max(min_row - row, row - max_row, 0)
        horizontal_extension = max(min_column - column, column - max_column, 0)
        if vertical_extension == 0 and horizontal_extension == 0:
            return False
        source = RangeReference(
            CellReference(min_row, min_column),
            CellReference(max_row, max_column),
        )
        if vertical_extension >= horizontal_extension:
            target = RangeReference(
                CellReference(min(min_row, row), min_column),
                CellReference(max(max_row, row), max_column),
            )
        else:
            target = RangeReference(
                CellReference(min_row, min(min_column, column)),
                CellReference(max_row, max(max_column, column)),
            )
        self.grid_model.history.execute(
            FillRangeCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                source,
                target,
            )
        )
        return True

    @property
    def frozen_views(self) -> tuple[QTableView, QTableView, QTableView]:
        """Expose the row, column, and corner overlays for view coordination."""
        return self._frozen_views

    @property
    def _frozen_views(self) -> tuple[QTableView, QTableView, QTableView]:
        return self._frozen_rows, self._frozen_columns, self._frozen_corner

    def _create_frozen_view(self, name: str, border: str) -> QTableView:
        view = QTableView(self.viewport())
        view.setObjectName(name)
        view.horizontalHeader().hide()
        view.verticalHeader().hide()
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        view.setEditTriggers(self.editTriggers())
        view.setWordWrap(False)
        view.setStyleSheet(f"QTableView {{ background: white; {border} }}")
        view.clicked.connect(self.activate_hyperlink)
        view.hide()
        return view

    def _sync_horizontal_frozen_scroll(self, value: int) -> None:
        self._frozen_rows.horizontalScrollBar().setValue(value)

    def _sync_vertical_frozen_scroll(self, value: int) -> None:
        self._frozen_columns.verticalScrollBar().setValue(value)

    def _sync_frozen_views(self) -> None:
        if self.model() is None:
            return
        panes = self.grid_model.sheet.freeze_panes
        if panes is None or panes == (0, 0):
            for view in self._frozen_views:
                view.hide()
            return
        frozen_rows, frozen_columns = panes
        for overlay in self._frozen_views:
            overlay.setShowGrid(self.showGrid())
            overlay.verticalHeader().setDefaultSectionSize(
                self.verticalHeader().defaultSectionSize()
            )
            overlay.horizontalHeader().setDefaultSectionSize(
                self.horizontalHeader().defaultSectionSize()
            )
        sheet = self.grid_model.sheet
        for row, height in sheet.row_heights.items():
            pixels = max(1, round(height * 4 / 3))
            for overlay in self._frozen_views:
                overlay.setRowHeight(row, pixels)
        for column, width in sheet.column_widths.items():
            pixels = max(1, round(width * 7))
            for overlay in self._frozen_views:
                overlay.setColumnWidth(column, pixels)

        viewport = self.viewport().rect()
        frozen_height = self._section_extent(
            self.verticalHeader(),
            frozen_rows,
            viewport.height(),
        )
        frozen_width = self._section_extent(
            self.horizontalHeader(),
            frozen_columns,
            viewport.width(),
        )
        if frozen_rows:
            self._frozen_rows.setGeometry(0, 0, viewport.width(), frozen_height)
            self._frozen_rows.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value()
            )
            self._frozen_rows.show()
        else:
            self._frozen_rows.hide()
        if frozen_columns:
            self._frozen_columns.setGeometry(0, 0, frozen_width, viewport.height())
            self._frozen_columns.verticalScrollBar().setValue(
                self.verticalScrollBar().value()
            )
            self._frozen_columns.show()
        else:
            self._frozen_columns.hide()
        if frozen_rows and frozen_columns:
            self._frozen_corner.setGeometry(0, 0, frozen_width, frozen_height)
            self._frozen_corner.horizontalScrollBar().setValue(0)
            self._frozen_corner.verticalScrollBar().setValue(0)
            self._frozen_corner.show()
        else:
            self._frozen_corner.hide()
        self._frozen_rows.raise_()
        self._frozen_columns.raise_()
        self._frozen_corner.raise_()

    @staticmethod
    def _section_extent(header: Any, count: int, limit: int) -> int:
        extent = 0
        for section in range(count):
            extent += header.sectionSize(section)
            if extent >= limit:
                return limit
        return extent

    def _fill_preview_rect(
        self,
        bounds: tuple[int, int, int, int],
        row: int,
        column: int,
    ) -> QRect | None:
        min_row, min_column, max_row, max_column = bounds
        vertical_extension = max(min_row - row, row - max_row, 0)
        horizontal_extension = max(min_column - column, column - max_column, 0)
        if vertical_extension == 0 and horizontal_extension == 0:
            return None
        if vertical_extension >= horizontal_extension:
            min_row, max_row = min(min_row, row), max(max_row, row)
        else:
            min_column, max_column = min(min_column, column), max(max_column, column)
        top_left = self.visualRect(self.grid_model.index(min_row, min_column))
        bottom_right = self.visualRect(self.grid_model.index(max_row, max_column))
        return top_left.united(bottom_right)
