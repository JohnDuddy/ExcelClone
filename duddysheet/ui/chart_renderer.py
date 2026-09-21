"""Matplotlib renderer for every chart type and chart element.

Rendering is split by chart family. Each family draws its marks; the shared
finishing pass then applies Excel's chart elements (axes, gridlines, data
labels, data table, error bars, trendlines, drop and high-low lines, up/down
bars), axis formatting, titles, and the legend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import ConnectionPatch, Rectangle, Wedge
from matplotlib.ticker import FuncFormatter, MultipleLocator

from duddysheet.core.chart import (
    DISPLAY_UNITS,
    POLAR_TYPES,
    STOCK_COLUMNS,
    THREE_D_TYPES,
    ChartData,
    ChartSeries,
    ChartSpec,
    HierarchyNode,
    bubble_series,
    chart_data,
    error_bar_amounts,
    fit_trendline,
    hierarchy_data,
    moving_average,
    pareto_data,
    percent_stack,
    squarify,
)
from duddysheet.core.workbook import Workbook

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

# Excel's Change Colors gallery: one colorful set and monochromatic ramps.
COLOR_SCHEME_PALETTES = {
    "colorful": ("#4472c4", "#ed7d31", "#a5a5a5", "#ffc000", "#5b9bd5", "#70ad47"),
    "blue": ("#1f3b73", "#2f5597", "#4472c4", "#8faadc", "#b4c7e7", "#dae3f3"),
    "orange": ("#843c0c", "#c55a11", "#ed7d31", "#f4b183", "#f8cbad", "#fbe5d6"),
    "green": ("#385723", "#548235", "#70ad47", "#a9d18e", "#c5e0b4", "#e2f0d9"),
    "purple": ("#3f2a56", "#5b3f7d", "#7e5ca8", "#a58cc8", "#c7b8df", "#e4dcf0"),
    "gray": ("#262626", "#595959", "#7f7f7f", "#a6a6a6", "#bfbfbf", "#d9d9d9"),
}

HIERARCHY_TYPES = frozenset({"treemap", "sunburst"})
_COLUMN_TYPES = {
    "column": "clustered",
    "stacked_column": "stacked",
    "stacked_column_100": "percent",
}
_BAR_TYPES = {
    "bar": "clustered",
    "stacked_bar": "stacked",
    "stacked_bar_100": "percent",
}
_LINE_TYPES = {
    "line_plain": ("clustered", False),
    "stacked_line": ("stacked", False),
    "stacked_line_100": ("percent", False),
    "line": ("clustered", True),
    "stacked_line_markers": ("stacked", True),
    "stacked_line_100_markers": ("percent", True),
}
_AREA_TYPES = {
    "area": "clustered",
    "stacked_area": "stacked",
    "stacked_area_100": "percent",
}
_SCATTER_TYPES = {
    "scatter": (False, False, True),
    "scatter_smooth_markers": (True, True, True),
    "scatter_smooth": (True, True, False),
    "scatter_lines_markers": (True, False, True),
    "scatter_lines": (True, False, False),
}
_THREE_D_BARS = {
    "column_3d_clustered": (False, "clustered"),
    "column_3d_stacked": (False, "stacked"),
    "column_3d_stacked_100": (False, "percent"),
    "column_3d": (False, "depth"),
    "bar_3d_clustered": (True, "clustered"),
    "bar_3d_stacked": (True, "stacked"),
    "bar_3d_stacked_100": (True, "percent"),
}
_THREE_D_AREAS = {
    "area_3d": "depth",
    "area_3d_stacked": "stacked",
    "area_3d_stacked_100": "percent",
}
_COMBO_TYPES = frozenset(
    {"combo", "combo_secondary", "combo_area_column", "combo_custom"}
)
# Families whose horizontal axis is the category axis and vertical the value.
_VERTICAL_CATEGORY = (
    set(_COLUMN_TYPES)
    | set(_LINE_TYPES)
    | set(_AREA_TYPES)
    | set(STOCK_COLUMNS)
    | _COMBO_TYPES
    | {"step", "waterfall", "pareto"}
)
_HORIZONTAL_CATEGORY = set(_BAR_TYPES)
_XY_TYPES = set(_SCATTER_TYPES) | {"bubble", "bubble_3d"}
_VALUE_AXIS_TYPES = (
    _VERTICAL_CATEGORY | _HORIZONTAL_CATEGORY | _XY_TYPES | {"histogram", "box"}
)
_TRENDLINE_TYPES = (
    {"column", "line", "line_plain", "step", "area"}
    | _XY_TYPES
)
_ERROR_BAR_TYPES = (
    {"column", "bar", "line", "line_plain", "step", "area"} | _XY_TYPES
)
_LINE_ELEMENT_TYPES = set(_LINE_TYPES) | {"step"}
_DATA_TABLE_TYPES = (
    set(_COLUMN_TYPES)
    | set(_LINE_TYPES)
    | set(_AREA_TYPES)
    | _COMBO_TYPES
    | {"step"}
)
_EXTREMA_TYPES = {"column", "line", "line_plain", "step"} | set(_SCATTER_TYPES)


@dataclass
class _Canvas:
    """Shared state for one render pass."""

    axes: Any
    data: ChartData
    spec: ChartSpec
    theme: dict[str, Any]
    palette: tuple[str, ...]
    categories: list[str]
    positions: np.ndarray
    secondary_axes: Any = None
    # Artists that receive data labels: (container, series index).
    bar_containers: list[tuple[Any, int]] = field(default_factory=list)
    # Plotted point series for labels and elements: (x, y, series index).
    point_series: list[tuple[np.ndarray, np.ndarray, int]] = field(
        default_factory=list
    )

    def color(self, index: int) -> str:
        return self.palette[index % len(self.palette)]


def chart_projection(chart_type: str) -> str | None:
    """Return the Matplotlib projection a chart type needs."""
    if chart_type in THREE_D_TYPES:
        return "3d"
    if chart_type in POLAR_TYPES:
        return "polar"
    return None


def draw_chart(figure: Figure, workbook: Workbook, spec: ChartSpec) -> ChartData:
    """Clear a figure and draw one chart from live workbook values."""
    figure.clear()
    axes = figure.add_subplot(111, projection=chart_projection(spec.chart_type))
    data = chart_data(workbook, spec)
    hierarchy = (
        hierarchy_data(workbook, spec)
        if spec.chart_type in HIERARCHY_TYPES
        else None
    )
    render_chart(axes, data, spec, hierarchy=hierarchy)
    return data


def series_palette(spec: ChartSpec) -> tuple[str, ...]:
    """Return the series colors for a chart's theme and color scheme."""
    if spec.color_scheme == "theme":
        return THEMES[spec.theme]["palette"]
    return COLOR_SCHEME_PALETTES[spec.color_scheme]


def render_chart(
    axes: Any,
    data: ChartData,
    spec: ChartSpec,
    *,
    hierarchy: tuple[HierarchyNode, ...] | None = None,
) -> None:
    """Render prepared chart data with consistent analytical styling."""
    theme = THEMES[spec.theme]
    figure = axes.figure
    figure.set_facecolor(theme["background"])
    axes.set_facecolor(theme["plot"])
    axes.tick_params(colors=theme["text"], labelsize=9)
    for spine in getattr(axes, "spines", {}).values():
        spine.set_color(theme["grid"])

    if spec.empty_cells == "zero":
        data = ChartData(
            data.categories,
            tuple(
                ChartSeries(
                    series.name,
                    tuple(0.0 if math.isnan(value) else value for value in series.values),
                )
                for series in data.series
            ),
        )
    categories = [str(value) for value in data.categories]
    canvas = _Canvas(
        axes,
        data,
        spec,
        theme,
        series_palette(spec),
        categories,
        np.arange(len(categories), dtype=float),
    )
    chart_type = spec.chart_type
    if chart_type in THREE_D_TYPES:
        # Constrained layout collapses 3-D axes that carry text tick labels,
        # so they keep a fixed box instead.
        axes.set_in_layout(False)
        axes.set_position((0.02, 0.02, 0.9, 0.86))

    if chart_type in HIERARCHY_TYPES:
        nodes = hierarchy if hierarchy is not None else _flat_hierarchy(data)
        if not nodes:
            _message(canvas, "No positive values to show in the hierarchy")
        elif chart_type == "treemap":
            _draw_treemap(canvas, nodes)
        else:
            _draw_sunburst(canvas, nodes)
        _finish_title(canvas)
        _place_legend(canvas)
        return
    if not data.series or not categories:
        _message(canvas, "No plottable data")
        _finish_title(canvas)
        return

    drawn = _draw_marks(canvas)
    if drawn is False:
        _finish_title(canvas)
        return
    _finish(canvas)


