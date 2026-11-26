"""Pictures, shapes, and text boxes that float over a sheet (Insert > Illustrations)."""

from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from typing import Any

KINDS = ("picture", "shape", "textbox")
# Excel's preset geometry names for the shapes offered in Insert > Shapes.
SHAPES = {
    "rect": "Rectangle",
    "roundRect": "Rounded Rectangle",
    "ellipse": "Oval",
    "triangle": "Isosceles Triangle",
    "rightArrow": "Right Arrow",
    "line": "Line",
    "star5": "Star: 5 Points",
    "wedgeRectCallout": "Speech Bubble: Rectangle",
}
IMAGE_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "gif": "image/gif", "bmp": "image/bmp"}


@dataclass(frozen=True, slots=True)
class Drawing:
    """One floating object, anchored to a cell with a pixel offset and size."""

    name: str
    kind: str
    row: int
    column: int
    width: float
    height: float
    row_offset: float = 0.0
    column_offset: float = 0.0
    shape: str = "rect"
    text: str = ""
    fill: str = "#4472c4"
    line: str = "#2f528f"
    font_color: str = "#ffffff"
    font_size: float = 11.0
    image: bytes = b""
    image_format: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Unknown drawing kind {self.kind!r}")
        if self.kind == "shape" and self.shape not in SHAPES:
            raise ValueError(f"Unknown shape {self.shape!r}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("A drawing needs a positive width and height")
        if self.kind == "picture" and self.image_format not in IMAGE_TYPES:
            raise ValueError("Pictures must be PNG, JPEG, GIF, or BMP images")


def image_format(data: bytes) -> str:
    """Return 'png', 'jpeg', 'gif', or 'bmp' from an image's signature ('' if unknown)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    return ""


def image_size(data: bytes) -> tuple[int, int] | None:
    """Read pixel dimensions from PNG, GIF, BMP, or JPEG headers without an imaging library."""
    kind = image_format(data)
    try:
        if kind == "png":
            width, height = struct.unpack(">II", data[16:24])
            return width, height
        if kind == "gif":
            width, height = struct.unpack("<HH", data[6:10])
            return width, height
        if kind == "bmp":
            width, height = struct.unpack("<ii", data[18:26])
            return width, abs(height)
        if kind == "jpeg":
            position = 2
            while position + 9 < len(data):
                if data[position] != 0xFF:
                    position += 1
                    continue
                marker = data[position + 1]
                length = struct.unpack(">H", data[position + 2 : position + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    height, width = struct.unpack(">HH", data[position + 5 : position + 9])
                    return width, height
                position += 2 + length
    except struct.error:
        return None
    return None


def next_drawing_name(sheet: Any, kind: str) -> str:
    """Return Excel's next default name: 'Picture 1', 'Rectangle 2', 'TextBox 3'."""
    used = {drawing.name for drawing in sheet.drawings}
    number = len(sheet.drawings) + 1
    base = {"picture": "Picture", "textbox": "TextBox"}.get(kind, "Shape")
    while f"{base} {number}" in used:
        number += 1
    return f"{base} {number}"


def drawing_to_dict(drawing: Drawing) -> dict[str, Any]:
    data = {
        "name": drawing.name,
        "kind": drawing.kind,
        "row": drawing.row,
        "column": drawing.column,
        "width": drawing.width,
        "height": drawing.height,
        "row_offset": drawing.row_offset,
        "column_offset": drawing.column_offset,
        "shape": drawing.shape,
        "text": drawing.text,
        "fill": drawing.fill,
        "line": drawing.line,
        "font_color": drawing.font_color,
        "font_size": drawing.font_size,
        "image_format": drawing.image_format,
        "description": drawing.description,
    }
    if drawing.image:
        data["image"] = base64.b64encode(drawing.image).decode("ascii")
    return data


def drawing_from_dict(data: dict[str, Any]) -> Drawing:
    values = dict(data)
    values["image"] = base64.b64decode(values["image"]) if values.get("image") else b""
    return Drawing(**values)


def shift_drawings(drawings: list[Drawing], axis: str, index: int, count: int, delete: bool) -> list[Drawing]:
    """Move drawings below/right of inserted or deleted rows or columns, as Excel does."""
    from dataclasses import replace

    result = []
    for drawing in drawings:
        position = drawing.row if axis == "row" else drawing.column
        if position >= index:
            if delete:
                position = max(index, position - count)
            else:
                position += count
        result.append(replace(drawing, **({"row": position} if axis == "row" else {"column": position})))
    return result
