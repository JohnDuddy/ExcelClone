"""Excel 365 calculation semantics: arrays, spills, operators, names, and LAMBDA."""

from __future__ import annotations

from time import perf_counter

import pytest

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.errors import (
    CALC_ERROR,
    NA_ERROR,
    NAME_ERROR,
    REF_ERROR,
    VALUE_ERROR,
)
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.parser import parse_formula
from duddysheet.core.translation import formula_to_text, translate_formula_copy
from duddysheet.core.workbook import Workbook


@pytest.fixture
def engine() -> FormulaEngine:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    for row in range(5):
        engine.set_cell("Sheet1", row, 0, row + 1)
        engine.set_cell("Sheet1", row, 1, "x" if row % 2 else "y")
    return engine


def value_at(engine: FormulaEngine, formula: str, row: int = 20, column: int = 6) -> object:
    engine.set_cell("Sheet1", row, column, formula)
    cell = engine.workbook.active_sheet.get_cell(row, column)
    return cell.error if cell.error is not None else cell.cached_value


def spill_at(engine: FormulaEngine, formula: str, row: int = 20, column: int = 6) -> list[list[object]]:
    engine.set_cell("Sheet1", row, column, formula)
    sheet = engine.workbook.active_sheet
    rows: list[list[object]] = []
    for r in range(row, row + 12):
        line = []
        for c in range(column, column + 6):
            cell = sheet.get_cell(r, c)
            if (r, c) == (row, column) or cell.spill_parent == (row, column):
                line.append(cell.error if cell.error is not None else cell.cached_value)
        if line:
            rows.append(line)
    return rows


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=SUMPRODUCT((B1:B5=\"x\")*A1:A5)", 6),
        ("=SUM(A1:A5*2)", 30),
        ("=MAX(IF(A1:A5>2,A1:A5))", 5),
        ("=SUM(A1:INDEX(A1:A5,3))", 6),
        ("=ROWS(A1:INDEX(A:A,4))", 4),
        ("=SUM((A1:A2,A2:A3))", 8),
        ("=COUNTIF(A:A,\">2\")", 3),
        ("=VLOOKUP(3,A:B,2,0)", "y"),
        ("=SUM(A:A)", 15),
        ("=IF(1,,)", 0),
        ("=SUM(1,)", 1),
        ("=Z99", 0),
        ("=AND(TRUE,Z1:Z3)", True),
    ],
)
def test_arrays_and_ranges_follow_excel_365(engine: FormulaEngine, formula: str, expected: object) -> None:
    assert value_at(engine, formula) == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=A1:A5*10", [[10], [20], [30], [40], [50]]),
        ("=-A1:A3", [[-1], [-2], [-3]]),
        ("=A1:A3", [[1], [2], [3]]),
        ("={1,2;3,4}*2", [[2, 4], [6, 8]]),
        ("=FILTER(A1:A5,A1:A5>2)", [[3], [4], [5]]),
        ("=LEN(B1:B5)", [[1], [1], [1], [1], [1]]),
        ('=IF(A1:A3>2,"big","small")', [["small"], ["small"], ["big"]]),
        ("=ISNUMBER(A1:B2)", [[True, False], [True, False]]),
        ('=IFERROR(1/(A1:A3-2),"x")', [[-1.0], ["x"], [1.0]]),
        ("=ROUND(A1:A3/3,2)", [[0.33], [0.67], [1]]),
        ("=VLOOKUP({2;4},A1:B5,2,0)", [["x"], ["x"]]),
        ('=COUNTIF(B1:B5,{"x","y"})', [[2, 3]]),
        ("=INDEX(A1:A5,{1;3})", [[1], [3]]),
        ("=INDEX(A1:B5,2,0)", [[2, "x"]]),
        ("={1,2,3}+{10;20}", [[11, 12, 13], [21, 22, 23]]),
    ],
)
def test_operators_and_scalar_functions_broadcast(
    engine: FormulaEngine,
    formula: str,
    expected: list[list[object]],
) -> None:
    assert spill_at(engine, formula) == expected


