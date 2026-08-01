"""Excel-style function name popup for formula editors."""

from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)

from duddysheet.core.completion import (
    ActiveCall,
    active_call_at,
    find_functions,
    function_prefix_at,
)

NAME_ROLE = Qt.ItemDataRole.UserRole
DETAIL_ROLE = Qt.ItemDataRole.UserRole + 1

_MAX_VISIBLE_ROWS = 8
_MIN_WIDTH = 340
_MAX_WIDTH = 520
_COLUMN_GAP = 18
_HORIZONTAL_PADDING = 8
_VERTICAL_PADDING = 4
_TIP_MARGIN = 5


def _row_fonts(base: QFont) -> tuple[QFont, QFont]:
    """Return the bold name font and the plain signature font for a row."""
    name_font = QFont(base)
    name_font.setBold(True)
    detail_font = QFont(base)
    detail_font.setBold(False)
    return name_font, detail_font


class _CompletionRowDelegate(QStyledItemDelegate):
    """Paint a completion row as a bold name beside a dimmed signature."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.name_column_width = 0

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> None:
        name = str(index.data(NAME_ROLE) or "")
        detail = str(index.data(DETAIL_ROLE) or "")
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.save()
        if selected:
            painter.fillRect(option.rect, option.palette.highlight())
            name_color = option.palette.highlightedText().color()
            detail_color = QColor(name_color)
            detail_color.setAlpha(200)
        else:
            name_color = option.palette.text().color()
            detail_color = QColor(name_color)
            detail_color.setAlpha(140)

        name_font, detail_font = _row_fonts(option.font)
        body = option.rect.adjusted(_HORIZONTAL_PADDING, 0, -_HORIZONTAL_PADDING, 0)
        alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        painter.setFont(name_font)
        painter.setPen(name_color)
        painter.drawText(body, alignment, name)

        detail_rect = QRect(body)
        detail_rect.setLeft(
            body.left()
            + max(
                self.name_column_width,
                QFontMetrics(name_font).horizontalAdvance(name),
            )
            + _COLUMN_GAP
        )
        if detail and detail_rect.width() > 0:
            painter.setFont(detail_font)
            painter.setPen(detail_color)
            painter.drawText(
                detail_rect,
                alignment,
                QFontMetrics(detail_font).elidedText(
                    detail,
                    Qt.TextElideMode.ElideRight,
                    detail_rect.width(),
                ),
            )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
        name_font, detail_font = _row_fonts(option.font)
        name_metrics = QFontMetrics(name_font)
        detail_metrics = QFontMetrics(detail_font)
        width = (
            max(
                self.name_column_width,
                name_metrics.horizontalAdvance(str(index.data(NAME_ROLE) or "")),
            )
            + _COLUMN_GAP
            + detail_metrics.horizontalAdvance(str(index.data(DETAIL_ROLE) or ""))
            + 2 * _HORIZONTAL_PADDING
        )
        height = max(name_metrics.height(), detail_metrics.height())
        return QSize(width, height + 2 * _VERTICAL_PADDING)


class FunctionCompleter(QObject):
    """Suggest registered function names while a formula is being typed."""

    def __init__(self, editor: QLineEdit, parent: Any = None) -> None:
        super().__init__(parent if parent is not None else editor)
        self._editor = editor
        self._prefix_start = 0
        self._prefix_end = 0
        self._accepting = False
        self._call: ActiveCall | None = None
        self._popup = QListWidget(editor)
        self._popup.setObjectName("functionCompleterPopup")
        self._popup.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setUniformItemSizes(True)
        self._popup.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._popup.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._row_delegate = _CompletionRowDelegate(self._popup)
        self._popup.setItemDelegate(self._row_delegate)
        self._popup.itemClicked.connect(lambda _item: self.accept_current())
        self._popup.hide()

        self._tip = QLabel(editor)
        self._tip.setObjectName("functionArgumentTip")
        self._tip.setWindowFlags(
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint
        )
        self._tip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tip.setTextFormat(Qt.TextFormat.RichText)
        self._tip.setMargin(_TIP_MARGIN)
        self._tip.setStyleSheet(
            "QLabel#functionArgumentTip {"
            " background: palette(tool-tip-base);"
            " color: palette(tool-tip-text);"
            " border: 1px solid palette(mid);"
            "}"
        )
        self._tip.hide()

        editor.textEdited.connect(lambda _text: self.refresh())
        editor.cursorPositionChanged.connect(lambda _old, _new: self.refresh())
        editor.installEventFilter(self)

    @property
    def popup(self) -> QListWidget:
        """Return the suggestion list widget."""
        return self._popup

    def is_active(self) -> bool:
        """Report whether suggestions are currently displayed."""
        return self._popup.isVisible()

    def suggestions(self) -> tuple[str, ...]:
        """Return the currently listed function names."""
        return tuple(
            str(self._popup.item(row).data(NAME_ROLE))
            for row in range(self._popup.count())
        )

    def is_tip_active(self) -> bool:
        """Report whether the argument guide is currently displayed."""
        return self._tip.isVisible()

    def argument_tip(self) -> str | None:
        """Return the displayed call signature, or None when no guide is shown."""
        if self._call is None:
            return None
        return f"{self._call.name}({', '.join(self._call.fields)})"

    def active_argument(self) -> str | None:
        """Return the argument field the caret currently sits in."""
        if self._call is None:
            return None
        return self._call.fields[self._call.active_field]

    def refresh(self) -> None:
        """Update the suggestion list or the argument guide for the caret."""
        if self._accepting:
            return
        text = self._editor.text()
        cursor = self._editor.cursorPosition()
        if self._refresh_suggestions(text, cursor):
            self._hide_tip()
            return
        self.hide_popup()
        self._refresh_tip(text, cursor)

    def dismiss(self) -> None:
        """Hide both the suggestion list and the argument guide."""
        self.hide_popup()
        self._hide_tip()

    def _refresh_tip(self, text: str, cursor: int) -> None:
        call = active_call_at(text, cursor)
        if call is None or not call.fields:
            self._hide_tip()
            return
        self._call = call
        self._tip.setText(_argument_markup(call))
        self._tip.adjustSize()
        size = self._tip.size()
        self._tip.move(self._popup_origin(size.width(), size.height()))
        self._tip.show()
        self._tip.raise_()

    def _hide_tip(self) -> None:
        self._call = None
        self._tip.hide()

    def _refresh_suggestions(self, text: str, cursor: int) -> bool:
        prefix = function_prefix_at(text, cursor)
        if prefix is None or not prefix.text:
            self.hide_popup()
            return False
        matches = find_functions(prefix.text)
        if not matches:
            self.hide_popup()
            return False
        self._prefix_start = prefix.start
        self._prefix_end = prefix.end
        name_font, _ = _row_fonts(self._popup.font())
        self._row_delegate.name_column_width = max(
            QFontMetrics(name_font).horizontalAdvance(spec.name) for spec in matches
        )
        self._popup.clear()
        for spec in matches:
            item = QListWidgetItem()
            item.setData(NAME_ROLE, spec.name)
            item.setData(DETAIL_ROLE, _detail_text(spec))
            item.setText(spec.name)
            self._popup.addItem(item)
        self._popup.setCurrentRow(0)
        self._show_popup()
        return True

    def hide_popup(self) -> None:
        """Dismiss the suggestion list."""
        self._popup.hide()

    def accept_current(self) -> None:
        """Replace the typed prefix with the highlighted function name."""
        item = self._popup.currentItem()
        if item is None:
            self.hide_popup()
            return
        name = str(item.data(NAME_ROLE))
        text = self._editor.text()
        start = min(self._prefix_start, len(text))
        end = min(self._prefix_end, len(text))
        # The completed name is itself a valid prefix, so suppress the refresh
        # these edits trigger or the list would reopen on the word just chosen.
        # The argument guide appears once the caller types the opening paren.
        self._accepting = True
        try:
            self._editor.setText(text[:start] + name + text[end:])
            self._editor.setCursorPosition(start + len(name))
        finally:
            self._accepting = False
        self.hide_popup()

    def handle_key(self, event: QKeyEvent) -> bool:
        """Consume a navigation or acceptance key while suggestions are shown."""
        if not self.is_active():
            return False
        key = event.key()
        if key in (Qt.Key.Key_Escape,):
            self.dismiss()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
            self.accept_current()
            return True
        step = {
            Qt.Key.Key_Up: -1,
            Qt.Key.Key_Down: 1,
            Qt.Key.Key_PageUp: -_MAX_VISIBLE_ROWS,
            Qt.Key.Key_PageDown: _MAX_VISIBLE_ROWS,
        }.get(key)
        if step is None:
            return False
        count = self._popup.count()
        if count:
            row = max(0, min(count - 1, self._popup.currentRow() + step))
            self._popup.setCurrentRow(row)
        return True

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        """Dismiss suggestions when the editor stops being usable."""
        if watched is self._editor and event.type() in (
            QEvent.Type.FocusOut,
            QEvent.Type.Hide,
        ):
            self.dismiss()
        return super().eventFilter(watched, event)

    def _show_popup(self) -> None:
        width = self._popup.sizeHintForColumn(0)
        frame = 2 * self._popup.frameWidth()
        visible_rows = min(_MAX_VISIBLE_ROWS, self._popup.count())
        row_height = self._popup.sizeHintForRow(0)
        if visible_rows < self._popup.count():
            width += self._popup.verticalScrollBar().sizeHint().width()
        width = max(_MIN_WIDTH, min(_MAX_WIDTH, width + frame))
        height = row_height * visible_rows + frame
        self._popup.resize(width, height)
        self._popup.move(self._popup_origin(width, height))
        self._popup.show()
        self._popup.raise_()

    def _popup_origin(self, width: int, height: int) -> QPoint:
        below = self._editor.mapToGlobal(self._editor.rect().bottomLeft())
        origin = QPoint(below.x(), below.y() + 1)
        screen = QApplication.screenAt(below)
        if screen is None:
            return origin
        available = screen.availableGeometry()
        if origin.y() + height > available.bottom():
            above = self._editor.mapToGlobal(self._editor.rect().topLeft())
            origin.setY(above.y() - height - 1)
        origin.setX(max(available.left(), min(origin.x(), available.right() - width)))
        return origin


def _detail_text(spec: Any) -> str:
    """Return the signature and description shown beside a function name."""
    arguments = spec.argument_spec or "no arguments"
    return f"({arguments})  {spec.description}"


def _argument_markup(call: ActiveCall) -> str:
    """Render a call signature with the argument being typed emphasized."""
    active = call.active_field
    fields = [
        f"<b><u>{escape(field)}</u></b>" if position == active else escape(field)
        for position, field in enumerate(call.fields)
    ]
    return f"{escape(call.name)}(" + ", ".join(fields) + ")"
