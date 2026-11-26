"""Excel objects added to, and read from, the XLSX package after openpyxl.

openpyxl handles cells, styles, and classic charts. Sparklines, Office 2016
charts, PivotTables, pictures, and shapes are written into the saved package
and read back from it here, so a workbook keeps them through ``.xlsx``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from duddysheet.core.refs import CellReference, RangeReference, parse_a1
from duddysheet.core.sparkline import Sparkline
from duddysheet.io.xlsx_package import XlsxPackage, quote_sheet, xml_text

SPARKLINE_EXT_URI = "{05C60535-1F16-4fd2-B633-F4F36F0B64E0}"
X14_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM_NS = "http://schemas.microsoft.com/office/excel/2006/main"
_SPARKLINE_TYPES = {"line": None, "column": "column", "win_loss": "stacked"}
_SPARKLINE_FLAGS = (
    ("show_markers", "markers"),
    ("show_high", "high"),
    ("show_low", "low"),
    ("show_first", "first"),
    ("show_last", "last"),
    ("show_negative", "negative"),
    ("show_axis", "displayXAxis"),
)


def write_package_extras(path: str | Path, workbook: Any, pending_charts: dict[str, list[Any]]) -> None:
    """Add the objects openpyxl cannot write to a saved XLSX file."""
    from duddysheet.io.xlsx_charts import add_chartex_charts
    from duddysheet.io.xlsx_drawings import add_drawings
    from duddysheet.io.xlsx_pivots import add_pivot_tables

    needs_charts = any(pending_charts.values())
    needs_sparklines = any(sheet.sparklines for sheet in workbook)
    needs_pivots = any(getattr(sheet, "pivots", None) for sheet in workbook)
    needs_drawings = any(getattr(sheet, "drawings", None) for sheet in workbook)
    needs_comments = any(getattr(sheet, "comments", None) for sheet in workbook)
    if not (needs_charts or needs_sparklines or needs_pivots or needs_drawings or needs_comments):
        return
    package = XlsxPackage(path)
    if needs_charts:
        add_chartex_charts(package, workbook, pending_charts)
    if needs_sparklines:
        _add_sparklines(package, workbook)
    if needs_pivots:
        add_pivot_tables(package, workbook)
    if needs_drawings:
        add_drawings(package, workbook)
    if needs_comments:
        from duddysheet.io.xlsx_comments import write_threaded_comments

        write_threaded_comments(package, workbook)
    package.save()


def read_package_extras(path: str | Path, workbook: Any, warnings: list[str]) -> None:
    """Read sparklines, Office 2016 charts, pictures, and shapes from a file."""
    from duddysheet.io.xlsx_charts import read_chartex_charts
    from duddysheet.io.xlsx_comments import read_threaded_comments
    from duddysheet.io.xlsx_drawings import read_drawings

    try:
        package = XlsxPackage(path)
        parts = package.sheet_parts()
    except (OSError, KeyError, ValueError):
        return
    for sheet in workbook:
        part = parts.get(sheet.name)
        if part is None or part not in package.entries:
            continue
        sheet.sparklines.extend(_read_sparklines(package.text(part), sheet.name))
        sheet.charts.extend(read_chartex_charts(package, part, sheet.name))
        read_drawings(package, part, sheet, warnings)
        read_threaded_comments(package, part, sheet)


# ---------------------------------------------------------------- sparklines
def _color(value: str) -> str:
    return "FF" + value.lstrip("#").upper()


def _group_key(sparkline: Sparkline) -> tuple[Any, ...]:
    return (
        sparkline.kind,
        sparkline.color,
        sparkline.negative_color,
        sparkline.marker_color,
        *(getattr(sparkline, name) for name, _attribute in _SPARKLINE_FLAGS),
    )


def sparkline_groups_xml(sheet: Any) -> str:
    """Return the worksheet ``<ext>`` element holding the sheet's sparklines."""
    groups: dict[tuple[Any, ...], list[Sparkline]] = {}
    for sparkline in sheet.sparklines:
        if isinstance(sparkline, Sparkline):
            groups.setdefault(_group_key(sparkline), []).append(sparkline)
    body = []
    for items in groups.values():
        first = items[0]
        attributes = ['displayEmptyCellsAs="gap"']
        kind = _SPARKLINE_TYPES[first.kind]
        if kind:
            attributes.insert(0, f'type="{kind}"')
        attributes.extend(f'{attribute}="1"' for name, attribute in _SPARKLINE_FLAGS if getattr(first, name))
        marker = _color(first.marker_color)
        colors = (
            f'<x14:colorSeries rgb="{_color(first.color)}"/>'
            f'<x14:colorNegative rgb="{_color(first.negative_color)}"/>'
            '<x14:colorAxis rgb="FF000000"/>'
            f'<x14:colorMarkers rgb="{marker}"/><x14:colorFirst rgb="{marker}"/>'
            f'<x14:colorLast rgb="{marker}"/><x14:colorHigh rgb="{marker}"/><x14:colorLow rgb="{marker}"/>'
        )
        lines = []
        for item in items:
            data = item.data_range
            data_sheet = data.sheet or sheet.name
            reference = f"{quote_sheet(data_sheet)}!{RangeReference(CellReference(data.min_row, data.min_column), CellReference(data.max_row, data.max_column)).to_a1()}"
            location = CellReference(item.row, item.column).to_a1(include_sheet=False)
            lines.append(
                f"<x14:sparkline><xm:f>{xml_text(reference)}</xm:f><xm:sqref>{location}</xm:sqref></x14:sparkline>"
            )
        body.append(
            f"<x14:sparklineGroup {' '.join(attributes)}>{colors}<x14:sparklines>{''.join(lines)}</x14:sparklines></x14:sparklineGroup>"
        )
    return (
        f'<ext uri="{SPARKLINE_EXT_URI}" xmlns:x14="{X14_NS}">'
        f'<x14:sparklineGroups xmlns:xm="{XM_NS}">{"".join(body)}</x14:sparklineGroups></ext>'
    )


