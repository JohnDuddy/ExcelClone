"""Interactive Matplotlib chart panel and professional shared renderer."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from excelclone.core.chart import ChartData, ChartSpec, chart_data
from excelclone.core.workbook import Workbook

THEMES = {
    "executive": {
        "background": "#fbfaf6",
        "plot": "#ffffff",
        "text": "#17212b",
        "grid": "#d8ddd9",
        "palette": ("#0b6e75", "#e76f51", "#e9b949", "#2a6fbb", "#6a4c93"),
        "accent": "#b42318",
    },
    "coastal": {
        "background": "#f3faf8",
        "plot": "#ffffff",
        "text": "#163832",
        "grid": "#cfe3de",
        "palette": ("#007f86", "#49a078", "#f2b134", "#d95d39", "#335c81"),
        "accent": "#c44536",
    },
    "editorial": {
        "background": "#f7f4ee",
        "plot": "#fffdf8",
        "text": "#181818",
        "grid": "#d9d2c4",
        "palette": ("#111111", "#d1495b", "#2d5d7b", "#edae49", "#5f6f52"),
        "accent": "#d1495b",
    },
    "monochrome": {
        "background": "#f5f5f3",
        "plot": "#ffffff",
        "text": "#202020",
        "grid": "#d7d7d2",
        "palette": ("#222222", "#555555", "#777777", "#999999", "#bbbbbb"),
        "accent": "#000000",
    },
    "high_contrast": {
        "background": "#ffffff",
        "plot": "#ffffff",
        "text": "#000000",
        "grid": "#b8b8b8",
        "palette": ("#0057b8", "#d00000", "#008450", "#f6c700", "#6f2da8"),
        "accent": "#d00000",
    },
}


class ChartPanel(QDockWidget):
    """Movable chart studio panel with live refresh, editing, and export."""

    closeRequested = Signal(str)
    editRequested = Signal(str)

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
        self.figure = Figure(figsize=(7.4, 4.8), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigation = NavigationToolbar2QT(self.canvas, self)
        self.navigation.setIconSize(self.navigation.iconSize() * 0.8)
        self.summary = QLabel()
        self.summary.setObjectName("chartSummary")
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(
            lambda: self.editRequested.emit(self.spec.chart_id)
        )
        copy_button = QPushButton("Copy Image")
        copy_button.clicked.connect(self.copy_image)
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.choose_export_path)
        controls = QHBoxLayout()
        controls.addWidget(self.summary)
        controls.addStretch(1)
        controls.addWidget(edit_button)
        controls.addWidget(copy_button)
        controls.addWidget(export_button)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(controls)
        layout.addWidget(self.navigation)
        layout.addWidget(self.canvas, 1)
        self.setWidget(content)
        self.setMinimumSize(420, 300)
        self.resize(760, 500)
        self.refresh()

    def refresh(self) -> None:
        """Redraw from current workbook cached values."""
        self.figure.clear()
        projection = "polar" if self.spec.chart_type == "radar" else None
        axes = self.figure.add_subplot(111, projection=projection)
        data = chart_data(self.workbook, self.spec)
        render_chart(axes, data, self.spec)
        point_count = sum(len(series.values) for series in data.series)
        self.summary.setText(
            f"{len(data.series)} series  |  {point_count} live values"
        )
        self.setWindowTitle(self.spec.title or "Chart")
        self.canvas.draw_idle()

    def choose_export_path(self) -> None:
        """Prompt for a PNG, SVG, or PDF destination."""
        selected, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Chart",
            f"{self.spec.title or 'chart'}.png",
            "PNG Image (*.png);;SVG Vector (*.svg);;PDF Document (*.pdf)",
        )
        if not selected:
            return
        destination = Path(selected)
        if not destination.suffix:
            suffixes = {
                "SVG Vector (*.svg)": ".svg",
                "PDF Document (*.pdf)": ".pdf",
            }
            destination = destination.with_suffix(
                suffixes.get(selected_filter, ".png")
            )
        self.export(destination)

    def export(self, path: str | Path) -> Path:
        """Export based on the destination suffix."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        suffix = destination.suffix.lower()
        if suffix not in {".png", ".svg", ".pdf"}:
            raise ValueError("Charts can be exported as PNG, SVG, or PDF")
        self.figure.savefig(
            destination,
            format=suffix[1:],
            dpi=180 if suffix == ".png" else None,
            facecolor=self.figure.get_facecolor(),
        )
        return destination

    def export_png(self, path: str | Path) -> Path:
        """Retain the direct PNG export API."""
        destination = Path(path)
        if destination.suffix.lower() != ".png":
            destination = destination.with_suffix(".png")
        return self.export(destination)

    def copy_image(self) -> None:
        """Copy the rendered chart to the system clipboard."""
        QApplication.clipboard().setPixmap(self.canvas.grab())

    def closeEvent(self, event: Any) -> None:
        self.closeRequested.emit(self.spec.chart_id)
        super().closeEvent(event)


