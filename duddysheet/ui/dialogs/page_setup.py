"""Page setup dialog.

The dialog only reads and writes an immutable :class:`PageSetup`; it holds no
layout logic of its own, so what the user configures here is exactly what
pagination, preview, printing, and PDF export consume.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.printing import (
    PAPER_SIZES,
    Margins,
    Orientation,
    PageOrder,
    PageSetup,
)
from duddysheet.core.refs import RangeReference, parse_a1

_HEADER_TOKEN_HELP = (
    "Tokens:  &P page   &N total pages   &D date   &T time   "
    "&F file   &A sheet   && literal ampersand"
)


def _points_to_inches(points: float) -> float:
    return points / 72.0


def _inches_to_points(inches: float) -> float:
    return inches * 72.0


class PageSetupDialog(QDialog):
    """Collect paper, scaling, margin, header, and sheet print options."""

    def __init__(
        self,
        setup: PageSetup | None = None,
        parent: QWidget | None = None,
        *,
        sheet_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Page Setup")
        self.resize(520, 520)
        self._sheet_name = sheet_name
        self._initial = setup or PageSetup()

        layout = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_page_tab(), "Page")
        tabs.addTab(self._build_margins_tab(), "Margins")
        tabs.addTab(self._build_header_tab(), "Header/Footer")
        tabs.addTab(self._build_sheet_tab(), "Sheet")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load(self._initial)

    def _build_page_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.paper_box = QComboBox(page)
        for name in PAPER_SIZES:
            self.paper_box.addItem(name)
        form.addRow("Paper size", self.paper_box)

        orientation = QWidget(page)
        row = QHBoxLayout(orientation)
        row.setContentsMargins(0, 0, 0, 0)
        self.portrait_button = QRadioButton("Portrait", orientation)
        self.landscape_button = QRadioButton("Landscape", orientation)
        row.addWidget(self.portrait_button)
        row.addWidget(self.landscape_button)
        row.addStretch(1)
        form.addRow("Orientation", orientation)

        scaling = QGroupBox("Scaling", page)
        scaling_form = QFormLayout(scaling)
        self.scale_button = QRadioButton("Adjust to", scaling)
        self.scale_spin = QSpinBox(scaling)
        self.scale_spin.setRange(10, 400)
        self.scale_spin.setSuffix(" %")
        scaling_form.addRow(self.scale_button, self.scale_spin)

        self.fit_button = QRadioButton("Fit to", scaling)
        fit_row = QWidget(scaling)
        fit_layout = QHBoxLayout(fit_row)
        fit_layout.setContentsMargins(0, 0, 0, 0)
        self.fit_width_spin = QSpinBox(fit_row)
        self.fit_width_spin.setRange(0, 50)
        self.fit_width_spin.setSpecialValueText("auto")
        self.fit_height_spin = QSpinBox(fit_row)
        self.fit_height_spin.setRange(0, 50)
        self.fit_height_spin.setSpecialValueText("auto")
        fit_layout.addWidget(self.fit_width_spin)
        fit_layout.addWidget(QLabel("pages wide by", fit_row))
        fit_layout.addWidget(self.fit_height_spin)
        fit_layout.addWidget(QLabel("tall", fit_row))
        fit_layout.addStretch(1)
        scaling_form.addRow(self.fit_button, fit_row)
        form.addRow(scaling)

        self.first_page_spin = QSpinBox(page)
        self.first_page_spin.setRange(1, 10000)
        form.addRow("First page number", self.first_page_spin)

        self.scale_button.toggled.connect(self._sync_scaling_enabled)
        self.fit_button.toggled.connect(self._sync_scaling_enabled)
        return page

    def _sync_scaling_enabled(self) -> None:
        """Keep only the selected scaling mode's inputs active."""
        self.scale_spin.setEnabled(self.scale_button.isChecked())
        self.fit_width_spin.setEnabled(self.fit_button.isChecked())
        self.fit_height_spin.setEnabled(self.fit_button.isChecked())

    def _build_margins_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        def spin() -> QDoubleSpinBox:
            box = QDoubleSpinBox(page)
            box.setRange(0.0, 10.0)
            box.setSingleStep(0.1)
            box.setDecimals(2)
            box.setSuffix(" in")
            return box

        self.margin_top = spin()
        self.margin_bottom = spin()
        self.margin_left = spin()
        self.margin_right = spin()
        self.margin_header = spin()
        self.margin_footer = spin()

        form.addRow("Top", self.margin_top)
        form.addRow("Bottom", self.margin_bottom)
        form.addRow("Left", self.margin_left)
        form.addRow("Right", self.margin_right)
        form.addRow("Header", self.margin_header)
        form.addRow("Footer", self.margin_footer)

        self.center_horizontal = QCheckBox("Center horizontally", page)
        self.center_vertical = QCheckBox("Center vertically", page)
        form.addRow(self.center_horizontal)
        form.addRow(self.center_vertical)
        return page

    def _build_header_tab(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)

        header_box = QGroupBox("Header", page)
        header_form = QFormLayout(header_box)
        self.header_left = QLineEdit(header_box)
        self.header_center = QLineEdit(header_box)
        self.header_right = QLineEdit(header_box)
        header_form.addRow("Left", self.header_left)
        header_form.addRow("Center", self.header_center)
        header_form.addRow("Right", self.header_right)
        layout.addWidget(header_box)

        footer_box = QGroupBox("Footer", page)
        footer_form = QFormLayout(footer_box)
        self.footer_left = QLineEdit(footer_box)
        self.footer_center = QLineEdit(footer_box)
        self.footer_right = QLineEdit(footer_box)
        footer_form.addRow("Left", self.footer_left)
        footer_form.addRow("Center", self.footer_center)
        footer_form.addRow("Right", self.footer_right)
        layout.addWidget(footer_box)

        hint = QLabel(_HEADER_TOKEN_HELP, page)
        hint.setWordWrap(True)
        hint.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_sheet_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.print_area_edit = QLineEdit(page)
        self.print_area_edit.setPlaceholderText("Entire sheet, for example A1:H40")
        form.addRow("Print area", self.print_area_edit)

        self.repeat_rows_edit = QLineEdit(page)
        self.repeat_rows_edit.setPlaceholderText("Rows to repeat, for example 1:2")
        form.addRow("Repeat rows at top", self.repeat_rows_edit)

        self.repeat_columns_edit = QLineEdit(page)
        self.repeat_columns_edit.setPlaceholderText(
            "Columns to repeat, for example A:A"
        )
        form.addRow("Repeat columns at left", self.repeat_columns_edit)

        self.gridlines_check = QCheckBox("Print gridlines", page)
        self.headings_check = QCheckBox("Print row and column headings", page)
        form.addRow(self.gridlines_check)
        form.addRow(self.headings_check)

        self.order_box = QComboBox(page)
        self.order_box.addItem("Down, then over", PageOrder.DOWN_THEN_OVER)
        self.order_box.addItem("Over, then down", PageOrder.OVER_THEN_DOWN)
        form.addRow("Page order", self.order_box)

        self.error_label = QLabel("", page)
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)
        form.addRow(self.error_label)
        return page

    def _load(self, setup: PageSetup) -> None:
        """Populate every control from a page setup."""
        self.paper_box.setCurrentText(setup.paper.name)
        self.portrait_button.setChecked(setup.orientation is Orientation.PORTRAIT)
        self.landscape_button.setChecked(setup.orientation is Orientation.LANDSCAPE)

        self.fit_button.setChecked(setup.fits_to_page)
        self.scale_button.setChecked(not setup.fits_to_page)
        self.scale_spin.setValue(round(setup.scale * 100))
        self.fit_width_spin.setValue(setup.fit_to_width or 0)
        self.fit_height_spin.setValue(setup.fit_to_height or 0)
        self.first_page_spin.setValue(setup.first_page_number)
        self._sync_scaling_enabled()

        self.margin_top.setValue(_points_to_inches(setup.margins.top))
        self.margin_bottom.setValue(_points_to_inches(setup.margins.bottom))
        self.margin_left.setValue(_points_to_inches(setup.margins.left))
        self.margin_right.setValue(_points_to_inches(setup.margins.right))
        self.margin_header.setValue(_points_to_inches(setup.margins.header))
        self.margin_footer.setValue(_points_to_inches(setup.margins.footer))
        self.center_horizontal.setChecked(setup.center_horizontally)
        self.center_vertical.setChecked(setup.center_vertically)

        self.header_left.setText(setup.header_left)
        self.header_center.setText(setup.header_center)
        self.header_right.setText(setup.header_right)
        self.footer_left.setText(setup.footer_left)
        self.footer_center.setText(setup.footer_center)
        self.footer_right.setText(setup.footer_right)

        self.print_area_edit.setText(
            setup.print_area.to_a1(include_sheet=False) if setup.print_area else ""
        )
        self.repeat_rows_edit.setText(_span_text(setup.repeat_rows, numeric=True))
        self.repeat_columns_edit.setText(
            _span_text(setup.repeat_columns, numeric=False)
        )
        self.gridlines_check.setChecked(setup.show_gridlines)
        self.headings_check.setChecked(setup.show_headings)
        index = self.order_box.findData(setup.page_order)
        self.order_box.setCurrentIndex(max(0, index))

    def page_setup(self) -> PageSetup:
        """Return the configured page setup."""
        margins = Margins(
            left=_inches_to_points(self.margin_left.value()),
            right=_inches_to_points(self.margin_right.value()),
            top=_inches_to_points(self.margin_top.value()),
            bottom=_inches_to_points(self.margin_bottom.value()),
            header=_inches_to_points(self.margin_header.value()),
            footer=_inches_to_points(self.margin_footer.value()),
        )

        fitting = self.fit_button.isChecked()
        return PageSetup(
            paper=PAPER_SIZES[self.paper_box.currentText()],
            orientation=(
                Orientation.LANDSCAPE
                if self.landscape_button.isChecked()
                else Orientation.PORTRAIT
            ),
            margins=margins,
            scale=1.0 if fitting else self.scale_spin.value() / 100.0,
            fit_to_width=(
                self.fit_width_spin.value()
                if fitting and self.fit_width_spin.value() > 0
                else None
            ),
            fit_to_height=(
                self.fit_height_spin.value()
                if fitting and self.fit_height_spin.value() > 0
                else None
            ),
            print_area=self._parse_print_area(),
            show_gridlines=self.gridlines_check.isChecked(),
            show_headings=self.headings_check.isChecked(),
            repeat_rows=_parse_span(self.repeat_rows_edit.text(), numeric=True),
            repeat_columns=_parse_span(
                self.repeat_columns_edit.text(), numeric=False
            ),
            header_left=self.header_left.text(),
            header_center=self.header_center.text(),
            header_right=self.header_right.text(),
            footer_left=self.footer_left.text(),
            footer_center=self.footer_center.text(),
            footer_right=self.footer_right.text(),
            center_horizontally=self.center_horizontal.isChecked(),
            center_vertically=self.center_vertical.isChecked(),
            page_order=self.order_box.currentData(),
            first_page_number=self.first_page_spin.value(),
        )

    def _parse_print_area(self) -> RangeReference | None:
        text = self.print_area_edit.text().strip()
        if not text:
            return None
        try:
            parsed = parse_a1(text, default_sheet=self._sheet_name or None)
        except (ValueError, KeyError):
            return None
        return parsed if isinstance(parsed, RangeReference) else None

    def accept(self) -> None:
        """Validate the entered ranges before closing."""
        problems: list[str] = []
        if self.print_area_edit.text().strip() and self._parse_print_area() is None:
            problems.append("Print area must be a range such as A1:H40.")
        if self.repeat_rows_edit.text().strip() and _parse_span(
            self.repeat_rows_edit.text(), numeric=True
        ) is None:
            problems.append("Rows to repeat must look like 1:2.")
        if self.repeat_columns_edit.text().strip() and _parse_span(
            self.repeat_columns_edit.text(), numeric=False
        ) is None:
            problems.append("Columns to repeat must look like A:B.")

        if problems:
            self.error_label.setText(" ".join(problems))
            return
        super().accept()