def test_mismatched_array_sizes_pad_with_na(engine: FormulaEngine) -> None:
    assert spill_at(engine, "={1,2,3}+{1,2}") == [[2, 4, NA_ERROR.literal]]


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ('="10"=10', False),
        ("=TRUE>1", True),
        ('="a"<1', False),
        ('="b">"A"', True),
        ("=1/3&\"\"", "0.333333333333333"),
        ("=0.1+0.2&\"\"", "0.3"),
        ('="$1,000"+1', 1001),
        ('="50%"*2', 1.0),
        ('="(5)"+0', -5),
        ('="1 1/2"+0', 1.5),
        ("=(-8)^(1/3)", -2.0),
        ("=10^1000", "#NUM!"),
        ("=0^0", "#NUM!"),
        ('="abc"+1', "#VALUE!"),
    ],
)
def test_coercion_and_comparison_match_excel(formula: str, expected: object) -> None:
    result = FormulaEvaluator(Workbook()).evaluate(formula)
    assert getattr(result, "literal", result) == expected


def test_spill_operator_and_anchorarray_follow_the_spill(engine: FormulaEngine) -> None:
    engine.set_cell("Sheet1", 10, 4, "=SEQUENCE(4)")

    assert value_at(engine, "=SUM(E11#)") == 10
    assert value_at(engine, "=ROWS(E11#)", column=8) == 4
    assert value_at(engine, "=SUM(ANCHORARRAY(E11))", column=9) == 10
    assert value_at(engine, "=A1#", column=10) == REF_ERROR.literal


def test_at_operator_uses_formula_row(engine: FormulaEngine) -> None:
    assert value_at(engine, "=@A1:A5", row=2) == 3
    assert value_at(engine, "=@A1:A5", row=20) == VALUE_ERROR.literal


def test_three_dimensional_references_span_sheets() -> None:
    workbook = Workbook()
    for name, value in (("Jan", 1), ("Feb", 2), ("Mar", 3)):
        workbook.add_sheet(name).set_cell(1, 1, value)
    engine = FormulaEngine(workbook)

    engine.set_cell("Sheet1", 0, 0, "=SUM(Jan:Mar!B2)")
    engine.set_cell("Sheet1", 0, 1, "=SUM('Jan:Feb'!B2:C3)")
    assert workbook.active_sheet.get_cell(0, 0).cached_value == 6
    assert workbook.active_sheet.get_cell(0, 1).cached_value == 3

    engine.set_cell("Feb", 1, 1, 20)
    assert workbook.active_sheet.get_cell(0, 0).cached_value == 24


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=LET(x,2,y,x*3,x+y)", 8),
        ("=LAMBDA(x,x*x)(7)", 49),
        ("=REDUCE(0,{1,2,3,4,5},LAMBDA(a,v,a+v))", 15),
        ("=LET(f,LAMBDA(a,[b],IF(ISOMITTED(b),a,a+b)),f(1)+f(1,5))", 7),
        ("=LAMBDA(a,b,ISOMITTED(b))(1,)", True),
        ("=LET(sq,LAMBDA(n,n^2),SUM(MAP({1,2,3},sq)))", 14),
        ("=LAMBDA(x,x)", "#CALC!"),
        ("=LET(1,2,3)", "#NAME?"),
    ],
)
def test_let_and_lambda(formula: str, expected: object) -> None:
    result = FormulaEvaluator(Workbook()).evaluate(formula)
    assert getattr(result, "literal", result) == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=MAP({1,2,3},LAMBDA(v,v*10))", ((10, 20, 30),)),
        ("=SCAN(0,{1;2;3},LAMBDA(a,v,a+v))", ((1,), (3,), (6,))),
        ("=BYROW({1,2;3,4},LAMBDA(r,SUM(r)))", ((3,), (7,))),
        ("=BYCOL({1,2;3,4},LAMBDA(c,SUM(c)))", ((4, 6),)),
        ("=MAKEARRAY(2,3,LAMBDA(r,c,r*c))", ((1, 2, 3), (2, 4, 6))),
    ],
)
def test_lambda_helpers_build_arrays(formula: str, expected: object) -> None:
    assert FormulaEvaluator(Workbook()).evaluate(formula) == expected


