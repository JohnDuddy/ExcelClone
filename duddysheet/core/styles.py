"""Excel's built-in cell styles and Home-tab number-format shortcuts."""

from __future__ import annotations

import re
from typing import Any

from duddysheet.core.cell import BorderStyle
from duddysheet.core.conditional import FormatPatch

# Office 2023 theme (the Aptos theme): text and accent colors.
_TEXT2 = "#0e2841"
_ACCENTS = ("#156082", "#e97132", "#196b24", "#0f9ed5", "#a02b93", "#4ea72e")

ACCOUNTING = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)'
ACCOUNTING_0 = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
COMMA = '_(* #,##0.00_);_(* (#,##0.00);_(* "-"??_);_(@_)'
COMMA_0 = '_(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)'

#: Home > Number Format gallery entries: (label, format code).
NUMBER_FORMAT_GALLERY = (
    ("General", "General"),
    ("Number", "0.00"),
    ("Currency", "$#,##0.00"),
    ("Accounting", ACCOUNTING),
    ("Short Date", "m/d/yyyy"),
    ("Long Date", "dddd, mmmm d, yyyy"),
    ("Time", "h:mm:ss AM/PM"),
    ("Percentage", "0.00%"),
    ("Fraction", "# ?/?"),
    ("Scientific", "0.00E+00"),
    ("Text", "@"),
)
#: Keyboard number formats (Ctrl+Shift+~ $ % ^ # @ !).
SHORTCUT_FORMATS = {
    "general": "General",
    "currency": "$#,##0.00_);($#,##0.00)",
    "percent": "0%",
    "scientific": "0.00E+00",
    "date": "d-mmm-yy",
    "time": "h:mm AM/PM",
    "number": "#,##0.00",
}


def _tint(color: str, amount: float) -> str:
    """Blend a color toward white by ``amount`` (0..1), like Excel theme tints."""
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    blend = [round(channel + (255 - channel) * amount) for channel in (red, green, blue)]
    return "#" + "".join(f"{channel:02x}" for channel in blend)


def _thin(color: str) -> BorderStyle:
    return BorderStyle("thin", color)


def _box(color: str, style: str = "thin") -> dict[str, BorderStyle]:
    border = BorderStyle(style, color)
    return {"left_border": border, "right_border": border, "top_border": border, "bottom_border": border}


