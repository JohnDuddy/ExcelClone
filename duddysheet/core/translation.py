"""Formula text rendering and copy/structure reference translation."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from duddysheet.core.errors import REF_ERROR
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
    map_children,
    parse_formula,
    shift_references,
)
from duddysheet.core.refs import (
    CellReference,
    RangeReference,
    Reference,
    quote_sheet_name,
)

ReferenceMapper = Callable[[Reference], Reference | Node]


def formula_to_text(node: Node, *, dialect: str = "native") -> str:
    """Render an AST as a valid, semantically equivalent formula.

    ``dialect="xlsx"`` adds the function and parameter prefixes Excel's file
    format requires.
    """
    return "=" + _render_node(node, dialect)


# Excel operator precedence, lowest to highest; all binary operators are
# left-associative (Excel evaluates 2^3^2 as 64).
_PRECEDENCE = {
    "=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
    "&": 2,
    "+": 3, "-": 3,
    "*": 4, "/": 4,
    "^": 5,
}


def _precedence(node: Node) -> int:
    if isinstance(node, BinaryNode):
        return _PRECEDENCE.get(node.operator, 0)
    if isinstance(node, PercentNode):
        return 6
    if isinstance(node, UnaryNode):
        return 7
    return 9


def render_sheet_span(first: str, last: str) -> str:
    """Render the sheet prefix of a three-dimensional reference."""
    span = f"{first}:{last}"
    if all(part.replace("_", "a").isalnum() and not part[0].isdigit() for part in (first, last)):
        return span
    return "'" + span.replace("'", "''") + "'"


def translate_formula_copy(
    formula: str,
    *,
    rows: int = 0,
    columns: int = 0,
) -> str:
    """Translate relative references when copying a formula."""
    return formula_to_text(
        shift_references(
            parse_formula(formula),
            rows=rows,
            columns=columns,
        )
    )


def translate_formula_structure(
    formula: str,
    *,
    formula_sheet: str,
    target_sheet: str,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> str:
    """Translate references affected by row or column insertion/deletion."""
    if axis not in ("row", "column"):
        raise ValueError(f"Unknown structure axis: {axis!r}")
    if count < 1:
        raise ValueError("Structural edit count must be positive")

    def adjust(reference: Reference) -> Reference | Node:
        selected_sheet = reference.sheet or formula_sheet
        if selected_sheet.casefold() != target_sheet.casefold():
            return reference
        translated = translate_reference_structure(
            reference,
            axis=axis,
            index=index,
            count=count,
            delete=delete,
        )
        return ErrorNode(REF_ERROR) if translated is None else translated

    return formula_to_text(_map_references(parse_formula(formula), adjust))


def rename_formula_sheet(formula: str, old_name: str, new_name: str) -> str:
    """Rename explicit sheet qualifiers in a formula."""

    def adjust(reference: Reference) -> Reference:
        if reference.sheet is None or reference.sheet.casefold() != old_name.casefold():
            return reference
        if isinstance(reference, CellReference):
            return replace(reference, sheet=new_name)
        return RangeReference(
            replace(reference.start, sheet=new_name),
            replace(reference.end, sheet=new_name),
            whole_row=reference.whole_row,
            whole_column=reference.whole_column,
        )

    node = _map_references(parse_formula(formula), adjust)
    node = _rename_name_nodes(node, old_name, new_name)
    return formula_to_text(node)


def translate_reference_structure(
    reference: Reference,
    *,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> Reference | None:
    """Translate one reference for a structural edit."""
    if isinstance(reference, CellReference):
        coordinate = reference.row if axis == "row" else reference.column
        translated = _translate_cell_coordinate(
            coordinate,
            index=index,
            count=count,
            delete=delete,
        )
        if translated is None:
            return None
        return replace(
            reference,
            row=translated if axis == "row" else reference.row,
            column=translated if axis == "column" else reference.column,
        )

    if axis == "row" and reference.whole_column:
        return reference
    if axis == "column" and reference.whole_row:
        return reference
    start_value = reference.start.row if axis == "row" else reference.start.column
    end_value = reference.end.row if axis == "row" else reference.end.column
    translated = _translate_range_coordinates(
        start_value,
        end_value,
        index=index,
        count=count,
        delete=delete,
    )
    if translated is None:
        return None
    translated_start, translated_end = translated
    start = replace(
        reference.start,
        row=translated_start if axis == "row" else reference.start.row,
        column=translated_start if axis == "column" else reference.start.column,
    )
    end = replace(
        reference.end,
        row=translated_end if axis == "row" else reference.end.row,
        column=translated_end if axis == "column" else reference.end.column,
    )
    return RangeReference(
        start,
        end,
        whole_row=reference.whole_row,
        whole_column=reference.whole_column,
    )


def _map_references(node: Node, mapper: ReferenceMapper) -> Node:
    if isinstance(node, ReferenceNode):
        mapped = mapper(node.reference)
        return mapped if isinstance(mapped, Node) else ReferenceNode(mapped)
    return map_children(node, lambda child: _map_references(child, mapper))


def _rename_name_nodes(node: Node, old_name: str, new_name: str) -> Node:
    if isinstance(node, NameNode):
        if node.sheet is not None and node.sheet.casefold() == old_name.casefold():
            return replace(node, sheet=new_name)
        return node
    if isinstance(node, ThreeDReferenceNode):
        first = new_name if node.first_sheet.casefold() == old_name.casefold() else node.first_sheet
        last = new_name if node.last_sheet.casefold() == old_name.casefold() else node.last_sheet
        return replace(node, first_sheet=first, last_sheet=last)
    return map_children(
        node,
        lambda child: _rename_name_nodes(child, old_name, new_name),
    )


def _translate_cell_coordinate(
    value: int,
    *,
    index: int,
    count: int,
    delete: bool,
) -> int | None:
    if not delete:
        return value + count if value >= index else value
    end = index + count
    if index <= value < end:
        return None
    return value - count if value >= end else value


def _translate_range_coordinates(
    start: int,
    end: int,
    *,
    index: int,
    count: int,
    delete: bool,
) -> tuple[int, int] | None:
    ascending = start <= end
    low, high = (start, end) if ascending else (end, start)
    if not delete:
        if index <= low:
            low += count
            high += count
        elif low < index <= high:
            high += count
    else:
        deleted_end = index + count
        if high < index:
            pass
        elif low >= deleted_end:
            low -= count
            high -= count
        else:
            new_low = low if low < index else index
            new_high = high - count if high >= deleted_end else index - 1
            if new_low > new_high:
                return None
            low, high = new_low, new_high
    return (low, high) if ascending else (high, low)


def _render_node(
    node: Node,
    dialect: str = "native",
    bound: frozenset[str] = frozenset(),
) -> str:
    def render(child: Node, names: frozenset[str] = bound) -> str:
        return _render_node(child, dialect, names)

    xlsx = dialect == "xlsx"
    if isinstance(node, LiteralNode):
        if isinstance(node.value, str):
            return '"' + node.value.replace('"', '""') + '"'
        if isinstance(node.value, bool):
            return "TRUE" if node.value else "FALSE"
        return str(node.value)
    if isinstance(node, ErrorNode):
        return node.error.literal
    if isinstance(node, ReferenceNode):
        return node.reference.to_a1()
    if isinstance(node, NameNode):
        if xlsx and node.sheet is None and node.name.casefold() in bound:
            return "_xlpm." + node.name
        prefix = (
            f"{quote_sheet_name(node.sheet)}!" if node.sheet is not None else ""
        )
        return prefix + node.name
    if isinstance(node, UnaryNode):
        operand = render(node.operand)
        if _precedence(node.operand) < 7:
            operand = f"({operand})"
        return f"{node.operator}{operand}"
    if isinstance(node, PercentNode):
        operand = render(node.operand)
        if _precedence(node.operand) < 6:
            operand = f"({operand})"
        return f"{operand}%"
    if isinstance(node, BinaryNode):
        level = _PRECEDENCE.get(node.operator, 0)
        left = render(node.left)
        right = render(node.right)
        if _precedence(node.left) < level:
            left = f"({left})"
        if _precedence(node.right) <= level:
            right = f"({right})"
        return f"{left}{node.operator}{right}"
    if isinstance(node, ReferenceOperatorNode):
        return f"{render(node.left)}{node.operator}{render(node.right)}"
    if isinstance(node, ParenNode):
        return f"({render(node.inner)})"
    if isinstance(node, StructuredReferenceNode):
        from duddysheet.core.tables import render_structured

        if xlsx:
            return render_structured(node.table, node.spec, file_format=True)
        return (node.table or "") + "[" + node.inner + "]"
    if isinstance(node, MissingNode):
        return ""
    if isinstance(node, CallNode):
        callee = render(node.callee)
        arguments = ",".join(render(item) for item in node.arguments)
        return f"{callee}({arguments})"
    if isinstance(node, ImplicitIntersectionNode):
        if xlsx:
            return f"_xlfn.SINGLE({render(node.operand)})"
        return f"@{render(node.operand)}"
    if isinstance(node, SpillNode):
        if xlsx:
            return f"_xlfn.ANCHORARRAY({render(node.operand)})"
        return f"{render(node.operand)}#"
    if isinstance(node, ThreeDReferenceNode):
        return f"{render_sheet_span(node.first_sheet, node.last_sheet)}!{node.reference.to_a1()}"
    if isinstance(node, FunctionNode):
        name = node.name
        arguments_nodes = node.arguments
        if xlsx and name in ("LET", "LAMBDA"):
            return _render_binding_function(node, dialect, bound)
        if xlsx:
            from duddysheet.io.formula_compat import FUTURE_FUNCTIONS, WORKSHEET_FUNCTIONS

            if name in WORKSHEET_FUNCTIONS:
                name = "_xlfn._xlws." + name
            elif name in FUTURE_FUNCTIONS:
                name = "_xlfn." + name
            elif name.casefold() in bound:
                name = "_xlpm." + node.name
        arguments = ",".join(render(item) for item in arguments_nodes)
        return f"{name}({arguments})"
    if isinstance(node, ArrayNode):
        rows = ";".join(",".join(render(item) for item in row) for row in node.rows)
        return "{" + rows + "}"
    raise TypeError(f"Cannot render formula node: {type(node).__name__}")


def _render_binding_function(
    node: FunctionNode,
    dialect: str,
    bound: frozenset[str],
) -> str:
    """Render LET/LAMBDA with ``_xlpm.`` parameter names for the file format."""
    names = set(bound)
    rendered: list[str] = []
    arguments = node.arguments
    if node.name == "LET":
        for index, argument in enumerate(arguments):
            is_name = index % 2 == 0 and index < len(arguments) - 1
            if is_name and isinstance(argument, NameNode):
                names.add(argument.name.casefold())
                rendered.append("_xlpm." + argument.name)
            else:
                rendered.append(_render_node(argument, dialect, frozenset(names)))
    else:
        for argument in arguments[:-1]:
            if isinstance(argument, NameNode):
                names.add(argument.name.casefold())
                rendered.append("_xlpm." + argument.name)
            elif isinstance(argument, StructuredReferenceNode) and argument.table is None:
                # Optional LAMBDA parameter: [b] is stored as [_xlpm.b].
                name = argument.inner.strip()
                names.add(name.casefold())
                rendered.append(f"[_xlpm.{name}]")
            else:
                rendered.append(_render_node(argument, dialect, frozenset(names)))
        if arguments:
            rendered.append(_render_node(arguments[-1], dialect, frozenset(names)))
    return f"_xlfn.{node.name}({','.join(rendered)})"
