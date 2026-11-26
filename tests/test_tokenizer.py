from __future__ import annotations

import pytest

from duddysheet.core.tokenizer import FormulaSyntaxError, TokenKind, tokenize


@pytest.mark.parametrize(
    ("formula", "kinds", "values"),
    [
        (
            "=SUM(A1:A10)*1.08",
            [
                TokenKind.IDENTIFIER,
                TokenKind.LEFT_PAREN,
                TokenKind.CELL,
                TokenKind.COLON,
                TokenKind.CELL,
                TokenKind.RIGHT_PAREN,
                TokenKind.STAR,
                TokenKind.NUMBER,
                TokenKind.EOF,
            ],
            ["SUM", "(", "A1", ":", "A10", ")", "*", 1.08, None],
        ),
        (
            '="He said ""Hi"""&TRUE',
            [
                TokenKind.STRING,
                TokenKind.AMPERSAND,
                TokenKind.BOOLEAN,
                TokenKind.EOF,
            ],
            ['He said "Hi"', "&", True, None],
        ),
        (
            "=-1.25E-3+50%",
            [
                TokenKind.MINUS,
                TokenKind.NUMBER,
                TokenKind.PLUS,
                TokenKind.NUMBER,
                TokenKind.PERCENT,
                TokenKind.EOF,
            ],
            ["-", 1.25e-3, "+", 50, "%", None],
        ),
        (
            "='My Sheet'!$A$1<>#N/A",
            [
                TokenKind.QUOTED_NAME,
                TokenKind.BANG,
                TokenKind.CELL,
                TokenKind.NOT_EQUAL,
                TokenKind.ERROR,
                TokenKind.EOF,
            ],
            ["My Sheet", "!", "$A$1", "<>", "#N/A", None],
        ),
        (
            "={1,2;3,4}",
            [
                TokenKind.LEFT_BRACE,
                TokenKind.NUMBER,
                TokenKind.COMMA,
                TokenKind.NUMBER,
                TokenKind.SEMICOLON,
                TokenKind.NUMBER,
                TokenKind.COMMA,
                TokenKind.NUMBER,
                TokenKind.RIGHT_BRACE,
                TokenKind.EOF,
            ],
            ["{", 1, ",", 2, ";", 3, ",", 4, "}", None],
        ),
        (
            "=A1 B2",
            [TokenKind.CELL, TokenKind.SPACE, TokenKind.CELL, TokenKind.EOF],
            ["A1", " ", "B2", None],
        ),
    ],
)
def test_tokenize_formula(
    formula: str,
    kinds: list[TokenKind],
    values: list[object],
) -> None:
    tokens = tokenize(formula)

    assert [token.kind for token in tokens] == kinds
    assert [token.value for token in tokens] == values


@pytest.mark.parametrize(
    ("operator", "kind"),
    [
        ("+", TokenKind.PLUS),
        ("-", TokenKind.MINUS),
        ("*", TokenKind.STAR),
        ("/", TokenKind.SLASH),
        ("^", TokenKind.CARET),
        ("&", TokenKind.AMPERSAND),
        ("<>", TokenKind.NOT_EQUAL),
        ("<", TokenKind.LESS),
        (">", TokenKind.GREATER),
        ("<=", TokenKind.LESS_EQUAL),
        (">=", TokenKind.GREATER_EQUAL),
    ],
)
def test_tokenize_operators(operator: str, kind: TokenKind) -> None:
    tokens = tokenize(operator)
    assert [token.kind for token in tokens] == [kind, TokenKind.EOF]


def test_equality_operator_is_distinct_from_formula_prefix() -> None:
    tokens = tokenize("=1=1")

    assert [token.kind for token in tokens] == [
        TokenKind.NUMBER,
        TokenKind.EQUAL,
        TokenKind.NUMBER,
        TokenKind.EOF,
    ]


@pytest.mark.parametrize(
    "formula",
    [
        '="unterminated',
        "='unterminated!A1",
        "=1+€",
        "=#BOGUS!",
    ],
)
def test_invalid_lexemes_report_source_position(formula: str) -> None:
    with pytest.raises(FormulaSyntaxError) as error:
        tokenize(formula)

    assert error.value.position >= 0
    assert "position" in str(error.value)


def test_spaces_around_arithmetic_are_not_intersection_tokens() -> None:
    tokens = tokenize("= A1 + B2 ")

    assert [token.kind for token in tokens] == [
        TokenKind.CELL,
        TokenKind.PLUS,
        TokenKind.CELL,
        TokenKind.EOF,
    ]
