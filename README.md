# Duddy Spreadsheet

Duddy Spreadsheet is a personal, offline spreadsheet application for Windows 11. It
provides an Excel-sized virtual grid, formulas, financial modeling, charts,
formatting, data tools, and `.xlsx`, `.csv`, `.tsv`, and lossless `.dsheet`
files without requiring Microsoft Office or an internet connection.

## Install

1. Extract `DuddySpreadsheet.zip`.
2. Open the extracted `DuddySpreadsheet` folder.
3. Double-click `INSTALL.bat`.
4. Launch **DuddySpreadsheet** from the Desktop shortcut.

The installer verifies Python 3.13, creates `.venv` inside the extracted
folder, installs only from the included `wheelhouse`, verifies the application,
and creates a direct `pythonw.exe` shortcut. Rerunning it upgrades the same
installation and shortcut safely.

For development, run:

```powershell
python -m pip install -r requirements.txt
python run.py
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N`, `Ctrl+O`, `Ctrl+S` | New, open, save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+Z`, `Ctrl+Y` | Undo, redo |
| `Ctrl+C`, `Ctrl+V` | Copy, paste |
| `Ctrl+Enter` | Fill the selection with the current cell |
| `Ctrl+D`, `Ctrl+R` | Fill down, fill right |
| `Delete` | Clear selected contents |
| `F2` | Edit the active cell |
| `F4` | Cycle relative/absolute references while editing a formula |
| `F9` | Recalculate the workbook |
| `Ctrl+~` | Toggle formula display |

## Formula Reference

Open **Formulas > Insert Function** for searchable signatures and descriptions
for all 196 registered functions.

| Category | Functions |
|---|---|
| Math and trig | `SUM`, `SUMIF(S)`, `SUMPRODUCT`, `ROUND`, `CEILING`, `FLOOR`, `MOD`, `POWER`, `SQRT`, `RAND`, `GCD`, `SIN`, `COS`, `PI`, and related functions |
| Statistical | `AVERAGE(IF/S)`, `COUNT(IF/S)`, `MEDIAN`, `MODE`, `MAXIFS`, `MINIFS`, `STDEV`, `VAR`, `PERCENTILE`, `CORREL`, `FORECAST`, `TREND` |
| Logical | `IF`, `IFS`, `IFERROR`, `IFNA`, `AND`, `OR`, `NOT`, `XOR`, `SWITCH` |
| Text | `CONCAT`, `TEXTJOIN`, `LEFT`, `RIGHT`, `MID`, `FIND`, `SEARCH`, `SUBSTITUTE`, `TEXT`, `VALUE`, `TEXTBEFORE`, `TEXTAFTER` |
| Lookup and arrays | `VLOOKUP`, `HLOOKUP`, `XLOOKUP`, `INDEX`, `MATCH`, `XMATCH`, `OFFSET`, `INDIRECT`, `UNIQUE`, `SORT`, `FILTER`, `TRANSPOSE` |
| Date and time | `TODAY`, `NOW`, `DATE`, `TIME`, `YEAR`, `MONTH`, `DAY`, `WEEKDAY`, `EOMONTH`, `DATEDIF`, `NETWORKDAYS`, `WORKDAY`, `YEARFRAC` |
| Financial | Annuities and loans; periodic and irregular cash-flow returns; effective/nominal rates; cumulative interest and principal; fixed, declining, and sum-of-years depreciation; bond price, yield, duration, accrued interest, coupon dates, discount securities, Treasury bills, and fractional-dollar quotations |
| Information | `ISBLANK`, `ISNUMBER`, `ISTEXT`, `ISERROR`, `ISERR`, `ISNA`, `ISLOGICAL`, `TYPE`, `ERROR.TYPE` |

Dynamic-array results spill into adjacent cells and report `#SPILL!` if a
target is occupied. Formula errors propagate as spreadsheet values rather than
crashing the application.

## Charts And Visual Analysis

