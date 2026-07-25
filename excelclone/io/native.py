"""Lossless versioned OGrid ZIP/JSON serialization."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from excelclone.core.cell import BorderStyle, Cell, CellFormat
from excelclone.core.chart import ChartSpec
from excelclone.core.conditional import ConditionalRule, FormatPatch
from excelclone.core.data_tools import AutoFilter, DataValidation
from excelclone.core.refs import parse_a1
from excelclone.core.workbook import Workbook

CURRENT_SCHEMA_VERSION = 1
Migration = Callable[[dict[str, Any], dict[str, dict[str, Any]]], None]
MIGRATIONS: dict[int, Migration] = {}


def save_ogrid(workbook: Workbook, path: str | Path) -> Path:
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
        "defined_names": [
            {
                "name": item.name,
                "reference": item.reference.to_a1(),
                "scope": item.scope,
            }
            for item in workbook.defined_names
        ],
    }
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        archive.writestr("workbook.json", _json_bytes(manifest))
        for sheet, sheet_file in zip(workbook, sheet_files):
            archive.writestr(sheet_file, _json_bytes(_sheet_to_data(sheet)))
    return destination


def load_ogrid(path: str | Path) -> Workbook:
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
        raise ValueError(f"Invalid OGrid file: {source}") from error

    version = manifest.get("schema_version")
    if not isinstance(version, int):
        raise ValueError("OGrid manifest has no valid schema version")
    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This file was created by a newer OpenGrid version "
            f"(schema {version})"
        )
    while version < CURRENT_SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"No migration is available for OGrid schema {version}")
        migration(manifest, sheet_data)
        version += 1
        manifest["schema_version"] = version

    workbook = Workbook(create_default=False)
    for item in manifest.get("sheets", ()):
        data = sheet_data[item["file"]]
        sheet = workbook.add_sheet(item["name"])
        _restore_sheet(sheet, data)
    if not len(workbook):
        raise ValueError("OGrid workbook contains no sheets")
    try:
        workbook.active_sheet = int(manifest.get("active_sheet", 0))
    except (IndexError, ValueError, TypeError) as error:
        raise ValueError("OGrid active-sheet index is invalid") from error
    for item in manifest.get("defined_names", ()):
        workbook.define_name(
            item["name"],
            item["reference"],
            scope=item.get("scope"),
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
        "freeze_panes": list(sheet.freeze_panes) if sheet.freeze_panes else None,
        "tab_color": sheet.tab_color,
        "visible": sheet.visible,
    }


def _restore_sheet(sheet: Any, data: dict[str, Any]) -> None:
    for item in data.get("cells", ()):
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
    panes = data.get("freeze_panes")
    sheet.freeze_panes = tuple(panes) if panes is not None else None
    sheet.tab_color = data.get("tab_color")
    sheet.visible = bool(data.get("visible", True))


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


def _chart_to_data(chart: ChartSpec) -> dict[str, Any]:
    return {
        "chart_id": chart.chart_id,
        "sheet_name": chart.sheet_name,
        "source_range": chart.source_range.to_a1(),
        "chart_type": chart.chart_type,
        "title": chart.title,
        "x_axis_title": chart.x_axis_title,
        "y_axis_title": chart.y_axis_title,
        "legend_position": chart.legend_position,
        "has_headers": chart.has_headers,
        "category_column": chart.category_column,
        "series_columns": (
            list(chart.series_columns)
            if chart.series_columns is not None
            else None
        ),
    }


def _chart_from_data(data: dict[str, Any]) -> ChartSpec:
    columns = data.get("series_columns")
    return ChartSpec(
        data["chart_id"],
        data["sheet_name"],
        parse_a1(data["source_range"]),
        data["chart_type"],
        data.get("title", ""),
        data.get("x_axis_title", ""),
        data.get("y_axis_title", ""),
        data.get("legend_position", "right"),
        bool(data.get("has_headers", True)),
        data.get("category_column"),
        tuple(columns) if columns is not None else None,
    )


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
