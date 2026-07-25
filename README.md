# OpenGrid

OpenGrid is a personal, offline spreadsheet application for Windows 11. It
provides an Excel-sized virtual grid, formulas, charts, formatting, data tools,
and `.xlsx`, `.csv`, `.tsv`, and lossless `.ogrid` files without requiring
Microsoft Office or an internet connection.

## Install

1. Extract `ExcelClone.zip`.
2. Open the extracted `ExcelClone` folder.
3. Double-click `INSTALL.bat`.
4. Launch **ExcelClone** from the Desktop shortcut.

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
for all 162 registered functions.

| Category | Functions |
|---|---|
| Math and trig | `SUM`, `SUMIF(S)`, `SUMPRODUCT`, `ROUND`, `CEILING`, `FLOOR`, `MOD`, `POWER`, `SQRT`, `RAND`, `GCD`, `SIN`, `COS`, `PI`, and related functions |
| Statistical | `AVERAGE(IF/S)`, `COUNT(IF/S)`, `MEDIAN`, `MODE`, `MAXIFS`, `MINIFS`, `STDEV`, `VAR`, `PERCENTILE`, `CORREL`, `FORECAST`, `TREND` |
| Logical | `IF`, `IFS`, `IFERROR`, `IFNA`, `AND`, `OR`, `NOT`, `XOR`, `SWITCH` |
| Text | `CONCAT`, `TEXTJOIN`, `LEFT`, `RIGHT`, `MID`, `FIND`, `SEARCH`, `SUBSTITUTE`, `TEXT`, `VALUE`, `TEXTBEFORE`, `TEXTAFTER` |
| Lookup and arrays | `VLOOKUP`, `HLOOKUP`, `XLOOKUP`, `INDEX`, `MATCH`, `XMATCH`, `OFFSET`, `INDIRECT`, `UNIQUE`, `SORT`, `FILTER`, `TRANSPOSE` |
| Date and time | `TODAY`, `NOW`, `DATE`, `TIME`, `YEAR`, `MONTH`, `DAY`, `WEEKDAY`, `EOMONTH`, `DATEDIF`, `NETWORKDAYS`, `WORKDAY`, `YEARFRAC` |
| Financial | `PMT`, `PPMT`, `IPMT`, `PV`, `FV`, `NPV`, `IRR`, `XNPV`, `XIRR`, `RATE`, `NPER`, `SLN` |
| Information | `ISBLANK`, `ISNUMBER`, `ISTEXT`, `ISERROR`, `ISERR`, `ISNA`, `ISLOGICAL`, `TYPE`, `ERROR.TYPE` |

Dynamic-array results spill into adjacent cells and report `#SPILL!` if a
target is occupied. Formula errors propagate as spreadsheet values rather than
crashing the application.

## Files And Recovery

- `.ogrid` is the lossless native format.
- `.xlsx` preserves supported formulas, values, styles, dimensions, names,
  merges, filters, validation, frozen panes, and external/internal hyperlinks.
  Click a linked cell to open its URL or navigate to its workbook destination.
  OpenGrid reports unsupported features before dropping them.
- `.csv` and `.tsv` import and export the active sheet.
- Unsaved workbooks receive a recovery snapshot every five minutes under
  `%LOCALAPPDATA%\ExcelClone\autosave`.
- Logs rotate under `%LOCALAPPDATA%\ExcelClone\logs`.

## Troubleshooting

| Problem | Resolution |
|---|---|
| Installer cannot find Python | Install 64-bit Python 3.13 from `python.org`, including the Python launcher, then rerun `INSTALL.bat`. |
| Offline package installation fails | Extract the complete ZIP again; do not remove or rename `wheelhouse`. |
| Shortcut was moved or removed | Rerun `INSTALL.bat`; it recreates one Desktop shortcut without duplicating it. |
| An XLSX warning appears | Save as `.ogrid` when the source uses unsupported macros, pivots, embedded objects, or external charts. |
| The app closed with unsaved work | Relaunch and choose **Recover** in the startup prompt. |
| A formula shows `#CIRC!` | Remove the circular reference identified in the status bar. |

## Verify

```powershell
python -W error -m pytest
python -W error -m pytest -m "not performance" --cov=excelclone/core
python -m pytest tests/test_performance.py
```

See `TESTING.md` for fixture and release-verification details.
