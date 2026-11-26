"""Slicers: floating button lists that filter a PivotTable by one field."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.pivot import PivotSlicer, slicer_items


class SlicerPanel(QDockWidget):
    """One slicer: click an item to show only it; Ctrl+click to pick several."""

    selectionApplied = Signal(str, object)
    closeRequested = Signal(str)

    def __init__(self, workbook: Any, slicer: PivotSlicer, parent: QWidget | None = None) -> None:
        super().__init__(slicer.title, parent)
        self.slicer = slicer
        self.workbook = workbook
        self.setObjectName(f"slicer-{slicer.name}")
        self._updating = False
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 4, 6, 6)
        header = QHBoxLayout()
        self.caption = QLabel(slicer.title)
        self.caption.setStyleSheet("font-weight: bold;")
        clear = QPushButton("Clear Filter")
        clear.setObjectName("clearSlicerFilter")
        clear.setToolTip("Show every item")
        clear.clicked.connect(self.clear_filter)
        remove = QPushButton("Remove")
        remove.setObjectName("removeSlicer")
        remove.clicked.connect(lambda: self.closeRequested.emit(self.slicer.name))
        header.addWidget(self.caption, 1)
        header.addWidget(clear)
        header.addWidget(remove)
        layout.addLayout(header)
        self.items = QListWidget()
        self.items.setObjectName("slicerItems")
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items.setStyleSheet(
            "QListWidget::item { border: 1px solid #b7b7b7; margin: 2px; padding: 3px; }"
            "QListWidget::item:selected { background: #1f6fbf; color: white; }"
        )
        self.items.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.items)
        self.setWidget(body)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.refresh(workbook)

    def refresh(self, workbook: Any) -> None:
        """Show the field's items, selecting the ones the PivotTable shows."""
        self.workbook = workbook
        self._updating = True
        self.items.clear()
        for item, selected in slicer_items(workbook, self.slicer):
            entry = QListWidgetItem("(blank)" if item is None else str(item))
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self.items.addItem(entry)
            entry.setSelected(selected)
        self._updating = False

    def selected_items(self) -> list[Any]:
        return [entry.data(Qt.ItemDataRole.UserRole) for entry in self.items.selectedItems()]

    def _selection_changed(self) -> None:
        if self._updating:
            return
        chosen = self.selected_items()
        if not chosen:
            return
        everything = len(chosen) == self.items.count()
        self.selectionApplied.emit(self.slicer.name, None if everything else chosen)

    def clear_filter(self) -> None:
        """Show every item again."""
        self.selectionApplied.emit(self.slicer.name, None)


class InsertSlicersDialog(QDialog):
    """Insert Slicers: tick the fields to slice the PivotTable by."""

    def __init__(self, fields: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Slicers")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the fields to filter the PivotTable by:"))
        self.checks: list[QCheckBox] = []
        for name in fields:
            check = QCheckBox(name)
            layout.addWidget(check)
            self.checks.append(check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> list[str]:
        """Return the ticked fields."""
        return [check.text() for check in self.checks if check.isChecked()]
