"""Flash Fill: infer a text transformation from examples and apply it to a column.

Programs are concatenations of constant text and pieces of the source
columns: whole values, words counted from either end (optionally upper-,
lower-, proper-cased, or reduced to an initial), or character slices. The
first program consistent with every example is used.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_TRANSFORMS = ("none", "upper", "lower", "proper", "initial", "initial_lower")


@dataclass(frozen=True, slots=True)
class Piece:
    """One output piece: constant text or a transformed part of a source value."""

    kind: str  # "const", "word", "slice", "whole"
    text: str = ""
    source: int = 0
    index: int = 0
    end: int = 0
    transform: str = "none"


def _words(value: str) -> list[str]:
    return _WORD_RE.findall(value)


def _transform(text: str, transform: str) -> str:
    if transform == "upper":
        return text.upper()
    if transform == "lower":
        return text.lower()
    if transform == "proper":
        return text[:1].upper() + text[1:].lower()
    if transform == "initial":
        return text[:1].upper()
    if transform == "initial_lower":
        return text[:1].lower()
    return text


def _render(piece: Piece, sources: list[str]) -> str | None:
    if piece.kind == "const":
        return piece.text
    if piece.source >= len(sources):
        return None
    value = sources[piece.source]
    if piece.kind == "whole":
        return _transform(value, piece.transform)
    if piece.kind == "word":
        words = _words(value)
        if not -len(words) <= piece.index < len(words):
            return None
        return _transform(words[piece.index], piece.transform)
    if piece.kind == "slice":
        start = piece.index if piece.index >= 0 else len(value) + piece.index
        end = piece.end if piece.end > 0 else len(value) + piece.end
        if not 0 <= start < end <= len(value):
            return None
        return _transform(value[start:end], piece.transform)
    return None


def apply_program(program: tuple[Piece, ...], sources: list[str]) -> str | None:
    """Render a program for one row of source values."""
    parts: list[str] = []
    for piece in program:
        rendered = _render(piece, sources)
        if rendered is None:
            return None
        parts.append(rendered)
    return "".join(parts)


def _candidates(sources: list[str], output: str, position: int) -> list[tuple[Piece, int]]:
    """Pieces that can produce output[position:], longest matches first."""
    found: list[tuple[Piece, int]] = []
    remaining = output[position:]
    for source_index, value in enumerate(sources):
        if not value:
            continue
        for transform in ("none", "upper", "lower", "proper"):
            text = _transform(value, transform)
            if text and remaining.startswith(text):
                found.append((Piece("whole", source=source_index, transform=transform), len(text)))
        words = _words(value)
        for word_index, word in enumerate(words):
            for transform in _TRANSFORMS:
                text = _transform(word, transform)
                if text and remaining.startswith(text):
                    for index in (word_index, word_index - len(words)):
                        found.append((Piece("word", source=source_index, index=index, transform=transform), len(text)))
        if len(words) <= 1:
            for start in range(len(value)):
                for end in range(len(value), start, -1):
                    text = value[start:end]
                    if len(text) >= 2 and remaining.startswith(text):
                        found.append((Piece("slice", source=source_index, index=start, end=end), len(text)))
                        break
    def preference(item: tuple[Piece, int]) -> tuple[int, int, int, int]:
        piece, length = item
        edge_word = piece.kind == "word" and piece.index in (0, -1)
        return (-length, piece.kind != "word", not edge_word, piece.kind == "slice")

    found.sort(key=preference)
    return found


def _programs(sources: list[str], output: str, limit: int = 400) -> list[tuple[Piece, ...]]:
    """Enumerate programs that produce one example, preferring fewer pieces."""
    results: list[tuple[Piece, ...]] = []

    def search(position: int, pieces: tuple[Piece, ...]) -> None:
        if len(results) >= limit:
            return
        if position == len(output):
            results.append(pieces)
            return
        for piece, length in _candidates(sources, output, position)[:12]:
            search(position + length, pieces + (piece,))
        character = output[position]
        if pieces and pieces[-1].kind == "const":
            merged = Piece("const", text=pieces[-1].text + character)
            search(position + 1, pieces[:-1] + (merged,))
        else:
            search(position + 1, pieces + (Piece("const", text=character),))

    search(0, ())
    def cost(program: tuple[Piece, ...]) -> tuple[int, int, int]:
        constant_characters = sum(len(piece.text) for piece in program if piece.kind == "const")
        middle_words = sum(
            piece.kind == "word" and piece.index not in (0, -1) for piece in program
        )
        return (constant_characters, middle_words, len(program))

    results.sort(key=cost)
    return results


def infer_program(examples: list[tuple[list[str], str]]) -> tuple[Piece, ...] | None:
    """Return the simplest program consistent with every (sources, output) example."""
    if not examples:
        return None
    first_sources, first_output = examples[0]
    for program in _programs(first_sources, first_output):
        if all(apply_program(program, sources) == output for sources, output in examples[1:]):
            if all(piece.kind == "const" for piece in program) and len(examples) == 1 and any(first_sources):
                continue
            return program
    return None


def flash_fill(
    sheet: Any,
    column: int,
    first_row: int,
    last_row: int,
    source_columns: list[int],
) -> dict[int, str] | None:
    """Return row -> value to fill in ``column`` from examples already typed there."""

    def text(row: int, source: int) -> str:
        value = sheet.get_cell(row, source).display_value
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    examples: list[tuple[list[str], str]] = []
    blanks: list[int] = []
    for row in range(first_row, last_row + 1):
        sources = [text(row, source) for source in source_columns]
        target = sheet.get_cell(row, column).display_value
        if target not in (None, ""):
            examples.append((sources, str(target)))
        elif any(sources):
            blanks.append(row)
    program = infer_program(examples)
    if program is None:
        return None
    filled: dict[int, str] = {}
    for row in blanks:
        rendered = apply_program(program, [text(row, source) for source in source_columns])
        if rendered is not None:
            filled[row] = rendered
    return filled
