"""PivotTables: summarize a source range by row, column, and filter fields.

``PivotSpec`` describes a PivotTable the way Excel's field list does: fields
in the Filters, Columns, Rows, and Values areas, item filters, date grouping,
layout, subtotals, and grand totals. ``compute_pivot`` turns a spec into an
output grid; ``render_pivot`` writes that grid onto its host sheet. Refreshing
recomputes from the current source, so a PivotTable is a live summary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from duddysheet.core.cell import BorderStyle, CellFormat

FUNCTIONS = (
    "sum",
    "count",
    "average",
    "max",
    "min",
    "product",
    "count_numbers",
    "stddev",
    "stddevp",
    "var",
    "varp",
)
FUNCTION_LABELS = {
    "sum": "Sum",
    "count": "Count",
    "average": "Average",
    "max": "Max",
    "min": "Min",
    "product": "Product",
    "count_numbers": "Count Numbers",
    "stddev": "StdDev",
    "stddevp": "StdDevp",
    "var": "Var",
    "varp": "Varp",
}
SHOW_AS = (
    "normal",
    "percent_of_grand_total",
    "percent_of_column_total",
    "percent_of_row_total",
    "running_total",
)
SHOW_AS_LABELS = {
    "normal": "No Calculation",
    "percent_of_grand_total": "% of Grand Total",
    "percent_of_column_total": "% of Column Total",
    "percent_of_row_total": "% of Row Total",
    "running_total": "Running Total In (rows)",
}
GROUPINGS = ("none", "years", "quarters", "months", "days")
LAYOUTS = ("compact", "outline", "tabular")
BLANK = "(blank)"
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


@dataclass(frozen=True, slots=True)
class PivotValueField:
    """A field in the Values area with its summary and display options."""

    field: str
    function: str = "sum"
    show_as: str = "normal"
    caption: str | None = None
    number_format: str | None = None

    @property
    def name(self) -> str:
        """Return the header Excel shows, such as 'Sum of Sales'."""
        return self.caption or f"{FUNCTION_LABELS.get(self.function, 'Sum')} of {self.field}"


@dataclass(frozen=True, slots=True)
class PivotSpec:
    """One PivotTable's source, layout, and field areas."""

    name: str
    source_sheet: str
    source: tuple[int, int, int, int]
    anchor: tuple[int, int]
    rows: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    values: tuple[PivotValueField, ...] = ()
    page_fields: tuple[str, ...] = ()
    hidden_items: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    grouping: tuple[tuple[str, str], ...] = ()
    layout: str = "compact"
    subtotals: bool = True
    grand_total_rows: bool = True
    grand_total_columns: bool = True
    source_table: str | None = None
    extent: tuple[int, int, int, int] | None = None
    style: str = "PivotStyleLight16"
    # GETPIVOTDATA reads the last refresh, like Excel's pivot cache.
    cache: Any = field(default=None, compare=False, repr=False)

    def hidden_for(self, field_name: str) -> frozenset[Any]:
        folded = field_name.casefold()
        for name, items in self.hidden_items:
            if name.casefold() == folded:
                return frozenset(_identity(item) for item in items)
        return frozenset()

    def grouping_for(self, field_name: str) -> str:
        folded = field_name.casefold()
        return next((value for name, value in self.grouping if name.casefold() == folded), "none")


@dataclass(slots=True)
class PivotCell:
    """One output cell: its value and its role for formatting."""

    value: Any
    role: str = "value"
    number_format: str | None = None
    indent: int = 0


@dataclass(slots=True)
class PivotResult:
    """The computed grid plus GETPIVOTDATA's lookup index."""

    cells: dict[tuple[int, int], PivotCell] = field(default_factory=dict)
    height: int = 0
    width: int = 0
    lookup: dict[tuple[str, frozenset[tuple[str, Any]]], Any] = field(default_factory=dict)
    table_top: int = 0
    cell_filters: dict[tuple[int, int], frozenset[tuple[str, Any]]] = field(default_factory=dict)


