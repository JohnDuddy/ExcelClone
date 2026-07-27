from __future__ import annotations

import struct
from pathlib import Path

from build_zip import ROOT, package_files
from generate_icon import SIZES, generate_icon


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


def test_installer_uses_offline_wheels_and_direct_pythonw_shortcut() -> None:
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    launcher = (ROOT / "INSTALL.bat").read_text(encoding="utf-8")

    assert "--no-index" in installer
    assert "--find-links" in installer
    assert '"Scripts\\pythonw.exe"' in installer
    assert '$shortcut.TargetPath = $venvPythonw' in installer
    assert '$shortcut.WorkingDirectory = $installDir' in installer
    assert "ExecutionPolicy Bypass" in launcher
