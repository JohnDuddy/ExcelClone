"""Format Cells dialog spanning number, font, fill, alignment, and borders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.core.conditional import FormatPatch

NUMBER_FORMATS = (
    "General",
    "0",
    "0.00",
    "#,##0",
    "#,##0.00",
    "$#,##0.00",
    '_("$"* #,##0.00_);_("$"* (#,##0.00);_("$"* "-"??_);_(@_)',
    "0%",
    "0.00%",
    "# ?/?",
    "0.00E+00",
    "m/d/yyyy",
    "mm/dd/yyyy",
    "d-mmm-yy",
    "yyyy-mm-dd",
    "h:mm AM/PM",
    "h:mm:ss",
    "@",
)

BORDER_STYLES = (
    "none",
    "thin",
    "medium",
    "dashed",
    "dotted",
    "thick",
    "double",
    "hair",
)


class FormatCellsDialog(QDialog):
    """Edit a cell-format patch without mutating workbook state."""

    def __init__(self, base: CellFormat, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Format Cells")
        self.setMinimumWidth(460)
        self._base = base
        tabs = QTabWidget()
        tabs.addTab(self._number_tab(base), "Number")
        tabs.addTab(self._font_tab(base), "Font")
        tabs.addTab(self._fill_tab(base), "Fill")
        tabs.addTab(self._alignment_tab(base), "Alignment")
        tabs.addTab(self._border_tab(base), "Border")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _number_tab(self, base: CellFormat) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.number_format = QComboBox()
        self.number_format.setEditable(True)
        self.number_format.addItems(NUMBER_FORMATS)
        self.number_format.setCurrentText(base.number_format)
        layout.addRow("Format code", self.number_format)
        layout.addRow(
            QLabel(
                "Custom codes support positive;negative;zero;text sections, "
                "colors, literals, #, 0, ?, commas, percent, and @."
            )
        )
        return page

    def _font_tab(self, base: CellFormat) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        self.font_family.addItems(("Aptos", "Calibri", "Arial", "Cambria", "Consolas"))
        self.font_family.setCurrentText(base.font_family)
        self.font_size = QDoubleSpinBox()
        self.font_size.setRange(6, 96)
        self.font_size.setValue(base.font_size)
        self.bold = QCheckBox("Bold")
        self.bold.setChecked(base.bold)
        self.italic = QCheckBox("Italic")
        self.italic.setChecked(base.italic)
        self.underline = QCheckBox("Underline")
        self.underline.setChecked(base.underline)
        self.font_color = self._color_row(base.font_color)
        layout.addRow("Family", self.font_family)
        layout.addRow("Size", self.font_size)
        layout.addRow(self.bold)
        layout.addRow(self.italic)
        layout.addRow(self.underline)
        layout.addRow("Color", self.font_color)
        return page

    def _fill_tab(self, base: CellFormat) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.fill_color = self._color_row(base.fill_color or "")
        layout.addRow("Fill color", self.fill_color)
        layout.addRow(QLabel("Leave blank for no fill."))
        return page

    def _alignment_tab(self, base: CellFormat) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.horizontal = QComboBox()
        self.horizontal.addItems(("general", "left", "center", "right"))
        self.horizontal.setCurrentText(base.horizontal_alignment)
        self.vertical = QComboBox()
        self.vertical.addItems(("top", "center", "bottom"))
        self.vertical.setCurrentText(base.vertical_alignment)
        self.wrap_text = QCheckBox("Wrap text")
        self.wrap_text.setChecked(base.wrap_text)
        layout.addRow("Horizontal", self.horizontal)
        layout.addRow("Vertical", self.vertical)
        layout.addRow(self.wrap_text)
        return page

    def _border_tab(self, base: CellFormat) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.border_style = QComboBox()
        self.border_style.addItems(BORDER_STYLES)
        self.border_color = self._color_row("#000000")
        self.border_left = QCheckBox("Left")
        self.border_right = QCheckBox("Right")
        self.border_top = QCheckBox("Top")
        self.border_bottom = QCheckBox("Bottom")
        edges = QHBoxLayout()
        for checkbox in (
            self.border_left,
            self.border_right,
            self.border_top,
            self.border_bottom,
        ):
            edges.addWidget(checkbox)
        layout.addRow("Style", self.border_style)
        layout.addRow("Color", self.border_color)
        layout.addRow("Edges", edges)
        return page

    def _color_row(self, initial: str) -> QLineEdit:
        editor = QLineEdit(initial)
        button = QPushButton("Choose")
        button.clicked.connect(lambda: self._choose_color(editor))
        editor.setProperty("chooserButton", button)
        return editor

    def _choose_color(self, editor: QLineEdit) -> None:
        selected = QColorDialog.getColor(QColor(editor.text() or "#ffffff"), self)
        if selected.isValid():
            editor.setText(selected.name())

    def format_patch(self) -> FormatPatch:
        """Return the dialog values as a complete format patch."""
        border = BorderStyle(
            self.border_style.currentText(),
            self.border_color.text() or "#000000",
        )
        return FormatPatch(
            number_format=self.number_format.currentText() or "General",
            font_family=self.font_family.currentText() or "Aptos",
            font_size=self.font_size.value(),
            bold=self.bold.isChecked(),
            italic=self.italic.isChecked(),
            underline=self.underline.isChecked(),
            font_color=self.font_color.text() or "#000000",
            fill_color=self.fill_color.text() or None,
            horizontal_alignment=self.horizontal.currentText(),
            vertical_alignment=self.vertical.currentText(),
            wrap_text=self.wrap_text.isChecked(),
            left_border=border if self.border_left.isChecked() else self._base.left_border,
            right_border=border if self.border_right.isChecked() else self._base.right_border,
            top_border=border if self.border_top.isChecked() else self._base.top_border,
            bottom_border=border if self.border_bottom.isChecked() else self._base.bottom_border,
        )
