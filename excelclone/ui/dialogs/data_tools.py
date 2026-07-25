"""Dialogs for sort, filter, validation, find/replace, and Paste Special."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from excelclone.core.data_tools import DataValidation, FindOptions, SortKey
from excelclone.core.refs import RangeReference, index_to_column


class _AcceptedDialog(QDialog):
    def _add_buttons(self, layout: QVBoxLayout) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SortDialog(_AcceptedDialog):
    """Configure up to three sort keys."""

    def __init__(self, target: RangeReference, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sort")
        self.target = target
        layout = QVBoxLayout(self)
        self.has_header = QCheckBox("My data has headers")
        self.has_header.setChecked(True)
        layout.addWidget(self.has_header)
        self.key_rows: list[tuple[QComboBox, QComboBox]] = []
        choices = ["(none)"] + [
            index_to_column(column)
            for column in range(target.min_column, target.max_column + 1)
        ]
        for index in range(3):
            row = QHBoxLayout()
            row.addWidget(QLabel("Sort by" if index == 0 else "Then by"))
            column = QComboBox()
            column.addItems(choices)
            column.setCurrentIndex(1 if index == 0 else 0)
            direction = QComboBox()
            direction.addItems(("Ascending", "Descending"))
            row.addWidget(column)
            row.addWidget(direction)
            layout.addLayout(row)
            self.key_rows.append((column, direction))
        self._add_buttons(layout)

    def sort_keys(self) -> tuple[SortKey, ...]:
        result: list[SortKey] = []
        for column, direction in self.key_rows:
            if column.currentIndex() == 0:
                continue
            absolute_column = self.target.min_column + column.currentIndex() - 1
            result.append(SortKey(absolute_column, direction.currentIndex() == 0))
        return tuple(result)


class FilterDialog(_AcceptedDialog):
    """Choose visible values for one filter column."""

    def __init__(self, values: tuple[Any, ...], parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filter Values")
        layout = QVBoxLayout(self)
        self.values = values
        self.list_widget = QListWidget()
        for value in values:
            item = QListWidgetItem("(Blanks)" if value is None else str(value))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        self._add_buttons(layout)

    def allowed_values(self) -> frozenset[Any]:
        return frozenset(
            value
            for index, value in enumerate(self.values)
            if self.list_widget.item(index).checkState() == Qt.CheckState.Checked
        )


class ValidationDialog(_AcceptedDialog):
    """Configure one validation rule for a selection."""

    def __init__(self, target: RangeReference, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Data Validation")
        self.target = target
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItems(
            ("list", "whole_number", "decimal", "date", "text_length", "custom")
        )
        self.operator = QComboBox()
        self.operator.addItems(
            (
                "between",
                "not_between",
                "equal",
                "not_equal",
                "greater_than",
                "greater_equal",
                "less_than",
                "less_equal",
            )
        )
        self.value1 = QLineEdit()
        self.value2 = QLineEdit()
        self.formula = QLineEdit()
        self.allow_blank = QCheckBox()
        self.allow_blank.setChecked(True)
        self.error_message = QLineEdit(
            "The value does not satisfy this cell's validation rule."
        )
        form.addRow("Allow", self.kind)
        form.addRow("Operator", self.operator)
        form.addRow("Value / list", self.value1)
        form.addRow("Second value", self.value2)
        form.addRow("Custom formula", self.formula)
        form.addRow("Allow blank", self.allow_blank)
        form.addRow("Error message", self.error_message)
        layout.addLayout(form)
        self._add_buttons(layout)

    def validation(self) -> DataValidation:
        kind = self.kind.currentText()
        values: tuple[Any, ...]
        if kind == "list":
            values = tuple(
                item.strip()
                for item in self.value1.text().split(",")
                if item.strip()
            )
        else:
            values = tuple(
                _parse_scalar(item)
                for item in (self.value1.text(), self.value2.text())
                if item != ""
            )
        return DataValidation(
            self.target,
            kind,
            self.operator.currentText(),
            values,
            self.formula.text() or None,
            self.allow_blank.isChecked(),
            error_message=self.error_message.text(),
        )


class FindReplaceDialog(_AcceptedDialog):
    """Collect find/replace options."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find and Replace")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.query = QLineEdit()
        self.replacement = QLineEdit()
        self.look_in = QComboBox()
        self.look_in.addItems(("values", "formulas"))
        self.match_case = QCheckBox()
        self.regex = QCheckBox()
        self.whole_cell = QCheckBox()
        self.replace_all = QCheckBox("Replace all matches")
        form.addRow("Find", self.query)
        form.addRow("Replace with", self.replacement)
        form.addRow("Look in", self.look_in)
        form.addRow("Match case", self.match_case)
        form.addRow("Regular expression", self.regex)
        form.addRow("Whole cell", self.whole_cell)
        form.addRow(self.replace_all)
        layout.addLayout(form)
        self._add_buttons(layout)

    def options(self) -> FindOptions:
        return FindOptions(
            self.query.text(),
            self.replacement.text(),
            self.match_case.isChecked(),
            self.regex.isChecked(),
            self.look_in.currentText(),
            self.whole_cell.isChecked(),
        )


class PasteSpecialDialog(_AcceptedDialog):
    """Choose a Paste Special content mode and transpose option."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste Special")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(("all", "values", "formulas", "formats"))
        self.transpose = QCheckBox()
        form.addRow("Paste", self.mode)
        form.addRow("Transpose", self.transpose)
        layout.addLayout(form)
        self._add_buttons(layout)


def _parse_scalar(value: str) -> Any:
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
