"""Qt rendering of paginated worksheets to printers, preview, and PDF.

The pages themselves are decided by :mod:`duddysheet.core.printing`, which is
Qt-free. This module only paints them, so print output, print preview, and PDF
export are guaranteed to agree: they share one renderer over one pagination.

The painter works in PostScript points. Device resolution is applied once as a
transform, which keeps every measurement here in the same units the core uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPagedPaintDevice,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)
from PySide6.QtPrintSupport import QPrinter

from duddysheet.branding import PRODUCT_NAME
from duddysheet.core.cell import CellFormat
from duddysheet.core.conditional import ConditionalFormatEngine
from duddysheet.core.formats import format_value
from duddysheet.core.printing import (
    POINTS_PER_INCH,
    HeaderContext,
    Orientation,
    Page,
    PageSetup,
    Pagination,
    column_width,
    expand_header,
    paginate,
    row_height,
)
from duddysheet.core.refs import CellReference
from duddysheet.core.sheet import Sheet
from duddysheet.core.workbook import Workbook

_GRIDLINE_COLOR = QColor("#d0d0d0")
_HEADING_BACKGROUND = QColor("#f0f0f0")
_HEADING_TEXT = QColor("#404040")
_HEADING_FONT_POINTS = 7.5
_HEADER_FONT_POINTS = 9.0
_CELL_PADDING = 2.0

#: Width of the row-number gutter and height of the column-letter strip.
_ROW_HEADING_WIDTH = 34.0
_COLUMN_HEADING_HEIGHT = 13.0

_PEN_WIDTHS = {
    "thin": 0.75,
    "medium": 1.5,
    "thick": 2.25,
    "double": 0.75,
    "dashed": 0.75,
    "dotted": 0.75,
    "hair": 0.5,
}
_PEN_STYLES = {
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
}

_QT_PAGE_SIZES = {
    "A4": QPageSize.PageSizeId.A4,
    "Letter": QPageSize.PageSizeId.Letter,
    "Legal": QPageSize.PageSizeId.Legal,
    "A3": QPageSize.PageSizeId.A3,
    "Tabloid": QPageSize.PageSizeId.Tabloid,
}


@dataclass(frozen=True)
class _Track:
    """One laid-out row or column: its index, offset, and size in points."""

    index: int
    offset: float
    size: float

    @property
    def end(self) -> float:
        return self.offset + self.size


def apply_setup_to_paged_device(
    device: QPagedPaintDevice,
    setup: PageSetup,
) -> None:
    """Configure any paged device's page layout from a page setup."""
    layout = device.pageLayout()
    page_size_id = _QT_PAGE_SIZES.get(setup.paper.name)
    if page_size_id is not None:
        layout.setPageSize(QPageSize(page_size_id))
    else:  # pragma: no cover - custom sizes are not offered in the UI
        layout.setPageSize(
            QPageSize(
                QSizeF(setup.paper.width, setup.paper.height),
                QPageSize.Unit.Point,
            )
        )
    layout.setOrientation(
        QPageLayout.Orientation.Landscape
        if setup.orientation is Orientation.LANDSCAPE
        else QPageLayout.Orientation.Portrait
    )
    layout.setUnits(QPageLayout.Unit.Point)
    layout.setMargins(
        QMarginsF(
            setup.margins.left,
            setup.margins.top,
            setup.margins.right,
            setup.margins.bottom,
        )
    )
    device.setPageLayout(layout)


def apply_setup_to_printer(printer: QPrinter, setup: PageSetup) -> None:
    """Configure a printer's page layout from a page setup."""
    apply_setup_to_paged_device(printer, setup)


