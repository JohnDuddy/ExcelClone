"""Live-preview chart studio with recommendations and detailed controls."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
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
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.chart import (
    CHART_FAMILIES,
    CHART_INFO,
    CHART_TYPE_LABELS,
    ChartSpec,
    chart_data,
    detect_chart_headers,
    infer_chart_title,
    recommend_charts,
)
from duddysheet.core.refs import (
    RangeReference,
    column_to_index,
    index_to_column,
    parse_a1,
)
from duddysheet.core.workbook import Workbook
from duddysheet.ui.chart_renderer import draw_chart
from duddysheet.ui.dialogs.chart_help import ChartHelpDialog

_LABEL_POSITIONS = (
    ("Automatic", "auto"),
    ("Center", "center"),
    ("Inside end", "inside_end"),
    ("Inside base", "inside_base"),
    ("Outside end", "outside_end"),
)
_LABEL_CONTENTS = (
    ("Value", "value"),
    ("Percentage", "percent"),
    ("Category name", "category"),
    ("Series name", "series"),
    ("Category and value", "category_value"),
)
_ERROR_BARS = (
    ("None", "none"),
    ("Standard error", "standard_error"),
    ("Percentage", "percentage"),
    ("Standard deviation", "standard_deviation"),
    ("Fixed value", "fixed"),
)
_TRENDLINES = (
    ("Linear", "linear"),
    ("Exponential", "exponential"),
    ("Logarithmic", "logarithmic"),
    ("Polynomial", "polynomial"),
    ("Power", "power"),
    ("Moving average", "moving_average"),
)
_DISPLAY_UNITS = (
    ("None", "none"),
    ("Hundreds", "hundreds"),
    ("Thousands", "thousands"),
    ("Millions", "millions"),
    ("Billions", "billions"),
)
_COLOR_SCHEMES = (
    ("Theme colors", "theme"),
    ("Colorful", "colorful"),
    ("Monochromatic blue", "blue"),
    ("Monochromatic orange", "orange"),
    ("Monochromatic green", "green"),
    ("Monochromatic purple", "purple"),
    ("Monochromatic gray", "gray"),
)
_EMPTY_CELLS = (
    ("Gaps", "gaps"),
    ("Zero", "zero"),
    ("Connect data points with line", "connect"),
)


class _KeyCombo(QComboBox):
    """Display friendly labels while accepting stable keys in setCurrentText."""

    def __init__(self, items: tuple[tuple[str, str], ...] = ()) -> None:
        super().__init__()
        for label, key in items:
            self.addItem(label, key)

    def setCurrentText(self, text: str) -> None:
        index = self.findData(text)
        if index >= 0:
            self.setCurrentIndex(index)
            return
        super().setCurrentText(text)


# Retained name: tests and callers address chart types by key.
_ChartTypeCombo = _KeyCombo


class ChartWizard(QDialog):
    """Build or edit a chart with ranked suggestions and a live preview."""

    def __init__(
        self,
        sheet_name: str,
        range_text: str,
        parent: Any = None,
        *,
        workbook: Workbook | None = None,
        existing: ChartSpec | None = None,
        initial_type: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.sheet_name = sheet_name
        self.workbook = workbook
        self.existing = existing
        self._recommendations = ()
        self.setWindowTitle("Chart Studio")
        self.resize(1120, 720)

        self._create_fields(range_text)
        self.recommendation_list = QListWidget()
        self.recommendation_list.setMinimumHeight(180)
        self.recommendation_reason = QLabel(
            "Select a recommendation to see why it fits."
        )
        self.recommendation_reason.setWordWrap(True)
        self.recommendation_reason.setObjectName("recommendationReason")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._recommended_tab(), "Recommended")
        self.tabs.addTab(self._all_charts_tab(), "All Charts")
        self.tabs.addTab(_scrolling(self._elements_tab()), "Elements")
        self.tabs.addTab(_scrolling(self._format_tab()), "Format")
        self.tabs.addTab(_scrolling(self._data_tab()), "Data")
        self.tabs.setMinimumWidth(390)
        self.tabs.setMaximumWidth(470)

        self.preview_figure = Figure(figsize=(6.2, 4.6), constrained_layout=True)
        self.preview_canvas = FigureCanvasQTAgg(self.preview_figure)
        preview_label = QLabel("LIVE PREVIEW")
        preview_label.setObjectName("previewLabel")
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(10, 0, 0, 0)
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.preview_canvas, 1)

        body = QHBoxLayout()
        body.addWidget(self.tabs)
        body.addWidget(preview, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Help
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Update Chart" if existing is not None else "Create Chart"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.helpRequested.connect(self.show_help)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)
        self.setStyleSheet(
            """
            QDialog {
                background: #f4f1e8;
                font-family: "Segoe UI";
                font-size: 12px;
            }
            QTabWidget::pane { border: 1px solid #cec7b6; background: #fffdf8; }
            QListWidget, QTreeWidget { border: 0; background: #fffdf8; font-size: 13px; }
            QListWidget::item { padding: 10px; margin: 2px; }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background: #0b6e75; color: white;
            }
            QScrollArea { border: 0; background: #fffdf8; }
            #recommendationReason, #chartTypeDescription {
                background: #e7f0ed; color: #183832; padding: 10px;
                border-left: 4px solid #0b6e75;
            }
            #previewLabel {
                color: #0b6e75; font-weight: 700; letter-spacing: 2px;
            }
            #sectionLabel {
                color: #0b6e75; font-weight: 700; padding-top: 8px;
            }
            """
        )

        self._load_existing()
        if self.existing is None and self.workbook is not None:
            try:
                self.has_headers.setChecked(
                    detect_chart_headers(
                        self.workbook,
                        self.sheet_name,
                        self._source_range(),
                    )
                )
            except (KeyError, ValueError):
                pass
        self._connect_updates()
        self._refresh_recommendations()
        if initial_type is not None and existing is None:
            self.chart_type.setCurrentText(initial_type)
            self.tabs.setCurrentIndex(1)
        self._sync_gallery()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Fields

    def _create_fields(self, range_text: str) -> None:
        self.range_editor = QLineEdit(range_text)
        self.chart_type = _KeyCombo(
            tuple(
                (CHART_TYPE_LABELS[key], key)
                for _, keys in CHART_FAMILIES
                for key in keys
            )
        )
        self.title = QLineEdit()
        self.x_axis = QLineEdit()
        self.y_axis = QLineEdit()
        self.legend = QComboBox()
        self.legend.addItems(("right", "left", "top", "bottom", "none"))
        self.theme = QComboBox()
        self.theme.addItems(
            ("executive", "coastal", "editorial", "monochrome", "high_contrast")
        )
        self.number_format = QComboBox()
        self.number_format.addItems(("auto", "number", "currency", "percent"))
        self.has_headers = QCheckBox()
        self.has_headers.setChecked(True)
        self.show_grid = QCheckBox("Major (value)")
        self.show_grid.setChecked(True)
        self.vertical_gridlines = QCheckBox("Major (category)")
        self.minor_gridlines = QCheckBox("Minor")
        self.show_x_axis = QCheckBox("Primary horizontal")
        self.show_x_axis.setChecked(True)
        self.show_y_axis = QCheckBox("Primary vertical")
        self.show_y_axis.setChecked(True)
        self.show_labels = QCheckBox()
        self.label_position = _KeyCombo(_LABEL_POSITIONS)
        self.label_content = _KeyCombo(_LABEL_CONTENTS)
        self.show_data_table = QCheckBox()
        self.error_bars = _KeyCombo(_ERROR_BARS)
        self.error_amount = QLineEdit()
        self.error_amount.setPlaceholderText("Default for the type")
        self.show_trendline = QCheckBox()
        self.trendline_type = _KeyCombo(_TRENDLINES)
        self.trendline_order = QSpinBox()
        self.trendline_order.setRange(2, 100)
        self.trendline_order.setValue(2)
        self.trendline_forward = QLineEdit()
        self.trendline_forward.setPlaceholderText("0")
        self.trendline_backward = QLineEdit()
        self.trendline_backward.setPlaceholderText("0")
        self.show_equation = QCheckBox()
        self.show_r_squared = QCheckBox()
        self.drop_lines = QCheckBox("Drop lines")
        self.high_low_lines = QCheckBox("High-low lines")
        self.up_down_bars = QCheckBox("Up/down bars")
        self.highlight_extrema = QCheckBox()
        self.secondary_axis = QCheckBox()
        self.color_scheme = _KeyCombo(_COLOR_SCHEMES)
        self.axis_min = QLineEdit()
        self.axis_min.setPlaceholderText("Auto")
        self.axis_max = QLineEdit()
        self.axis_max.setPlaceholderText("Auto")
        self.major_unit = QLineEdit()
        self.major_unit.setPlaceholderText("Auto")
        self.log_scale = QCheckBox()
        self.reverse_categories = QCheckBox()
        self.display_units = _KeyCombo(_DISPLAY_UNITS)
        self.smooth_lines = QCheckBox()
        self.gap_width = _spin(0, 500, 22, "%")
        self.series_overlap = _spin(-100, 100, 0, "%")
        self.hole_size = _spin(10, 90, 58, "%")
        self.first_slice_angle = _spin(0, 360, 0, "°")
        self.pie_explosion = _spin(0, 400, 0, "%")
        self.split_count = _spin(1, 50, 3, "")
        self.bin_count = _spin(0, 1000, 0, "")
        self.bin_count.setSpecialValueText("Automatic")
        self.category_editor = QLineEdit()
        self.category_editor.setPlaceholderText("Auto or column letter, e.g. A")
        self.series_editor = QLineEdit()
        self.series_editor.setPlaceholderText("Auto or columns, e.g. B,C,D")
        self.switch_row_column = QCheckBox()
        self.empty_cells = _KeyCombo(_EMPTY_CELLS)
        self.combo_types_editor = QLineEdit()
        self.combo_types_editor.setPlaceholderText("e.g. column,line,area")
        self.secondary_series_editor = QLineEdit()
        self.secondary_series_editor.setPlaceholderText("Series numbers, e.g. 2,3")

    def _recommended_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "Ranked from the shape and meaning of the selected data. "
            "Choose one, then refine it in Elements and Format."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self.recommendation_list)
        layout.addWidget(self.recommendation_reason)
        layout.addStretch(1)
        return page

    def _all_charts_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("Chart type", self.chart_type)
        layout.addLayout(form)
        self.gallery = QTreeWidget()
        self.gallery.setObjectName("chartGallery")
        self.gallery.setHeaderHidden(True)
        for family, keys in CHART_FAMILIES:
            parent = QTreeWidgetItem([family])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for key in keys:
                child = QTreeWidgetItem([CHART_TYPE_LABELS[key]])
                child.setData(0, Qt.ItemDataRole.UserRole, key)
                child.setToolTip(0, CHART_INFO[key].summary)
                parent.addChild(child)
            self.gallery.addTopLevelItem(parent)
        self.gallery.expandAll()
        self.type_description = QLabel()
        self.type_description.setObjectName("chartTypeDescription")
        self.type_description.setWordWrap(True)
        layout.addWidget(self.gallery, 1)
        layout.addWidget(self.type_description)
        return page

    def _elements_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(_section("Titles"))
        form.addRow("Chart title", self.title)
        form.addRow("Horizontal axis title", self.x_axis)
        form.addRow("Vertical axis title", self.y_axis)
        form.addRow(_section("Axes and gridlines"))
        form.addRow("Axes", _row(self.show_x_axis, self.show_y_axis))
        form.addRow(
            "Gridlines",
            _row(self.show_grid, self.vertical_gridlines, self.minor_gridlines),
        )
        form.addRow("Legend", self.legend)
        form.addRow(_section("Data labels and table"))
        form.addRow("Show data labels", self.show_labels)
        form.addRow("Label position", self.label_position)
        form.addRow("Label contains", self.label_content)
        form.addRow("Show data table", self.show_data_table)
        form.addRow(_section("Error bars"))
        form.addRow("Error bars", self.error_bars)
        form.addRow("Amount", self.error_amount)
        form.addRow(_section("Trendline"))
        form.addRow("Show trendline", self.show_trendline)
        form.addRow("Type", self.trendline_type)
        form.addRow("Order / period", self.trendline_order)
        form.addRow("Forecast forward", self.trendline_forward)
        form.addRow("Forecast backward", self.trendline_backward)
        form.addRow("Display equation", self.show_equation)
        form.addRow("Display R-squared", self.show_r_squared)
        form.addRow(_section("Lines and bars"))
        form.addRow("Lines", _row(self.drop_lines, self.high_low_lines))
        form.addRow("Bars", self.up_down_bars)
        form.addRow("Highlight minimum / maximum", self.highlight_extrema)
        return page

    def _format_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(_section("Style and colors"))
        form.addRow("Chart style (theme)", self.theme)
        form.addRow("Colors", self.color_scheme)
        form.addRow("Number style", self.number_format)
        form.addRow(_section("Value axis"))
        form.addRow("Minimum", self.axis_min)
        form.addRow("Maximum", self.axis_max)
        form.addRow("Major unit", self.major_unit)
        form.addRow("Logarithmic scale", self.log_scale)
        form.addRow("Display units", self.display_units)
        form.addRow("Categories in reverse order", self.reverse_categories)
        form.addRow(_section("Series"))
        form.addRow("Smoothed line", self.smooth_lines)
        form.addRow("Gap width", self.gap_width)
        form.addRow("Series overlap", self.series_overlap)
        form.addRow("Combo lines on secondary axis", self.secondary_axis)
        form.addRow(_section("Pie and doughnut"))
        form.addRow("Angle of first slice", self.first_slice_angle)
        form.addRow("Point explosion", self.pie_explosion)
        form.addRow("Doughnut hole size", self.hole_size)
        form.addRow("Values in second plot", self.split_count)
        form.addRow(_section("Histogram"))
        form.addRow("Number of bins", self.bin_count)
        return page

    def _data_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Data range", self.range_editor)
        form.addRow("First row contains headers", self.has_headers)
        form.addRow("Category column", self.category_editor)
        form.addRow("Series columns", self.series_editor)
        form.addRow("Switch row / column", self.switch_row_column)
        form.addRow("Show empty cells as", self.empty_cells)
        note = QLabel(
            "Leave category and series columns on Auto for smart detection. "
            "Column letters are absolute worksheet columns. Series columns "
            "also act as Excel's chart filter: list only the series to show."
        )
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow(_section("Custom combination"))
        form.addRow("Series chart types", self.combo_types_editor)
        form.addRow("Series on secondary axis", self.secondary_series_editor)
        return page

    # ------------------------------------------------------------------
    # Loading and syncing

    def _load_existing(self) -> None:
        if self.existing is None:
            return
        spec = self.existing
        self.chart_type.setCurrentText(spec.chart_type)
        self.title.setText(spec.title)
        self.x_axis.setText(spec.x_axis_title)
        self.y_axis.setText(spec.y_axis_title)
        self.legend.setCurrentText(spec.legend_position)
        self.theme.setCurrentText(spec.theme)
        self.number_format.setCurrentText(spec.number_format)
        self.has_headers.setChecked(spec.has_headers)
        self.show_labels.setChecked(spec.show_data_labels)
        self.show_trendline.setChecked(spec.show_trendline)
        self.highlight_extrema.setChecked(spec.highlight_extrema)
        self.show_grid.setChecked(spec.show_grid)
        self.secondary_axis.setChecked(spec.secondary_axis)
        if spec.category_column is not None:
            self.category_editor.setText(index_to_column(spec.category_column))
        if spec.series_columns is not None:
            self.series_editor.setText(
                ",".join(index_to_column(column) for column in spec.series_columns)
            )
        self.switch_row_column.setChecked(spec.switch_row_column)
        self.empty_cells.setCurrentText(spec.empty_cells)
        self.show_x_axis.setChecked(spec.show_x_axis)
        self.show_y_axis.setChecked(spec.show_y_axis)
        self.minor_gridlines.setChecked(spec.minor_gridlines)
        self.vertical_gridlines.setChecked(spec.vertical_gridlines)
        self.label_position.setCurrentText(spec.data_label_position)
        self.label_content.setCurrentText(spec.data_label_content)
        self.show_data_table.setChecked(spec.show_data_table)
        self.error_bars.setCurrentText(spec.error_bars)
        self.error_amount.setText(_number_text(spec.error_amount))
        self.trendline_type.setCurrentText(spec.trendline_type)
        self.trendline_order.setValue(spec.trendline_order)
        self.trendline_forward.setText(_number_text(spec.trendline_forward or None))
        self.trendline_backward.setText(_number_text(spec.trendline_backward or None))
        self.show_equation.setChecked(spec.show_equation)
        self.show_r_squared.setChecked(spec.show_r_squared)
        self.drop_lines.setChecked(spec.drop_lines)
        self.high_low_lines.setChecked(spec.high_low_lines)
        self.up_down_bars.setChecked(spec.up_down_bars)
        self.axis_min.setText(_number_text(spec.axis_min))
        self.axis_max.setText(_number_text(spec.axis_max))
        self.major_unit.setText(_number_text(spec.major_unit))
        self.log_scale.setChecked(spec.log_scale)
        self.reverse_categories.setChecked(spec.reverse_categories)
        self.display_units.setCurrentText(spec.display_units)
        self.color_scheme.setCurrentText(spec.color_scheme)
        self.smooth_lines.setChecked(spec.smooth_lines)
        self.gap_width.setValue(spec.gap_width)
        self.series_overlap.setValue(spec.series_overlap)
        self.hole_size.setValue(spec.hole_size)
        self.first_slice_angle.setValue(spec.first_slice_angle)
        self.pie_explosion.setValue(spec.pie_explosion)
        self.split_count.setValue(spec.split_count)
        self.bin_count.setValue(spec.bin_count or 0)
        if spec.combo_series_types is not None:
            self.combo_types_editor.setText(",".join(spec.combo_series_types))
        self.secondary_series_editor.setText(
            ",".join(str(number) for number in spec.secondary_series)
        )

    def _connect_updates(self) -> None:
        self.recommendation_list.currentRowChanged.connect(
            self._select_recommendation
        )
        self.gallery.currentItemChanged.connect(self._select_gallery_item)
        self.range_editor.editingFinished.connect(self._range_changed)
        self.chart_type.currentIndexChanged.connect(self._sync_gallery)
        combos = (
            self.chart_type,
            self.legend,
            self.theme,
            self.number_format,
            self.label_position,
            self.label_content,
            self.error_bars,
            self.trendline_type,
            self.display_units,
            self.color_scheme,
            self.empty_cells,
        )
        for combo in combos:
            combo.currentIndexChanged.connect(self._refresh_preview)
        editors = (
            self.title,
            self.x_axis,
            self.y_axis,
            self.category_editor,
            self.series_editor,
            self.error_amount,
            self.trendline_forward,
            self.trendline_backward,
            self.axis_min,
            self.axis_max,
            self.major_unit,
            self.combo_types_editor,
            self.secondary_series_editor,
        )
        for editor in editors:
            editor.editingFinished.connect(self._refresh_preview)
        checkboxes = (
            self.has_headers,
            self.show_labels,
            self.show_trendline,
            self.highlight_extrema,
            self.show_grid,
            self.secondary_axis,
            self.vertical_gridlines,
            self.minor_gridlines,
            self.show_x_axis,
            self.show_y_axis,
            self.show_data_table,
            self.show_equation,
            self.show_r_squared,
            self.drop_lines,
            self.high_low_lines,
            self.up_down_bars,
            self.log_scale,
            self.reverse_categories,
            self.smooth_lines,
            self.switch_row_column,
        )
        for checkbox in checkboxes:
            checkbox.stateChanged.connect(self._refresh_preview)
        spins = (
            self.trendline_order,
            self.gap_width,
            self.series_overlap,
            self.hole_size,
            self.first_slice_angle,
            self.pie_explosion,
            self.split_count,
            self.bin_count,
        )
        for spin in spins:
            spin.valueChanged.connect(self._refresh_preview)

    def _sync_gallery(self, *_: Any) -> None:
        key = self.chart_type.currentData()
        info = CHART_INFO.get(key)
        if info is None:
            return
        self.type_description.setText(
            f"<b>{info.label}</b> ({info.family})<br>{info.summary}"
            f"<br><br><b>Arrange your data:</b> {info.layout}"
        )
        iterator_items = [
            self.gallery.topLevelItem(index).child(child)
            for index in range(self.gallery.topLevelItemCount())
            for child in range(self.gallery.topLevelItem(index).childCount())
        ]
        for item in iterator_items:
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                if self.gallery.currentItem() is not item:
                    self.gallery.blockSignals(True)
                    self.gallery.setCurrentItem(item)
                    self.gallery.blockSignals(False)
                break

    def _select_gallery_item(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            return
        key = current.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.chart_type.setCurrentText(key)

    def show_help(self) -> None:
        """Open the charts tutorial at the lesson for the current type."""
        ChartHelpDialog(self, chart_type=self.chart_type.currentData()).exec()

    def _range_changed(self) -> None:
        self._refresh_recommendations()
        self._refresh_preview()

    def _refresh_recommendations(self) -> None:
        self.recommendation_list.clear()
        if self.workbook is None:
            item = QListWidgetItem("Clustered Column  |  reliable default")
            item.setData(Qt.ItemDataRole.UserRole, "column")
            self.recommendation_list.addItem(item)
            self.recommendation_list.setCurrentRow(0)
            return
        try:
            source_range = self._source_range()
            self._recommendations = recommend_charts(
                self.workbook,
                self.sheet_name,
                source_range,
                has_headers=self.has_headers.isChecked(),
            )
        except (KeyError, ValueError):
            self._recommendations = ()
        for recommendation in self._recommendations:
            item = QListWidgetItem(
                f"{CHART_TYPE_LABELS[recommendation.chart_type]}\n"
                f"{recommendation.score}% fit"
            )
            item.setData(
                Qt.ItemDataRole.UserRole,
                recommendation.chart_type,
            )
            self.recommendation_list.addItem(item)
        # Editing keeps the chart's own type; only new charts adopt the top
        # recommendation automatically.
        if self.recommendation_list.count() and self.existing is None:
            self.recommendation_list.setCurrentRow(0)

    def _select_recommendation(self, row: int) -> None:
        if row < 0:
            return
        item = self.recommendation_list.item(row)
        chart_type = item.data(Qt.ItemDataRole.UserRole)
        self.chart_type.setCurrentText(chart_type)
        if row < len(self._recommendations):
            recommendation = self._recommendations[row]
            self.recommendation_reason.setText(recommendation.reason)
            if not self.title.text():
                self.title.setText(recommendation.title)
        else:
            self.recommendation_reason.setText(
                "A clustered column chart is a dependable comparison view."
            )
        self._refresh_preview()

    def _source_range(self) -> RangeReference:
        source_range = parse_a1(
            self.range_editor.text(),
            default_sheet=self.sheet_name,
        )
        if not isinstance(source_range, RangeReference):
            raise ValueError("A chart requires a multi-cell range")
        return source_range

    # ------------------------------------------------------------------
    # Result

    def chart_spec(self) -> ChartSpec:
        """Build a validated immutable chart specification."""
        source_range = self._source_range()
        combo_text = self.combo_types_editor.text().strip()
        spec = ChartSpec(
            self.existing.chart_id if self.existing is not None else uuid4().hex,
            self.sheet_name,
            source_range,
            self.chart_type.currentData(),
            title=self.title.text(),
            x_axis_title=self.x_axis.text(),
            y_axis_title=self.y_axis.text(),
            legend_position=self.legend.currentText(),
            has_headers=self.has_headers.isChecked(),
            category_column=self._column_value(self.category_editor.text()),
            series_columns=self._series_values(self.series_editor.text()),
            theme=self.theme.currentText(),
            show_data_labels=self.show_labels.isChecked(),
            show_trendline=self.show_trendline.isChecked(),
            highlight_extrema=self.highlight_extrema.isChecked(),
            show_grid=self.show_grid.isChecked(),
            secondary_axis=self.secondary_axis.isChecked(),
            number_format=self.number_format.currentText(),
            switch_row_column=self.switch_row_column.isChecked(),
            empty_cells=self.empty_cells.currentData(),
            show_x_axis=self.show_x_axis.isChecked(),
            show_y_axis=self.show_y_axis.isChecked(),
            minor_gridlines=self.minor_gridlines.isChecked(),
            vertical_gridlines=self.vertical_gridlines.isChecked(),
            data_label_position=self.label_position.currentData(),
            data_label_content=self.label_content.currentData(),
            show_data_table=self.show_data_table.isChecked(),
            error_bars=self.error_bars.currentData(),
            error_amount=_optional_number(self.error_amount, "Error amount"),
            trendline_type=self.trendline_type.currentData(),
            trendline_order=self.trendline_order.value(),
            trendline_forward=_optional_number(self.trendline_forward, "Forecast forward") or 0.0,
            trendline_backward=_optional_number(self.trendline_backward, "Forecast backward") or 0.0,
            show_equation=self.show_equation.isChecked(),
            show_r_squared=self.show_r_squared.isChecked(),
            drop_lines=self.drop_lines.isChecked(),
            high_low_lines=self.high_low_lines.isChecked(),
            up_down_bars=self.up_down_bars.isChecked(),
            axis_min=_optional_number(self.axis_min, "Axis minimum"),
            axis_max=_optional_number(self.axis_max, "Axis maximum"),
            major_unit=_optional_number(self.major_unit, "Major unit"),
            log_scale=self.log_scale.isChecked(),
            reverse_categories=self.reverse_categories.isChecked(),
            display_units=self.display_units.currentData(),
            color_scheme=self.color_scheme.currentData(),
            smooth_lines=self.smooth_lines.isChecked(),
            gap_width=self.gap_width.value(),
            series_overlap=self.series_overlap.value(),
            hole_size=self.hole_size.value(),
            first_slice_angle=self.first_slice_angle.value(),
            pie_explosion=self.pie_explosion.value(),
            split_count=self.split_count.value(),
            bin_count=self.bin_count.value() or None,
            combo_series_types=(
                tuple(
                    item.strip().casefold()
                    for item in combo_text.split(",")
                    if item.strip()
                )
                if combo_text
                else None
            ),
            secondary_series=self._numbers(self.secondary_series_editor.text()),
        )
        if self.workbook is not None:
            chart_data(self.workbook, spec)
        return spec

    def _column_value(self, text: str) -> int | None:
        stripped = text.strip()
        return None if not stripped else column_to_index(stripped)

    def _series_values(self, text: str) -> tuple[int, ...] | None:
        stripped = text.strip()
        if not stripped:
            return None
        return tuple(
            column_to_index(item.strip())
            for item in stripped.split(",")
            if item.strip()
        )

    @staticmethod
    def _numbers(text: str) -> tuple[int, ...]:
        try:
            return tuple(int(item) for item in text.split(",") if item.strip())
        except ValueError as error:
            raise ValueError(
                "Secondary axis series must be numbers such as 2,3"
            ) from error

    def _refresh_preview(self, *_: Any) -> None:
        if self.workbook is None:
            return
        try:
            spec = self.chart_spec()
            if not spec.title:
                spec = replace(
                    spec,
                    title=infer_chart_title(chart_data(self.workbook, spec)),
                )
            draw_chart(self.preview_figure, self.workbook, spec)
        except (KeyError, TypeError, ValueError) as error:
            self.preview_figure.clear()
            axes = self.preview_figure.add_subplot(111)
            axes.text(
                0.5,
                0.5,
                str(error),
                ha="center",
                va="center",
                wrap=True,
                transform=axes.transAxes,
            )
            axes.set_axis_off()
        self.preview_canvas.draw_idle()


def _scrolling(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    return area


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionLabel")
    return label


def _row(*widgets: QWidget) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return container


def _spin(low: int, high: int, value: int, suffix: str) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    spin.setSuffix(suffix)
    return spin


def _optional_number(editor: QLineEdit, name: str) -> float | None:
    text = editor.text().strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error


def _number_text(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"
