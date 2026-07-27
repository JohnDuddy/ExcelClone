# Third-Party Notices

Duddy Spreadsheet 1.0.0 incorporates the third-party components listed
below. Each remains governed by its own licence, which prevails over the
Duddy Spreadsheet EULA in respect of that component.

Full licence texts for every component are installed alongside the
application in the `licenses/` folder and are reachable from
**Help > About > Third-Party Licences**.

## Qt and PySide6 — LGPL-3.0 (important)

| Component | Version | Licence |
|---|---|---|
| PySide6-Essentials | 6.11.0 | LGPL-3.0-only |
| shiboken6 | 6.11.0 | LGPL-3.0-only |
| Qt libraries (bundled by PySide6) | 6.11.0 | LGPL-3.0-only |

Duddy Spreadsheet uses the Qt libraries under the **GNU Lesser General
Public License version 3.0**. We do not modify Qt.

Under the LGPL-3.0 you have the following rights, which the Duddy
Spreadsheet EULA does not and cannot restrict:

1. **You may obtain the source code of Qt and PySide6.** It is published at
   <https://download.qt.io/> and <https://code.qt.io/>. On written request
   to support@duddysoftware.com we will supply the corresponding source for
   the exact versions shipped here, on a physical medium or by download, for
   no more than our cost of distribution, for at least three years from your
   purchase.

2. **You may modify Qt and relink this application against your modified
   version.** Qt is bundled as separate, dynamically loaded shared libraries
   (`.dll` / `.pyd`) and is not statically linked into the application. To
   relink, replace the Qt libraries in the application's installation
   directory with your own binary-compatible build of the same Qt version.
   The application loads whichever compatible Qt libraries are present.

3. **You may reverse engineer this application** to the extent necessary to
   debug your modifications to Qt, notwithstanding Section 2 of the EULA.

The full LGPL-3.0 text is in `licenses/LGPL-3.0.txt`, and the GPL-3.0 text
it incorporates by reference is in `licenses/GPL-3.0.txt`.

Qt is a trademark of The Qt Company Ltd.

## Permissively licensed components

These impose no obligation beyond preserving their copyright and licence
notices, which is satisfied by shipping `licenses/` and this file.

| Component | Version | Licence |
|---|---|---|
| matplotlib | 3.10.9 | Matplotlib License (PSF-derived, BSD-compatible) |
| numpy | 2.4.4 | BSD-3-Clause (with 0BSD, MIT, Zlib, CC0-1.0 parts) |
| openpyxl | 3.1.5 | MIT |
| et_xmlfile | 2.0.0 | MIT |
| Pillow | 12.3.0 | MIT-CMU |
| python-dateutil | 2.9.0.post0 | Apache-2.0 AND BSD-3-Clause |
| six | 1.17.0 | MIT |
| contourpy | 1.3.3 | BSD-3-Clause |
| cycler | 0.12.1 | BSD-3-Clause |
| fonttools | 4.63.0 | MIT |
| kiwisolver | 1.5.0 | BSD-3-Clause |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause |
| pyparsing | 3.3.2 | MIT |

`python-dateutil` is dual-licensed Apache-2.0 and BSD-3-Clause; we rely on
it under BSD-3-Clause. Both texts ship in `licenses/`.

## Fonts

Font files redistributed by matplotlib (the DejaVu family) are licensed
under the DejaVu Fonts License, a permissive Bitstream Vera derivative. Its
text is in `licenses/DejaVu-Fonts-License.txt`.

## Trademarks

Microsoft and Excel are trademarks of Microsoft Corporation. Duddy
Spreadsheet is not affiliated with, endorsed by, or sponsored by Microsoft
Corporation. References to the `.xlsx` format describe interoperability
only.

## Regenerating this file

Run `python tools/collect_licenses.py` after any dependency change. It
rebuilds the `licenses/` folder from installed package metadata and fails
if a dependency ships no discoverable licence text.
