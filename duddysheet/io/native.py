"""Lossless versioned Duddy Spreadsheet ZIP/JSON serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from duddysheet.core.cell import (
    BorderStyle,
    Cell,
    CellFormat,
    Hyperlink,
    Note,
    SheetProtection,
)
from duddysheet.core.chart import ChartSpec
from duddysheet.core.conditional import ConditionalRule, FormatPatch
from duddysheet.core.data_tools import AutoFilter, DataValidation
from duddysheet.core.printing import setup_from_dict, setup_to_dict
from duddysheet.core.refs import RangeReference, parse_a1
from duddysheet.core.sparkline import Sparkline
from duddysheet.core.data_table import data_table_from_dict, data_table_to_dict
from duddysheet.core.pivot import pivot_from_dict, pivot_to_dict
from duddysheet.core.tables import table_from_dict, table_to_dict
from duddysheet.core.workbook import WORKBOOK_OPTIONS, Workbook

CURRENT_SCHEMA_VERSION = 5
Migration = Callable[[dict[str, Any], dict[str, dict[str, Any]]], None]


def _migrate_v1_to_v2(
    manifest: dict[str, Any],
    sheet_data: dict[str, dict[str, Any]],
) -> None:
    """Accept v1 cells, whose missing hyperlink field means no hyperlink."""
    del manifest, sheet_data


def _migrate_v2_to_v3(
    manifest: dict[str, Any],
    sheet_data: dict[str, dict[str, Any]],
) -> None:
    """Accept v2 sheets, whose missing page setup means the print default."""
    del manifest, sheet_data


def _migrate_v3_to_v4(
    manifest: dict[str, Any],
    sheet_data: dict[str, dict[str, Any]],
) -> None:
    """Accept v3 sheets: no sparklines, and chart options at their defaults."""
    del manifest, sheet_data


def _migrate_v4_to_v5(
    manifest: dict[str, Any],
    sheet_data: dict[str, dict[str, Any]],
) -> None:
    """Accept v4 sheets: no notes, outlines, protection, or axis formats."""
    del manifest, sheet_data


MIGRATIONS: dict[int, Migration] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}


def save_native(workbook: Workbook, path: str | Path) -> Path:
    """Write a workbook to a versioned native archive."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet_files = [f"sheets/{index:04d}.json" for index in range(len(workbook))]
    manifest = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "active_sheet": workbook.active_sheet_index,
        "sheets": [
            {"name": sheet.name, "file": sheet_file}
            for sheet, sheet_file in zip(workbook, sheet_files)
        ],
        "options": {
            option: getattr(workbook, option) for option in WORKBOOK_OPTIONS
        },
        "defined_names": [
            {
                "name": item.name,
                "reference": item.refers_to,
                "scope": item.scope,
                **({"comment": item.comment} if item.comment else {}),
            }
            for item in workbook.defined_names
        ],
    }
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("workbook.json", _json_bytes(manifest))
        for sheet, sheet_file in zip(workbook, sheet_files):
            archive.writestr(sheet_file, _json_bytes(_sheet_to_data(sheet)))
    return destination


def load_native(path: str | Path) -> Workbook:
    """Load and validate a native archive, applying schema migrations."""
    source = Path(path)
    try:
        with ZipFile(source) as archive:
            manifest = json.loads(archive.read("workbook.json"))
            sheet_data = {
                item["file"]: json.loads(archive.read(item["file"]))
                for item in manifest.get("sheets", ())
            }
    except (BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid Duddy Spreadsheet file: {source}") from error

    version = manifest.get("schema_version")
    if not isinstance(version, int):
        raise ValueError("Duddy Spreadsheet manifest has no valid schema version")
    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This file was created by a newer Duddy Spreadsheet version "
            f"(schema {version})"
        )
    while version < CURRENT_SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"No migration is available for Duddy Spreadsheet schema {version}")
        migration(manifest, sheet_data)
        version += 1
        manifest["schema_version"] = version

    workbook = Workbook(create_default=False)
    for item in manifest.get("sheets", ()):
        data = sheet_data[item["file"]]
        sheet = workbook.add_sheet(item["name"])
        _restore_sheet(sheet, data)
    if not len(workbook):
        raise ValueError("Duddy Spreadsheet workbook contains no sheets")
    try:
        workbook.active_sheet = int(manifest.get("active_sheet", 0))
    except (IndexError, ValueError, TypeError) as error:
        raise ValueError("Duddy Spreadsheet active-sheet index is invalid") from error
    for option, value in manifest.get("options", {}).items():
        if option in WORKBOOK_OPTIONS:
            setattr(workbook, option, value)
    for item in manifest.get("defined_names", ()):
        workbook.define_name(
            item["name"],
            item["reference"],
            scope=item.get("scope"),
            comment=str(item.get("comment", "")),
        )
    return workbook


