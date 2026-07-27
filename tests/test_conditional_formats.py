from __future__ import annotations

import pytest

from duddysheet.core.cell import CellFormat
from duddysheet.core.conditional import (
    ConditionalFormatEngine,
    ConditionalRule,
    FormatPatch,
)
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook


def workbook_with_values() -> Workbook:
    workbook = Workbook()
    for row, value in enumerate((10, 20, 20, 40, 50)):
        workbook.active_sheet.set_cell(row, 0, value)
    return workbook


def test_cell_value_rule_overlays_base_format() -> None:
    workbook = workbook_with_values()
    rule = ConditionalRule(
        range=parse_a1("A1:A5"),
        kind="cell_value",
        operator="greater_than",
        values=(30,),
        format_patch=FormatPatch(fill_color="#ffcccc", bold=True),
    )
    workbook.active_sheet.conditional_formats.append(rule)
    engine = ConditionalFormatEngine(workbook)

    result = engine.evaluate(workbook.active_sheet, 3, 0)
    unaffected = engine.evaluate(workbook.active_sheet, 0, 0)

    assert result.format.fill_color == "#ffcccc"
    assert result.format.bold
    assert unaffected.format == CellFormat()


def test_top_bottom_average_and_duplicate_rules() -> None:
    workbook = workbook_with_values()
    target = parse_a1("A1:A5")
    workbook.active_sheet.conditional_formats.extend(
        [
            ConditionalRule(
                range=target,
                kind="top_bottom",
                rank=1,
                format_patch=FormatPatch(font_color="#ff0000"),
            ),
            ConditionalRule(
                range=target,
                kind="above_average",
                format_patch=FormatPatch(italic=True),
            ),
            ConditionalRule(
                range=target,
                kind="duplicate",
                format_patch=FormatPatch(underline=True),
            ),
        ]
    )
    engine = ConditionalFormatEngine(workbook)

    maximum = engine.evaluate(workbook.active_sheet, 4, 0)
    duplicate = engine.evaluate(workbook.active_sheet, 1, 0)

    assert maximum.format.font_color == "#ff0000"
    assert maximum.format.italic
    assert duplicate.format.underline


def test_formula_rule_and_stop_if_true() -> None:
    workbook = workbook_with_values()
    target = parse_a1("A1:A5")
    workbook.active_sheet.conditional_formats.extend(
        [
            ConditionalRule(
                range=target,
                kind="formula",
                formula="=A1=10",
                format_patch=FormatPatch(fill_color="#00ff00"),
                stop_if_true=True,
            ),
            ConditionalRule(
                range=target,
                kind="cell_value",
                operator="equal",
                values=(10,),
                format_patch=FormatPatch(font_color="#ff0000"),
            ),
        ]
    )

    result = ConditionalFormatEngine(workbook).evaluate(
        workbook.active_sheet,
        0,
        0,
    )

    assert result.format.fill_color == "#00ff00"
    assert result.format.font_color == "#000000"


def test_formula_rule_translates_relative_references_from_range_origin() -> None:
    workbook = workbook_with_values()
    target = parse_a1("A1:A5")
    workbook.active_sheet.conditional_formats.extend(
        [
            ConditionalRule(
                target,
                "formula",
                formula="=A1>15",
                format_patch=FormatPatch(bold=True),
            ),
            ConditionalRule(
                target,
                "formula",
                formula="=$A$1=10",
                format_patch=FormatPatch(italic=True),
            ),
        ]
    )
    engine = ConditionalFormatEngine(workbook)

    assert not engine.evaluate(workbook.active_sheet, 0, 0).format.bold
    assert engine.evaluate(workbook.active_sheet, 3, 0).format.bold
    assert engine.evaluate(workbook.active_sheet, 3, 0).format.italic


