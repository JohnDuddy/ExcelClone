"""Indent, rotation, stacking, shrink-to-fit, the outline bar, and the ribbon font boxes."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from duddysheet.commands.editing import OutlineCommand
from duddysheet.core.cell import CellFormat
from duddysheet.core.outline import OutlineGroup, is_collapsed, max_level, outline_groups
from duddysheet.ui.delegates import INDENT_PIXELS, needs_custom_text, text_layout
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_outline_groups_follow_levels() -> None:
    levels = {2: 1, 3: 2, 4: 2, 5: 1, 8: 1}
    assert max_level(levels) == 2 and max_level({}) == 0
    assert outline_groups(levels) == [
        OutlineGroup(1, 2, 5),
        OutlineGroup(1, 8, 8),
        OutlineGroup(2, 3, 4),
    ]
    group = OutlineGroup(2, 3, 4)
    assert group.summary == 5 and group.indexes == (3, 4)
    assert is_collapsed(group, {3, 4}) and not is_collapsed(group, {3})


def test_text_layout_handles_excel_alignment_options() -> None:
    application()
    font = QFont()
    rect = QRectF(0, 0, 100, 20)
    assert not needs_custom_text(CellFormat())
    indented = text_layout(CellFormat(indent=2), rect, font, "x")
    assert indented.rect.left() == 2 * INDENT_PIXELS
    right = text_layout(CellFormat(indent=1, horizontal_alignment="right"), rect, font, "x")
    assert right.rect.right() == 100 - INDENT_PIXELS
    assert text_layout(CellFormat(text_rotation=45), rect, font, "x").angle == 45
    assert text_layout(CellFormat(text_rotation=135), rect, font, "x").angle == -45
    assert text_layout(CellFormat(text_rotation=255), rect, font, "x").stacked
    shrunk = text_layout(CellFormat(shrink_to_fit=True), QRectF(0, 0, 30, 20), font, "a long label that does not fit")
    assert shrunk.font.pointSizeF() < font.pointSizeF()
    assert text_layout(CellFormat(shrink_to_fit=True), rect, font, "ok").font.pointSizeF() == font.pointSizeF()


def test_outline_bar_collapses_and_expands_groups() -> None:
    application()
    window = MainWindow()
    window.resize(900, 600)
    window.show()
    frame = window.outline_frame
    assert not frame.rows.isVisible() and not frame.columns.isVisible()
    window._run(OutlineCommand(window.engine, window.grid_model.active_sheet_name, "row", 2, 4, True))
    QApplication.processEvents()
    gutter = frame.rows
    assert gutter.isVisible() and gutter.depth() == 2
    gutter.grab()
    boxes = {target: box for box, target in gutter._targets}
    group = OutlineGroup(1, 2, 4)
    assert group in boxes and 1 in boxes and 2 in boxes
    QTest.mouseClick(gutter, Qt.MouseButton.LeftButton, pos=boxes[group].center())
    sheet = window.grid_model.sheet
    assert {2, 3, 4} <= sheet.hidden_rows
    gutter.grab()
    boxes = {target: box for box, target in gutter._targets}
    QTest.mouseClick(gutter, Qt.MouseButton.LeftButton, pos=boxes[group].center())
    assert not {2, 3, 4} & window.grid_model.sheet.hidden_rows
    gutter.grab()
    boxes = {target: box for box, target in gutter._targets}
    QTest.mouseClick(gutter, Qt.MouseButton.LeftButton, pos=boxes[1].center())
    assert {2, 3, 4} <= window.grid_model.sheet.hidden_rows
    window.history.undo()
    assert not {2, 3, 4} & window.grid_model.sheet.hidden_rows
    assert gutter.target_at(QPoint(-50, -50)) is None
    window.close()


def test_ribbon_font_boxes_apply_and_follow_the_active_cell() -> None:
    application()
    window = MainWindow()
    ribbon = window.ribbon
    assert ribbon.font_family_box.objectName() == "fontFamilyBox"
    assert ribbon.font_size_box.currentText() == "11"
    window.grid.setCurrentIndex(window.grid_model.index(1, 1))
    ribbon.font_size_box.setCurrentText("16")
    ribbon.font_size_box.activated.emit(0)
    assert window.grid_model.sheet.effective_format(1, 1).font_size == 16
    ribbon.font_family_box.setCurrentFont(QFont("Courier New"))
    ribbon.font_family_box.activated.emit(0)
    family = window.grid_model.sheet.effective_format(1, 1).font_family
    assert family == ribbon.font_family_box.currentFont().family()
    window.grid.setCurrentIndex(window.grid_model.index(0, 0))
    assert ribbon.font_size_box.currentText() == "11"
    window.grid.setCurrentIndex(window.grid_model.index(1, 1))
    assert ribbon.font_size_box.currentText() == "16"
    cell = window.grid_model.sheet.get_cell(1, 1)
    window.grid_model.sheet.put_cell(1, 1, replace(cell, format=replace(cell.format, indent=1)))
    assert needs_custom_text(window.grid_model.sheet.effective_format(1, 1))
    window.close()
