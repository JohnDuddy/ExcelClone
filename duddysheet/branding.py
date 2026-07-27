"""Single source of truth for product identity.

Every user-visible product name, vendor string, file-format label, and
support endpoint is defined here so that packaging, the installer, the
about dialog, licensing, and documentation cannot drift apart.
"""

from __future__ import annotations

from typing import Final

PRODUCT_NAME: Final = "Duddy Spreadsheet"
PRODUCT_TAGLINE: Final = "Offline financial modeling workbench"
VENDOR_NAME: Final = "Duddy Software"
COPYRIGHT: Final = "Copyright (c) 2026 Duddy Software. All rights reserved."

VERSION: Final = "1.0.0"

#: Windows-safe identifier used for install directories and app data.
SLUG: Final = "DuddySpreadsheet"

#: Native workbook extension, including the leading dot.
NATIVE_SUFFIX: Final = ".dsheet"

#: Legacy extension still accepted when opening files.
LEGACY_NATIVE_SUFFIX: Final = ".ogrid"

NATIVE_FORMAT_LABEL: Final = f"{PRODUCT_NAME} Workbook"

SUPPORT_EMAIL: Final = "support@duddysoftware.com"
WEBSITE: Final = "https://duddysoftware.com"


def window_title(document: str | None = None, *, dirty: bool = False) -> str:
    """Return the main-window title for an optional document name."""
    if document is None:
        return PRODUCT_NAME
    marker = "*" if dirty else ""
    return f"{marker}{document} - {PRODUCT_NAME}"