# ------------------------------------------------------------------- source
def _identity(value: Any) -> Any:
    if isinstance(value, str):
        return ("t", value.casefold())
    if isinstance(value, bool):
        return ("b", value)
    if value is None or value == "":
        return ("blank",)
    if isinstance(value, (date, datetime)):
        from duddysheet.core.values import date_serial

        return ("n", date_serial(value))
    if isinstance(value, float) and value.is_integer():
        return ("n", int(value))
    return ("n", value)


def source_rect(workbook: Any, spec: PivotSpec) -> tuple[str, tuple[int, int, int, int]]:
    """Return the source sheet and rectangle, following a source Excel Table."""
    if spec.source_table:
        from duddysheet.core.tables import find_table

        found = find_table(workbook, spec.source_table)
        if found is not None:
            sheet, table = found
            return sheet.name, (table.top, table.left, table.last_data_row, table.right)
    return spec.source_sheet, spec.source


def source_fields(workbook: Any, spec: PivotSpec) -> tuple[str, ...]:
    """Return the source's field names (its header row)."""
    sheet_name, (top, left, _, right) = source_rect(workbook, spec)
    from duddysheet.core.tables import header_names

    return header_names(workbook.get_sheet(sheet_name), top, left, right)


def _records(workbook: Any, spec: PivotSpec) -> tuple[tuple[str, ...], list[list[Any]], list[str]]:
    sheet_name, (top, left, bottom, right) = source_rect(workbook, spec)
    sheet = workbook.get_sheet(sheet_name)
    fields = source_fields(workbook, spec)
    formats = [sheet.effective_format(top + 1, column).number_format for column in range(left, right + 1)]
    records: list[list[Any]] = []
    for row in range(top + 1, bottom + 1):
        values = [
            None if sheet.get_cell(row, column).error is not None else sheet.get_cell(row, column).display_value
            for column in range(left, right + 1)
        ]
        if all(value in (None, "") for value in values):
            continue
        records.append(values)
    return fields, records, formats


def _field_index(fields: tuple[str, ...], name: str) -> int:
    folded = name.casefold()
    for index, candidate in enumerate(fields):
        if candidate.casefold() == folded:
            return index
    raise ValueError(f"The PivotTable field {name!r} is not in the source data.")


def _as_date(value: Any, number_format: str) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        from duddysheet.core.formats import is_date_format
        from duddysheet.core.functions.common import serial_datetime

        if is_date_format(number_format):
            converted = serial_datetime(value)
            return converted if isinstance(converted, datetime) else None
    return None


def _group(value: Any, grouping: str, number_format: str) -> tuple[Any, Any]:
    """Return (display item, sort key) for a field value under date grouping."""
    if grouping != "none":
        moment = _as_date(value, number_format)
        if moment is not None:
            if grouping == "years":
                return moment.year, (0, moment.year)
            if grouping == "quarters":
                quarter = (moment.month - 1) // 3 + 1
                return f"Qtr{quarter}", (0, quarter)
            if grouping == "months":
                return _MONTHS[moment.month - 1], (0, moment.month)
            if grouping == "days":
                return f"{moment.day}-{_MONTHS[moment.month - 1]}", (0, moment.month * 100 + moment.day)
    if value is None or value == "":
        return BLANK, (9, 0)
    from duddysheet.core.functions.array_fn import sort_key

    return value, sort_key(value)


def field_items(workbook: Any, spec: PivotSpec, field_name: str) -> list[Any]:
    """Return a field's distinct items in display order (for filter lists)."""
    fields, records, formats = _records(workbook, spec)
    index = _field_index(fields, field_name)
    grouping = spec.grouping_for(field_name)
    items: dict[Any, tuple[Any, Any]] = {}
    for record in records:
        item, key = _group(record[index], grouping, formats[index])
        items.setdefault(_identity(item), (item, key))
    return [item for item, _ in sorted(items.values(), key=lambda pair: pair[1])]


