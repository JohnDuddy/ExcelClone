# OpenGrid

OpenGrid is a personal, offline spreadsheet application for Windows 11. It is
implemented in Python with a headless spreadsheet engine and a virtualized
PySide6 grid.

The project is under active milestone development. The currently verified build
opens the application shell with the user-visible title
`OpenGrid — Personal Spreadsheet`.

## Developer Run

Python 3.13 is required.

```powershell
python -m pip install -r requirements.txt
python run.py
```

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

See `TESTING.md` for the regression policy and `FEATURES.md` for the current
capability contract.

## Project Layout

| Path | Responsibility |
|---|---|
| `excelclone/core` | Qt-free spreadsheet engine |
| `excelclone/commands` | Reversible mutation interface |
| `excelclone/io` | Workbook file-format adapters |
| `excelclone/ui` | PySide6 model/view interface |
| `excelclone/util` | Local settings, logs, and paths |
| `tests` | Behavioral and performance verification |

