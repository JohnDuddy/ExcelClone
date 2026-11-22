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

M13 is complete. Charting matches Excel's gallery apart from Map charts: 62
chart types across Excel's families (including 100% stacked, 3-D, stock,
surface, treemap, sunburst, Pareto, funnel, and custom combos), every Add
Chart Element item, Excel's axis and series format options, Line, Column, and
Win/Loss sparklines, an Insert menu and ribbon galleries, and a 25-lesson
Charts and Graphing Tutorial under Help. The chart catalog in
`duddysheet.core.chart` is the single source for type names, gallery order,
and tutorial reference tables; rendering lives in `duddysheet.ui.chart_renderer`.
The native schema is 4.

The prior M12 commercial readiness, M11 financial modeling with the Financial
Calculations Lab, and comprehensive F1 help remain covered by the release
regression contract.

## Known Issues

No shipped behavior is known to be broken. VBA, pivots, Power Query, live
market feeds, multi-variable optimization, collaboration, and embedded Office
objects remain intentionally outside scope. Map charts are out of scope
because they need an online geography service. Charts and sparklines persist
only in `.dsheet`; `.xlsx` import and export carry data without them.

## Manuscript Desk workbook links

File > Link selection to Manuscript Desk opens the selected sheet and range in the local document companion. Links use saved native workbooks, including calculated values. Install the matching Manuscript Desk build on Windows to enable the handoff.