# -------------------------------------------------------------- aggregation
def summarize(function: str, values: list[Any]) -> Any:
    """Apply a PivotTable summary function to a field's values."""
    if not values:
        return None
    numbers = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if function == "count":
        return sum(value not in (None, "") for value in values)
    if function == "count_numbers":
        return len(numbers)
    if not numbers:
        return None
    if function == "sum":
        total = math.fsum(numbers)
        return int(total) if total.is_integer() and abs(total) < 2**53 else total
    if function == "average":
        return math.fsum(numbers) / len(numbers)
    if function == "max":
        return max(numbers)
    if function == "min":
        return min(numbers)
    if function == "product":
        return math.prod(numbers)
    mean = math.fsum(numbers) / len(numbers)
    squares = math.fsum((value - mean) ** 2 for value in numbers)
    if function in ("stddev", "var"):
        if len(numbers) < 2:
            return None
        variance = squares / (len(numbers) - 1)
    else:
        variance = squares / len(numbers)
    return math.sqrt(variance) if function.startswith("stddev") else variance


# ------------------------------------------------------------------ compute
def compute_pivot(workbook: Any, spec: PivotSpec) -> PivotResult:
    """Compute a PivotTable's output grid (relative to its anchor)."""
    fields, records, formats = _records(workbook, spec)
    for name in spec.rows + spec.columns + spec.page_fields + tuple(item.field for item in spec.values):
        _field_index(fields, name)
    hidden = {name: spec.hidden_for(name) for name in fields}

    def item_of(record: list[Any], name: str) -> tuple[Any, Any]:
        index = _field_index(fields, name)
        return _group(record[index], spec.grouping_for(name), formats[index])

    kept = [
        record
        for record in records
        if all(_identity(item_of(record, name)[0]) not in hidden[name] for name in fields if hidden[name])
    ]
    result = PivotResult()
    row = 0
    # Report filters (page fields) sit above the table.
    for name in spec.page_fields:
        hidden_items = hidden[name]
        all_items = field_items(workbook, replace(spec, hidden_items=()), name)
        visible = [item for item in all_items if _identity(item) not in hidden_items]
        label = "(All)" if not hidden_items else (str(visible[0]) if len(visible) == 1 else "(Multiple Items)")
        result.cells[(row, 0)] = PivotCell(name, "page_field")
        result.cells[(row, 1)] = PivotCell(label, "page_item")
        row += 1
    if spec.page_fields:
        row += 1
    result.table_top = row
    if not (spec.rows or spec.columns or spec.values):
        result.cells[(row, 0)] = PivotCell(spec.name, "header")
        result.cells[(row + 1, 0)] = PivotCell("To build a report, choose fields from the PivotTable Field List.")
        result.height = row + 2
        result.width = 3
        return result
    values = list(spec.values)
    row_keys = _ordered_keys(kept, spec.rows, item_of)
    column_keys = _ordered_keys(kept, spec.columns, item_of)
    groups: dict[tuple[tuple[Any, ...], tuple[Any, ...]], list[list[Any]]] = {}
    for record in kept:
        row_key = tuple(_identity(item_of(record, name)[0]) for name in spec.rows)
        column_key = tuple(_identity(item_of(record, name)[0]) for name in spec.columns)
        groups.setdefault((row_key, column_key), []).append(record)
    cache: dict[tuple[Any, ...], Any] = {}

    def aggregate(value_field: PivotValueField, row_prefix: tuple[Any, ...], column_prefix: tuple[Any, ...]) -> Any:
        key = (value_field.name, row_prefix, column_prefix)
        if key not in cache:
            index = _field_index(fields, value_field.field)
            members = [
                record[index]
                for (row_key, column_key), records_in_group in groups.items()
                if row_key[: len(row_prefix)] == row_prefix and column_key[: len(column_prefix)] == column_prefix
                for record in records_in_group
            ]
            cache[key] = summarize(value_field.function, members)
        return cache[key]

    # Column entries: (kind, items, identities, value field).
    if spec.columns:
        column_entries = [
            (kind, items, identities, value_field)
            for items, identities, kind in _column_paths(column_keys, len(spec.columns), spec)
            for value_field in values
        ]
    else:
        column_entries = [("item", (), (), value_field) for value_field in values]
    tabular = spec.layout == "tabular"
    label_columns = max(1, len(spec.rows)) if tabular else 1
    multiple_values = len(values) > 1
    top = row
    header_rows = (1 + len(spec.columns) + (1 if multiple_values else 0)) if spec.columns else 1
    labels_row = top + header_rows - 1
    if spec.columns:
        result.cells[(top, 0)] = PivotCell(values[0].name if len(values) == 1 else "", "header")
        result.cells[(top, label_columns)] = PivotCell("Column Labels", "header")
    previous_items: tuple[Any, ...] | None = None
    for offset, (kind, items, _, value_field) in enumerate(column_entries):
        column = label_columns + offset
        if spec.columns:
            if kind == "grand":
                caption = "Grand Total" if not multiple_values else f"Total {value_field.name}"
                result.cells[(top + 1, column)] = PivotCell(caption, "header")
            elif kind == "subtotal":
                if value_field is values[0]:
                    result.cells[(top + 1, column)] = PivotCell(f"{items[0]} Total", "header")
            else:
                for level, item in enumerate(items):
                    changed = previous_items is None or previous_items[: level + 1] != items[: level + 1]
                    if changed and value_field is values[0]:
                        result.cells[(top + 1 + level, column)] = PivotCell(item, "header")
                if value_field is values[-1]:
                    previous_items = items
            if multiple_values and kind != "grand":
                result.cells[(labels_row, column)] = PivotCell(value_field.name, "header")
        else:
            result.cells[(labels_row, column)] = PivotCell(value_field.name, "header")
    if tabular and spec.rows:
        for index, name in enumerate(spec.rows):
            result.cells[(labels_row, index)] = PivotCell(name, "header")
    elif spec.rows or not spec.columns:
        result.cells[(labels_row, 0)] = PivotCell("Row Labels" if spec.rows else "", "header")
    row = labels_row + 1
    running: dict[int, float] = {}

    def write_values(target_row: int, row_prefix: tuple[Any, ...], role: str, leaf: bool) -> None:
        for offset, (column_kind, _, column_prefix, value_field) in enumerate(column_entries):
            value = aggregate(value_field, row_prefix, column_prefix)
            if value_field.show_as == "running_total":
                if leaf and column_kind == "item":
                    running[offset] = running.get(offset, 0.0) + (value or 0)
                    display = running[offset]
                else:
                    display = value
            else:
                display = _show_as(value, value_field, aggregate, row_prefix, column_prefix)
            number_format = value_field.number_format or (
                "0.00%" if value_field.show_as.startswith("percent") else None
            )
            if role == "grand_total":
                cell_role = "grand_total"
            elif column_kind == "grand":
                cell_role = "grand_column"
            else:
                cell_role = role
            result.cells[(target_row, label_columns + offset)] = PivotCell(display, cell_role, number_format)
            filters = frozenset(
                list(zip((name.casefold() for name in spec.rows), row_prefix))
                + list(zip((name.casefold() for name in spec.columns), column_prefix))
            )
            result.lookup[(value_field.name.casefold(), filters)] = display
            result.lookup.setdefault((value_field.field.casefold(), filters), display)
            result.cell_filters[(target_row, label_columns + offset)] = filters

    depth = len(spec.rows)
    if depth == 0:
        if values:
            write_values(row, (), "value", True)
            row += 1
    elif tabular:
        previous: tuple[Any, ...] | None = None
        open_items: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
        for items, identities, _ in row_keys:
            split = 0
            if previous is not None:
                while split < depth and previous[split] == identities[split]:
                    split += 1
            # Close finished groups (deepest first) with "X Total" rows.
            while len(open_items) > split:
                group_items, group_ids = open_items.pop()
                if spec.subtotals:
                    result.cells[(row, len(group_ids) - 1)] = PivotCell(f"{group_items[-1]} Total", "subtotal")
                    write_values(row, group_ids, "subtotal", False)
                    row += 1
            for level in range(split, depth):
                result.cells[(row, level)] = PivotCell(items[level], "row_label")
                if level < depth - 1:
                    open_items.append((items[: level + 1], identities[: level + 1]))
            write_values(row, identities, "value", True)
            row += 1
            previous = identities
        while open_items:
            group_items, group_ids = open_items.pop()
            if spec.subtotals:
                result.cells[(row, len(group_ids) - 1)] = PivotCell(f"{group_items[-1]} Total", "subtotal")
                write_values(row, group_ids, "subtotal", False)
                row += 1
    else:
        for items, identities, kind in _row_paths(row_keys, depth, spec):
            level = len(items) - 1
            if kind == "group":
                result.cells[(row, 0)] = PivotCell(items[-1], "group", indent=level)
                if spec.subtotals:
                    write_values(row, identities, "subtotal", False)
                row += 1
                continue
            result.cells[(row, 0)] = PivotCell(items[-1], "row_label", indent=level)
            write_values(row, identities, "value", True)
            row += 1
    if depth and spec.grand_total_rows and values:
        result.cells[(row, 0)] = PivotCell("Grand Total", "grand_total")
        for column in range(1, label_columns):
            result.cells[(row, column)] = PivotCell(None, "grand_total")
        write_values(row, (), "grand_total", False)
        row += 1
    result.height = row
    result.width = label_columns + len(column_entries)
    return result


