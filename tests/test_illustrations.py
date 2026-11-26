"""Pictures, shapes, and text boxes: model, files, and the floating layer."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import struct
import zlib
from dataclasses import replace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from duddysheet.commands.edits import InsertRowsCommand
from duddysheet.core.drawings import (
    SHAPES,
    Drawing,
    drawing_from_dict,
    drawing_to_dict,
    image_format,
    image_size,
    shift_drawings,
)
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.drawing_layer import shape_path
from duddysheet.ui.main_window import MainWindow


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + bytes([200, 60, 60]) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _sample() -> list[Drawing]:
    return [
        Drawing("Picture 1", "picture", 5, 1, 64, 32, image=png(64, 32), image_format="png", description="Red bar"),
        Drawing("Rectangle 2", "shape", 8, 1, 120, 50, shape="roundRect", text="Hello\nworld"),
        Drawing("Oval 3", "shape", 8, 4, 80, 80, shape="ellipse", fill="#70ad47", line=""),
        Drawing("TextBox 4", "textbox", 12, 1, 200, 60, text="A note & <tags>", fill="#ffffff", line="#000000", font_color="#000000", font_size=12),
    ]


def test_image_headers_are_read_without_an_imaging_library() -> None:
    data = png(64, 32)
    assert image_format(data) == "png" and image_size(data) == (64, 32)
    gif = b"GIF89a" + struct.pack("<HH", 10, 7) + b"\x00" * 8
    assert image_format(gif) == "gif" and image_size(gif) == (10, 7)
    jpeg = b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", 20, 30) + b"\x00" * 10
    assert image_format(jpeg) == "jpeg" and image_size(jpeg) == (30, 20)
    assert image_format(b"nope") == ""
    with pytest.raises(ValueError):
        Drawing("x", "picture", 0, 0, 10, 10, image=b"nope", image_format="")


def test_drawings_round_trip_through_both_file_formats(tmp_path) -> None:
    workbook = Workbook()
    workbook.active_sheet.drawings.extend(_sample())
    for drawing in _sample():
        assert drawing_from_dict(drawing_to_dict(drawing)) == drawing
    native = tmp_path / "drawings.dsheet"
    save_native(workbook, native)
    assert load_native(native).active_sheet.drawings == _sample()
    excel = tmp_path / "drawings.xlsx"
    write_xlsx(workbook, excel)
    loaded = read_xlsx(excel)
    assert loaded.warnings == ()
    assert loaded.workbook.active_sheet.drawings == _sample()


def test_drawings_move_with_inserted_and_deleted_rows() -> None:
    drawings = _sample()
    moved = shift_drawings(drawings, "row", 6, 2, False)
    assert [item.row for item in moved] == [5, 10, 10, 14]
    removed = shift_drawings(drawings, "row", 6, 3, True)
    assert [item.row for item in removed] == [5, 6, 6, 9]


def test_every_shape_has_an_outline() -> None:
    application()
    from PySide6.QtCore import QRectF

    for shape in SHAPES:
        assert not shape_path(shape, QRectF(0, 0, 100, 60)).isEmpty(), shape


def test_window_inserts_moves_edits_and_deletes_drawings(tmp_path) -> None:
    application()
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    picture_file = tmp_path / "logo.png"
    picture_file.write_bytes(png(40, 20))
    window.grid.setCurrentIndex(window.grid_model.index(2, 2))
    picture = window.insert_picture_file(picture_file)
    assert (picture.row, picture.column, picture.width, picture.height) == (2, 2, 40, 20)
    assert picture.description == "logo"
    shape = window.insert_shape("ellipse")
    box = window.insert_text_box("Note")
    sheet = window.grid_model.sheet
    assert [item.kind for item in sheet.drawings] == ["picture", "shape", "textbox"]
    layer = window.drawing_layer
    assert set(layer.items) == {picture.name, shape.name, box.name}
    item = layer.items[box.name]
    assert item.isVisible() and item.geometry().topLeft() == QPoint(
        window.grid.columnViewportPosition(2), window.grid.rowViewportPosition(2)
    )
    # Drag the text box down and to the right; the move is one undoable step.
    QTest.mousePress(item, Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    QTest.mouseMove(item, QPoint(20 + 150, 20 + 90))
    QTest.mouseRelease(item, Qt.MouseButton.LeftButton, pos=QPoint(20 + 150, 20 + 90))
    moved = next(drawing for drawing in window.grid_model.sheet.drawings if drawing.name == box.name)
    assert (moved.row, moved.column) != (2, 2)
    window.history.undo()
    restored = next(drawing for drawing in window.grid_model.sheet.drawings if drawing.name == box.name)
    assert (restored.row, restored.column) == (2, 2)
    window.update_drawing(box.name, replace(restored, text="Edited"))
    assert layer.items[box.name].drawing.text == "Edited"
    layer.items[shape.name].setFocus()
    QTest.keyClick(layer.items[shape.name], Qt.Key.Key_Delete)
    assert shape.name not in {item.name for item in window.grid_model.sheet.drawings}
    assert shape.name not in layer.items
    window.history.execute(InsertRowsCommand(window.engine, window.grid_model.active_sheet_name, 0, 1))
    assert {item.row for item in window.grid_model.sheet.drawings} == {3}
    assert "insertPicture" in window.excel_actions and "Pictures" in window.excel_ribbon_handlers
    window.close()
