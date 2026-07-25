"""Compact tabbed spreadsheet ribbon."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QToolButton, QWidget


class Ribbon(QTabWidget):
    """Tabbed command surface with deliberately small action groups."""

    actionRequested = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setDocumentMode(True)
        self.setMaximumHeight(104)
        definitions = {
            "Home": (
                "Undo",
                "Redo",
                "Copy",
                "Paste",
                "Paste Special",
                "Bold",
                "Italic",
                "Underline",
                "Font Color",
                "Fill",
                "Wrap",
                "Merge",
                "Row Height",
                "Column Width",
                "Autofit",
                "Find",
                "Format Cells",
            ),
            "Insert": ("Chart", "Rows", "Columns"),
            "Data": (
                "Sort",
                "Filter",
                "Clear Filter",
                "Validate",
                "Remove Duplicates",
                "Text to Columns",
            ),
            "Formulas": ("Insert Function", "Recalculate", "Sheet Recalculate"),
            "View": (
                "Freeze Panes",
                "Split View",
                "Gridlines",
                "Formula View",
                "Zoom",
            ),
        }
        for tab_name, actions in definitions.items():
            page = QWidget()
            layout = QHBoxLayout(page)
            layout.setContentsMargins(10, 6, 10, 6)
            for action_name in actions:
                button = QToolButton()
                button.setText(action_name)
                button.setObjectName(
                    action_name.replace(" ", "")[0].lower()
                    + action_name.replace(" ", "")[1:]
                    + "Button"
                )
                button.clicked.connect(
                    lambda checked=False, name=action_name: self.actionRequested.emit(name)
                )
                layout.addWidget(button)
            layout.addStretch(1)
            self.addTab(page, tab_name)