class WorksheetRenderer:
    """Paints paginated worksheet pages onto any Qt paint device."""

    def __init__(
        self,
        sheet: Sheet,
        setup: PageSetup | None = None,
        *,
        workbook: Workbook | None = None,
        document_name: str = "",
        document_path: str = "",
        moment: datetime | None = None,
    ) -> None:
        self.sheet = sheet
        self.setup = setup or PageSetup()
        self.document_name = document_name
        self.document_path = document_path
        self.moment = moment
        self._conditional = (
            ConditionalFormatEngine(workbook) if workbook is not None else None
        )
        self.pagination: Pagination = paginate(sheet, self.setup)

    @property
    def page_count(self) -> int:
        """Return the number of printed pages."""
        return len(self.pagination)

    def _effective_format(self, row: int, column: int) -> CellFormat:
        """Return a cell's format including any conditional overrides."""
        if self._conditional is None:
            return self.sheet.get_cell(row, column).format
        return self._conditional.evaluate(self.sheet, row, column).format

    def _tracks(self, page: Page) -> tuple[list[_Track], list[_Track]]:
        """Return laid-out rows and columns, repeated titles included first."""
        scale = self.pagination.scale

        def build(
            repeat: tuple[int, int] | None,
            first: int,
            last: int,
            measure,
            start: float,
        ) -> list[_Track]:
            tracks: list[_Track] = []
            offset = start
            indices: list[int] = []
            if repeat is not None:
                indices.extend(range(repeat[0], repeat[1] + 1))
            indices.extend(
                index for index in range(first, last + 1)
                if repeat is None or not repeat[0] <= index <= repeat[1]
            )
            for index in indices:
                size = measure(self.sheet, index) * scale
                if size <= 0.0:
                    continue
                tracks.append(_Track(index, offset, size))
                offset += size
            return tracks

        heading_offset_x = _ROW_HEADING_WIDTH if self.setup.show_headings else 0.0
        heading_offset_y = _COLUMN_HEADING_HEIGHT if self.setup.show_headings else 0.0

        rows = build(
            page.repeat_rows, page.first_row, page.last_row, row_height,
            heading_offset_y,
        )
        columns = build(
            page.repeat_columns, page.first_column, page.last_column, column_width,
            heading_offset_x,
        )
        return rows, columns

    def render_page(self, painter: QPainter, index: int, dpi: float) -> None:
        """Paint one page. ``index`` is zero-based within the pagination."""
        if not 0 <= index < self.page_count:
            raise IndexError(f"Page {index} is outside the printed range")

        page = self.pagination.pages[index]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Work in points regardless of device resolution.
        painter.scale(dpi / POINTS_PER_INCH, dpi / POINTS_PER_INCH)

        rows, columns = self._tracks(page)
        self._center(painter, rows, columns)
        self._paint_headings(painter, rows, columns)
        self._paint_cells(painter, rows, columns)
        self._paint_header_and_footer(painter, page, index)
        painter.restore()

    def _center(
        self,
        painter: QPainter,
        rows: list[_Track],
        columns: list[_Track],
    ) -> None:
        """Offset the block for centred layouts."""
        if not rows or not columns:
            return
        dx = dy = 0.0
        if self.setup.center_horizontally:
            used = columns[-1].end - columns[0].offset
            dx = max(0.0, (self.setup.printable_width - used) / 2.0)
        if self.setup.center_vertically:
            used = rows[-1].end - rows[0].offset
            dy = max(0.0, (self.setup.printable_height - used) / 2.0)
        if dx or dy:
            painter.translate(dx, dy)

    def _paint_headings(
        self,
        painter: QPainter,
        rows: list[_Track],
        columns: list[_Track],
    ) -> None:
        """Paint the A/B/C and 1/2/3 reference strips when requested."""
        if not self.setup.show_headings or not rows or not columns:
            return

        painter.save()
        font = QFont("Aptos", -1)
        font.setPointSizeF(_HEADING_FONT_POINTS)
        painter.setFont(font)

        for column in columns:
            rect = QRectF(
                column.offset, 0.0, column.size, _COLUMN_HEADING_HEIGHT
            )
            painter.fillRect(rect, _HEADING_BACKGROUND)
            painter.setPen(QPen(_HEADING_TEXT))
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                CellReference(0, column.index).to_a1().rstrip("1"),
            )

        for row in rows:
            rect = QRectF(0.0, row.offset, _ROW_HEADING_WIDTH, row.size)
            painter.fillRect(rect, _HEADING_BACKGROUND)
            painter.setPen(QPen(_HEADING_TEXT))
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignCenter, str(row.index + 1)
            )

        painter.restore()

    def _paint_cells(
        self,
        painter: QPainter,
        rows: list[_Track],
        columns: list[_Track],
    ) -> None:
        """Paint fills, gridlines, text, and borders for every visible cell."""
        merged = self._merged_lookup()

        for row in rows:
            for column in columns:
                if (row.index, column.index) in merged:
                    continue
                rect = QRectF(column.offset, row.offset, column.size, row.size)
                self._paint_cell(painter, rect, row.index, column.index)

        if self.setup.show_gridlines:
            painter.save()
            painter.setPen(QPen(_GRIDLINE_COLOR, 0.5))
            top = rows[0].offset if rows else 0.0
            bottom = rows[-1].end if rows else 0.0
            left = columns[0].offset if columns else 0.0
            right = columns[-1].end if columns else 0.0
            for row in rows:
                painter.drawLine(QPointF(left, row.offset), QPointF(right, row.offset))
            painter.drawLine(QPointF(left, bottom), QPointF(right, bottom))
            for column in columns:
                painter.drawLine(
                    QPointF(column.offset, top), QPointF(column.offset, bottom)
                )
            painter.drawLine(QPointF(right, top), QPointF(right, bottom))
            painter.restore()

        for row in rows:
            for column in columns:
                rect = QRectF(column.offset, row.offset, column.size, row.size)
                self._paint_borders(
                    painter, rect, self._effective_format(row.index, column.index)
                )

    def _merged_lookup(self) -> dict[tuple[int, int], None]:
        """Return coordinates covered by a merge but not its anchor."""
        covered: dict[tuple[int, int], None] = {}
        for merged in self.sheet.merged_ranges:
            for row in range(merged.min_row, merged.max_row + 1):
                for column in range(merged.min_column, merged.max_column + 1):
                    if (row, column) != (merged.min_row, merged.min_column):
                        covered[(row, column)] = None
        return covered

    def _paint_cell(
        self,
        painter: QPainter,
        rect: QRectF,
        row: int,
        column: int,
    ) -> None:
        """Paint one cell's fill and text."""
        cell = self.sheet.get_cell(row, column)
        cell_format = self._effective_format(row, column)

        if cell_format.fill_color:
            painter.fillRect(rect, QColor(cell_format.fill_color))

        if cell.display_value is None:
            return

        formatted = format_value(cell.display_value, cell_format.number_format)
        if not formatted.text:
            return

        painter.save()
        font = QFont(cell_format.font_family)
        font.setPointSizeF(cell_format.font_size)
        font.setBold(cell_format.bold)
        font.setItalic(cell_format.italic)
        font.setUnderline(cell_format.underline or cell.hyperlink is not None)
        painter.setFont(font)

        color = (
            "#0563c1"
            if cell.hyperlink is not None
            else (formatted.color or cell_format.font_color)
        )
        painter.setPen(QPen(QColor(color)))

        text_rect = rect.adjusted(_CELL_PADDING, 0.0, -_CELL_PADDING, 0.0)
        painter.setClipRect(rect)
        painter.drawText(
            text_rect,
            int(self._alignment(cell_format, cell.display_value)),
            formatted.text,
        )
        painter.restore()

    @staticmethod
    def _alignment(cell_format: CellFormat, value: object) -> Qt.AlignmentFlag:
        """Return the Qt alignment matching the on-screen grid."""
        horizontal = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
            "general": (
                Qt.AlignmentFlag.AlignRight
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else Qt.AlignmentFlag.AlignLeft
            ),
        }.get(cell_format.horizontal_alignment, Qt.AlignmentFlag.AlignLeft)
        vertical = {
            "top": Qt.AlignmentFlag.AlignTop,
            "center": Qt.AlignmentFlag.AlignVCenter,
            "bottom": Qt.AlignmentFlag.AlignBottom,
        }.get(cell_format.vertical_alignment, Qt.AlignmentFlag.AlignBottom)
        flags = horizontal | vertical
        if cell_format.wrap_text:
            flags |= Qt.TextFlag.TextWordWrap
        return flags

    @staticmethod
    def _paint_borders(
        painter: QPainter,
        rect: QRectF,
        cell_format: CellFormat,
    ) -> None:
        """Paint a cell's four border edges."""
        edges = (
            (cell_format.left_border, rect.topLeft(), rect.bottomLeft()),
            (cell_format.right_border, rect.topRight(), rect.bottomRight()),
            (cell_format.top_border, rect.topLeft(), rect.topRight()),
            (cell_format.bottom_border, rect.bottomLeft(), rect.bottomRight()),
        )
        painter.save()
        for border, start, end in edges:
            if border.style == "none":
                continue
            painter.setPen(
                QPen(
                    QColor(border.color),
                    _PEN_WIDTHS.get(border.style, 0.75),
                    _PEN_STYLES.get(border.style, Qt.PenStyle.SolidLine),
                )
            )
            painter.drawLine(start, end)
            if border.style == "double":
                horizontal = start.y() == end.y()
                shift = 1.5
                if horizontal:
                    painter.drawLine(
                        QPointF(start.x(), start.y() - shift),
                        QPointF(end.x(), end.y() - shift),
                    )
                else:
                    painter.drawLine(
                        QPointF(start.x() - shift, start.y()),
                        QPointF(end.x() - shift, end.y()),
                    )
        painter.restore()

    def _paint_header_and_footer(
        self,
        painter: QPainter,
        page: Page,
        index: int,
    ) -> None:
        """Paint the header and footer bands outside the printable body."""
        setup = self.setup
        context = HeaderContext(
            page=page.number,
            total_pages=self.page_count,
            sheet_name=self.sheet.name,
            file_name=self.document_name,
            file_path=self.document_path,
            moment=self.moment,
        )

        painter.save()
        painter.resetTransform()
        painter.scale(
            painter.device().logicalDpiX() / POINTS_PER_INCH,
            painter.device().logicalDpiY() / POINTS_PER_INCH,
        )
        font = QFont("Aptos")
        font.setPointSizeF(_HEADER_FONT_POINTS)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#404040")))

        width = setup.printable_width
        bands = (
            (
                -setup.margins.header - _HEADER_FONT_POINTS,
                (setup.header_left, setup.header_center, setup.header_right),
            ),
            (
                setup.printable_height + setup.margins.footer,
                (setup.footer_left, setup.footer_center, setup.footer_right),
            ),
        )
        alignments = (
            Qt.AlignmentFlag.AlignLeft,
            Qt.AlignmentFlag.AlignHCenter,
            Qt.AlignmentFlag.AlignRight,
        )

        for y, templates in bands:
            for template, alignment in zip(templates, alignments):
                text = expand_header(template, context)
                if not text:
                    continue
                painter.drawText(
                    QRectF(0.0, y, width, _HEADER_FONT_POINTS * 1.6),
                    int(alignment | Qt.AlignmentFlag.AlignVCenter),
                    text,
                )
        painter.restore()

    def _render_to_device(self, device: QPagedPaintDevice) -> int:
        """Render every page onto any paged device and return the count.

        Printers and PDF writers share this path so that printed output and
        exported PDFs cannot drift apart.
        """
        if self.page_count == 0:
            return 0

        painter = QPainter()
        if not painter.begin(device):  # pragma: no cover - device failure
            raise RuntimeError("Could not start painting on the output device")
        try:
            dpi = float(painter.device().logicalDpiX())
            for index in range(self.page_count):
                if index and not device.newPage():  # pragma: no cover
                    raise RuntimeError("The output device refused a new page")
                self.render_page(painter, index, dpi)
        finally:
            painter.end()
        return self.page_count

    def print_to(self, printer: QPrinter) -> int:
        """Render every page to a configured printer and return the count."""
        apply_setup_to_printer(printer, self.setup)
        return self._render_to_device(printer)

    def export_pdf(self, path: str | Path) -> Path:
        """Render the worksheet to a PDF file and return its path.

        This uses a PDF writer rather than a printer set to PDF output, so
        exporting works on machines with no printer drivers installed and
        never touches the Windows print spooler.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        writer = QPdfWriter(str(target))
        writer.setTitle(self.document_name or self.sheet.name)
        writer.setCreator(PRODUCT_NAME)
        writer.setResolution(600)
        apply_setup_to_paged_device(writer, self.setup)
        self._render_to_device(writer)
        return target
