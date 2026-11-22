"""Exercise the File menu handoff to the installed Windows companion."""
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QItemSelection, QItemSelectionModel
from PySide6.QtGui import QAction

from duddysheet.app import create_application

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_menu_sends_saved_workbook_sheet_and_rectangle(tmp_path: Path, monkeypatch) -> None:
    app, window = create_application([])
    path = window.save_path(tmp_path / "My forecast.dsheet")
    home = tmp_path / "ManuscriptDesk"
    executable = home / "source-env" / "Scripts" / "pythonw.exe"
    executable.parent.mkdir(parents=True)
    for item in (executable, home / "native_source.py", home / "source_window.pyw"):
        item.touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    launches = []
    monkeypatch.setattr(subprocess, "Popen", launches.append)
    model = window.grid_model
    selection = QItemSelection(model.index(1, 1), model.index(4, 3))
    window.grid.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    action = next(a for a in window.findChildren(QAction) if a.text() == "Link selection to Manuscript Desk...")
    action.trigger()
    assert launches == [[str(executable), str(home / "source_window.pyw"), str(path.resolve()),
                         model.active_sheet_name, "B2:D5"]]
    window.close()
