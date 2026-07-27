from __future__ import annotations

from datetime import date

import pytest

from duddysheet.core.data_tools import (
    DataValidation,
    FindOptions,
    SortKey,
    apply_filter,
    clear_filter,
    find_cells,
    remove_duplicates,
    replace_matches,
    sort_range,
    text_to_columns,
    validate_value,
)
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import CellReference, parse_a1
from duddysheet.core.workbook import Workbook


def table_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active_sheet
    rows = (
        ("Name", "Team", "Score"),
        ("Amy", "Blue", 8),
        ("Ben", "Red", 10),
        ("Cara", "Blue", 10),
        ("Dan", "Red", 7),
    )
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            sheet.set_cell(row, column, value)
    return workbook


def test_multi_key_sort_preserves_header_and_orders_mixed_directions() -> None:
    workbook = table_workbook()

    sort_range(
        workbook,
        "Sheet1",
        parse_a1("A1:C5"),
        (SortKey(1, True), SortKey(2, False)),
        has_header=True,
    )

    sheet = workbook.active_sheet
    assert [sheet.get_cell(row, 0).display_value for row in range(5)] == [
        "Name",
        "Cara",
        "Amy",
        "Ben",
        "Dan",
    ]


def test_sort_translates_formulas_to_their_new_rows() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, "Key")
    engine.set_cell("Sheet1", 0, 1, "Calc")
    engine.set_cell("Sheet1", 1, 0, 2)
    engine.set_cell("Sheet1", 1, 1, "=A2*10")
    engine.set_cell("Sheet1", 2, 0, 1)
    engine.set_cell("Sheet1", 2, 1, "=A3*10")

    sort_range(
        workbook,
        "Sheet1",
        parse_a1("A1:B3"),
        (SortKey(0),),
        has_header=True,
    )
    engine.rebuild_index()

    assert workbook.active_sheet.get_cell(1, 1).display_value == 10
    assert "A2" in workbook.active_sheet.get_cell(1, 1).raw_input


def test_filter_hides_nonmatching_rows_and_clear_restores_only_filter_rows() -> None:
    workbook = table_workbook()
    sheet = workbook.active_sheet
    sheet.hidden_rows.add(10)

    apply_filter(
        sheet,
        parse_a1("A1:C5"),
        column=1,
        allowed_values={"Blue"},
        has_header=True,
    )

    assert sheet.filtered_rows == {2, 4}
    assert {2, 4, 10} <= sheet.hidden_rows
    clear_filter(sheet)
    assert sheet.filtered_rows == set()
    assert sheet.hidden_rows == {10}


@pytest.mark.parametrize(
    ("validation", "value", "valid"),
    [
        (DataValidation(parse_a1("A1"), "list", values=("Red", "Blue")), "Red", True),
        (DataValidation(parse_a1("A1"), "list", values=("Red", "Blue")), "Green", False),
        (DataValidation(parse_a1("A1"), "whole_number", "between", (1, 10)), 5, True),
        (DataValidation(parse_a1("A1"), "whole_number", "between", (1, 10)), 5.5, False),
        (DataValidation(parse_a1("A1"), "decimal", "greater_than", (0,)), 0.1, True),
        (
            DataValidation(
                parse_a1("A1"),
                "date",
                "between",
                (date(2026, 1, 1), date(2026, 12, 31)),
            ),
            date(2026, 7, 25),
            True,
        ),
        (DataValidation(parse_a1("A1"), "text_length", "less_equal", (5,)), "hello!", False),
    ],
)
def test_data_validation_kinds(
    validation: DataValidation,
    value: object,
    valid: bool,
) -> None:
    result = validate_value(validation, value, Workbook(), "Sheet1", (0, 0))
    assert result.valid is valid


def test_custom_formula_validation_and_blank_policy() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 5)
    custom = DataValidation(
        parse_a1("B1"),
        "custom",
        formula="=A1>0",
        allow_blank=False,
    )

    assert validate_value(custom, 3, workbook, "Sheet1", (0, 1)).valid
    assert not validate_value(custom, None, workbook, "Sheet1", (0, 1)).valid

    candidate_rule = DataValidation(
        parse_a1("B1"),
        "custom",
        formula="=B1>0",
    )
    assert validate_value(candidate_rule, 2, workbook, "Sheet1", (0, 1)).valid
    assert not validate_value(
        candidate_rule,
        -2,
        workbook,
        "Sheet1",
        (0, 1),
    ).valid


