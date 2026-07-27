"""Packaging and distribution contract.

These assert the properties that make a build lawfully and practically
distributable. They deliberately check configuration rather than running a
full freeze, which takes minutes and needs PyInstaller installed.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from generate_icon import SIZES, generate_icon

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"

#: Qt modules shipped by PySide6-Essentials that the product is allowed to use.
ESSENTIAL_QT_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtPrintSupport"}


def test_generated_icon_contains_all_required_windows_sizes(tmp_path) -> None:
    icon = generate_icon(tmp_path / "duddysheet.ico")
    data = icon.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", data)
    sizes = []
    for index in range(count):
        offset = 6 + index * 16
        width, height = struct.unpack_from("<BB", data, offset)
        sizes.append((width or 256, height or 256))

    assert (reserved, image_type) == (0, 1)
    assert sizes == [(size, size) for size in SIZES]


def test_product_imports_only_essential_qt_modules() -> None:
    """Guard the PySide6-Essentials dependency.

    Importing any Qt module outside Essentials would silently reintroduce the
    PySide6-Addons dependency and roughly triple the shipped Qt footprint.
    """
    used: set[str] = set()
    for source in (ROOT / "duddysheet").rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        used.update(re.findall(r"PySide6\.(Qt[A-Za-z]+)", text))

    assert used, "expected the product to import Qt"
    assert used <= ESSENTIAL_QT_MODULES, (
        f"non-Essentials Qt modules imported: {sorted(used - ESSENTIAL_QT_MODULES)}"
    )


def test_requirements_pin_essentials_rather_than_full_pyside() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pinned = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    names = {re.split(r"[=<>!~]", line, maxsplit=1)[0].lower() for line in pinned}

    assert "pyside6-essentials" in names
    assert "pyside6" not in names
    assert "pyside6-addons" not in names


def test_every_runtime_dependency_is_pinned() -> None:
    """Unpinned dependencies make a shipped build unreproducible."""
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        assert "==" in cleaned, f"{cleaned} is not pinned to an exact version"


def test_pyinstaller_spec_excludes_unused_qt_and_backends() -> None:
    spec = (PACKAGING / "duddysheet.spec").read_text(encoding="utf-8")

    for excluded in ("PySide6.QtWebEngineCore", "PySide6.QtQuick", "tkinter"):
        assert excluded in spec
    # The 20 MB software OpenGL fallback is never used by a raster-painted
    # widget application.
    assert "opengl32sw.dll" in spec
    # Qt networking is excluded so the no-network claim is structural.
    assert "qt6network.dll" in spec


def test_pyinstaller_spec_bundles_legal_documents() -> None:
    """The About dialog and the LGPL both depend on these being packaged."""
    spec = (PACKAGING / "duddysheet.spec").read_text(encoding="utf-8")

    for document in ("LICENSE", "EULA.md", "THIRD-PARTY-NOTICES.md", "PRIVACY.md"):
        assert document in spec
    assert "licenses" in spec


def test_pyinstaller_spec_builds_onedir_for_lgpl_relinking() -> None:
    """Qt must remain replaceable, which a onefile build would prevent."""
    spec = (PACKAGING / "duddysheet.spec").read_text(encoding="utf-8")

    assert "COLLECT(" in spec
    assert "exclude_binaries=True" in spec


def test_installer_script_declares_identity_and_associations() -> None:
    script = (PACKAGING / "installer.iss").read_text(encoding="utf-8")

    assert "AppId=" in script
    assert "DuddySpreadsheet.exe" in script
    assert ".dsheet" in script
    assert "LicenseFile=..\\EULA.md" in script
    assert "OutputBaseFilename=DuddySpreadsheet-{#AppVersion}-Setup" in script


def test_installer_does_not_delete_user_data_on_uninstall() -> None:
    """Uninstalling must never destroy a customer's work or activation."""
    script = (PACKAGING / "installer.iss").read_text(encoding="utf-8")
    directives = [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    ]
    deletions = [line.lower() for line in directives if line.lower().startswith("type:")]

    assert deletions, "expected the uninstaller to clean its own files"
    for deletion in deletions:
        assert "{localappdata}" not in deletion
        assert "{userappdata}" not in deletion
        assert "{userdocs}" not in deletion
        assert "{app}" in deletion


def test_build_script_signs_and_verifies() -> None:
    build = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "--self-test" in build
    assert "signtool" in build
    assert "timestamp" in build
    # An unsigned release must warn rather than pass silently.
    assert "NOT SIGNED" in build


def test_release_check_blocks_a_placeholder_signing_key() -> None:
    from tools.release_check import check_vendor_key

    problems = check_vendor_key()

    assert problems, "a placeholder vendor key must block release"
    assert "placeholder" in problems[0].lower()
