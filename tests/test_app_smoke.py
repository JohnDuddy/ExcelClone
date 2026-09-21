from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from duddysheet.app import create_application, open_startup_workbook, startup_path


def test_application_shell_uses_product_title() -> None:
    app, window = create_application([])

    assert app.applicationName() == "Duddy Spreadsheet"
    assert window.windowTitle() == "Duddy Spreadsheet"
    assert window.minimumWidth() >= 800
    assert window.minimumHeight() >= 600

    window.close()


def test_startup_path_reads_the_open_option() -> None:
    assert startup_path(["--open", "book.xlsx"]) == Path("book.xlsx")
    assert startup_path(["--open=book.xlsx"]) == Path("book.xlsx")


def test_startup_path_accepts_a_bare_path() -> None:
    assert startup_path(["book.xlsx"]) == Path("book.xlsx")
    assert startup_path(["--version", "book.xlsx"]) == Path("book.xlsx")


def test_startup_path_is_absent_without_a_file() -> None:
    assert startup_path([]) is None
    assert startup_path(["--self-test"]) is None
    assert startup_path(["--open"]) is None
    assert startup_path(["--open="]) is None


def test_startup_workbook_loads_into_the_window(tmp_path: Path) -> None:
    from duddysheet.core.workbook import Workbook
    from duddysheet.io import write_xlsx

    source = tmp_path / "startup.xlsx"
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, "Opened at startup")
    write_xlsx(workbook, source)

    app, window = create_application([])
    open_startup_workbook(window, source)

    assert window.windowTitle().startswith(source.name)
    loaded = window.engine.workbook.active_sheet.get_cell(0, 0)
    assert loaded.raw_input == "Opened at startup"
    window.close()
