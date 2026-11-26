"""Virtualized Qt table model over a sparse core sheet."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import SetCellCommand
from duddysheet.core.conditional import ConditionalFormatEngine, ConditionalResult
from duddysheet.core.sparkline import Sparkline, sparkline_at, sparkline_values
from duddysheet.core.data_tools import validation_for_cell, validate_value
from duddysheet.core.engine import FormulaEngine, SpillCellReadOnlyError
from duddysheet.core.formats import format_value
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, index_to_column
from duddysheet.core.tokenizer import FormulaSyntaxError

DATA_BAR_ROLE = int(Qt.ItemDataRole.UserRole) + 1
ICON_ROLE = int(Qt.ItemDataRole.UserRole) + 2
EFFECTIVE_FORMAT_ROLE = int(Qt.ItemDataRole.UserRole) + 3
HYPERLINK_ROLE = int(Qt.ItemDataRole.UserRole) + 4
SPARKLINE_ROLE = int(Qt.ItemDataRole.UserRole) + 5

_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+[Ee][+-]?[0-9]+"
    r"|[0-9]+\.[0-9]*[Ee][+-]?[0-9]+)$"
)


class GridModel(QAbstractTableModel):
    """Advertise the full Excel grid while reading only sparse cells."""

    editRejected = Signal(str)

    def __init__(
        self,
        engine: FormulaEngine,
        history: CommandHistory,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.history = history
        self.active_sheet_name = engine.workbook.active_sheet.name
        self.last_error = ""
        self.formula_view = False
        self.conditional_formats = ConditionalFormatEngine(engine.workbook)
        self.history.add_listener(self._history_changed)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else MAX_ROWS

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else MAX_COLUMNS

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid():
            return None
        cell = self.sheet.get_cell(index.row(), index.column())
        presentation = self._presentation(index)
        cell_format = presentation.format
        if role == Qt.ItemDataRole.DisplayRole:
            if self.formula_view and cell.is_formula:
                return cell.raw_input
            if cell.display_value is None:
                return None
            return format_value(cell.display_value, cell_format.number_format).text
        if role == Qt.ItemDataRole.EditRole:
            if (
                self.sheet.protection is not None
                and cell_format.formula_hidden
                and cell.is_formula
            ):
                return ""
            return "" if cell.raw_input is None else str(cell.raw_input)
        if role == Qt.ItemDataRole.ToolTipRole:
            if cell.error is not None:
                return cell.error
            if cell.hyperlink is not None:
                return cell.hyperlink.tooltip or (
                    f"Open link: {cell.hyperlink.target}"
                )
            return str(cell.raw_input) if cell.is_formula else None
        if role == Qt.ItemDataRole.FontRole:
            font = QFont(cell_format.font_family, round(cell_format.font_size))
            font.setBold(cell_format.bold)
            font.setItalic(cell_format.italic)
            font.setUnderline(cell_format.underline or cell.hyperlink is not None)
            font.setStrikeOut(cell_format.strikethrough)
            return font
        if role == Qt.ItemDataRole.ForegroundRole:
            if cell.hyperlink is not None:
                return QBrush(QColor("#0563c1"))
            formatted = format_value(cell.display_value, cell_format.number_format)
            return QBrush(QColor(formatted.color or cell_format.font_color))
        if role == Qt.ItemDataRole.BackgroundRole and cell_format.fill_color:
            return QBrush(QColor(cell_format.fill_color))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            horizontal = {
                "left": Qt.AlignmentFlag.AlignLeft,
                "center": Qt.AlignmentFlag.AlignHCenter,
                "right": Qt.AlignmentFlag.AlignRight,
                "general": (
                    Qt.AlignmentFlag.AlignRight
                    if isinstance(cell.display_value, (int, float))
                    else Qt.AlignmentFlag.AlignLeft
                ),
            }.get(cell_format.horizontal_alignment, Qt.AlignmentFlag.AlignLeft)
            vertical = {
                "top": Qt.AlignmentFlag.AlignTop,
                "center": Qt.AlignmentFlag.AlignVCenter,
                "bottom": Qt.AlignmentFlag.AlignBottom,
            }.get(cell_format.vertical_alignment, Qt.AlignmentFlag.AlignBottom)
            return horizontal | vertical
        if role == DATA_BAR_ROLE:
            return presentation.data_bar
        if role == ICON_ROLE:
            return presentation.icon
        if role == EFFECTIVE_FORMAT_ROLE:
            return cell_format
        if role == HYPERLINK_ROLE:
            return cell.hyperlink
        if role == SPARKLINE_ROLE:
            return self._sparkline(index)
        return None

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        if self.sheet.get_cell(index.row(), index.column()).is_spill:
            return False
        from duddysheet.core.protection import can_edit_cell

        sheet = self.sheet
        row, column = index.row(), index.column()
        if sheet.pivots:
            from duddysheet.core.pivot import pivot_at

            if pivot_at(sheet, row, column) is not None:
                self.last_error = "Cannot change this part of a PivotTable report."
                self.editRejected.emit(self.last_error)
                return False
        if sheet.data_tables:
            from duddysheet.core.data_table import data_table_at

            if data_table_at(sheet, row, column) is not None:
                self.last_error = "Cannot change part of a data table."
                self.editRejected.emit(self.last_error)
                return False
        if not can_edit_cell(self.sheet, index.row(), index.column()):
            self.last_error = (
                "The cell or chart you're trying to change is on a protected sheet. "
                "To make a change, unprotect the sheet."
            )
            self.editRejected.emit(self.last_error)
            return False
        parsed_value = _parse_user_input(value)
        validation = validation_for_cell(self.sheet, index.row(), index.column())
        if validation is not None:
            result = validate_value(
                validation,
                parsed_value,
                self.engine.workbook,
                self.active_sheet_name,
                (index.row(), index.column()),
            )
            if not result.valid:
                self.last_error = result.message
                self.editRejected.emit(self.last_error)
                return False
        command = SetCellCommand(
            self.engine,
            self.active_sheet_name,
            index.row(),
            index.column(),
            parsed_value,
        )
        if sheet.tables and _touches_table(sheet, row, column):
            from duddysheet.commands.analysis import TableEntryCommand

            command = TableEntryCommand(
                self.engine,
                self.active_sheet_name,
                row,
                column,
                parsed_value,
            )
        try:
            self.history.execute(command)
        except (FormulaSyntaxError, SpillCellReadOnlyError, ValueError) as error:
            self.last_error = str(error)
            self.editRejected.emit(self.last_error)
            return False
        self.last_error = ""
        self._emit_command_changes(index, command)
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not self.sheet.get_cell(index.row(), index.column()).is_spill:
            flags |= Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return (
            index_to_column(section)
            if orientation == Qt.Orientation.Horizontal
            else str(section + 1)
        )

    @property
    def sheet(self):
        """Return the currently displayed core sheet."""
        return self.engine.workbook.get_sheet(self.active_sheet_name)

    def set_active_sheet(self, name: str) -> None:
        """Switch the workbook and model to a sheet by name."""
        selected = self.engine.workbook.get_sheet(name)
        if selected.name == self.active_sheet_name:
            return
        self.beginResetModel()
        self.engine.workbook.active_sheet = selected
        self.active_sheet_name = selected.name
        self.endResetModel()

    def replace_engine(self, engine: FormulaEngine) -> None:
        """Install a newly loaded workbook under one model reset."""
        self.beginResetModel()
        self.engine = engine
        self.active_sheet_name = engine.workbook.active_sheet.name
        self.conditional_formats = ConditionalFormatEngine(engine.workbook)
        self.last_error = ""
        self.endResetModel()

    def refresh(self) -> None:
        """Notify views that sparse workbook content may have changed."""
        self.layoutChanged.emit()

    def set_formula_view(self, enabled: bool) -> None:
        """Show raw formula text instead of calculated values."""
        selected = bool(enabled)
        if selected == self.formula_view:
            return
        self.formula_view = selected
        self.layoutChanged.emit()

    def _presentation(self, index: QModelIndex) -> ConditionalResult:
        return self.conditional_formats.evaluate(
            self.sheet,
            index.row(),
            index.column(),
        )

    def _sparkline(
        self,
        index: QModelIndex,
    ) -> tuple[Sparkline, tuple[float, ...]] | None:
        """Return a cell's sparkline with its current values, if it has one."""
        sheet = self.sheet
        if not sheet.sparklines:
            return None
        sparkline = sparkline_at(sheet.sparklines, index.row(), index.column())
        if sparkline is None:
            return None
        try:
            values = sparkline_values(
                self.engine.workbook, self.active_sheet_name, sparkline
            )
        except KeyError:
            return None
        return sparkline, values

    def _history_changed(self, history: CommandHistory) -> None:
        self.refresh()

    def _emit_command_changes(
        self,
        index: QModelIndex,
        command: SetCellCommand,
    ) -> None:
        addresses = {(
            self.active_sheet_name.casefold(),
            index.row(),
            index.column(),
        )}
        if command.result is not None:
            addresses.update(
                (address.sheet.casefold(), address.row, address.column)
                for address in command.result.recalculated + command.result.circular
            )
        for sheet_name, row, column in addresses:
            if sheet_name == self.active_sheet_name.casefold():
                changed = self.index(row, column)
                self.dataChanged.emit(
                    changed,
                    changed,
                    [
                        Qt.ItemDataRole.DisplayRole,
                        Qt.ItemDataRole.EditRole,
                        Qt.ItemDataRole.ToolTipRole,
                    ],
                )


def _touches_table(sheet: Any, row: int, column: int) -> bool:
    """Whether an entry is inside a table or just below/right of one."""
    for table in sheet.tables:
        if table.contains(row, column):
            return True
        if row == table.bottom + 1 and table.left <= column <= table.right and not table.show_totals:
            return True
        if column == table.right + 1 and table.top <= row <= table.bottom:
            return True
    return False


def _parse_user_input(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value == "":
        return None
    if value.startswith("'"):
        return value[1:]
    if value.startswith("="):
        return value
    upper = value.upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if _INTEGER_RE.fullmatch(value):
        try:
            return int(value)
        except ValueError:
            return value
    if _FLOAT_RE.fullmatch(value):
        try:
            return float(value)
        except ValueError:
            return value
    return value