def _sheet_to_data(sheet: Any) -> dict[str, Any]:
    return {
        "cells": [
            {
                "row": row,
                "column": column,
                "raw_input": _encode_value(cell.raw_input),
                "cached_value": _encode_value(cell.cached_value),
                "format": _format_to_data(cell.format),
                "error": cell.error,
                "spill_parent": list(cell.spill_parent) if cell.spill_parent else None,
                "hyperlink": (
                    {
                        "target": cell.hyperlink.target,
                        "internal": cell.hyperlink.internal,
                        "tooltip": cell.hyperlink.tooltip,
                    }
                    if cell.hyperlink is not None
                    else None
                ),
            }
            for (row, column), cell in sheet.iter_populated()
        ],
        "row_heights": {str(key): value for key, value in sheet.row_heights.items()},
        "column_widths": {
            str(key): value for key, value in sheet.column_widths.items()
        },
        "hidden_rows": sorted(sheet.hidden_rows),
        "hidden_columns": sorted(sheet.hidden_columns),
        "merged_ranges": [item.to_a1() for item in sheet.merged_ranges],
        "conditional_formats": [
            _conditional_rule_to_data(item)
            for item in sheet.conditional_formats
            if isinstance(item, ConditionalRule)
        ],
        "data_validations": [
            _validation_to_data(item)
            for item in sheet.data_validations
            if isinstance(item, DataValidation)
        ],
        "auto_filter": (
            _filter_to_data(sheet.auto_filter)
            if isinstance(sheet.auto_filter, AutoFilter)
            else None
        ),
        "filtered_rows": sorted(sheet.filtered_rows),
        "charts": [
            _chart_to_data(item)
            for item in sheet.charts
            if isinstance(item, ChartSpec)
        ],
        "sparklines": [
            _sparkline_to_data(item)
            for item in sheet.sparklines
            if isinstance(item, Sparkline)
        ],
        "freeze_panes": list(sheet.freeze_panes) if sheet.freeze_panes else None,
        "tab_color": sheet.tab_color,
        "visible": sheet.visible,
        "page_setup": (
            setup_to_dict(sheet.page_setup) if sheet.page_setup is not None else None
        ),
        "notes": [
            {"row": row, "column": column, "text": note.text, "author": note.author}
            for (row, column), note in sorted(sheet.notes.items())
        ],
        "row_outline": {str(key): value for key, value in sheet.row_outline.items()},
        "column_outline": {
            str(key): value for key, value in sheet.column_outline.items()
        },
        "protection": (
            {item.name: getattr(sheet.protection, item.name) for item in fields(sheet.protection)}
            if sheet.protection is not None
            else None
        ),
        "column_formats": {
            str(key): _format_to_data(value) for key, value in sheet.column_formats.items()
        },
        "row_formats": {
            str(key): _format_to_data(value) for key, value in sheet.row_formats.items()
        },
        "default_column_width": sheet.default_column_width,
        "default_row_height": sheet.default_row_height,
        "tables": [table_to_dict(item) for item in sheet.tables],
        "pivots": [pivot_to_dict(item) for item in sheet.pivots],
        "data_tables": [data_table_to_dict(item) for item in sheet.data_tables],
    }


