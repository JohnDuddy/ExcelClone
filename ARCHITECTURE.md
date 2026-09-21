# Architecture

Duddy Spreadsheet separates spreadsheet behavior from its desktop presentation. The core
is a deep module: callers learn a small workbook interface while parsing,
dependency tracking, recalculation, spill management, and formatting remain
local to its implementation.

## Data Flow

```text
User gesture
    |
    v
Qt view/model -----> Command interface -----> Workbook / Sheet
    ^                                             |
    |                                             v
    +---------- display values <---------- Recalculation engine
                                                  |
Disk dialogs -> I/O adapter <---------------------+
```

Qt types stop at the UI seam. File-format types stop at the I/O seam. Core
objects never import either.

I/O adapters translate at the boundary: OpenPyXL types are converted to domain
cells and formats, delimited text produces one sparse sheet, and native Duddy Spreadsheet
stores versioned JSON inside a ZIP. Loaders return domain workbooks; XLSX also
returns an immutable warning list for content that cannot be represented.

## Recalculation

The formula parser exposes cell and range precedents while building an AST.
On edit, the dependency graph replaces the edited cell's incoming edges, marks
its transitive dependents dirty, detects cycles, and evaluates the affected
subgraph in topological order. Cached values make display reads constant-time.
Volatile cells are added to every recalculation pass.

## Commands

Every mutation is represented by a command with `do`, `undo`, and optional
`merge_with` behavior. Commands retain only the prior state required to reverse
their own mutation. The UI submits commands to a bounded history rather than
editing a sheet directly, giving the same seam to toolbar actions, keyboard
editing, paste, sorting, and tests.

Small edits retain prior cells or metadata. Structural and data-table commands
snapshot the immutable-cell workbook graph, perform one headless operation,
and restore that graph on undo. Formula AST translation runs before sparse
coordinates move; a dependency-index rebuild then recalculates the resulting
workbook without stale graph edges.

## Charts

`ChartSpec` is immutable workbook metadata; `chart_data` reads current cached
values and emits renderer-neutral categories and numeric series.
`recommend_charts` scores that shape using deterministic, explainable rules;
`expand_chart_range` discovers the connected sparse data island around a single
selection. Neither service depends on Qt or matplotlib.

`CHART_CATALOG` lists every chart type with its label, Excel family, purpose,
and expected data layout, in Excel's gallery order. Menus, the ribbon
galleries, Chart Studio, and the tutorial's reference tables are all generated
from it. The Qt-free core also holds the analytical math the renderer needs:
trendline regression in Excel's forms, error-bar amounts, 100% stacking,
Pareto ordering, bubble pairing, treemap hierarchies, and squarified layout.

`duddysheet.ui.chart_renderer` draws each chart family, then applies the chart
elements and axis format in one shared finishing pass. The Qt Chart Studio
owns live preview and editing, while `ChartPanel` owns the interactive
matplotlib figure, navigation, clipboard, and PNG/SVG/PDF export. Both call
the same renderer. Commands add, replace, or remove complete immutable
specifications, preserving undo, native persistence, structural translation,
and live refresh without duplicating source data.

Sparklines are sheet metadata beside charts: one immutable `Sparkline` per
cell, created by commands and translated by structural edits. The grid model
exposes each one with its live values through a dedicated role, and the cell
delegate paints it. They are persisted from native schema 4.

## Financial Analysis

Financial formulas remain ordinary registry functions with shared day-count
and coupon-schedule helpers. Goal Seek, scenarios, and sensitivity tables are
headless services that probe a copied `Workbook` through a private
`FormulaEngine`; exploratory values therefore never enter the live dependency
graph. The UI applies only a confirmed Goal Seek result or completed output
matrix through `SetCellCommand` or `SetRangeCommand`.

Built-in models are factories that return normal workbooks containing values,
formulas, and formats. They do not introduce a separate template file format or
runtime dependency. A final dependency-index rebuild recalculates every model
before it reaches the UI. Model audit consumes only public workbook cells and
parser reference metadata, keeping Qt out of diagnostics.

## Performance Shape

Sheets allocate cells only when content or non-default formatting exists. The Qt
model advertises Excel-sized dimensions without materializing them. Dependency
edges and cached formula values scale with populated and referenced cells.

Frozen panes are three clipped `QTableView` overlays sharing the same virtual
model and selection state; no cells are copied. Split view adds a second
independently scrollable `GridView` over that model. Fill-handle gestures emit
the same `FillRangeCommand` used by keyboard filling.

## Recovery And Distribution

Dirty workbooks are serialized atomically through the native Duddy Spreadsheet adapter
every five minutes. A small JSON sidecar identifies the source path and UTC
timestamp; recovery loads through the normal versioned file boundary. Normal
save removes the matching snapshot. Diagnostics use a bounded rotating log.

The release is a frozen application and a signed Windows installer, described
under Packaging below. Neither installation nor use makes any network call.

## Printing

`core/printing.py` turns a sheet and an immutable `PageSetup` into immutable
`Page` values without importing Qt. It resolves row heights and column widths
to points, excludes hidden and filtered lines, applies explicit or
fit-to-page scaling, reserves space for repeated title rows and columns, and
tiles the remaining grid into pages. A row or column larger than the page
still occupies one page rather than looping.

`ui/printing.py` paints those pages. It applies device resolution once as a
transform so every measurement stays in points, then draws fills, text,
borders, gridlines, headings, and header/footer bands. Print preview, the
printer, and PDF export all drive one renderer over one pagination, so they
cannot drift apart. PDF export uses a PDF writer rather than a printer, which
avoids the Windows print spooler entirely.

Page setup is sheet metadata, persisted in the native format since schema 3.
A malformed stored setup falls back to defaults rather than refusing the file.

## Licensing

`core/licensing.py` is Qt-free and takes its storage directory as an
argument, so the whole activation lifecycle is testable without touching a
real profile. Licence keys carry a JSON payload signed with Ed25519; the
build holds only the public key, so verification needs no network and no
secret. Trial state is HMAC-bound to the machine, which deters copying it
between installs or editing the start date.

The UI layer adds an activation dialog and a status-bar indicator. Entitlement
is advisory to the shell rather than enforced in the engine: expiry prompts
for a key and never closes over unsaved work.

## Packaging

The release is a PyInstaller onedir freeze wrapped in an Inno Setup installer.
Qt modules outside PySide6-Essentials, unused matplotlib backends, Python's
TLS stack, Qt's software OpenGL fallback, and Qt networking are excluded.
Excluding Qt networking makes the product's offline claim structural.

`duddysheet/selftest.py` runs inside the packaged application and exercises
formulas, both file formats, the bundled models, charts, PDF export, and
licensing. The build fails when it does not pass, which catches breakage that
only exists after freezing.
