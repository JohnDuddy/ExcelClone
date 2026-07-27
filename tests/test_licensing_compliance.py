"""Distribution licence-compliance contract.

Shipping Qt under LGPL-3.0 imposes obligations that are easy to break
silently during packaging, so they are asserted here rather than trusted to
review.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit

from duddysheet.branding import PRODUCT_NAME, SUPPORT_EMAIL, VERSION
from duddysheet.ui.dialogs.about import AboutDialog

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_licence_and_eula_documents_are_present() -> None:
    for name in ("LICENSE", "EULA.md", "THIRD-PARTY-NOTICES.md", "PRIVACY.md"):
        document = ROOT / name
        assert document.is_file(), f"{name} must ship with the product"
        assert document.read_text(encoding="utf-8").strip()


def test_notices_disclose_qt_lgpl_and_relinking_right() -> None:
    notices = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")

    assert "LGPL-3.0" in notices
    assert "relink" in notices.lower()
    assert "source" in notices.lower()
    assert SUPPORT_EMAIL in notices


def test_eula_defers_to_third_party_licences() -> None:
    """The EULA must not purport to override the rights the LGPL grants."""
    eula = (ROOT / "EULA.md").read_text(encoding="utf-8")

    assert "THIRD-PARTY-NOTICES.md" in eula
    assert "prevail" in eula.lower()


def test_eula_disclaims_financial_advice() -> None:
    eula = (ROOT / "EULA.md").read_text(encoding="utf-8")

    assert "not financial, investment, accounting, tax, or legal advice" in eula


def test_product_does_not_claim_microsoft_affiliation() -> None:
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "not affiliated" in text.lower()
        assert "Microsoft" in text


def test_collect_licenses_reports_missing_gnu_texts(tmp_path, monkeypatch) -> None:
    """The collector must fail while the mandatory GNU texts are absent."""
    from tools import collect_licenses

    monkeypatch.setattr(collect_licenses, "LICENSE_DIR", tmp_path / "licenses")
    _, problems = collect_licenses.collect(write=False)

    assert any("LGPL-3.0.txt" in problem for problem in problems)


def test_about_dialog_discloses_qt_lgpl_usage(application) -> None:
    dialog = AboutDialog()
    try:
        disclosed = "\n".join(
            pane.toPlainText() for pane in dialog.findChildren(QPlainTextEdit)
        )
        headings = "\n".join(label.text() for label in dialog.findChildren(QLabel))

        assert "Lesser General Public License" in disclosed
        assert "relink" in disclosed.lower()
        assert SUPPORT_EMAIL in disclosed
        assert PRODUCT_NAME in dialog.windowTitle()
        assert VERSION in headings
    finally:
        dialog.deleteLater()


def test_about_dialog_survives_a_build_missing_licence_texts(
    application, monkeypatch, tmp_path
) -> None:
    """A packaging fault must degrade to a clear message, not a crash."""
    monkeypatch.setattr(
        "duddysheet.ui.dialogs.about.resource_path",
        lambda relative: tmp_path / relative,
    )

    dialog = AboutDialog()
    try:
        disclosed = "\n".join(
            pane.toPlainText() for pane in dialog.findChildren(QPlainTextEdit)
        )
        assert "packaging fault" in disclosed
    finally:
        dialog.deleteLater()
