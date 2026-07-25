from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.ui.dialogs.format_cells import FormatCellsDialog


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_format_cells_dialog_builds_patch_from_all_tabs() -> None:
    application()
    dialog = FormatCellsDialog(CellFormat())
    dialog.number_format.setCurrentText("#,##0.00")
    dialog.font_size.setValue(14)
    dialog.bold.setChecked(True)
    dialog.fill_color.setText("#ffeeaa")
    dialog.horizontal.setCurrentText("center")
    dialog.wrap_text.setChecked(True)
    dialog.border_style.setCurrentText("double")
    dialog.border_bottom.setChecked(True)

    patch = dialog.format_patch()

    assert patch.number_format == "#,##0.00"
    assert patch.font_size == 14
    assert patch.bold
    assert patch.fill_color == "#ffeeaa"
    assert patch.horizontal_alignment == "center"
    assert patch.wrap_text
    assert patch.bottom_border == BorderStyle("double", "#000000")
    dialog.close()