def test_find_values_and_regex_formula_scope() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, "Alpha")
    engine.set_cell("Sheet1", 1, 0, "alphabet")
    engine.set_cell("Sheet1", 0, 1, "=A1&\" beta\"")

    values = find_cells(workbook, FindOptions("alpha", match_case=False))
    formulas = find_cells(
        workbook,
        FindOptions(r"A1&", regex=True, look_in="formulas"),
    )

    assert values == (
        CellReference(0, 0, sheet="Sheet1"),
        CellReference(0, 1, sheet="Sheet1"),
        CellReference(1, 0, sheet="Sheet1"),
    )
    assert formulas == (CellReference(0, 1, sheet="Sheet1"),)


def test_remove_duplicates_compacts_rows_and_text_to_columns_splits_data() -> None:
    workbook = Workbook()
    sheet = workbook.active_sheet
    rows = (("Code", "Value"), ("A", 1), ("A", 2), ("B", 3))
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            sheet.set_cell(row, column, value)

    removed = remove_duplicates(
        sheet,
        parse_a1("A1:B4"),
        key_columns=(0,),
        has_header=True,
    )
    sheet.set_cell(0, 3, "first|second|third")
    columns = text_to_columns(sheet, parse_a1("D1:D1"), delimiter="|")

    assert removed == 1
    assert sheet.get_cell(1, 0).display_value == "A"
    assert sheet.get_cell(2, 0).display_value == "B"
    assert sheet.get_cell(3, 0).is_empty
    assert columns == 3
    assert sheet.get_cell(0, 5).display_value == "third"


def test_replace_matches_supports_values_formulas_regex_and_whole_cell() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, "Alpha beta")
    engine.set_cell("Sheet1", 1, 0, "Alpha")
    engine.set_cell("Sheet1", 0, 1, '=A2&"!"')

    count = replace_matches(
        workbook,
        FindOptions(
            r"alpha",
            "Omega",
            regex=True,
            look_in="values",
            whole_cell=True,
        ),
    )
    formula_count = replace_matches(
        workbook,
        FindOptions("A2", "A1", look_in="formulas"),
    )
    engine.rebuild_index()

    assert count == 1
    assert formula_count == 1
    assert workbook.active_sheet.get_cell(1, 0).raw_input == "Omega"
    assert workbook.active_sheet.get_cell(0, 1).display_value == "Alpha beta!"


def test_data_tool_invalid_inputs_are_rejected() -> None:
    workbook = table_workbook()
    sheet = workbook.active_sheet
    with pytest.raises(ValueError, match="at least one"):
        sort_range(workbook, "Sheet1", parse_a1("A1:C5"), ())
    with pytest.raises(ValueError, match="outside"):
        sort_range(
            workbook,
            "Sheet1",
            parse_a1("A1:C5"),
            (SortKey(5),),
        )
    with pytest.raises(ValueError, match="outside"):
        apply_filter(
            sheet,
            parse_a1("A1:C5"),
            column=5,
            allowed_values=set(),
        )
    with pytest.raises(ValueError, match="scope"):
        find_cells(workbook, FindOptions("x", look_in="invalid"))
    with pytest.raises(ValueError, match="key columns"):
        remove_duplicates(sheet, parse_a1("A1:C5"), key_columns=())
    with pytest.raises(ValueError, match="one character"):
        text_to_columns(sheet, parse_a1("A1:A2"), delimiter="::")


@pytest.mark.parametrize(
    ("operator", "value", "operands", "valid"),
    [
        ("equal", 3, (3,), True),
        ("not_equal", 3, (4,), True),
        ("greater_equal", 3, (3,), True),
        ("less_than", 3, (4,), True),
        ("not_between", 3, (4, 6), True),
        ("unknown", 3, (3,), False),
        ("greater_than", 3, (), False),
        ("greater_than", 3, ("text",), False),
    ],
)
def test_validation_comparison_operators(
    operator: str,
    value: int,
    operands: tuple[object, ...],
    valid: bool,
) -> None:
    validation = DataValidation(
        parse_a1("A1"),
        "whole_number",
        operator,
        operands,
    )
    assert validate_value(validation, value, Workbook(), "Sheet1", (0, 0)).valid is valid
