from __future__ import annotations

from datetime import date, datetime

import pytest

from excelclone.core.formats import format_value


@pytest.mark.parametrize(
    ("value", "format_code", "text", "color"),
    [
        (None, "General", "", None),
        (True, "General", "TRUE", None),
        (1234, "General", "1234", None),
        (1.25, "General", "1.25", None),
        (1234.5, "Number", "1,234.50", None),
        (-1234.5, "Number", "-1,234.50", None),
        (1234.5, "Currency", "$1,234.50", None),
        (-1234.5, "Currency", "-$1,234.50", None),
        (1234.5, "Accounting", "$ 1,234.50", None),
        (0.125, "Percentage", "12.50%", None),
        (0.333333, "Fraction", "1/3", None),
        (1234, "Scientific", "1.23E+03", None),
        (1, "m/d/yyyy", "1/1/1900", None),
        (59, "m/d/yyyy", "2/28/1900", None),
        (60, "m/d/yyyy", "2/29/1900", None),
        (61, "m/d/yyyy", "3/1/1900", None),
        (0.5, "h:mm AM/PM", "12:00 PM", None),
        (0.5625, "hh:mm:ss", "13:30:00", None),
        (123, "Text", "123", None),
        (12.3, "0.00", "12.30", None),
        (12.3, "#,##0.0", "12.3", None),
        (0.125, "0.0%", "12.5%", None),
        (-12.3, "0.00;[Red](0.00);-", "(12.30)", "red"),
        (0, "0.00;[Red](0.00);-", "-", None),
        ("hello", '0.00;[Red](0.00);-;"Text: "@', "Text: hello", None),
        (12, '"USD "0.00', "USD 12.00", None),
        (1_200_000, "0.0,,", "1.2", None),
        ("#DIV/0!", "0.00", "#DIV/0!", None),
    ],
)
def test_number_formats(
    value: object,
    format_code: str,
    text: str,
    color: str | None,
) -> None:
    formatted = format_value(value, format_code)

    assert formatted.text == text
    assert formatted.color == color


@pytest.mark.parametrize(
    ("value", "format_code", "expected"),
    [
        (1.2, "0", "1"),
        (1.6, "0", "2"),
        (0.5, ".00", ".50"),
        (12, "00000", "00012"),
        (12.5, "???.??", " 12.5 "),
        (-5, "0;[Red]-0", "-5"),
        (0, "0;[Red]-0;Zero", "Zero"),
        ("abc", "@", "abc"),
    ],
)
def test_custom_placeholder_formats(
    value: object,
    format_code: str,
    expected: str,
) -> None:
    assert format_value(value, format_code).text == expected


@pytest.mark.parametrize(
    ("value", "format_code", "expected"),
    [
        ("word", "Fraction", "word"),
        (-1.5, "Fraction", "-1 1/2"),
        ("word", "Scientific", "word"),
        ("word", "Accounting", "word"),
        (0, "Accounting", "$ -"),
        (-12, "Accounting", "($ 12.00)"),
        (datetime(2024, 5, 6, 7, 8, 9), "General", "2024-05-06 07:08:09"),
        (date(2024, 5, 6), "General", "2024-05-06"),
        (date(2024, 5, 6), "yyyy-mm-dd", "2024-05-06"),
        ("word", "yyyy-mm-dd", "word"),
        ("abc", '"fixed"', "abc"),
        (object(), "0.00", "<object>"),
        (7, r'\$0', "$7"),
        (0, "#.##", ""),
        (60, "yyyy-mm-dd", "1900-02-29"),
        (60, "mm/dd/yyyy", "02/29/1900"),
        (60, "mm/dd/yy", "02/29/00"),
        (60, "d-mmm-yy", "29-Feb-00"),
        (2, "ddd", "1/2/1900"),
        (0.5, "hh custom", "12:00:00"),
    ],
)
def test_number_format_edge_paths(
    value: object,
    format_code: str,
    expected: str,
) -> None:
    result = format_value(value, format_code).text
    if expected == "<object>":
        assert result.startswith("<object object at ")
    else:
        assert result == expected
