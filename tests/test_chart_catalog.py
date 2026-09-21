from __future__ import annotations

import math
from dataclasses import replace

import pytest

from duddysheet.core.chart import (
    CHART_CATALOG,
    CHART_FAMILIES,
    CHART_INFO,
    CHART_TYPE_LABELS,
    CHART_TYPES,
    ChartData,
    ChartSeries,
    ChartSpec,
    bubble_series,
    chart_data,
    error_bar_amounts,
    fit_trendline,
    hierarchy_data,
    moving_average,
    pareto_data,
    percent_stack,
    recommend_charts,
    squarify,
    switch_rows_columns,
)
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook

EXCEL_FAMILIES = (
    "Column",
    "Line",
    "Pie",
    "Bar",
    "Area",
    "X Y (Scatter)",
    "Stock",
    "Surface",
    "Radar",
    "Treemap",
    "Sunburst",
    "Histogram",
    "Box & Whisker",
    "Waterfall",
    "Funnel",
    "Combo",
)


def table(rows: tuple[tuple[object, ...], ...]) -> Workbook:
    workbook = Workbook()
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            if value is not None:
                workbook.active_sheet.set_cell(row, column, value)
    return workbook


def spec(chart_type: str, source: str, **options: object) -> ChartSpec:
    return ChartSpec("c", "Sheet1", parse_a1(source), chart_type, **options)


def test_catalog_covers_every_excel_chart_family_except_map() -> None:
    families = [family for family, _ in CHART_FAMILIES]

    assert families[: len(EXCEL_FAMILIES)] == list(EXCEL_FAMILIES)
    assert len(CHART_TYPES) == len(CHART_CATALOG) == 62
    assert len(set(CHART_TYPE_LABELS.values())) == len(CHART_TYPES)
    for info in CHART_CATALOG:
        assert info.summary and info.layout
    # The subtype counts of Excel's gallery.
    assert len(dict(CHART_FAMILIES)["Column"]) == 7
    assert len(dict(CHART_FAMILIES)["Line"]) == 7
    assert len(dict(CHART_FAMILIES)["Bar"]) == 6
    assert len(dict(CHART_FAMILIES)["Area"]) == 6
    assert len(dict(CHART_FAMILIES)["Stock"]) == 4
    assert len(dict(CHART_FAMILIES)["Surface"]) == 4
    assert len(dict(CHART_FAMILIES)["Radar"]) == 3


def test_legacy_chart_keys_keep_their_meaning() -> None:
    assert CHART_INFO["line"].label == "Line with Markers"
    assert CHART_INFO["donut"].label == "Doughnut"
    assert CHART_INFO["combo"].family == "Combo"
    for key in (
        "area",
        "bar",
        "box",
        "column",
        "heatmap",
        "histogram",
        "pie",
        "radar",
        "scatter",
        "stacked_area",
        "stacked_bar",
        "stacked_column",
        "step",
        "waterfall",
    ):
        assert key in CHART_TYPES


