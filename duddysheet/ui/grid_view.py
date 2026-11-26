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

from duddysheet.commands.editing import ClearRangesCommand, MoveCellsCommand
from duddysheet.commands.edits import FillRangeCommand, PasteCellsCommand, SetRangeCommand
from duddysheet.core.cell import Cell
from duddysheet.core.formats import general_number
from duddysheet.core.navigation import (
    clip_range,
    current_region,
    data_edge,
    last_cell,
    selection_statistics,
)
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS
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
    #: Ctrl+PgUp / Ctrl+PgDn ask the window to step to the previous/next sheet.
    sheetStepRequested = Signal(int)
    metadataSynced = Signal()

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
        #: The moving corner of a keyboard-extended selection (Excel keeps the
        #: active cell fixed while Shift+Arrow grows the block).
        self._corner: tuple[int, int] | None = None
        #: (sheet name, rectangle) marked by Cut, shown with a dashed marquee.
        self.cut_source: tuple[str, tuple[int, int, int, int]] | None = None
        #: "enter" when editing began by typing, "edit" after F2/double-click.
        self.edit_mode = "edit"
        #: Formula auditing arrows as ((from_row, from_column), (to_row, to_column)).
        self.trace_arrows: list[tuple[tuple[int, int], tuple[int, int]]] = []
        #: Show Excel's green error-checking triangles.
        self.error_checking = True
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

    # ------------------------------------------------------------ keyboard
    _ARROWS = {
        Qt.Key.Key_Up: (-1, 0),
        Qt.Key.Key_Down: (1, 0),
        Qt.Key.Key_Left: (0, -1),
        Qt.Key.Key_Right: (0, 1),
    }

    def edit(self, index: QModelIndex, trigger: Any = None, event: Any = None) -> bool:
        """Open the editor, remembering whether typing (Enter mode) started it."""
        if trigger is None:
            return super().edit(index)
        if trigger == QAbstractItemView.EditTrigger.AnyKeyPressed:
            self.edit_mode = "enter"
        elif trigger in (
            QAbstractItemView.EditTrigger.DoubleClicked,
            QAbstractItemView.EditTrigger.EditKeyPressed,
        ):
            self.edit_mode = "edit"
        return super().edit(index, trigger, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        modifiers = event.modifiers()
        key = event.key()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        if key in self._ARROWS and not alt:
            d_row, d_column = self._ARROWS[key]
            self.navigate(d_row, d_column, to_edge=control, extend=shift)
            return
        if key in (Qt.Key.Key_Home, Qt.Key.Key_End) and not alt:
            current = self.currentIndex()
            row = current.row() if current.isValid() else 0
            if key == Qt.Key.Key_Home:
                target = (0, 0) if control else (row, 0)
            elif control:
                target = last_cell(self.grid_model.sheet)
            else:
                super().keyPressEvent(event)
                return
            if shift:
                self.extend_to(*target)
            else:
                self.set_active_cell(*target)
            return
        if control and key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self.sheetStepRequested.emit(-1 if key == Qt.Key.Key_PageUp else 1)
            return
        if control and not shift:
            if key == Qt.Key.Key_C:
                self.copy_selection()
                return
            if key == Qt.Key.Key_X:
                self.cut_selection()
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
            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
                self.fill_selection_with_current()
                return
            if key == Qt.Key.Key_D:
                self.fill_down()
                return
            if key == Qt.Key.Key_R:
                self.fill_right()
                return
            if key == Qt.Key.Key_A:
                self.select_current_region_or_all()
                return
            if key == Qt.Key.Key_Space:
                self.select_entire_columns()
                return
        if shift and not control and key == Qt.Key.Key_Space:
            self.select_entire_rows()
            return
        if control and shift and key in (Qt.Key.Key_Space, Qt.Key.Key_Asterisk, Qt.Key.Key_8):
            self.select_current_region_or_all()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not control and not alt:
            self.move_within_selection(-1 if shift else 1, 0)
            return
        if key == Qt.Key.Key_Tab and not control:
            self.move_within_selection(0, 1)
            return
        if key == Qt.Key.Key_Backtab:
            self.move_within_selection(0, -1)
            return
        if key == Qt.Key.Key_Delete:
            self.clear_selection_contents()
            return
        if key == Qt.Key.Key_Backspace and self.currentIndex().isValid():
            self.clear_selection_contents(active_only=True)
            self.edit_mode = "enter"
            super().edit(self.currentIndex())
            return
        if key == Qt.Key.Key_Escape and self.cut_source is not None:
            self.cut_source = None
            self.viewport().update()
            return
        if key == Qt.Key.Key_F2 and self.currentIndex().isValid():
            self.edit_mode = "edit"
            super().edit(self.currentIndex())
            return
        super().keyPressEvent(event)

    def _visible_step(self, row: int, column: int, d_row: int, d_column: int) -> tuple[int, int]:
        """Move one visible cell, skipping hidden rows and columns."""
        sheet = self.grid_model.sheet
        row, column = row + d_row, column + d_column
        while 0 <= row < MAX_ROWS and 0 <= column < MAX_COLUMNS and (
            row in sheet.hidden_rows or column in sheet.hidden_columns
        ):
            row, column = row + d_row, column + d_column
        return (
            max(0, min(MAX_ROWS - 1, row)),
            max(0, min(MAX_COLUMNS - 1, column)),
        )

    def navigate(self, d_row: int, d_column: int, *, to_edge: bool, extend: bool) -> None:
        """Excel arrow navigation: Ctrl jumps to data edges, Shift extends."""
        current = self.currentIndex()
        if not current.isValid():
            self.set_active_cell(0, 0)
            return
        origin = self._corner if extend and self._corner is not None else (current.row(), current.column())
        if to_edge:
            target = data_edge(self.grid_model.sheet, origin[0], origin[1], d_row, d_column)
        else:
            target = self._visible_step(origin[0], origin[1], d_row, d_column)
        if extend:
            self.extend_to(*target)
        else:
            self.set_active_cell(*target)

    def set_active_cell(self, row: int, column: int) -> None:
        """Select one cell and make it active, scrolling it into view."""
        index = self.grid_model.index(row, column)
        if not index.isValid():
            return
        self.setCurrentIndex(index)
        self.selectionModel().select(
            index,
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        self._corner = (row, column)
        self.scrollTo(index)

    def extend_to(self, row: int, column: int) -> None:
        """Grow the selection from the active cell to (row, column)."""
        current = self.currentIndex()
        if not current.isValid():
            return
        top, bottom = sorted((current.row(), row))
        left, right = sorted((current.column(), column))
        self.select_block(top, left, bottom, right, keep_current=True)
        self._corner = (row, column)
        self.scrollTo(self.grid_model.index(row, column))

    def select_block(
        self,
        top: int,
        left: int,
        bottom: int,
        right: int,
        *,
        keep_current: bool = False,
    ) -> None:
        """Select a rectangle as one selection range."""
        model = self.grid_model
        selection = QItemSelection(model.index(top, left), model.index(bottom, right))
        self.selectionModel().select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        if not keep_current:
            self.selectionModel().setCurrentIndex(
                model.index(top, left),
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )

    def select_entire_columns(self) -> None:
        """Ctrl+Space: select the columns of the current selection."""
        bounds = self.selection_bounds()
        if bounds is not None:
            self.select_block(0, bounds[1], MAX_ROWS - 1, bounds[3], keep_current=True)

    def select_entire_rows(self) -> None:
        """Shift+Space: select the rows of the current selection."""
        bounds = self.selection_bounds()
        if bounds is not None:
            self.select_block(bounds[0], 0, bounds[2], MAX_COLUMNS - 1, keep_current=True)

    def select_current_region_or_all(self) -> None:
        """Ctrl+A: select the data region; when already selected, the whole sheet."""
        current = self.currentIndex()
        if not current.isValid():
            return
        region = current_region(self.grid_model.sheet, current.row(), current.column())
        bounds = self.selection_bounds()
        single_empty = region[0] == region[2] and region[1] == region[3]
        if bounds == region or single_empty:
            self.select_block(0, 0, MAX_ROWS - 1, MAX_COLUMNS - 1, keep_current=True)
        else:
            self.select_block(*region, keep_current=True)

    def move_within_selection(self, d_row: int, d_column: int) -> None:
        """Enter/Tab: move the active cell, cycling inside a multi-cell selection."""
        current = self.currentIndex()
        if not current.isValid():
            return
        ranges = self.selection_ranges()
        bounds = self.selection_bounds()
        single = (
            bounds is None
            or (bounds[0] == bounds[2] and bounds[1] == bounds[3])
            or len(ranges) != 1
            or (bounds[2] - bounds[0] + 1) * (bounds[3] - bounds[1] + 1) > 1_000_000
        )
        if single:
            target = self._visible_step(current.row(), current.column(), d_row, d_column)
            self.set_active_cell(*target)
            return
        top, left, bottom, right = bounds
        row, column = current.row(), current.column()
        if d_row:
            row += d_row
            if row > bottom:
                row, column = top, column + 1 if column < right else left
            elif row < top:
                row, column = bottom, column - 1 if column > left else right
        else:
            column += d_column
            if column > right:
                column, row = left, row + 1 if row < bottom else top
            elif column < left:
                column, row = right, row - 1 if row > top else bottom
        self.selectionModel().setCurrentIndex(
            self.grid_model.index(row, column),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )
        self.scrollTo(self.grid_model.index(row, column))

    def move_after_edit(self, d_row: int, d_column: int) -> None:
        """Move after committing an edit with Enter, Tab, or an arrow key."""
        self.move_within_selection(d_row, d_column)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex) -> None:
        super().currentChanged(current, previous)
        if current.isValid() and not (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._corner = (current.row(), current.column())

    # ----------------------------------------------------------- selection
    def selection_ranges(self) -> list[tuple[int, int, int, int]]:
        """Return selected rectangles as (top, left, bottom, right) without expanding cells."""
        ranges: list[tuple[int, int, int, int]] = []
        model = self.selectionModel()
        if model is not None:
            for item in model.selection():
                ranges.append((item.top(), item.left(), item.bottom(), item.right()))
        if not ranges:
            current = self.currentIndex()
            if current.isValid():
                ranges.append((current.row(), current.column(), current.row(), current.column()))
        return ranges

    def selectionChanged(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        super().selectionChanged(selected, deselected)
        self.selectionSummaryChanged.emit(self.selection_summary())
        self.viewport().update()

    def selection_summary(self) -> str:
        """Return Excel's status bar text: Average, Count, and Sum of the selection."""
        if self.model() is None:
            return ""
        ranges = self.selection_ranges()
        area = sum((b - t + 1) * (r - l + 1) for t, l, b, r in ranges)
        if area <= 1:
            return ""
        statistics = selection_statistics(self.grid_model.sheet, ranges)
        if statistics.count == 0:
            return ""
        if statistics.numerical_count == 0:
            return f"Count: {statistics.count}"
        average = general_number(statistics.average or 0.0)
        total = general_number(statistics.total)
        return f"Average: {average}   Count: {statistics.count}   Sum: {total}"

    @property
    def grid_model(self) -> GridModel:
        model = self.model()
        if not isinstance(model, GridModel):
            raise RuntimeError("GridView requires GridModel")
        return model

    def _copy_bounds(self) -> tuple[int, int, int, int] | None:
        bounds = self.selection_bounds()
        if bounds is None:
            return None
        whole = bounds[2] - bounds[0] + 1 >= MAX_ROWS or bounds[3] - bounds[1] + 1 >= MAX_COLUMNS
        if whole:
            clipped = clip_range(self.grid_model.sheet, bounds)
            return clipped if clipped is not None else (bounds[0], bounds[1], bounds[0], bounds[1])
        return bounds

    def copy_selection(self) -> None:
        """Copy the selected rectangle as TSV text plus rich cells."""
        bounds = self._copy_bounds()
        if bounds is None:
            return
        self.cut_source = None
        minimum_row, minimum_column, maximum_row, maximum_column = bounds
        sheet = self.grid_model.sheet
        block = sheet.cell_block(minimum_row, minimum_column, maximum_row, maximum_column)
        lines: list[str] = []
        for offset, row_cells in enumerate(block):
            fields = []
            for column_offset, cell in enumerate(row_cells):
                index = self.grid_model.index(minimum_row + offset, minimum_column + column_offset)
                text = self.grid_model.data(index, Qt.ItemDataRole.DisplayRole) if not cell.is_empty else ""
                fields.append("" if text is None else str(text))
            lines.append("\t".join(fields))
        cells = tuple(tuple(row_cells) for row_cells in block)
        mime = QMimeData()
        mime.setText("\n".join(lines))
        mime.setData(
            RICH_CELL_MIME,
            encode_cell_matrix(cells, (minimum_row, minimum_column)),
        )
        QApplication.clipboard().setMimeData(mime)

    def cut_selection(self) -> None:
        """Mark the selection for moving; the next paste moves it (Ctrl+X)."""
        bounds = self._copy_bounds()
        if bounds is None:
            return
        self.copy_selection()
        self.cut_source = (self.grid_model.active_sheet_name, bounds)
        self.viewport().update()

    def paste_clipboard(self) -> None:
        """Paste at the active cell; a cut moves cells, one cell fills a selection."""
        current = self.currentIndex()
        if not current.isValid():
            return
        if self.cut_source is not None:
            sheet_name, source = self.cut_source
            self.cut_source = None
            try:
                self.grid_model.history.execute(
                    MoveCellsCommand(
                        self.grid_model.engine,
                        sheet_name,
                        source,
                        self.grid_model.active_sheet_name,
                        current.row(),
                        current.column(),
                    )
                )
            except (IndexError, ValueError):
                return
            height, width = source[2] - source[0], source[3] - source[1]
            self.select_block(current.row(), current.column(), current.row() + height, current.column() + width)
            self.grid_model.refresh()
            return
        mime = QApplication.clipboard().mimeData()
        if mime.hasFormat(RICH_CELL_MIME):
            try:
                cells, origin = decode_cell_matrix(bytes(mime.data(RICH_CELL_MIME)))
            except (ValueError, TypeError):
                pass
            else:
                for row, column in self._paste_targets(len(cells), len(cells[0]) if cells else 0):
                    self.grid_model.history.execute(
                        PasteCellsCommand(
                            self.grid_model.engine,
                            self.grid_model.active_sheet_name,
                            row,
                            column,
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

    def _paste_targets(self, height: int, width: int) -> list[tuple[int, int]]:
        """Top-left corners: tile the source over a selection that is a multiple of it."""
        current = self.currentIndex()
        bounds = self.selection_bounds()
        if not height or not width or bounds is None:
            return [(current.row(), current.column())]
        top, left, bottom, right = bounds
        rows, columns = bottom - top + 1, right - left + 1
        if (rows, columns) == (height, width) or rows % height or columns % width:
            return [(current.row(), current.column())]
        if rows * columns > 100_000:
            return [(current.row(), current.column())]
        return [
            (row, column)
            for row in range(top, bottom + 1, height)
            for column in range(left, right + 1, width)
        ]

    def clear_selection_contents(self, *, active_only: bool = False) -> None:
        """Delete key: clear contents (keeping formats) of the selection."""
        if active_only:
            current = self.currentIndex()
            ranges = [(current.row(), current.column(), current.row(), current.column())]
        else:
            ranges = self.selection_ranges()
        if not ranges:
            return
        self.grid_model.history.execute(
            ClearRangesCommand(
                self.grid_model.engine,
                self.grid_model.active_sheet_name,
                tuple(ranges),
                "contents",
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
        """Return the bounding rectangle of the selection (top, left, bottom, right)."""
        ranges = self.selection_ranges()
        if not ranges:
            return None
        return (
            min(item[0] for item in ranges),
            min(item[1] for item in ranges),
            max(item[2] for item in ranges),
            max(item[3] for item in ranges),
        )

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
        self.metadataSynced.emit()

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
        self._paint_note_markers(painter)
        self._paint_error_markers(painter)
        self._paint_cut_marquee(painter)
        self._paint_trace_arrows(painter)
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

    def _paint_note_markers(self, painter: QPainter) -> None:
        """Draw Excel's red triangle for notes and purple triangle for comment threads."""
        self._paint_corner_markers(painter, self.grid_model.sheet.notes, "#c00000")
        self._paint_corner_markers(painter, self.grid_model.sheet.comments, "#7030a0")

    def _paint_corner_markers(self, painter: QPainter, notes: Any, color: str) -> None:
        if not notes:
            return
        viewport = self.viewport().rect()
        top = self.rowAt(0)
        bottom = self.rowAt(viewport.height() - 1)
        left = self.columnAt(0)
        right = self.columnAt(viewport.width() - 1)
        bottom = MAX_ROWS - 1 if bottom < 0 else bottom
        right = MAX_COLUMNS - 1 if right < 0 else right
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        for row, column in notes:
            if not (top <= row <= bottom and left <= column <= right):
                continue
            rect = self.visualRect(self.grid_model.index(row, column))
            if not rect.isValid():
                continue
            from PySide6.QtCore import QPoint
            from PySide6.QtGui import QPolygon

            corner = rect.topRight()
            painter.drawPolygon(
                QPolygon(
                    [
                        QPoint(corner.x() - 6, corner.y()),
                        QPoint(corner.x(), corner.y()),
                        QPoint(corner.x(), corner.y() + 6),
                    ]
                )
            )

    def _visible_bounds(self) -> tuple[int, int, int, int]:
        viewport = self.viewport().rect()
        top = max(0, self.rowAt(0))
        left = max(0, self.columnAt(0))
        bottom = self.rowAt(viewport.height() - 1)
        right = self.columnAt(viewport.width() - 1)
        return (
            top,
            left,
            MAX_ROWS - 1 if bottom < 0 else bottom,
            MAX_COLUMNS - 1 if right < 0 else right,
        )

    def _paint_error_markers(self, painter: QPainter) -> None:
        """Draw the green triangle Excel uses for error-checking findings."""
        if not self.error_checking:
            return
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPolygon

        from duddysheet.core.auditing import error_flags

        sheet = self.grid_model.sheet
        top, left, bottom, right = self._visible_bounds()
        if (bottom - top + 1) * (right - left + 1) > 20_000:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#008000")))
        for row in range(top, bottom + 1):
            for column in range(left, right + 1):
                cell = sheet.get_cell(row, column)
                if cell.is_empty or not error_flags(sheet, row, column):
                    continue
                rect = self.visualRect(self.grid_model.index(row, column))
                corner = rect.topLeft()
                painter.drawPolygon(
                    QPolygon(
                        [
                            QPoint(corner.x(), corner.y()),
                            QPoint(corner.x() + 6, corner.y()),
                            QPoint(corner.x(), corner.y() + 6),
                        ]
                    )
                )

    def _paint_trace_arrows(self, painter: QPainter) -> None:
        """Draw Trace Precedents/Dependents arrows between cell centers."""
        if not self.trace_arrows:
            return
        import math as _math

        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPolygonF

        pen = QPen(QColor("#0000ff"), 1.5)
        painter.setPen(pen)
        for (from_row, from_column), (to_row, to_column) in self.trace_arrows:
            start = self.visualRect(self.grid_model.index(from_row, from_column)).center()
            end = self.visualRect(self.grid_model.index(to_row, to_column)).center()
            painter.setBrush(QBrush(QColor("#0000ff")))
            painter.drawEllipse(start, 3, 3)
            painter.drawLine(start, end)
            angle = _math.atan2(end.y() - start.y(), end.x() - start.x())
            head = QPolygonF(
                [
                    QPointF(end),
                    QPointF(end.x() - 9 * _math.cos(angle - 0.4), end.y() - 9 * _math.sin(angle - 0.4)),
                    QPointF(end.x() - 9 * _math.cos(angle + 0.4), end.y() - 9 * _math.sin(angle + 0.4)),
                ]
            )
            painter.drawPolygon(head)

    def _paint_cut_marquee(self, painter: QPainter) -> None:
        if self.cut_source is None or self.cut_source[0] != self.grid_model.active_sheet_name:
            return
        top, left, bottom, right = self.cut_source[1]
        first = self.visualRect(self.grid_model.index(top, left))
        last = self.visualRect(self.grid_model.index(bottom, right))
        if not first.isValid() and not last.isValid():
            return
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#217346"), 2, Qt.PenStyle.DashLine))
        painter.drawRect(first.united(last).adjusted(1, 1, -1, -1))

    def _open_editor(self) -> Any:
        from PySide6.QtWidgets import QLineEdit

        if self.state() != QAbstractItemView.State.EditingState:
            return None
        editor = self.findChild(QLineEdit, "cellEditor")
        return editor if editor is not None and editor.isVisible() else None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        editor = self._open_editor()
        if editor is not None and event.button() == Qt.MouseButton.LeftButton:
            from duddysheet.ui.delegates import can_point, insert_point_reference

            target = self.indexAt(event.position().toPoint())
            if target.isValid() and target != self.currentIndex() and can_point(editor):
                # Point mode: clicking while typing a formula inserts a reference.
                editor.setProperty("pointAnchor", None)
                insert_point_reference(editor, target.row(), target.column())
                editor.setProperty("pointDragAnchor", (target.row(), target.column()))
                editor.setFocus()
                event.accept()
                return
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
        editor = self._open_editor()
        if editor is not None and editor.property("pointDragAnchor") is not None:
            if event.buttons() & Qt.MouseButton.LeftButton:
                from duddysheet.ui.delegates import insert_point_reference

                target = self.indexAt(event.position().toPoint())
                if target.isValid():
                    insert_point_reference(
                        editor,
                        target.row(),
                        target.column(),
                        anchor=tuple(editor.property("pointDragAnchor")),
                    )
                event.accept()
                return
            editor.setProperty("pointDragAnchor", None)
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
