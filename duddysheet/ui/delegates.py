"""Qt delegates for cell borders and conditional-format visuals."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.ui.completer import FunctionCompleter
from duddysheet.core.sparkline import Sparkline
from duddysheet.ui.grid_model import (
    DATA_BAR_ROLE,
    EFFECTIVE_FORMAT_ROLE,
    ICON_ROLE,
    SPARKLINE_ROLE,
)

_PEN_STYLES = {
    "thin": (1, Qt.PenStyle.SolidLine),
    "medium": (2, Qt.PenStyle.SolidLine),
    "dashed": (1, Qt.PenStyle.DashLine),
    "dotted": (1, Qt.PenStyle.DotLine),
    "thick": (3, Qt.PenStyle.SolidLine),
    "double": (3, Qt.PenStyle.SolidLine),
    "hair": (1, Qt.PenStyle.DotLine),
}


_POINT_TRIGGERS = set("=(,+-*/^&<>:; ")


def clear_point(editor: Any) -> None:
    """Forget any in-progress point-mode reference."""
    editor.setProperty("pointSpan", None)
    editor.setProperty("pointCell", None)
    editor.setProperty("pointAnchor", None)


def can_point(editor: Any) -> bool:
    """Return whether the formula is waiting for a reference at the cursor."""
    text = editor.text()
    if not text.startswith("="):
        return False
    if editor.property("pointSpan") is not None:
        return True
    position = editor.cursorPosition()
    return position > 0 and text[position - 1] in _POINT_TRIGGERS


def insert_point_reference(
    editor: Any,
    row: int,
    column: int,
    *,
    anchor: tuple[int, int] | None = None,
) -> None:
    """Insert or replace the point-mode reference with a cell or range."""
    from duddysheet.core.refs import CellReference, RangeReference

    text = editor.text()
    span = editor.property("pointSpan")
    if span is None:
        start = end = editor.cursorPosition()
    else:
        start, end = span
    if anchor is not None and anchor != (row, column):
        top, bottom = sorted((anchor[0], row))
        left, right = sorted((anchor[1], column))
        reference = RangeReference(CellReference(top, left), CellReference(bottom, right)).to_a1()
    else:
        reference = CellReference(row, column).to_a1(include_sheet=False)
    editor.setText(text[:start] + reference + text[end:])
    editor.setCursorPosition(start + len(reference))
    editor.setProperty("pointSpan", (start, start + len(reference)))
    editor.setProperty("pointCell", (row, column))


def point_reference(
    editor: Any,
    view: Any,
    d_row: int,
    d_column: int,
    *,
    extend: bool,
    to_edge: bool,
) -> bool:
    """Excel point mode: arrow keys while typing a formula insert a reference."""
    if not can_point(editor):
        return False
    current = view.currentIndex()
    base = editor.property("pointCell") or (current.row(), current.column())
    anchor = editor.property("pointAnchor")
    if extend and anchor is None:
        anchor = tuple(base)
        editor.setProperty("pointAnchor", anchor)
    if not extend:
        editor.setProperty("pointAnchor", None)
        anchor = None
    if to_edge:
        from duddysheet.core.navigation import data_edge

        row, column = data_edge(view.grid_model.sheet, base[0], base[1], d_row, d_column)
    else:
        row = max(0, base[0] + d_row)
        column = max(0, base[1] + d_column)
    insert_point_reference(editor, row, column, anchor=anchor)
    view.scrollTo(view.grid_model.index(row, column))
    return True


def _completer_for(editor: Any) -> FunctionCompleter | None:
    """Return the suggestion controller owned by a cell editor, if present."""
    if not isinstance(editor, QLineEdit):
        return None
    return editor.findChild(FunctionCompleter)


class CellDelegate(QStyledItemDelegate):
    """Paint standard Qt cells plus bars, icons, and Excel-like borders."""

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> QWidget:
        """Return a line editor that suggests function names while typing."""
        del option, index
        editor = QLineEdit(parent)
        editor.setObjectName("cellEditor")
        FunctionCompleter(editor, editor)
        return editor

    def eventFilter(self, editor: Any, event: QEvent) -> bool:
        """Excel editing keys: suggestions first, then point mode, then commit-and-move."""
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            completer = _completer_for(editor)
            if completer is not None and completer.handle_key(event):
                return True
            if isinstance(editor, QLineEdit) and self._handle_excel_key(editor, event):
                return True
        return super().eventFilter(editor, event)

    _MOVES = {
        Qt.Key.Key_Up: (-1, 0),
        Qt.Key.Key_Down: (1, 0),
        Qt.Key.Key_Left: (0, -1),
        Qt.Key.Key_Right: (0, 1),
    }

    def _view(self) -> Any:
        view = self.parent()
        return view if hasattr(view, "move_after_edit") else None

    def _commit_and_move(self, editor: QLineEdit, d_row: int, d_column: int) -> None:
        view = self._view()
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)
        if view is not None:
            view.move_after_edit(d_row, d_column)

    def _handle_excel_key(self, editor: QLineEdit, event: QKeyEvent) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not alt and not control:
            self._commit_and_move(editor, -1 if shift else 1, 0)
            return True
        if key == Qt.Key.Key_Tab:
            self._commit_and_move(editor, 0, 1)
            return True
        if key == Qt.Key.Key_Backtab:
            self._commit_and_move(editor, 0, -1)
            return True
        view = self._view()
        if key in self._MOVES and not alt and view is not None and view.edit_mode == "enter":
            d_row, d_column = self._MOVES[key]
            if point_reference(editor, view, d_row, d_column, extend=shift, to_edge=control):
                return True
            self._commit_and_move(editor, d_row, d_column)
            return True
        if event.text():
            clear_point(editor)
        return False

    def destroyEditor(self, editor: QWidget, index: Any) -> None:
        """Dismiss any open guidance before the editor is torn down."""
        completer = _completer_for(editor)
        if completer is not None:
            completer.dismiss()
        super().destroyEditor(editor, index)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> None:
        data_bar = index.data(DATA_BAR_ROLE)
        icon = index.data(ICON_ROLE)
        cell_format = index.data(EFFECTIVE_FORMAT_ROLE)

        if isinstance(data_bar, (int, float)):
            painter.save()
            width = max(0.0, min(1.0, float(data_bar))) * option.rect.width()
            bar = QRectF(option.rect)
            bar.setWidth(width)
            bar.adjust(1, 3, -1, -3)
            painter.fillRect(bar, QColor(91, 155, 213, 90))
            painter.restore()

        painted_option = QStyleOptionViewItem(option)
        if icon:
            painted_option.rect.adjust(16, 0, 0, 0)
        super().paint(painter, painted_option, index)

        if icon:
            self._paint_icon(painter, option.rect, str(icon))
        sparkline = index.data(SPARKLINE_ROLE)
        if sparkline is not None:
            paint_sparkline(painter, QRectF(option.rect), *sparkline)
        if isinstance(cell_format, CellFormat):
            self._paint_borders(painter, option.rect, cell_format)

    @staticmethod
    def _paint_icon(painter: QPainter, rect: Any, icon: str) -> None:
        painter.save()
        colors = {
            "up": QColor("#2e7d32"),
            "sideways": QColor("#d89b00"),
            "down": QColor("#c62828"),
        }
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.get(icon, QColor("#666666")))
        center_x = rect.left() + 9
        center_y = rect.center().y()
        if icon == "up":
            points = [
                QPointF(center_x, center_y - 5),
                QPointF(center_x - 5, center_y + 4),
                QPointF(center_x + 5, center_y + 4),
            ]
        elif icon == "down":
            points = [
                QPointF(center_x, center_y + 5),
                QPointF(center_x - 5, center_y - 4),
                QPointF(center_x + 5, center_y - 4),
            ]
        else:
            points = [
                QPointF(center_x + 5, center_y),
                QPointF(center_x - 4, center_y - 5),
                QPointF(center_x - 4, center_y + 5),
            ]
        painter.drawPolygon(QPolygonF(points))
        painter.restore()

    def _paint_borders(
        self,
        painter: QPainter,
        rect: Any,
        cell_format: CellFormat,
    ) -> None:
        edges = (
            (cell_format.left_border, rect.topLeft(), rect.bottomLeft()),
            (cell_format.right_border, rect.topRight(), rect.bottomRight()),
            (cell_format.top_border, rect.topLeft(), rect.topRight()),
            (cell_format.bottom_border, rect.bottomLeft(), rect.bottomRight()),
        )
        painter.save()
        for border, start, end in edges:
            if border.style == "none":
                continue
            width, style = _PEN_STYLES.get(
                border.style,
                _PEN_STYLES["thin"],
            )
            painter.setPen(QPen(QColor(border.color), width, style))
            painter.drawLine(start, end)
            if border.style == "double":
                offset = 2 if start.y() == end.y() else -2
                if start.y() == end.y():
                    painter.drawLine(start.x(), start.y() - offset, end.x(), end.y() - offset)
                else:
                    painter.drawLine(start.x() - offset, start.y(), end.x() - offset, end.y())
        painter.restore()


def paint_sparkline(
    painter: QPainter,
    rect: QRectF,
    sparkline: Sparkline,
    values: tuple[float, ...],
) -> None:
    """Draw a line, column, or win/loss sparkline inside a cell rectangle."""
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return
    area = rect.adjusted(3, 3, -3, -3)
    if area.width() <= 2 or area.height() <= 2:
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    count = len(values)
    color = QColor(sparkline.color)
    negative = QColor(sparkline.negative_color)
    marker = QColor(sparkline.marker_color)
    highest, lowest = max(finite), min(finite)
    first_index = next(i for i, v in enumerate(values) if math.isfinite(v))
    last_index = max(i for i, v in enumerate(values) if math.isfinite(v))

    def highlighted(position: int, value: float) -> bool:
        return (
            (sparkline.show_high and value == highest)
            or (sparkline.show_low and value == lowest)
            or (sparkline.show_first and position == first_index)
            or (sparkline.show_last and position == last_index)
            or (sparkline.show_negative and value < 0)
        )

    if sparkline.kind == "win_loss":
        slot = area.width() / count
        middle = area.center().y()
        for position, value in enumerate(values):
            if not math.isfinite(value) or value == 0:
                continue
            height = area.height() / 2 - 1
            top = middle - height if value > 0 else middle + 1
            bar = QRectF(area.left() + position * slot + slot * 0.15, top, slot * 0.7, height)
            fill = negative if value < 0 else color
            if highlighted(position, value) and value > 0:
                fill = marker
            painter.fillRect(bar, fill)
    else:
        low = min(0.0, lowest) if sparkline.kind == "column" else lowest
        high = max(0.0, highest) if sparkline.kind == "column" else highest
        span = (high - low) or 1.0

        def y_of(value: float) -> float:
            return area.bottom() - (value - low) / span * area.height()

        if sparkline.show_axis and low < 0 < high:
            painter.setPen(QPen(QColor("#8c8c8c"), 1))
            painter.drawLine(QPointF(area.left(), y_of(0)), QPointF(area.right(), y_of(0)))
        if sparkline.kind == "column":
            slot = area.width() / count
            base = y_of(max(low, 0.0)) if low < 0 else area.bottom()
            for position, value in enumerate(values):
                if not math.isfinite(value):
                    continue
                top = y_of(value)
                bar = QRectF(
                    area.left() + position * slot + slot * 0.15,
                    min(top, base),
                    slot * 0.7,
                    max(1.0, abs(base - top)),
                )
                fill = negative if value < 0 else color
                if highlighted(position, value):
                    fill = marker if value >= 0 else negative
                painter.fillRect(bar, fill)
        else:
            step = area.width() / max(1, count - 1)
            points = [
                QPointF(area.left() + position * step, y_of(value))
                for position, value in enumerate(values)
                if math.isfinite(value)
            ]
            painter.setPen(QPen(color, 1.5))
            if len(points) > 1:
                painter.drawPolyline(QPolygonF(points))
            painter.setPen(Qt.PenStyle.NoPen)
            for position, value in enumerate(values):
                if not math.isfinite(value):
                    continue
                if sparkline.show_markers or highlighted(position, value):
                    point = QPointF(area.left() + position * step, y_of(value))
                    painter.setBrush(
                        negative
                        if value < 0 and sparkline.show_negative
                        else (marker if highlighted(position, value) else color)
                    )
                    painter.drawEllipse(point, 2.2, 2.2)
    painter.restore()
