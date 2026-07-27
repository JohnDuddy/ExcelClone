"""About dialog carrying product identity and licence disclosures.

The LGPL-3.0 obliges us to tell users that the product uses Qt under that
licence and to make its terms available to them, so the licence tabs here are
a distribution requirement rather than a nicety.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from duddysheet.branding import (
    COPYRIGHT,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    SUPPORT_EMAIL,
    VENDOR_NAME,
    VERSION,
    WEBSITE,
)
from duddysheet.util.paths import resource_path

_MISSING_LICENCE_TEXT = (
    "Licence texts were not packaged with this build.\n\n"
    "This is a packaging fault. Please report it to {email} and we will "
    "supply the texts, including the GNU Lesser General Public License "
    "v3.0 under which this product uses the Qt libraries."
)

_QT_NOTICE = (
    "{product} uses the Qt libraries under the GNU Lesser General Public "
    "License version 3.0. Qt is not modified and is bundled as separate, "
    "dynamically loaded libraries.\n\n"
    "You may obtain the source code for Qt and PySide6, modify it, and "
    "relink this application against your modified build by replacing the "
    "Qt libraries in the installation directory. To request the "
    "corresponding source on physical media, email {email}.\n\n"
    "Qt is a trademark of The Qt Company Ltd. {product} is not affiliated "
    "with, endorsed by, or sponsored by Microsoft Corporation. Microsoft "
    "and Excel are trademarks of Microsoft Corporation."
)


def _read_document(name: str) -> str | None:
    """Return the text of a packaged top-level document, if it is present."""
    path = resource_path(name)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _licence_files() -> list[Path]:
    """Return packaged third-party licence texts, sorted for stable display."""
    directory = resource_path("licenses")
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_file()),
        key=lambda path: path.name.lower(),
    )


class AboutDialog(QDialog):
    """Product, licence, and third-party attribution disclosure."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {PRODUCT_NAME}")
        self.resize(720, 540)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_header())

        tabs = QTabWidget(self)
        tabs.addTab(self._build_qt_notice(), "Qt and LGPL")
        tabs.addTab(self._build_document_tab("EULA.md"), "Licence Agreement")
        tabs.addTab(self._build_document_tab("THIRD-PARTY-NOTICES.md"), "Notices")
        tabs.addTab(self._build_licence_browser(), "Third-Party Licences")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _build_header(self) -> QWidget:
        """Return the product identity block."""
        header = QWidget(self)
        rows = QVBoxLayout(header)
        rows.setContentsMargins(4, 4, 4, 8)

        title = QLabel(f"<h2>{PRODUCT_NAME} {VERSION}</h2>", header)
        subtitle = QLabel(PRODUCT_TAGLINE, header)
        vendor = QLabel(
            f"{COPYRIGHT}<br>"
            f'<a href="{WEBSITE}">{WEBSITE}</a> &nbsp;|&nbsp; '
            f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>',
            header,
        )
        vendor.setOpenExternalLinks(True)
        vendor.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        for widget in (title, subtitle, vendor):
            widget.setWordWrap(True)
            rows.addWidget(widget)
        return header

    def _build_qt_notice(self) -> QWidget:
        """Return the mandatory Qt/LGPL disclosure pane."""
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setPlainText(
            _QT_NOTICE.format(product=PRODUCT_NAME, email=SUPPORT_EMAIL)
        )
        return view

    def _build_document_tab(self, name: str) -> QWidget:
        """Return a read-only pane showing a packaged top-level document."""
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        text = _read_document(name)
        view.setPlainText(
            text
            if text is not None
            else _MISSING_LICENCE_TEXT.format(email=SUPPORT_EMAIL)
        )
        return view

    def _build_licence_browser(self) -> QWidget:
        """Return a selectable list of every packaged third-party licence."""
        pane = QWidget(self)
        columns = QHBoxLayout(pane)

        names = QListWidget(pane)
        text = QPlainTextEdit(pane)
        text.setReadOnly(True)

        files = _licence_files()
        if not files:
            text.setPlainText(_MISSING_LICENCE_TEXT.format(email=SUPPORT_EMAIL))
        else:
            for path in files:
                names.addItem(path.name)

            def show(row: int) -> None:
                if 0 <= row < len(files):
                    text.setPlainText(
                        files[row].read_text(encoding="utf-8", errors="replace")
                    )

            names.currentRowChanged.connect(show)
            names.setCurrentRow(0)

        names.setMaximumWidth(260)
        columns.addWidget(names)
        columns.addWidget(text, 1)
        return pane