def _catalog() -> dict[str, tuple[str, FormatPatch]]:
    """Return style name -> (gallery group, format patch)."""
    styles: dict[str, tuple[str, FormatPatch]] = {
        "Normal": ("Good, Bad and Neutral", FormatPatch(
            number_format="General", font_family="Aptos", font_size=11, bold=False,
            italic=False, underline=False, font_color="#000000", fill_color="",
            left_border=BorderStyle(), right_border=BorderStyle(),
            top_border=BorderStyle(), bottom_border=BorderStyle(),
        )),
        "Bad": ("Good, Bad and Neutral", FormatPatch(fill_color="#ffc7ce", font_color="#9c0006")),
        "Good": ("Good, Bad and Neutral", FormatPatch(fill_color="#c6efce", font_color="#006100")),
        "Neutral": ("Good, Bad and Neutral", FormatPatch(fill_color="#ffeb9c", font_color="#9c5700")),
        "Calculation": ("Data and Model", FormatPatch(
            fill_color="#f2f2f2", font_color="#fa7d00", bold=True, **_box("#7f7f7f"),
        )),
        "Check Cell": ("Data and Model", FormatPatch(
            fill_color="#a5a5a5", font_color="#ffffff", bold=True, **_box("#3f3f3f", "double"),
        )),
        "Explanatory Text": ("Data and Model", FormatPatch(font_color="#7f7f7f", italic=True)),
        "Input": ("Data and Model", FormatPatch(
            fill_color="#ffcc99", font_color="#3f3f76", **_box("#7f7f7f"),
        )),
        "Linked Cell": ("Data and Model", FormatPatch(
            font_color="#fa7d00", bottom_border=BorderStyle("double", "#ff8001"),
        )),
        "Note": ("Data and Model", FormatPatch(fill_color="#ffffcc", **_box("#b2b2b2"))),
        "Output": ("Data and Model", FormatPatch(
            fill_color="#f2f2f2", font_color="#3f3f3f", bold=True, **_box("#3f3f3f"),
        )),
        "Warning Text": ("Data and Model", FormatPatch(font_color="#ff0000")),
        "Title": ("Titles and Headings", FormatPatch(font_family="Aptos Display", font_size=18, font_color=_TEXT2)),
        "Heading 1": ("Titles and Headings", FormatPatch(
            font_size=15, bold=True, font_color=_TEXT2, bottom_border=BorderStyle("thick", _ACCENTS[0]),
        )),
        "Heading 2": ("Titles and Headings", FormatPatch(
            font_size=13, bold=True, font_color=_TEXT2, bottom_border=BorderStyle("thick", _tint(_ACCENTS[0], 0.5)),
        )),
        "Heading 3": ("Titles and Headings", FormatPatch(
            font_size=11, bold=True, font_color=_TEXT2, bottom_border=BorderStyle("medium", _tint(_ACCENTS[0], 0.6)),
        )),
        "Heading 4": ("Titles and Headings", FormatPatch(bold=True, font_color=_TEXT2)),
        "Total": ("Titles and Headings", FormatPatch(
            bold=True,
            top_border=_thin(_ACCENTS[0]),
            bottom_border=BorderStyle("double", _ACCENTS[0]),
        )),
        "Comma": ("Number Format", FormatPatch(number_format=COMMA)),
        "Comma [0]": ("Number Format", FormatPatch(number_format=COMMA_0)),
        "Currency": ("Number Format", FormatPatch(number_format=ACCOUNTING)),
        "Currency [0]": ("Number Format", FormatPatch(number_format=ACCOUNTING_0)),
        "Percent": ("Number Format", FormatPatch(number_format="0%")),
    }
    for number, accent in enumerate(_ACCENTS, start=1):
        for percent, amount, font in ((20, 0.8, "#000000"), (40, 0.6, "#000000"), (60, 0.4, "#ffffff")):
            styles[f"{percent}% - Accent{number}"] = (
                "Themed Cell Styles",
                FormatPatch(fill_color=_tint(accent, amount), font_color=font),
            )
        styles[f"Accent{number}"] = ("Themed Cell Styles", FormatPatch(fill_color=accent, font_color="#ffffff"))
    return styles


CELL_STYLES = _catalog()


def style_patch(name: str) -> FormatPatch:
    """Return the format patch for a built-in cell style."""
    try:
        return CELL_STYLES[name][1]
    except KeyError:
        raise KeyError(f"Unknown cell style: {name!r}") from None


def _general_decimals(value: Any) -> int:
    if isinstance(value, float) and not value.is_integer():
        from duddysheet.core.formats import general_number

        text = general_number(value)
        if "E" in text:
            return 2
        return len(text.split(".")[1]) if "." in text else 0
    return 0


def change_decimals(format_code: str, delta: int, value: Any = None) -> str:
    """Return a number format with one more (delta=+1) or fewer (-1) decimals."""
    if format_code in ("General", ""):
        decimals = max(0, _general_decimals(value) + delta)
        return "0" if decimals == 0 else "0." + "0" * decimals
    sections = format_code.split(";")
    return ";".join(_change_section(section, delta) for section in sections)


_DIGITS_RE = re.compile(r"([0#?])((?:\.[0#?]*)?)")


def _change_section(section: str, delta: int) -> str:
    if "@" in section and not any(character in section for character in "0#?"):
        return section
    exponent = re.search(r"[Ee][+-]", section)
    if exponent is not None:
        head, tail = section[: exponent.start()], section[exponent.start() :]
        return _change_section(head, delta) + tail
    # Work outside quoted literals: find the last digit run.
    matches = [match for match in _DIGITS_RE.finditer(section) if not _in_quotes(section, match.start())]
    if not matches:
        return section
    last = matches[-1]
    start, end = last.span()
    integer, fraction = last.group(1), last.group(2)
    if delta > 0:
        fraction = (fraction or ".") + "0"
    else:
        if not fraction:
            return section
        fraction = fraction[:-1]
        if fraction == ".":
            fraction = ""
    return section[:start] + integer + fraction + section[end:]


def _in_quotes(text: str, position: int) -> bool:
    return text[:position].count('"') % 2 == 1
