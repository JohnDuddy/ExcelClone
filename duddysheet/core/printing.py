"""Headless worksheet pagination.

Deciding what lands on which sheet of paper is spreadsheet behavior, not
presentation, so it lives here and stays free of Qt. The renderer consumes the
immutable pages this module produces, which lets pagination be tested exactly
and keeps print output identical to PDF export.

All geometry is in PostScript points (1/72 inch). Row heights are stored in
points already; column widths are stored in character units, where one unit is
seven pixels at 96 dpi.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from duddysheet.core.refs import CellReference, RangeReference

if TYPE_CHECKING:  # pragma: no cover - typing only
    from duddysheet.core.sheet import Sheet

POINTS_PER_INCH = 72.0
_POINTS_PER_PIXEL = 0.75
_PIXELS_PER_WIDTH_UNIT = 7.0

#: Grid defaults mirrored from the on-screen view, converted to points.
DEFAULT_ROW_HEIGHT = 22.0 * _POINTS_PER_PIXEL
DEFAULT_COLUMN_WIDTH = 96.0 * _POINTS_PER_PIXEL

#: Bound on fit-to-page shrinking, matching common spreadsheet behavior.
MINIMUM_SCALE = 0.10
MAXIMUM_SCALE = 4.0

#: Fit-to-page scales content to exactly the printable extent, so binary
#: rounding alone can push the final band onto a spurious extra page. Absorb
#: a sub-point discrepancy, which is far below anything a printer resolves.
_FIT_EPSILON = 1e-6


class Orientation(Enum):
    """Paper orientation."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class PageOrder(Enum):
    """Order in which a grid wider and taller than one page is walked."""

    DOWN_THEN_OVER = "down_then_over"
    OVER_THEN_DOWN = "over_then_down"


@dataclass(frozen=True)
class PaperSize:
    """A named paper size in points, described in portrait orientation."""

    name: str
    width: float
    height: float

    def oriented(self, orientation: Orientation) -> tuple[float, float]:
        """Return (width, height) for the requested orientation."""
        if orientation is Orientation.LANDSCAPE:
            return self.height, self.width
        return self.width, self.height


A4 = PaperSize("A4", 595.28, 841.89)
LETTER = PaperSize("Letter", 612.0, 792.0)
LEGAL = PaperSize("Legal", 612.0, 1008.0)
A3 = PaperSize("A3", 841.89, 1190.55)
TABLOID = PaperSize("Tabloid", 792.0, 1224.0)

PAPER_SIZES: dict[str, PaperSize] = {
    paper.name: paper for paper in (A4, LETTER, LEGAL, A3, TABLOID)
}


@dataclass(frozen=True)
class Margins:
    """Page margins in points."""

    left: float = 54.0
    right: float = 54.0
    top: float = 54.0
    bottom: float = 54.0
    header: float = 27.0
    footer: float = 27.0

    def __post_init__(self) -> None:
        for name in ("left", "right", "top", "bottom", "header", "footer"):
            if getattr(self, name) < 0:
                raise ValueError(f"Margin {name} cannot be negative")