def render_chart(axes: Any, data: ChartData, spec: ChartSpec) -> None:
    """Render prepared chart data with consistent analytical styling."""
    theme = THEMES[spec.theme]
    palette = theme["palette"]
    figure = axes.figure
    figure.set_facecolor(theme["background"])
    axes.set_facecolor(theme["plot"])
    axes.tick_params(colors=theme["text"], labelsize=9)
    for spine in axes.spines.values():
        spine.set_color(theme["grid"])

    categories = [str(value) for value in data.categories]
    positions = np.arange(len(categories), dtype=float)
    chart_type = spec.chart_type
    secondary_axes = None

    if not data.series or not categories:
        axes.text(
            0.5,
            0.5,
            "No plottable data",
            ha="center",
            va="center",
            transform=axes.transAxes,
            color=theme["text"],
        )
    elif chart_type == "column":
        _grouped_bars(axes, positions, data, palette, horizontal=False)
    elif chart_type == "bar":
        _grouped_bars(axes, positions, data, palette, horizontal=True)
    elif chart_type == "stacked_column":
        _stacked_bars(axes, positions, data, palette, horizontal=False)
    elif chart_type == "stacked_bar":
        _stacked_bars(axes, positions, data, palette, horizontal=True)
    elif chart_type in {"line", "step"}:
        for index, series in enumerate(data.series):
            values = np.asarray(series.values, dtype=float)
            if chart_type == "step":
                axes.step(
                    positions,
                    values,
                    where="mid",
                    linewidth=2.2,
                    label=series.name,
                    color=palette[index % len(palette)],
                )
            else:
                axes.plot(
                    positions,
                    values,
                    marker="o",
                    markersize=4.5,
                    linewidth=2.2,
                    label=series.name,
                    color=palette[index % len(palette)],
                )
    elif chart_type in {"area", "stacked_area"}:
        values = [
            np.nan_to_num(np.asarray(series.values, dtype=float))
            for series in data.series
        ]
        if chart_type == "stacked_area":
            axes.stackplot(
                positions,
                values,
                labels=[series.name for series in data.series],
                colors=palette[: len(values)],
                alpha=0.82,
            )
        else:
            for index, (series, series_values) in enumerate(
                zip(data.series, values)
            ):
                axes.fill_between(
                    positions,
                    series_values,
                    alpha=0.34,
                    label=series.name,
                    color=palette[index % len(palette)],
                )
                axes.plot(
                    positions,
                    series_values,
                    linewidth=1.8,
                    color=palette[index % len(palette)],
                )
    elif chart_type in {"pie", "donut"}:
        values = np.maximum(
            0,
            np.nan_to_num(np.asarray(data.series[0].values, dtype=float)),
        )
        if np.any(values):
            axes.pie(
                values,
                labels=categories,
                autopct="%1.1f%%" if spec.show_data_labels else None,
                startangle=90,
                colors=palette,
                wedgeprops=(
                    {"width": 0.42, "edgecolor": theme["plot"]}
                    if chart_type == "donut"
                    else {"edgecolor": theme["plot"]}
                ),
            )
            axes.set_aspect("equal")
    elif chart_type == "scatter":
        x_values = _numeric_categories(data)
        for index, series in enumerate(data.series):
            axes.scatter(
                x_values,
                series.values,
                s=46,
                alpha=0.82,
                label=series.name,
                color=palette[index % len(palette)],
                edgecolors=theme["plot"],
                linewidths=0.7,
            )
    elif chart_type == "histogram":
        for index, series in enumerate(data.series):
            values = _finite(series.values)
            if values:
                axes.hist(
                    values,
                    bins="auto",
                    alpha=0.62,
                    label=series.name,
                    color=palette[index % len(palette)],
                    edgecolor=theme["plot"],
                )
    elif chart_type == "box":
        values = [_finite(series.values) for series in data.series]
        usable = [
            (series.name, series_values)
            for series, series_values in zip(data.series, values)
            if series_values
        ]
        if usable:
            box = axes.boxplot(
                [values for _, values in usable],
                tick_labels=[name for name, _ in usable],
                patch_artist=True,
                showmeans=True,
            )
            for index, patch in enumerate(box["boxes"]):
                patch.set_facecolor(palette[index % len(palette)])
                patch.set_alpha(0.68)
    elif chart_type == "waterfall":
        values = np.nan_to_num(np.asarray(data.series[0].values, dtype=float))
        starts = np.concatenate(([0.0], np.cumsum(values)[:-1]))
        colors = [
            palette[0] if value >= 0 else theme["accent"] for value in values
        ]
        axes.bar(
            positions,
            values,
            bottom=starts,
            color=colors,
            edgecolor=theme["plot"],
        )
        axes.plot(
            positions,
            np.cumsum(values),
            color=theme["text"],
            linewidth=1,
            alpha=0.55,
        )
    elif chart_type == "heatmap":
        matrix = np.asarray(
            [
                np.nan_to_num(np.asarray(series.values, dtype=float))
                for series in data.series
            ]
        )
        image = axes.imshow(matrix, aspect="auto", cmap="YlGnBu")
        axes.set_yticks(
            np.arange(len(data.series)),
            [series.name for series in data.series],
        )
        axes.set_xticks(positions, categories)
        if spec.show_data_labels and matrix.size <= 120:
            for row in range(matrix.shape[0]):
                for column in range(matrix.shape[1]):
                    axes.text(
                        column,
                        row,
                        _format_value(matrix[row, column], spec.number_format),
                        ha="center",
                        va="center",
                        fontsize=8,
                    )
        figure.colorbar(image, ax=axes, shrink=0.78, pad=0.02)
    elif chart_type == "radar":
        angles = np.linspace(0, 2 * math.pi, len(categories), endpoint=False)
        closed_angles = np.concatenate((angles, angles[:1]))
        for index, series in enumerate(data.series):
            values = np.nan_to_num(np.asarray(series.values, dtype=float))
            closed_values = np.concatenate((values, values[:1]))
            color = palette[index % len(palette)]
            axes.plot(
                closed_angles,
                closed_values,
                linewidth=2,
                label=series.name,
                color=color,
            )
            axes.fill(closed_angles, closed_values, alpha=0.12, color=color)
        axes.set_xticks(angles, categories)
        axes.set_theta_offset(math.pi / 2)
        axes.set_theta_direction(-1)
    elif chart_type == "combo":
        first = data.series[0]
        axes.bar(
            positions,
            first.values,
            alpha=0.78,
            label=first.name,
            color=palette[0],
        )
        target_axes = axes
        if spec.secondary_axis and len(data.series) > 1:
            secondary_axes = axes.twinx()
            target_axes = secondary_axes
            target_axes.set_facecolor("none")
        for index, series in enumerate(data.series[1:], start=1):
            target_axes.plot(
                positions,
                series.values,
                marker="o",
                linewidth=2.2,
                label=series.name,
                color=palette[index % len(palette)],
            )

    if spec.show_trendline and chart_type in {"line", "step", "scatter"}:
        _add_trendlines(axes, data, palette, chart_type)
    if spec.highlight_extrema and chart_type in {
        "column",
        "line",
        "step",
        "scatter",
    }:
        _highlight_extrema(axes, data, positions, theme["accent"])

    if chart_type not in {
        "bar",
        "box",
        "heatmap",
        "histogram",
        "pie",
        "donut",
        "radar",
        "scatter",
        "stacked_bar",
    }:
        axes.set_xticks(positions, categories)
    if chart_type in {"bar", "stacked_bar"}:
        axes.set_yticks(positions, categories)
    if len(categories) > 8 and chart_type not in {
        "bar",
        "box",
        "histogram",
        "pie",
        "donut",
        "radar",
        "stacked_bar",
    }:
        axes.tick_params(axis="x", rotation=35)

    axes.set_title(
        spec.title,
        loc="left",
        color=theme["text"],
        fontsize=15,
        fontweight="bold",
        pad=12,
    )
    if chart_type != "radar":
        axes.set_xlabel(spec.x_axis_title, color=theme["text"])
        axes.set_ylabel(spec.y_axis_title, color=theme["text"])
    if secondary_axes is not None:
        secondary_axes.tick_params(colors=theme["text"])
    formatter = FuncFormatter(
        lambda value, _: _format_value(value, spec.number_format)
    )
    if chart_type not in {"pie", "donut", "radar", "heatmap"}:
        if chart_type in {"bar", "stacked_bar"}:
            axes.xaxis.set_major_formatter(formatter)
        else:
            axes.yaxis.set_major_formatter(formatter)
            if secondary_axes is not None:
                secondary_axes.yaxis.set_major_formatter(formatter)

    if spec.show_data_labels and chart_type not in {
        "heatmap",
        "pie",
        "donut",
        "radar",
        "scatter",
    }:
        _add_data_labels(axes, spec.number_format)
    if spec.show_data_labels and chart_type in {"line", "step", "scatter"}:
        label_positions = (
            _numeric_categories(data)
            if chart_type == "scatter"
            else positions
        )
        _add_point_labels(axes, data, label_positions, spec.number_format)
    if chart_type == "radar":
        axes.grid(spec.show_grid, alpha=0.22)
    elif chart_type in {"pie", "donut"}:
        axes.grid(False)
    elif spec.show_grid:
        grid_axis = "x" if chart_type in {"bar", "stacked_bar"} else "y"
        axes.grid(True, axis=grid_axis, color=theme["grid"], alpha=0.7)
        axes.set_axisbelow(True)
    else:
        axes.grid(False)
    _place_legend(axes, secondary_axes, spec)


