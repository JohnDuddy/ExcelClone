"""AST evaluation, type coercion, references, and date serials."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from duddysheet.core.errors import (
    DIV_ZERO_ERROR,
    NAME_ERROR,
    NULL_ERROR,
    NUM_ERROR,
    REF_ERROR,
    VALUE_ERROR,
    SpreadsheetError,
    error_from_literal,
    is_error,
)
from duddysheet.core.functions import FUNCTION_REGISTRY, FunctionSpec
from duddysheet.core.parser import (
    ArrayNode,
    BinaryNode,
    ErrorNode,
    FunctionNode,
    LiteralNode,
    NameNode,
    Node,
    PercentNode,
    ReferenceNode,
    ReferenceOperatorNode,
    UnaryNode,
    parse_formula,
)
from duddysheet.core.refs import CellReference, RangeReference, Reference
from duddysheet.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    """One or more reference areas retained lazily during evaluation."""

    areas: tuple[Reference, ...]


@dataclass(slots=True)
class EvaluationContext:
    """Workbook location and evaluator access supplied to functions."""

    evaluator: FormulaEvaluator
    sheet_name: str
    origin: tuple[int, int]

    def evaluate(self, node: Node) -> Any:
        """Evaluate an AST node in the current formula context."""
        return self.evaluator._evaluate_node(node, self)

    def scalar(self, value: Any) -> Any:
        """Resolve a reference to a scalar for scalar function arguments."""
        return self.evaluator._scalarize(value, self)

    def values(self, value: Any) -> list[Any]:
        """Flatten a reference or array into formula values."""
        return list(self.evaluator.iter_values(value, self))


class FormulaEvaluator:
    """Evaluate formulas against one workbook without mutating it."""

    def __init__(
        self,
        workbook: Workbook,
        *,
        function_registry: dict[str, FunctionSpec] | None = None,
    ) -> None:
        self.workbook = workbook
        self.function_registry = (
            FUNCTION_REGISTRY if function_registry is None else function_registry
        )

    def evaluate(
        self,
        formula: str | Node,
        *,
        sheet_name: str | None = None,
        origin: tuple[int, int] = (0, 0),
    ) -> Any:
        """Evaluate a formula or parsed AST and return a scalar, array, or error."""
        node = parse_formula(formula) if isinstance(formula, str) else formula
        selected_sheet = (
            self.workbook.active_sheet.name if sheet_name is None else sheet_name
        )
        try:
            self.workbook.get_sheet(selected_sheet)
        except KeyError:
            return REF_ERROR
        context = EvaluationContext(self, selected_sheet, origin)
        return self._scalarize(self._evaluate_node(node, context), context)

    def _evaluate_node(self, node: Node, context: EvaluationContext) -> Any:
        if isinstance(node, LiteralNode):
            return node.value
        if isinstance(node, ErrorNode):
            return node.error
        if isinstance(node, ReferenceNode):
            return ReferenceValue((node.reference,))
        if isinstance(node, NameNode):
            return self._evaluate_name(node, context)
        if isinstance(node, UnaryNode):
            return self._evaluate_unary(node, context)
        if isinstance(node, PercentNode):
            value = self._coerce_number(context.evaluate(node.operand), context)
            return value if is_error(value) else value / 100
        if isinstance(node, BinaryNode):
            return self._evaluate_binary(node, context)
        if isinstance(node, ReferenceOperatorNode):
            return self._evaluate_reference_operator(node, context)
        if isinstance(node, FunctionNode):
            return self._evaluate_function(node, context)
        if isinstance(node, ArrayNode):
            return tuple(
                tuple(self._scalarize(context.evaluate(item), context) for item in row)
                for row in node.rows
            )
        return VALUE_ERROR

    def _evaluate_name(self, node: NameNode, context: EvaluationContext) -> Any:
        scope = node.sheet if node.sheet is not None else context.sheet_name
        try:
            defined_name = self.workbook.get_name(node.name, scope=scope)
        except (KeyError, ValueError):
            return NAME_ERROR
        return ReferenceValue((defined_name.reference,))

    def _evaluate_unary(self, node: UnaryNode, context: EvaluationContext) -> Any:
        value = self._coerce_number(context.evaluate(node.operand), context)
        if is_error(value):
            return value
        return value if node.operator == "+" else -value

    def _evaluate_binary(self, node: BinaryNode, context: EvaluationContext) -> Any:
        left = self._scalarize(context.evaluate(node.left), context)
        if is_error(left):
            return left
        right = self._scalarize(context.evaluate(node.right), context)
        if is_error(right):
            return right

        if node.operator == "&":
            return _coerce_text(left) + _coerce_text(right)
        if node.operator in {"=", "<>", "<", ">", "<=", ">="}:
            return _compare(left, right, node.operator)

        left_number = self._coerce_number(left, context)
        if is_error(left_number):
            return left_number
        right_number = self._coerce_number(right, context)
        if is_error(right_number):
            return right_number
        try:
            if node.operator == "+":
                return left_number + right_number
            if node.operator == "-":
                return left_number - right_number
            if node.operator == "*":
                return left_number * right_number
            if node.operator == "/":
                return DIV_ZERO_ERROR if right_number == 0 else left_number / right_number
            if node.operator == "^":
                result = left_number**right_number
                if isinstance(result, complex) or not math.isfinite(float(result)):
                    return NUM_ERROR
                return result
        except (OverflowError, ValueError):
            return NUM_ERROR
        except ZeroDivisionError:
            return DIV_ZERO_ERROR
        return VALUE_ERROR

    def _evaluate_reference_operator(
        self,
        node: ReferenceOperatorNode,
        context: EvaluationContext,
    ) -> Any:
        left = context.evaluate(node.left)
        right = context.evaluate(node.right)
        if is_error(left):
            return left
        if is_error(right):
            return right
        if not isinstance(left, ReferenceValue) or not isinstance(right, ReferenceValue):
            return VALUE_ERROR
        if node.operator == ",":
            return ReferenceValue(left.areas + right.areas)

        intersections: list[Reference] = []
        for left_area in left.areas:
            for right_area in right.areas:
                overlap = _intersect_areas(
                    left_area,
                    right_area,
                    default_sheet=context.sheet_name,
                )
                if overlap is not None:
                    intersections.append(overlap)
        return ReferenceValue(tuple(intersections)) if intersections else NULL_ERROR

    def _evaluate_function(self, node: FunctionNode, context: EvaluationContext) -> Any:
        specification = self.function_registry.get(node.name.upper())
        if specification is None:
            return NAME_ERROR
        argument_count = len(node.arguments)
        if not specification.min_args <= argument_count <= specification.max_args:
            return VALUE_ERROR
        if specification.lazy:
            return specification.implementation(context, *node.arguments)
        arguments = [context.evaluate(argument) for argument in node.arguments]
        error = next((value for value in arguments if is_error(value)), None)
        if error is not None:
            return error
        try:
            return specification.implementation(context, *arguments)
        except (ArithmeticError, TypeError, ValueError):
            return VALUE_ERROR

    def _scalarize(self, value: Any, context: EvaluationContext) -> Any:
        if not isinstance(value, ReferenceValue):
            return value
        if not value.areas:
            return NULL_ERROR
        reference = value.areas[0]
        cell_reference = _implicit_intersection(reference, context.origin)
        return self._read_cell(cell_reference, context)

    def _read_cell(
        self,
        reference: CellReference,
        context: EvaluationContext,
    ) -> Any:
        sheet_name = reference.sheet or context.sheet_name
        try:
            sheet = self.workbook.get_sheet(sheet_name)
        except KeyError:
            return REF_ERROR
        cell = sheet.get_cell(reference.row, reference.column)
        if cell.error is not None:
            try:
                return error_from_literal(cell.error)
            except ValueError:
                return VALUE_ERROR
        return cell.cached_value

    def _coerce_number(self, value: Any, context: EvaluationContext) -> Any:
        value = self._scalarize(value, context)
        if is_error(value):
            return value
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, (date, datetime)):
            return date_to_serial(value)
        if isinstance(value, str):
            try:
                normalized = value.strip()
                return float(normalized) if any(c in normalized for c in ".eE") else int(normalized)
            except ValueError:
                return VALUE_ERROR
        return VALUE_ERROR

    def iter_values(
        self,
        value: Any,
        context: EvaluationContext,
    ):
        """Yield scalar values from a reference, array, or scalar."""
        if isinstance(value, ReferenceValue):
            seen: set[tuple[str, int, int]] = set()
            for area in value.areas:
                for reference in _iter_area(area):
                    sheet_name = reference.sheet or context.sheet_name
                    key = (sheet_name.casefold(), reference.row, reference.column)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield self._read_cell(reference, context)
            return
        if isinstance(value, tuple):
            for row in value:
                if isinstance(row, tuple):
                    yield from row
                else:
                    yield row
            return
        yield value


def date_to_serial(value: date | datetime) -> float:
    """Convert a date/time to an Excel 1900-system serial."""
    if isinstance(value, datetime):
        day = value.date()
        fraction = (
            value.hour * 3600
            + value.minute * 60
            + value.second
            + value.microsecond / 1_000_000
        ) / 86_400
    else:
        day = value
        fraction = 0.0
    epoch = date(1899, 12, 31)
    serial = (day - epoch).days
    if day >= date(1900, 3, 1):
        serial += 1
    return serial + fraction


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _compare(left: Any, right: Any, operator: str) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        normalized_left: Any = left.casefold()
        normalized_right: Any = right.casefold()
    elif isinstance(left, (int, float, bool)) and isinstance(
        right,
        (int, float, bool),
    ):
        normalized_left = float(left)
        normalized_right = float(right)
    else:
        normalized_left = _coerce_text(left).casefold()
        normalized_right = _coerce_text(right).casefold()
    if operator == "=":
        return normalized_left == normalized_right
    if operator == "<>":
        return normalized_left != normalized_right
    if operator == "<":
        return normalized_left < normalized_right
    if operator == ">":
        return normalized_left > normalized_right
    if operator == "<=":
        return normalized_left <= normalized_right
    return normalized_left >= normalized_right


def _iter_area(reference: Reference):
    if isinstance(reference, CellReference):
        yield reference
    else:
        yield from reference


def _implicit_intersection(
    reference: Reference,
    origin: tuple[int, int],
) -> CellReference:
    if isinstance(reference, CellReference):
        return reference
    origin_row, origin_column = origin
    if reference.min_row <= origin_row <= reference.max_row:
        return CellReference(origin_row, reference.min_column, sheet=reference.sheet)
    if reference.min_column <= origin_column <= reference.max_column:
        return CellReference(reference.min_row, origin_column, sheet=reference.sheet)
    return CellReference(reference.min_row, reference.min_column, sheet=reference.sheet)


def _intersect_areas(
    left: Reference,
    right: Reference,
    *,
    default_sheet: str,
) -> Reference | None:
    left_range = _as_range(left)
    right_range = _as_range(right)
    left_sheet = left_range.sheet or default_sheet
    right_sheet = right_range.sheet or default_sheet
    if left_sheet.casefold() != right_sheet.casefold():
        return None
    min_row = max(left_range.min_row, right_range.min_row)
    max_row = min(left_range.max_row, right_range.max_row)
    min_column = max(left_range.min_column, right_range.min_column)
    max_column = min(left_range.max_column, right_range.max_column)
    if min_row > max_row or min_column > max_column:
        return None
    if min_row == max_row and min_column == max_column:
        return CellReference(min_row, min_column, sheet=left_sheet)
    return RangeReference(
        CellReference(min_row, min_column, sheet=left_sheet),
        CellReference(max_row, max_column, sheet=left_sheet),
    )


def _as_range(reference: Reference) -> RangeReference:
    if isinstance(reference, RangeReference):
        return reference
    return RangeReference(reference, reference)
