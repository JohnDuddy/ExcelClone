"""Formula auditing: precedents, dependents, Evaluate Formula steps, error checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duddysheet.core.errors import SpreadsheetError
from duddysheet.core.parser import (
    ArrayNode,
    FunctionNode,
    LiteralNode,
    Node,
    ParenNode,
    ReferenceNode,
    collect_references,
    map_children,
    node_children,
    parse_formula,
)
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.values import number_text, parse_number_text

Address = tuple[str, int, int]
_LAZY = frozenset({"IF", "IFS", "IFERROR", "IFNA", "SWITCH", "LET", "LAMBDA", "CHOOSE"})


def _resolve(workbook: Any, sheet_name: str, reference: Any) -> list[Address]:
    if isinstance(reference, str):
        try:
            defined = workbook.get_name(reference.split("!")[-1], scope=sheet_name)
        except (KeyError, ValueError):
            return []
        reference = defined.reference
        if reference is None:
            return []
    sheet = reference.sheet or sheet_name
    try:
        target = workbook.get_sheet(sheet)
    except KeyError:
        return []
    if isinstance(reference, CellReference):
        return [(target.name, reference.row, reference.column)]
    max_row, max_column = target.extent
    bottom = min(reference.max_row, max(max_row, reference.min_row))
    right = min(reference.max_column, max(max_column, reference.min_column))
    if (bottom - reference.min_row + 1) * (right - reference.min_column + 1) > 200_000:
        return []
    return [
        (target.name, row, column)
        for row in range(reference.min_row, bottom + 1)
        for column in range(reference.min_column, right + 1)
    ]


def precedents(workbook: Any, sheet_name: str, row: int, column: int) -> set[Address]:
    """Return the cells a formula reads directly."""
    cell = workbook.get_sheet(sheet_name).get_cell(row, column)
    if not cell.is_formula:
        return set()
    try:
        references = collect_references(parse_formula(cell.raw_input), sheet_names=workbook.sheet_names)
    except ValueError:
        return set()
    found: set[Address] = set()
    for reference in references:
        found.update(_resolve(workbook, sheet_name, reference))
    return found


def dependents(workbook: Any, sheet_name: str, row: int, column: int) -> set[Address]:
    """Return the formulas that read a cell directly."""
    target_sheet = workbook.get_sheet(sheet_name).name.casefold()
    found: set[Address] = set()
    for sheet in workbook:
        for (formula_row, formula_column), cell in sheet.iter_unordered():
            if not cell.is_formula:
                continue
            try:
                references = collect_references(parse_formula(cell.raw_input), sheet_names=workbook.sheet_names)
            except ValueError:
                continue
            for reference in references:
                if isinstance(reference, str):
                    resolved = _resolve(workbook, sheet.name, reference)
                    if any(item[0].casefold() == target_sheet and item[1:] == (row, column) for item in resolved):
                        found.add((sheet.name, formula_row, formula_column))
                    continue
                reference_sheet = (reference.sheet or sheet.name).casefold()
                if reference_sheet != target_sheet:
                    continue
                if isinstance(reference, CellReference):
                    hit = (reference.row, reference.column) == (row, column)
                else:
                    hit = reference.contains(row, column)
                if hit:
                    found.add((sheet.name, formula_row, formula_column))
                    break
    return found


# ------------------------------------------------------- Evaluate Formula
@dataclass(frozen=True, slots=True)
class EvaluationStep:
    """One Evaluate Formula state: the formula text and the part evaluated next."""

    text: str
    underline: tuple[int, int] | None


def _value_node(value: Any) -> Node:
    if isinstance(value, tuple):
        rows = value if value and isinstance(value[0], tuple) else (value,)
        return ArrayNode(tuple(tuple(_value_node(item) for item in row) for row in rows))
    if isinstance(value, SpreadsheetError):
        from duddysheet.core.parser import ErrorNode

        return ErrorNode(value)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    if isinstance(value, float):
        value = float(number_text(value))
    return LiteralNode(value)


def _is_value(node: Node) -> bool:
    from duddysheet.core.parser import ErrorNode, MissingNode

    if isinstance(node, (LiteralNode, ArrayNode, ErrorNode, MissingNode)):
        return True
    return isinstance(node, ReferenceNode) and isinstance(node.reference, RangeReference)


def _next_target(node: Node) -> Node | None:
    """The next part Excel evaluates: the leftmost innermost unevaluated part."""
    if _is_value(node):
        return None
    if isinstance(node, ReferenceNode):
        return node
    children = node_children(node)
    if isinstance(node, FunctionNode) and node.name in _LAZY:
        children = children[:1]
    for child in children:
        found = _next_target(child)
        if found is not None:
            return found
    if isinstance(node, ParenNode):
        return None
    return node


def evaluation_steps(workbook: Any, sheet_name: str, row: int, column: int) -> list[EvaluationStep]:
    """Return Evaluate Formula's successive states for a cell, ending with the result."""
    from duddysheet.core.evaluator import FormulaEvaluator
    from duddysheet.core.parser import NameNode
    from duddysheet.core.translation import formula_to_text

    cell = workbook.get_sheet(sheet_name).get_cell(row, column)
    if not cell.is_formula:
        return []
    try:
        tree = parse_formula(cell.raw_input)
    except ValueError:
        return [EvaluationStep(cell.raw_input, None)]
    evaluator = FormulaEvaluator(workbook)
    steps: list[EvaluationStep] = []
    marker = NameNode("Q_EVAL_MARK")
    for _ in range(500):
        target = _next_target(tree)
        if target is None:
            break
        text = formula_to_text(tree)
        marked = formula_to_text(_replace_node(tree, target, marker))
        start = marked.find("Q_EVAL_MARK")
        fragment = formula_to_text(target)[1:]
        steps.append(EvaluationStep(text, (start, start + len(fragment)) if start >= 0 else None))
        value = evaluator.evaluate(target, sheet_name=sheet_name, origin=(row, column))
        tree = _strip_parens(_replace_node(tree, target, _value_node(value)))
    if not _is_value(tree) or isinstance(tree, ReferenceNode):
        value = evaluator.evaluate(tree, sheet_name=sheet_name, origin=(row, column))
        tree = _value_node(value)
    steps.append(EvaluationStep(formula_to_text(tree), None))
    return steps