The **Insert** ribbon offers two chart paths:

- **Quick Chart** expands a single selected cell to its contiguous data table,
  detects headers, ranks suitable visualizations, and creates the best match in
  one click.
- **Chart Studio** shows five explained recommendations beside a live preview,
  then exposes data, design, theme, label, trendline, extrema, grid, legend,
  number-format, and secondary-axis controls.

Seventeen live chart types are available: clustered and stacked columns/bars,
line, step, area, stacked area, pie, donut, scatter, histogram, box-and-whisker,
waterfall, heatmap, radar, and column/line combo. Charts update after edits or
recalculation, remain bound through row/column changes and sheet renames, and
can be edited with undo/redo. Panels include zoom/pan, clipboard copying, and
print-quality PNG, SVG, or PDF export.

## Financial Modeling

Open the **Financial** ribbon tab or menu for the modeling toolkit:

- **Financial Help** (or `F1`) opens the complete offline guide with searchable
  reference pages for all 46 financial functions, copyable examples, nine
  modeling tutorials, sign/rate/day-count quick-reference tables,
  troubleshooting, and instructions for each built-in model.
- **Model Templates** creates an editable DCF, three-statement forecast, LBO,
  loan amortization, rental property, budget/forecast, or Financial
  Calculations Lab workbook. The lab provides synthetic inputs, 76 live
  calculations, and 12 editable charts across four galleries. Templates use
  conventional blue/yellow assumptions, green cross-sheet links, complete
  schedules, output summaries, and model checks.
- **Goal Seek** solves one numeric input for a target formula on a cloned
  workbook. The live input changes only after confirmation and can be undone.
- **Sensitivity** calculates one- or two-variable data tables and writes the
  result as one undoable range edit.
- **Scenarios** evaluates named assumption sets against selected output cells
  without changing source assumptions, then writes a comparison table.
- **Model Audit** recalculates the workbook and prioritizes formula errors,
  circulars, blank direct precedents, uncalculated formulas, and embedded
  constants that merit review.

The financial library includes 46 worksheet functions across loans, cash
flows, rates, depreciation, coupon securities, discount securities, and
Treasury bills. Duddy Spreadsheet remains offline and deterministic: it does not ship
VBA, pivots, Power Query, live market feeds, or a multi-variable optimization
solver.

The guide is also available from **Help > Financial Functions Guide**.

## Files And Recovery

- `.dsheet` is the lossless native format.
- `.xlsx` preserves supported formulas, values, styles, dimensions, names,
  merges, filters, validation, frozen panes, and external/internal hyperlinks.
  Click a linked cell to open its URL or navigate to its workbook destination.
  Duddy Spreadsheet reports unsupported features before dropping them.
- `.csv` and `.tsv` import and export the active sheet.
- Unsaved workbooks receive a recovery snapshot every five minutes under
  `%LOCALAPPDATA%\DuddySpreadsheet\autosave`.
- Logs rotate under `%LOCALAPPDATA%\DuddySpreadsheet\logs`.

## Troubleshooting

| Problem | Resolution |
|---|---|
| Installer cannot find Python | Install 64-bit Python 3.13 from `python.org`, including the Python launcher, then rerun `INSTALL.bat`. |
| Offline package installation fails | Extract the complete ZIP again; do not remove or rename `wheelhouse`. |
| Shortcut was moved or removed | Rerun `INSTALL.bat`; it recreates one Desktop shortcut without duplicating it. |
| An XLSX warning appears | Save as `.dsheet` when the source uses unsupported macros, pivots, embedded objects, or external charts. |
| The app closed with unsaved work | Relaunch and choose **Recover** in the startup prompt. |
| A formula shows `#CIRC!` | Remove the circular reference identified in the status bar. |

## Verify

```powershell
python -W error -m pytest
python -W error -m pytest -m "not performance" --cov=duddysheet/core
python -m pytest tests/test_performance.py
```

See `TESTING.md` for fixture and release-verification details.