def _ordered_keys(
    records: list[list[Any]],
    names: tuple[str, ...],
    item_of: Any,
) -> list[tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]]:
    """Distinct (items, identities, sort keys) paths, sorted level by level."""
    paths: dict[tuple[Any, ...], tuple[tuple[Any, ...], tuple[Any, ...]]] = {}
    for record in records:
        pairs = [item_of(record, name) for name in names]
        identities = tuple(_identity(item) for item, _ in pairs)
        paths.setdefault(identities, (tuple(item for item, _ in pairs), tuple(key for _, key in pairs)))
    ordered = sorted(paths.items(), key=lambda entry: entry[1][1])
    return [(items, identities, keys) for identities, (items, keys) in ordered]


def _row_paths(
    keys: list[tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]],
    depth: int,
    spec: PivotSpec,
) -> list[tuple[tuple[Any, ...], tuple[Any, ...], str]]:
    """Compact/outline rows: a header row per outer group, then leaf items."""
    del spec
    emitted: list[tuple[tuple[Any, ...], tuple[Any, ...], str]] = []
    open_groups: list[tuple[Any, ...]] = []
    for items, identities, _ in keys:
        while open_groups and identities[: len(open_groups[-1])] != open_groups[-1]:
            open_groups.pop()
        for level in range(len(open_groups), depth - 1):
            open_groups.append(identities[: level + 1])
            emitted.append((items[: level + 1], identities[: level + 1], "group"))
        emitted.append((items, identities, "item"))
    return emitted


