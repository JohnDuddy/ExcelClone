"""Name box and editable formula line."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget

_REFERENCE_RE = re.compile(r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]*")


class FormulaBar(QWidget):
    """Current-cell name box and formula editor."""

    commitRequested = Signal()
    gotoRequested = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("formulaBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.name_box = QLineEdit()
        self.name_box.setObjectName("nameBox")
        self.name_box.setFixedWidth(100)
        self.name_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_box.returnPressed.connect(
            lambda: self.gotoRequested.emit(self.name_box.text())
        )

        function_label = QLabel("fx")
        function_label.setObjectName("functionLabel")
        function_label.setStyleSheet("font-weight: 700; font-style: italic;")

        self.editor = QLineEdit()
        self.editor.setObjectName("formulaEditor")
        self.editor.returnPressed.connect(self.commitRequested.emit)
        self.editor.installEventFilter(self)

        layout.addWidget(self.name_box)
        layout.addWidget(function_label)
        layout.addWidget(self.editor, 1)

    def set_cell(self, reference: str, raw_input: Any) -> None:
        """Display a cell reference and its raw input."""
        self.name_box.setText(reference)
        self.editor.setText("" if raw_input is None else str(raw_input))

    def eventFilter(self, watched: Any, event: QEvent) -> bool:
        if (
            watched is self.editor
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_F4
        ):
            updated, position = cycle_absolute_reference(
                self.editor.text(),
                self.editor.cursorPosition(),
            )
            self.editor.setText(updated)
            self.editor.setCursorPosition(position)
            return True
        return super().eventFilter(watched, event)


def cycle_absolute_reference(formula: str, cursor: int) -> tuple[str, int]:
    """Cycle the A1 reference at or immediately before the cursor."""
    selected = None
    for match in _REFERENCE_RE.finditer(formula):
        if match.start() <= cursor <= match.end() or match.end() == cursor:
            selected = match
    if selected is None:
        return formula, cursor
    reference = selected.group(0)
    match = re.fullmatch(r"(\$?)([A-Za-z]{1,3})(\$?)([1-9][0-9]*)", reference)
    if match is None:
        return formula, cursor
    column_absolute, column, row_absolute, row = match.groups()
    state = (bool(column_absolute), bool(row_absolute))
    next_state = {
        (False, False): (True, True),
        (True, True): (False, True),
        (False, True): (True, False),
        (True, False): (False, False),
    }[state]
    replacement = (
        ("$" if next_state[0] else "")
        + column
        + ("$" if next_state[1] else "")
        + row
    )
    updated = formula[: selected.start()] + replacement + formula[selected.end() :]
    new_cursor = selected.start() + len(replacement)
    return updated, new_cursor

