from __future__ import annotations

import re
import struct
from pathlib import Path

from build_zip import ROOT, package_files
from generate_icon import SIZES, generate_icon

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


def test_distribution_inputs_include_runtime_wheels_and_installers() -> None:
    relative = {
        path.relative_to(ROOT).as_posix()
        for path in package_files()
    }

    assert "INSTALL.bat" in relative
    assert "install.ps1" in relative
    assert "assets/duddysheet.ico" in relative
    assert "duddysheet/app.py" in relative
    assert any(path.startswith("wheelhouse/pyside6-") for path in relative)
    assert any(path.startswith("wheelhouse/openpyxl-") for path in relative)


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


def test_installer_uses_offline_wheels_and_direct_pythonw_shortcut() -> None:
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    launcher = (ROOT / "INSTALL.bat").read_text(encoding="utf-8")

    assert "--no-index" in installer
    assert "--find-links" in installer
    assert '"Scripts\\pythonw.exe"' in installer
    assert '$shortcut.TargetPath = $venvPythonw' in installer
    assert '$shortcut.WorkingDirectory = $installDir' in installer
    assert "ExecutionPolicy Bypass" in launcher
