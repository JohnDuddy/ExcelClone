"""PivotTables in XLSX: written as Excel PivotTables and read back.

Each PivotTable is written with a pivot cache (definition and records) and a
PivotTable definition that Excel refreshes when the file opens, so the report
stays a working PivotTable in Excel. Reading maps Excel's PivotTable
definitions back to ``PivotSpec`` so they stay refreshable here too.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from openpyxl.utils import get_column_letter

from duddysheet.core.pivot import (
    BLANK,
    PivotSpec,
    PivotValueField,
    compute_pivot,
    item_identity,
    source_fields,
    source_rect,
    source_records,
)
from duddysheet.io.xlsx_package import RELATIONSHIPS_NS, XlsxPackage, xml_text

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
CACHE_DEFINITION_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml"
CACHE_RECORDS_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheRecords+xml"
PIVOT_TABLE_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml"
_FUNCTIONS = {
    "sum": "sum",
    "count": "count",
    "average": "average",
    "max": "max",
    "min": "min",
    "product": "product",
    "count_numbers": "countNums",
    "stddev": "stdDev",
    "stddevp": "stdDevp",
    "var": "var",
    "varp": "varp",
}
_FUNCTIONS_BACK = {value: key for key, value in _FUNCTIONS.items()}
_SHOW_AS = {
    "percent_of_grand_total": "percentOfTotal",
    "percent_of_column_total": "percentOfCol",
    "percent_of_row_total": "percentOfRow",
    "running_total": "runTotal",
}
_SHOW_AS_BACK = {value: key for key, value in _SHOW_AS.items()}
_GROUP_BY = {"years": "years", "quarters": "quarters", "months": "months", "days": "days"}
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def add_pivot_tables(package: XlsxPackage, workbook: Any) -> None:
    """Write each PivotTable with its cache definition and records."""
    sheet_parts = package.sheet_parts()
    cache_id = 0
    for sheet in workbook:
        for spec in getattr(sheet, "pivots", None) or []:
            if not isinstance(spec, PivotSpec) or spec.extent is None or sheet.name not in sheet_parts:
                continue
            try:
                parts = _pivot_parts(workbook, spec, package.number_format_id)
            except (ValueError, KeyError):
                continue
            cache_id += 1
            definition = package.next_part("xl/pivotCache/pivotCacheDefinition{}.xml")
            records = definition.replace("pivotCacheDefinition", "pivotCacheRecords")
            table = package.next_part("xl/pivotTables/pivotTable{}.xml")
            package.set_text(records, parts["records"])
            package.add_override(records, CACHE_RECORDS_TYPE)
            package.set_text(definition, "")
            package.add_override(definition, CACHE_DEFINITION_TYPE)
            records_rel = package.add_relationship(
                definition, f"{RELATIONSHIPS_NS}/pivotCacheRecords", records
            )
            package.set_text(definition, parts["definition"].replace("__RECORDS__", records_rel))
            package.add_pivot_cache(cache_id, definition)
            package.set_text(table, parts["table"].replace("__CACHE_ID__", str(cache_id)))
            package.add_override(table, PIVOT_TABLE_TYPE)
            package.add_relationship(table, f"{RELATIONSHIPS_NS}/pivotCacheDefinition", definition)
            package.add_relationship(sheet_parts[sheet.name], f"{RELATIONSHIPS_NS}/pivotTable", table)


def _a1(top: int, left: int, bottom: int, right: int) -> str:
    return f"{get_column_letter(left + 1)}{top + 1}:{get_column_letter(right + 1)}{bottom + 1}"


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def _as_moment(value: Any, number_format: str) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        from duddysheet.core.formats import is_date_format
        from duddysheet.core.functions.common import serial_datetime

        if is_date_format(number_format):
            converted = serial_datetime(value)
            return converted if isinstance(converted, datetime) else None
    return None


class _CacheField:
    """One cache field: its shared items (when listed) and type flags."""

    def __init__(self, name: str, values: list[Any], number_format: str, listed: bool, grouping: str) -> None:
        self.name = name
        self.number_format = number_format
        self.grouping = grouping
        self.listed = listed or grouping != "none"
        self.items: list[tuple[str, Any]] = []
        self.index: dict[tuple[str, Any], int] = {}
        self.kinds: set[str] = set()
        self.numbers: list[float] = []
        self.dates: list[datetime] = []
        self.long_text = False
        for value in values:
            item = self.item(value)
            self.kinds.add(item[0])
            if item[0] == "n":
                self.numbers.append(item[1])
            elif item[0] == "d":
                self.dates.append(item[1])
            elif item[0] == "s" and len(item[1]) > 255:
                self.long_text = True
            if self.listed and item not in self.index:
                self.index[item] = len(self.items)
                self.items.append(item)

    def item(self, value: Any) -> tuple[str, Any]:
        if value is None or value == "":
            return ("m", None)
        if isinstance(value, bool):
            return ("b", value)
        moment = _as_moment(value, self.number_format) if self.grouping != "none" or isinstance(value, (date, datetime)) else None
        if moment is not None:
            return ("d", moment)
        if isinstance(value, (int, float)) and math.isfinite(value):
            return ("n", float(value))
        return ("s", str(value))

    def record(self, value: Any) -> str:
        item = self.item(value)
        if self.listed:
            return f'<x v="{self.index[item]}"/>'
        return _item_xml(item)

    def xml(self, field_index: int) -> str:
        attributes: list[str] = []
        kinds = self.kinds - {"m"}
        has_text = "s" in kinds
        if "m" in self.kinds:
            attributes.append('containsBlank="1"')
        if not has_text and kinds:
            attributes.append('containsSemiMixedTypes="0"')
            attributes.append('containsString="0"')
        if "n" in kinds:
            attributes.append('containsNumber="1"')
            if all(number == int(number) for number in self.numbers):
                attributes.append('containsInteger="1"')
            attributes.append(f'minValue="{_number(min(self.numbers))}" maxValue="{_number(max(self.numbers))}"')
        if "d" in kinds:
            attributes.append('containsDate="1"')
            if kinds == {"d"}:
                attributes.append('containsNonDate="0"')
            attributes.append(f'minDate="{_iso(min(self.dates))}" maxDate="{_iso(max(self.dates))}"')
        if len(kinds) > 1:
            attributes.append('containsMixedTypes="1"')
        if self.long_text:
            attributes.append('longText="1"')
        body = ""
        if self.listed and self.grouping == "none":
            body = "".join(_item_xml(item) for item in self.items)
            attributes.append(f'count="{len(self.items)}"')
        shared = f"<sharedItems {' '.join(attributes)}>{body}</sharedItems>" if body or self.listed and self.grouping == "none" else f"<sharedItems {' '.join(attributes)}/>"
        group = self.group_xml(field_index) if self.grouping != "none" and self.dates else ""
        number_format = ' numFmtId="14"' if self.dates else ' numFmtId="0"'
        return f'<cacheField name="{xml_text(self.name)}"{number_format}>{shared}{group}</cacheField>'

    def group_labels(self) -> list[str]:
        start, end = min(self.dates), max(self.dates)
        if self.grouping == "years":
            labels = [str(year) for year in range(start.year, end.year + 1)]
        elif self.grouping == "quarters":
            labels = [f"Qtr{quarter}" for quarter in range(1, 5)]
        elif self.grouping == "months":
            labels = list(_MONTHS)
        else:
            labels = [f"{day}-{_MONTHS[month - 1]}" for month, days in enumerate((31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31), 1) for day in range(1, days + 1)]
        return [f"<{start.month}/{start.day}/{start.year}", *labels, f">{end.month}/{end.day}/{end.year}"]

    def group_index(self, value: Any) -> int | None:
        moment = _as_moment(value, self.number_format)
        if moment is None:
            return None
        labels = self.group_labels()[1:-1]
        if self.grouping == "years":
            label = str(moment.year)
        elif self.grouping == "quarters":
            label = f"Qtr{(moment.month - 1) // 3 + 1}"
        elif self.grouping == "months":
            label = _MONTHS[moment.month - 1]
        else:
            label = f"{moment.day}-{_MONTHS[moment.month - 1]}"
        return labels.index(label) + 1

    def group_xml(self, field_index: int) -> str:
        start, end = min(self.dates), max(self.dates)
        labels = self.group_labels()
        items = "".join(f'<s v="{xml_text(label)}"/>' for label in labels)
        end_date = datetime(end.year, end.month, end.day) if end.hour == end.minute == 0 else end
        return (
            f'<fieldGroup base="{field_index}"><rangePr groupBy="{_GROUP_BY[self.grouping]}" '
            f'startDate="{_iso(start)}" endDate="{_iso(end_date)}"/>'
            f'<groupItems count="{len(labels)}">{items}</groupItems></fieldGroup>'
        )

    @property
    def axis_count(self) -> int:
        if self.grouping != "none" and self.dates:
            return len(self.group_labels())
        return len(self.items)


def _number(value: float) -> str:
    return str(int(value)) if value == int(value) and abs(value) < 1e15 else repr(value)


def _item_xml(item: tuple[str, Any]) -> str:
    kind, value = item
    if kind == "m":
        return "<m/>"
    if kind == "b":
        return f'<b v="{int(value)}"/>'
    if kind == "d":
        return f'<d v="{_iso(value)}"/>'
    if kind == "n":
        return f'<n v="{_number(value)}"/>'
    return f'<s v="{xml_text(value)}"/>'


def _pivot_parts(workbook: Any, spec: PivotSpec, format_id: Any) -> dict[str, str]:
    source_names, records, formats = source_records(workbook, spec)
    calculated = list(spec.calculated_fields)
    fields = tuple(source_names) + tuple(name for name, _formula in calculated)
    sheet_name, (top, left, bottom, right) = source_rect(workbook, spec)
    axis_names = {name.casefold() for name in spec.rows + spec.columns + spec.page_fields}
    lookup = {name.casefold(): index for index, name in enumerate(fields)}
    cache_fields = [
        _CacheField(
            name,
            [record[index] for record in records],
            formats[index],
            name.casefold() in axis_names,
            spec.grouping_for(name) if name.casefold() in axis_names else "none",
        )
        for index, name in enumerate(source_names)
    ]
    # -- cache definition and records
    source = (
        f'<worksheetSource name="{xml_text(spec.source_table)}"/>'
        if spec.source_table
        else f'<worksheetSource ref="{_a1(top, left, bottom, right)}" sheet="{xml_text(sheet_name)}"/>'
    )
    definition = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<pivotCacheDefinition xmlns="{MAIN_NS}" xmlns:r="{RELATIONSHIPS_NS}" r:id="__RECORDS__" '
        f'refreshOnLoad="1" createdVersion="6" refreshedVersion="6" minRefreshableVersion="3" recordCount="{len(records)}">'
        f'<cacheSource type="worksheet">{source}</cacheSource>'
        f'<cacheFields count="{len(fields)}">'
        + "".join(field.xml(index) for index, field in enumerate(cache_fields))
        + "".join(
            f'<cacheField name="{xml_text(name)}" numFmtId="0" formula="{xml_text(formula.lstrip("=").strip())}" databaseField="0"/>'
            for name, formula in calculated
        )
        + "</cacheFields></pivotCacheDefinition>"
    )
    rows_xml = "".join(
        "<r>" + "".join(field.record(record[index]) for index, field in enumerate(cache_fields)) + "</r>"
        for record in records
    )
    records_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<pivotCacheRecords xmlns="{MAIN_NS}" xmlns:r="{RELATIONSHIPS_NS}" count="{len(records)}">{rows_xml}</pivotCacheRecords>'
    )
    # -- table definition
    tabular = spec.layout == "tabular"
    compact = spec.layout == "compact"
    pivot_fields = []
    data_fields = {lookup[item.field.casefold()] for item in spec.values}
    for index, name in enumerate(fields):
        if index >= len(cache_fields):
            used = ' dataField="1"' if index in data_fields else ""
            pivot_fields.append(f'<pivotField{used} dragToRow="0" dragToCol="0" dragToPage="0" showAll="0" defaultSubtotal="0"/>')
            continue
        field = cache_fields[index]
        folded = name.casefold()
        attributes = []
        if folded in {item.casefold() for item in spec.rows}:
            attributes.append('axis="axisRow"')
        elif folded in {item.casefold() for item in spec.columns}:
            attributes.append('axis="axisCol"')
        elif folded in {item.casefold() for item in spec.page_fields}:
            attributes.append('axis="axisPage"')
        if index in data_fields:
            attributes.append('dataField="1"')
        if not compact:
            attributes.append('compact="0"')
        if tabular:
            attributes.append('outline="0"')
        attributes.append('showAll="0"')
        if not spec.subtotals:
            attributes.append('defaultSubtotal="0"')
        items = ""
        if attributes[0].startswith("axis="):
            hidden = spec.hidden_for(name)
            entries = []
            if field.grouping != "none" and field.dates:
                for position, label in enumerate(field.group_labels()):
                    entries.append(f'<item x="{position}"/>')
            else:
                for position, (kind, value) in enumerate(field.items):
                    flag = ' h="1"' if item_identity(BLANK if kind == "m" else value) in hidden else ""
                    entries.append(f'<item x="{position}"{flag}/>')
            if spec.subtotals:
                entries.append('<item t="default"/>')
            items = f'<items count="{len(entries)}">{"".join(entries)}</items>'
        pivot_fields.append(f"<pivotField {' '.join(attributes)}>{items}</pivotField>" if items else f"<pivotField {' '.join(attributes)}/>")
    row_fields = [lookup[name.casefold()] for name in spec.rows]
    column_fields = [lookup[name.casefold()] for name in spec.columns]
    if len(spec.values) > 1:
        column_fields.append(-2)
    page_fields = [lookup[name.casefold()] for name in spec.page_fields]
    result = compute_pivot(workbook, spec)
    extent_top, extent_left, extent_bottom, extent_right = spec.extent
    location_top = extent_top + result.table_top
    location = _a1(location_top, extent_left, max(location_top, extent_bottom), extent_right)
    first_data_col = 1 if compact or not spec.rows else len(spec.rows)
    has_column_header = bool(spec.columns) or len(spec.values) > 1
    first_header_row = 1 if has_column_header or spec.values else 0
    first_data_row = 2 if has_column_header else 1
    location_attributes = (
        f'ref="{location}" firstHeaderRow="{first_header_row}" firstDataRow="{first_data_row}" firstDataCol="{first_data_col}"'
    )
    if page_fields:
        location_attributes += f' rowPageCount="{len(page_fields)}" colPageCount="1"'
    data_xml = []
    for item in spec.values:
        attributes = [f'name="{xml_text(item.name)}"', f'fld="{lookup[item.field.casefold()]}"']
        if item.function != "sum":
            attributes.append(f'subtotal="{_FUNCTIONS[item.function]}"')
        if item.show_as in _SHOW_AS:
            attributes.append(f'showDataAs="{_SHOW_AS[item.show_as]}"')
        base = row_fields[0] if row_fields else 0
        if item.number_format:
            attributes.append(f'numFmtId="{format_id(item.number_format)}"')
        attributes.append(f'baseField="{base}" baseItem="0"')
        data_xml.append(f"<dataField {' '.join(attributes)}/>")
    table_attributes = [
        f'name="{xml_text(spec.name)}"',
        'cacheId="__CACHE_ID__"',
        'applyNumberFormats="0" applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0"',
        'applyAlignmentFormats="0" applyWidthHeightFormats="1" dataCaption="Values"',
        'updatedVersion="6" minRefreshableVersion="3" useAutoFormatting="1" itemPrintTitles="1"',
        'createdVersion="6" indent="0" outline="1" outlineData="1" multipleFieldFilters="0"',
    ]
    if not compact:
        table_attributes.append('compact="0" compactData="0"')
    if tabular:
        table_attributes.append('gridDropZones="0"')
    if not spec.grand_total_rows:
        table_attributes.append('rowGrandTotals="0"')
    if not spec.grand_total_columns:
        table_attributes.append('colGrandTotals="0"')
    parts = [f"<location {location_attributes}/>", f'<pivotFields count="{len(pivot_fields)}">{"".join(pivot_fields)}</pivotFields>']
    if row_fields:
        parts.append(f'<rowFields count="{len(row_fields)}">' + "".join(f'<field x="{index}"/>' for index in row_fields) + "</rowFields>")
    if column_fields:
        parts.append(f'<colFields count="{len(column_fields)}">' + "".join(f'<field x="{index}"/>' for index in column_fields) + "</colFields>")
    if page_fields:
        parts.append(f'<pageFields count="{len(page_fields)}">' + "".join(f'<pageField fld="{index}" hier="-1"/>' for index in page_fields) + "</pageFields>")
    if data_xml:
        parts.append(f'<dataFields count="{len(data_xml)}">{"".join(data_xml)}</dataFields>')
    parts.append(
        f'<pivotTableStyleInfo name="{xml_text(spec.style)}" showRowHeaders="1" showColHeaders="1" '
        'showRowStripes="0" showColStripes="0" showLastColumn="1"/>'
    )
    table = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<pivotTableDefinition xmlns="{MAIN_NS}" {" ".join(table_attributes)}>{"".join(parts)}</pivotTableDefinition>'
    )
    return {"definition": definition, "records": records_xml, "table": table}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_pivot_tables(package: Any, workbook: Any, warnings: list[str], formats: dict[int, str] | None = None) -> None:
    """Rebuild Excel PivotTables (read by openpyxl) as refreshable PivotTables."""
    for worksheet in package.worksheets:
        pivots = getattr(worksheet, "_pivots", None) or []
        if not pivots:
            continue
        sheet = workbook.get_sheet(worksheet.title)
        dropped = 0
        for definition in pivots:
            spec = _spec_from_definition(definition, workbook, worksheet.title, formats or {})
            if spec is None:
                dropped += 1
                continue
            sheet.pivots.append(spec)
        if dropped:
            warnings.append(
                f"{dropped} PivotTable(s) on sheet {worksheet.title!r} use an external or "
                "unsupported source and were imported as values."
            )


def _spec_from_definition(definition: Any, workbook: Any, host: str, formats: dict[int, str]) -> PivotSpec | None:
    from duddysheet.core.refs import CellReference, RangeReference, parse_a1

    cache = definition.cache
    source = getattr(getattr(cache, "cacheSource", None), "worksheetSource", None)
    if source is None:
        return None
    source_table = None
    if source.name:
        from duddysheet.core.tables import find_table

        found = find_table(workbook, source.name)
        if found is None:
            return None
        source_sheet, table = found
        source_table = table.name
        sheet_name = source_sheet.name
        rect = (table.top, table.left, table.last_data_row, table.right)
    else:
        if not source.ref:
            return None
        sheet_name = source.sheet or host
        if sheet_name not in workbook.sheet_names:
            return None
        reference = parse_a1(source.ref)
        if isinstance(reference, CellReference) or not isinstance(reference, RangeReference):
            return None
        rect = (reference.min_row, reference.min_column, reference.max_row, reference.max_column)
    names = [field.name for field in cache.cacheFields]
    location = parse_a1(definition.location.ref)
    if isinstance(location, CellReference):
        location = RangeReference(location, location)

    def name_of(index: int) -> str | None:
        return names[index] if 0 <= index < len(names) else None

    rows = tuple(name for field in (definition.rowFields or []) if (name := name_of(field.x)))
    columns = tuple(name for field in (definition.colFields or []) if (name := name_of(field.x)))
    pages = tuple(name for field in (definition.pageFields or []) if (name := name_of(field.fld)))
    calculated = tuple(
        (field.name, "=" + field.formula)
        for field in cache.cacheFields
        if getattr(field, "formula", None) and field.databaseField is False
    )
    values = []
    for data in definition.dataFields or []:
        name = name_of(data.fld)
        if name is None:
            continue
        function = _FUNCTIONS_BACK.get(data.subtotal or "sum", "sum")
        show_as = _SHOW_AS_BACK.get(data.showDataAs or "normal", "normal")
        caption = data.name if data.name and data.name != PivotValueField(name, function).name else None
        number_format = formats.get(data.numFmtId) if data.numFmtId else None
        values.append(PivotValueField(name, function, show_as, caption, number_format))
    hidden: list[tuple[str, tuple[Any, ...]]] = []
    grouping: list[tuple[str, str]] = []
    for index, field in enumerate(definition.pivotFields or []):
        if index >= len(names):
            break
        cache_field = cache.cacheFields[index]
        if getattr(cache_field, "databaseField", True) is False:
            continue
        group = getattr(cache_field, "fieldGroup", None)
        range_pr = getattr(group, "rangePr", None) if group is not None else None
        if range_pr is not None and range_pr.groupBy in _GROUP_BY:
            grouping.append((names[index], range_pr.groupBy))
            continue
        shared = []
        if cache_field.sharedItems is not None:
            for item in cache_field.sharedItems._fields:
                value = getattr(item, "v", None)
                if item.tagname == "m":
                    value = BLANK
                elif item.tagname == "n" and value is not None and float(value) == int(float(value)):
                    value = int(float(value))
                shared.append(value)
        hidden_items = tuple(
            shared[item.x]
            for item in (field.items or [])
            if item.h and item.x is not None and item.x < len(shared)
        )
        if hidden_items:
            hidden.append((names[index], hidden_items))
    layout = "compact"
    pivot_fields = list(definition.pivotFields or [])
    axis_fields = [pivot_fields[names.index(name)] for name in rows if names.index(name) < len(pivot_fields)]
    if axis_fields and all(field.compact is False for field in axis_fields):
        layout = "tabular" if all(field.outline is False for field in axis_fields) else "outline"
    subtotals = not axis_fields or any(field.defaultSubtotal is not False for field in axis_fields)
    page_offset = len(pages) + 1 if pages else 0
    anchor = (location.min_row, location.min_column)
    spec = PivotSpec(
        name=definition.name or "PivotTable1",
        source_sheet=sheet_name,
        source=rect,
        anchor=anchor,
        rows=rows,
        columns=columns,
        values=tuple(values),
        page_fields=pages,
        hidden_items=tuple(hidden),
        grouping=tuple(grouping),
        layout=layout,
        subtotals=subtotals,
        grand_total_rows=definition.rowGrandTotals is not False,
        grand_total_columns=definition.colGrandTotals is not False,
        source_table=source_table,
        extent=(max(0, location.min_row - page_offset), location.min_column, location.max_row, location.max_column),
        style=getattr(definition.pivotTableStyleInfo, "name", None) or "PivotStyleLight16",
        calculated_fields=calculated,
    )
    try:
        source_fields(workbook, spec)
    except (ValueError, KeyError):
        return None
    return spec
