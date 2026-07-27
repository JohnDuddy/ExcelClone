from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook as OpenPyxlWorkbook, load_workbook
from openpyxl.worksheet.hyperlink import Hyperlink as OpenPyxlHyperlink
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from duddysheet.core.cell import Cell, Hyperlink
from duddysheet.core.clipboard import decode_cell_matrix, encode_cell_matrix
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.main_window import MainWindow


def linked_xlsx(path) -> None:
    package = OpenPyxlWorkbook()
    overview = package.active
    overview.title = "Overview"
    overview["A1"] = "Example listing"
    overview["A1"].hyperlink = "https://example.com/listings/42"
    overview["A1"].style = "Hyperlink"
    details = package.create_sheet("Details")
    details["B2"] = "Return to overview"
    details["B2"].hyperlink = OpenPyxlHyperlink(
        ref="B2",
        location="'Overview'!A1",
        tooltip="Go to overview",
    )
    package.save(path)
    package.close()


def test_xlsx_hyperlinks_survive_import_and_export(tmp_path) -> None:
    source = tmp_path / "links.xlsx"
    output = tmp_path / "links-roundtrip.xlsx"
    linked_xlsx(source)

    result = read_xlsx(source)
    external = result.workbook.get_sheet("Overview").get_cell(0, 0).hyperlink
    internal = result.workbook.get_sheet("Details").get_cell(1, 1).hyperlink

    assert external is not None
    assert external.target == "https://example.com/listings/42"
    assert not external.internal
    assert internal is not None
    assert internal.target == "'Overview'!A1"
    assert internal.internal
    assert internal.tooltip == "Go to overview"
    assert not any("hyperlink" in warning.casefold() for warning in result.warnings)

    write_xlsx(result.workbook, output)
    package = load_workbook(output, data_only=False)
    assert package["Overview"]["A1"].hyperlink.target == external.target
    assert package["Details"]["B2"].hyperlink.location == internal.target
    package.close()


def test_grid_click_emits_external_link_and_navigates_internal_link(tmp_path) -> None:
    application = QApplication.instance() or QApplication([])
    del application
    source = tmp_path / "links.xlsx"
    linked_xlsx(source)
    workbook = read_xlsx(source).workbook
    opened: list[str] = []
    window = MainWindow(
        workbook,
        hyperlink_opener=lambda url: not opened.append(url.toString()),
    )
    requested: list[str] = []
    window.grid.externalHyperlinkRequested.connect(requested.append)

    external_index = window.grid_model.index(0, 0)
    assert window.grid.activate_hyperlink(external_index)
    assert requested == ["https://example.com/listings/42"]
    assert opened == ["https://example.com/listings/42"]

    window.switch_sheet(1)
    internal_index = window.grid_model.index(1, 1)
    assert window.grid.activate_hyperlink(internal_index)
    assert window.grid_model.active_sheet_name == "Overview"
    assert window.grid.currentIndex() == window.grid_model.index(0, 0)
    window.close()


def test_grid_presents_link_color_underline_and_tooltip(tmp_path) -> None:
    QApplication.instance() or QApplication([])
    source = tmp_path / "links.xlsx"
    linked_xlsx(source)
    window = MainWindow(read_xlsx(source).workbook, hyperlink_opener=lambda url: True)
    index = window.grid_model.index(0, 0)

    assert window.grid_model.data(index, Qt.ItemDataRole.FontRole).underline()
    assert (
        window.grid_model.data(index, Qt.ItemDataRole.ForegroundRole).color()
        == QColor("#0563c1")
    )
    assert "example.com" in window.grid_model.data(
        index,
        Qt.ItemDataRole.ToolTipRole,
    )
    window.close()


def test_hyperlinks_survive_native_file_and_rich_clipboard(tmp_path) -> None:
    hyperlink = Hyperlink(
        "https://example.com/listings/42",
        tooltip="Open example",
    )
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, "Example", hyperlink=hyperlink)
    path = tmp_path / "links.dsheet"

    save_native(workbook, path)
    restored = load_native(path)
    assert restored.active_sheet.get_cell(0, 0).hyperlink == hyperlink

    payload = encode_cell_matrix(
        ((Cell(raw_input="Example", cached_value="Example", hyperlink=hyperlink),),),
        (0, 0),
    )
    cells, origin = decode_cell_matrix(payload)
    assert origin == (0, 0)
    assert cells[0][0].hyperlink == hyperlink


def test_editing_linked_cell_removes_old_link_metadata() -> None:
    QApplication.instance() or QApplication([])
    workbook = Workbook()
    workbook.active_sheet.set_cell(
        0,
        0,
        "Example",
        hyperlink=Hyperlink("https://example.com"),
    )
    window = MainWindow(workbook, hyperlink_opener=lambda url: True)

    assert window.grid_model.setData(window.grid_model.index(0, 0), "Changed")
    assert window.grid_model.sheet.get_cell(0, 0).hyperlink is None
    window.close()