def _column_paths(
    keys: list[tuple[tuple[Any, ...], tuple[Any, ...], tuple[Any, ...]]],
    depth: int,
    spec: PivotSpec,
) -> list[tuple[tuple[Any, ...], tuple[Any, ...], str]]:
    if depth == 0:
        return [((), (), "item")]
    emitted: list[tuple[tuple[Any, ...], tuple[Any, ...], str]] = []
    previous: tuple[Any, ...] | None = None
    for items, identities, _ in keys:
        if spec.subtotals and depth > 1 and previous is not None and previous[:1] != identities[:1]:
            emitted.append((emitted[-1][0][:1], previous[:1], "subtotal"))
        emitted.append((items, identities, "item"))
        previous = identities
    if spec.subtotals and depth > 1 and previous is not None:
        emitted.append((emitted[-1][0][:1], previous[:1], "subtotal"))
    if spec.grand_total_columns:
        emitted.append(((), (), "grand"))
    return emitted


def _show_as(
    value: Any,
    value_field: PivotValueField,
    aggregate: Any,
    row_prefix: tuple[Any, ...],
    column_prefix: tuple[Any, ...],
) -> Any:
    if value_field.show_as in ("normal", "running_total") or value is None:
        return value
    if value_field.show_as == "percent_of_grand_total":
        total = aggregate(value_field, (), ())
    elif value_field.show_as == "percent_of_column_total":
        total = aggregate(value_field, (), column_prefix)
    else:
        total = aggregate(value_field, row_prefix, ())
    if not total:
        return None
    return value / total


