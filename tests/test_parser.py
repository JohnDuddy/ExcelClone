from __future__ import annotations

import pytest

from duddysheet.core.parser import collect_references, parse_formula, shift_references
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.tokenizer import FormulaSyntaxError


@pytest.mark.parametrize(
    "formula",
    [
        "=1",
        "=-1",
        "=+1",
        "=50%",
        "=2^3^2",
        "=1+2*3",
        '="A"&"B"',
        "=1<2",
        "=1<=2",
        "=1<>2",
        "=A1",
        "=$A$1",
        "=A1:B10",
        "=A:A",
        "=1:2",
        "=Sheet2!A1",
        "='My Sheet'!A1:B2",
        "=A1:B2 B2:C3",
        "=(A1,B2)",
        "=SUM(A1:A3, 4)",
        '=IF(A1>0, "yes", "no")',
        "={1,2;3,4}",
        "=-(1+2)^2%",
    ],
)
def test_valid_formulas_parse(formula: str) -> None:
    assert parse_formula(formula) is not None


def test_shift_references_moves_relative_parts_and_preserves_absolute_parts() -> None:
    shifted = shift_references(parse_formula("=A1+$B1+C$2+$D$3"), rows=2, columns=3)

    references = collect_references(shifted)

    assert [reference.to_a1() for reference in references] == [
        "D3",
        "$B3",
        "F$2",
        "$D$3",
    ]


@pytest.mark.parametrize(
    "formula",
    [
        "=",
        "=1+",
        "=*1",
        "=(1+2",
        "=1+2)",
        "=SUM(",
        "=SUM(1,)",
        "=SUM(,1)",
        "=A0",
        "=XFE1",
        "=A1:",
        "=:A1",
        "=A1:B2:C3",
        "=Sheet!",
        "='Sheet' A1",
        "={}",
        "={1,2;3}",
        "=1 2",
        "=!",
        "=#UNKNOWN!",
    ],
)
def test_invalid_formulas_raise_syntax_error(formula: str) -> None:
    with pytest.raises(FormulaSyntaxError):
        parse_formula(formula)


def test_collect_references_reports_cells_ranges_and_names() -> None:
    ast = parse_formula("=A1+$B$2+SUM(Data!C3:C5)+TaxRate")

    references = collect_references(ast)

    assert CellReference(0, 0) in references
    assert CellReference(1, 1, row_absolute=True, column_absolute=True) in references
    assert RangeReference(
        CellReference(2, 2, sheet="Data"),
        CellReference(4, 2, sheet="Data"),
    ) in references
    assert "TaxRate" in references


def test_function_names_are_not_reported_as_defined_names() -> None:
    references = collect_references(parse_formula("=SUM(A1, ABS(B1))"))

    assert references == (CellReference(0, 0), CellReference(0, 1))
