from __future__ import annotations

import math

import pytest

from excelclone.core.engine import FormulaEngine
from excelclone.core.chart import chart_data
from excelclone.core.financial_help import FINANCIAL_HELP_ENTRIES
from excelclone.core.financial_models import (
    COMMON_FINANCIAL_METRICS,
    FINANCIAL_LAB_FUNCTIONS,
    FINANCIAL_MODEL_CATALOG,
    create_financial_model,
)
from excelclone.core.refs import CellReference, parse_a1
from excelclone.io.native import load_ogrid, save_ogrid
from excelclone.io.xlsx_reader import read_xlsx
from excelclone.io.xlsx_writer import write_xlsx


def value_at(workbook: object, reference: str) -> object:
    selected = parse_a1(reference, default_sheet=workbook.active_sheet.name)
    assert isinstance(selected, CellReference)
    return workbook.get_sheet(selected.sheet).get_cell(
        selected.row,
        selected.column,
    ).display_value


def test_financial_model_catalog_has_seven_unique_professional_templates() -> None:
    assert {template.key for template in FINANCIAL_MODEL_CATALOG} == {
        "dcf",
        "three_statement",
        "lbo",
        "loan",
        "rental",
        "budget",
        "financial_lab",
    }
    assert len({template.name for template in FINANCIAL_MODEL_CATALOG}) == 7
    assert all(template.description for template in FINANCIAL_MODEL_CATALOG)


@pytest.mark.parametrize("template", FINANCIAL_MODEL_CATALOG, ids=lambda item: item.key)
def test_financial_models_recalculate_without_formula_errors(template: object) -> None:
    workbook = create_financial_model(template.key)
    formulas = 0
    errors: list[str] = []
    for sheet in workbook:
        for _, cell in sheet.iter_populated():
            formulas += int(cell.is_formula)
            if cell.error is not None:
                errors.append(cell.error)

    primary = value_at(workbook, template.primary_output)

    assert len(workbook) >= 2
    assert formulas >= 60
    assert errors == []
    assert isinstance(primary, (int, float))
    assert math.isfinite(primary)


def test_dcf_and_three_statement_models_include_working_integrity_checks() -> None:
    dcf = create_financial_model("dcf")
    three_statement = create_financial_model("three_statement")

    assert value_at(dcf, "Checks!B4") == "OK"
    assert value_at(dcf, "Checks!B5") == "OK"
    for column in "BCDEF":
        assert value_at(
            three_statement,
            f"'Balance Sheet'!{column}16",
        ) == pytest.approx(0, abs=1e-9)
        assert value_at(
            three_statement,
            f"Checks!{column}5",
        ) == pytest.approx(0, abs=1e-9)


def test_loan_model_builds_full_term_and_pays_balance_to_zero() -> None:
    workbook = create_financial_model("loan")
    schedule = workbook.get_sheet("Amortization")

    assert schedule.get_cell(363, 0).display_value == 360
    assert schedule.get_cell(363, 6).display_value == pytest.approx(0, abs=1e-7)
    assert value_at(workbook, "Summary!B9") > 0
    assert value_at(workbook, "Summary!B11") > 0


def test_lbo_irr_uses_an_excel_compatible_cash_flow_range() -> None:
    workbook = create_financial_model("lbo")
    returns = workbook.get_sheet("Returns")

    assert returns.get_cell(11, 1).raw_input == "=IRR(B13:G13)"
    assert returns.get_cell(12, 1).raw_input == "=-B5"
    assert returns.get_cell(12, 6).raw_input == "=B10"
    assert returns.get_cell(11, 1).error is None


def test_financial_lab_covers_every_financial_function_and_common_metrics() -> None:
    workbook = create_financial_model("financial_lab")
    function_names = {
        str(workbook.get_sheet("Function Lab").get_cell(row, 2).display_value)
        for row in range(3, 49)
    }
    registered_financial_functions = {
        entry.name for entry in FINANCIAL_HELP_ENTRIES
    }

    assert len(FINANCIAL_LAB_FUNCTIONS) == 46
    assert len(COMMON_FINANCIAL_METRICS) == 30
    assert function_names == registered_financial_functions
    assert value_at(workbook, "Guide!B4") == 46
    assert value_at(workbook, "Guide!B5") == 30
    assert value_at(workbook, "Guide!B6") == 76


def test_financial_lab_includes_twelve_working_editable_charts() -> None:
    workbook = create_financial_model("financial_lab")
    charts = [chart for sheet in workbook for chart in sheet.charts]

    assert len(charts) == 12
    assert len({chart.chart_id for chart in charts}) == 12
    assert {chart.chart_type for chart in charts} >= {
        "box",
        "combo",
        "donut",
        "heatmap",
        "histogram",
        "line",
        "radar",
        "scatter",
        "waterfall",
    }
    for chart in charts:
        data = chart_data(workbook, chart)
        assert data.series
        assert all(series.values for series in data.series)


def test_financial_lab_native_round_trip_preserves_formulas_and_charts(
    tmp_path,
) -> None:
    path = tmp_path / "Financial Calculations Lab.ogrid"
    source = create_financial_model("financial_lab")

    save_ogrid(source, path)
    restored = load_ogrid(path)
    FormulaEngine(restored).rebuild_index()

    assert restored.sheet_names == source.sheet_names
    assert value_at(restored, "Guide!B6") == 76
    assert sum(len(sheet.charts) for sheet in restored) == 12
    assert not [
        cell.error
        for sheet in restored
        for _, cell in sheet.iter_populated()
        if cell.error is not None
    ]


def test_unknown_financial_model_is_rejected_with_available_keys() -> None:
    with pytest.raises(ValueError, match="Unknown financial model"):
        create_financial_model("not-a-model")


@pytest.mark.parametrize("key", ("dcf", "loan", "rental"))
def test_financial_models_export_to_xlsx_and_recalculate(
    key: str,
    tmp_path,
) -> None:
    path = tmp_path / f"{key}.xlsx"
    source = create_financial_model(key)

    write_xlsx(source, path)
    imported = read_xlsx(path).workbook
    FormulaEngine(imported).rebuild_index()

    assert imported.sheet_names == source.sheet_names
    assert not [
        cell.error
        for sheet in imported
        for _, cell in sheet.iter_populated()
        if cell.error is not None
    ]
