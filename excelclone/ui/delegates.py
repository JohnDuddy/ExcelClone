"""Qt delegates for cell borders and conditional-format visuals."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.ui.grid_model import DATA_BAR_ROLE, EFFECTIVE_FORMAT_ROLE, ICON_ROLE

_PEN_STYLES = {
    "thin": (1, Qt.PenStyle.SolidLine),
    "medium": (2, Qt.PenStyle.SolidLine),
    "dashed": (1, Qt.PenStyle.DashLine),
    "dotted": (1, Qt.PenStyle.DotLine),
    "thick": (3, Qt.PenStyle.SolidLine),
    "double": (3, Qt.PenStyle.SolidLine),
    "hair": (1, Qt.PenStyle.DotLine),
}


class CellDelegate(QStyledItemDelegate):
    """Paint standard Qt cells plus bars, icons, and Excel-like borders."""

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