@dataclass(frozen=True)
class PageSetup:
    """An immutable description of how a sheet should be laid onto paper."""

    paper: PaperSize = LETTER
    orientation: Orientation = Orientation.PORTRAIT
    margins: Margins = Margins()
    scale: float = 1.0
    fit_to_width: int | None = None
    fit_to_height: int | None = None
    print_area: RangeReference | None = None
    show_gridlines: bool = False
    show_headings: bool = False
    repeat_rows: tuple[int, int] | None = None
    repeat_columns: tuple[int, int] | None = None
    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = "&A"
    footer_right: str = "Page &P of &N"
    center_horizontally: bool = False
    center_vertically: bool = False
    page_order: PageOrder = PageOrder.DOWN_THEN_OVER
    first_page_number: int = 1

    def __post_init__(self) -> None:
        if not MINIMUM_SCALE <= self.scale <= MAXIMUM_SCALE:
            raise ValueError(
                f"Scale must be between {MINIMUM_SCALE} and {MAXIMUM_SCALE}"
            )
        for name in ("fit_to_width", "fit_to_height"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1 page")
        if self.first_page_number < 1:
            raise ValueError("First page number must be at least 1")
        for name in ("repeat_rows", "repeat_columns"):
            span = getattr(self, name)
            if span is not None:
                first, last = span
                if first < 0 or last < first:
                    raise ValueError(f"{name} must be an ordered, non-negative span")

    @property
    def fits_to_page(self) -> bool:
        """Return whether automatic shrink-to-fit is requested."""
        return self.fit_to_width is not None or self.fit_to_height is not None

    @property
    def printable_width(self) -> float:
        """Return the usable width in points, before scaling."""
        width, _ = self.paper.oriented(self.orientation)
        usable = width - self.margins.left - self.margins.right
        if usable <= 0:
            raise ValueError("Left and right margins exceed the paper width")
        return usable

    @property
    def printable_height(self) -> float:
        """Return the usable height in points, before scaling."""
        _, height = self.paper.oriented(self.orientation)
        usable = height - self.margins.top - self.margins.bottom
        if usable <= 0:
            raise ValueError("Top and bottom margins exceed the paper height")
        return usable


@dataclass(frozen=True)
class Page:
    """One sheet of paper: the body block plus any repeated titles."""

    number: int
    first_row: int
    last_row: int
    first_column: int
    last_column: int
    repeat_rows: tuple[int, int] | None = None
    repeat_columns: tuple[int, int] | None = None

    @property
    def row_count(self) -> int:
        """Return the number of body rows on this page."""
        return self.last_row - self.first_row + 1

    @property
    def column_count(self) -> int:
        """Return the number of body columns on this page."""
        return self.last_column - self.first_column + 1


@dataclass(frozen=True)
class Pagination:
    """The complete result of laying a sheet onto paper."""

    pages: tuple[Page, ...]
    scale: float
    sheet_name: str

    def __len__(self) -> int:
        return len(self.pages)

    def __iter__(self):
        return iter(self.pages)

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to print."""
        return not self.pages


def row_height(sheet: Sheet, row: int) -> float:
    """Return a row's printed height in points."""
    if row in sheet.hidden_rows or row in sheet.filtered_rows:
        return 0.0
    return sheet.row_heights.get(row, DEFAULT_ROW_HEIGHT)


def column_width(sheet: Sheet, column: int) -> float:
    """Return a column's printed width in points."""
    if column in sheet.hidden_columns:
        return 0.0
    stored = sheet.column_widths.get(column)
    if stored is None:
        return DEFAULT_COLUMN_WIDTH
    return stored * _PIXELS_PER_WIDTH_UNIT * _POINTS_PER_PIXEL


def _printed_extent(sheet: Sheet, setup: PageSetup) -> RangeReference | None:
    """Return the range to print, honoring an explicit print area."""
    if setup.print_area is not None:
        return setup.print_area
    return sheet.used_range


def _visible(indices: range, sizes: dict[int, float]) -> list[int]:
    """Return indices that occupy space, preserving order."""
    return [index for index in indices if sizes[index] > 0.0]


def _band(
    indices: list[int],
    sizes: dict[int, float],
    available: float,
    reserved: float,
) -> list[tuple[int, int]]:
    """Split ordered indices into runs that each fit the available space.

    A single row or column larger than the page still occupies its own page
    rather than looping forever; spreadsheets clip in that case.
    """
    if not indices:
        return []

    usable = available - reserved
    if usable <= 0.0:
        # Repeated titles alone exceed the page; give the body what is left.
        usable = available

    bands: list[tuple[int, int]] = []
    start = indices[0]
    previous = indices[0]
    consumed = 0.0

    tolerance = usable * _FIT_EPSILON
    for index in indices:
        size = sizes[index]
        if consumed > 0.0 and consumed + size > usable + tolerance:
            bands.append((start, previous))
            start = index
            consumed = size
        else:
            consumed += size
        previous = index

    bands.append((start, previous))
    return bands


def _fit_scale(
    setup: PageSetup,
    column_sizes: dict[int, float],
    row_sizes: dict[int, float],
    repeat_width: float,
    repeat_height: float,
) -> float:
    """Return the scale that satisfies the requested fit-to-page limits."""
    scale = 1.0

    if setup.fit_to_width is not None:
        content = sum(column_sizes.values())
        budget = setup.fit_to_width * setup.printable_width - repeat_width * (
            setup.fit_to_width
        )
        if content > 0.0 and budget > 0.0:
            scale = min(scale, budget / content)

    if setup.fit_to_height is not None:
        content = sum(row_sizes.values())
        budget = setup.fit_to_height * setup.printable_height - repeat_height * (
            setup.fit_to_height
        )
        if content > 0.0 and budget > 0.0:
            scale = min(scale, budget / content)

    return max(MINIMUM_SCALE, min(scale, 1.0))


def paginate(sheet: Sheet, setup: PageSetup | None = None) -> Pagination:
    """Lay a sheet onto paper and return its immutable pages.

    Pagination is deterministic: the same sheet and setup always produce the
    same pages, which is what allows preview, print, and PDF export to agree.
    """
    setup = setup or PageSetup()
    extent = _printed_extent(sheet, setup)
    if extent is None:
        return Pagination((), setup.scale, sheet.name)

    rows = range(extent.min_row, extent.max_row + 1)
    columns = range(extent.min_column, extent.max_column + 1)

    row_sizes = {row: row_height(sheet, row) for row in rows}
    column_sizes = {column: column_width(sheet, column) for column in columns}

    visible_rows = _visible(rows, row_sizes)
    visible_columns = _visible(columns, column_sizes)
    if not visible_rows or not visible_columns:
        return Pagination((), setup.scale, sheet.name)

    repeat_rows = _clamp_span(setup.repeat_rows, visible_rows)
    repeat_columns = _clamp_span(setup.repeat_columns, visible_columns)

    repeat_height = _span_size(repeat_rows, sheet, row_height)
    repeat_width = _span_size(repeat_columns, sheet, column_width)

    scale = (
        _fit_scale(setup, column_sizes, row_sizes, repeat_width, repeat_height)
        if setup.fits_to_page
        else setup.scale
    )

    # Repeated titles are part of the body block, so exclude them from it.
    body_rows = _exclude_span(visible_rows, repeat_rows)
    body_columns = _exclude_span(visible_columns, repeat_columns)
    if not body_rows or not body_columns:
        body_rows = body_rows or visible_rows
        body_columns = body_columns or visible_columns

    scaled_rows = {row: row_sizes[row] * scale for row in body_rows}
    scaled_columns = {column: column_sizes[column] * scale for column in body_columns}

    row_bands = _band(
        body_rows,
        scaled_rows,
        setup.printable_height,
        repeat_height * scale,
    )
    column_bands = _band(
        body_columns,
        scaled_columns,
        setup.printable_width,
        repeat_width * scale,
    )

    if setup.page_order is PageOrder.DOWN_THEN_OVER:
        blocks = [
            (rows_band, columns_band)
            for columns_band in column_bands
            for rows_band in row_bands
        ]
    else:
        blocks = [
            (rows_band, columns_band)
            for rows_band in row_bands
            for columns_band in column_bands
        ]

    pages = tuple(
        Page(
            number=setup.first_page_number + offset,
            first_row=rows_band[0],
            last_row=rows_band[1],
            first_column=columns_band[0],
            last_column=columns_band[1],
            repeat_rows=repeat_rows,
            repeat_columns=repeat_columns,
        )
        for offset, (rows_band, columns_band) in enumerate(blocks)
    )
    return Pagination(pages, scale, sheet.name)


def _clamp_span(
    span: tuple[int, int] | None,
    visible: list[int],
) -> tuple[int, int] | None:
    """Return a repeat span narrowed to indices that are actually printed."""
    if span is None or not visible:
        return None
    first, last = span
    inside = [index for index in visible if first <= index <= last]
    if not inside:
        return None
    return inside[0], inside[-1]


def _span_size(span: tuple[int, int] | None, sheet: Sheet, measure) -> float:
    """Return the total printed size of a repeated span."""
    if span is None:
        return 0.0
    return sum(measure(sheet, index) for index in range(span[0], span[1] + 1))


def _exclude_span(indices: list[int], span: tuple[int, int] | None) -> list[int]:
    """Return indices outside a repeated span."""
    if span is None:
        return list(indices)
    first, last = span
    return [index for index in indices if not first <= index <= last]


@dataclass(frozen=True)
class HeaderContext:
    """Values substituted into header and footer templates."""

    page: int
    total_pages: int
    sheet_name: str
    file_name: str = ""
    file_path: str = ""
    moment: datetime | date | None = None


_TOKENS = ("&P", "&N", "&D", "&T", "&F", "&A", "&Z")


def expand_header(template: str, context: HeaderContext) -> str:
    """Expand header and footer tokens.

    Supported tokens follow the spreadsheet convention: ``&P`` page number,
    ``&N`` total pages, ``&D`` date, ``&T`` time, ``&F`` file name, ``&Z``
    file path, ``&A`` sheet name, and ``&&`` a literal ampersand.
    """
    if not template:
        return ""

    moment = context.moment or datetime.now()
    replacements = {
        "&P": str(context.page),
        "&N": str(context.total_pages),
        "&D": moment.strftime("%Y-%m-%d"),
        "&T": moment.strftime("%H:%M") if isinstance(moment, datetime) else "",
        "&F": context.file_name,
        "&Z": context.file_path,
        "&A": context.sheet_name,
    }

    result: list[str] = []
    index = 0
    while index < len(template):
        character = template[index]
        if character != "&":
            result.append(character)
            index += 1
            continue
        pair = template[index : index + 2]
        if pair == "&&":
            result.append("&")
            index += 2
        elif pair.upper() in _TOKENS:
            result.append(replacements[pair.upper()])
            index += 2
        else:
            result.append(character)
            index += 1
    return "".join(result)


def setup_to_dict(setup: PageSetup) -> dict:
    """Return a JSON-serializable form of a page setup."""
    return {
        "paper": setup.paper.name,
        "orientation": setup.orientation.value,
        "margins": {
            "left": setup.margins.left,
            "right": setup.margins.right,
            "top": setup.margins.top,
            "bottom": setup.margins.bottom,
            "header": setup.margins.header,
            "footer": setup.margins.footer,
        },
        "scale": setup.scale,
        "fit_to_width": setup.fit_to_width,
        "fit_to_height": setup.fit_to_height,
        "print_area": setup.print_area.to_a1() if setup.print_area else None,
        "show_gridlines": setup.show_gridlines,
        "show_headings": setup.show_headings,
        "repeat_rows": list(setup.repeat_rows) if setup.repeat_rows else None,
        "repeat_columns": (
            list(setup.repeat_columns) if setup.repeat_columns else None
        ),
        "header_left": setup.header_left,
        "header_center": setup.header_center,
        "header_right": setup.header_right,
        "footer_left": setup.footer_left,
        "footer_center": setup.footer_center,
        "footer_right": setup.footer_right,
        "center_horizontally": setup.center_horizontally,
        "center_vertically": setup.center_vertically,
        "page_order": setup.page_order.value,
        "first_page_number": setup.first_page_number,
    }


def setup_from_dict(data: dict) -> PageSetup:
    """Rebuild a page setup from its serialized form.

    Unknown or malformed fields fall back to defaults rather than refusing the
    file: a bad print preference must never make a workbook unopenable.
    """
    from duddysheet.core.refs import parse_a1

    margins_data = data.get("margins") or {}
    margins = Margins(
        left=float(margins_data.get("left", 54.0)),
        right=float(margins_data.get("right", 54.0)),
        top=float(margins_data.get("top", 54.0)),
        bottom=float(margins_data.get("bottom", 54.0)),
        header=float(margins_data.get("header", 27.0)),
        footer=float(margins_data.get("footer", 27.0)),
    )

    print_area = None
    raw_area = data.get("print_area")
    if raw_area:
        try:
            parsed = parse_a1(raw_area)
        except (ValueError, KeyError):
            parsed = None
        if isinstance(parsed, RangeReference):
            print_area = parsed

    def span(key: str) -> tuple[int, int] | None:
        value = data.get(key)
        if not value or len(value) != 2:
            return None
        first, last = int(value[0]), int(value[1])
        return (first, last) if 0 <= first <= last else None

    try:
        return PageSetup(
            paper=PAPER_SIZES.get(data.get("paper", "Letter"), LETTER),
            orientation=Orientation(data.get("orientation", "portrait")),
            margins=margins,
            scale=float(data.get("scale", 1.0)),
            fit_to_width=data.get("fit_to_width"),
            fit_to_height=data.get("fit_to_height"),
            print_area=print_area,
            show_gridlines=bool(data.get("show_gridlines", False)),
            show_headings=bool(data.get("show_headings", False)),
            repeat_rows=span("repeat_rows"),
            repeat_columns=span("repeat_columns"),
            header_left=str(data.get("header_left", "")),
            header_center=str(data.get("header_center", "")),
            header_right=str(data.get("header_right", "")),
            footer_left=str(data.get("footer_left", "")),
            footer_center=str(data.get("footer_center", "&A")),
            footer_right=str(data.get("footer_right", "Page &P of &N")),
            center_horizontally=bool(data.get("center_horizontally", False)),
            center_vertically=bool(data.get("center_vertically", False)),
            page_order=PageOrder(data.get("page_order", "down_then_over")),
            first_page_number=int(data.get("first_page_number", 1)),
        )
    except (ValueError, TypeError):
        return PageSetup()


def with_print_area(setup: PageSetup, area: RangeReference | None) -> PageSetup:
    """Return a copy of the setup targeting a different print area."""
    return replace(setup, print_area=area)


def selection_to_area(
    first_row: int,
    first_column: int,
    last_row: int,
    last_column: int,
    sheet_name: str,
) -> RangeReference:
    """Return a print area from a grid selection."""
    return RangeReference(
        CellReference(min(first_row, last_row), min(first_column, last_column),
                      sheet=sheet_name),
        CellReference(max(first_row, last_row), max(first_column, last_column),
                      sheet=sheet_name),
    )
