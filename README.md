# Duddy Spreadsheet

**An offline financial modeling workbench that reads and writes Excel files.**

Duddy Spreadsheet is a Windows desktop application for building, auditing, and
presenting financial models on machines where cloud tools are not permitted.
It runs entirely offline, transmits nothing, and needs neither Microsoft
Office nor an internet connection.

## Who it is for

Analysts who cannot use cloud spreadsheets, and teams who would rather not.

If your work happens inside a regulated bank, a defence contractor, a
healthcare provider, a legal practice, or any air-gapped or
data-classification-controlled environment, cloud spreadsheets are usually
prohibited outright and desktop Excel is licensed per seat through a process
you do not control. Duddy Spreadsheet is built for that gap: a purchased,
perpetual, single-file install that works with the network cable unplugged.

**It is deliberately not a general-purpose Excel replacement.** It has no
macros, no pivot tables, no Power Query, and no live market feeds. What it
has is a fast, correct, auditable modeling environment.

## What it does

### Financial modeling

- **46 financial functions** covering loans and annuities, regular and
  irregular cash flows, effective and nominal rates, four depreciation
  methods, coupon securities, discount securities, and Treasury bills.
- **Seven ready-built models** — DCF, three-statement forecast, LBO, loan
  amortisation, rental property, budget/forecast, and a Financial
  Calculations Lab with 76 live calculations across four chart galleries.
  Each is an ordinary editable workbook, not a locked template.
- **Goal Seek, scenarios, and sensitivity tables**, all evaluated on a cloned
  workbook so exploratory values never contaminate your live model or its
  undo history.
- **Model audit** that ranks formula errors, circular references, blank
  precedents, stale caches, and hard-coded constants buried in formulas.

### Spreadsheet engine

- **196 functions** with searchable in-application help.
- Excel-sized virtual grid, dynamic-array spilling with `#SPILL!` reporting,
  and an incremental dependency graph that recalculates only what changed.
- 200-level undo across every mutation, including structural edits.
- Conditional formatting, data validation, sorting, filtering, find/replace,
  remove duplicates, text-to-columns, frozen panes, and split views.
- **Verified against Microsoft Excel**: 200 formulas are cross-checked
  against values Excel itself computed, and the suite fails if they diverge.

### Presenting the work

- **Printing and PDF export** with page setup, print preview, print areas,
  repeating header rows and columns, fit-to-page scaling, and header/footer
  tokens. Page setup is saved with the workbook.
- **17 chart types** that stay bound to their ranges through edits, row and
  column changes, and sheet renames, exportable to PNG, SVG, and PDF.

### Files

| Format | Support |
|---|---|
| `.dsheet` | Native format. Lossless, versioned, migration-safe. |
| `.xlsx` / `.xlsm` | Formulas, values, styles, merges, names, validation, frozen panes, and hyperlinks. Unsupported content is reported before it is dropped, never silently lost. |
| `.csv` / `.tsv` | Import and export of the active sheet. |
| `.ogrid` | Legacy files from earlier versions still open. |

Unsaved work is snapshotted every five minutes and offered back after a
crash.

## Privacy

The application makes no network connection in normal operation. There is no
telemetry, no analytics, no crash reporting, no account, and no update ping.
Licence activation is verified offline against a key compiled into the
build, so it works on an air-gapped machine.

Qt's networking library is excluded from the shipped build entirely, which
makes this a structural property rather than a policy. See PRIVACY.md.

## Installing

Download and run `DuddySpreadsheet-1.0.0-Setup.exe`. Nothing else is
required — no Python, no runtime, no administrator rights if you install for
your user only.

## Licensing

Duddy Spreadsheet is commercial software with a 30-day evaluation period.
See EULA.md for the terms and THIRD-PARTY-NOTICES.md for the components it
includes, which are used under their own licences — notably the Qt libraries
under the LGPL-3.0.

Enter a licence key under **Help > Licence and Activation**.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N`, `Ctrl+O`, `Ctrl+S` | New, open, save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+P` | Print |
| `Ctrl+Shift+P` | Print preview |
| `Ctrl+Z`, `Ctrl+Y` | Undo, redo |
| `Ctrl+C`, `Ctrl+V` | Copy, paste |
| `Ctrl+Enter` | Fill the selection with the current cell |
| `Ctrl+D`, `Ctrl+R` | Fill down, fill right |
| `F1` | Financial functions guide |
| `F2` | Edit the active cell |
| `F4` | Cycle relative/absolute references while editing |
| `F9` | Recalculate the workbook |
| `Ctrl+~` | Toggle formula display |

## Deliberately out of scope

VBA and macros, pivot tables, Power Query, live market data, real-time
collaboration, embedded Office objects, and a multi-variable optimisation
solver. These are not silently approximated: the application says so when a
file uses them.

## Building from source

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
python run.py

python -W error -m pytest              # full suite
python run.py --self-test              # packaged-build verification
python tools/release_check.py          # release blockers
python tools/build_release.py          # installer
```

See `PACKAGING.md` for the release process, `ARCHITECTURE.md` for the
internal design, and `TESTING.md` for verification details.

## Support

support@duddysoftware.com — https://duddysoftware.com

---

Duddy Spreadsheet is not affiliated with, endorsed by, or sponsored by
Microsoft Corporation. Microsoft and Excel are trademarks of Microsoft
Corporation.
