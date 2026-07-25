"""JSON codec for trusted internal rich-cell clipboard data."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, datetime, time
from typing import Any

from excelclone.core.cell import BorderStyle, Cell, CellFormat, Hyperlink

RICH_CELL_MIME = "application/x-opengrid-cells+json"


def encode_cell_matrix(
    cells: tuple[tuple[Cell, ...], ...],
    origin: tuple[int, int],
) -> bytes:
    """Encode cells, formulas, cached values, and formats as UTF-8 JSON."""
    data = {
        "version": 1,
        "origin": list(origin),
        "cells": [
            [_cell_to_data(cell) for cell in row]
            for row in cells
        ],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_cell_matrix(
    payload: bytes,
) -> tuple[tuple[tuple[Cell, ...], ...], tuple[int, int]]:
    """Decode and validate internal rich-cell JSON."""
    data = json.loads(payload.decode("utf-8"))
    if data.get("version") != 1:
        raise ValueError("Unsupported rich clipboard version")
    origin_data = data.get("origin")
    if not isinstance(origin_data, list) or len(origin_data) != 2:
        raise ValueError("Invalid rich clipboard origin")
    cells = tuple(
        tuple(_cell_from_data(cell) for cell in row)
        for row in data.get("cells", ())
    )
    if not cells or any(len(row) != len(cells[0]) for row in cells):
        raise ValueError("Invalid rich clipboard cell matrix")
    return cells, (int(origin_data[0]), int(origin_data[1]))


def _cell_to_data(cell: Cell) -> dict[str, Any]:
    return {
        "raw": _encode_value(cell.raw_input),
        "cached": _encode_value(cell.cached_value),
        "format": _format_to_data(cell.format),
        "error": cell.error,
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


def _cell_from_data(data: dict[str, Any]) -> Cell:
    link_data = data.get("hyperlink")
    return Cell(
        raw_input=_decode_value(data.get("raw")),
        cached_value=_decode_value(data.get("cached")),
        format=_format_from_data(data.get("format", {})),
        error=data.get("error"),
        hyperlink=(
            Hyperlink(
                str(link_data["target"]),
                bool(link_data.get("internal", False)),
                link_data.get("tooltip"),
            )
            if isinstance(link_data, dict) and link_data.get("target")
            else None
        ),
    )


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
        if isinstance(values.get(name), dict):
            values[name] = BorderStyle(**values[name])
    return CellFormat(**values)


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"type": "time", "value": value.isoformat()}
    return str(value)


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    kind = value.get("type")
    if kind == "datetime":
        return datetime.fromisoformat(value["value"])
    if kind == "date":
        return date.fromisoformat(value["value"])
    if kind == "time":
        return time.fromisoformat(value["value"])
    raise ValueError(f"Unsupported rich clipboard value type: {kind!r}")
