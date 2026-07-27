"""Formula text rendering and copy/structure reference translation."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from duddysheet.core.errors import REF_ERROR
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
    shift_references,
)
from duddysheet.core.refs import (
    CellReference,
    RangeReference,
    Reference,
    quote_sheet_name,
)

ReferenceMapper = Callable[[Reference], Reference | Node]


def formula_to_text(node: Node) -> str:
    """Render an AST as a valid, semantically equivalent formula."""
    rendered = _render_node(node)
    if isinstance(node, (UnaryNode, PercentNode, BinaryNode, ReferenceOperatorNode)):
        rendered = rendered[1:-1]
    return "=" + rendered


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
    if isinstance(node, UnaryNode):
        return replace(node, operand=_map_references(node.operand, mapper))
    if isinstance(node, PercentNode):
        return replace(node, operand=_map_references(node.operand, mapper))
    if isinstance(node, (BinaryNode, ReferenceOperatorNode)):
        return replace(
            node,
            left=_map_references(node.left, mapper),
            right=_map_references(node.right, mapper),
        )
    if isinstance(node, FunctionNode):
        return replace(
            node,
            arguments=tuple(_map_references(item, mapper) for item in node.arguments),
        )
    if isinstance(node, ArrayNode):
        return replace(
            node,
            rows=tuple(
                tuple(_map_references(item, mapper) for item in row)
                for row in node.rows
            ),
        )
    return node


def _rename_name_nodes(node: Node, old_name: str, new_name: str) -> Node:
    if isinstance(node, NameNode):
        if node.sheet is not None and node.sheet.casefold() == old_name.casefold():
            return replace(node, sheet=new_name)
        return node
    if isinstance(node, UnaryNode):
        return replace(
            node,
            operand=_rename_name_nodes(node.operand, old_name, new_name),
        )
    if isinstance(node, PercentNode):
        return replace(
            node,
            operand=_rename_name_nodes(node.operand, old_name, new_name),
        )
    if isinstance(node, (BinaryNode, ReferenceOperatorNode)):
        return replace(
            node,
            left=_rename_name_nodes(node.left, old_name, new_name),
            right=_rename_name_nodes(node.right, old_name, new_name),
        )
    if isinstance(node, FunctionNode):
        return replace(
            node,
            arguments=tuple(
                _rename_name_nodes(item, old_name, new_name)
                for item in node.arguments
            ),
        )
    if isinstance(node, ArrayNode):
        return replace(
            node,
            rows=tuple(
                tuple(
                    _rename_name_nodes(item, old_name, new_name)
                    for item in row
                )
                for row in node.rows
            ),
        )
    return node


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


def _render_node(node: Node) -> str:
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
        prefix = (
            f"{quote_sheet_name(node.sheet)}!" if node.sheet is not None else ""
        )
        return prefix + node.name
    if isinstance(node, UnaryNode):
        return f"({node.operator}{_render_node(node.operand)})"
    if isinstance(node, PercentNode):
        return f"({_render_node(node.operand)}%)"
    if isinstance(node, BinaryNode):
        return (
            f"({_render_node(node.left)}{node.operator}"
            f"{_render_node(node.right)})"
        )
    if isinstance(node, ReferenceOperatorNode):
        separator = " " if node.operator == " " else ","
        return f"({_render_node(node.left)}{separator}{_render_node(node.right)})"
    if isinstance(node, FunctionNode):
        arguments = ",".join(_render_node(item) for item in node.arguments)
        return f"{node.name}({arguments})"
    if isinstance(node, ArrayNode):
        rows = ";".join(
            ",".join(_render_node(item) for item in row) for row in node.rows
        )
        return "{" + rows + "}"
    raise TypeError(f"Cannot render formula node: {type(node).__name__}")
