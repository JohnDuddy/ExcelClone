"""Recursive-descent formula parser and immutable AST values."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from excelclone.core.errors import SpreadsheetError, error_from_literal
from excelclone.core.refs import (
    CellReference,
    RangeReference,
    Reference,
    column_to_index,
    parse_a1,
)
from excelclone.core.tokenizer import (
    FormulaSyntaxError,
    Token,
    TokenKind,
    tokenize,
)


class Node:
    """Marker base class for formula AST values."""


@dataclass(frozen=True, slots=True)
class LiteralNode(Node):
    value: Any


@dataclass(frozen=True, slots=True)
class ErrorNode(Node):
    error: SpreadsheetError


@dataclass(frozen=True, slots=True)
class ReferenceNode(Node):
    reference: Reference


@dataclass(frozen=True, slots=True)
class NameNode(Node):
    name: str
    sheet: str | None = None


@dataclass(frozen=True, slots=True)
class UnaryNode(Node):
    operator: str
    operand: Node


@dataclass(frozen=True, slots=True)
class PercentNode(Node):
    operand: Node


@dataclass(frozen=True, slots=True)
class BinaryNode(Node):
    operator: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class ReferenceOperatorNode(Node):
    operator: str
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class FunctionNode(Node):
    name: str
    arguments: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class ArrayNode(Node):
    rows: tuple[tuple[Node, ...], ...]


_COMPARISON_OPERATORS = {
    TokenKind.EQUAL: "=",
    TokenKind.NOT_EQUAL: "<>",
    TokenKind.LESS: "<",
    TokenKind.GREATER: ">",
    TokenKind.LESS_EQUAL: "<=",
    TokenKind.GREATER_EQUAL: ">=",
}
_INVALID_A1_LIKE_NAME_RE = re.compile(r"^[A-Za-z]{1,3}[0-9]+$")


def parse_formula(formula: str) -> Node:
    """Parse a formula string into an immutable AST."""
    return _Parser(tokenize(formula)).parse()


def collect_references(node: Node) -> tuple[Reference | str, ...]:
    """Collect referenced cells, ranges, and defined names in source order."""
    collected: list[Reference | str] = []

    def visit(current: Node) -> None:
        if isinstance(current, ReferenceNode):
            collected.append(current.reference)
        elif isinstance(current, NameNode):
            name = (
                f"{current.sheet}!{current.name}"
                if current.sheet is not None
                else current.name
            )
            collected.append(name)
        elif isinstance(current, (UnaryNode, PercentNode)):
            visit(current.operand)
        elif isinstance(current, (BinaryNode, ReferenceOperatorNode)):
            visit(current.left)
            visit(current.right)
        elif isinstance(current, FunctionNode):
            for argument in current.arguments:
                visit(argument)
        elif isinstance(current, ArrayNode):
            for row in current.rows:
                for item in row:
                    visit(item)

    visit(node)
    return tuple(dict.fromkeys(collected))


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse(self) -> Node:
        if self.current.kind is TokenKind.EOF:
            raise FormulaSyntaxError("Formula cannot be empty", self.current.position)
        expression = self._comparison(allow_union=True)
        self._expect(TokenKind.EOF, "Unexpected token")
        return expression

    @property
    def current(self) -> Token:
        return self.tokens[self.position]

    def _peek(self, distance: int = 1) -> Token:
        index = min(self.position + distance, len(self.tokens) - 1)
        return self.tokens[index]

    def _advance(self) -> Token:
        token = self.current
        if token.kind is not TokenKind.EOF:
            self.position += 1
        return token

    def _match(self, *kinds: TokenKind) -> Token | None:
        if self.current.kind in kinds:
            return self._advance()
        return None

    def _expect(self, kind: TokenKind, message: str) -> Token:
        if self.current.kind is not kind:
            raise FormulaSyntaxError(message, self.current.position)
        return self._advance()

    def _comparison(self, *, allow_union: bool) -> Node:
        node = self._concatenation(allow_union=allow_union)
        while self.current.kind in _COMPARISON_OPERATORS:
            operator = _COMPARISON_OPERATORS[self._advance().kind]
            node = BinaryNode(
                operator,
                node,
                self._concatenation(allow_union=allow_union),
            )
        return node

    def _concatenation(self, *, allow_union: bool) -> Node:
        node = self._additive(allow_union=allow_union)
        while self._match(TokenKind.AMPERSAND):
            node = BinaryNode(
                "&",
                node,
                self._additive(allow_union=allow_union),
            )
        return node

    def _additive(self, *, allow_union: bool) -> Node:
        node = self._multiplicative(allow_union=allow_union)
        while self.current.kind in (TokenKind.PLUS, TokenKind.MINUS):
            operator = self._advance().value
            node = BinaryNode(
                operator,
                node,
                self._multiplicative(allow_union=allow_union),
            )
        return node

    def _multiplicative(self, *, allow_union: bool) -> Node:
        node = self._power(allow_union=allow_union)
        while self.current.kind in (TokenKind.STAR, TokenKind.SLASH):
            operator = self._advance().value
            node = BinaryNode(
                operator,
                node,
                self._power(allow_union=allow_union),
            )
        return node

    def _power(self, *, allow_union: bool) -> Node:
        node = self._percent(allow_union=allow_union)
        while self._match(TokenKind.CARET):
            node = BinaryNode(
                "^",
                node,
                self._percent(allow_union=allow_union),
            )
        return node

    def _percent(self, *, allow_union: bool) -> Node:
        node = self._unary(allow_union=allow_union)
        while self._match(TokenKind.PERCENT):
            node = PercentNode(node)
        return node

    def _unary(self, *, allow_union: bool) -> Node:
        operator = self._match(TokenKind.PLUS, TokenKind.MINUS)
        if operator is not None:
            return UnaryNode(
                operator.value,
                self._unary(allow_union=allow_union),
            )
        if allow_union:
            return self._union()
        return self._intersection()

    def _union(self) -> Node:
        node = self._intersection()
        while self._match(TokenKind.COMMA):
            node = ReferenceOperatorNode(",", node, self._intersection())
        return node

    def _intersection(self) -> Node:
        node = self._range()
        while self._match(TokenKind.SPACE):
            right = self._range()
            if not _is_reference_expression(node) or not _is_reference_expression(right):
                raise FormulaSyntaxError(
                    "Intersection operands must be references",
                    self.current.position,
                )
            node = ReferenceOperatorNode(" ", node, right)
        return node

    def _range(self) -> Node:
        node = self._primary()
        while self._match(TokenKind.COLON):
            right = self._primary()
            node = _combine_range(node, right, position=self.current.position)
        return node

    def _primary(self) -> Node:
        token = self.current
        if token.kind is TokenKind.NUMBER:
            self._advance()
            return LiteralNode(token.value)
        if token.kind is TokenKind.STRING:
            self._advance()
            return LiteralNode(token.value)
        if token.kind is TokenKind.BOOLEAN:
            self._advance()
            return LiteralNode(token.value)
        if token.kind is TokenKind.ERROR:
            self._advance()
            return ErrorNode(error_from_literal(token.value))
        if token.kind is TokenKind.CELL:
            self._advance()
            try:
                return ReferenceNode(parse_a1(token.value))
            except ValueError as error:
                raise FormulaSyntaxError(str(error), token.position) from None
        if token.kind in (TokenKind.IDENTIFIER, TokenKind.QUOTED_NAME):
            return self._name_or_function()
        if self._match(TokenKind.LEFT_PAREN):
            expression = self._comparison(allow_union=True)
            self._expect(TokenKind.RIGHT_PAREN, "Expected closing parenthesis")
            return expression
        if self._match(TokenKind.LEFT_BRACE):
            return self._array()
        raise FormulaSyntaxError("Expected expression", token.position)

    def _name_or_function(self) -> Node:
        token = self._advance()
        name = str(token.value)
        if self._match(TokenKind.BANG):
            reference = self._primary()
            return _apply_sheet(reference, name, position=token.position)
        if token.kind is TokenKind.QUOTED_NAME:
            raise FormulaSyntaxError(
                "Quoted sheet name must be followed by !",
                token.position,
            )
        if self._match(TokenKind.LEFT_PAREN):
            arguments: list[Node] = []
            if self.current.kind is TokenKind.RIGHT_PAREN:
                self._advance()
                return FunctionNode(name.upper(), ())
            while True:
                arguments.append(self._comparison(allow_union=False))
                if self._match(TokenKind.COMMA):
                    if self.current.kind is TokenKind.RIGHT_PAREN:
                        raise FormulaSyntaxError(
                            "Missing function argument",
                            self.current.position,
                        )
                    continue
                self._expect(TokenKind.RIGHT_PAREN, "Expected closing parenthesis")
                break
            return FunctionNode(name.upper(), tuple(arguments))
        if _INVALID_A1_LIKE_NAME_RE.fullmatch(name):
            raise FormulaSyntaxError("Invalid cell reference", token.position)
        return NameNode(name)

    def _array(self) -> Node:
        if self.current.kind is TokenKind.RIGHT_BRACE:
            raise FormulaSyntaxError("Array cannot be empty", self.current.position)
        rows: list[tuple[Node, ...]] = []
        row: list[Node] = []
        while True:
            row.append(self._comparison(allow_union=False))
            if self._match(TokenKind.COMMA):
                continue
            rows.append(tuple(row))
            if self._match(TokenKind.SEMICOLON):
                row = []
                continue
            self._expect(TokenKind.RIGHT_BRACE, "Expected closing array brace")
            break
        width = len(rows[0])
        if any(len(items) != width for items in rows):
            raise FormulaSyntaxError("Array rows must have equal length", self.current.position)
        return ArrayNode(tuple(rows))


def _combine_range(left: Node, right: Node, *, position: int) -> ReferenceNode:
    if isinstance(left, ReferenceNode) and isinstance(right, ReferenceNode):
        if not isinstance(left.reference, CellReference) or not isinstance(
            right.reference,
            CellReference,
        ):
            raise FormulaSyntaxError("Range endpoint must be a cell", position)
        start, end = _align_sheets(left.reference, right.reference, position=position)
        return ReferenceNode(RangeReference(start, end))

    if isinstance(left, NameNode) and isinstance(right, NameNode):
        try:
            column_to_index(left.name)
            column_to_index(right.name)
        except ValueError:
            raise FormulaSyntaxError("Invalid range endpoint", position) from None
        sheet = _shared_sheet(left.sheet, right.sheet, position=position)
        prefix = f"'{sheet.replace(chr(39), chr(39) * 2)}'!" if sheet else ""
        try:
            return ReferenceNode(parse_a1(f"{prefix}{left.name}:{right.name}"))
        except ValueError as error:
            raise FormulaSyntaxError(str(error), position) from None

    if (
        isinstance(left, LiteralNode)
        and isinstance(right, LiteralNode)
        and isinstance(left.value, int)
        and not isinstance(left.value, bool)
        and isinstance(right.value, int)
        and not isinstance(right.value, bool)
    ):
        try:
            return ReferenceNode(parse_a1(f"{left.value}:{right.value}"))
        except ValueError as error:
            raise FormulaSyntaxError(str(error), position) from None

    raise FormulaSyntaxError("Invalid range endpoint", position)


def _apply_sheet(node: Node, sheet: str, *, position: int) -> Node:
    if isinstance(node, ReferenceNode):
        reference = node.reference
        if isinstance(reference, CellReference):
            return ReferenceNode(replace(reference, sheet=sheet))
        return ReferenceNode(
            RangeReference(
                replace(reference.start, sheet=sheet),
                replace(reference.end, sheet=sheet),
                whole_row=reference.whole_row,
                whole_column=reference.whole_column,
            )
        )
    if isinstance(node, NameNode):
        return replace(node, sheet=sheet)
    raise FormulaSyntaxError("Sheet qualifier requires a reference", position)


def _align_sheets(
    left: CellReference,
    right: CellReference,
    *,
    position: int,
) -> tuple[CellReference, CellReference]:
    sheet = _shared_sheet(left.sheet, right.sheet, position=position)
    return replace(left, sheet=sheet), replace(right, sheet=sheet)


def _shared_sheet(
    left: str | None,
    right: str | None,
    *,
    position: int,
) -> str | None:
    if left is not None and right is not None and left.casefold() != right.casefold():
        raise FormulaSyntaxError("Range cannot cross sheets", position)
    return left if left is not None else right


def _is_reference_expression(node: Node) -> bool:
    return isinstance(node, (ReferenceNode, NameNode, ReferenceOperatorNode))

