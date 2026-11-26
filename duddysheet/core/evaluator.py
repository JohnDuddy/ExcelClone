"""AST evaluation with Excel 365 dynamic-array semantics.

Operators broadcast element-wise over arrays and multi-cell ranges, scalar
function parameters lift over arrays, a bare range spills, ``@`` performs
implicit intersection, ``#`` names a spilled range, and LET/LAMBDA bind local
names. Values follow the coercion rules in :mod:`duddysheet.core.values`.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from duddysheet.core.errors import (
    CALC_ERROR,
    NA_ERROR,
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
    CallNode,
    ErrorNode,
    FunctionNode,
    ImplicitIntersectionNode,
    LiteralNode,
    MissingNode,
    NameNode,
    Node,
    ParenNode,
    PercentNode,
    ReferenceNode,
    ReferenceOperatorNode,
    SpillNode,
    StructuredReferenceNode,
    ThreeDReferenceNode,
    UnaryNode,
    expand_sheet_span,
    parse_formula,
    with_sheet,
)
from duddysheet.core.refs import CellReference, RangeReference, Reference
from duddysheet.core.values import arithmetic, date_serial, to_number
from duddysheet.core.workbook import Workbook

#: Ranges with more cells than this are clipped to the workbook's populated
#: extent, so whole-column references cost what the data costs.
LARGE_RANGE_CELLS = 65_536
#: Legacy functions where an empty argument means blank/FALSE, not the default.
_MISSING_AS_BLANK = frozenset({"VLOOKUP", "HLOOKUP", "MATCH", "LOOKUP"})


class _Omitted:
    """Sentinel for an omitted argument or unsupplied LAMBDA parameter."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "OMITTED"

    def __bool__(self) -> bool:
        return False


OMITTED = _Omitted()


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    """One or more reference areas retained lazily during evaluation."""

    areas: tuple[Reference, ...]


@dataclass(frozen=True, slots=True)
class LambdaValue:
    """A LAMBDA closure: parameter names, body, and captured bindings."""

    parameters: tuple[str, ...]
    body: Node
    bindings: tuple[tuple[str, Any], ...] = ()


