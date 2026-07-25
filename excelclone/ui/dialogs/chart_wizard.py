"""Chart wizard for range, type, titles, and legend placement."""

from __future__ import annotations

from uuid import uuid4
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from excelclone.core.chart import CHART_TYPES, ChartSpec
from excelclone.core.refs import RangeReference, parse_a1


class ChartWizard(QDialog):
    """Collect a valid immutable chart specification."""

    def __init__(
        self,
        sheet_name: str,
        range_text: str,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.sheet_name = sheet_name
        self.setWindowTitle("Insert Chart")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.range_editor = QLineEdit(range_text)
        self.chart_type = QComboBox()
        self.chart_type.addItems(sorted(CHART_TYPES))
        self.title = QLineEdit()
        self.x_axis = QLineEdit()
        self.y_axis = QLineEdit()
        self.legend = QComboBox()
        self.legend.addItems(("right", "left", "top", "bottom", "none"))
        self.has_headers = QCheckBox()
        self.has_headers.setChecked(True)
        form.addRow("Data range", self.range_editor)
        form.addRow("Chart type", self.chart_type)
        form.addRow("Title", self.title)
        form.addRow("Horizontal axis", self.x_axis)
        form.addRow("Vertical axis", self.y_axis)
        form.addRow("Legend", self.legend)
        form.addRow("First row contains headers", self.has_headers)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chart_spec(self) -> ChartSpec:
        """Build a chart spec or raise for an invalid single-cell range."""
        source_range = parse_a1(
            self.range_editor.text(),
            default_sheet=self.sheet_name,
        )
        if not isinstance(source_range, RangeReference):
            raise ValueError("A chart requires a multi-cell range")
        return ChartSpec(
            uuid4().hex,
            self.sheet_name,
            source_range,
            self.chart_type.currentText(),
            self.title.text(),
            self.x_axis.text(),
            self.y_axis.text(),
            self.legend.currentText(),
            self.has_headers.isChecked(),
        )
