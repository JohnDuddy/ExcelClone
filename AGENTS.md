# Duddy Spreadsheet Standing Context

Read this file before changing the project.

## Product

Duddy Spreadsheet is a personal, offline spreadsheet application for Windows 11. The
internal package name is `duddysheet`; user-visible branding is
`Duddy Spreadsheet`.

## Fixed Constraints

- Python 3.13 and PySide6 only for the application shell.
- The core engine imports no Qt modules.
- Sheets are sparse dictionaries; allocated memory follows populated cells.
- The grid uses `QTableView` and `QAbstractTableModel`.
- Every mutation reaches the model through a command with undo/redo behavior.
- Runtime code performs no network calls, telemetry, or license checks.
- Runtime dependencies are limited to the exact versions in `requirements.txt`.

## Module Seams

- `duddysheet.core`: cell, sheet, workbook, formulas, recalculation, and formats.
  Its interface is pure Python values and domain objects.
- `duddysheet.commands`: the only mutation interface used by the UI.
- `duddysheet.io`: adapters between core domain objects and disk formats.
- `duddysheet.ui`: Qt adapter over core and command interfaces.
- `duddysheet.util`: local settings, paths, logging, and autosave support.

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

M12 is complete. Duddy Spreadsheet includes explainable chart recommendations, Quick
Chart, a live-preview Chart Studio, 17 analytical chart types, five themes,
labels, trendlines, extrema, secondary axes, interactive navigation,
PNG/SVG/PDF export, undoable editing, and lossless native chart persistence.
The prior M11 financial modeling, the 76-calculation/12-chart Financial
Calculations Lab, and comprehensive F1 help remain covered by the release
regression contract.

## Known Issues

No shipped behavior is known to be broken. VBA, pivots, Power Query, live
market feeds, multi-variable optimization, collaboration, and embedded Office
objects remain intentionally outside scope.