def _draw_marks(canvas: _Canvas) -> bool:
    """Draw the chart family's marks; False means a message was shown."""
    chart_type = canvas.spec.chart_type
    if chart_type in _COLUMN_TYPES:
        _draw_bars(canvas, horizontal=False, mode=_COLUMN_TYPES[chart_type])
    elif chart_type in _BAR_TYPES:
        _draw_bars(canvas, horizontal=True, mode=_BAR_TYPES[chart_type])
    elif chart_type in _LINE_TYPES:
        mode, markers = _LINE_TYPES[chart_type]
        _draw_lines(canvas, mode=mode, markers=markers)
    elif chart_type == "step":
        _draw_step(canvas)
    elif chart_type in _AREA_TYPES:
        _draw_areas(canvas, mode=_AREA_TYPES[chart_type])
    elif chart_type in {"pie", "pie_3d", "donut"}:
        _draw_pie(canvas)
    elif chart_type in {"pie_of_pie", "bar_of_pie"}:
        _draw_pie_of_pie(canvas)
    elif chart_type in _SCATTER_TYPES:
        lines, smooth, markers = _SCATTER_TYPES[chart_type]
        _draw_scatter(canvas, lines=lines, smooth=smooth, markers=markers)
    elif chart_type in {"bubble", "bubble_3d"}:
        _draw_bubble(canvas, shaded=chart_type == "bubble_3d")
    elif chart_type in STOCK_COLUMNS:
        return _draw_stock(canvas)
    elif chart_type in _THREE_D_BARS:
        horizontal, mode = _THREE_D_BARS[chart_type]
        _draw_bars_3d(canvas, horizontal=horizontal, mode=mode)
    elif chart_type == "line_3d":
        _draw_line_3d(canvas)
    elif chart_type in _THREE_D_AREAS:
        _draw_area_3d(canvas, mode=_THREE_D_AREAS[chart_type])
    elif chart_type in {"surface_3d", "surface_wireframe", "contour", "contour_wireframe"}:
        return _draw_surface(canvas)
    elif chart_type in POLAR_TYPES:
        _draw_radar(canvas)
    elif chart_type == "histogram":
        _draw_histogram(canvas)
    elif chart_type == "pareto":
        _draw_pareto(canvas)
    elif chart_type == "box":
        _draw_box(canvas)
    elif chart_type == "waterfall":
        _draw_waterfall(canvas)
    elif chart_type == "funnel":
        _draw_funnel(canvas)
    elif chart_type in _COMBO_TYPES:
        _draw_combo(canvas)
    elif chart_type == "heatmap":
        _draw_heatmap(canvas)
    return True


# ---------------------------------------------------------------------------
# Column, bar, line, and area families


def _values(series: ChartSeries) -> np.ndarray:
    return np.asarray(series.values, dtype=float)


def _series_matrix(canvas: _Canvas, mode: str) -> list[np.ndarray]:
    """Return per-series values, rescaled to percentages for 100% stacks."""
    matrix = [_values(series) for series in canvas.data.series]
    if mode == "percent":
        scaled = percent_stack(tuple(tuple(row) for row in matrix))
        return [np.asarray(row, dtype=float) for row in scaled]
    return matrix


def _bar_geometry(canvas: _Canvas, count: int) -> tuple[float, float]:
    """Return (bar width, step between series) from gap width and overlap."""
    width = 1.0 / (count + canvas.spec.gap_width / 100.0)
    step = width * (1.0 - canvas.spec.series_overlap / 100.0)
    return width, step


def _draw_bars(canvas: _Canvas, *, horizontal: bool, mode: str) -> None:
    axes = canvas.axes
    matrix = _series_matrix(canvas, mode)
    count = len(matrix)
    if mode == "clustered":
        width, step = _bar_geometry(canvas, count)
        span = step * (count - 1)
        for index, (series, values) in enumerate(zip(canvas.data.series, matrix)):
            shifted = canvas.positions - span / 2 + index * step
            error = _error_array(canvas, series)
            draw = axes.barh if horizontal else axes.bar
            extent = {"height": width} if horizontal else {"width": width}
            errors = (
                {"xerr" if horizontal else "yerr": error, "capsize": 3}
                if error is not None
                else {}
            )
            container = draw(
                shifted,
                np.nan_to_num(values),
                label=series.name,
                color=canvas.color(index),
                **extent,
                **errors,
            )
            canvas.bar_containers.append((container, index))
            canvas.point_series.append((shifted, values, index))
        return
    width, _ = _bar_geometry(canvas, 1)
    positive = np.zeros(len(canvas.positions))
    negative = np.zeros(len(canvas.positions))
    for index, (series, values) in enumerate(zip(canvas.data.series, matrix)):
        values = np.nan_to_num(values)
        base = np.where(values >= 0, positive, negative)
        if horizontal:
            container = axes.barh(
                canvas.positions,
                values,
                left=base,
                height=width,
                label=series.name,
                color=canvas.color(index),
            )
        else:
            container = axes.bar(
                canvas.positions,
                values,
                bottom=base,
                width=width,
                label=series.name,
                color=canvas.color(index),
            )
        canvas.bar_containers.append((container, index))
        positive += np.where(values >= 0, values, 0)
        negative += np.where(values < 0, values, 0)


def _stacked_matrix(matrix: list[np.ndarray]) -> list[np.ndarray]:
    """Return the running totals of a stack, treating blanks as zero."""
    running = np.zeros(len(matrix[0])) if matrix else np.zeros(0)
    totals = []
    for values in matrix:
        running = running + np.nan_to_num(values)
        totals.append(running.copy())
    return totals


def _draw_lines(canvas: _Canvas, *, mode: str, markers: bool) -> None:
    matrix = _series_matrix(canvas, mode)
    if mode != "clustered":
        matrix = _stacked_matrix(matrix)
    for index, (series, values) in enumerate(zip(canvas.data.series, matrix)):
        _plot_line(
            canvas,
            canvas.positions,
            values,
            index,
            series.name,
            markers=markers,
            smooth=canvas.spec.smooth_lines,
        )
        canvas.point_series.append((canvas.positions, values, index))
        if mode == "clustered":
            _line_error_bars(canvas, canvas.positions, values, series, index)


def _draw_step(canvas: _Canvas) -> None:
    for index, series in enumerate(canvas.data.series):
        values = _values(series)
        canvas.axes.step(
            canvas.positions,
            values,
            where="mid",
            linewidth=2.2,
            label=series.name,
            color=canvas.color(index),
        )
        canvas.point_series.append((canvas.positions, values, index))
        _line_error_bars(canvas, canvas.positions, values, series, index)


def _draw_areas(canvas: _Canvas, *, mode: str) -> None:
    axes = canvas.axes
    matrix = [np.nan_to_num(values) for values in _series_matrix(canvas, mode)]
    names = [series.name for series in canvas.data.series]
    if mode == "clustered":
        for index, (name, values) in enumerate(zip(names, matrix)):
            axes.fill_between(
                canvas.positions,
                values,
                alpha=0.34,
                label=name,
                color=canvas.color(index),
            )
            axes.plot(
                canvas.positions,
                values,
                linewidth=1.8,
                color=canvas.color(index),
            )
            canvas.point_series.append((canvas.positions, values, index))
            _line_error_bars(
                canvas, canvas.positions, values, canvas.data.series[index], index
            )
        return
    axes.stackplot(
        canvas.positions,
        matrix,
        labels=names,
        colors=[canvas.color(index) for index in range(len(matrix))],
        alpha=0.82,
    )
    for index, totals in enumerate(_stacked_matrix(matrix)):
        canvas.point_series.append((canvas.positions, totals, index))


def _plot_line(
    canvas: _Canvas,
    x_values: np.ndarray,
    y_values: np.ndarray,
    index: int,
    label: str,
    *,
    markers: bool,
    smooth: bool,
    axes: Any = None,
    linewidth: float = 2.2,
) -> None:
    """Draw one series as a line, honoring smoothing and empty-cell rules."""
    target = axes if axes is not None else canvas.axes
    color = canvas.color(index)
    x_values = np.asarray(x_values, dtype=float)
    y_values = np.asarray(y_values, dtype=float)
    if canvas.spec.empty_cells == "connect":
        keep = np.isfinite(y_values)
        segments = [(x_values[keep], y_values[keep])]
    else:
        segments = _finite_segments(x_values, y_values)
    labelled = False
    for x_segment, y_segment in segments:
        if smooth and len(x_segment) > 2:
            curve_x, curve_y = _smooth_curve(x_segment, y_segment)
        else:
            curve_x, curve_y = x_segment, y_segment
        target.plot(
            curve_x,
            curve_y,
            linewidth=linewidth,
            color=color,
            label=None if labelled else label,
        )
        labelled = True
        if markers:
            target.plot(
                x_segment,
                y_segment,
                linestyle="none",
                marker="o",
                markersize=4.5,
                color=color,
            )
    if not labelled:
        target.plot([], [], color=color, label=label)


