"""Virtualized Qt table model over a sparse core sheet."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from excelclone.commands.base import CommandHistory
from excelclone.commands.edits import SetCellCommand
from excelclone.core.conditional import ConditionalFormatEngine, ConditionalResult
from excelclone.core.data_tools import validation_for_cell, validate_value
from excelclone.core.engine import FormulaEngine, SpillCellReadOnlyError
from excelclone.core.formats import format_value
from excelclone.core.refs import MAX_COLUMNS, MAX_ROWS, index_to_column
from excelclone.core.tokenizer import FormulaSyntaxError

DATA_BAR_ROLE = int(Qt.ItemDataRole.UserRole) + 1
ICON_ROLE = int(Qt.ItemDataRole.UserRole) + 2
EFFECTIVE_FORMAT_ROLE = int(Qt.ItemDataRole.UserRole) + 3

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
            return "" if cell.raw_input is None else str(cell.raw_input)
        if role == Qt.ItemDataRole.ToolTipRole:
            if cell.error is not None:
                return cell.error
            return str(cell.raw_input) if cell.is_formula else None
        if role == Qt.ItemDataRole.FontRole:
            font = QFont(cell_format.font_family, round(cell_format.font_size))
            font.setBold(cell_format.bold)
            font.setItalic(cell_format.italic)
            font.setUnderline(cell_format.underline)
            return font
        if role == Qt.ItemDataRole.ForegroundRole:
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
