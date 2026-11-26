from __future__ import annotations

from datetime import date, datetime

import pytest

from duddysheet.core.formats import format_value


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
        (0, "#.##", "."),
        (60, "yyyy-mm-dd", "1900-02-29"),
        (60, "mm/dd/yyyy", "02/29/1900"),
        (60, "mm/dd/yy", "02/29/00"),
        (60, "d-mmm-yy", "29-Feb-00"),
        # Excel's 1900 leap-year bug makes 1900-01-02 a Monday.
        (2, "ddd", "Mon"),
        (0.5, 'hh "custom"', "12 custom"),
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


EXCEL_FORMAT_CODES = [
    (1234.567, "#,##0.00", "1,234.57"),
    (1234.567, "$#,##0", "$1,235"),
    (0.256, "0.0%", "25.6%"),
    (-1234.5, "#,##0.00;(#,##0.00)", "(1,234.50)"),
    (0, '0;-0;"zero"', "zero"),
    (46000, "mmm d, yyyy", "Dec 9, 2025"),
    (46000, "dddd", "Tuesday"),
    (46000.75, "h:mm AM/PM", "6:00 PM"),
    (46000.75, "yyyy-mm-dd hh:mm", "2025-12-09 18:00"),
    (1.5, "[h]:mm", "36:00"),
    (0.0001234, "0.00E+00", "1.23E-04"),
    (1.25, "# ?/?", "1 1/4"),
    (0.3333, "# ??/??", "  1/3 "),
    (12, "00000", "00012"),
    (1234567, '#,##0,"K"', "1,235K"),
    (5, "@", "5"),
    ("abc", '@"!"', "abc!"),
    (-5, "[Red]0;[Blue]-0", "-5"),
    (3.14159, "0.###", "3.142"),
    (1234.5, "#,##0.00_);(#,##0.00)", "1,234.50 "),
    (0.5, "0%", "50%"),
    (1234, "0.00E+0", "1.23E+3"),
    (46000, "mm/dd/yy", "12/09/25"),
    (46000, "d-mmm", "9-Dec"),
    (46000, "mmmm", "December"),
    (46000, "ddd", "Tue"),
    (0.5, "h:mm:ss", "12:00:00"),
    (1.75, "[mm]:ss", "2520:00"),
    (46000, "[$-409]mmmm d, yyyy", "December 9, 2025"),
    (1000, '[>999]#,##0,"K";0', "1K"),
    (123.456, "?.??", "123.46"),
    (12345678, '0.0,,"M"', "12.3M"),
    (123456789, "000-00-0000", "123-45-6789"),
    (2.675, "0.00", "2.68"),
    (5, "#,##0", "5"),
    (1234, "0,000", "1,234"),
    (5, "0,000", "0,005"),
    (0, "#.##", "."),
    (1.0, "# ?/?", "1    "),
    (0.25, "# ?/?", " 1/4"),
    (2.5, "?/8", "20/8"),
    (0.5, "# ?/8", " 4/8"),
    (-0.001, "0.00", "0.00"),
    (12345.678, "##0.0E+0", "12.3E+3"),
    (1e-10, "0.00E+00", "1.00E-10"),
    (46000.5, "dd/mm/yyyy hh:mm:ss", "09/12/2025 12:00:00"),
    (0.5004, "hh:mm:ss.00", "12:00:34.56"),
    (46000, "yy", "25"),
    (46000, "mmmmm", "D"),
    (0.25, "h AM/PM", "6 AM"),
    (0.75, "h:mm a/p", "6:00 p"),
    (-5, "0.0;-0.0", "-5.0"),
    (-5, "0.0;(0.0)", "(5.0)"),
    (5, '"+"0;"-"0', "+5"),
    (-1234.5, "$#,##0.00", "-$1,234.50"),
    (1234.5, "[$€-407] #,##0.00", "€ 1,234.50"),
    (0.123, "0.0%;-0.0%", "12.3%"),
    (1 / 3, "General", "0.333333333"),
    (123456789012, "General", "1.23457E+11"),
    (0.00001, "General", "0.00001"),
    (1e-10, "General", "1E-10"),
    (1234567890, "General", "1234567890"),
    (-0.5, "General", "-0.5"),
    (100000000000, "General", "1E+11"),
    (1, "m/d/yyyy", "1/1/1900"),
    (60, "m/d/yyyy", "2/29/1900"),
    (2, "ddd", "Mon"),
    (1, "dddd", "Sunday"),
    (61, "dddd", "Thursday"),
]


@pytest.mark.parametrize(("value", "format_code", "expected"), EXCEL_FORMAT_CODES)
def test_excel_custom_format_codes(value: object, format_code: str, expected: str) -> None:
    assert format_value(value, format_code).text == expected


def test_format_colors_conditions_and_palette() -> None:
    assert format_value(-5, "0;[Red]0").color == "red"
    assert format_value(5, "[Color10]0").color == "#008000"
    assert format_value(150, "[Blue][>100]0;[Red]0").color == "#0000ff"
    assert format_value(50, "[Blue][>100]0;[Red]0").color == "red"