def _finite_segments(
    x_values: np.ndarray,
    y_values: np.ndarray,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Split a series into runs of finite points, leaving gaps at blanks."""
    segments = []
    start = None
    finite = np.isfinite(y_values) & np.isfinite(x_values)
    for position, ok in enumerate(finite):
        if ok and start is None:
            start = position
        if not ok and start is not None:
            segments.append((x_values[start:position], y_values[start:position]))
            start = None
    if start is not None:
        segments.append((x_values[start:], y_values[start:]))
    return segments


def _smooth_curve(
    x_values: np.ndarray,
    y_values: np.ndarray,
    samples: int = 12,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a Catmull-Rom curve that passes through every point."""
    points = np.column_stack((x_values, y_values))
    padded = np.vstack((points[0], points, points[-1]))
    curve = []
    for index in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[index - 1 : index + 3]
        for step in np.linspace(0, 1, samples, endpoint=False):
            t2, t3 = step * step, step * step * step
            curve.append(
                0.5
                * (
                    2 * p1
                    + (-p0 + p2) * step
                    + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3
                )
            )
    curve.append(points[-1])
    result = np.asarray(curve)
    return result[:, 0], result[:, 1]


def _error_array(canvas: _Canvas, series: ChartSeries) -> np.ndarray | None:
    spec = canvas.spec
    if spec.error_bars == "none" or spec.chart_type not in _ERROR_BAR_TYPES:
        return None
    return np.asarray(
        error_bar_amounts(series.values, spec.error_bars, spec.effective_error_amount)
    )


def _line_error_bars(
    canvas: _Canvas,
    x_values: np.ndarray,
    y_values: np.ndarray,
    series: ChartSeries,
    index: int,
    axes: Any = None,
) -> None:
    error = _error_array(canvas, series)
    if error is None:
        return
    (axes or canvas.axes).errorbar(
        x_values,
        y_values,
        yerr=error,
        fmt="none",
        ecolor=canvas.color(index),
        elinewidth=1.1,
        capsize=3,
    )


# ---------------------------------------------------------------------------
# Pie family


def _pie_values(canvas: _Canvas) -> np.ndarray:
    return np.maximum(0, np.nan_to_num(_values(canvas.data.series[0])))


def _pie_start(canvas: _Canvas) -> float:
    # Excel measures the first slice clockwise from 12 o'clock.
    return 90.0 - canvas.spec.first_slice_angle


def _pie_text(canvas: _Canvas, values: np.ndarray, labels: list[str]) -> list[str]:
    total = float(values.sum()) or 1.0
    content = canvas.spec.data_label_content
    texts = []
    for label, value in zip(labels, values):
        if content == "percent":
            texts.append(f"{value / total:.1%}")
        elif content == "category":
            texts.append(label)
        elif content == "series":
            texts.append(canvas.data.series[0].name)
        elif content == "category_value":
            texts.append(f"{label}: {_format_value(value, canvas.spec.number_format)}")
        else:
            texts.append(_format_value(value, canvas.spec.number_format))
    return texts


def _label_distance(canvas: _Canvas, radius: float, width: float | None) -> float:
    position = canvas.spec.data_label_position
    if position == "outside_end":
        return radius * 1.12
    if width is not None:
        return radius - width / 2
    if position == "inside_base":
        return radius * 0.35
    if position == "center":
        return radius * 0.55
    return radius * 0.7


def _annotate_wedges(
    canvas: _Canvas,
    wedges: list[Any],
    texts: list[str],
    distance: float,
    center: tuple[float, float] = (0.0, 0.0),
) -> None:
    for wedge, text in zip(wedges, texts):
        angle = math.radians((wedge.theta1 + wedge.theta2) / 2)
        canvas.axes.text(
            center[0] + distance * math.cos(angle),
            center[1] + distance * math.sin(angle),
            text,
            ha="center",
            va="center",
            fontsize=8,
            color=canvas.theme["text"],
        )


def _draw_pie(canvas: _Canvas) -> None:
    axes = canvas.axes
    spec = canvas.spec
    chart_type = spec.chart_type
    explode_fraction = spec.pie_explosion / 100.0
    edge = {"edgecolor": canvas.theme["plot"]}
    if chart_type == "donut":
        hole = spec.hole_size / 100.0
        rings = [np.maximum(0, np.nan_to_num(_values(series))) for series in canvas.data.series]
        ring_width = (1.0 - hole) / max(1, len(rings))
        colors = [canvas.color(index) for index in range(len(canvas.categories))]
        for ring, values in enumerate(rings):
            if not np.any(values):
                continue
            radius = 1.0 - ring * ring_width
            wedges, _ = axes.pie(
                values,
                labels=canvas.categories if ring == 0 else None,
                labeldistance=1.08,
                startangle=_pie_start(canvas),
                counterclock=False,
                colors=colors,
                radius=radius,
                explode=[explode_fraction * 0.3] * len(values) if ring == 0 else None,
                wedgeprops={"width": ring_width, **edge},
            )
            if spec.show_data_labels:
                _annotate_wedges(
                    canvas,
                    wedges,
                    _pie_text(canvas, values, canvas.categories),
                    radius - ring_width / 2,
                )
        axes.set_aspect("equal")
        return

    values = _pie_values(canvas)
    if not np.any(values):
        _message(canvas, "A pie needs at least one positive value")
        return
    colors = [canvas.color(index) for index in range(len(values))]
    explode = [explode_fraction] * len(values)
    if chart_type == "pie_3d":
        # Stack darkened copies below the top face to give the pie depth.
        shade = [_mix(color, "#000000", 0.35) for color in colors]
        for layer in range(12, 0, -1):
            axes.pie(
                values,
                startangle=_pie_start(canvas),
                counterclock=False,
                colors=shade,
                explode=explode,
                center=(0, -0.022 * layer),
                wedgeprops={"linewidth": 0},
            )
    wedges, _ = axes.pie(
        values,
        labels=canvas.categories,
        startangle=_pie_start(canvas),
        counterclock=False,
        colors=colors,
        explode=explode,
        wedgeprops=edge,
    )
    if spec.show_data_labels:
        _annotate_wedges(
            canvas,
            wedges,
            _pie_text(canvas, values, canvas.categories),
            _label_distance(canvas, 1.0, None),
        )
    if chart_type == "pie_3d":
        axes.set_aspect(0.55)
        axes.set_xlim(-1.35, 1.35)
        axes.set_ylim(-1.55, 1.3)
    else:
        axes.set_aspect("equal")


def _draw_pie_of_pie(canvas: _Canvas) -> None:
    """Draw a main pie whose last values are expanded in a second plot."""
    axes = canvas.axes
    values = _pie_values(canvas)
    labels = canvas.categories
    split = min(canvas.spec.split_count, max(1, len(values) - 1))
    main_values = list(values[:-split]) + [float(values[-split:].sum())]
    main_labels = labels[:-split] + ["Other"]
    detail_values = values[-split:]
    detail_labels = labels[-split:]
    if not any(main_values):
        _message(canvas, "Pie of Pie needs at least one positive value")
        return
    other_share = main_values[-1] / sum(main_values)
    other_span = 360.0 * other_share
    # Point the combined "Other" slice straight at the second plot.
    start = other_span / 2.0 + (360.0 - other_span)
    colors = [canvas.color(index) for index in range(len(main_values))]
    wedges, _ = axes.pie(
        main_values,
        labels=main_labels,
        startangle=start,
        counterclock=False,
        colors=colors,
        explode=[0.0] * (len(main_values) - 1) + [0.06],
        wedgeprops={"edgecolor": canvas.theme["plot"]},
    )
    edge_angles = (math.radians(other_span / 2), math.radians(-other_span / 2))
    detail_colors = [
        _mix(colors[-1], "#ffffff", 0.15 + 0.6 * index / max(1, split))
        for index in range(split)
    ]
    if canvas.spec.chart_type == "pie_of_pie":
        detail_wedges, _ = axes.pie(
            detail_values if np.any(detail_values) else np.ones(split),
            labels=detail_labels,
            startangle=90,
            counterclock=False,
            colors=detail_colors,
            center=(2.5, 0),
            radius=0.62,
            wedgeprops={"edgecolor": canvas.theme["plot"]},
        )
        targets = ((2.5, 0.62), (2.5, -0.62))
        if canvas.spec.show_data_labels:
            _annotate_wedges(
                canvas,
                detail_wedges,
                _pie_text(canvas, detail_values, detail_labels),
                0.4,
                center=(2.5, 0),
            )
    else:
        total = float(detail_values.sum()) or 1.0
        bottom = -0.9
        for index, (label, value) in enumerate(zip(detail_labels, detail_values)):
            height = 1.8 * value / total
            axes.add_patch(
                Rectangle(
                    (2.2, bottom),
                    0.5,
                    height,
                    facecolor=detail_colors[index],
                    edgecolor=canvas.theme["plot"],
                    label=label,
                )
            )
            axes.text(2.78, bottom + height / 2, label, va="center", fontsize=8)
            if canvas.spec.show_data_labels:
                axes.text(
                    2.45,
                    bottom + height / 2,
                    _format_value(value, canvas.spec.number_format),
                    ha="center",
                    va="center",
                    fontsize=7.5,
                )
            bottom += height
        targets = ((2.2, 0.9), (2.2, -0.9))
    for angle, target in zip(edge_angles, targets):
        origin = (1.06 * math.cos(angle) + 0.06, 1.06 * math.sin(angle))
        axes.add_artist(
            ConnectionPatch(
                origin,
                target,
                "data",
                "data",
                color=canvas.theme["grid"],
                linewidth=1,
            )
        )
    if canvas.spec.show_data_labels:
        _annotate_wedges(
            canvas,
            wedges,
            _pie_text(canvas, np.asarray(main_values), main_labels),
            0.7,
        )
    axes.set_aspect("equal")
    axes.set_xlim(-1.35, 3.6)
    axes.set_ylim(-1.35, 1.35)


# ---------------------------------------------------------------------------
# Scatter, bubble, and stock


def _numeric_categories(data: ChartData) -> np.ndarray:
    values = []
    for index, value in enumerate(data.categories):
        values.append(
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else float(index)
        )
    return np.asarray(values)


def _draw_scatter(
    canvas: _Canvas,
    *,
    lines: bool,
    smooth: bool,
    markers: bool,
) -> None:
    x_values = _numeric_categories(canvas.data)
    for index, series in enumerate(canvas.data.series):
        y_values = _values(series)
        if lines:
            order = np.argsort(x_values, kind="stable")
            _plot_line(
                canvas,
                x_values[order],
                y_values[order],
                index,
                series.name,
                markers=markers,
                smooth=smooth or canvas.spec.smooth_lines,
            )
        else:
            canvas.axes.scatter(
                x_values,
                y_values,
                s=46,
                alpha=0.82,
                label=series.name,
                color=canvas.color(index),
                edgecolors=canvas.theme["plot"],
                linewidths=0.7,
            )
        canvas.point_series.append((x_values, y_values, index))
        _line_error_bars(canvas, x_values, y_values, series, index)


def _draw_bubble(canvas: _Canvas, *, shaded: bool) -> None:
    x_values = _numeric_categories(canvas.data)
    groups = bubble_series(canvas.data)
    sizes_all = [
        abs(size)
        for _, _, sizes in groups
        for size in sizes
        if math.isfinite(size)
    ]
    largest = max(sizes_all) if sizes_all else 1.0
    for index, (name, y_values, sizes) in enumerate(groups):
        y_array = np.asarray(y_values, dtype=float)
        # Excel sizes bubbles by area, with the largest at a fixed size.
        area = np.asarray(
            [
                1400.0 * abs(size) / largest if math.isfinite(size) and largest else 0
                for size in sizes
            ]
        )
        color = canvas.color(index)
        canvas.axes.scatter(
            x_values,
            y_array,
            s=area,
            alpha=0.62 if not shaded else 0.9,
            label=name,
            color=color,
            edgecolors=_mix(color, "#000000", 0.25),
            linewidths=0.8,
        )
        if shaded:
            canvas.axes.scatter(
                x_values,
                y_array,
                s=area * 0.22,
                color=_mix(color, "#ffffff", 0.65),
                alpha=0.8,
                linewidths=0,
            )
        canvas.point_series.append((x_values, y_array, index))
        _line_error_bars(canvas, x_values, y_array, ChartSeries(name, y_values), index)
    canvas.axes.margins(0.12)


def _draw_stock(canvas: _Canvas) -> bool:
    chart_type = canvas.spec.chart_type
    expected = STOCK_COLUMNS[chart_type]
    if len(canvas.data.series) != len(expected):
        _message(
            canvas,
            f"This stock chart needs {len(expected)} data columns in this "
            f"order: {', '.join(expected)}",
        )
        return False
    columns = {
        name: _values(series) for name, series in zip(expected, canvas.data.series)
    }
    axes = canvas.axes
    price_axes = axes
    if "Volume" in columns:
        axes.bar(
            canvas.positions,
            np.nan_to_num(columns["Volume"]),
            width=0.6,
            color=canvas.color(3),
            alpha=0.45,
            label="Volume",
        )
        price_axes = axes.twinx()
        price_axes.set_facecolor("none")
        canvas.secondary_axes = price_axes
    high, low, close = columns["High"], columns["Low"], columns["Close"]
    up_color = canvas.color(0)
    down_color = canvas.theme["accent"]
    if "Open" in columns:
        opening = columns["Open"]
        rising = close >= opening
        price_axes.vlines(
            canvas.positions, low, high, color=canvas.theme["text"], linewidth=1
        )
        bottoms = np.minimum(opening, close)
        heights = np.maximum(np.abs(close - opening), 1e-9)
        price_axes.bar(
            canvas.positions,
            heights,
            bottom=bottoms,
            width=0.55,
            color=[canvas.theme["plot"] if up else down_color for up in rising],
            edgecolor=[up_color if up else down_color for up in rising],
            linewidth=1.2,
            label="Open-Close",
        )
    else:
        price_axes.vlines(
            canvas.positions,
            low,
            high,
            color=canvas.theme["text"],
            linewidth=1.4,
            label="High-Low",
        )
        price_axes.plot(
            canvas.positions,
            close,
            linestyle="none",
            marker="_",
            markersize=11,
            markeredgewidth=2,
            color=up_color,
            label="Close",
        )
    canvas.point_series.append((canvas.positions, close, 0))
    return True


# ---------------------------------------------------------------------------
# Three-dimensional and surface charts


def _draw_bars_3d(canvas: _Canvas, *, horizontal: bool, mode: str) -> None:
    axes = canvas.axes
    matrix = [np.nan_to_num(values) for values in _series_matrix(canvas, mode)]
    count = len(matrix)
    depth = 0.5
    if mode == "depth":
        for index, values in enumerate(matrix):
            axes.bar3d(
                canvas.positions - 0.25,
                np.full(len(values), index - 0.25),
                np.zeros(len(values)),
                0.5,
                depth,
                values,
                color=canvas.color(index),
                shade=True,
                label=canvas.data.series[index].name,
            )
        axes.set_yticks(
            range(count), [series.name for series in canvas.data.series]
        )
        axes.set_xticks(canvas.positions, canvas.categories)
        axes.set_box_aspect((2.6, 1.5, 1.3), zoom=0.9)
        return
    width, step = (
        _bar_geometry(canvas, count) if mode == "clustered" else (0.6, 0.0)
    )
    span = step * (count - 1)
    running_positive = np.zeros(len(canvas.positions))
    running_negative = np.zeros(len(canvas.positions))
    for index, values in enumerate(matrix):
        offset = (
            canvas.positions - span / 2 + index * step - width / 2
            if mode == "clustered"
            else canvas.positions - width / 2
        )
        base = (
            np.zeros(len(values))
            if mode == "clustered"
            else np.where(values >= 0, running_positive, running_negative)
        )
        zeros = np.zeros(len(values))
        if horizontal:
            # Excel's 3-D bars run along x with the categories stacked up z.
            axes.bar3d(
                base,
                zeros,
                offset,
                values,
                depth,
                width,
                color=canvas.color(index),
                shade=True,
                label=canvas.data.series[index].name,
            )
        else:
            axes.bar3d(
                offset,
                zeros,
                base,
                width,
                depth,
                values,
                color=canvas.color(index),
                shade=True,
                label=canvas.data.series[index].name,
            )
        if mode != "clustered":
            running_positive += np.where(values >= 0, values, 0)
            running_negative += np.where(values < 0, values, 0)
    axes.set_ylim(-0.4, depth + 0.4)
    axes.set_yticks([])
    if horizontal:
        axes.set_zticks(canvas.positions, canvas.categories)
        axes.set_box_aspect((2.0, 0.7, 1.9), zoom=0.9)
        axes.view_init(elev=12, azim=-70)
    else:
        axes.set_xticks(canvas.positions, canvas.categories)
        axes.set_box_aspect((2.6, 0.7, 1.4), zoom=0.9)


def _draw_line_3d(canvas: _Canvas) -> None:
    axes = canvas.axes
    for index, series in enumerate(canvas.data.series):
        values = np.nan_to_num(_values(series))
        x_grid = np.vstack((canvas.positions, canvas.positions))
        y_grid = np.vstack(
            (np.full(len(values), index), np.full(len(values), index + 0.6))
        )
        z_grid = np.vstack((values, values))
        axes.plot_surface(
            x_grid,
            y_grid,
            z_grid,
            color=canvas.color(index),
            shade=True,
            label=series.name,
        )
    axes.set_xticks(canvas.positions, canvas.categories)
    axes.set_yticks(
        np.arange(len(canvas.data.series)) + 0.3,
        [series.name for series in canvas.data.series],
    )
    axes.set_box_aspect((2.6, 1.5, 1.2), zoom=0.9)
    axes.view_init(elev=18, azim=-60)


def _draw_area_3d(canvas: _Canvas, *, mode: str) -> None:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    axes = canvas.axes
    matrix = [np.nan_to_num(values) for values in _series_matrix(canvas, mode)]
    x_values = canvas.positions
    lower = np.zeros(len(x_values))
    for index, values in enumerate(matrix):
        depth = index if mode == "depth" else 0
        upper = lower + values if mode != "depth" else values
        base = lower if mode != "depth" else np.zeros(len(x_values))
        top = list(zip(x_values, np.full(len(x_values), depth), upper))
        bottom = list(zip(x_values[::-1], np.full(len(x_values), depth), base[::-1]))
        face = Poly3DCollection(
            [top + bottom],
            facecolor=canvas.color(index),
            edgecolor=_mix(canvas.color(index), "#000000", 0.3),
            alpha=0.85,
            label=canvas.data.series[index].name,
        )
        axes.add_collection3d(face)
        if mode != "depth":
            lower = upper
    all_values = np.concatenate(
        [np.zeros(1)]
        + (
            [np.asarray(matrix).ravel()]
            if mode == "depth"
            else [lower]
        )
    )
    axes.set_xlim(x_values.min() - 0.5 if len(x_values) else 0, x_values.max() + 0.5 if len(x_values) else 1)
    axes.set_ylim(-0.5, max(1, len(matrix)) - 0.5 if mode == "depth" else 0.5)
    axes.set_zlim(min(0.0, float(all_values.min())), float(all_values.max()) or 1.0)
    axes.set_xticks(canvas.positions, canvas.categories)
    if mode == "depth":
        axes.set_yticks(
            range(len(matrix)), [series.name for series in canvas.data.series]
        )
        axes.set_box_aspect((2.6, 1.5, 1.2), zoom=0.9)
    else:
        axes.set_yticks([])
        axes.set_box_aspect((2.6, 0.6, 1.4), zoom=0.9)


def _draw_surface(canvas: _Canvas) -> bool:
    chart_type = canvas.spec.chart_type
    matrix = np.asarray(
        [np.nan_to_num(_values(series)) for series in canvas.data.series]
    )
    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        _message(
            canvas,
            "Surface and contour charts need at least two rows and two value "
            "columns",
        )
        return False
    x_grid, y_grid = np.meshgrid(
        np.arange(matrix.shape[1], dtype=float),
        np.arange(matrix.shape[0], dtype=float),
    )
    axes = canvas.axes
    names = [series.name for series in canvas.data.series]
    if chart_type == "surface_3d":
        surface = axes.plot_surface(
            x_grid, y_grid, matrix, cmap="viridis", edgecolor="none", alpha=0.95
        )
        axes.figure.colorbar(surface, ax=axes, shrink=0.6, pad=0.1)
    elif chart_type == "surface_wireframe":
        axes.plot_wireframe(
            x_grid, y_grid, matrix, color=canvas.color(0), linewidth=1.1
        )
    elif chart_type == "contour":
        filled = axes.contourf(x_grid, y_grid, matrix, levels=8, cmap="viridis")
        axes.figure.colorbar(filled, ax=axes, shrink=0.85, pad=0.02)
    else:
        lines = axes.contour(x_grid, y_grid, matrix, levels=8, cmap="viridis")
        axes.clabel(lines, fontsize=7, inline=True)
    axes.set_xticks(canvas.positions, canvas.categories)
    axes.set_yticks(range(len(names)), names)
    return True


# ---------------------------------------------------------------------------
# Radar, statistical, flow, and hierarchy charts


def _draw_radar(canvas: _Canvas) -> None:
    axes = canvas.axes
    chart_type = canvas.spec.chart_type
    angles = np.linspace(0, 2 * math.pi, len(canvas.categories), endpoint=False)
    closed_angles = np.concatenate((angles, angles[:1]))
    for index, series in enumerate(canvas.data.series):
        values = np.nan_to_num(_values(series))
        closed_values = np.concatenate((values, values[:1]))
        color = canvas.color(index)
        axes.plot(
            closed_angles,
            closed_values,
            linewidth=2,
            label=series.name,
            color=color,
            marker="o" if chart_type == "radar_markers" else None,
            markersize=4.5,
        )
        if chart_type == "radar_filled":
            axes.fill(closed_angles, closed_values, alpha=0.4, color=color)
        canvas.point_series.append((angles, values, index))
    axes.set_xticks(angles, canvas.categories)
    axes.set_theta_offset(math.pi / 2)
    axes.set_theta_direction(-1)
    if canvas.spec.axis_min is not None or canvas.spec.axis_max is not None:
        axes.set_ylim(canvas.spec.axis_min, canvas.spec.axis_max)


def _finite(values: tuple[float, ...]) -> list[float]:
    return [float(value) for value in values if math.isfinite(value)]


def _draw_histogram(canvas: _Canvas) -> None:
    bins: Any = canvas.spec.bin_count or "auto"
    for index, series in enumerate(canvas.data.series):
        values = _finite(series.values)
        if values:
            canvas.axes.hist(
                values,
                bins=bins,
                alpha=0.62 if len(canvas.data.series) > 1 else 0.9,
                label=series.name,
                color=canvas.color(index),
                edgecolor=canvas.theme["plot"],
            )


def _draw_pareto(canvas: _Canvas) -> None:
    labels, values, cumulative = pareto_data(
        canvas.data.categories, canvas.data.series[0].values
    )
    positions = np.arange(len(labels), dtype=float)
    canvas.categories = [str(label) for label in labels]
    canvas.positions = positions
    container = canvas.axes.bar(
        positions,
        values,
        width=0.8,
        color=canvas.color(0),
        label=canvas.data.series[0].name,
    )
    canvas.bar_containers.append((container, 0))
    percent_axes = canvas.axes.twinx()
    percent_axes.plot(
        positions,
        cumulative,
        marker="o",
        markersize=4,
        linewidth=2,
        color=canvas.theme["accent"],
        label="Cumulative %",
    )
    percent_axes.set_ylim(0, 105)
    percent_axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    percent_axes.tick_params(colors=canvas.theme["text"], labelsize=9)
    canvas.secondary_axes = percent_axes


def _draw_box(canvas: _Canvas) -> None:
    values = [_finite(series.values) for series in canvas.data.series]
    usable = [
        (series.name, series_values)
        for series, series_values in zip(canvas.data.series, values)
        if series_values
    ]
    if not usable:
        return
    box = canvas.axes.boxplot(
        [series_values for _, series_values in usable],
        tick_labels=[name for name, _ in usable],
        patch_artist=True,
        showmeans=True,
    )
    for index, patch in enumerate(box["boxes"]):
        patch.set_facecolor(canvas.color(index))
        patch.set_alpha(0.68)


def _draw_waterfall(canvas: _Canvas) -> None:
    values = np.nan_to_num(_values(canvas.data.series[0]))
    starts = np.concatenate(([0.0], np.cumsum(values)[:-1]))
    colors = [
        canvas.color(0) if value >= 0 else canvas.theme["accent"] for value in values
    ]
    container = canvas.axes.bar(
        canvas.positions,
        values,
        bottom=starts,
        color=colors,
        edgecolor=canvas.theme["plot"],
    )
    canvas.bar_containers.append((container, 0))
    canvas.axes.plot(
        canvas.positions,
        np.cumsum(values),
        color=canvas.theme["text"],
        linewidth=1,
        alpha=0.55,
    )


def _draw_funnel(canvas: _Canvas) -> None:
    axes = canvas.axes
    values = np.maximum(0, np.nan_to_num(_values(canvas.data.series[0])))
    axes.barh(
        canvas.positions,
        values,
        left=-values / 2,
        height=0.82,
        color=canvas.color(0),
        edgecolor=canvas.theme["plot"],
    )
    for position, value in zip(canvas.positions, values):
        axes.text(
            0,
            position,
            _format_value(value, canvas.spec.number_format),
            ha="center",
            va="center",
            fontsize=9,
            color="#ffffff",
            fontweight="bold",
        )
    axes.set_yticks(canvas.positions, canvas.categories)
    axes.invert_yaxis()
    axes.xaxis.set_visible(False)
    for side in ("top", "right", "bottom"):
        axes.spines[side].set_visible(False)


def _draw_heatmap(canvas: _Canvas) -> None:
    axes = canvas.axes
    matrix = np.asarray(
        [np.nan_to_num(_values(series)) for series in canvas.data.series]
    )
    image = axes.imshow(matrix, aspect="auto", cmap="YlGnBu")
    axes.set_yticks(
        np.arange(len(canvas.data.series)),
        [series.name for series in canvas.data.series],
    )
    axes.set_xticks(canvas.positions, canvas.categories)
    if canvas.spec.show_data_labels and matrix.size <= 120:
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                axes.text(
                    column,
                    row,
                    _format_value(matrix[row, column], canvas.spec.number_format),
                    ha="center",
                    va="center",
                    fontsize=8,
                )
    axes.figure.colorbar(image, ax=axes, shrink=0.78, pad=0.02)


def _combo_plan(canvas: _Canvas) -> tuple[list[str], set[int]]:
    """Return each series' mark type and the set on the secondary axis."""
    spec = canvas.spec
    count = len(canvas.data.series)
    if spec.chart_type == "combo_area_column":
        split = max(1, math.ceil(count / 2)) if count > 1 else 1
        return ["area"] * split + ["column"] * (count - split), set()
    if spec.chart_type == "combo_custom":
        kinds = list(spec.combo_series_types or ())
        defaults = ["column"] + ["line"] * max(0, count - 1)
        kinds = (kinds + defaults[len(kinds):])[:count]
        return kinds, {number - 1 for number in spec.secondary_series if number <= count}
    kinds = ["column"] + ["line"] * (count - 1)
    secondary = (
        set(range(1, count))
        if spec.chart_type == "combo_secondary" or spec.secondary_axis
        else set()
    )
    return kinds, secondary


def _draw_combo(canvas: _Canvas) -> None:
    kinds, secondary = _combo_plan(canvas)
    if secondary:
        canvas.secondary_axes = canvas.axes.twinx()
        canvas.secondary_axes.set_facecolor("none")
    stacked_area = canvas.spec.chart_type == "combo_area_column"
    for on_secondary in (False, True):
        target = canvas.secondary_axes if on_secondary else canvas.axes
        if target is None:
            continue
        members = [
            index
            for index in range(len(kinds))
            if (index in secondary) == on_secondary
        ]
        areas = [index for index in members if kinds[index] == "area"]
        if areas and stacked_area:
            target.stackplot(
                canvas.positions,
                [np.nan_to_num(_values(canvas.data.series[index])) for index in areas],
                labels=[canvas.data.series[index].name for index in areas],
                colors=[canvas.color(index) for index in areas],
                alpha=0.7,
            )
        else:
            for index in areas:
                values = np.nan_to_num(_values(canvas.data.series[index]))
                target.fill_between(
                    canvas.positions,
                    values,
                    alpha=0.35,
                    color=canvas.color(index),
                    label=canvas.data.series[index].name,
                )
        columns = [index for index in members if kinds[index] == "column"]
        if columns:
            width, step = _bar_geometry(canvas, len(columns))
            span = step * (len(columns) - 1)
            for slot, index in enumerate(columns):
                shifted = canvas.positions - span / 2 + slot * step
                container = target.bar(
                    shifted,
                    np.nan_to_num(_values(canvas.data.series[index])),
                    width=width,
                    alpha=0.85,
                    label=canvas.data.series[index].name,
                    color=canvas.color(index),
                )
                if target is canvas.axes:
                    canvas.bar_containers.append((container, index))
        for index in members:
            if kinds[index] != "line":
                continue
            values = _values(canvas.data.series[index])
            _plot_line(
                canvas,
                canvas.positions,
                values,
                index,
                canvas.data.series[index].name,
                markers=True,
                smooth=canvas.spec.smooth_lines,
                axes=target,
            )
            if target is canvas.axes:
                canvas.point_series.append((canvas.positions, values, index))


def _flat_hierarchy(data: ChartData) -> tuple[HierarchyNode, ...]:
    """Fallback hierarchy from categories and the first series."""
    values = data.series[0].values if data.series else ()
    return tuple(
        HierarchyNode(str(category), value)
        for category, value in zip(data.categories, values)
        if math.isfinite(value) and value > 0
    )


def _draw_treemap(canvas: _Canvas, nodes: tuple[HierarchyNode, ...]) -> None:
    axes = canvas.axes
    ordered = sorted(nodes, key=lambda node: node.value, reverse=True)
    rects = squarify(tuple(node.value for node in ordered), 0, 0, 100, 100)
    for index, (node, rect) in enumerate(zip(ordered, rects)):
        color = canvas.color(index)
        axes.add_patch(
            Rectangle(
                (rect.x, rect.y),
                rect.width,
                rect.height,
                facecolor=color,
                edgecolor=canvas.theme["plot"],
                linewidth=2.5,
                label=node.label,
            )
        )
        if node.children:
            _treemap_children(canvas, node.children, rect, color, depth=1)
            axes.text(
                rect.x + 1,
                rect.y + rect.height - 1,
                node.label,
                ha="left",
                va="top",
                fontsize=9,
                fontweight="bold",
                color="#ffffff",
            )
        else:
            _treemap_label(canvas, node, rect)
    axes.set_xlim(0, 100)
    axes.set_ylim(0, 100)
    axes.set_axis_off()


def _treemap_children(
    canvas: _Canvas,
    nodes: tuple[HierarchyNode, ...],
    parent: Any,
    color: str,
    depth: int,
) -> None:
    inset = 5.0 if parent.height > 14 else 0.0
    ordered = sorted(nodes, key=lambda node: node.value, reverse=True)
    rects = squarify(
        tuple(node.value for node in ordered),
        parent.x,
        parent.y,
        parent.width,
        max(0.0, parent.height - inset),
    )
    for index, (node, rect) in enumerate(zip(ordered, rects)):
        shade = _mix(color, "#ffffff", min(0.55, 0.12 * depth + 0.08 * (index % 3)))
        canvas.axes.add_patch(
            Rectangle(
                (rect.x, rect.y),
                rect.width,
                rect.height,
                facecolor=shade,
                edgecolor=canvas.theme["plot"],
                linewidth=1,
            )
        )
        if node.children:
            _treemap_children(canvas, node.children, rect, color, depth + 1)
        else:
            _treemap_label(canvas, node, rect)


def _treemap_label(canvas: _Canvas, node: HierarchyNode, rect: Any) -> None:
    if rect.width < 7 or rect.height < 5:
        return
    text = node.label
    if canvas.spec.show_data_labels:
        text += "\n" + _format_value(node.value, canvas.spec.number_format)
    canvas.axes.text(
        rect.x + rect.width / 2,
        rect.y + rect.height / 2,
        text,
        ha="center",
        va="center",
        fontsize=8,
        color=canvas.theme["text"],
        wrap=True,
    )


def _draw_sunburst(canvas: _Canvas, nodes: tuple[HierarchyNode, ...]) -> None:
    axes = canvas.axes
    depth = _hierarchy_depth(nodes)
    ring = 1.0 / (depth + 0.6)
    total = sum(node.value for node in nodes) or 1.0

    def draw(level_nodes: tuple[HierarchyNode, ...], start: float, span: float, level: int, colors: list[str] | None) -> None:
        level_total = sum(node.value for node in level_nodes) or 1.0
        angle = start
        for index, node in enumerate(level_nodes):
            width = span * node.value / level_total
            color = (
                canvas.color(index)
                if colors is None
                else _mix(colors[0], "#ffffff", min(0.6, 0.18 * level + 0.06 * (index % 3)))
            )
            outer = ring * (level + 1.6)
            wedge = Wedge(
                (0, 0),
                outer,
                90 - angle - width,
                90 - angle,
                width=ring,
                facecolor=color,
                edgecolor=canvas.theme["plot"],
                linewidth=1.2,
                label=node.label if level == 0 else None,
            )
            axes.add_patch(wedge)
            if width >= 12:
                middle = math.radians(90 - angle - width / 2)
                radius = outer - ring / 2
                text = node.label
                if canvas.spec.show_data_labels:
                    text += "\n" + _format_value(node.value, canvas.spec.number_format)
                axes.text(
                    radius * math.cos(middle),
                    radius * math.sin(middle),
                    text,
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=canvas.theme["text"],
                )
            if node.children:
                draw(node.children, angle, width, level + 1, [color])
            angle += width

    draw(nodes, 0.0, 360.0 * sum(node.value for node in nodes) / total, 0, None)
    limit = ring * (depth + 0.7)
    axes.set_xlim(-limit, limit)
    axes.set_ylim(-limit, limit)
    axes.set_aspect("equal")
    axes.set_axis_off()


def _hierarchy_depth(nodes: tuple[HierarchyNode, ...]) -> int:
    if not nodes:
        return 0
    return 1 + max(_hierarchy_depth(node.children) for node in nodes)


# ---------------------------------------------------------------------------
# Chart elements, axis format, titles, and legend


def _finish(canvas: _Canvas) -> None:
    spec = canvas.spec
    chart_type = spec.chart_type
    axes = canvas.axes

    if chart_type in _VERTICAL_CATEGORY:
        axes.set_xticks(canvas.positions, canvas.categories)
        if len(canvas.categories) > 8:
            axes.tick_params(axis="x", rotation=35)
    elif chart_type in _HORIZONTAL_CATEGORY:
        axes.set_yticks(canvas.positions, canvas.categories)

    if spec.show_trendline and chart_type in _TRENDLINE_TYPES:
        _add_trendlines(canvas)
    if spec.highlight_extrema and chart_type in _EXTREMA_TYPES:
        _highlight_extrema(canvas)
    if chart_type in _LINE_ELEMENT_TYPES:
        _add_line_elements(canvas)
    elif spec.drop_lines and chart_type in _AREA_TYPES:
        _add_drop_lines(canvas)

    _format_value_axis(canvas)
    if spec.reverse_categories:
        if chart_type in _VERTICAL_CATEGORY or chart_type in _XY_TYPES:
            axes.invert_xaxis()
        elif chart_type in _HORIZONTAL_CATEGORY or chart_type == "funnel":
            axes.invert_yaxis()

    _finish_title(canvas)
    if chart_type not in POLAR_TYPES and chart_type not in THREE_D_TYPES:
        x_title, y_title = _axis_titles(canvas)
        axes.set_xlabel(x_title, color=canvas.theme["text"])
        axes.set_ylabel(y_title, color=canvas.theme["text"])
    elif chart_type in THREE_D_TYPES:
        axes.set_xlabel(spec.x_axis_title, color=canvas.theme["text"])
        axes.set_zlabel(spec.y_axis_title, color=canvas.theme["text"])
    if canvas.secondary_axes is not None:
        canvas.secondary_axes.tick_params(colors=canvas.theme["text"])

    if spec.show_data_labels:
        _add_data_labels(canvas)
    _apply_gridlines(canvas)
    _apply_axis_visibility(canvas)
    if spec.show_data_table and chart_type in _DATA_TABLE_TYPES:
        _add_data_table(canvas)
    _place_legend(canvas)


def _finish_title(canvas: _Canvas) -> None:
    canvas.axes.set_title(
        canvas.spec.title,
        loc="left",
        color=canvas.theme["text"],
        fontsize=15,
        fontweight="bold",
        pad=12,
    )


def _axis_titles(canvas: _Canvas) -> tuple[str, str]:
    """Return bottom and left axis titles, naming any display unit."""
    spec = canvas.spec
    x_title, y_title = spec.x_axis_title, spec.y_axis_title
    if (
        spec.display_units != "none"
        and spec.chart_type in _VALUE_AXIS_TYPES
        and not _is_percent_stack(spec.chart_type)
    ):
        unit = spec.display_units.capitalize()
        if spec.chart_type in _HORIZONTAL_CATEGORY:
            x_title = f"{x_title} ({unit})" if x_title else unit
        else:
            y_title = f"{y_title} ({unit})" if y_title else unit
    return x_title, y_title


def _format_value_axis(canvas: _Canvas) -> None:
    spec = canvas.spec
    chart_type = spec.chart_type
    axes = canvas.axes
    unit = DISPLAY_UNITS[spec.display_units]
    percent_stack_type = _is_percent_stack(chart_type)

    def label(value: float, _: Any) -> str:
        if percent_stack_type:
            return f"{value:.0f}%"
        return _format_value(value / unit, spec.number_format if unit == 1 else "auto")

    formatter = FuncFormatter(label)
    if chart_type in THREE_D_TYPES:
        value_axis = axes.xaxis if chart_type.startswith("bar_3d") else axes.zaxis
        value_axis.set_major_formatter(formatter)
        limits = axes.get_xlim() if chart_type.startswith("bar_3d") else axes.get_zlim()
        low = spec.axis_min if spec.axis_min is not None else limits[0]
        high = spec.axis_max if spec.axis_max is not None else limits[1]
        if chart_type.startswith("bar_3d"):
            axes.set_xlim(low, high)
        else:
            axes.set_zlim(low, high)
        return
    if chart_type not in _VALUE_AXIS_TYPES:
        return
    horizontal = chart_type in _HORIZONTAL_CATEGORY
    value_axis = axes.xaxis if horizontal else axes.yaxis
    if spec.log_scale:
        (axes.set_xscale if horizontal else axes.set_yscale)("log")
    else:
        value_axis.set_major_formatter(formatter)
        if spec.major_unit is not None:
            value_axis.set_major_locator(MultipleLocator(spec.major_unit))
    if spec.axis_min is not None or spec.axis_max is not None:
        setter = axes.set_xlim if horizontal else axes.set_ylim
        setter(spec.axis_min, spec.axis_max)
    if canvas.secondary_axes is not None and chart_type in _COMBO_TYPES:
        canvas.secondary_axes.yaxis.set_major_formatter(formatter)


def _is_percent_stack(chart_type: str) -> bool:
    return chart_type.endswith("_100") or chart_type.endswith("_100_markers")


def _apply_gridlines(canvas: _Canvas) -> None:
    spec = canvas.spec
    chart_type = spec.chart_type
    axes = canvas.axes
    theme = canvas.theme
    if chart_type in POLAR_TYPES:
        # Passing style arguments to grid() re-enables it, so only style an
        # enabled grid.
        if spec.show_grid:
            axes.grid(True, alpha=0.22)
        else:
            axes.grid(False)
        return
    if chart_type in THREE_D_TYPES:
        axes.grid(spec.show_grid)
        return
    if chart_type in {"pie", "pie_3d", "donut", "pie_of_pie", "bar_of_pie", "funnel", "heatmap"}:
        axes.grid(False)
        return
    horizontal = chart_type in _HORIZONTAL_CATEGORY
    value_axis = "x" if horizontal else "y"
    category_axis = "y" if horizontal else "x"
    axes.grid(False)
    if spec.show_grid:
        axes.grid(True, axis=value_axis, which="major", color=theme["grid"], alpha=0.7)
    if spec.vertical_gridlines:
        axes.grid(True, axis=category_axis, which="major", color=theme["grid"], alpha=0.7)
    if spec.minor_gridlines:
        axes.minorticks_on()
        if horizontal:
            axes.tick_params(axis="y", which="minor", left=False)
        elif chart_type not in _XY_TYPES:
            axes.tick_params(axis="x", which="minor", bottom=False)
        axes.grid(
            True,
            axis=value_axis if not spec.vertical_gridlines else "both",
            which="minor",
            color=theme["grid"],
            alpha=0.35,
            linewidth=0.6,
        )
    axes.set_axisbelow(True)


def _apply_axis_visibility(canvas: _Canvas) -> None:
    spec = canvas.spec
    chart_type = spec.chart_type
    if chart_type in POLAR_TYPES or chart_type not in _VALUE_AXIS_TYPES:
        return
    axes = canvas.axes
    # Excel's "Primary Horizontal" is always the bottom axis.
    if not spec.show_x_axis:
        axes.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
        axes.spines["bottom"].set_visible(False)
    if not spec.show_y_axis:
        axes.tick_params(axis="y", which="both", left=False, labelleft=False)
        axes.spines["left"].set_visible(False)


def _trend_x(canvas: _Canvas, x_values: np.ndarray) -> np.ndarray:
    # Excel numbers categories 1..n for trendlines on category charts.
    if canvas.spec.chart_type in _XY_TYPES:
        return x_values
    return canvas.positions + 1.0


def _add_trendlines(canvas: _Canvas) -> None:
    spec = canvas.spec
    axes = canvas.axes
    notes = []
    seen: set[int] = set()
    for x_plot, y_values, index in canvas.point_series:
        if index in seen:
            continue
        seen.add(index)
        series = canvas.data.series[index]
        y_values = np.asarray(series.values, dtype=float)
        x_plot = np.asarray(x_plot, dtype=float)
        x_fit = _trend_x(canvas, x_plot)
        # Clustered columns sit beside the category centre; follow the bars.
        shift = float(x_plot[0] - x_fit[0]) if len(x_plot) else 0.0
        color = canvas.color(index)
        name = f"{series.name} trend"
        if spec.trendline_type == "moving_average":
            averaged = np.asarray(moving_average(tuple(y_values), spec.trendline_order))
            axes.plot(
                x_plot,
                averaged,
                linestyle="--",
                linewidth=1.5,
                color=color,
                label=f"{spec.trendline_order} per. Mov. Avg. ({series.name})",
            )
            continue
        fit = fit_trendline(
            tuple(x_fit),
            tuple(y_values),
            spec.trendline_type,
            spec.trendline_order,
        )
        if fit is None:
            continue
        finite = x_fit[np.isfinite(x_fit)]
        if not len(finite):
            continue
        start = finite.min() - spec.trendline_backward
        end = finite.max() + spec.trendline_forward
        if spec.trendline_type in {"logarithmic", "power"}:
            start = max(start, 1e-9)
        sample = np.linspace(start, end, 120)
        fitted = np.asarray([fit.predict(value) for value in sample])
        axes.plot(
            sample + shift,
            fitted,
            linestyle="--",
            linewidth=1.4,
            alpha=0.85,
            color=color,
            label=name,
        )
        parts = []
        if spec.show_equation:
            parts.append(fit.equation)
        if spec.show_r_squared:
            parts.append(f"R² = {fit.r_squared:.4f}")
        if parts:
            notes.append((", ".join(parts), color))
    for row, (text, color) in enumerate(notes):
        axes.text(
            0.02,
            0.97 - row * 0.075,
            text,
            transform=axes.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            color=color,
            bbox={"facecolor": canvas.theme["plot"], "edgecolor": "none", "alpha": 0.8},
        )


def _highlight_extrema(canvas: _Canvas) -> None:
    accent = canvas.theme["accent"]
    seen: set[int] = set()
    for x_values, values, index in canvas.point_series:
        if index in seen:
            continue
        seen.add(index)
        values = np.asarray(values, dtype=float)
        valid = np.flatnonzero(np.isfinite(values))
        if not len(valid):
            continue
        minimum = valid[np.argmin(values[valid])]
        maximum = valid[np.argmax(values[valid])]
        canvas.axes.scatter(
            [x_values[minimum], x_values[maximum]],
            [values[minimum], values[maximum]],
            s=70,
            facecolors="none",
            edgecolors=accent,
            linewidths=1.8,
            zorder=5,
        )


def _add_line_elements(canvas: _Canvas) -> None:
    spec = canvas.spec
    axes = canvas.axes
    if spec.drop_lines:
        _add_drop_lines(canvas)
    series_values = [np.asarray(values, dtype=float) for _, values, _ in canvas.point_series]
    if len(series_values) < 2:
        return
    matrix = np.vstack(series_values)
    if spec.high_low_lines:
        with np.errstate(all="ignore"):
            high = np.nanmax(matrix, axis=0)
            low = np.nanmin(matrix, axis=0)
        axes.vlines(
            canvas.positions,
            low,
            high,
            color=canvas.theme["text"],
            linewidth=1,
            alpha=0.7,
            zorder=1,
        )
    if spec.up_down_bars:
        first, last = matrix[0], matrix[-1]
        rising = last >= first
        axes.bar(
            canvas.positions,
            np.nan_to_num(last - first),
            bottom=np.nan_to_num(first),
            width=0.3,
            color=[
                canvas.theme["plot"] if up else canvas.theme["text"] for up in rising
            ],
            edgecolor=canvas.theme["text"],
            linewidth=1,
            zorder=2,
        )


def _add_drop_lines(canvas: _Canvas) -> None:
    axes = canvas.axes
    bottom, top = axes.get_ylim()
    for x_values, values, _ in canvas.point_series:
        values = np.asarray(values, dtype=float)
        finite = np.isfinite(values)
        axes.vlines(
            np.asarray(x_values)[finite],
            bottom,
            values[finite],
            color=canvas.theme["grid"],
            linewidth=1,
            linestyle=":",
            zorder=1,
        )
    axes.set_ylim(bottom, top)


def _data_label_text(
    canvas: _Canvas,
    series_index: int,
    point_index: int,
    value: float,
) -> str:
    spec = canvas.spec
    content = spec.data_label_content
    value_text = _format_value(value, spec.number_format)
    category = (
        canvas.categories[point_index]
        if 0 <= point_index < len(canvas.categories)
        else ""
    )
    if content == "value":
        return value_text
    if content == "percent":
        total = sum(
            abs(series.values[point_index])
            for series in canvas.data.series
            if point_index < len(series.values)
            and math.isfinite(series.values[point_index])
        )
        raw = canvas.data.series[series_index].values[point_index]
        return f"{raw / total:.1%}" if total and math.isfinite(raw) else ""
    if content == "category":
        return category
    if content == "series":
        return canvas.data.series[series_index].name
    return f"{category}: {value_text}"


def _add_data_labels(canvas: _Canvas) -> None:
    chart_type = canvas.spec.chart_type
    if chart_type in {"heatmap", "funnel", "treemap", "sunburst"} or chart_type in POLAR_TYPES:
        return
    if chart_type in THREE_D_TYPES or chart_type in {
        "pie", "pie_3d", "donut", "pie_of_pie", "bar_of_pie",
    }:
        return
    position = canvas.spec.data_label_position
    stacked = chart_type.startswith("stacked") or chart_type == "combo_area_column"
    if position == "auto":
        position = "center" if stacked else "outside_end"
    for container, series_index in canvas.bar_containers:
        horizontal = chart_type in _HORIZONTAL_CATEGORY
        for point_index, patch in enumerate(container.patches):
            _label_bar(canvas, patch, series_index, point_index, position, horizontal)
    if canvas.bar_containers:
        return
    if len(canvas.point_series) * max(1, len(canvas.categories)) > 150:
        return
    offsets = {
        "center": (0, 0),
        "inside_base": (0, -11),
        "inside_end": (0, 7),
        "outside_end": (0, 7),
    }
    offset = offsets[position]
    for x_values, values, series_index in canvas.point_series:
        for point_index, (x_value, y_value) in enumerate(zip(x_values, values)):
            if not math.isfinite(y_value):
                continue
            raw = canvas.data.series[series_index].values
            shown = raw[point_index] if point_index < len(raw) else y_value
            canvas.axes.annotate(
                _data_label_text(canvas, series_index, point_index, shown),
                (x_value, y_value),
                xytext=offset,
                textcoords="offset points",
                ha="center",
                va="center",
                fontsize=7.5,
                color=canvas.theme["text"],
            )


def _label_bar(
    canvas: _Canvas,
    patch: Any,
    series_index: int,
    point_index: int,
    position: str,
    horizontal: bool,
) -> None:
    x, y = patch.get_x(), patch.get_y()
    width, height = patch.get_width(), patch.get_height()
    raw_series = canvas.data.series[series_index].values
    if canvas.spec.chart_type == "pareto":
        value = height
    else:
        value = raw_series[point_index] if point_index < len(raw_series) else math.nan
    if not math.isfinite(value) or (width == 0 and height == 0):
        return
    length = width if horizontal else height
    sign = 1.0 if length >= 0 else -1.0
    if horizontal:
        base, end, middle = x, x + width, y + height / 2
    else:
        base, end, middle = y, y + height, x + width / 2
    anchor = {
        "center": (base + end) / 2,
        "inside_base": base,
        "inside_end": end,
        "outside_end": end,
    }[position]
    shift = {"center": 0, "inside_base": 9, "inside_end": -9, "outside_end": 8}[position]
    offset = (sign * shift, 0) if horizontal else (0, sign * shift)
    point = (anchor, middle) if horizontal else (middle, anchor)
    canvas.axes.annotate(
        _data_label_text(canvas, series_index, point_index, value),
        point,
        xytext=offset,
        textcoords="offset points",
        ha="center",
        va="center",
        fontsize=7.5,
        color=canvas.theme["text"],
    )


def _add_data_table(canvas: _Canvas) -> None:
    axes = canvas.axes
    # The table's columns line up with the plotted categories.
    step = -1 if canvas.spec.reverse_categories else 1
    cells = [
        [
            _format_value(value, canvas.spec.number_format) if math.isfinite(value) else ""
            for value in series.values[::step]
        ]
        for series in canvas.data.series
    ]
    table = axes.table(
        cellText=cells,
        rowLabels=[series.name for series in canvas.data.series],
        rowColours=[canvas.color(index) for index in range(len(cells))],
        colLabels=canvas.categories[::step],
        loc="bottom",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    table.scale(1, 1.15)
    axes.tick_params(axis="x", labelbottom=False)
    axes.set_xlabel("")


def _place_legend(canvas: _Canvas) -> None:
    spec = canvas.spec
    if spec.legend_position == "none":
        return
    axes = canvas.axes
    handles, labels = axes.get_legend_handles_labels()
    if canvas.secondary_axes is not None:
        extra_handles, extra_labels = canvas.secondary_axes.get_legend_handles_labels()
        handles += extra_handles
        labels += extra_labels
    visible = [(handle, label) for handle, label in zip(handles, labels) if label and not label.startswith("_")]
    if len(visible) <= 1:
        return
    # Combos draw areas, columns, then lines; list entries in series order.
    order = {series.name: index for index, series in enumerate(canvas.data.series)}
    visible.sort(key=lambda item: order.get(item[1], len(order)))
    handles, labels = [item[0] for item in visible], [item[1] for item in visible]
    legend_locations = {
        "right": ("center left", (1.02, 0.5)),
        "left": ("center right", (-0.02, 0.5)),
        "top": ("lower center", (0.5, 1.02)),
        "bottom": ("upper center", (0.5, -0.14)),
    }
    location, anchor = legend_locations[spec.legend_position]
    if spec.chart_type in THREE_D_TYPES:
        axes.legend(handles, labels, loc="upper left", frameon=False, fontsize=8)
        return
    if spec.show_data_table and spec.legend_position == "bottom":
        anchor = (0.5, -0.1 - 0.06 * (len(canvas.data.series) + 1))
    axes.legend(
        handles,
        labels,
        loc=location,
        bbox_to_anchor=anchor,
        frameon=False,
        ncols=2 if spec.legend_position in {"top", "bottom"} else 1,
    )


def _message(canvas: _Canvas, text: str) -> None:
    canvas.axes.text(
        0.5,
        0.5,
        text,
        ha="center",
        va="center",
        wrap=True,
        transform=canvas.axes.transAxes,
        color=canvas.theme["text"],
    )
    if canvas.axes.name == "rectilinear":
        canvas.axes.set_xticks([])
        canvas.axes.set_yticks([])


def _mix(color: str, other: str, amount: float) -> tuple[float, float, float]:
    first, second = np.asarray(to_rgb(color)), np.asarray(to_rgb(other))
    mixed = first * (1 - amount) + second * amount
    return (float(mixed[0]), float(mixed[1]), float(mixed[2]))


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
