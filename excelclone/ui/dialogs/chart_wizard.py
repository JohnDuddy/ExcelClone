"""Live-preview chart studio with recommendations and detailed controls."""

from __future__ import annotations

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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from excelclone.core.chart import (
    CHART_THEMES,
    CHART_TYPE_LABELS,
    CHART_TYPES,
    NUMBER_FORMATS,
    ChartSpec,
    chart_data,
    detect_chart_headers,
    infer_chart_title,
    recommend_charts,
)
from excelclone.core.refs import (
    RangeReference,
    column_to_index,
    index_to_column,
    parse_a1,
)
from excelclone.core.workbook import Workbook
from excelclone.ui.charting import render_chart


class _ChartTypeCombo(QComboBox):
    """Display friendly labels while accepting stable chart type keys in tests."""

    def setCurrentText(self, text: str) -> None:
        index = self.findData(text)
        if index >= 0:
            self.setCurrentIndex(index)
            return
        super().setCurrentText(text)


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
    ) -> None:
        super().__init__(parent)
        self.sheet_name = sheet_name
        self.workbook = workbook
        self.existing = existing
        self._recommendations = ()
        self.setWindowTitle("Chart Studio")
        self.resize(1060, 680)

        self.range_editor = QLineEdit(range_text)
        self.chart_type = _ChartTypeCombo()
        for chart_type in sorted(CHART_TYPES):
            self.chart_type.addItem(CHART_TYPE_LABELS[chart_type], chart_type)
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
        self.show_grid = QCheckBox()
        self.show_grid.setChecked(True)
        self.show_labels = QCheckBox()
        self.show_trendline = QCheckBox()
        self.highlight_extrema = QCheckBox()
        self.secondary_axis = QCheckBox()
        self.category_editor = QLineEdit()
        self.category_editor.setPlaceholderText("Auto or column letter, e.g. A")
        self.series_editor = QLineEdit()
        self.series_editor.setPlaceholderText("Auto or columns, e.g. B,C,D")

        self.recommendation_list = QListWidget()
        self.recommendation_list.setMinimumHeight(180)
        self.recommendation_reason = QLabel(
            "Select a recommendation to see why it fits."
        )
        self.recommendation_reason.setWordWrap(True)
        self.recommendation_reason.setObjectName("recommendationReason")

        tabs = QTabWidget()
        tabs.addTab(self._recommended_tab(), "Recommended")
        tabs.addTab(self._design_tab(), "Design")
        tabs.addTab(self._data_tab(), "Data")
        tabs.setMinimumWidth(360)
        tabs.setMaximumWidth(430)

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
        body.addWidget(tabs)
        body.addWidget(preview, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Update Chart" if existing is not None else "Create Chart"
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
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
            QListWidget { border: 0; background: #fffdf8; font-size: 13px; }
            QListWidget::item { padding: 10px; margin: 2px; }
            QListWidget::item:selected { background: #0b6e75; color: white; }
            #recommendationReason {
                background: #e7f0ed; color: #183832; padding: 10px;
                border-left: 4px solid #0b6e75;
            }
            #previewLabel {
                color: #0b6e75; font-weight: 700; letter-spacing: 2px;
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
        self._refresh_preview()

    def _recommended_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "Ranked from the shape and meaning of the selected data. "
            "Choose one, then refine it in Design."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self.recommendation_list)
        layout.addWidget(self.recommendation_reason)
        layout.addStretch(1)
        return page

    def _design_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Chart type", self.chart_type)
        form.addRow("Title", self.title)
        form.addRow("Horizontal axis", self.x_axis)
        form.addRow("Vertical axis", self.y_axis)
        form.addRow("Theme", self.theme)
        form.addRow("Number style", self.number_format)
        form.addRow("Legend", self.legend)
        form.addRow("Show data labels", self.show_labels)
        form.addRow("Show trendline", self.show_trendline)
        form.addRow("Highlight minimum / maximum", self.highlight_extrema)
        form.addRow("Show grid", self.show_grid)
        form.addRow("Combo lines on secondary axis", self.secondary_axis)
        return page

    def _data_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Data range", self.range_editor)
        form.addRow("First row contains headers", self.has_headers)
        form.addRow("Category column", self.category_editor)
        form.addRow("Series columns", self.series_editor)
        note = QLabel(
            "Leave category and series columns on Auto for smart detection. "
            "Column letters are absolute worksheet columns."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return page

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

    def _connect_updates(self) -> None:
        self.recommendation_list.currentRowChanged.connect(
            self._select_recommendation
        )
        self.range_editor.editingFinished.connect(self._range_changed)
        self.chart_type.currentIndexChanged.connect(self._refresh_preview)
        self.legend.currentIndexChanged.connect(self._refresh_preview)
        self.theme.currentIndexChanged.connect(self._refresh_preview)
        self.number_format.currentIndexChanged.connect(self._refresh_preview)
        for editor in (
            self.title,
            self.x_axis,
            self.y_axis,
            self.category_editor,
            self.series_editor,
        ):
            editor.editingFinished.connect(self._refresh_preview)
        for checkbox in (
            self.has_headers,
            self.show_labels,
            self.show_trendline,
            self.highlight_extrema,
            self.show_grid,
            self.secondary_axis,
        ):
            checkbox.stateChanged.connect(self._refresh_preview)

    def _range_changed(self) -> None:
        self._refresh_recommendations()
        self._refresh_preview()

    def _refresh_recommendations(self) -> None:
        self.recommendation_list.clear()
        if self.workbook is None:
            item = QListWidgetItem("Clustered Columns  |  reliable default")
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
        if self.recommendation_list.count():
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

    def chart_spec(self) -> ChartSpec:
        """Build a validated immutable chart specification."""
        source_range = self._source_range()
        category_column = self._column_value(self.category_editor.text())
        series_columns = self._series_values(self.series_editor.text())
        spec = ChartSpec(
            self.existing.chart_id if self.existing is not None else uuid4().hex,
            self.sheet_name,
            source_range,
            self.chart_type.currentData(),
            self.title.text(),
            self.x_axis.text(),
            self.y_axis.text(),
            self.legend.currentText(),
            self.has_headers.isChecked(),
            category_column,
            series_columns,
            self.theme.currentText(),
            self.show_labels.isChecked(),
            self.show_trendline.isChecked(),
            self.highlight_extrema.isChecked(),
            self.show_grid.isChecked(),
            self.secondary_axis.isChecked(),
            self.number_format.currentText(),
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

    def _refresh_preview(self, *_: Any) -> None:
        if self.workbook is None:
            return
        self.preview_figure.clear()
        projection = (
            "polar"
            if self.chart_type.currentData() == "radar"
            else None
        )
        axes = self.preview_figure.add_subplot(111, projection=projection)
        try:
            spec = self.chart_spec()
            if not spec.title:
                spec = ChartSpec(
                    spec.chart_id,
                    spec.sheet_name,
                    spec.source_range,
                    spec.chart_type,
                    infer_chart_title(chart_data(self.workbook, spec)),
                    spec.x_axis_title,
                    spec.y_axis_title,
                    spec.legend_position,
                    spec.has_headers,
                    spec.category_column,
                    spec.series_columns,
                    spec.theme,
                    spec.show_data_labels,
                    spec.show_trendline,
                    spec.highlight_extrema,
                    spec.show_grid,
                    spec.secondary_axis,
                    spec.number_format,
                )
            render_chart(axes, chart_data(self.workbook, spec), spec)
        except (KeyError, TypeError, ValueError) as error:
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
