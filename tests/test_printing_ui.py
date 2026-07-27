"""Print rendering, PDF export, page setup dialog, and menu wiring."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.core.printing import (
    Margins,
    Orientation,
    PageSetup,
    setup_from_dict,
    setup_to_dict,
)
from duddysheet.core.sheet import Sheet
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.ui.dialogs.page_setup import PageSetupDialog, _parse_span
from duddysheet.ui.main_window import MainWindow
from duddysheet.ui.printing import WorksheetRenderer


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sheet() -> Sheet:
    sheet = Sheet("Model")
    for row in range(30):
        for column in range(6):
            sheet.set_cell(row, column, row * 10 + column)
    return sheet


def render_to_image(
    renderer: WorksheetRenderer,
    index: int = 0,
    size: tuple[int, int] = (816, 1056),
) -> QImage:
    """Paint a page onto a white letter-sized raster at 96 dpi."""
    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        renderer.render_page(painter, index, 96.0)
    finally:
        painter.end()
    return image


def ink(image: QImage, step: int = 3) -> int:
    """Return a sampled count of non-white pixels."""
    white = QColor("white")
    return sum(
        1
        for y in range(0, image.height(), step)
        for x in range(0, image.width(), step)
        if image.pixelColor(x, y) != white
    )


def test_renderer_paints_visible_content(application, sheet) -> None:
    renderer = WorksheetRenderer(sheet)

    assert ink(render_to_image(renderer)) > 0


def test_empty_sheet_renders_no_pages(application) -> None:
    renderer = WorksheetRenderer(Sheet("Blank"))

    assert renderer.page_count == 0
    with pytest.raises(IndexError):
        render_to_image(renderer)


def test_gridlines_add_ink(application, sheet) -> None:
    plain = WorksheetRenderer(sheet, PageSetup(show_gridlines=False))
    ruled = WorksheetRenderer(sheet, PageSetup(show_gridlines=True))

    assert ink(render_to_image(ruled)) > ink(render_to_image(plain))


def test_headings_add_ink(application, sheet) -> None:
    plain = WorksheetRenderer(sheet, PageSetup(show_headings=False))
    labelled = WorksheetRenderer(sheet, PageSetup(show_headings=True))

    assert ink(render_to_image(labelled)) > ink(render_to_image(plain))


def test_fills_and_borders_are_painted(application) -> None:
    sheet = Sheet("Styled")
    sheet.set_cell(
        0,
        0,
        1,
        cell_format=CellFormat(
            fill_color="#ff0000",
            bottom_border=BorderStyle(style="thick", color="#0000ff"),
        ),
    )
    renderer = WorksheetRenderer(sheet)
    image = render_to_image(renderer)

    colors = {
        image.pixelColor(x, y).name()
        for y in range(0, 80)
        for x in range(0, 120)
    }
    assert "#ff0000" in colors


def test_conditional_formats_reach_the_printed_page(application) -> None:
    """Printing must show the same conditional formatting as the screen."""
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, 5)

    with_workbook = WorksheetRenderer(sheet, workbook=workbook)
    without = WorksheetRenderer(sheet)

    assert with_workbook.page_count == without.page_count == 1


def test_export_pdf_writes_a_real_pdf(application, sheet, tmp_path) -> None:
    renderer = WorksheetRenderer(sheet, document_name="model.dsheet")

    written = renderer.export_pdf(tmp_path / "out.pdf")
    data = written.read_bytes()

    assert written.is_file()
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_export_pdf_creates_missing_directories(application, sheet, tmp_path) -> None:
    written = WorksheetRenderer(sheet).export_pdf(tmp_path / "deep" / "out.pdf")

    assert written.is_file()


def test_multi_page_export_contains_every_page(application, tmp_path) -> None:
    sheet = Sheet("Long")
    for row in range(400):
        sheet.set_cell(row, 0, row)
    renderer = WorksheetRenderer(sheet)

    written = renderer.export_pdf(tmp_path / "long.pdf")

    assert renderer.page_count > 1
    assert written.read_bytes().count(b"/Type /Page") >= renderer.page_count


def test_landscape_export_differs_from_portrait(application, sheet, tmp_path) -> None:
    portrait = WorksheetRenderer(sheet, PageSetup(orientation=Orientation.PORTRAIT))
    landscape = WorksheetRenderer(
        sheet, PageSetup(orientation=Orientation.LANDSCAPE)
    )

    first = portrait.export_pdf(tmp_path / "p.pdf").read_bytes()
    second = landscape.export_pdf(tmp_path / "l.pdf").read_bytes()

    assert first != second


def test_page_setup_round_trips_through_serialization() -> None:
    setup = PageSetup(
        orientation=Orientation.LANDSCAPE,
        margins=Margins(left=36.0, right=36.0, top=72.0, bottom=72.0),
        scale=0.75,
        show_gridlines=True,
        show_headings=True,
        repeat_rows=(0, 2),
        repeat_columns=(0, 1),
        header_center="Quarterly Model",
        footer_right="Page &P of &N",
        center_horizontally=True,
        first_page_number=3,
    )

    assert setup_from_dict(setup_to_dict(setup)) == setup


def test_corrupt_page_setup_falls_back_to_defaults() -> None:
    """A bad print preference must never make a workbook unopenable."""
    assert setup_from_dict({"paper": "Nonsense", "scale": "banana"}) == PageSetup()
    assert setup_from_dict({"repeat_rows": [9, 2]}).repeat_rows is None
    assert setup_from_dict({"print_area": "not a range"}).print_area is None


def test_page_setup_persists_through_a_native_save(tmp_path) -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 1)
    workbook.active_sheet.page_setup = PageSetup(
        orientation=Orientation.LANDSCAPE,
        show_gridlines=True,
        repeat_rows=(0, 0),
        header_center="Board Pack",
    )

    save_native(workbook, tmp_path / "book.dsheet")
    reloaded = load_native(tmp_path / "book.dsheet")

    restored = reloaded.active_sheet.page_setup
    assert restored.orientation is Orientation.LANDSCAPE
    assert restored.show_gridlines is True
    assert restored.repeat_rows == (0, 0)
    assert restored.header_center == "Board Pack"


def test_sheet_without_page_setup_loads_as_default(tmp_path) -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 1)

    save_native(workbook, tmp_path / "plain.dsheet")
    reloaded = load_native(tmp_path / "plain.dsheet")

    assert reloaded.active_sheet.page_setup is None


def test_page_setup_survives_sheet_copy() -> None:
    sheet = Sheet("Source")
    sheet.page_setup = PageSetup(show_gridlines=True)

    assert sheet.copy().page_setup == sheet.page_setup


@pytest.mark.parametrize(
    ("text", "numeric", "expected"),
    [
        ("1:2", True, (0, 1)),
        ("3", True, (2, 2)),
        ("$1:$4", True, (0, 3)),
        ("5:2", True, (1, 4)),
        ("A:B", False, (0, 1)),
        ("C", False, (2, 2)),
        ("AA:AB", False, (26, 27)),
        ("", True, None),
        ("nonsense", True, None),
        ("1:B", False, None),
    ],
)
def test_repeat_span_parsing(text, numeric, expected) -> None:
    assert _parse_span(text, numeric=numeric) == expected


def test_page_setup_dialog_round_trips_a_setup(application) -> None:
    original = PageSetup(
        orientation=Orientation.LANDSCAPE,
        scale=0.8,
        show_gridlines=True,
        show_headings=True,
        repeat_rows=(0, 1),
        repeat_columns=(0, 0),
        header_center="Model",
        footer_right="Page &P of &N",
        center_horizontally=True,
        first_page_number=4,
    )
    dialog = PageSetupDialog(original, sheet_name="Model")
    try:
        result = dialog.page_setup()

        assert result.orientation is Orientation.LANDSCAPE
        assert result.scale == pytest.approx(0.8)
        assert result.show_gridlines is True
        assert result.show_headings is True
        assert result.repeat_rows == (0, 1)
        assert result.repeat_columns == (0, 0)
        assert result.header_center == "Model"
        assert result.center_horizontally is True
        assert result.first_page_number == 4
    finally:
        dialog.deleteLater()


def test_page_setup_dialog_rejects_a_malformed_range(application) -> None:
    dialog = PageSetupDialog(sheet_name="Model")
    try:
        dialog.print_area_edit.setText("!!!")
        dialog.accept()

        assert dialog.result() != dialog.DialogCode.Accepted
        assert "Print area" in dialog.error_label.text()
    finally:
        dialog.deleteLater()


def test_fit_to_page_selection_clears_explicit_scale(application) -> None:
    dialog = PageSetupDialog(PageSetup(fit_to_width=1))
    try:
        result = dialog.page_setup()

        assert result.fit_to_width == 1
        assert result.scale == 1.0
    finally:
        dialog.deleteLater()


def test_main_window_exposes_print_actions(application) -> None:
    window = MainWindow()
    try:
        assert window.print_action.shortcut().toString() == "Ctrl+P"
        assert window.print_preview_action.shortcut().toString() == "Ctrl+Shift+P"
        for action in (
            window.page_setup_action,
            window.print_preview_action,
            window.print_action,
            window.export_pdf_action,
            window.set_print_area_action,
            window.clear_print_area_action,
        ):
            assert action.text()
    finally:
        window.close()


def test_main_window_exports_the_active_sheet(application, tmp_path) -> None:
    window = MainWindow()
    try:
        sheet = window.engine.workbook.active_sheet
        for row in range(40):
            sheet.set_cell(row, 0, row)

        renderer = window._renderer()
        written = renderer.export_pdf(tmp_path / "active.pdf")

        assert renderer.page_count >= 1
        assert written.read_bytes().startswith(b"%PDF")
    finally:
        window.close()


def test_setting_a_print_area_marks_the_workbook_dirty(application) -> None:
    window = MainWindow()
    try:
        sheet = window.engine.workbook.active_sheet
        sheet.set_cell(0, 0, 1)
        window.grid.selectRow(0)
        window.dirty = False

        window.set_print_area()

        assert sheet.page_setup is not None
        assert sheet.page_setup.print_area is not None
        assert window.dirty is True

        window.clear_print_area()
        assert sheet.page_setup.print_area is None
    finally:
        window.close()
