from __future__ import annotations

import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.core.chart import ChartSpec
from excelclone.core.conditional import ConditionalRule, FormatPatch
from excelclone.core.data_tools import DataValidation, apply_filter
from excelclone.core.refs import parse_a1
from excelclone.core.workbook import Workbook
from excelclone.io.native import CURRENT_SCHEMA_VERSION, load_ogrid, save_ogrid


def rich_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(
        0,
        0,
        12.5,
        cell_format=CellFormat(
            number_format="$#,##0.00",
            font_family="Cambria",
            font_size=13,
            bold=True,
            italic=True,
            underline=True,
            font_color="#112233",
            fill_color="#ffeeaa",
            horizontal_alignment="center",
            vertical_alignment="top",
            wrap_text=True,
            bottom_border=BorderStyle("double", "#445566"),
        ),
    )
    sheet.set_cell(0, 1, "=A1*2")
    sheet.row_heights[0] = 27.5
    sheet.column_widths[0] = 18.25
    sheet.hidden_rows.add(4)
    sheet.hidden_columns.add(5)
    sheet.merged_ranges.append(parse_a1("C3:D4"))
    sheet.freeze_panes = (2, 1)
    sheet.tab_color = "#44aa66"
    sheet.conditional_formats.append(
        ConditionalRule(
            parse_a1("A1:A10"),
            "cell_value",
            "greater_than",
            (10,),
            FormatPatch(fill_color="#ffcccc", bold=True),
            stop_if_true=True,
        )
    )
    sheet.data_validations.append(
        DataValidation(
            parse_a1("A1:A10"),
            "decimal",
            "greater_than",
            (0,),
        )
    )
    sheet.charts.append(
        ChartSpec(
            "sales",
            "Sheet1",
            parse_a1("A1:B2"),
            "line",
            title="Sales",
            theme="editorial",
            show_data_labels=True,
            show_trendline=True,
            highlight_extrema=True,
            secondary_axis=True,
            number_format="currency",
        )
    )
    apply_filter(
        sheet,
        parse_a1("A1:A10"),
        column=0,
        allowed_values={12.5},
        has_header=False,
    )
    workbook.add_sheet("Data").visible = False
    workbook.active_sheet = "Data"
    workbook.define_name("InputValue", "Sheet1!$A$1")
    workbook.define_name("LocalValue", "Sheet1!$A$1", scope="Sheet1")
    return workbook


def test_ogrid_round_trip_is_lossless(tmp_path) -> None:
    path = tmp_path / "book.ogrid"
    original = rich_workbook()

    save_ogrid(original, path)
    loaded = load_ogrid(path)

    assert loaded.sheet_names == ("Sheet1", "Data")
    assert loaded.active_sheet.name == "Data"
    assert loaded.defined_names == original.defined_names
    source = original.get_sheet("Sheet1")
    restored = loaded.get_sheet("Sheet1")
    assert tuple(restored.iter_populated()) == tuple(source.iter_populated())
    assert restored.row_heights == source.row_heights
    assert restored.column_widths == source.column_widths
    assert restored.hidden_rows == source.hidden_rows
    assert restored.hidden_columns == source.hidden_columns
    assert restored.merged_ranges == source.merged_ranges
    assert restored.freeze_panes == source.freeze_panes
    assert restored.tab_color == source.tab_color
    assert restored.conditional_formats == source.conditional_formats
    assert restored.data_validations == source.data_validations
    assert restored.auto_filter == source.auto_filter
    assert restored.filtered_rows == source.filtered_rows
    assert restored.charts == source.charts
    assert not loaded.get_sheet("Data").visible


def test_ogrid_archive_has_versioned_manifest_and_per_sheet_json(tmp_path) -> None:
    path = tmp_path / "book.ogrid"
    save_ogrid(rich_workbook(), path)

    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("workbook.json"))
        names = set(archive.namelist())

    assert manifest["schema_version"] == CURRENT_SCHEMA_VERSION
    assert names == {"workbook.json", "sheets/0000.json", "sheets/0001.json"}


def test_future_ogrid_schema_is_rejected_clearly(tmp_path) -> None:
    path = tmp_path / "future.ogrid"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "workbook.json",
            json.dumps(
                {
                    "schema_version": CURRENT_SCHEMA_VERSION + 1,
                    "active_sheet": 0,
                    "sheets": [],
                    "defined_names": [],
                }
            ),
        )

    with pytest.raises(ValueError, match="newer OpenGrid version"):
        load_ogrid(path)
