# OpenGrid Standing Context

Read this file before changing the project.

## Product

OpenGrid is a personal, offline spreadsheet application for Windows 11. The
internal package name is `excelclone`; user-visible branding is
`OpenGrid — Personal Spreadsheet`.

## Fixed Constraints

- Python 3.13 and PySide6 only for the application shell.
- The core engine imports no Qt modules.
- Sheets are sparse dictionaries; allocated memory follows populated cells.
- The grid uses `QTableView` and `QAbstractTableModel`.
- Every mutation reaches the model through a command with undo/redo behavior.
- Runtime code performs no network calls, telemetry, or license checks.
- Runtime dependencies are limited to the exact versions in `requirements.txt`.

## Module Seams

- `excelclone.core`: cell, sheet, workbook, formulas, recalculation, and formats.
  Its interface is pure Python values and domain objects.
- `excelclone.commands`: the only mutation interface used by the UI.
- `excelclone.io`: adapters between core domain objects and disk formats.
- `excelclone.ui`: Qt adapter over core and command interfaces.
- `excelclone.util`: local settings, paths, logging, and autosave support.

Tests exercise behavior through these interfaces. They do not reach into private
implementation details or mock internal collaborators.

## Conventions

- Rows and columns are zero-based internally; user-facing references are A1.
- Public functions and classes have type annotations and concise docstrings.
- Errors use domain values rather than exceptions during formula evaluation.
- Files are UTF-8, line endings are platform-neutral, and source is warning-free.
- A bug fix and its regression test belong to the same commit.
- Before completing a milestone, run the full suite and update `FEATURES.md`,
  `CHANGELOG.md`, and this file.

## Current Milestone

M5 is complete: the virtualized grid, editing, selection summaries, formula bar,
sheet tabs, TSV clipboard, and command history are covered by the regression
suite. The current milestone is M6: number formats, cell presentation,
conditional formatting, delegates, freeze panes, and formula/grid views.

## Known Issues

Advanced formatting and data tools remain scheduled. No shipped M1 through M5
behavior is known to be broken.
