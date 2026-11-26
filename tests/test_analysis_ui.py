"""Main-window workflows for Tables, PivotTables, data tables, and their tutorial."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QToolButton

from duddysheet.core.analysis_help import LESSONS, SECTIONS, build_practice_workbook, lesson_html, search_lessons
from duddysheet.core.pivot import PivotValueField
from duddysheet.ui.dialogs.analysis_dialogs import PivotFieldsDialog, ValueFieldDialog
from duddysheet.ui.dialogs.analysis_help import AnalysisHelpDialog
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window_with_sales() -> MainWindow:
    application()
    window = MainWindow()
    rows = (("Region", "Product", "Sales"), ("East", "Apple", 100), ("West", "Pear", 50), ("East", "Pear", 25))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            window.grid_model.setData(window.grid_model.index(row, column), str(value))
    window.grid.setCurrentIndex(window.grid_model.index(1, 1))
    return window


def _type(window: MainWindow, row: int, column: int, text: str) -> bool:
    return window.grid_model.setData(window.grid_model.index(row, column), text)


def _value(window: MainWindow, row: int, column: int) -> object:
    cell = window.grid_model.sheet.get_cell(row, column)
    return cell.error or cell.display_value


def test_menus_ribbon_and_shortcuts_expose_the_features() -> None:
    window = _window_with_sales()
    actions = window.excel_actions
    assert [sequence.toString() for sequence in actions["createTable"].shortcuts()] == ["Ctrl+T", "Ctrl+L"]
    assert actions["refreshPivot"].shortcut().toString() == "Alt+F5"
    assert actions["refreshAll"].shortcut().toString() == "Ctrl+Alt+F5"
    assert actions["totalRow"].shortcut().toString() == "Ctrl+Shift+T"
    menu_titles = [action.text().replace("&", "") for action in window.menuBar().actions()]
    assert len(menu_titles) == len(set(menu_titles)), menu_titles
    data = window._menu("Data")
    titles = [action.text() for action in data.actions()]
    assert {"Table", "PivotTable", "What-If Analysis"} <= set(titles)
    what_if = window.findChild(QMenu, "whatIfMenu")
    assert [action.text() for action in what_if.actions()][:3] == [
        window.scenarios_action.text(),
        "Goal Seek...",
        "Data Table...",
    ]
    insert_texts = [action.text() for action in window._menu("Insert").actions()]
    assert insert_texts[:2] == ["PivotTable...", "Table..."]
    help_texts = [action.text() for action in window._menu("Help").actions()]
    assert "PivotTables, Tables, and What-If Tutorial..." in help_texts
    buttons = {button.objectName() for button in window.ribbon.findChildren(QToolButton)}
    assert {"pivotTableButton", "tableButton", "refreshAllButton", "WhatIfAnalysisGalleryButton", "analysisHelpButton"} <= buttons
    assert not actions["totalRow"].isEnabled()
    window.close()


def test_create_table_then_type_to_grow_it_and_add_totals() -> None:
    window = _window_with_sales()
    assert window._default_table_area() == (0, 0, 3, 2)
    assert window.create_table_at((0, 0, 3, 2))
    sheet = window.grid_model.sheet
    assert sheet.tables[0].name == "Table1"
    assert window.excel_actions["totalRow"].isEnabled()
    # A heading beside the table adds a column; a formula fills it down.
    assert _type(window, 0, 3, "Double")
    assert _type(window, 1, 3, "=[@Sales]*2")
    assert [_value(window, row, 3) for row in (1, 2, 3)] == [200, 100, 50]
    # Typing below the table adds a row that receives the calculated column.
    assert _type(window, 4, 0, "West")
    assert _type(window, 4, 2, "10")
    assert window.grid_model.sheet.tables[0].bottom == 4
    assert _value(window, 4, 3) == 20
    window.toggle_total_row()
    table = window.grid_model.sheet.tables[0]
    assert table.show_totals and window.excel_actions["totalRow"].isChecked()
    assert _value(window, 5, 3) == 370
    window.grid.setCurrentIndex(window.grid_model.index(2, 2))
    window.set_total_function("average")
    assert _value(window, 5, 2) == 46.25
    window.toggle_table_option("banded_rows")
    assert not window.grid_model.sheet.tables[0].banded_rows
    window.set_table_style("TableStyleDark1")
    assert window.grid_model.sheet.tables[0].style == "TableStyleDark1"
    assert window.rename_table_to("Table1", "Sales")
    assert window.grid_model.sheet.tables[0].name == "Sales"
    window.history.undo()
    assert window.grid_model.sheet.tables[0].name == "Table1"
    window.close()


def test_convert_to_range_keeps_values() -> None:
    window = _window_with_sales()
    window.create_table_at((0, 0, 3, 2))
    _type(window, 0, 3, "Double")
    _type(window, 1, 3, "=[@Sales]*2")
    window.grid.setCurrentIndex(window.grid_model.index(1, 1))
    assert window.convert_active_table()
    sheet = window.grid_model.sheet
    assert sheet.tables == []
    assert sheet.get_cell(1, 3).raw_input == "=$C2*2"
    assert _value(window, 3, 3) == 50
    window.close()


def test_insert_pivot_on_new_sheet_and_refresh() -> None:
    window = _window_with_sales()
    spec = window.pivot_from_source("Sheet1!$A$1:$C$4")
    assert spec.source == (0, 0, 3, 2) and spec.name == "PivotTable1"
    spec = PivotFieldsDialog.remove_field_spec(spec, "Sales")
    spec = spec.__class__(**{**{name: getattr(spec, name) for name in spec.__dataclass_fields__}, "rows": ("Region",), "values": (PivotValueField("Sales"),)})
    assert window.create_pivot(spec)
    workbook = window.engine.workbook
    assert workbook.sheet_names[0] != "Sheet1"
    assert window.grid_model.active_sheet_name == workbook.sheet_names[0]
    assert _value(window, 3, 0) == "East" and _value(window, 3, 1) == 125
    # Pivot cells can't be typed over.
    assert not _type(window, 3, 1, "9")
    assert "PivotTable" in window.grid_model.last_error
    # Change the source data, then refresh with the active cell in the report.
    window.engine.set_cell("Sheet1", 1, 2, 200)
    window.grid.setCurrentIndex(window.grid_model.index(3, 1))
    window.refresh_pivot()
    assert _value(window, 3, 1) == 225
    assert window.show_pivot_details()
    details = window.grid_model.sheet
    assert details.get_cell(0, 0).display_value == "Region"
    assert sorted(details.get_cell(row, 2).display_value for row in (1, 2)) == [25, 200]
    assert details.tables
    window.close()


def test_pivot_fields_dialog_places_fields_like_excel() -> None:
    window = _window_with_sales()
    spec = window.pivot_from_source("A1:C4")
    dialog = PivotFieldsDialog(window.engine.workbook, spec, window)
    items = {dialog.field_list.item(index).text(): dialog.field_list.item(index) for index in range(dialog.field_list.count())}
    items["Region"].setCheckState(Qt.CheckState.Checked)
    items["Sales"].setCheckState(Qt.CheckState.Checked)
    dialog.field_list.setCurrentItem(items["Product"])
    dialog.add_selected("columns")
    result = dialog.result_spec()
    assert result.rows == ("Region",) and result.columns == ("Product",)
    assert result.values == (PivotValueField("Sales", "sum"),)
    dialog.area_lists["values"].setCurrentRow(0)
    settings = ValueFieldDialog(result.values[0], dialog)
    settings.function.setCurrentIndex(2)
    assert settings.value().function == "average" and settings.value().name == "Average of Sales"
    items["Region"].setCheckState(Qt.CheckState.Unchecked)
    assert dialog.result_spec().rows == ()
    dialog.close()
    window.close()


def test_pivot_source_errors_are_explained() -> None:
    window = _window_with_sales()
    for text in ("A1:C1", "E1:F5"):
        try:
            window.pivot_from_source(text)
        except ValueError as error:
            assert "field name is not valid" in str(error)
        else:
            raise AssertionError(text)
    window.close()


def test_data_table_from_the_window(monkeypatch) -> None:
    application()
    window = MainWindow()
    for row, value in enumerate(("0.05", "360", "200000", "=PMT(B1/12,B2,-B3)")):
        _type(window, row, 1, value)
    _type(window, 5, 3, "=B4")
    _type(window, 6, 2, "4%")
    _type(window, 7, 2, "6%")
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    assert not window.create_data_table_at((5, 2, 7, 3), "", "Sheet2!B1")
    assert warnings[-1] == "Input cell reference is not valid."
    assert window.create_data_table_at((5, 2, 7, 3), "", "B1")
    assert round(_value(window, 6, 3), 2) == 954.83
    assert not _type(window, 6, 3, "1")
    window.grid.select_block(6, 3, 6, 3)
    window.clear_selection("contents")
    assert warnings[-1] == "Cannot change part of a data table."
    window.grid.select_block(6, 3, 7, 3)
    window.clear_selection("contents")
    assert window.grid_model.sheet.data_tables == []
    window.close()


def test_tutorial_covers_every_section_and_opens_lessons() -> None:
    application()
    assert {lesson.section for lesson in LESSONS} == set(SECTIONS)
    assert len({lesson.key for lesson in LESSONS}) == len(LESSONS)
    assert all(lesson.steps for lesson in LESSONS)
    assert "<ol>" in lesson_html(LESSONS[0])
    assert [lesson.key for lesson in search_lessons("two-variable")] == ["datatable-two"]
    dialog = AnalysisHelpDialog(topic="pivot-refresh")
    assert dialog.current_topic == "pivot-refresh"
    assert "GETPIVOTDATA" in dialog.detail.toPlainText()
    dialog.search.setText("Total Function")
    assert dialog.current_topic == "table-totals"
    dialog.close()


def test_practice_workbook_contains_working_examples() -> None:
    workbook = build_practice_workbook()
    assert workbook.sheet_names == ("Sales", "Pivot", "Loan")
    sales = workbook.get_sheet("Sales")
    assert sales.tables[0].name == "SalesTable" and sales.tables[0].show_totals
    assert sales.get_cell(11, 5).display_value == 1635
    pivot = workbook.get_sheet("Pivot")
    assert pivot.get_cell(7, 0).display_value == "Grand Total" and pivot.get_cell(7, 3).display_value == 1635
    loan = workbook.get_sheet("Loan")
    assert round(loan.get_cell(8, 5).display_value, 2) == 1342.05
    application()
    window = MainWindow()
    window.open_practice_workbook()
    assert window.engine.workbook.sheet_names == ("Sales", "Pivot", "Loan")
    window.close()


def test_context_menu_offers_table_and_pivot_commands() -> None:
    window = _window_with_sales()
    window.create_table_at((0, 0, 3, 2))
    window.grid.setCurrentIndex(window.grid_model.index(1, 0))
    titles = [action.text() for action in window.cell_context_menu().actions()]
    assert "Table" in titles
    window.close()


def test_create_table_dialog_runs_from_ctrl_t(monkeypatch) -> None:
    from duddysheet.ui.dialogs import analysis_dialogs

    window = _window_with_sales()
    seen: list[str] = []

    def accept(dialog: QDialog) -> int:
        seen.append(dialog.range.text())
        assert dialog.headers.isChecked()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(analysis_dialogs.CreateTableDialog, "exec", accept)
    window.excel_actions["createTable"].trigger()
    assert seen == ["$A$1:$C$4"]
    assert window.grid_model.sheet.tables[0].rect == (0, 0, 3, 2)
    window.close()
