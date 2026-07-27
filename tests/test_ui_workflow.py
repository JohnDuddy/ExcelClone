from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from duddysheet.ui.delegates import CellDelegate
from duddysheet.ui.formula_bar import cycle_absolute_reference
from duddysheet.ui.main_window import MainWindow
from duddysheet.util.settings import SettingsStore


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
    app.clipboard().clear()
    window.close()


def test_cycle_absolute_reference_matches_f4_sequence() -> None:
    assert cycle_absolute_reference("=A1", 3) == ("=$A$1", 5)
    assert cycle_absolute_reference("=$A$1", 5) == ("=A$1", 4)
    assert cycle_absolute_reference("=A$1", 4) == ("=$A1", 4)
    assert cycle_absolute_reference("=$A1", 4) == ("=A1", 3)


def test_main_window_uses_cell_delegate_and_format_actions_are_undoable() -> None:
    application()
    window = MainWindow()
    index = window.grid_model.index(0, 0)
    window.grid.setCurrentIndex(index)

    window._ribbon_action("Bold")
    assert window.grid_model.sheet.get_cell(0, 0).format.bold
    window.history.undo()
    assert not window.grid_model.sheet.get_cell(0, 0).format.bold
    assert isinstance(window.grid.itemDelegate(), CellDelegate)
    window.close()


def test_view_actions_toggle_gridlines_formulas_zoom_and_freeze_panes() -> None:
    application()
    window = MainWindow()
    model = window.grid_model
    model.setData(model.index(0, 0), "=1+1")

    window._ribbon_action("Formula View")
    assert model.data(model.index(0, 0)) == "=1+1"
    window._ribbon_action("Gridlines")
    assert not window.grid.showGrid()
    window._ribbon_action("Zoom")
    assert window.grid.zoom_percent == 125

    window.grid.setCurrentIndex(model.index(2, 3))
    window._ribbon_action("Freeze Panes")
    assert model.sheet.freeze_panes == (2, 3)
    window._ribbon_action("Freeze Panes")
    assert model.sheet.freeze_panes is None
    window.close()


def test_main_window_saves_and_opens_native_workbook_path(tmp_path) -> None:
    application()
    settings = SettingsStore(tmp_path / "settings.json")
    path = tmp_path / "workbook.dsheet"
    window = MainWindow(settings_store=settings)
    window.grid_model.setData(window.grid_model.index(0, 0), "42")

    window.save_path(path)
    window.grid_model.setData(window.grid_model.index(0, 0), "99")
    warnings = window.open_path(path)

    assert warnings == ()
    assert window.grid_model.data(window.grid_model.index(0, 0)) == "42"
    assert window.current_path == path
    assert str(path) == settings.recent_files[0]
    assert not window.dirty
    assert path.name in window.windowTitle()
    window.close()


def test_main_window_path_dispatch_supports_xlsx_csv_and_tsv(tmp_path) -> None:
    application()
    window = MainWindow(settings_store=SettingsStore(tmp_path / "settings.json"))
    window.grid_model.setData(window.grid_model.index(0, 0), "7")

    for suffix in (".xlsx", ".csv", ".tsv"):
        path = tmp_path / f"book{suffix}"
        window.save_path(path)
        assert path.exists()
        window.open_path(path)
        assert window.grid_model.data(window.grid_model.index(0, 0)) == "7"

    window.close()


def test_internal_clipboard_preserves_formulas_and_formats() -> None:
    app = application()
    window = MainWindow()
    model = window.grid_model
    model.setData(model.index(0, 0), "2")
    model.setData(model.index(0, 1), "=A1*3")
    window.grid.setCurrentIndex(model.index(0, 1))
    window._ribbon_action("Bold")
    selection = window.grid.selectionModel()
    selection.select(
        model.index(0, 0),
        selection.SelectionFlag.ClearAndSelect,
    )
    selection.select(model.index(0, 1), selection.SelectionFlag.Select)

    window.grid.copy_selection()
    window.grid.setCurrentIndex(model.index(2, 2))
    window.grid.paste_clipboard()

    assert model.sheet.get_cell(2, 3).raw_input == "=C3*3"
    assert model.sheet.get_cell(2, 3).format.bold
    assert app.clipboard().text() == "2\t6"
    app.clipboard().clear()
    window.close()