def _add_sparklines(package: XlsxPackage, workbook: Any) -> None:
    parts = package.sheet_parts()
    for sheet in workbook:
        if not sheet.sparklines or sheet.name not in parts:
            continue
        package.add_worksheet_extension(parts[sheet.name], sparkline_groups_xml(sheet))


def _read_sparklines(xml: str, sheet_name: str) -> list[Sparkline]:
    result: list[Sparkline] = []
    for group in re.finditer(r"<(\w+):sparklineGroup\b([^>]*)>(.*?)</\1:sparklineGroup>", xml, re.DOTALL):
        attributes = dict(re.findall(r'(\w+)="([^"]*)"', group.group(2)))
        body = group.group(3)
        kind = {"column": "column", "stacked": "win_loss"}.get(attributes.get("type", "line"), "line")
        colors = {
            name: "#" + value[-6:].lower()
            for name, value in re.findall(r'<\w+:color(\w+)\b[^>]*\brgb="([0-9A-Fa-f]{6,8})"', body)
        }
        options: dict[str, Any] = {
            name: attributes.get(attribute) in ("1", "true") for name, attribute in _SPARKLINE_FLAGS
        }
        for key, name in (("Series", "color"), ("Negative", "negative_color"), ("Markers", "marker_color")):
            if key in colors:
                options[name] = colors[key]
        for formula, location in re.findall(
            r"<\w+:sparkline>\s*<\w+:f>([^<]*)</\w+:f>\s*<\w+:sqref>([^<]*)</\w+:sqref>", body
        ):
            try:
                data = parse_a1(_unescape(formula).replace("$", ""), default_sheet=sheet_name)
                cell = parse_a1(location.split()[0], default_sheet=sheet_name)
            except (ValueError, KeyError):
                continue
            if isinstance(data, CellReference):
                data = RangeReference(data, data)
            if not isinstance(data, RangeReference) or not isinstance(cell, CellReference):
                continue
            if data.sheet == sheet_name:
                data = RangeReference(
                    CellReference(data.min_row, data.min_column),
                    CellReference(data.max_row, data.max_column),
                )
            try:
                result.append(Sparkline(cell.row, cell.column, data, kind, **options))
            except ValueError:
                continue
    return result


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
