"""Excel's rules for formulas typed into a cell.

Excel refuses some formulas when they are entered, before calculating
anything: a function given too few or too many arguments, an array constant
holding anything but plain values, and a value where a function needs a cell
range (``=COUNTIF({1,2,3},">1")``). ``validate_entry`` applies the same rules
so that a formula accepted here is one Excel accepts too. Formulas read from
files are not checked, so older workbooks keep opening.
"""

from __future__ import annotations

from collections.abc import Callable

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
    ReferenceNode,
    ReferenceOperatorNode,
    SpillNode,
    StructuredReferenceNode,
    ThreeDReferenceNode,
    UnaryNode,
    node_children,
    parse_formula,
)
from duddysheet.core.tokenizer import FormulaSyntaxError

PROBLEM = "There's a problem with this formula."
TOO_FEW = "You've entered too few arguments for this function."
TOO_MANY = "You've entered too many arguments for this function."

# Functions that can return a cell reference, so they may fill a range argument.
REFERENCE_FUNCTIONS = frozenset(
    {"IF", "IFS", "CHOOSE", "INDEX", "XLOOKUP", "LET", "SWITCH", "TAKE", "DROP", "INDIRECT", "OFFSET", "TRIMRANGE"}
)


def _first(index: int, _count: int) -> bool:
    return index == 0


def _second(index: int, _count: int) -> bool:
    return index == 1


def _first_and_third(index: int, _count: int) -> bool:
    return index in (0, 2)


def _criteria_pairs(index: int, _count: int) -> bool:
    return index % 2 == 0


def _target_then_pairs(index: int, _count: int) -> bool:
    return index == 0 or index % 2 == 1


def _after_first(index: int, _count: int) -> bool:
    return index >= 1


_D_FUNCTIONS = ("DAVERAGE", "DCOUNT", "DCOUNTA", "DGET", "DMAX", "DMIN", "DPRODUCT", "DSTDEV", "DSTDEVP", "DSUM", "DVAR", "DVARP")
REFERENCE_ARGUMENTS: dict[str, Callable[[int, int], bool]] = {
    "COUNTIF": _first,
    "COUNTIFS": _criteria_pairs,
    "SUMIF": _first_and_third,
    "AVERAGEIF": _first_and_third,
    "SUMIFS": _target_then_pairs,
    "AVERAGEIFS": _target_then_pairs,
    "MAXIFS": _target_then_pairs,
    "MINIFS": _target_then_pairs,
    "COUNTBLANK": _first,
    "RANK": _second,
    "RANK.EQ": _second,
    "RANK.AVG": _second,
    "SUBTOTAL": _after_first,
    "OFFSET": _first,
    "ROW": _first,
    "COLUMN": _first,
    "AREAS": _first,
    "CELL": _second,
    "FORMULATEXT": _first,
    "ISFORMULA": _first,
    **{name: _first for name in _D_FUNCTIONS},
}
# Functions whose arguments come in pairs after a fixed start.
_EVEN_COUNT = frozenset({"IFS", "COUNTIFS"})
_ODD_COUNT = frozenset({"SUMIFS", "AVERAGEIFS", "MAXIFS", "MINIFS"})


def validate_entry(formula: str | Node) -> Node:
    """Parse (if needed) and check a typed formula; raise ``FormulaSyntaxError`` if Excel refuses it."""
    node = parse_formula(formula) if isinstance(formula, str) else formula
    _check(node)
    return node


def _check(node: Node) -> None:
    if isinstance(node, ArrayNode):
        for row in node.rows:
            for item in row:
                if not _is_constant(item):
                    raise FormulaSyntaxError(PROBLEM, 0)
        return
    if isinstance(node, FunctionNode):
        _check_call(node)
    for child in node_children(node):
        _check(child)


def _check_call(node: FunctionNode) -> None:
    from duddysheet.core.functions import FUNCTION_REGISTRY

    name = node.name.upper().removeprefix("_XLFN.").removeprefix("_XLWS.")
    specification = FUNCTION_REGISTRY.get(name)
    if specification is None:
        return
    count = len(node.arguments)
    if count == 1 and isinstance(node.arguments[0], MissingNode) and specification.min_args == 0:
        count = 0
    if count < specification.min_args:
        raise FormulaSyntaxError(TOO_FEW, 0)
    if count > specification.max_args:
        raise FormulaSyntaxError(TOO_MANY, 0)
    if name in _EVEN_COUNT and count % 2:
        raise FormulaSyntaxError(TOO_FEW, 0)
    if name in _ODD_COUNT and not count % 2:
        raise FormulaSyntaxError(TOO_FEW, 0)
    # LET names come before each value, and LAMBDA's parameters before its body.
    if name == "LET" and (not count % 2 or any(not isinstance(node.arguments[index], NameNode) for index in range(0, count - 1, 2))):
        raise FormulaSyntaxError(PROBLEM, 0)
    if name == "LAMBDA" and any(not _is_parameter(argument) for argument in node.arguments[:-1]):
        raise FormulaSyntaxError(PROBLEM, 0)
    needs_reference = REFERENCE_ARGUMENTS.get(name)
    if needs_reference is None:
        return
    for index, argument in enumerate(node.arguments):
        if needs_reference(index, count) and not _is_reference(argument):
            raise FormulaSyntaxError(PROBLEM, 0)


def _is_parameter(node: Node) -> bool:
    """A LAMBDA parameter: a name, or [name] for an optional one."""
    if isinstance(node, NameNode):
        return True
    return isinstance(node, StructuredReferenceNode) and node.table is None and node.inner.strip().replace("_", "a").replace(".", "a").isalnum()


def _is_constant(node: Node) -> bool:
    if isinstance(node, (LiteralNode, ErrorNode)):
        return True
    return (
        isinstance(node, UnaryNode)
        and node.operator in ("-", "+")
        and isinstance(node.operand, LiteralNode)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    )


def _is_reference(node: Node) -> bool:
    if isinstance(node, ParenNode):
        return _is_reference(node.inner)
    if isinstance(
        node,
        (
            ReferenceNode,
            NameNode,
            ThreeDReferenceNode,
            StructuredReferenceNode,
            SpillNode,
            ImplicitIntersectionNode,
            ReferenceOperatorNode,
            CallNode,
            MissingNode,
        ),
    ):
        return True
    if isinstance(node, BinaryNode) and node.operator in (":", " ", ","):
        return True
    if isinstance(node, FunctionNode):
        from duddysheet.core.functions import FUNCTION_REGISTRY

        name = node.name.upper().removeprefix("_XLFN.").removeprefix("_XLWS.")
        return name in REFERENCE_FUNCTIONS or name not in FUNCTION_REGISTRY
    return False
