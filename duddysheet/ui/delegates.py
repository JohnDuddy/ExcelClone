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
        """Let an open suggestion list claim navigation keys before the view."""
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            completer = _completer_for(editor)
            if completer is not None and completer.handle_key(event):
                return True
        return super().eventFilter(editor, event)

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