# ------------------------------------------------------------------- render
_HEADER_FILL = "#c0e6f5"
_TOTAL_BORDER = BorderStyle("thin", "#156082")


def render_pivot(workbook: Any, sheet_name: str, spec: PivotSpec) -> PivotSpec:
    """Write a PivotTable's output, clearing its previous extent; returns the updated spec."""
    sheet = workbook.get_sheet(sheet_name)
    result = compute_pivot(workbook, spec)
    anchor_row, anchor_column = spec.anchor
    # Report filters render above the anchor when there is room, as in Excel.
    shift = 0
    if spec.page_fields:
        shift = -min(anchor_row, len(spec.page_fields) + 1)
    origin_row = anchor_row + shift
    previous = spec.extent
    new_extent = (
        origin_row,
        anchor_column,
        origin_row + max(result.height, 1) - 1,
        anchor_column + max(result.width, 1) - 1,
    )
    own = set()
    if previous is not None:
        own = {
            (row, column)
            for row in range(previous[0], previous[2] + 1)
            for column in range(previous[1], previous[3] + 1)
        }
    for row in range(new_extent[0], new_extent[2] + 1):
        for column in range(new_extent[1], new_extent[3] + 1):
            if (row, column) in own:
                continue
            cell = sheet.get_cell(row, column)
            if cell.raw_input not in (None, "") or cell.is_spill:
                raise ValueError(
                    "A PivotTable report cannot overlap cells that contain data. "
                    "Move it or clear the destination cells."
                )
    for row, column in own:
        sheet.clear_cell(row, column)
    for (row, column), item in result.cells.items():
        target_row, target_column = origin_row + row, anchor_column + column
        if target_row < 0:
            continue
        sheet.put_cell(target_row, target_column, _styled_cell(item))
    updated = replace(spec, extent=new_extent, cache=result.lookup)
    sheet.pivots = [updated if pivot.name == spec.name else pivot for pivot in sheet.pivots]
    return updated


def _styled_cell(item: PivotCell) -> Any:
    from duddysheet.core.cell import Cell

    value = item.value
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        value = int(value)
    cell_format = CellFormat(number_format=item.number_format or "General", indent=item.indent)
    if item.role == "header":
        cell_format = replace(cell_format, bold=True, fill_color=_HEADER_FILL, bottom_border=_TOTAL_BORDER)
    elif item.role in ("group", "subtotal", "grand_column"):
        cell_format = replace(cell_format, bold=True)
    elif item.role == "grand_total":
        cell_format = replace(cell_format, bold=True, fill_color=_HEADER_FILL, top_border=_TOTAL_BORDER)
    elif item.role == "page_field":
        cell_format = replace(cell_format, bold=True)
    if value is None:
        return Cell(format=cell_format) if not cell_format.is_default else Cell()
    return Cell(raw_input=value, cached_value=value, format=cell_format)


def pivot_at(sheet: Any, row: int, column: int) -> PivotSpec | None:
    """Return the PivotTable whose output covers a cell."""
    for pivot in sheet.pivots:
        if pivot.extent is not None:
            top, left, bottom, right = pivot.extent
            if top <= row <= bottom and left <= column <= right:
                return pivot
    return None


def next_pivot_name(workbook: Any) -> str:
    used = {pivot.name.casefold() for sheet in workbook for pivot in sheet.pivots}
    number = 1
    while f"pivottable{number}" in used:
        number += 1
    return f"PivotTable{number}"


def detail_records(workbook: Any, spec: PivotSpec, filters: dict[str, Any]) -> list[list[Any]]:
    """Return the source rows behind one value (Show Details / double-click)."""
    fields, records, formats = _records(workbook, spec)
    selected = [list(fields)]
    for record in records:
        keep = True
        for name, item in filters.items():
            index = _field_index(fields, name)
            grouped, _ = _group(record[index], spec.grouping_for(name), formats[index])
            if _identity(grouped) != _identity(item):
                keep = False
                break
        if keep:
            selected.append(record)
    return selected


