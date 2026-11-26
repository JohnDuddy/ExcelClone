"""Data > Forecast Sheet: extend a time series with FORECAST.ETS and confidence bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duddysheet.core.cell import CellFormat
from duddysheet.core.chart import ChartSpec
from duddysheet.core.refs import CellReference, RangeReference


@dataclass(frozen=True, slots=True)
class ForecastOptions:
    """The Forecast Sheet dialog's choices."""

    periods: int = 6
    confidence: float = 0.95
    seasonality: int | None = None  # None detects it, as Excel's "Detect Automatically"
    chart_type: str = "line"

    def __post_init__(self) -> None:
        if not 1 <= self.periods <= 10_000:
            raise ValueError("Forecast End must add between 1 and 10,000 periods.")
        if not 0 < self.confidence < 1:
            raise ValueError("Confidence Interval must be between 0% and 100%.")
        if self.chart_type not in ("line", "column"):
            raise ValueError("The forecast chart is a line or column chart.")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def forecast_sheet_name(workbook: Any) -> str:
    """Return the next free 'SheetN' name, as Excel uses for a new forecast sheet."""
    number = len(workbook.sheet_names) + 1
    while f"Sheet{number}" in workbook.sheet_names:
        number += 1
    return f"Sheet{number}"


def build_forecast_sheet(workbook: Any, engine: Any, sheet_name: str, timeline: RangeReference, values: RangeReference, options: ForecastOptions) -> tuple[str, ChartSpec]:
    """Create a sheet with the history, a FORECAST.ETS forecast, its bounds, and a chart."""
    source = workbook.get_sheet(sheet_name)
    if (timeline.max_row - timeline.min_row) != (values.max_row - values.min_row) or timeline.min_column != timeline.max_column or values.min_column != values.max_column:
        raise ValueError("Select a timeline column and a values column of the same length.")
    header_row = None
    first = timeline.min_row
    if _number(source.get_cell(first, timeline.min_column).display_value) is None:
        header_row = first
        first += 1
    times = [_number(source.get_cell(row, timeline.min_column).display_value) for row in range(first, timeline.max_row + 1)]
    numbers = [_number(source.get_cell(row, values.min_column).display_value) for row in range(first, values.max_row + 1)]
    if len(times) < 3 or any(time is None for time in times):
        raise ValueError("The timeline needs at least three numeric or date values.")
    differences = {round(later - earlier, 9) for earlier, later in zip(times, times[1:])}
    if len(differences) != 1 or next(iter(differences)) <= 0:
        raise ValueError("The timeline values must be evenly spaced and increasing.")
    step = next(iter(differences))
    timeline_header = str(source.get_cell(header_row, timeline.min_column).display_value) if header_row is not None else "Timeline"
    values_header = str(source.get_cell(header_row, values.min_column).display_value) if header_row is not None else "Values"
    name = forecast_sheet_name(workbook)
    workbook.add_sheet(name)
    timeline_format = source.effective_format(first, timeline.min_column)
    headers = (timeline_header, values_header, f"Forecast({values_header})", f"Lower Confidence Bound({values_header})", f"Upper Confidence Bound({values_header})")
    for column, text in enumerate(headers):
        engine.set_cell(name, 0, column, text)
    last_history = len(times)
    history_values = f"$B$2:$B${last_history + 1}"
    history_times = f"$A$2:$A${last_history + 1}"
    seasonality = 1 if options.seasonality is None else options.seasonality
    confidence = f"{options.confidence:g}"
    for index, (time, number) in enumerate(zip(times, numbers), start=1):
        engine.set_cell(name, index, 0, time, cell_format=CellFormat(number_format=timeline_format.number_format))
        engine.set_cell(name, index, 1, number if number is not None else "")
    # Excel starts the forecast and both bounds at the last actual value.
    engine.set_cell(name, last_history, 2, f"=B{last_history + 1}")
    engine.set_cell(name, last_history, 3, f"=B{last_history + 1}")
    engine.set_cell(name, last_history, 4, f"=B{last_history + 1}")
    for offset in range(1, options.periods + 1):
        row = last_history + offset
        excel_row = row + 1
        engine.set_cell(name, row, 0, times[-1] + step * offset, cell_format=CellFormat(number_format=timeline_format.number_format))
        engine.set_cell(name, row, 2, f"=FORECAST.ETS(A{excel_row},{history_values},{history_times},{seasonality},1)")
        bound = f"FORECAST.ETS.CONFINT(A{excel_row},{history_values},{history_times},{confidence},{seasonality},1)"
        engine.set_cell(name, row, 3, f"=C{excel_row}-{bound}")
        engine.set_cell(name, row, 4, f"=C{excel_row}+{bound}")
    sheet = workbook.get_sheet(name)
    for column, width in enumerate((12, 14, 18, 26, 26)):
        sheet.column_widths[column] = width
    last_row = last_history + options.periods
    chart = ChartSpec(
        f"forecast-{name}",
        name,
        RangeReference(CellReference(0, 0, name), CellReference(last_row, 4, name)),
        options.chart_type if options.chart_type == "column" else "line_plain",
        title=f"Forecast of {values_header}",
        empty_cells="gaps",
    )
    sheet.charts.append(chart)
    return name, chart
