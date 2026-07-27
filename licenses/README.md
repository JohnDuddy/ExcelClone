# Licence texts

Most files here are generated. Run `python tools/collect_licenses.py` to
rebuild them from installed package metadata after any dependency change.

Two files are **not** generated and are tracked in version control, because
no wheel ships them and Qt cannot lawfully be distributed without them:

| File | Source |
|---|---|
| `LGPL-3.0.txt` | <https://www.gnu.org/licenses/lgpl-3.0.txt> |
| `GPL-3.0.txt` | <https://www.gnu.org/licenses/gpl-3.0.txt> |

**These are currently missing and must be added before the first release.**
Download both from the URLs above and commit them. `collect_licenses.py`
exits non-zero until they exist, and the release build refuses to package
without them.

Note that the PySide6 wheel ships only `LicenseRef-Qt-Commercial.txt`. That
file describes the commercial Qt licence, which is *not* the licence we use.
Duddy Spreadsheet uses Qt under LGPL-3.0, so the LGPL text above is the
operative one and must accompany every copy of the product.
