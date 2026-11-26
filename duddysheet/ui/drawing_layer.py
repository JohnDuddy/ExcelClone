"""Floating pictures, shapes, and text boxes drawn over the grid."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

from duddysheet.core.drawings import Drawing

HANDLE = 8


def shape_path(shape: str, rect: QRectF) -> QPainterPath:
    """Return the outline of one of Excel's preset shapes inside ``rect``."""
    path = QPainterPath()
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if shape == "roundRect":
        radius = min(w, h) * 0.16
        path.addRoundedRect(rect, radius, radius)
    elif shape == "ellipse":
        path.addEllipse(rect)
    elif shape == "triangle":
        path.addPolygon(QPolygonF([QPointF(x + w / 2, y), QPointF(x + w, y + h), QPointF(x, y + h), QPointF(x + w / 2, y)]))
    elif shape == "rightArrow":
        shaft_top, shaft_bottom, head = y + h * 0.25, y + h * 0.75, x + w * 0.6
        path.addPolygon(
            QPolygonF(
                [
                    QPointF(x, shaft_top),
                    QPointF(head, shaft_top),
                    QPointF(head, y),
                    QPointF(x + w, y + h / 2),
                    QPointF(head, y + h),
                    QPointF(head, shaft_bottom),
                    QPointF(x, shaft_bottom),
                    QPointF(x, shaft_top),
                ]
            )
        )
    elif shape == "star5":
        points = []
        for index in range(10):
            angle = -math.pi / 2 + index * math.pi / 5
            scale = 1.0 if index % 2 == 0 else 0.4
            points.append(QPointF(x + w / 2 + math.cos(angle) * w / 2 * scale, y + h / 2 + math.sin(angle) * h / 2 * scale))
        points.append(points[0])
        path.addPolygon(QPolygonF(points))
    elif shape == "wedgeRectCallout":
        body = QRectF(x, y, w, h * 0.78)
        path.addRect(body)
        tail = QPolygonF([QPointF(x + w * 0.2, body.bottom()), QPointF(x + w * 0.12, y + h), QPointF(x + w * 0.38, body.bottom())])
        path.addPolygon(tail)
        path = path.simplified()
    elif shape == "line":
        path.moveTo(x, y)
        path.lineTo(x + w, y + h)
    else:
        path.addRect(rect)
    return path


class DrawingItem(QWidget):
    """One drawing on the grid's viewport: select, drag to move, drag the corner to resize."""

    def __init__(self, layer: DrawingLayer, drawing: Drawing) -> None:
        super().__init__(layer.grid.viewport())
        self.layer = layer
        self.drawing = drawing
        self.selected = False
        self._pixmap: QPixmap | None = None
        self._press: QPoint | None = None
        self._start = QRect()
        self._resizing = False
        self.setObjectName(f"drawing-{drawing.name}")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setToolTip(drawing.description or drawing.name)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_drawing(self, drawing: Drawing) -> None:
        if drawing.image != self.drawing.image:
            self._pixmap = None
        self.drawing = drawing
        self.setToolTip(drawing.description or drawing.name)
        self.update()

    def pixmap(self) -> QPixmap:
        if self._pixmap is None:
            self._pixmap = QPixmap()
            self._pixmap.loadFromData(self.drawing.image)
        return self._pixmap

    # -- painting ---------------------------------------------------------
    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        drawing = self.drawing
        if drawing.kind == "picture":
            painter.drawPixmap(area.toRect(), self.pixmap())
        else:
            path = shape_path("rect" if drawing.kind == "textbox" else drawing.shape, area)
            pen = QPen(QColor(drawing.line)) if drawing.line else QPen(Qt.PenStyle.NoPen)
            if drawing.shape == "line" and drawing.kind == "shape":
                pen = QPen(QColor(drawing.line or drawing.fill), 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(drawing.fill)) if drawing.fill and drawing.shape != "line" else Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            if drawing.text:
                font = QFont(self.font())
                font.setPointSizeF(drawing.font_size * self.layer.scale())
                painter.setFont(font)
                painter.setPen(QColor(drawing.font_color))
                flags = (
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                    if drawing.kind == "textbox"
                    else Qt.AlignmentFlag.AlignCenter
                ) | Qt.TextFlag.TextWordWrap
                painter.drawText(area.adjusted(6, 4, -6, -4), int(flags), drawing.text)
        if self.selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#2f6fb0"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.setPen(QPen(QColor("#2f6fb0")))
            painter.setBrush(QColor("white"))
            painter.drawRect(self._handle())
        painter.end()

    def _handle(self) -> QRect:
        return QRect(self.width() - HANDLE - 1, self.height() - HANDLE - 1, HANDLE, HANDLE)

    # -- interaction ------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.layer.select(self.drawing.name)
        self.setFocus()
        self._press = event.globalPosition().toPoint()
        self._start = self.geometry()
        self._resizing = self._handle().adjusted(-3, -3, 3, 3).contains(event.position().toPoint())
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press is None:
            return
        delta = event.globalPosition().toPoint() - self._press
        if self._resizing:
            self.resize(max(8, self._start.width() + delta.x()), max(8, self._start.height() + delta.y()))
        else:
            self.move(self._start.topLeft() + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._press is not None and self.geometry() != self._start:
            self.layer.commit_geometry(self)
        self._press = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.drawing.kind != "picture":
            self.layer.textEditRequested.emit(self.drawing.name)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.layer.drawingDeleted.emit(self.drawing.name)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.layer.select(None)
            self.layer.grid.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)