def _restore_sheet(sheet: Any, data: dict[str, Any]) -> None:
    for item in data.get("cells", ()):
        hyperlink_data = item.get("hyperlink")
        sheet.put_cell(
            int(item["row"]),
            int(item["column"]),
            Cell(
                raw_input=_decode_value(item.get("raw_input")),
                cached_value=_decode_value(item.get("cached_value")),
                format=_format_from_data(item.get("format", {})),
                error=item.get("error"),
                spill_parent=(
                    tuple(item["spill_parent"])
                    if item.get("spill_parent") is not None
                    else None
                ),
                hyperlink=(
                    Hyperlink(
                        str(hyperlink_data["target"]),
                        bool(hyperlink_data.get("internal", False)),
                        hyperlink_data.get("tooltip"),
                    )
                    if isinstance(hyperlink_data, dict)
                    and hyperlink_data.get("target")
                    else None
                ),
            ),
        )
    sheet.row_heights = {
        int(key): float(value) for key, value in data.get("row_heights", {}).items()
    }
    sheet.column_widths = {
        int(key): float(value)
        for key, value in data.get("column_widths", {}).items()
    }
    sheet.hidden_rows = {int(value) for value in data.get("hidden_rows", ())}
    sheet.hidden_columns = {int(value) for value in data.get("hidden_columns", ())}
    sheet.merged_ranges = [
        parse_a1(value) for value in data.get("merged_ranges", ())
    ]
    sheet.conditional_formats = [
        _conditional_rule_from_data(item)
        for item in data.get("conditional_formats", ())
    ]
    sheet.data_validations = [
        _validation_from_data(item)
        for item in data.get("data_validations", ())
    ]
    filter_data = data.get("auto_filter")
    sheet.auto_filter = (
        _filter_from_data(filter_data) if isinstance(filter_data, dict) else None
    )
    sheet.filtered_rows = {int(value) for value in data.get("filtered_rows", ())}
    sheet.charts = [
        _chart_from_data(item) for item in data.get("charts", ())
    ]
    sheet.sparklines = [
        _sparkline_from_data(item) for item in data.get("sparklines", ())
    ]
    panes = data.get("freeze_panes")
    sheet.freeze_panes = tuple(panes) if panes is not None else None
    sheet.tab_color = data.get("tab_color")
    sheet.visible = bool(data.get("visible", True))
    page_setup = data.get("page_setup")
    sheet.page_setup = (
        setup_from_dict(page_setup) if isinstance(page_setup, dict) else None
    )
    sheet.notes = {
        (int(item["row"]), int(item["column"])): Note(
            str(item.get("text", "")),
            str(item.get("author", "")),
        )
        for item in data.get("notes", ())
    }
    sheet.row_outline = {
        int(key): int(value) for key, value in data.get("row_outline", {}).items()
    }
    sheet.column_outline = {
        int(key): int(value) for key, value in data.get("column_outline", {}).items()
    }
    protection = data.get("protection")
    sheet.protection = (
        SheetProtection(**protection) if isinstance(protection, dict) else None
    )
    sheet.column_formats = {
        int(key): _format_from_data(value)
        for key, value in data.get("column_formats", {}).items()
    }
    sheet.row_formats = {
        int(key): _format_from_data(value)
        for key, value in data.get("row_formats", {}).items()
    }
    sheet.default_column_width = data.get("default_column_width")
    sheet.default_row_height = data.get("default_row_height")
    sheet.tables = [table_from_dict(item) for item in data.get("tables", ())]
    sheet.pivots = [pivot_from_dict(item) for item in data.get("pivots", ())]
    sheet.data_tables = [data_table_from_dict(item) for item in data.get("data_tables", ())]


def _format_to_data(cell_format: CellFormat) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in fields(cell_format):
        value = getattr(cell_format, item.name)
        result[item.name] = (
            {"style": value.style, "color": value.color}
            if isinstance(value, BorderStyle)
            else value
        )
    return result


def _format_from_data(data: dict[str, Any]) -> CellFormat:
    values = dict(data)
    for name in (
        "left_border",
        "right_border",
        "top_border",
        "bottom_border",
    ):
        border = values.get(name)
        if isinstance(border, dict):
            values[name] = BorderStyle(
                border.get("style", "none"),
                border.get("color", "#000000"),
            )
    return CellFormat(**values)


def _patch_to_data(patch: FormatPatch) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in fields(patch):
        value = getattr(patch, item.name)
        if isinstance(value, BorderStyle):
            result[item.name] = {"style": value.style, "color": value.color}
        else:
            result[item.name] = value
    return result


def _patch_from_data(data: dict[str, Any]) -> FormatPatch:
    values = dict(data)
    for name in (
        "left_border",
        "right_border",
        "top_border",
        "bottom_border",
    ):
        border = values.get(name)
        if isinstance(border, dict):
            values[name] = BorderStyle(
                border.get("style", "none"),
                border.get("color", "#000000"),
            )
    return FormatPatch(**values)


def _conditional_rule_to_data(rule: ConditionalRule) -> dict[str, Any]:
    return {
        "range": rule.range.to_a1(),
        "kind": rule.kind,
        "operator": rule.operator,
        "values": [_encode_value(value) for value in rule.values],
        "format_patch": _patch_to_data(rule.format_patch),
        "rank": rule.rank,
        "percent": rule.percent,
        "above": rule.above,
        "formula": rule.formula,
        "colors": list(rule.colors),
        "stop_if_true": rule.stop_if_true,
    }