def _grouped_bars(
    axes: Any,
    positions: np.ndarray,
    data: ChartData,
    palette: tuple[str, ...],
    *,
    horizontal: bool,
) -> None:
    count = max(1, len(data.series))
    width = 0.82 / count
    for index, series in enumerate(data.series):
        shifted = positions - 0.41 + width / 2 + index * width
        values = np.nan_to_num(np.asarray(series.values, dtype=float))
        if horizontal:
            axes.barh(
                shifted,
                values,
                height=width,
                label=series.name,
                color=palette[index % len(palette)],
            )
        else:
            axes.bar(
                shifted,
                values,
                width=width,
                label=series.name,
                color=palette[index % len(palette)],
            )


def _stacked_bars(
    axes: Any,
    positions: np.ndarray,
    data: ChartData,
    palette: tuple[str, ...],
    *,
    horizontal: bool,
) -> None:
    positive = np.zeros(len(positions))
    negative = np.zeros(len(positions))
    for index, series in enumerate(data.series):
        values = np.nan_to_num(np.asarray(series.values, dtype=float))
        base = np.where(values >= 0, positive, negative)
        if horizontal:
            axes.barh(
                positions,
                values,
                left=base,
                label=series.name,
                color=palette[index % len(palette)],
            )
        else:
            axes.bar(
                positions,
                values,
                bottom=base,
                label=series.name,
                color=palette[index % len(palette)],
            )
        positive += np.where(values >= 0, values, 0)
        negative += np.where(values < 0, values, 0)