def details_at(workbook: Any, spec: PivotSpec, row: int, column: int) -> list[list[Any]] | None:
    """Source rows behind the value at a sheet cell (Show Details), or None."""
    if spec.extent is None:
        return None
    result = compute_pivot(workbook, spec)
    origin_row = spec.extent[0]
    filters = result.cell_filters.get((row - origin_row, column - spec.anchor[1]))
    if filters is None:
        return None
    fields, records, formats = _records(workbook, spec)
    hidden = {name: spec.hidden_for(name) for name in fields}
    selected = [list(fields)]
    for record in records:
        keep = True
        for index, name in enumerate(fields):
            item, _ = _group(record[index], spec.grouping_for(name), formats[index])
            identity = _identity(item)
            if identity in hidden[name]:
                keep = False
                break
            wanted = next((value for key, value in filters if key == name.casefold()), None)
            if wanted is not None and identity != wanted:
                keep = False
                break
        if keep:
            selected.append(record)
    return selected


def getpivotdata(workbook: Any, spec: PivotSpec, data_field: str, pairs: list[tuple[str, Any]]) -> Any:
    """Return a value from a PivotTable for GETPIVOTDATA (as of its last refresh)."""
    lookup = spec.cache if spec.cache is not None else compute_pivot(workbook, spec).lookup
    filters = frozenset((name.casefold(), _identity(item)) for name, item in pairs)
    key = (data_field.casefold(), filters)
    if key in lookup:
        return lookup[key]
    for value_field in spec.values:
        if data_field.casefold() in (value_field.field.casefold(), value_field.name.casefold()):
            alternate = (value_field.name.casefold(), filters)
            if alternate in lookup:
                return lookup[alternate]
    raise KeyError(data_field)


# ---------------------------------------------------------------- persistence
def pivot_to_dict(spec: PivotSpec) -> dict[str, Any]:
    from duddysheet.io.native import _encode_value

    return {
        "name": spec.name,
        "source_sheet": spec.source_sheet,
        "source": list(spec.source),
        "anchor": list(spec.anchor),
        "rows": list(spec.rows),
        "columns": list(spec.columns),
        "values": [
            {
                "field": item.field,
                "function": item.function,
                "show_as": item.show_as,
                "caption": item.caption,
                "number_format": item.number_format,
            }
            for item in spec.values
        ],
        "page_fields": list(spec.page_fields),
        "hidden_items": [[name, [_encode_value(item) for item in items]] for name, items in spec.hidden_items],
        "grouping": [list(item) for item in spec.grouping],
        "layout": spec.layout,
        "subtotals": spec.subtotals,
        "grand_total_rows": spec.grand_total_rows,
        "grand_total_columns": spec.grand_total_columns,
        "source_table": spec.source_table,
        "extent": list(spec.extent) if spec.extent else None,
        "style": spec.style,
    }


def pivot_from_dict(data: dict[str, Any]) -> PivotSpec:
    from duddysheet.io.native import _decode_value

    return PivotSpec(
        name=str(data["name"]),
        source_sheet=str(data["source_sheet"]),
        source=tuple(data["source"]),
        anchor=tuple(data["anchor"]),
        rows=tuple(data.get("rows", ())),
        columns=tuple(data.get("columns", ())),
        values=tuple(PivotValueField(**item) for item in data.get("values", ())),
        page_fields=tuple(data.get("page_fields", ())),
        hidden_items=tuple((name, tuple(_decode_value(item) for item in items)) for name, items in data.get("hidden_items", ())),
        grouping=tuple(tuple(item) for item in data.get("grouping", ())),
        layout=data.get("layout", "compact"),
        subtotals=bool(data.get("subtotals", True)),
        grand_total_rows=bool(data.get("grand_total_rows", True)),
        grand_total_columns=bool(data.get("grand_total_columns", True)),
        source_table=data.get("source_table"),
        extent=tuple(data["extent"]) if data.get("extent") else None,
        style=data.get("style", "PivotStyleLight16"),
    )