class DrawingLayer(QObject):
    """Keeps one ``DrawingItem`` per drawing on the active sheet, positioned over its cell."""

    drawingChanged = Signal(str, object)
    drawingDeleted = Signal(str)
    textEditRequested = Signal(str)

    def __init__(self, grid: Any) -> None:
        super().__init__(grid)
        self.grid = grid
        self.items: dict[str, DrawingItem] = {}
        self.selected: str | None = None
        grid.metadataSynced.connect(self.sync)
        grid.verticalScrollBar().valueChanged.connect(lambda *_: self.reposition())
        grid.horizontalScrollBar().valueChanged.connect(lambda *_: self.reposition())
        grid.verticalHeader().sectionResized.connect(lambda *_: self.reposition())
        grid.horizontalHeader().sectionResized.connect(lambda *_: self.reposition())

    def scale(self) -> float:
        return getattr(self.grid, "zoom_percent", 100) / 100

    def sync(self) -> None:
        """Match the items to the active sheet's drawings."""
        drawings = {drawing.name: drawing for drawing in self.grid.grid_model.sheet.drawings}
        for name in tuple(self.items):
            if name not in drawings:
                item = self.items.pop(name)
                item.hide()
                item.setParent(None)
                item.deleteLater()
        for name, drawing in drawings.items():
            item = self.items.get(name)
            if item is None:
                item = DrawingItem(self, drawing)
                self.items[name] = item
            else:
                item.set_drawing(drawing)
            item.selected = name == self.selected
        if self.selected not in drawings:
            self.selected = None
        self.reposition()

    def reposition(self) -> None:
        scale = self.scale()
        for item in self.items.values():
            drawing = item.drawing
            x = self.grid.columnViewportPosition(drawing.column) + drawing.column_offset * scale
            y = self.grid.rowViewportPosition(drawing.row) + drawing.row_offset * scale
            item.setGeometry(int(round(x)), int(round(y)), max(2, int(round(drawing.width * scale))), max(2, int(round(drawing.height * scale))))
            item.show()
            item.raise_()

    def select(self, name: str | None) -> None:
        self.selected = name
        for item_name, item in self.items.items():
            item.selected = item_name == name
            item.update()

    def anchor_at(self, point: QPoint) -> tuple[int, float, int, float]:
        """Return (row, row offset, column, column offset) for a viewport point."""
        scale = self.scale()
        row = max(0, self.grid.rowAt(max(0, point.y())))
        column = max(0, self.grid.columnAt(max(0, point.x())))
        row_offset = (point.y() - self.grid.rowViewportPosition(row)) / scale
        column_offset = (point.x() - self.grid.columnViewportPosition(column)) / scale
        return row, max(0.0, row_offset), column, max(0.0, column_offset)

    def commit_geometry(self, item: DrawingItem) -> None:
        row, row_offset, column, column_offset = self.anchor_at(item.geometry().topLeft())
        scale = self.scale()
        moved = replace(
            item.drawing,
            row=row,
            column=column,
            row_offset=round(row_offset, 2),
            column_offset=round(column_offset, 2),
            width=round(item.width() / scale, 2),
            height=round(item.height() / scale, 2),
        )
        self.drawingChanged.emit(item.drawing.name, moved)
