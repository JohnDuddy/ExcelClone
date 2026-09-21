"""Create Sparklines dialog, modelled on Excel's."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.refs import CellReference, RangeReference, parse_a1
from duddysheet.core.sparkline import (
    SPARKLINE_KIND_LABELS,
    SPARKLINE_KINDS,
    Sparkline,
    build_sparklines,
)

SPARKLINE_COLORS = {
    "Blue": "#2f6fb0",
    "Teal": "#0b6e75",
    "Orange": "#d9822b",
    "Green": "#3a8a3a",
    "Purple": "#6a4c93",
    "Gray": "#595959",
}


def default_location(data_range: RangeReference) -> RangeReference:
    """Suggest the column (or cell) just right of the data, as Excel users do."""
    column = data_range.max_column + 1
    return RangeReference(
        CellReference(data_range.min_row, column),
        CellReference(data_range.max_row, column),
    )


class SparklineDialog(QDialog):
    """Choose the data range, location range, and style of new sparklines."""

    def __init__(
        self,
        sheet_name: str,
        kind: str,
        data_text: str,
        location_text: str,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.sheet_name = sheet_name
        self.setObjectName("sparklineDialog")
        self.setWindowTitle("Create Sparklines")
        self.kind = QComboBox()
        for key in SPARKLINE_KINDS:
            self.kind.addItem(SPARKLINE_KIND_LABELS[key], key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(kind)))
        self.data_range = QLineEdit(data_text)
        self.location_range = QLineEdit(location_text)
        self.color = QComboBox()
        self.color.addItems(tuple(SPARKLINE_COLORS))
        self.show_markers = QCheckBox("Markers")
        self.show_high = QCheckBox("High point")
        self.show_low = QCheckBox("Low point")
        self.show_first = QCheckBox("First point")
        self.show_last = QCheckBox("Last point")
        self.show_negative = QCheckBox("Negative points")
        self.show_axis = QCheckBox("Show axis")
        intro = QLabel(
            "Each location cell gets one sparkline. A location column takes "
            "one data row per cell; a location row takes one data column per "
            "cell."
        )
        intro.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Type", self.kind)
        form.addRow("Data range", self.data_range)
        form.addRow("Location range", self.location_range)
        form.addRow("Color", self.color)
        form.addRow("Show", _pair(self.show_markers, self.show_axis))
        form.addRow("", _pair(self.show_high, self.show_low))
        form.addRow("", _pair(self.show_first, self.show_last))
        form.addRow("", self.show_negative)
        self.error = QLabel()
        self.error.setStyleSheet("color: #b42318;")
        self.error.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self._sync_markers)
        self._sync_markers()

    def _sync_markers(self, *_: Any) -> None:
        self.show_markers.setEnabled(self.kind.currentData() == "line")

    def sparklines(self) -> tuple[Sparkline, ...]:
        """Build the sparklines described by the dialog's fields."""
        sheet_name = self.sheet_name
        data = parse_a1(self.data_range.text(), default_sheet=sheet_name)
        location = parse_a1(self.location_range.text())
        if isinstance(data, CellReference):
            data = RangeReference(data, data)
        if not isinstance(data, RangeReference):
            raise ValueError("The data range must be a cell range")
        if not isinstance(location, (CellReference, RangeReference)):
            raise ValueError("The location range must be cells on this sheet")
        if location.sheet is not None and location.sheet.casefold() != sheet_name.casefold():
            raise ValueError("Sparklines are placed on the active sheet")
        return build_sparklines(
            data,
            location,
            self.kind.currentData(),
            color=SPARKLINE_COLORS[self.color.currentText()],
            show_markers=self.show_markers.isChecked()
            and self.kind.currentData() == "line",
            show_high=self.show_high.isChecked(),
            show_low=self.show_low.isChecked(),
            show_first=self.show_first.isChecked(),
            show_last=self.show_last.isChecked(),
            show_negative=self.show_negative.isChecked(),
            show_axis=self.show_axis.isChecked(),
        )

    def _accept(self) -> None:
        try:
            self.sparklines()
        except (ValueError, KeyError) as error:
            self.error.setText(str(error))
            return
        self.accept()


def _pair(first: QWidget, second: QWidget) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(first)
    layout.addWidget(second)
    layout.addStretch(1)
    return container