def _span_text(span: tuple[int, int] | None, *, numeric: bool) -> str:
    """Render a zero-based repeat span as user-facing 1:2 or A:B text."""
    if span is None:
        return ""
    first, last = span
    if numeric:
        return f"{first + 1}:{last + 1}"
    return f"{_column_letters(first)}:{_column_letters(last)}"


def _column_letters(index: int) -> str:
    """Return the spreadsheet letters for a zero-based column index."""
    letters = ""
    current = index + 1
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _column_index(letters: str) -> int | None:
    """Return the zero-based column index for spreadsheet letters."""
    if not letters or not letters.isalpha():
        return None
    index = 0
    for character in letters.upper():
        index = index * 26 + (ord(character) - ord("A") + 1)
    return index - 1


def _parse_span(text: str, *, numeric: bool) -> tuple[int, int] | None:
    """Parse ``1:2`` or ``A:B`` into an ordered zero-based span."""
    cleaned = text.strip().replace("$", "")
    if not cleaned:
        return None
    parts = cleaned.split(":")
    if len(parts) == 1:
        parts = [parts[0], parts[0]]
    if len(parts) != 2:
        return None

    if numeric:
        if not all(part.isdigit() for part in parts):
            return None
        first, last = int(parts[0]) - 1, int(parts[1]) - 1
    else:
        indices = [_column_index(part) for part in parts]
        if any(index is None for index in indices):
            return None
        first, last = indices  # type: ignore[assignment]

    if first < 0 or last < 0:
        return None
    return (min(first, last), max(first, last))
