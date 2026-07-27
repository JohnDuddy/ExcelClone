"""Headless pagination behavior."""

from __future__ import annotations

from datetime import datetime

import pytest

from duddysheet.core.printing import (
    A4,
    DEFAULT_COLUMN_WIDTH,
    DEFAULT_ROW_HEIGHT,
    LETTER,
    HeaderContext,
    Margins,
    Orientation,
    PageOrder,
    PageSetup,
    Pagination,
    column_width,
    expand_header,
    paginate,
    row_height,
    selection_to_area,
)
from duddysheet.core.sheet import Sheet


def populate(sheet: Sheet, rows: int, columns: int) -> Sheet:
    for row in range(rows):
        for column in range(columns):
            sheet.set_cell(row, column, row * 100 + column)
    return sheet


@pytest.fixture
def sheet() -> Sheet:
    return Sheet("Model")


def test_empty_sheet_produces_no_pages(sheet) -> None:
    result = paginate(sheet)

    assert result.is_empty
    assert len(result) == 0


def test_small_sheet_fits_one_page(sheet) -> None:
    populate(sheet, 10, 5)

    result = paginate(sheet)

    assert len(result) == 1
    page = result.pages[0]
    assert (page.first_row, page.last_row) == (0, 9)
    assert (page.first_column, page.last_column) == (0, 4)
    assert page.number == 1


def test_tall_sheet_breaks_into_multiple_pages(sheet) -> None:
    populate(sheet, 300, 3)

    result = paginate(sheet)

    assert len(result) > 1
    assert result.pages[0].first_row == 0
    assert result.pages[-1].last_row == 299
    # Pages must tile the range with no gap and no overlap.
    for earlier, later in zip(result.pages, result.pages[1:]):
        assert later.first_row == earlier.last_row + 1


def test_page_numbers_are_sequential(sheet) -> None:
    populate(sheet, 300, 3)

    result = paginate(sheet)

    assert [page.number for page in result.pages] == list(
        range(1, len(result.pages) + 1)
    )


def test_first_page_number_offsets_numbering(sheet) -> None:
    populate(sheet, 100, 3)

    result = paginate(sheet, PageSetup(first_page_number=7))

    assert result.pages[0].number == 7


def test_wide_sheet_breaks_across_columns(sheet) -> None:
    populate(sheet, 5, 40)

    result = paginate(sheet)

    assert len(result) > 1
    assert result.pages[0].first_column == 0
    assert result.pages[-1].last_column == 39


def test_landscape_fits_more_columns_than_portrait(sheet) -> None:
    populate(sheet, 5, 40)

    portrait = paginate(sheet, PageSetup(orientation=Orientation.PORTRAIT))
    landscape = paginate(sheet, PageSetup(orientation=Orientation.LANDSCAPE))

    assert landscape.pages[0].column_count > portrait.pages[0].column_count


def test_page_order_controls_traversal(sheet) -> None:
    populate(sheet, 200, 40)

    down = paginate(sheet, PageSetup(page_order=PageOrder.DOWN_THEN_OVER))
    over = paginate(sheet, PageSetup(page_order=PageOrder.OVER_THEN_DOWN))

    assert len(down) == len(over)
    # Down-then-over advances rows first; over-then-down advances columns.
    assert down.pages[1].first_column == down.pages[0].first_column
    assert over.pages[1].first_row == over.pages[0].first_row
    assert over.pages[1].first_column > over.pages[0].first_column


def test_hidden_rows_and_columns_are_not_printed(sheet) -> None:
    populate(sheet, 10, 5)
    sheet.hidden_rows.add(3)
    sheet.hidden_columns.add(2)

    assert row_height(sheet, 3) == 0.0
    assert column_width(sheet, 2) == 0.0
    assert row_height(sheet, 4) == DEFAULT_ROW_HEIGHT
    assert column_width(sheet, 1) == DEFAULT_COLUMN_WIDTH


def test_filtered_rows_are_not_printed(sheet) -> None:
    populate(sheet, 10, 3)
    sheet.filtered_rows.add(5)

    assert row_height(sheet, 5) == 0.0


def test_custom_sizes_convert_to_points(sheet) -> None:
    populate(sheet, 3, 3)
    sheet.row_heights[0] = 30.0
    sheet.column_widths[0] = 20.0

    assert row_height(sheet, 0) == 30.0
    assert column_width(sheet, 0) == pytest.approx(20.0 * 7.0 * 0.75)


def test_print_area_restricts_output(sheet) -> None:
    populate(sheet, 50, 20)
    area = selection_to_area(2, 1, 6, 3, sheet.name)

    result = paginate(sheet, PageSetup(print_area=area))

    assert len(result) == 1
    page = result.pages[0]
    assert (page.first_row, page.last_row) == (2, 6)
    assert (page.first_column, page.last_column) == (1, 3)


def test_repeat_rows_are_excluded_from_the_body(sheet) -> None:
    populate(sheet, 300, 3)

    result = paginate(sheet, PageSetup(repeat_rows=(0, 1)))

    for page in result.pages:
        assert page.repeat_rows == (0, 1)
        assert page.first_row >= 2, "header rows must not repeat inside the body"


