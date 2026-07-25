from __future__ import annotations

from datetime import date, datetime

import pytest

from excelclone.core.errors import (
    CIRC_ERROR,
    DIV_ZERO_ERROR,
    NAME_ERROR,
    NULL_ERROR,
    NUM_ERROR,
    REF_ERROR,
    VALUE_ERROR,
    SpreadsheetError,
    error_from_literal,
)
from excelclone.core.evaluator import FormulaEvaluator, date_to_serial
from excelclone.core.evaluator import ReferenceValue
from excelclone.core.functions import FunctionSpec
from excelclone.core.parser import LiteralNode, Node, ReferenceOperatorNode
from excelclone.core.refs import CellReference
from excelclone.core.cell import Cell
from excelclone.core.workbook import Workbook


@pytest.fixture
def evaluator() -> FormulaEvaluator:
    return FormulaEvaluator(Workbook())


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=1+2", 3),
        ("=10-3-2", 5),
        ("=2*3+4", 10),
        ("=2+3*4", 14),
        ("=(2+3)*4", 20),
        ("=8/4/2", 1),
        ("=2^3", 8),
        ("=2^3^2", 64),
        ("=-2^2", 4),
        ("=2^-2", 0.25),
        ("=50%", 0.5),
        ("=200*10%", 20),
        ("=-50%", -0.5),
        ('="Open"&"Grid"', "OpenGrid"),
        ('="5"+1', 6),
        ("=TRUE+1", 2),
        ("=FALSE*100", 0),
        ("=1=1", True),
        ("=1<>2", True),
        ("=2>1", True),
        ("=2>=2", True),
        ("=1<2", True),
        ("=1<=1", True),
        ('="a"="A"', True),
        ("=1+2&3", "33"),
        ("=1&2+3", "15"),
    ],
)
def test_operator_evaluation(
    evaluator: FormulaEvaluator,
    formula: str,
    expected: object,
) -> None:
    assert evaluator.evaluate(formula) == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=1/0", DIV_ZERO_ERROR),
        ('="abc"+1', VALUE_ERROR),
        ("=SQRT(-1)", NAME_ERROR),
        ("=#REF!", REF_ERROR),
        ("=#NUM!", NUM_ERROR),
        ("=#CIRC!", CIRC_ERROR),
        ("=MissingName+1", NAME_ERROR),
        ("=MissingSheet!A1", REF_ERROR),
        ("=A1:B2 C3:D4", NULL_ERROR),
    ],
)
def test_formula_errors_are_values_and_propagate(
    evaluator: FormulaEvaluator,
    formula: str,
    expected: SpreadsheetError,
) -> None:
    assert evaluator.evaluate(formula) == expected


@pytest.mark.parametrize(
    ("literal", "type_number"),
    [
        ("#NULL!", 1),
        ("#DIV/0!", 2),
        ("#VALUE!", 3),
        ("#REF!", 4),
        ("#NAME?", 5),
        ("#NUM!", 6),
        ("#N/A", 7),
    ],
)
def test_standard_error_literals_have_excel_type_numbers(
    literal: str,
    type_number: int,
) -> None:
    error = error_from_literal(literal)

    assert str(error) == literal
    assert error.type_number == type_number


def test_reference_and_named_range_values_are_resolved() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 10)
    workbook.active_sheet.set_cell(1, 1, 7)
    workbook.define_name("TaxRate", "B2")
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("=A1*TaxRate") == 70


def test_cross_sheet_and_quoted_sheet_references_are_resolved() -> None:
    workbook = Workbook()
    data = workbook.add_sheet("My Data")
    data.set_cell(2, 3, 9)
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("='My Data'!D3+1") == 10


def test_reference_intersection_returns_the_overlapping_cell() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(1, 1, 12)
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("=A1:B2 B2:C3") == 12


def test_array_literals_return_rectangular_values(
    evaluator: FormulaEvaluator,
) -> None:
    assert evaluator.evaluate("={1,2;3,4}") == ((1, 2), (3, 4))


@pytest.mark.parametrize(
    ("value", "serial"),
    [
        (date(1900, 1, 1), 1),
        (date(1900, 2, 28), 59),
        (date(1900, 3, 1), 61),
        (date(2026, 7, 25), 46228),
        (datetime(1900, 1, 1, 12, 0), 1.5),
    ],
)
def test_excel_date_serials_preserve_the_1900_leap_bug(
    value: date | datetime,
    serial: float,
) -> None:
    assert date_to_serial(value) == serial


def _function_spec(
    name: str,
    implementation: object,
    *,
    min_args: int = 0,
    max_args: int = 255,
    lazy: bool = False,
) -> FunctionSpec:
    return FunctionSpec(
        name=name,
        implementation=implementation,
        min_args=min_args,
        max_args=max_args,
        volatile=False,
        argument_spec="",
        description="Test function.",
        lazy=lazy,
    )


def test_registered_function_can_flatten_ranges_arrays_and_unions() -> None:
    workbook = Workbook()
    for row, value in enumerate((1, 2, 3)):
        workbook.active_sheet.set_cell(row, 0, value)

    def total(context: object, value: object) -> object:
        return sum(item for item in context.values(value) if isinstance(item, (int, float)))

    evaluator = FormulaEvaluator(
        workbook,
        function_registry={"TOTAL": _function_spec("TOTAL", total, min_args=1, max_args=1)},
    )

    assert evaluator.evaluate("=TOTAL(A1:A3)") == 6
    assert evaluator.evaluate("=TOTAL({1,2;3,4})") == 10
    assert evaluator.evaluate("=TOTAL((A1:A2,A2:A3))") == 6