@pytest.mark.parametrize(
    ("options", "message"),
    (
        ({"error_bars": "wide"}, "error bar type"),
        ({"trendline_type": "spline"}, "trendline type"),
        ({"trendline_type": "polynomial", "trendline_order": 7}, "order"),
        ({"trendline_type": "moving_average", "trendline_order": 1}, "period"),
        ({"axis_min": 10.0, "axis_max": 5.0}, "minimum"),
        ({"major_unit": 0.0}, "major unit"),
        ({"gap_width": 501}, "Gap width"),
        ({"series_overlap": -101}, "overlap"),
        ({"hole_size": 5}, "hole size"),
        ({"first_slice_angle": 361}, "slice angle"),
        ({"pie_explosion": 401}, "explosion"),
        ({"split_count": 0}, "second plot"),
        ({"bin_count": 0}, "bin count"),
        ({"combo_series_types": ("column", "pie")}, "Combo series"),
        ({"secondary_series": (0,)}, "start at 1"),
        ({"display_units": "dozens"}, "display unit"),
        ({"color_scheme": "neon"}, "color scheme"),
        ({"empty_cells": "skip"}, "empty cell"),
        ({"error_amount": -1.0}, "negative"),
    ),
)
def test_chart_spec_rejects_invalid_element_options(
    options: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        spec("column", "A1:B3", **options)


def test_error_amount_defaults_follow_excel_per_type() -> None:
    base = spec("column", "A1:B3")

    assert replace(base, error_bars="percentage").effective_error_amount == 5.0
    assert replace(base, error_bars="standard_deviation").effective_error_amount == 1.0
    assert (
        replace(base, error_bars="fixed", error_amount=2.5).effective_error_amount
        == 2.5
    )


def test_switch_row_column_turns_rows_into_series() -> None:
    workbook = table(
        (
            ("Region", "Q1", "Q2"),
            ("North", 10, 20),
            ("South", 30, 40),
            ("West", 50, 60),
        )
    )

    data = chart_data(workbook, spec("column", "A1:C4", switch_row_column=True))

    assert data.categories == ("Q1", "Q2")
    assert [series.name for series in data.series] == ["North", "South", "West"]
    assert data.series[2].values == (50.0, 60.0)
    # Switching back restores the original Q1 series.
    assert switch_rows_columns(data).series[0].values == (
        10.0,
        30.0,
        50.0,
    )


def test_percent_stack_scales_each_category_to_one_hundred() -> None:
    assert percent_stack(((30.0, 20.0), (10.0, 30.0))) == (
        (75.0, 40.0),
        (25.0, 60.0),
    )
    assert percent_stack(((0.0,), (0.0,))) == ((0.0,), (0.0,))


def test_error_bar_amounts_match_excel_definitions() -> None:
    values = (120.0, 135.0, 128.0, 150.0, 162.0, 171.0)

    percentage = error_bar_amounts(values, "percentage", 5.0)
    deviation = error_bar_amounts(values, "standard_deviation", 1.0)
    standard_error = error_bar_amounts(values, "standard_error", 1.0)

    assert percentage[0] == pytest.approx(6.0)
    assert percentage[-1] == pytest.approx(8.55)
    assert deviation[0] == pytest.approx(20.00667, rel=1e-5)
    assert standard_error[0] == pytest.approx(20.00667 / math.sqrt(6), rel=1e-5)
    assert error_bar_amounts(values, "fixed", 2.0) == (2.0,) * 6
    assert error_bar_amounts((math.nan, 4.0), "standard_deviation", 1.0) == (
        0.0,
        0.0,
    )


@pytest.mark.parametrize(
    ("kind", "function", "coefficients"),
    (
        ("linear", lambda x: 2 * x + 1, (2.0, 1.0)),
        ("exponential", lambda x: 3 * math.exp(0.5 * x), (3.0, 0.5)),
        ("logarithmic", lambda x: 4 * math.log(x) + 2, (4.0, 2.0)),
        ("power", lambda x: 2 * x**3, (2.0, 3.0)),
        ("polynomial", lambda x: x * x - 3 * x + 5, (1.0, -3.0, 5.0)),
    ),
)
def test_trendlines_recover_exact_models(kind, function, coefficients) -> None:
    xs = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    ys = tuple(function(x) for x in xs)

    fit = fit_trendline(xs, ys, kind, 2)

    assert fit is not None
    assert fit.coefficients == pytest.approx(coefficients, rel=1e-6, abs=1e-6)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.predict(8.0) == pytest.approx(function(8.0), rel=1e-6)


def test_trendline_equations_read_like_excel() -> None:
    xs = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    revenue = (120.0, 135.0, 128.0, 150.0, 162.0, 171.0)

    linear = fit_trendline(xs, revenue, "linear")
    quadratic = fit_trendline(xs, revenue, "polynomial", 2)

    assert linear is not None and quadratic is not None
    assert linear.equation == "y = 10.23x + 108.5"
    assert linear.r_squared == pytest.approx(0.9148, abs=1e-4)
    assert linear.predict(7.0) == pytest.approx(180.1, abs=0.05)
    assert quadratic.equation == "y = 0.8214x^2 + 4.479x + 116.2"


def test_trendline_skips_points_outside_the_model_domain() -> None:
    assert fit_trendline((1.0, 2.0), (-1.0, -2.0), "exponential") is None
    assert fit_trendline((1.0, 2.0, 3.0), (1.0, 2.0, 3.0), "polynomial", 3) is None
    with pytest.raises(ValueError):
        fit_trendline((1.0, 2.0), (1.0, 2.0), "moving_average")


def test_moving_average_is_trailing_and_waits_for_a_full_window() -> None:
    averaged = moving_average((3.0, 6.0, 9.0, 12.0), 3)

    assert math.isnan(averaged[0]) and math.isnan(averaged[1])
    assert averaged[2:] == (6.0, 9.0)


def test_pareto_sorts_descending_with_cumulative_percent() -> None:
    labels, values, cumulative = pareto_data(
        ("Other", "Late", "Damaged"),
        (6.0, 48.0, 22.0),
    )

    assert labels == ("Late", "Damaged", "Other")
    assert values == (48.0, 22.0, 6.0)
    assert cumulative == pytest.approx((63.157894, 92.105263, 100.0))


def test_bubble_series_pairs_value_and_size_columns() -> None:
    data = ChartData(
        (1, 2),
        (
            ChartSeries("Units", (4.0, 5.0)),
            ChartSeries("Profit", (40.0, 90.0)),
            ChartSeries("Returns", (1.0, 2.0)),
        ),
    )

    groups = bubble_series(data)

    assert groups[0] == ("Units", (4.0, 5.0), (40.0, 90.0))
    assert groups[1] == ("Returns", (1.0, 2.0), (1.0, 1.0))


def test_hierarchy_inherits_blank_levels_and_totals_groups() -> None:
    workbook = table(
        (
            ("Region", "Country", "Sales"),
            ("Europe", "France", 10),
            (None, "Germany", 14),
            ("Asia", "Japan", 20),
            (None, "India", 8),
            ("Americas", None, 30),
            ("Africa", "Kenya", 0),
        )
    )

    nodes = hierarchy_data(workbook, spec("treemap", "A1:C7"))

    by_label = {node.label: node for node in nodes}
    assert set(by_label) == {"Europe", "Asia", "Americas"}
    assert by_label["Europe"].value == 24
    assert [child.label for child in by_label["Europe"].children] == [
        "France",
        "Germany",
    ]
    # A fresh outer label must not inherit the previous row's inner label.
    assert by_label["Americas"].children == ()
    assert by_label["Americas"].value == 30


def test_squarify_fills_the_box_with_proportional_areas() -> None:
    values = (6.0, 6.0, 4.0, 3.0, 2.0, 2.0, 1.0)

    rects = squarify(values, 0.0, 0.0, 6.0, 4.0)

    total_area = 6.0 * 4.0
    for value, rect in zip(values, rects):
        assert rect.width * rect.height == pytest.approx(
            value / sum(values) * total_area
        )
        assert 0.0 <= rect.x and rect.x + rect.width <= 6.0 + 1e-9
        assert 0.0 <= rect.y and rect.y + rect.height <= 4.0 + 1e-9
    assert sum(rect.width * rect.height for rect in rects) == pytest.approx(total_area)


def test_recommendations_recognise_stock_hierarchy_and_funnel_data() -> None:
    stock = table(
        (
            ("Date", "Open", "High", "Low", "Close"),
            ("D1", 10, 12, 9, 11),
            ("D2", 11, 13, 10, 12),
        )
    )
    hierarchy = table(
        (
            ("Region", "Country", "Sales"),
            ("Europe", "France", 10),
            ("Asia", "Japan", 20),
        )
    )
    funnel = table(
        (("Stage", "Count"), ("Visit", 500), ("Trial", 120), ("Paid", 30))
    )

    stock_top = recommend_charts(stock, "Sheet1", parse_a1("A1:E3"))[0]
    hierarchy_types = [
        item.chart_type
        for item in recommend_charts(hierarchy, "Sheet1", parse_a1("A1:C3"))
    ]
    funnel_types = [
        item.chart_type
        for item in recommend_charts(funnel, "Sheet1", parse_a1("A1:B4"))
    ]

    assert stock_top.chart_type == "stock_ohlc"
    assert hierarchy_types[:2] == ["treemap", "sunburst"]
    assert "funnel" in funnel_types
    assert "pareto" in funnel_types