def _strip_parens(node: Node) -> Node:
    """Drop parentheses that now enclose a single value."""
    if isinstance(node, ParenNode) and _is_value(node.inner):
        return node.inner
    return map_children(node, _strip_parens)


def _replace_node(tree: Node, target: Node, replacement: Node) -> Node:
    if tree is target:
        return replacement
    return map_children(tree, lambda child: _replace_node(child, target, replacement))


# ------------------------------------------------------------ error checks
def error_flags(sheet: Any, row: int, column: int) -> tuple[str, ...]:
    """Return Excel's default error-checking findings for a cell (green triangle)."""
    cell = sheet.get_cell(row, column)
    flags: list[str] = []
    if cell.error is not None and cell.is_formula:
        flags.append("error_value")
    if (
        isinstance(cell.raw_input, str)
        and not cell.is_formula
        and cell.format.number_format != "@"
        and cell.raw_input.strip()
        and parse_number_text(cell.raw_input) is not None
        and not any(character in cell.raw_input for character in "/:-")
    ):
        flags.append("number_stored_as_text")
    if cell.is_formula and _inconsistent(sheet, row, column):
        flags.append("inconsistent_formula")
    return tuple(flags)


def _r1c1(sheet: Any, row: int, column: int) -> str | None:
    cell = sheet.get_cell(row, column)
    if not cell.is_formula:
        return None
    try:
        ast = parse_formula(cell.raw_input)
    except ValueError:
        return None

    def relative(node: Node) -> Node:
        if isinstance(node, ReferenceNode):
            reference = node.reference
            if isinstance(reference, CellReference):
                return LiteralNode(reference.to_r1c1(origin=(row, column)))
            if isinstance(reference, RangeReference):
                return LiteralNode(
                    reference.start.to_r1c1(origin=(row, column))
                    + ":"
                    + reference.end.to_r1c1(origin=(row, column))
                )
        return map_children(node, relative)

    from duddysheet.core.translation import formula_to_text

    return formula_to_text(relative(ast))


def _inconsistent(sheet: Any, row: int, column: int) -> bool:
    """A formula unlike the matching formulas on both sides of it."""
    own = _r1c1(sheet, row, column)
    if own is None:
        return False
    for first, second in (((row - 1, column), (row + 1, column)), ((row, column - 1), (row, column + 1))):
        if min(first) < 0:
            continue
        left = _r1c1(sheet, *first)
        right = _r1c1(sheet, *second)
        if left is not None and left == right and left != own:
            return True
    return False