def _numeric_categories(data: ChartData) -> np.ndarray:
    values = []
    for index, value in enumerate(data.categories):
        values.append(
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else float(index)
        )
    return np.asarray(values)


def _finite(values: tuple[float, ...]) -> list[float]:
    return [float(value) for value in values if math.isfinite(value)]


def _add_trendlines(
    axes: Any,
    data: ChartData,
    palette: tuple[str, ...],
    chart_type: str,
) -> None:
    x_values = (
        _numeric_categories(data)
        if chart_type == "scatter"
        else np.arange(len(data.categories), dtype=float)
    )
    for index, series in enumerate(data.series):
        y_values = np.asarray(series.values, dtype=float)
        valid = np.isfinite(x_values) & np.isfinite(y_values)
        if np.count_nonzero(valid) < 2:
            continue
        coefficient = np.polyfit(x_values[valid], y_values[valid], 1)
        trend = np.polyval(coefficient, x_values)
        axes.plot(
            x_values,
            trend,
            linestyle="--",
            linewidth=1.4,
            alpha=0.75,
            color=palette[index % len(palette)],
            label=f"{series.name} trend",
        )


def _highlight_extrema(
    axes: Any,
    data: ChartData,
    positions: np.ndarray,
    accent: str,
) -> None:
    for series in data.series:
        values = np.asarray(series.values, dtype=float)
        valid = np.flatnonzero(np.isfinite(values))
        if not len(valid):
            continue
        minimum = valid[np.argmin(values[valid])]
        maximum = valid[np.argmax(values[valid])]
        axes.scatter(
            [positions[minimum], positions[maximum]],
            [values[minimum], values[maximum]],
            s=70,
            facecolors="none",
            edgecolors=accent,
            linewidths=1.8,
            zorder=5,
        )


