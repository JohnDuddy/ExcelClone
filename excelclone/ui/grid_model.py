"""Virtualized Qt table model over a sparse core sheet."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont

from excelclone.commands.base import CommandHistory
from excelclone.commands.edits import SetCellCommand
from excelclone.core.engine import FormulaEngine, SpillCellReadOnlyError
from excelclone.core.refs import MAX_COLUMNS, MAX_ROWS, index_to_column
from excelclone.core.tokenizer import FormulaSyntaxError

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
        if role == Qt.ItemDataRole.DisplayRole:
            return _display_text(cell.display_value)
        if role == Qt.ItemDataRole.EditRole:
            return "" if cell.raw_input is None else str(cell.raw_input)
        if role == Qt.ItemDataRole.ToolTipRole:
            if cell.error is not None:
                return cell.error
            return str(cell.raw_input) if cell.is_formula else None
        if role == Qt.ItemDataRole.FontRole:
            font = QFont(cell.format.font_family, round(cell.format.font_size))
            font.setBold(cell.format.bold)
            font.setItalic(cell.format.italic)
            font.setUnderline(cell.format.underline)
            return font
        if role == Qt.ItemDataRole.ForegroundRole:
            return QBrush(QColor(cell.format.font_color))
        if role == Qt.ItemDataRole.BackgroundRole and cell.format.fill_color:
            return QBrush(QColor(cell.format.fill_color))
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
            }.get(cell.format.horizontal_alignment, Qt.AlignmentFlag.AlignLeft)
            vertical = {
                "top": Qt.AlignmentFlag.AlignTop,
                "center": Qt.AlignmentFlag.AlignVCenter,
                "bottom": Qt.AlignmentFlag.AlignBottom,
            }.get(cell.format.vertical_alignment, Qt.AlignmentFlag.AlignBottom)
            return horizontal | vertical
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
        command = SetCellCommand(
            self.engine,
            self.active_sheet_name,
            index.row(),
            index.column(),
            _parse_user_input(value),
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

    def refresh(self) -> None:
        """Notify views that sparse workbook content may have changed."""
        self.layoutChanged.emit()

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


def _display_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)

