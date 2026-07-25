from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from excelclone.ui.formula_bar import cycle_absolute_reference
from excelclone.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_main_window_exposes_grid_formula_bar_ribbon_and_sheet_tabs() -> None:
    application()
    window = MainWindow()

    assert window.grid.objectName() == "spreadsheetGrid"
    assert window.formula_bar.objectName() == "formulaBar"
    assert window.ribbon.objectName() == "ribbon"
    assert window.sheet_tabs.objectName() == "sheetTabs"
    assert window.grid.model().rowCount() == 1_048_576

    window.close()


def test_formula_bar_commits_to_current_cell_and_updates_name_box() -> None:
    application()
    window = MainWindow()
    index = window.grid_model.index(2, 3)
    window.grid.setCurrentIndex(index)
    window.on_current_cell_changed(index)

    assert window.formula_bar.name_box.text() == "D3"

    window.formula_bar.editor.setText("=2+3")
    window.commit_formula_bar()

    assert window.grid_model.data(index, Qt.ItemDataRole.DisplayRole) == "5"
    assert window.formula_bar.editor.text() == "=2+3"
    window.close()


def test_add_sheet_and_tab_selection_switch_active_model() -> None:
    application()
    window = MainWindow()

    window.add_sheet()
    window.sheet_tabs.tab_bar.setCurrentIndex(1)

    assert window.engine.workbook.sheet_names == ("Sheet1", "Sheet2")
    assert window.grid_model.active_sheet_name == "Sheet2"
    window.close()


def test_copy_and_paste_use_tab_separated_windows_clipboard() -> None:
    app = application()
    window = MainWindow()
    model = window.grid_model
    model.setData(model.index(0, 0), "1")
    model.setData(model.index(0, 1), "2")
    selection = window.grid.selectionModel()
    selection.select(
        model.index(0, 0),
        selection.SelectionFlag.ClearAndSelect,
    )
    selection.select(
        model.index(0, 1),
        selection.SelectionFlag.Select,
    )

    window.grid.copy_selection()
    assert app.clipboard().text() == "1\t2"

    app.clipboard().setText("3\t4\n5\t6")
    window.grid.setCurrentIndex(model.index(2, 2))
    window.grid.paste_clipboard()

    assert model.data(model.index(2, 2)) == "3"
    assert model.data(model.index(3, 3)) == "6"
    window.close()


def test_cycle_absolute_reference_matches_f4_sequence() -> None:
    assert cycle_absolute_reference("=A1", 3) == ("=$A$1", 5)
    assert cycle_absolute_reference("=$A$1", 5) == ("=A$1", 4)
    assert cycle_absolute_reference("=A$1", 4) == ("=$A1", 4)
    assert cycle_absolute_reference("=$A1", 4) == ("=A1", 3)
