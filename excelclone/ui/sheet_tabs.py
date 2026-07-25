"""Movable workbook sheet tabs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QToolButton, QWidget

from excelclone.core.workbook import Workbook


class SheetTabs(QWidget):
    """Sheet tab strip with add, close, move, and selection signals."""

    addRequested = Signal()
    closeRequested = Signal(int)
    activeChanged = Signal(int)
    moved = Signal(int, int)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("sheetTabs")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.add_button = QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip("New sheet")
        self.add_button.clicked.connect(self.addRequested.emit)
        self.tab_bar = QTabBar()
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.currentChanged.connect(self.activeChanged.emit)
        self.tab_bar.tabCloseRequested.connect(self.closeRequested.emit)
        self.tab_bar.tabMoved.connect(self.moved.emit)
        layout.addWidget(self.add_button)
        layout.addWidget(self.tab_bar, 1)

    def sync(self, workbook: Workbook) -> None:
        """Rebuild tabs from workbook order and active-sheet state."""
        self.tab_bar.blockSignals(True)
        while self.tab_bar.count():
            self.tab_bar.removeTab(self.tab_bar.count() - 1)
        for sheet in workbook:
            self.tab_bar.addTab(sheet.name)
        self.tab_bar.setCurrentIndex(workbook.active_sheet_index)
        self.tab_bar.blockSignals(False)
