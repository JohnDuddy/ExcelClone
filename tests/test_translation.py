from __future__ import annotations

from duddysheet.core.parser import collect_references, parse_formula
from duddysheet.core.translation import (
    formula_to_text,
    rename_formula_sheet,
    translate_formula_copy,
    translate_reference_structure,
    translate_formula_structure,
)
from duddysheet.core.refs import parse_a1

import pytest


def test_formula_text_round_trip_preserves_expression_semantics() -> None:
    formula = '=IF(A1>0,"yes","no")&SUM(B1:B3)'

    rendered = formula_to_text(parse_formula(formula))

    assert collect_references(parse_formula(rendered)) == collect_references(
        parse_formula(formula)
    )


def test_copy_translation_shifts_only_relative_reference_parts() -> None:
    translated = translate_formula_copy(
        "=A1+$B1+C$2+$D$3",
        rows=2,
        columns=3,
    )

    assert [
        reference.to_a1()
        for reference in collect_references(parse_formula(translated))
    ] == ["D3", "$B3", "F$2", "$D$3"]


def test_insert_translation_expands_ranges_and_moves_absolute_references() -> None:
    translated = translate_formula_structure(
        "=SUM($A$1:$A$2)+$A$2",
        formula_sheet="Sheet1",
        target_sheet="Sheet1",
        axis="row",
        index=1,
        count=1,
        delete=False,
    )

    assert [
        reference.to_a1()
        for reference in collect_references(parse_formula(translated))
    ] == ["$A$1:$A$3", "$A$3"]


def test_delete_translation_shrinks_ranges_and_invalidates_deleted_cells() -> None:
    translated = translate_formula_structure(
        "=SUM(A1:A3)+B2",
        formula_sheet="Sheet1",
        target_sheet="Sheet1",
        axis="row",
        index=1,
        count=1,
        delete=True,
    )

    assert "A1:A2" in translated
    assert "#REF!" in translated


def test_structure_translation_ignores_unqualified_other_sheet_references() -> None:
    translated = translate_formula_structure(
        "=A1+Sheet1!A1",
        formula_sheet="Data",
        target_sheet="Sheet1",
        axis="row",
        index=0,
        count=2,
        delete=False,
    )

    references = collect_references(parse_formula(translated))
    assert [reference.to_a1() for reference in references] == [
        "A1",
        "Sheet1!A3",
    ]


def test_formula_renderer_handles_arrays_names_unary_percent_and_errors() -> None:
    rendered = formula_to_text(
        parse_formula("=-A1%+SUM({1,2;3,4})+#N/A")
    )

    assert parse_formula(rendered) is not None
    assert "{" in rendered
    assert "#N/A" in rendered


def test_sheet_rename_translates_quoted_ranges_and_qualified_names() -> None:
    translated = rename_formula_sheet(
        "='Old Data'!A1:B2+'Old Data'!LocalName",
        "Old Data",
        "New Data",
    )

    assert "'New Data'!A1:B2" in translated
    assert "'New Data'!LocalName" in translated


def test_structure_reference_translation_handles_reversed_and_whole_ranges() -> None:
    reversed_range = translate_reference_structure(
        parse_a1("A3:A1"),
        axis="row",
        index=1,
        count=1,
        delete=True,
    )
    whole_column = translate_reference_structure(
        parse_a1("A:A"),
        axis="row",
        index=0,
        count=2,
        delete=False,
    )
    whole_row = translate_reference_structure(
        parse_a1("1:1"),
        axis="column",
        index=0,
        count=2,
        delete=False,
    )

    assert reversed_range is not None and reversed_range.to_a1() == "A2:A1"
    assert whole_column == parse_a1("A:A")
    assert whole_row == parse_a1("1:1")


def test_structure_translation_rejects_bad_axis_and_count() -> None:
    with pytest.raises(ValueError, match="axis"):
        translate_formula_structure(
            "=A1",
            formula_sheet="Sheet1",
            target_sheet="Sheet1",
            axis="depth",
            index=0,
            count=1,
            delete=False,
        )
    with pytest.raises(ValueError, match="positive"):
        translate_formula_structure(
            "=A1",
            formula_sheet="Sheet1",
            target_sheet="Sheet1",
            axis="row",
            index=0,
            count=0,
            delete=False,
        )