@dataclass(slots=True)
class EvaluationContext:
    """Workbook location, local bindings, and evaluator access for functions."""

    evaluator: FormulaEvaluator
    sheet_name: str
    origin: tuple[int, int]
    bindings: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, node: Node) -> Any:
        """Evaluate an AST node in the current formula context."""
        return self.evaluator._evaluate_node(node, self)

    def scalar(self, value: Any) -> Any:
        """Resolve a reference or array to one scalar."""
        return self.evaluator._scalarize(value, self)

    def values(self, value: Any) -> list[Any]:
        """Flatten a reference or array into formula values."""
        return list(self.evaluator.iter_values(value, self))

    def matrix(self, value: Any) -> list[list[Any]]:
        """Return a value as a rectangular list of rows."""
        return self.evaluator.to_matrix(value, self)

    def is_array(self, value: Any) -> bool:
        """Return whether a value is an array or a multi-cell reference."""
        return self.evaluator.is_array(value)

    def bind(self, bindings: dict[str, Any]) -> EvaluationContext:
        """Return a child context with additional local names."""
        merged = dict(self.bindings)
        merged.update({name.casefold(): value for name, value in bindings.items()})
        return EvaluationContext(self.evaluator, self.sheet_name, self.origin, merged)

    def call(self, function: Any, *arguments: Any) -> Any:
        """Invoke a LAMBDA value with already-evaluated arguments."""
        return self.evaluator.apply_lambda(function, list(arguments), self)

    def map_arrays(self, function: Callable[..., Any], *values: Any) -> Any:
        """Broadcast ``function`` element-wise over arrays and scalars."""
        return self.evaluator.broadcast(function, values, self)

    def finalize(self, value: Any) -> Any:
        """Convert a raw result to a cell value or array of cell values."""
        return self.evaluator.finalize(value, self)

    def cell_count(self, value: Any) -> int:
        """Return how many cells or elements a value spans, before clipping."""
        if isinstance(value, ReferenceValue):
            return sum(
                1 if isinstance(area, CellReference) else len(area)
                for area in value.areas
            )
        if isinstance(value, tuple):
            return sum(len(row) if isinstance(row, tuple) else 1 for row in value)
        return 1


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
        self._name_stack: set[tuple[str | None, str]] = set()
        self._name_asts: dict[str, Node] = {}
        self._signatures: dict[str, tuple[inspect.Parameter, ...]] = {}

    # ------------------------------------------------------------------ entry
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
        try:
            raw = self._evaluate_node(node, context)
        except RecursionError:
            return NUM_ERROR
        return self.finalize(raw, context)

    def finalize(self, value: Any, context: EvaluationContext) -> Any:
        """Convert an evaluation result to what a cell displays.

        A single-cell reference reads that cell, a multi-cell reference becomes
        an array that spills, blanks become zero, and functions become #CALC!.
        """
        value_type = type(value)
        if value_type is int or value_type is float or value_type is str:
            return value
        if isinstance(value, ReferenceValue):
            if not value.areas:
                return NULL_ERROR
            if len(value.areas) > 1:
                return VALUE_ERROR
            area = value.areas[0]
            if isinstance(area, CellReference) or len(area) == 1:
                return _blank_to_zero(self._scalarize(value, context))
            value = self._matrix_tuple(self.to_matrix(value, context))
        if isinstance(value, tuple):
            rows = self.to_matrix(value, context)
            if not rows or not rows[0]:
                return CALC_ERROR
            return tuple(
                tuple(_cell_result(item) for item in row) for row in rows
            )
        return _cell_result(value)

    # ------------------------------------------------------------ dispatching
    def _evaluate_node(self, node: Node, context: EvaluationContext) -> Any:
        if isinstance(node, LiteralNode):
            return node.value
        if isinstance(node, ReferenceNode):
            return ReferenceValue((node.reference,))
        if isinstance(node, BinaryNode):
            return self._evaluate_binary(node, context)
        if isinstance(node, FunctionNode):
            return self._evaluate_function(node, context)
        if isinstance(node, ParenNode):
            return self._evaluate_node(node.inner, context)
        if isinstance(node, NameNode):
            return self._evaluate_name(node, context)
        if isinstance(node, ErrorNode):
            return node.error
        if isinstance(node, UnaryNode):
            return self._evaluate_unary(node, context)
        if isinstance(node, PercentNode):
            return self._map_unary(
                context.evaluate(node.operand),
                lambda value: arithmetic("/", value, 100),
                context,
            )
        if isinstance(node, ReferenceOperatorNode):
            return self._evaluate_reference_operator(node, context)
        if isinstance(node, ArrayNode):
            return tuple(
                tuple(self._scalarize(context.evaluate(item), context) for item in row)
                for row in node.rows
            )
        if isinstance(node, MissingNode):
            return None
        if isinstance(node, CallNode):
            callee = context.evaluate(node.callee)
            if is_error(callee):
                return callee
            if not isinstance(callee, LambdaValue):
                return VALUE_ERROR
            return self._invoke_lambda(callee, node.arguments, context)
        if isinstance(node, ImplicitIntersectionNode):
            return self._implicit_intersection(context.evaluate(node.operand), context)
        if isinstance(node, SpillNode):
            return self._spill_range(context.evaluate(node.operand), context)
        if isinstance(node, StructuredReferenceNode):
            from duddysheet.core.tables import resolve_structured

            reference = resolve_structured(
                self.workbook,
                node.table,
                node.spec,
                context.sheet_name,
                context.origin,
            )
            return REF_ERROR if reference is None else ReferenceValue((reference,))
        if isinstance(node, ThreeDReferenceNode):
            sheets = expand_sheet_span(
                node.first_sheet,
                node.last_sheet,
                self.workbook.sheet_names,
            )
            if not sheets:
                return REF_ERROR
            return ReferenceValue(
                tuple(with_sheet(node.reference, sheet) for sheet in sheets)
            )
        return VALUE_ERROR

    # ------------------------------------------------------------------ names
    def _evaluate_name(self, node: NameNode, context: EvaluationContext) -> Any:
        if node.sheet is None:
            key = node.name.casefold()
            if key in context.bindings:
                bound = context.bindings[key]
                return None if bound is OMITTED else bound
        scope = node.sheet if node.sheet is not None else context.sheet_name
        try:
            defined_name = self.workbook.get_name(node.name, scope=scope)
        except (KeyError, ValueError):
            table_reference = self._table_name_reference(node)
            return NAME_ERROR if table_reference is None else table_reference
        formula = getattr(defined_name, "formula", None)
        if formula is None:
            return ReferenceValue((defined_name.reference,))
        key = (defined_name.scope, defined_name.name.casefold())
        if key in self._name_stack:
            return NAME_ERROR
        ast = self._name_asts.get(formula)
        if ast is None:
            try:
                ast = parse_formula(formula)
            except ValueError:
                return NAME_ERROR
            self._name_asts[formula] = ast
        self._name_stack.add(key)
        try:
            name_context = EvaluationContext(
                self,
                context.sheet_name,
                context.origin,
            )
            return self._evaluate_node(ast, name_context)
        finally:
            self._name_stack.discard(key)

    def _table_name_reference(self, node: NameNode) -> Any:
        """A bare table name (=ROWS(Table1)) means the table's data rows."""
        if node.sheet is not None or not any(sheet.tables for sheet in self.workbook):
            return None
        from duddysheet.core.tables import StructuredSpec, resolve_structured

        reference = resolve_structured(self.workbook, node.name, StructuredSpec(), "", (0, 0))
        return None if reference is None else ReferenceValue((reference,))

    def _resolve_callable(self, name: str, context: EvaluationContext) -> Any:
        key = name.casefold()
        if key in context.bindings:
            bound = context.bindings[key]
            return bound if isinstance(bound, LambdaValue) else VALUE_ERROR
        value = self._evaluate_name(NameNode(name), context)
        if isinstance(value, LambdaValue):
            return value
        if value == NAME_ERROR:
            return None
        return VALUE_ERROR

    # --------------------------------------------------------------- lambdas
    def _invoke_lambda(
        self,
        function: LambdaValue,
        argument_nodes: tuple[Node, ...],
        context: EvaluationContext,
    ) -> Any:
        values = [
            OMITTED if isinstance(argument, MissingNode) else context.evaluate(argument)
            for argument in argument_nodes
        ]
        return self.apply_lambda(function, values, context)

    def apply_lambda(
        self,
        function: Any,
        arguments: list[Any],
        context: EvaluationContext,
    ) -> Any:
        """Bind arguments to a LAMBDA's parameters and evaluate its body."""
        if not isinstance(function, LambdaValue):
            return function if is_error(function) else VALUE_ERROR
        if len(arguments) > len(function.parameters):
            return VALUE_ERROR
        bindings = dict(function.bindings)
        for index, parameter in enumerate(function.parameters):
            bindings[parameter] = arguments[index] if index < len(arguments) else OMITTED
        child = EvaluationContext(self, context.sheet_name, context.origin, bindings)
        return self._evaluate_node(function.body, child)

    # -------------------------------------------------------------- operators
    def _evaluate_unary(self, node: UnaryNode, context: EvaluationContext) -> Any:
        operator = node.operator
        return self._map_unary(
            context.evaluate(node.operand),
            lambda value: _negate(value) if operator == "-" else value,
            context,
        )

    def _map_unary(
        self,
        value: Any,
        function: Callable[[Any], Any],
        context: EvaluationContext,
    ) -> Any:
        if self.is_array(value):
            return self.broadcast(function, (value,), context)
        return function(self._scalarize(value, context))

    def _evaluate_binary(self, node: BinaryNode, context: EvaluationContext) -> Any:
        left_node = node.left
        right_node = node.right
        # Plain cell operands are read directly: the common A1+1 shape.
        if type(left_node) is ReferenceNode and type(left_node.reference) is CellReference:
            left = self._read_cell(left_node.reference, context)
        else:
            left = self._evaluate_node(left_node, context)
        if type(right_node) is ReferenceNode and type(right_node.reference) is CellReference:
            right = self._read_cell(right_node.reference, context)
        else:
            right = self._evaluate_node(right_node, context)
        operator = node.operator
        left_type = type(left)
        right_type = type(right)
        if (left_type is int or left_type is float) and (
            right_type is int or right_type is float
        ):
            return arithmetic(operator, left, right)
        if self.is_array(left) or self.is_array(right):
            return self.broadcast(
                lambda a, b: arithmetic(operator, a, b),
                (left, right),
                context,
            )
        left = self._scalarize(left, context)
        if is_error(left):
            return left
        right = self._scalarize(right, context)
        return arithmetic(operator, left, right)

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
        if node.operator == ":":
            return self._bounding_reference(left, right, context)

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

    def _bounding_reference(
        self,
        left: ReferenceValue,
        right: ReferenceValue,
        context: EvaluationContext,
    ) -> Any:
        areas = [_as_range(area) for area in left.areas + right.areas]
        if not areas:
            return NULL_ERROR
        sheets = {(area.sheet or context.sheet_name).casefold() for area in areas}
        if len(sheets) != 1:
            return VALUE_ERROR
        sheet = areas[0].sheet
        min_row = min(area.min_row for area in areas)
        max_row = max(area.max_row for area in areas)
        min_column = min(area.min_column for area in areas)
        max_column = max(area.max_column for area in areas)
        start = CellReference(min_row, min_column, sheet=sheet)
        if min_row == max_row and min_column == max_column:
            return ReferenceValue((start,))
        return ReferenceValue(
            (RangeReference(start, CellReference(max_row, max_column, sheet=sheet)),)
        )

    def _implicit_intersection(self, value: Any, context: EvaluationContext) -> Any:
        if isinstance(value, tuple):
            rows = self.to_matrix(value, context)
            return rows[0][0] if rows and rows[0] else CALC_ERROR
        if not isinstance(value, ReferenceValue):
            return value
        if len(value.areas) != 1:
            return VALUE_ERROR
        area = value.areas[0]
        if isinstance(area, CellReference):
            return value
        row, column = context.origin
        single_column = area.min_column == area.max_column
        single_row = area.min_row == area.max_row
        if single_column and single_row:
            target = (area.min_row, area.min_column)
        elif single_column:
            if not area.min_row <= row <= area.max_row:
                return VALUE_ERROR
            target = (row, area.min_column)
        elif single_row:
            if not area.min_column <= column <= area.max_column:
                return VALUE_ERROR
            target = (area.min_row, column)
        else:
            if not area.contains(row, column):
                return VALUE_ERROR
            target = (row, column)
        return ReferenceValue((CellReference(target[0], target[1], sheet=area.sheet),))

    def _spill_range(self, value: Any, context: EvaluationContext) -> Any:
        if is_error(value):
            return value
        if not isinstance(value, ReferenceValue) or len(value.areas) != 1:
            return REF_ERROR
        anchor = value.areas[0]
        if isinstance(anchor, RangeReference):
            if len(anchor) != 1:
                return REF_ERROR
            anchor = anchor.start
        sheet_name = anchor.sheet or context.sheet_name
        try:
            sheet = self.workbook.get_sheet(sheet_name)
        except KeyError:
            return REF_ERROR
        cell = sheet.get_cell(anchor.row, anchor.column)
        if not cell.is_formula:
            return REF_ERROR
        owner = (anchor.row, anchor.column)
        last_column = anchor.column
        while sheet.get_cell(anchor.row, last_column + 1).spill_parent == owner:
            last_column += 1
        last_row = anchor.row
        while sheet.get_cell(last_row + 1, anchor.column).spill_parent == owner:
            last_row += 1
        start = CellReference(anchor.row, anchor.column, sheet=anchor.sheet)
        if last_row == anchor.row and last_column == anchor.column:
            return ReferenceValue((start,))
        end = CellReference(last_row, last_column, sheet=anchor.sheet)
        return ReferenceValue((RangeReference(start, end),))

    # -------------------------------------------------------------- functions
    def _evaluate_function(self, node: FunctionNode, context: EvaluationContext) -> Any:
        specification = self.function_registry.get(node.name.upper())
        if specification is None:
            function = self._resolve_callable(node.name, context)
            if function is None:
                return NAME_ERROR
            if is_error(function):
                return function
            return self._invoke_lambda(function, node.arguments, context)
        argument_count = len(node.arguments)
        if not specification.min_args <= argument_count <= specification.max_args:
            return VALUE_ERROR
        if specification.lazy:
            try:
                return specification.implementation(context, *node.arguments)
            except (ArithmeticError, TypeError, ValueError, IndexError, KeyError):
                return VALUE_ERROR
        arguments = [
            OMITTED if isinstance(argument, MissingNode) else context.evaluate(argument)
            for argument in node.arguments
        ]
        return self.call_function(specification, arguments, context)

    def call_function(
        self,
        specification: FunctionSpec,
        arguments: list[Any],
        context: EvaluationContext,
    ) -> Any:
        """Call a registered function, lifting scalar parameters over arrays."""
        lift = specification.lift
        if lift is not None:
            count = len(arguments)
            lifted = [
                index
                for index, argument in enumerate(arguments)
                if lift(index, count) and self.is_array(argument)
            ]
            if lifted:
                return self._lifted_call(specification, arguments, lifted, context)
        return self._direct_call(specification, arguments, context)

    def _direct_call(
        self,
        specification: FunctionSpec,
        arguments: list[Any],
        context: EvaluationContext,
    ) -> Any:
        if not specification.accepts_errors:
            error = next((value for value in arguments if is_error(value)), None)
            if error is not None:
                return error
        if any(argument is OMITTED for argument in arguments):
            arguments = self._fill_omitted(specification, arguments)
        try:
            return specification.implementation(context, *arguments)
        except (ArithmeticError, TypeError, ValueError, IndexError, KeyError):
            return VALUE_ERROR

    def _fill_omitted(
        self,
        specification: FunctionSpec,
        arguments: list[Any],
    ) -> list[Any]:
        parameters = self._signatures.get(specification.name)
        if parameters is None:
            try:
                parameters = tuple(
                    inspect.signature(specification.implementation).parameters.values()
                )[1:]
            except (TypeError, ValueError):
                parameters = ()
            self._signatures[specification.name] = parameters
        filled: list[Any] = []
        for index, argument in enumerate(arguments):
            if argument is not OMITTED:
                filled.append(argument)
                continue
            default = None
            if (
                specification.name not in _MISSING_AS_BLANK
                and index < len(parameters)
                and parameters[index].kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
                and parameters[index].default is not inspect.Parameter.empty
            ):
                default = parameters[index].default
            filled.append(default)
        return filled

    def _lifted_call(
        self,
        specification: FunctionSpec,
        arguments: list[Any],
        lifted: list[int],
        context: EvaluationContext,
    ) -> Any:
        matrices = {
            index: self._lift_matrix(arguments[index], context) for index in lifted
        }
        rows = max(len(matrix) for matrix in matrices.values())
        columns = max(len(matrix[0]) if matrix else 0 for matrix in matrices.values())
        result: list[tuple[Any, ...]] = []
        for row in range(rows):
            items: list[Any] = []
            for column in range(columns):
                call_arguments = list(arguments)
                for index, matrix in matrices.items():
                    call_arguments[index] = _broadcast_item(matrix, row, column)
                value = self._direct_call(specification, call_arguments, context)
                items.append(self._element(value, context))
            result.append(tuple(items))
        return tuple(result)

    def _lift_matrix(self, value: Any, context: EvaluationContext) -> list[list[Any]]:
        """Matrix for lifting; reference cells stay references for IS* functions."""
        if isinstance(value, ReferenceValue) and len(value.areas) == 1:
            area = value.areas[0]
            if isinstance(area, RangeReference):
                min_row, max_row, min_column, max_column = self._clipped_bounds(area)
                sheet = area.sheet or context.sheet_name
                return [
                    [
                        ReferenceValue((CellReference(row, column, sheet=sheet),))
                        for column in range(min_column, max_column + 1)
                    ]
                    for row in range(min_row, max_row + 1)
                ]
        return self.to_matrix(value, context)

    def _element(self, value: Any, context: EvaluationContext) -> Any:
        """Reduce one lifted or broadcast result to a scalar array element."""
        if isinstance(value, ReferenceValue):
            return self._scalarize(value, context)
        if isinstance(value, tuple):
            rows = self.to_matrix(value, context)
            return rows[0][0] if rows and rows[0] else CALC_ERROR
        if isinstance(value, LambdaValue):
            return CALC_ERROR
        if value is OMITTED:
            return None
        return value

    # ------------------------------------------------------------ broadcasting
    def is_array(self, value: Any) -> bool:
        """Return whether a value is an array or a multi-cell reference."""
        if isinstance(value, tuple):
            return True
        if isinstance(value, ReferenceValue):
            if len(value.areas) != 1:
                return len(value.areas) > 1
            area = value.areas[0]
            return isinstance(area, RangeReference) and len(area) > 1
        return False

    def broadcast(
        self,
        function: Callable[..., Any],
        values: tuple[Any, ...] | list[Any],
        context: EvaluationContext,
    ) -> Any:
        """Apply ``function`` element-wise with Excel's broadcasting rules."""
        matrices = [self.to_matrix(value, context) for value in values]
        rows = max(len(matrix) for matrix in matrices)
        columns = max(len(matrix[0]) if matrix else 0 for matrix in matrices)
        return tuple(
            tuple(
                self._element(
                    function(*(_broadcast_item(matrix, row, column) for matrix in matrices)),
                    context,
                )
                for column in range(columns)
            )
            for row in range(rows)
        )

    def to_matrix(self, value: Any, context: EvaluationContext) -> list[list[Any]]:
        """Return a value as a rectangular list of rows of scalars."""
        if isinstance(value, tuple):
            if not value:
                return [[CALC_ERROR]]
            if all(isinstance(row, tuple) for row in value):
                return [list(row) for row in value]
            return [list(value)]
        if isinstance(value, ReferenceValue):
            if not value.areas:
                return [[NULL_ERROR]]
            if len(value.areas) > 1:
                return [[VALUE_ERROR]]
            area = value.areas[0]
            if isinstance(area, CellReference):
                return [[self._read_cell(area, context)]]
            return self._area_block(area, context)
        if isinstance(value, LambdaValue):
            return [[CALC_ERROR]]
        if value is OMITTED:
            return [[None]]
        return [[value]]

    @staticmethod
    def _matrix_tuple(rows: list[list[Any]]) -> tuple[tuple[Any, ...], ...]:
        return tuple(tuple(row) for row in rows)

    # ------------------------------------------------------------- reference IO
    def workbook_extent(self) -> tuple[int, int]:
        """Return the largest populated (row, column) across every sheet."""
        max_row = max_column = 0
        for sheet in self.workbook:
            row, column = sheet.extent
            max_row = max(max_row, row)
            max_column = max(max_column, column)
        return max_row, max_column

    def _clipped_bounds(self, area: RangeReference) -> tuple[int, int, int, int]:
        min_row, max_row = area.min_row, area.max_row
        min_column, max_column = area.min_column, area.max_column
        if (max_row - min_row + 1) * (max_column - min_column + 1) > LARGE_RANGE_CELLS:
            extent_row, extent_column = self.workbook_extent()
            max_row = max(min_row, min(max_row, extent_row))
            max_column = max(min_column, min(max_column, extent_column))
        return min_row, max_row, min_column, max_column

    def reference_bounds(self, area: RangeReference) -> tuple[int, int, int, int]:
        """Return (min_row, max_row, min_column, max_column) as evaluated."""
        return self._clipped_bounds(area)

    def _area_block(
        self,
        area: RangeReference,
        context: EvaluationContext,
    ) -> list[list[Any]]:
        sheet_name = area.sheet or context.sheet_name
        try:
            sheet = self.workbook.get_sheet(sheet_name)
        except KeyError:
            return [[REF_ERROR]]
        min_row, max_row, min_column, max_column = self._clipped_bounds(area)
        block = sheet.cell_block(min_row, min_column, max_row, max_column)
        return [[_cell_value(cell) for cell in row] for row in block]

    def _scalarize(self, value: Any, context: EvaluationContext) -> Any:
        if isinstance(value, ReferenceValue):
            if not value.areas:
                return NULL_ERROR
            reference = value.areas[0]
            if type(reference) is CellReference:
                return self._read_cell(reference, context)
            cell_reference = _implicit_intersection(reference, context.origin)
            return self._read_cell(cell_reference, context)
        if isinstance(value, tuple):
            rows = self.to_matrix(value, context)
            return rows[0][0] if rows and rows[0] else CALC_ERROR
        if isinstance(value, LambdaValue):
            return CALC_ERROR
        if value is OMITTED:
            return None
        return value

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
        return _cell_value(sheet.get_cell(reference.row, reference.column))

    def _coerce_number(self, value: Any, context: EvaluationContext) -> Any:
        return to_number(self._scalarize(value, context))

    def iter_values(
        self,
        value: Any,
        context: EvaluationContext,
    ) -> Iterator[Any]:
        """Yield scalar values from a reference, array, or scalar."""
        if isinstance(value, ReferenceValue):
            for area in value.areas:
                if isinstance(area, CellReference):
                    yield self._read_cell(area, context)
                    continue
                for row in self._area_block(area, context):
                    yield from row
            return
        if isinstance(value, tuple):
            for row in value:
                if isinstance(row, tuple):
                    yield from row
                else:
                    yield row
            return
        if isinstance(value, LambdaValue):
            yield CALC_ERROR
            return
        if value is OMITTED:
            yield None
            return
        yield value


def date_to_serial(value: date | datetime) -> float:
    """Convert a date/time to an Excel 1900-system serial."""
    return date_serial(value)


def _cell_value(cell: Any) -> Any:
    if cell.error is not None:
        try:
            return error_from_literal(cell.error)
        except ValueError:
            return VALUE_ERROR
    return cell.cached_value


def _blank_to_zero(value: Any) -> Any:
    return 0 if value is None else value


def _cell_result(value: Any) -> Any:
    if value is None or value is OMITTED:
        return 0
    if isinstance(value, LambdaValue):
        return CALC_ERROR
    if isinstance(value, (ReferenceValue, tuple)):
        return VALUE_ERROR
    return value


def _negate(value: Any) -> Any:
    converted = to_number(value)
    return converted if is_error(converted) else -converted


def _broadcast_item(matrix: list[list[Any]], row: int, column: int) -> Any:
    height = len(matrix)
    width = len(matrix[0]) if matrix else 0
    selected_row = 0 if height == 1 else row
    selected_column = 0 if width == 1 else column
    if selected_row >= height or selected_column >= width:
        return NA_ERROR
    return matrix[selected_row][selected_column]


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