def test_repeat_rows_reduce_body_rows_per_page(sheet) -> None:
    populate(sheet, 300, 3)

    plain = paginate(sheet)
    with_titles = paginate(sheet, PageSetup(repeat_rows=(0, 3)))

    assert with_titles.pages[0].row_count < plain.pages[0].row_count


def test_repeat_columns_are_excluded_from_the_body(sheet) -> None:
    populate(sheet, 5, 40)

    result = paginate(sheet, PageSetup(repeat_columns=(0, 0)))

    for page in result.pages:
        assert page.repeat_columns == (0, 0)
        assert page.first_column >= 1


def test_fit_to_one_page_wide_produces_a_single_column_band(sheet) -> None:
    populate(sheet, 5, 40)

    result = paginate(sheet, PageSetup(fit_to_width=1))

    assert result.scale < 1.0
    assert len({page.first_column for page in result.pages}) == 1
    assert result.pages[0].last_column == 39


def test_fit_to_page_never_enlarges(sheet) -> None:
    populate(sheet, 2, 2)

    result = paginate(sheet, PageSetup(fit_to_width=4))

    assert result.scale == 1.0


def test_explicit_scale_changes_rows_per_page(sheet) -> None:
    populate(sheet, 300, 3)

    full = paginate(sheet, PageSetup(scale=1.0))
    half = paginate(sheet, PageSetup(scale=0.5))

    assert half.pages[0].row_count > full.pages[0].row_count


def test_oversized_row_still_occupies_its_own_page(sheet) -> None:
    """A row taller than the page must not loop forever or vanish."""
    populate(sheet, 3, 2)
    sheet.row_heights[1] = 5000.0

    result = paginate(sheet)

    assert len(result) >= 2
    printed = {row for page in result.pages for row in range(page.first_row, page.last_row + 1)}
    assert printed == {0, 1, 2}


def test_oversized_column_still_occupies_its_own_page(sheet) -> None:
    populate(sheet, 2, 3)
    sheet.column_widths[1] = 900.0

    result = paginate(sheet)

    printed = {
        column
        for page in result.pages
        for column in range(page.first_column, page.last_column + 1)
    }
    assert printed == {0, 1, 2}


def test_margins_affect_capacity(sheet) -> None:
    populate(sheet, 300, 3)

    narrow = paginate(sheet, PageSetup(margins=Margins(10, 10, 10, 10)))
    wide = paginate(sheet, PageSetup(margins=Margins(120, 120, 120, 120)))

    assert narrow.pages[0].row_count > wide.pages[0].row_count


def test_paper_size_affects_capacity(sheet) -> None:
    populate(sheet, 300, 3)

    letter = paginate(sheet, PageSetup(paper=LETTER))
    a4 = paginate(sheet, PageSetup(paper=A4))

    assert a4.pages[0].row_count >= letter.pages[0].row_count


def test_impossible_margins_are_rejected(sheet) -> None:
    populate(sheet, 3, 3)
    setup = PageSetup(margins=Margins(left=400.0, right=400.0))

    with pytest.raises(ValueError, match="margins exceed"):
        paginate(sheet, setup)


def test_invalid_setup_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="Scale"):
        PageSetup(scale=0.0)
    with pytest.raises(ValueError, match="at least 1 page"):
        PageSetup(fit_to_width=0)
    with pytest.raises(ValueError, match="First page number"):
        PageSetup(first_page_number=0)
    with pytest.raises(ValueError, match="ordered"):
        PageSetup(repeat_rows=(5, 2))
    with pytest.raises(ValueError, match="negative"):
        Margins(left=-1.0)


def test_pagination_is_deterministic(sheet) -> None:
    """Preview, print, and PDF export rely on repeated calls agreeing."""
    populate(sheet, 250, 30)
    setup = PageSetup(repeat_rows=(0, 0), fit_to_width=2)

    first = paginate(sheet, setup)
    second = paginate(sheet, setup)

    assert first == second


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("Page &P of &N", "Page 3 of 9"),
        ("&A", "Budget"),
        ("&F", "model.dsheet"),
        ("&Z", "C:/work/model.dsheet"),
        ("&D", "2026-07-27"),
        ("&T", "14:30"),
        ("Profit && Loss", "Profit & Loss"),
        ("&p of &n", "3 of 9"),
        ("plain text", "plain text"),
        ("", ""),
        ("&X unknown", "&X unknown"),
    ],
)
def test_header_token_expansion(template, expected) -> None:
    context = HeaderContext(
        page=3,
        total_pages=9,
        sheet_name="Budget",
        file_name="model.dsheet",
        file_path="C:/work/model.dsheet",
        moment=datetime(2026, 7, 27, 14, 30),
    )

    assert expand_header(template, context) == expected


def test_header_expansion_handles_trailing_ampersand() -> None:
    context = HeaderContext(page=1, total_pages=1, sheet_name="S")

    assert expand_header("total &", context) == "total &"
