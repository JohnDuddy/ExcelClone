"""Formula lexer with source-positioned syntax errors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class FormulaSyntaxError(ValueError):
    """A formula syntax failure tied to a source character position."""

    def __init__(self, message: str, position: int) -> None:
        self.position = position
        super().__init__(f"{message} at position {position}")


class TokenKind(Enum):
    """Formula lexical token categories."""

    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    ERROR = auto()
    CELL = auto()
    IDENTIFIER = auto()
    QUOTED_NAME = auto()
    SPACE = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    CARET = auto()
    PERCENT = auto()
    AMPERSAND = auto()
    EQUAL = auto()
    NOT_EQUAL = auto()
    LESS = auto()
    GREATER = auto()
    LESS_EQUAL = auto()
    GREATER_EQUAL = auto()
    COLON = auto()
    COMMA = auto()
    SEMICOLON = auto()
    BANG = auto()
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    LEFT_BRACE = auto()
    RIGHT_BRACE = auto()
    AT = auto()
    HASH = auto()
    STRUCTURED = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class Token:
    """One formula token."""

    kind: TokenKind
    value: Any
    position: int


_NUMBER_RE = re.compile(
    r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?"
)
_CELL_RE = re.compile(r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]*")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_\\][A-Za-z0-9_.\\]*")
_ERROR_LITERALS = (
    "#GETTING_DATA",
    "#BLOCKED!",
    "#CONNECT!",
    "#UNKNOWN!",
    "#FIELD!",
    "#CALC!",
    "#SPILL!",
    "#DIV/0!",
    "#VALUE!",
    "#REF!",
    "#NAME?",
    "#NUM!",
    "#NULL!",
    "#CIRC!",
    "#N/A",
)
_TWO_CHARACTER_OPERATORS = {
    "<>": TokenKind.NOT_EQUAL,
    "<=": TokenKind.LESS_EQUAL,
    ">=": TokenKind.GREATER_EQUAL,
}
_ONE_CHARACTER_TOKENS = {
    "+": TokenKind.PLUS,
    "-": TokenKind.MINUS,
    "*": TokenKind.STAR,
    "/": TokenKind.SLASH,
    "^": TokenKind.CARET,
    "%": TokenKind.PERCENT,
    "&": TokenKind.AMPERSAND,
    "=": TokenKind.EQUAL,
    "<": TokenKind.LESS,
    ">": TokenKind.GREATER,
    ":": TokenKind.COLON,
    ",": TokenKind.COMMA,
    ";": TokenKind.SEMICOLON,
    "!": TokenKind.BANG,
    "(": TokenKind.LEFT_PAREN,
    ")": TokenKind.RIGHT_PAREN,
    "{": TokenKind.LEFT_BRACE,
    "}": TokenKind.RIGHT_BRACE,
    "@": TokenKind.AT,
}


def tokenize(formula: str) -> list[Token]:
    """Tokenize a formula, accepting an optional leading equals sign."""
    offset = 1 if formula.startswith("=") else 0
    source = formula[offset:]
    raw_tokens: list[Token] = []
    position = 0

    while position < len(source):
        character = source[position]
        absolute_position = position + offset

        if character.isspace():
            start = position
            while position < len(source) and source[position].isspace():
                position += 1
            raw_tokens.append(Token(TokenKind.SPACE, " ", start + offset))
            continue

        if character == '"':
            value, position = _read_double_quoted_string(
                source,
                position,
                offset=offset,
            )
            raw_tokens.append(Token(TokenKind.STRING, value, absolute_position))
            continue

        if character == "'":
            value, position = _read_quoted_name(source, position, offset=offset)
            raw_tokens.append(Token(TokenKind.QUOTED_NAME, value, absolute_position))
            continue

        if character == "#":
            literal = next(
                (
                    candidate
                    for candidate in _ERROR_LITERALS
                    if source[position : position + len(candidate)].upper()
                    == candidate
                ),
                None,
            )
            if literal is None:
                if raw_tokens and raw_tokens[-1].kind in (
                    TokenKind.CELL,
                    TokenKind.IDENTIFIER,
                    TokenKind.RIGHT_PAREN,
                ):
                    raw_tokens.append(Token(TokenKind.HASH, "#", absolute_position))
                    position += 1
                    continue
                raise FormulaSyntaxError("Unknown error literal", absolute_position)
            raw_tokens.append(Token(TokenKind.ERROR, literal, absolute_position))
            position += len(literal)
            continue

        if character == "[":
            # Structured reference: Table1[...] or a bare [...] inside a table.
            inner, position = _read_brackets(source, position, offset=offset)
            table = None
            if (
                raw_tokens
                and raw_tokens[-1].kind is TokenKind.IDENTIFIER
                and raw_tokens[-1].position + len(str(raw_tokens[-1].value)) == absolute_position
            ):
                table = str(raw_tokens.pop().value)
                absolute_position -= len(table)
            raw_tokens.append(Token(TokenKind.STRUCTURED, (table, inner), absolute_position))
            continue

        two_character = source[position : position + 2]
        if two_character in _TWO_CHARACTER_OPERATORS:
            raw_tokens.append(
                Token(
                    _TWO_CHARACTER_OPERATORS[two_character],
                    two_character,
                    absolute_position,
                )
            )
            position += 2
            continue

        token_kind = _ONE_CHARACTER_TOKENS.get(character)
        if token_kind is not None:
            raw_tokens.append(Token(token_kind, character, absolute_position))
            position += 1
            continue

        cell_match = _CELL_RE.match(source, position)
        if cell_match and _is_lexeme_boundary(source, cell_match.end()):
            value = cell_match.group(0)
            kind = (
                TokenKind.IDENTIFIER
                if cell_match.end() < len(source)
                and source[cell_match.end()] == "("
                and "$" not in value
                else TokenKind.CELL
            )
            raw_tokens.append(Token(kind, value, absolute_position))
            position = cell_match.end()
            continue

        number_match = _NUMBER_RE.match(source, position)
        if number_match:
            lexeme = number_match.group(0)
            value = (
                float(lexeme)
                if "." in lexeme or "e" in lexeme.casefold()
                else int(lexeme)
            )
            raw_tokens.append(Token(TokenKind.NUMBER, value, absolute_position))
            position = number_match.end()
            continue

        identifier_match = _IDENTIFIER_RE.match(source, position)
        if identifier_match:
            value = identifier_match.group(0)
            upper_value = value.upper()
            if upper_value == "TRUE":
                raw_tokens.append(Token(TokenKind.BOOLEAN, True, absolute_position))
            elif upper_value == "FALSE":
                raw_tokens.append(Token(TokenKind.BOOLEAN, False, absolute_position))
            else:
                raw_tokens.append(
                    Token(TokenKind.IDENTIFIER, value, absolute_position)
                )
            position = identifier_match.end()
            continue

        raise FormulaSyntaxError(
            f"Unexpected character {character!r}",
            absolute_position,
        )

    tokens = _filter_spaces(raw_tokens)
    tokens.append(Token(TokenKind.EOF, None, len(formula)))
    return tokens


def _read_double_quoted_string(
    source: str,
    start: int,
    *,
    offset: int,
) -> tuple[str, int]:
    position = start + 1
    characters: list[str] = []
    while position < len(source):
        if source[position] == '"':
            if position + 1 < len(source) and source[position + 1] == '"':
                characters.append('"')
                position += 2
                continue
            return "".join(characters), position + 1
        characters.append(source[position])
        position += 1
    raise FormulaSyntaxError("Unterminated string literal", start + offset)


def _read_quoted_name(
    source: str,
    start: int,
    *,
    offset: int,
) -> tuple[str, int]:
    position = start + 1
    characters: list[str] = []
    while position < len(source):
        if source[position] == "'":
            if position + 1 < len(source) and source[position + 1] == "'":
                characters.append("'")
                position += 2
                continue
            return "".join(characters), position + 1
        characters.append(source[position])
        position += 1
    raise FormulaSyntaxError("Unterminated quoted name", start + offset)


def _read_brackets(source: str, start: int, *, offset: int) -> tuple[str, int]:
    """Read a balanced [...] group (with ' escapes); return (inside, end)."""
    depth = 0
    position = start
    while position < len(source):
        character = source[position]
        if character == "'" and position + 1 < len(source):
            position += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return source[start + 1 : position], position + 1
        position += 1
    raise FormulaSyntaxError("Unterminated structured reference", start + offset)


def _is_lexeme_boundary(source: str, position: int) -> bool:
    return position >= len(source) or not (
        source[position].isalnum() or source[position] in "_.\\"
    )


def _filter_spaces(tokens: list[Token]) -> list[Token]:
    filtered: list[Token] = []
    for index, token in enumerate(tokens):
        if token.kind is not TokenKind.SPACE:
            filtered.append(token)
            continue
        previous = _neighbor(tokens, index, direction=-1)
        following = _neighbor(tokens, index, direction=1)
        if (
            previous is not None
            and following is not None
            and _can_end_reference(previous.kind)
            and _can_start_reference(following.kind)
        ):
            filtered.append(token)
    return filtered


def _neighbor(tokens: list[Token], index: int, *, direction: int) -> Token | None:
    position = index + direction
    while 0 <= position < len(tokens):
        if tokens[position].kind is not TokenKind.SPACE:
            return tokens[position]
        position += direction
    return None


def _can_end_reference(kind: TokenKind) -> bool:
    return kind in {
        TokenKind.STRUCTURED,
        TokenKind.CELL,
        TokenKind.IDENTIFIER,
        TokenKind.NUMBER,
        TokenKind.RIGHT_PAREN,
    }


def _can_start_reference(kind: TokenKind) -> bool:
    return kind in {
        TokenKind.STRUCTURED,
        TokenKind.CELL,
        TokenKind.IDENTIFIER,
        TokenKind.QUOTED_NAME,
        TokenKind.NUMBER,
        TokenKind.LEFT_PAREN,
    }
