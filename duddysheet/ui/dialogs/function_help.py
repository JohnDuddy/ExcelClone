"""Searchable formula-function reference and insertion dialog."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from duddysheet.core.functions import FUNCTION_REGISTRY, FunctionSpec


class FunctionHelpDialog(QDialog):
    """Browse registered function metadata and choose a formula template."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Function")
        self.resize(560, 520)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search functions or descriptions")
        self.function_list = QListWidget()
        self.signature = QLabel()
        self.signature.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Insert Function"
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.function_list, 1)
        layout.addWidget(self.signature)
        layout.addWidget(self.description)
        layout.addWidget(self.buttons)

        self.search.textChanged.connect(self._populate)
        self.function_list.currentItemChanged.connect(self._show_current)
        self.function_list.itemDoubleClicked.connect(lambda item: self.accept())
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self._populate("")

    @property
    def selected_spec(self) -> FunctionSpec | None:
        """Return metadata for the selected registry entry."""
        item = self.function_list.currentItem()
        if item is None:
            return None
        return FUNCTION_REGISTRY.get(item.data(Qt.ItemDataRole.UserRole))

    def formula_template(self) -> str:
        """Return an editable formula call for the selected function."""
        spec = self.selected_spec
        return f"={spec.name}()" if spec is not None else ""

    def _populate(self, query: str) -> None:
        selected_name = (
            self.selected_spec.name if self.selected_spec is not None else None
        )
        folded = query.strip().casefold()
        self.function_list.clear()
        for name, spec in sorted(FUNCTION_REGISTRY.items()):
            searchable = f"{name} {spec.description} {spec.argument_spec}".casefold()
            if folded and folded not in searchable:
                continue
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.function_list.addItem(item)
            if name == selected_name:
                self.function_list.setCurrentItem(item)
        if self.function_list.currentItem() is None and self.function_list.count():
            self.function_list.setCurrentRow(0)

    def _show_current(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        spec = (
            FUNCTION_REGISTRY.get(current.data(Qt.ItemDataRole.UserRole))
            if current is not None
            else None
        )
        if spec is None:
            self.signature.clear()
            self.description.clear()
            return
        arguments = spec.argument_spec or "no arguments"
        volatility = "  [volatile]" if spec.volatile else ""
        self.signature.setText(f"{spec.name}({arguments}){volatility}")
        self.description.setText(spec.description)
