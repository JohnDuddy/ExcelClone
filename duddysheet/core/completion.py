"""Partial function-name matching for formula editors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duddysheet.core.functions import FUNCTION_REGISTRY, FunctionSpec

# Mirrors the identifier shape accepted by the tokenizer so completion and
# lexing agree on where a function name starts and ends.
_NAME_BODY = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.")
_NAME_HEAD = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")

# A name directly after either character belongs to a reference, not a call.
_REFERENCE_PREFIXES = frozenset("$!")


@dataclass(frozen=True, slots=True)
class FunctionPrefix:
    """A partial function name being typed, and where it sits in the source."""

    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ActiveCall:
    """The innermost registered function call surrounding a cursor."""

    spec: FunctionSpec
    argument_index: int

    @property
    def name(self) -> str:
        """Return the called function name."""
        return self.spec.name

    @property
    def fields(self) -> tuple[str, ...]:
        """Return the declared argument names for the call."""
        return argument_fields(self.spec)

    @property
    def active_field(self) -> int:
        """Return the field index to emphasize, clamped onto the declared list."""
        fields = self.fields
        if not fields:
            return -1
        return min(self.argument_index, len(fields) - 1)


def argument_fields(spec: FunctionSpec) -> tuple[str, ...]:
    """Split a registered argument specification into individual field names."""
    return tuple(
        field.strip() for field in spec.argument_spec.split(",") if field.strip()
    )


def active_call_at(text: str, cursor: int) -> ActiveCall | None:
    """Return the function call being filled in at a cursor position, if any."""
    if not text.startswith("=") or not 0 <= cursor <= len(text):
        return None
    calls: list[list[Any]] = []
    braces = 0
    in_string = False
    index = 1
    while index < cursor:
        char = text[index]
        if in_string:
            if char == '"':
                if index + 1 < cursor and text[index + 1] == '"':
                    index += 2
                    continue
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            braces += 1
        elif char == "}":
            braces = max(0, braces - 1)
        elif braces == 0:
            if char == "(":
                calls.append([_name_before(text, index), 0])
            elif char == ")":
                if calls:
                    calls.pop()
            elif char == "," and calls:
                calls[-1][1] += 1
        index += 1
    for name, argument_index in reversed(calls):
        spec = FUNCTION_REGISTRY.get(name) if name else None
        if spec is not None:
            return ActiveCall(spec=spec, argument_index=argument_index)
    return None


def _name_before(text: str, paren: int) -> str:
    """Return the uppercased identifier immediately preceding an open paren."""
    start = paren
    while start > 0 and text[start - 1] in _NAME_BODY:
        start -= 1
    if start == paren or text[start] not in _NAME_HEAD:
        return ""
    return text[start:paren].upper()


def function_prefix_at(text: str, cursor: int) -> FunctionPrefix | None:
    """Return the function name being typed at a cursor position, if any."""
    if not text.startswith("="):
        return None
    if not 0 <= cursor <= len(text):
        return None
    if _inside_string_literal(text, cursor):
        return None
    start = cursor
    while start > 0 and text[start - 1] in _NAME_BODY:
        start -= 1
    if start == cursor or text[start] not in _NAME_HEAD:
        return None
    if start > 0 and text[start - 1] in _REFERENCE_PREFIXES:
        return None
    return FunctionPrefix(text=text[start:cursor].upper(), start=start, end=cursor)


def find_functions(prefix: str) -> tuple[FunctionSpec, ...]:
    """Return registered functions whose names start with a prefix, name-ordered."""
    folded = prefix.strip().upper()
    return tuple(
        spec
        for name, spec in sorted(FUNCTION_REGISTRY.items())
        if name.startswith(folded)
    )


def _inside_string_literal(text: str, cursor: int) -> bool:
    """Report whether a cursor sits inside an unterminated quoted string."""
    quotes = 0
    index = 0
    while index < cursor:
        if text[index] == '"':
            if index + 1 < cursor and text[index + 1] == '"':
                index += 2
                continue
            quotes += 1
        index += 1
    return quotes % 2 == 1
