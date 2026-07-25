"""Matplotlib Qt chart panel and shared chart renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from excelclone.core.chart import ChartData, ChartSpec, chart_data
from excelclone.core.workbook import Workbook


class ChartPanel(QDockWidget):
    """Movable/resizable chart panel with live refresh and PNG export."""

    closeRequested = Signal(str)

    def __init__(
        self,
        workbook: Workbook,
        spec: ChartSpec,
        parent: Any = None,
    ) -> None:
        super().__init__(spec.title or "Chart", parent)
        self.setObjectName(f"chart-{spec.chart_id}")
        self.workbook = workbook
        self.spec = spec
        self.figure = Figure(figsize=(6.4, 4.2), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        export_button = QPushButton("Export PNG")
        export_button.clicked.connect(self.choose_export_path)
        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(export_button)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, 1)
        self.setWidget(content)
        self.setMinimumSize(360, 260)
        self.resize(640, 420)
        self.refresh()

    def refresh(self) -> None:
        """Redraw from current workbook cached values."""
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        render_chart(axes, chart_data(self.workbook, self.spec), self.spec)
        self.canvas.draw_idle()

    def choose_export_path(self) -> None:
        """Prompt for a PNG destination."""
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chart",
            f"{self.spec.title or 'chart'}.png",
            "PNG Image (*.png)",
        )
        if selected:
            self.export_png(selected)

    def export_png(self, path: str | Path) -> Path:
        """Export the current chart at print-quality resolution."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.figure.savefig(destination, format="png", dpi=160)
        return destination

    def closeEvent(self, event: Any) -> None:
        self.closeRequested.emit(self.spec.chart_id)
        super().closeEvent(event)


def render_chart(axes: Any, data: ChartData, spec: ChartSpec) -> None:
    """Render prepared chart data on a matplotlib Axes."""
    categories = [str(value) for value in data.categories]
    positions = list(range(len(categories)))
    chart_type = spec.chart_type
    if chart_type == "column":
        _grouped_bars(axes, positions, data, horizontal=False)
    elif chart_type == "bar":
        _grouped_bars(axes, positions, data, horizontal=True)
    elif chart_type == "line":
        for series in data.series:
            axes.plot(positions, series.values, marker="o", label=series.name)
    elif chart_type == "pie":
        if data.series:
            axes.pie(
                data.series[0].values,
                labels=categories,
                autopct="%1.1f%%",
            )
            axes.set_aspect("equal")
    elif chart_type == "scatter":
        x_values = [
            float(value) if isinstance(value, (int, float)) else float(index)
            for index, value in enumerate(data.categories)
        ]
        for series in data.series:
            axes.scatter(x_values, series.values, label=series.name)
    elif chart_type == "area":
        for series in data.series:
            axes.fill_between(
                positions,
                series.values,
                alpha=0.45,
                label=series.name,
            )
    elif chart_type == "combo":
        if data.series:
            axes.bar(
                positions,
                data.series[0].values,
                alpha=0.75,
                label=data.series[0].name,
            )
        for series in data.series[1:]:
            axes.plot(positions, series.values, marker="o", label=series.name)

    if chart_type not in ("pie", "bar", "scatter"):
        axes.set_xticks(positions, categories)
    if chart_type == "bar":
        axes.set_yticks(positions, categories)
    axes.set_title(spec.title)
    axes.set_xlabel(spec.x_axis_title)
    axes.set_ylabel(spec.y_axis_title)
    if chart_type == "pie":
        axes.grid(False)
    else:
        axes.grid(True, axis="y", alpha=0.22)
    if spec.legend_position != "none" and len(data.series) > 1:
        legend_locations = {
            "right": "center left",
            "left": "center right",
            "top": "lower center",
            "bottom": "upper center",
        }
        location = legend_locations[spec.legend_position]
        anchor = {
            "right": (1.02, 0.5),
            "left": (-0.02, 0.5),
            "top": (0.5, 1.02),
            "bottom": (0.5, -0.12),
        }[spec.legend_position]
        axes.legend(loc=location, bbox_to_anchor=anchor)


def _grouped_bars(
    axes: Any,
    positions: list[int],
    data: ChartData,
    *,
    horizontal: bool,
) -> None:
    count = max(1, len(data.series))
    width = 0.8 / count
    for index, series in enumerate(data.series):
        shifted = [
            position - 0.4 + width / 2 + index * width
            for position in positions
        ]
        if horizontal:
            axes.barh(shifted, series.values, height=width, label=series.name)
        else:
            axes.bar(shifted, series.values, width=width, label=series.name)