def _conditional_rule_from_data(data: dict[str, Any]) -> ConditionalRule:
    return ConditionalRule(
        range=parse_a1(data["range"]),
        kind=data["kind"],
        operator=data.get("operator", "equal"),
        values=tuple(_decode_value(value) for value in data.get("values", ())),
        format_patch=_patch_from_data(data.get("format_patch", {})),
        rank=int(data.get("rank", 10)),
        percent=bool(data.get("percent", False)),
        above=bool(data.get("above", True)),
        formula=data.get("formula"),
        colors=tuple(data.get("colors", ("#f8696b", "#ffeb84", "#63be7b"))),
        stop_if_true=bool(data.get("stop_if_true", False)),
    )


def _validation_to_data(validation: DataValidation) -> dict[str, Any]:
    return {
        "range": validation.range.to_a1(),
        "kind": validation.kind,
        "operator": validation.operator,
        "values": [_encode_value(value) for value in validation.values],
        "formula": validation.formula,
        "allow_blank": validation.allow_blank,
        "input_message": validation.input_message,
        "error_message": validation.error_message,
    }


def _validation_from_data(data: dict[str, Any]) -> DataValidation:
    return DataValidation(
        range=parse_a1(data["range"]),
        kind=data["kind"],
        operator=data.get("operator", "between"),
        values=tuple(_decode_value(value) for value in data.get("values", ())),
        formula=data.get("formula"),
        allow_blank=bool(data.get("allow_blank", True)),
        input_message=data.get("input_message", ""),
        error_message=data.get(
            "error_message",
            "The value does not satisfy this cell's validation rule.",
        ),
    )


def _filter_to_data(auto_filter: AutoFilter) -> dict[str, Any]:
    return {
        "range": auto_filter.range.to_a1(),
        "column": auto_filter.column,
        "allowed_values": [
            _encode_value(value)
            for value in sorted(auto_filter.allowed_values, key=repr)
        ],
        "has_header": auto_filter.has_header,
    }


def _filter_from_data(data: dict[str, Any]) -> AutoFilter:
    return AutoFilter(
        range=parse_a1(data["range"]),
        column=int(data["column"]),
        allowed_values=frozenset(
            _decode_value(value) for value in data.get("allowed_values", ())
        ),
        has_header=bool(data.get("has_header", True)),
    )


_CHART_TUPLE_FIELDS = frozenset(
    {"series_columns", "combo_series_types", "secondary_series"}
)


def _chart_to_data(chart: ChartSpec) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for spec_field in fields(ChartSpec):
        value = getattr(chart, spec_field.name)
        if isinstance(value, RangeReference):
            value = value.to_a1()
        elif isinstance(value, tuple):
            value = list(value)
        data[spec_field.name] = value
    return data


def _chart_from_data(data: dict[str, Any]) -> ChartSpec:
    """Rebuild a chart; fields missing from older files keep their defaults."""
    values: dict[str, Any] = {}
    for spec_field in fields(ChartSpec):
        if spec_field.name not in data:
            continue
        value = data[spec_field.name]
        if spec_field.name == "source_range":
            value = parse_a1(value)
        elif spec_field.name in _CHART_TUPLE_FIELDS and value is not None:
            value = tuple(value)
        values[spec_field.name] = value
    return ChartSpec(**values)


def _sparkline_to_data(sparkline: Sparkline) -> dict[str, Any]:
    data = asdict(sparkline)
    data["data_range"] = sparkline.data_range.to_a1()
    return data


def _sparkline_from_data(data: dict[str, Any]) -> Sparkline:
    values = {
        spec_field.name: data[spec_field.name]
        for spec_field in fields(Sparkline)
        if spec_field.name in data
    }
    values["data_range"] = parse_a1(values["data_range"])
    return Sparkline(**values)


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"$type": "time", "value": value.isoformat()}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_encode_value(item) for item in value]}
    raise TypeError(f"Unsupported native cell value: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or "$type" not in value:
        return value
    kind = value["$type"]
    if kind == "datetime":
        return datetime.fromisoformat(value["value"])
    if kind == "date":
        return date.fromisoformat(value["value"])
    if kind == "time":
        return time.fromisoformat(value["value"])
    if kind == "tuple":
        return tuple(_decode_value(item) for item in value.get("items", ()))
    raise ValueError(f"Unknown native value type: {kind!r}")


def _json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
