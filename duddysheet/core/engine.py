"""Incremental formula parsing, dependency indexing, and recalculation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Any

from duddysheet.core.cell import EMPTY_CELL, Cell, CellFormat
from duddysheet.core.depgraph import CellAddress, DependencyGraph
from duddysheet.core.errors import CIRC_ERROR, SPILL_ERROR, VALUE_ERROR, SpreadsheetError
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.functions import FUNCTION_REGISTRY
from duddysheet.core.parser import (
    Node,
    collect_function_names,
    collect_references,
    parse_formula,
)
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference, Reference
from duddysheet.core.workbook import Workbook

_RANGE_EDGE_LIMIT = 100_000


class SpillCellReadOnlyError(ValueError):
    """Raised when editing a cell owned by a dynamic-array formula."""


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    """Observable outcome of one recalculation pass."""

    recalculated: tuple[CellAddress, ...]
    circular: tuple[CellAddress, ...]

    @property
    def first_circular(self) -> CellAddress | None:
        """Return the first deterministic circular-reference address."""
        return self.circular[0] if self.circular else None


class FormulaEngine:
    """The mutation and recalculation interface for a workbook."""

    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook
        self.graph = DependencyGraph()
        self.evaluator = FormulaEvaluator(workbook)
        # Data tables (TABLE) evaluate what-if variants through the engine.
        self.evaluator.engine = self
        self.calc_generation = 0
        self._asts: dict[CellAddress, Node] = {}
        self._range_precedents: dict[CellAddress, tuple[RangeReference, ...]] = {}
        self._volatile: set[CellAddress] = set()
        self._spill_cells: dict[CellAddress, set[CellAddress]] = {}
        self._spill_owners: dict[CellAddress, CellAddress] = {}
        self._spill_blockers: dict[CellAddress, set[CellAddress]] = {}
        #: Formulas awaiting calculation while the workbook is in manual mode.
        self.pending: set[CellAddress] = set()
        self._index_existing_formulas()

    def set_cell(
        self,
        sheet_name: str,
        row: int,
        column: int,
        raw_input: Any,
        *,
        cell_format: CellFormat | None = None,
    ) -> RecalculationResult:
        """Set a cell atomically and recalculate only affected formulas."""
        sheet = self.workbook.get_sheet(sheet_name)
        address = CellAddress(sheet.name, row, column)
        if address in self._spill_owners:
            owner = self._spill_owners[address]
            raise SpillCellReadOnlyError(
                f"{address.to_a1()} is owned by spill formula {owner.to_a1()}"
            )
        ast = (
            parse_formula(raw_input)
            if isinstance(raw_input, str) and raw_input.startswith("=")
            else None
        )

        changed = {address}
        changed.update(self._clear_spill(address))
        previous = sheet.get_cell(row, column)
        selected_format = (
            sheet.effective_format(row, column) if cell_format is None else cell_format
        )
        sheet.set_cell(
            row,
            column,
            raw_input,
            cell_format=selected_format,
        )

        if ast is None:
            self._asts.pop(address, None)
            self._range_precedents.pop(address, None)
            self._volatile.discard(address)
            self.graph.set_precedents(address, set())
        else:
            self._asts[address] = ast
            self._install_dependencies(address, ast)

        affected = self._affected_formulas(changed | self._volatile)
        if self.workbook.calculation_mode == "automatic_except_tables":
            deferred = {item for item in affected if self._is_table_formula(item) and item != address}
            self.pending.update(deferred)
            affected -= deferred
        if self.workbook.calculation_mode == "manual":
            # Excel calculates only the entered formula; dependents wait for F9.
            self.pending.update(affected)
            entered = {address} & self._asts.keys()
            self.pending.difference_update(entered)
            return self._calculate_nodes(entered)
        return self._calculate_nodes(affected)

    def recalculate(self, *, sheet_name: str | None = None) -> RecalculationResult:
        """Recalculate every formula, or formulas on one selected sheet."""
        if sheet_name is None:
            selected = set(self._asts)
            self.pending.clear()
        else:
            canonical = self.workbook.get_sheet(sheet_name).name.casefold()
            selected = {
                address
                for address in self._asts
                if address.sheet.casefold() == canonical
            }
        return self._calculate_nodes(selected)

    def rebuild_index(self) -> RecalculationResult:
        """Rebuild dependency state after structural workbook changes."""
        for sheet in self.workbook:
            spill_coordinates = [
                coordinate
                for coordinate, cell in sheet.iter_populated()
                if cell.is_spill
            ]
            for row, column in spill_coordinates:
                sheet.clear_cell(row, column)
        self.graph = DependencyGraph()
        self._asts.clear()
        self._range_precedents.clear()
        self._volatile.clear()
        self._spill_cells.clear()
        self._spill_owners.clear()
        self._spill_blockers.clear()
        self._index_existing_formulas()
        return self.recalculate()

    def _index_existing_formulas(self) -> None:
        for sheet in self.workbook:
            for (row, column), cell in sheet.iter_populated():
                if not cell.is_formula:
                    continue
                address = CellAddress(sheet.name, row, column)
                ast = parse_formula(cell.raw_input)
                self._asts[address] = ast
                self._install_dependencies(address, ast)

    def _install_dependencies(self, address: CellAddress, ast: Node) -> None:
        precedents: set[CellAddress] = set()
        ranges: list[RangeReference] = []
        for resolved in self._formula_references(ast, address.sheet, origin=(address.row, address.column)):
            if isinstance(resolved, CellReference):
                precedents.add(self._address_from_reference(resolved, address.sheet))
                continue

            normalized_range = self._normalize_range(resolved, address.sheet)
            ranges.append(normalized_range)
            if len(normalized_range) <= _RANGE_EDGE_LIMIT:
                precedents.update(
                    CellAddress(
                        normalized_range.sheet or address.sheet,
                        cell.row,
                        cell.column,
                    )
                    for cell in normalized_range
                )
            elif normalized_range.contains(address.row, address.column) and (
                normalized_range.sheet or address.sheet
            ).casefold() == address.sheet.casefold():
                precedents.add(address)

        self.graph.set_precedents(address, precedents)
        function_names = collect_function_names(ast)
        if any(
            name in FUNCTION_REGISTRY and FUNCTION_REGISTRY[name].volatile
            for name in function_names
        ):
            self._volatile.add(address)
        else:
            self._volatile.discard(address)
        if ranges:
            self._range_precedents[address] = tuple(ranges)
        else:
            self._range_precedents.pop(address, None)

    def _is_table_formula(self, address: CellAddress) -> bool:
        from duddysheet.core.parser import FunctionNode

        ast = self._asts.get(address)
        return isinstance(ast, FunctionNode) and ast.name == "TABLE"

    def _structured_references(
        self,
        ast: Node,
        scope: str,
        origin: tuple[int, int],
    ) -> list[Reference]:
        from duddysheet.core.parser import StructuredReferenceNode, node_children
        from duddysheet.core.tables import resolve_structured

        found: list[Reference] = []

        from duddysheet.core.parser import NameNode
        from duddysheet.core.tables import StructuredSpec, find_table

        def visit(node: Node) -> None:
            if isinstance(node, StructuredReferenceNode):
                reference = resolve_structured(self.workbook, node.table, node.spec, scope, origin)
                if reference is not None:
                    found.append(reference)
                return
            if isinstance(node, NameNode) and node.sheet is None and find_table(self.workbook, node.name):
                reference = resolve_structured(self.workbook, node.name, StructuredSpec(), scope, origin)
                if reference is not None:
                    found.append(reference)
                return
            for child in node_children(node):
                visit(child)

        if any(sheet.tables for sheet in self.workbook):
            visit(ast)
        from duddysheet.core.parser import FunctionNode

        if isinstance(ast, FunctionNode) and ast.name == "TABLE":
            from duddysheet.core.data_table import data_table_at, dependency_ranges

            try:
                sheet = self.workbook.get_sheet(scope)
            except KeyError:
                return found
            spec = data_table_at(sheet, *origin)
            if spec is not None:
                found.extend(dependency_ranges(spec, sheet.name))
        return found

    def _formula_references(
        self,
        ast: Node,
        scope: str,
        seen: frozenset[tuple[str | None, str]] = frozenset(),
        *,
        origin: tuple[int, int] = (0, 0),
    ) -> list[Reference]:
        """Return cell and range precedents, following named formulas and tables."""
        resolved: list[Reference] = self._structured_references(ast, scope, origin)
        for reference in collect_references(ast, sheet_names=self.workbook.sheet_names):
            if not isinstance(reference, str):
                resolved.append(reference)
                continue
            name_scope = scope
            name = reference
            if "!" in reference:
                name_scope, _, name = reference.partition("!")
            try:
                defined = self.workbook.get_name(name, scope=name_scope)
            except (KeyError, ValueError):
                continue
            if defined.reference is not None:
                resolved.append(defined.reference)
                continue
            key = (defined.scope, defined.name.casefold())
            if defined.formula is None or key in seen:
                continue
            try:
                name_ast = parse_formula(defined.formula)
            except ValueError:
                continue
            resolved.extend(
                self._formula_references(name_ast, scope, seen | {key})
            )
        return resolved

    def _address_from_reference(
        self,
        reference: CellReference,
        default_sheet: str,
    ) -> CellAddress:
        selected_sheet = reference.sheet or default_sheet
        try:
            selected_sheet = self.workbook.get_sheet(selected_sheet).name
        except KeyError:
            pass
        return CellAddress(selected_sheet, reference.row, reference.column)

    def _normalize_range(
        self,
        reference: RangeReference,
        default_sheet: str,
    ) -> RangeReference:
        selected_sheet = reference.sheet or default_sheet
        try:
            selected_sheet = self.workbook.get_sheet(selected_sheet).name
        except KeyError:
            pass
        return RangeReference(
            replace(reference.start, sheet=selected_sheet),
            replace(reference.end, sheet=selected_sheet),
            whole_row=reference.whole_row,
            whole_column=reference.whole_column,
        )

    def _affected_formulas(self, changed: set[CellAddress]) -> set[CellAddress]:
        affected = set(changed)
        queue = deque(changed)
        dependents = self.graph._dependents
        has_ranges = bool(self._range_precedents)
        has_blockers = bool(self._spill_blockers)
        while queue:
            current = queue.popleft()
            direct = dependents.get(current)
            if direct:
                for dependent in direct:
                    if dependent not in affected:
                        affected.add(dependent)
                        queue.append(dependent)
            if has_ranges:
                for dependent in self._range_dependents(current):
                    if dependent not in affected:
                        affected.add(dependent)
                        queue.append(dependent)
            if has_blockers:
                for parent, blockers in self._spill_blockers.items():
                    if current in blockers and parent not in affected:
                        affected.add(parent)
                        queue.append(parent)
        return affected & self._asts.keys()

    def _range_dependents(self, address: CellAddress) -> set[CellAddress]:
        dependents: set[CellAddress] = set()
        for formula, ranges in self._range_precedents.items():
            for reference in ranges:
                sheet_name = reference.sheet or formula.sheet
                if (
                    sheet_name.casefold() == address.sheet.casefold()
                    and reference.contains(address.row, address.column)
                ):
                    dependents.add(formula)
                    break
        return dependents

    def _calculate_nodes(
        self,
        selected: set[CellAddress],
    ) -> RecalculationResult:
        self.calc_generation += 1
        remaining = set(selected) & self._asts.keys()
        order, circular_cells = self.graph.recalculation_plan(remaining)
        circular: list[CellAddress] = list(circular_cells)
        if circular and self.workbook.iterative_calculation:
            return self._calculate_iteratively(order, circular)
        for address in circular:
            self._cache_result(address, CIRC_ERROR)
        recalculated: list[CellAddress] = []
        for address in order:
            result = self.evaluator.evaluate(
                self._asts[address],
                sheet_name=address.sheet,
                origin=(address.row, address.column),
            )
            self._cache_result(address, result)
            recalculated.append(address)
        return RecalculationResult(
            tuple(recalculated),
            tuple(sorted(set(circular))),
        )

    def _calculate_iteratively(
        self,
        order: tuple[CellAddress, ...],
        circular: list[CellAddress],
    ) -> RecalculationResult:
        """Resolve circular references by iteration, as Excel's option does."""
        for address in order:
            self._evaluate_into(address)
        limit = max(1, int(self.workbook.max_iterations))
        tolerance = float(self.workbook.max_change)
        for _ in range(limit):
            largest = 0.0
            for address in circular:
                before = self._numeric_cache(address)
                self._evaluate_into(address)
                after = self._numeric_cache(address)
                if before is None or after is None:
                    largest = max(largest, 0.0 if before == after else float("inf"))
                else:
                    largest = max(largest, abs(after - before))
            if largest <= tolerance:
                break
        for address in order:
            self._evaluate_into(address)
        return RecalculationResult(tuple(order) + tuple(circular), ())

    def _evaluate_into(self, address: CellAddress) -> None:
        result = self.evaluator.evaluate(
            self._asts[address],
            sheet_name=address.sheet,
            origin=(address.row, address.column),
        )
        self._cache_result(address, result)

    def _numeric_cache(self, address: CellAddress) -> float | None:
        cell = self.workbook.get_sheet(address.sheet).get_cell(address.row, address.column)
        value = cell.cached_value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    def _cache_result(self, address: CellAddress, value: Any) -> None:
        sheet = self.workbook.get_sheet(address.sheet)
        if isinstance(value, tuple):
            self._cache_spill(address, value)
            return
        self._clear_spill(address)
        self._spill_blockers.pop(address, None)
        if isinstance(value, SpreadsheetError):
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=value.literal,
            )
        else:
            sheet.update_cache(address.row, address.column, value, error=None)

    def _cache_spill(self, address: CellAddress, value: tuple[Any, ...]) -> None:
        sheet = self.workbook.get_sheet(address.sheet)
        rows = (
            [list(row) for row in value]
            if value and all(isinstance(row, tuple) for row in value)
            else [list(value)]
        )
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            self._clear_spill(address)
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=VALUE_ERROR.literal,
            )
            return

        desired: dict[CellAddress, Any] = {}
        out_of_bounds = False
        for row_offset, row_values in enumerate(rows):
            for column_offset, item in enumerate(row_values):
                row = address.row + row_offset
                column = address.column + column_offset
                if row >= MAX_ROWS or column >= MAX_COLUMNS:
                    out_of_bounds = True
                    continue
                desired[CellAddress(address.sheet, row, column)] = item

        old_children = self._spill_cells.get(address, set())
        blockers: set[CellAddress] = set()
        if out_of_bounds:
            blockers.add(address)
        for target in desired:
            if target == address or target in old_children:
                continue
            cell = sheet.get_cell(target.row, target.column)
            if not cell.is_empty:
                blockers.add(target)

        if blockers:
            self._clear_spill(address)
            self._spill_blockers[address] = blockers
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=SPILL_ERROR.literal,
            )
            return

        self._clear_spill(address)
        self._spill_blockers.pop(address, None)
        anchor_value = desired[address]
        if isinstance(anchor_value, SpreadsheetError):
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=anchor_value.literal,
            )
        else:
            sheet.update_cache(address.row, address.column, anchor_value, error=None)

        parent_cell = sheet.get_cell(address.row, address.column)
        children: set[CellAddress] = set()
        for target, item in desired.items():
            if target == address:
                continue
            child = (
                Cell(
                    cached_value=None,
                    format=parent_cell.format,
                    error=item.literal,
                    spill_parent=(address.row, address.column),
                )
                if isinstance(item, SpreadsheetError)
                else Cell(
                    cached_value=item,
                    format=parent_cell.format,
                    spill_parent=(address.row, address.column),
                )
            )
            sheet.put_cell(target.row, target.column, child)
            children.add(target)
            self._spill_owners[target] = address
        if children:
            self._spill_cells[address] = children

    def _clear_spill(self, address: CellAddress) -> set[CellAddress]:
        children = self._spill_cells.pop(address, set())
        if not children:
            return set()
        sheet = self.workbook.get_sheet(address.sheet)
        for child_address in children:
            cell = sheet.get_cell(child_address.row, child_address.column)
            if cell.spill_parent == (address.row, address.column):
                sheet.put_cell(child_address.row, child_address.column, EMPTY_CELL)
            self._spill_owners.pop(child_address, None)
        return children