def _add_data_labels(axes: Any, number_format: str) -> None:
    for container in axes.containers:
        if not hasattr(container, "datavalues"):
            continue
        labels = [
            _format_value(value, number_format)
            if math.isfinite(float(value))
            else ""
            for value in container.datavalues
        ]
        axes.bar_label(container, labels=labels, fontsize=8, padding=2)


def _add_point_labels(
    axes: Any,
    data: ChartData,
    x_values: np.ndarray,
    number_format: str,
) -> None:
    if len(x_values) * len(data.series) > 60:
        return
    for series in data.series:
        for x_value, y_value in zip(x_values, series.values):
            if not math.isfinite(y_value):
                continue
            axes.annotate(
                _format_value(y_value, number_format),
                (x_value, y_value),
                xytext=(0, 6),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
            )


def _format_value(value: float, number_format: str) -> str:
    if number_format == "currency":
        return f"${value:,.0f}"
    if number_format == "percent":
        return f"{value:.1%}"
    if number_format == "number":
        return f"{value:,.2f}"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _place_legend(axes: Any, secondary_axes: Any, spec: ChartSpec) -> None:
    if spec.legend_position == "none":
        return
    handles, labels = axes.get_legend_handles_labels()
    if secondary_axes is not None:
        extra_handles, extra_labels = secondary_axes.get_legend_handles_labels()
        handles += extra_handles
        labels += extra_labels
    if len(labels) <= 1:
        return
    legend_locations = {
        "right": ("center left", (1.02, 0.5)),
        "left": ("center right", (-0.02, 0.5)),
        "top": ("lower center", (0.5, 1.02)),
        "bottom": ("upper center", (0.5, -0.14)),
    }
    location, anchor = legend_locations[spec.legend_position]
    axes.legend(
        handles,
        labels,
        loc=location,
        bbox_to_anchor=anchor,
        frameon=False,
        ncols=2 if spec.legend_position in {"top", "bottom"} else 1,
    )
