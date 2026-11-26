"""Excel's outline bar: level buttons and +/- boxes beside grouped rows and columns."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QGridLayout, QWidget

from duddysheet.core.outline import OutlineGroup, is_collapsed, max_level, outline_groups

STEP = 16
BOX = 11


class OutlineGutter(QWidget):
    """The outline strip for one axis: one track per level, and level buttons."""

    groupToggled = Signal(str, int, tuple, bool)
    levelRequested = Signal(str, int)

    def __init__(self, grid: Any, axis: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = grid
        self.axis = axis
        self.setObjectName(f"{axis}OutlineGutter")
        self._targets: list[tuple[QRect, OutlineGroup | int]] = []

    # -- geometry ---------------------------------------------------------
    def levels(self) -> dict[int, int]:
        sheet = self.grid.grid_model.sheet
        return sheet.row_outline if self.axis == "row" else sheet.column_outline

    def hidden(self) -> set[int]:
        sheet = self.grid.grid_model.sheet
        return sheet.hidden_rows if self.axis == "row" else sheet.hidden_columns

    def depth(self) -> int:
        """Return the number of tracks (deepest level + 1), or 0 when there is no outline."""
        deepest = max_level(self.levels())
        return deepest + 1 if deepest else 0

    def extent(self) -> int:
        return self.depth() * STEP + (4 if self.depth() else 0)

    def _offset(self) -> int:
        """Where the grid's first cell starts, measured in this gutter's coordinates."""
        viewport = self.grid.viewport()
        origin = viewport.mapTo(self.window(), QPoint(0, 0))
        own = self.mapTo(self.window(), QPoint(0, 0))
        return origin.y() - own.y() if self.axis == "row" else origin.x() - own.x()

    def _span(self, index: int) -> tuple[int, int] | None:
        if self.axis == "row":
            if self.grid.isRowHidden(index):
                return None
            start, size = self.grid.rowViewportPosition(index), self.grid.rowHeight(index)
        else:
            if self.grid.isColumnHidden(index):
                return None
            start, size = self.grid.columnViewportPosition(index), self.grid.columnWidth(index)
        if start < 0 and size <= 0:
            return None
        return start + self._offset(), size

    # -- painting ---------------------------------------------------------
    def paintEvent(self, _event: QPaintEvent) -> None:
        self._targets = []
        depth = self.depth()
        if not depth:
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f3f3f3"))
        line = QPen(QColor("#6b6b6b"))
        painter.setPen(line)
        # Level buttons 1..depth sit in the header band, as in Excel.
        header = self._offset()
        for level in range(1, depth + 1):
            box = self._box(level - 1, max(2, header - BOX - 4))
            self._draw_box(painter, box, str(level))
            self._targets.append((box, level))
        hidden = self.hidden()
        limit = self.height() if self.axis == "row" else self.width()
        for group in outline_groups(self.levels()):
            summary = self._span(group.summary)
            spans = [span for span in (self._span(index) for index in group.indexes) if span is not None]
            track = (group.level - 1) * STEP + STEP // 2 + 2
            if spans:
                first = spans[0][0]
                last = spans[-1][0] + spans[-1][1]
                if last > header and first < limit:
                    self._line(painter, track, max(first, header), min(last, limit))
                    self._line_cap(painter, track, max(first, header))
            if summary is not None and header <= summary[0] < limit:
                box = self._box(group.level - 1, summary[0] + (summary[1] - BOX) // 2)
                self._draw_box(painter, box, "+" if is_collapsed(group, hidden) else "-")
                self._targets.append((box, group))
        painter.end()

    def _box(self, track: int, position: int) -> QRect:
        across = track * STEP + (STEP - BOX) // 2 + 2
        if self.axis == "row":
            return QRect(across, position, BOX, BOX)
        return QRect(position, across, BOX, BOX)

    def _draw_box(self, painter: QPainter, box: QRect, label: str) -> None:
        painter.fillRect(box, QColor("white"))
        painter.drawRect(box)
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), label)

    def _line(self, painter: QPainter, track: int, start: int, end: int) -> None:
        if self.axis == "row":
            painter.drawLine(track, start, track, end)
        else:
            painter.drawLine(start, track, end, track)

    def _line_cap(self, painter: QPainter, track: int, start: int) -> None:
        if self.axis == "row":
            painter.drawLine(track, start, track + 4, start)
        else:
            painter.drawLine(start, track, start, track + 4)

    # -- clicks -----------------------------------------------------------
    def target_at(self, point: QPoint) -> OutlineGroup | int | None:
        """Return the group or level button under ``point``."""
        for box, target in self._targets:
            if box.adjusted(-2, -2, 2, 2).contains(point):
                return target
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        target = self.target_at(event.position().toPoint())
        if isinstance(target, OutlineGroup):
            collapsed = is_collapsed(target, self.hidden())
            self.groupToggled.emit(self.axis, target.level, target.indexes, collapsed)
        elif isinstance(target, int):
            self.levelRequested.emit(self.axis, target)
        else:
            super().mousePressEvent(event)

    def refresh(self) -> None:
        extent = self.extent()
        if self.axis == "row":
            self.setFixedWidth(extent)
        else:
            self.setFixedHeight(extent)
        self.setVisible(bool(extent))
        self.update()


class OutlineFrame(QWidget):
    """Hosts the grid with an outline bar above (columns) and left of it (rows)."""

    def __init__(self, grid: Any, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.grid = grid
        self.rows = OutlineGutter(grid, "row", self)
        self.columns = OutlineGutter(grid, "column", self)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.columns, 0, 1)
        layout.addWidget(self.rows, 1, 0)
        layout.addWidget(content, 1, 1)
        for gutter in (self.rows, self.columns):
            gutter.refresh()
        grid.metadataSynced.connect(self.refresh)
        grid.verticalScrollBar().valueChanged.connect(self.rows.update)
        grid.horizontalScrollBar().valueChanged.connect(self.columns.update)
        grid.verticalHeader().sectionResized.connect(lambda *_: self.rows.update())
        grid.horizontalHeader().sectionResized.connect(lambda *_: self.columns.update())

    def refresh(self) -> None:
        """Resize and repaint both bars after the sheet's outline or hidden rows change."""
        self.rows.refresh()
        self.columns.refresh()