def test_registered_function_receives_scalar_reference_helper() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 8)

    def double(context: object, value: object) -> object:
        return context.scalar(value) * 2

    evaluator = FormulaEvaluator(
        workbook,
        function_registry={"DOUBLE": _function_spec("DOUBLE", double, min_args=1, max_args=1)},
    )

    assert evaluator.evaluate("=DOUBLE(A1)") == 16


def test_lazy_function_controls_argument_evaluation() -> None:
    def first(context: object, first_node: object, second_node: object) -> object:
        return context.evaluate(first_node)

    evaluator = FormulaEvaluator(
        Workbook(),
        function_registry={
            "FIRST": _function_spec("FIRST", first, min_args=2, max_args=2, lazy=True)
        },
    )

    assert evaluator.evaluate("=FIRST(7, 1/0)") == 7


def test_function_arity_exceptions_and_error_arguments_become_errors() -> None:
    def explode(context: object, value: object) -> object:
        raise ArithmeticError("failed")

    evaluator = FormulaEvaluator(
        Workbook(),
        function_registry={
            "EXPLODE": _function_spec("EXPLODE", explode, min_args=1, max_args=1)
        },
    )

    assert evaluator.evaluate("=EXPLODE()") == VALUE_ERROR
    assert evaluator.evaluate("=EXPLODE(1,2)") == VALUE_ERROR
    assert evaluator.evaluate("=EXPLODE(#N/A)") == error_from_literal("#N/A")
    assert evaluator.evaluate("=EXPLODE(1)") == VALUE_ERROR


def test_reference_errors_on_either_side_of_intersection_propagate() -> None:
    evaluator = FormulaEvaluator(Workbook())

    assert evaluator.evaluate("=Missing A1") == NAME_ERROR
    assert evaluator.evaluate("=A1 Missing") == NAME_ERROR


def test_evaluator_rejects_unknown_sheet_context_and_unknown_node() -> None:
    evaluator = FormulaEvaluator(Workbook())

    assert evaluator.evaluate("=1", sheet_name="Missing") == REF_ERROR
    assert evaluator.evaluate(Node()) == VALUE_ERROR


def test_malformed_cached_error_is_exposed_as_value_error() -> None:
    workbook = Workbook()
    workbook.active_sheet.put_cell(0, 0, Cell(raw_input="bad", error="#BOGUS!"))

    assert FormulaEvaluator(workbook).evaluate("=A1") == VALUE_ERROR


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=(-1)^0.5", NUM_ERROR),
        ("=10^1000", NUM_ERROR),
        ("=0^-1", DIV_ZERO_ERROR),
        ("=#N/A%", error_from_literal("#N/A")),
        ("=1+#N/A", error_from_literal("#N/A")),
        ("=#REF!+1", REF_ERROR),
        ('="x"<1', False),
    ],
)
def test_evaluator_numeric_and_error_edge_cases(
    evaluator: FormulaEvaluator,
    formula: str,
    expected: object,
) -> None:
    assert evaluator.evaluate(formula) == expected


def test_cell_dates_and_unsupported_objects_follow_number_coercion() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, date(1900, 3, 1))
    workbook.active_sheet.set_cell(0, 1, object())
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("=A1+0") == 61
    assert evaluator.evaluate("=B1+1") == VALUE_ERROR


def test_text_coercion_handles_blank_boolean_and_integral_float() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, None)
    workbook.active_sheet.set_cell(0, 1, True)
    workbook.active_sheet.set_cell(0, 2, 3.0)
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate('=A1&"x"') == "x"
    assert evaluator.evaluate('=B1&"x"') == "TRUEx"
    assert evaluator.evaluate('=C1&"x"') == "3x"


def test_implicit_intersection_uses_formula_row_then_column_then_first_cell() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(1, 0, 20)
    workbook.active_sheet.set_cell(0, 1, 30)
    workbook.active_sheet.set_cell(0, 0, 10)
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("=A1:A3", origin=(1, 5)) == 20
    assert evaluator.evaluate("=A1:C1", origin=(5, 1)) == 30
    assert evaluator.evaluate("=A1:B2", origin=(5, 5)) == 10


def test_sheet_scoped_name_can_be_qualified_explicitly() -> None:
    workbook = Workbook()
    data = workbook.add_sheet("Data")
    data.set_cell(0, 0, 11)
    workbook.define_name("LocalValue", "A1", scope="Data")
    evaluator = FormulaEvaluator(workbook)

    assert evaluator.evaluate("=Data!LocalValue") == 11


def test_empty_reference_and_non_reference_operator_are_safe_errors() -> None:
    workbook = Workbook()
    evaluator = FormulaEvaluator(workbook)
    empty_spec = _function_spec(
        "EMPTYREF",
        lambda context: ReferenceValue(()),
        max_args=0,
    )
    evaluator.function_registry = {"EMPTYREF": empty_spec}

    assert evaluator.evaluate("=EMPTYREF()") == NULL_ERROR
    invalid = ReferenceOperatorNode(" ", LiteralNode(1), LiteralNode(2))
    assert evaluator.evaluate(invalid) == VALUE_ERROR
