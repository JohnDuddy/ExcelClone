from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from excelclone.ui.dialogs.function_help import FunctionHelpDialog
from excelclone.ui.main_window import MainWindow
from excelclone.util.autosave import AutosaveManager
from excelclone.util.settings import SettingsStore


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_freeze_panes_shows_and_hides_real_overlay_views() -> None:
    application()
    window = MainWindow()
    window.show()
    window.grid.setCurrentIndex(window.grid_model.index(2, 3))

    window.toggle_freeze_panes()
    row_view, column_view, corner_view = window.grid.frozen_views

    assert not row_view.isHidden()
    assert not column_view.isHidden()
    assert not corner_view.isHidden()
    assert row_view.height() > 0
    assert column_view.width() > 0

    window.toggle_freeze_panes()
    assert all(view.isHidden() for view in window.grid.frozen_views)
    window.close()


def test_split_view_uses_same_virtual_model_and_closes_cleanly() -> None:
    application()
    window = MainWindow()

    window.toggle_split_view()

    assert window.secondary_grid is not None
    assert window.secondary_grid.model() is window.grid_model
    assert window.grid_splitter.count() == 2

    window.toggle_split_view()
    assert window.secondary_grid is None
    window.close()


def test_mouse_fill_path_extends_series_as_one_undoable_command() -> None:
    application()
    window = MainWindow()
    model = window.grid_model
    model.setData(model.index(0, 0), 1)
    model.setData(model.index(1, 0), 2)

    assert window.grid.fill_drag_to(4, 0, (0, 0, 1, 0))
    assert [model.sheet.get_cell(row, 0).raw_input for row in range(5)] == [
        1,
        2,
        3,
        4,
        5,
    ]

    window.history.undo()
    assert model.sheet.get_cell(4, 0).raw_input is None
    window.close()


def test_function_help_searches_registry_and_builds_template() -> None:
    application()
    dialog = FunctionHelpDialog()

    assert dialog.function_list.count() >= 120
    dialog.search.setText("sumif")
    names = [
        dialog.function_list.item(index).text()
        for index in range(dialog.function_list.count())
    ]
    assert "SUMIF" in names or "SUMIFS" in names
    dialog.search.setText("XLOOKUP")
    dialog.function_list.setCurrentRow(0)
    assert dialog.formula_template() == "=XLOOKUP()"
    dialog.close()


def test_window_autosaves_only_dirty_workbooks_and_normal_save_clears_it(
    tmp_path,
) -> None:
    application()
    manager = AutosaveManager(tmp_path / "autosave")
    window = MainWindow(
        settings_store=SettingsStore(tmp_path / "settings.json"),
        autosave_manager=manager,
    )
    assert window.autosave_timer.interval() == 300_000
    assert window.autosave_now() is None

    window.grid_model.setData(window.grid_model.index(0, 0), "recover")
    candidate = window.autosave_now()
    assert candidate is not None
    assert manager.candidates() == (candidate,)

    window.save_path(tmp_path / "saved.ogrid")
    assert manager.candidates() == ()
    window.close()