def test_named_constants_formulas_and_lambdas() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 100)
    workbook.define_name("TaxRate", "=0.07")
    workbook.define_name("Gross", "=Sheet1!$A$1*(1+TaxRate)")
    workbook.define_name("Double", "=LAMBDA(n,n*2)", comment="Doubles a number")
    engine = FormulaEngine(workbook)

    engine.set_cell("Sheet1", 1, 0, "=Gross")
    engine.set_cell("Sheet1", 2, 0, "=Double(21)")
    assert workbook.active_sheet.get_cell(1, 0).cached_value == pytest.approx(107)
    assert workbook.active_sheet.get_cell(2, 0).cached_value == 42
    assert workbook.get_name("TaxRate").refers_to == "=0.07"
    assert workbook.get_name("Double").comment == "Doubles a number"

    engine.set_cell("Sheet1", 0, 0, 200)
    assert workbook.active_sheet.get_cell(1, 0).cached_value == pytest.approx(214)


def test_inserting_rows_moves_defined_names() -> None:
    from duddysheet.core.operations import edit_structure

    workbook = Workbook()
    workbook.define_name("Rate", "Sheet1!$B$5")
    workbook.define_name("Total", "=SUM(Sheet1!$A$1:$A$10)")

    edit_structure(workbook, "Sheet1", axis="row", index=0, count=2, delete=False)

    assert workbook.get_name("Rate").reference.to_a1() == "Sheet1!$B$7"
    assert workbook.get_name("Total").formula == "=SUM(Sheet1!$A$3:$A$12)"


@pytest.mark.parametrize(
    "formula",
    [
        "=IF(A1,,1)",
        "=SUM(A1#)",
        "=@A1:A3",
        "=LAMBDA(x,x+1)(2)",
        "=SUM(Jan:Mar!B2)",
        "=SUM(A1:INDEX(B:B,3))",
    ],
)
def test_new_syntax_round_trips_through_formula_text(formula: str) -> None:
    rendered = formula_to_text(parse_formula(formula))

    assert parse_formula(rendered) == parse_formula(formula)
    assert translate_formula_copy(formula, rows=1)


def test_unknown_names_and_missing_sheets_are_errors() -> None:
    evaluator = FormulaEvaluator(Workbook())

    assert evaluator.evaluate("=NoSuchName") == NAME_ERROR
    assert evaluator.evaluate("=NOSUCHFUNCTION(1)") == NAME_ERROR
    assert evaluator.evaluate("=SUM(Nope:Nada!A1)") == REF_ERROR
    assert evaluator.evaluate("=SEQUENCE(0)") == CALC_ERROR


def test_whole_column_references_are_fast() -> None:
    workbook = Workbook()
    for row in range(2000):
        workbook.active_sheet.set_cell(row, 0, row)
        workbook.active_sheet.set_cell(row, 1, row % 7)
    evaluator = FormulaEvaluator(workbook)

    started = perf_counter()
    assert evaluator.evaluate("=SUM(A:A)") == sum(range(2000))
    assert evaluator.evaluate("=SUMIF(B:B,3,A:A)") == sum(r for r in range(2000) if r % 7 == 3)
    assert evaluator.evaluate("=COUNTBLANK(C:C)") == 1_048_576
    assert evaluator.evaluate('=COUNTIF(C:C,"")') == 1_048_576
    assert perf_counter() - started < 1.0


def test_cycle_reached_through_a_second_precedent_is_reported() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 3, 1)
    engine.set_cell("Sheet1", 0, 1, "=D1")
    engine.set_cell("Sheet1", 0, 0, "=B1+C1")
    engine.set_cell("Sheet1", 0, 2, "=A1+D1")

    result = engine.set_cell("Sheet1", 0, 3, 2)

    assert {address.to_a1() for address in result.circular} == {"Sheet1!A1", "Sheet1!C1"}
    assert workbook.active_sheet.get_cell(0, 1).cached_value == 2