def test_color_scale_data_bar_and_icon_set_visuals() -> None:
    workbook = workbook_with_values()
    target = parse_a1("A1:A5")
    workbook.active_sheet.conditional_formats.extend(
        [
            ConditionalRule(
                range=target,
                kind="color_scale",
                colors=("#f8696b", "#ffeb84", "#63be7b"),
            ),
            ConditionalRule(range=target, kind="data_bar"),
            ConditionalRule(range=target, kind="icon_set"),
        ]
    )
    engine = ConditionalFormatEngine(workbook)

    low = engine.evaluate(workbook.active_sheet, 0, 0)
    high = engine.evaluate(workbook.active_sheet, 4, 0)

    assert low.format.fill_color == "#f8696b"
    assert high.format.fill_color == "#63be7b"
    assert low.data_bar == 0
    assert high.data_bar == 1
    assert low.icon == "down"
    assert high.icon == "up"


def test_nonmatching_and_invalid_conditional_rules_are_ignored() -> None:
    workbook = workbook_with_values()
    sheet = workbook.active_sheet
    sheet.conditional_formats.extend(
        [
            "legacy-rule",
            ConditionalRule(parse_a1("Other!A1:A5"), "cell_value", values=(10,)),
            ConditionalRule(parse_a1("B1:B5"), "cell_value", values=(10,)),
            ConditionalRule(parse_a1("A1:A5"), "formula"),
            ConditionalRule(parse_a1("A1:A5"), "unknown"),
        ]
    )

    assert ConditionalFormatEngine(workbook).evaluate(sheet, 0, 0).format == CellFormat()


@pytest.mark.parametrize(
    ("operator", "operands", "expected"),
    [
        ("equal", (20,), True),
        ("not_equal", (10,), True),
        ("greater_equal", (20,), True),
        ("less_than", (30,), True),
        ("less_equal", (20,), True),
        ("between", (15, 25), True),
        ("not_between", (30, 40), True),
        ("between", (15,), False),
        ("unknown", (20,), False),
        ("equal", (), False),
        ("greater_than", ("text",), False),
    ],
)
def test_cell_value_rule_operators(
    operator: str,
    operands: tuple[object, ...],
    expected: bool,
) -> None:
    workbook = workbook_with_values()
    workbook.active_sheet.conditional_formats.append(
        ConditionalRule(
            parse_a1("A1:A5"),
            "cell_value",
            operator,
            operands,
            FormatPatch(bold=True),
        )
    )

    result = ConditionalFormatEngine(workbook).evaluate(
        workbook.active_sheet,
        1,
        0,
    )

    assert result.format.bold is expected


def test_bottom_percent_below_average_two_color_scale_and_equal_data_bar() -> None:
    workbook = workbook_with_values()
    sheet = workbook.active_sheet
    target = parse_a1("A1:A5")
    sheet.conditional_formats.extend(
        [
            ConditionalRule(
                target,
                "top_bottom",
                rank=40,
                percent=True,
                above=False,
                format_patch=FormatPatch(bold=True),
            ),
            ConditionalRule(
                target,
                "above_average",
                above=False,
                format_patch=FormatPatch(italic=True),
            ),
            ConditionalRule(target, "color_scale", colors=("#000000", "#ffffff")),
        ]
    )
    low = ConditionalFormatEngine(workbook).evaluate(sheet, 0, 0)

    assert low.format.bold
    assert low.format.italic
    assert low.format.fill_color == "#000000"

    equal_workbook = Workbook()
    equal_workbook.active_sheet.set_cell(0, 0, 5)
    equal_workbook.active_sheet.set_cell(1, 0, 5)
    equal_workbook.active_sheet.conditional_formats.append(
        ConditionalRule(parse_a1("A1:A2"), "data_bar")
    )
    assert (
        ConditionalFormatEngine(equal_workbook).evaluate(
            equal_workbook.active_sheet,
            0,
            0,
        ).data_bar
        == 0
    )


def test_numeric_conditional_rules_ignore_text_boolean_and_empty_ranges() -> None:
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, True)
    sheet.set_cell(1, 0, "text")
    sheet.conditional_formats.append(
        ConditionalRule(parse_a1("A1:A2"), "data_bar")
    )
    engine = ConditionalFormatEngine(workbook)

    assert engine.evaluate(sheet, 0, 0).data_bar is None
    assert engine.evaluate(sheet, 1, 0).data_bar is None
