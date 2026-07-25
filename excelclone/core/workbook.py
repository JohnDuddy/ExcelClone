"""Multi-sheet workbook and defined-name model."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace

from excelclone.core.refs import (
    CellReference,
    RangeReference,
    Reference,
    parse_a1,
    parse_r1c1,
)
from excelclone.core.sheet import Sheet

_INVALID_SHEET_CHARACTERS = frozenset(r"[]:*?/\\")
_DEFINED_NAME_RE = re.compile(r"^[A-Za-z_\\][A-Za-z0-9_.\\]*$")


@dataclass(frozen=True, slots=True)
class DefinedName:
    """A workbook- or sheet-scoped symbolic reference."""

    name: str
    reference: Reference
    scope: str | None = None


class Workbook:
    """Ordered sheets, active-sheet state, and case-insensitive defined names."""

    def __init__(self, *, create_default: bool = True) -> None:
        self._sheets: list[Sheet] = []
        self._active_sheet: Sheet | None = None
        self._defined_names: dict[tuple[str | None, str], DefinedName] = {}
        if create_default:
            self.add_sheet("Sheet1")

    def __len__(self) -> int:
        return len(self._sheets)

    def __iter__(self) -> Iterator[Sheet]:
        return iter(self._sheets)

    @property
    def sheet_names(self) -> tuple[str, ...]:
        """Return sheet names in tab order."""
        return tuple(sheet.name for sheet in self._sheets)

    @property
    def active_sheet(self) -> Sheet:
        """Return the active sheet."""
        if self._active_sheet is None:
            raise RuntimeError("Workbook contains no active sheet")
        return self._active_sheet

    @active_sheet.setter
    def active_sheet(self, sheet: str | int | Sheet) -> None:
        selected = sheet if isinstance(sheet, Sheet) else self.get_sheet(sheet)
        if selected not in self._sheets:
            raise ValueError("Active sheet must belong to this workbook")
        self._active_sheet = selected

    @property
    def active_sheet_index(self) -> int:
        """Return the zero-based index of the active sheet."""
        return self._sheets.index(self.active_sheet)

    @property
    def total_populated_cells(self) -> int:
        """Return the allocated cell count across every sheet."""
        return sum(sheet.populated_count for sheet in self._sheets)

    @property
    def defined_names(self) -> tuple[DefinedName, ...]:
        """Return defined names in deterministic scope/name order."""
        return tuple(
            sorted(
                self._defined_names.values(),
                key=lambda item: ((item.scope or "").casefold(), item.name.casefold()),
            )
        )

    def get_sheet(self, identifier: str | int) -> Sheet:
        """Find a sheet by case-insensitive name or zero-based index."""
        if isinstance(identifier, int):
            try:
                return self._sheets[identifier]
            except IndexError:
                raise IndexError(f"Sheet index out of range: {identifier}") from None
        folded = identifier.casefold()
        for sheet in self._sheets:
            if sheet.name.casefold() == folded:
                return sheet
        raise KeyError(f"Unknown sheet: {identifier!r}")

    def index_of(self, identifier: str | int) -> int:
        """Return the zero-based tab index of a sheet."""
        return self._sheets.index(self.get_sheet(identifier))

    def add_sheet(self, name: str | None = None, *, index: int | None = None) -> Sheet:
        """Add and return a new sheet."""
        selected_name = self._next_sheet_name() if name is None else name
        self._validate_new_sheet_name(selected_name)
        sheet = Sheet(selected_name)
        if index is None:
            self._sheets.append(sheet)
        else:
            if not 0 <= index <= len(self._sheets):
                raise IndexError(f"Sheet insertion index out of range: {index}")
            self._sheets.insert(index, sheet)
        if self._active_sheet is None:
            self._active_sheet = sheet
        return sheet

    def delete_sheet(self, identifier: str | int) -> Sheet:
        """Delete a sheet while preserving a valid active-sheet selection."""
        if len(self._sheets) == 1:
            raise ValueError("Cannot delete the last visible sheet")
        sheet = self.get_sheet(identifier)
        index = self._sheets.index(sheet)
        self._sheets.remove(sheet)
        if self._active_sheet is sheet:
            self._active_sheet = self._sheets[min(index, len(self._sheets) - 1)]
        self._defined_names = {
            key: value
            for key, value in self._defined_names.items()
            if value.scope is None or value.scope.casefold() != sheet.name.casefold()
        }
        return sheet

    def restore_sheet(self, sheet: Sheet, *, index: int | None = None) -> None:
        """Restore a previously removed sheet object at a tab position."""
        self._validate_new_sheet_name(sheet.name)
        destination = len(self._sheets) if index is None else index
        if not 0 <= destination <= len(self._sheets):
            raise IndexError(f"Sheet insertion index out of range: {destination}")
        self._sheets.insert(destination, sheet)
        if self._active_sheet is None:
            self._active_sheet = sheet

    def rename_sheet(self, identifier: str | int, new_name: str) -> Sheet:
        """Rename a sheet and update defined-name references atomically."""
        sheet = self.get_sheet(identifier)
        if sheet.name.casefold() != new_name.casefold():
            self._validate_new_sheet_name(new_name)
        old_name = sheet.name
        sheet.name = new_name

        updated_names: dict[tuple[str | None, str], DefinedName] = {}
        for defined_name in self._defined_names.values():
            scope = (
                new_name
                if defined_name.scope is not None
                and defined_name.scope.casefold() == old_name.casefold()
                else defined_name.scope
            )
            reference = _rename_reference_sheet(
                defined_name.reference,
                old_name=old_name,
                new_name=new_name,
            )
            updated = replace(defined_name, reference=reference, scope=scope)
            updated_names[_name_key(updated.name, updated.scope)] = updated
        self._defined_names = updated_names
        return sheet

    def move_sheet(self, identifier: str | int, index: int) -> None:
        """Move a sheet to a zero-based tab position."""
        if not 0 <= index < len(self._sheets):
            raise IndexError(f"Sheet destination index out of range: {index}")
        sheet = self.get_sheet(identifier)
        self._sheets.remove(sheet)
        self._sheets.insert(index, sheet)

    def duplicate_sheet(
        self,
        identifier: str | int,
        *,
        name: str | None = None,
    ) -> Sheet:
        """Copy a sheet directly after its source."""
        source = self.get_sheet(identifier)
        selected_name = name if name is not None else self._next_copy_name(source.name)
        self._validate_new_sheet_name(selected_name)
        duplicate = source.copy(name=selected_name)
        source_index = self._sheets.index(source)
        self._sheets.insert(source_index + 1, duplicate)
        return duplicate

    def define_name(
        self,
        name: str,
        reference: Reference | str,
        *,
        scope: str | None = None,
    ) -> DefinedName:
        """Create a workbook- or sheet-scoped defined name."""
        self._validate_defined_name(name)
        normalized_scope = self.get_sheet(scope).name if scope is not None else None
        resolved_reference = (
            parse_a1(reference, default_sheet=normalized_scope or self.active_sheet.name)
            if isinstance(reference, str)
            else reference
        )
        key = _name_key(name, normalized_scope)
        if key in self._defined_names:
            raise ValueError(f"Defined name already exists in scope: {name!r}")
        defined_name = DefinedName(name, resolved_reference, normalized_scope)
        self._defined_names[key] = defined_name
        return defined_name

    def get_name(self, name: str, *, scope: str | None = None) -> DefinedName:
        """Resolve a local defined name first, then its workbook fallback."""
        if scope is not None:
            canonical_scope = self.get_sheet(scope).name
            local = self._defined_names.get(_name_key(name, canonical_scope))
            if local is not None:
                return local
        global_name = self._defined_names.get(_name_key(name, None))
        if global_name is not None:
            return global_name
        raise KeyError(f"Unknown defined name: {name!r}")

    def delete_name(self, name: str, *, scope: str | None = None) -> DefinedName:
        """Delete and return a defined name."""
        canonical_scope = self.get_sheet(scope).name if scope is not None else None
        try:
            return self._defined_names.pop(_name_key(name, canonical_scope))
        except KeyError:
            raise KeyError(f"Unknown defined name: {name!r}") from None

    def copy(self) -> Workbook:
        """Create an independent workbook with the same data and active sheet."""
        duplicate = Workbook(create_default=False)
        duplicate._sheets = [sheet.copy() for sheet in self._sheets]
        duplicate._active_sheet = duplicate._sheets[self.active_sheet_index]
        duplicate._defined_names = self._defined_names.copy()
        return duplicate

    def _next_sheet_name(self) -> str:
        number = 1
        existing = {name.casefold() for name in self.sheet_names}
        while f"Sheet{number}".casefold() in existing:
            number += 1
        return f"Sheet{number}"

    def _next_copy_name(self, source_name: str) -> str:
        number = 2
        existing = {name.casefold() for name in self.sheet_names}
        while f"{source_name} ({number})".casefold() in existing:
            number += 1
        return f"{source_name} ({number})"

    def _validate_new_sheet_name(self, name: str) -> None:
        if not name or len(name) > 31:
            raise ValueError("Sheet name must contain 1 to 31 characters")
        if any(character in _INVALID_SHEET_CHARACTERS for character in name):
            raise ValueError(f"Sheet name contains an invalid character: {name!r}")
        if name.startswith("'") or name.endswith("'"):
            raise ValueError("Sheet name cannot begin or end with an apostrophe")
        if any(sheet.name.casefold() == name.casefold() for sheet in self._sheets):
            raise ValueError(f"Sheet name already exists: {name!r}")

    @staticmethod
    def _validate_defined_name(name: str) -> None:
        if not _DEFINED_NAME_RE.fullmatch(name):
            raise ValueError(f"Invalid defined name: {name!r}")
        try:
            parse_a1(name)
        except ValueError:
            pass
        else:
            raise ValueError(f"Defined name resembles an A1 reference: {name!r}")
        try:
            parse_r1c1(name, origin=(0, 0))
        except ValueError:
            return
        raise ValueError(f"Defined name resembles an R1C1 reference: {name!r}")


def _name_key(name: str, scope: str | None) -> tuple[str | None, str]:
    return (scope.casefold() if scope is not None else None, name.casefold())


def _rename_reference_sheet(
    reference: Reference,
    *,
    old_name: str,
    new_name: str,
) -> Reference:
    if isinstance(reference, CellReference):
        if reference.sheet is not None and reference.sheet.casefold() == old_name.casefold():
            return replace(reference, sheet=new_name)
        return reference
    return RangeReference(
        _rename_reference_sheet(
            reference.start,
            old_name=old_name,
            new_name=new_name,
        ),
        _rename_reference_sheet(
            reference.end,
            old_name=old_name,
            new_name=new_name,
        ),
        whole_row=reference.whole_row,
        whole_column=reference.whole_column,
    )
