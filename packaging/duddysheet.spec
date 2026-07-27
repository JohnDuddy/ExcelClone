# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Duddy Spreadsheet.

Produces a onedir build. Onedir rather than onefile is deliberate: onefile
unpacks to a temporary directory on every launch, which costs seconds of
startup, trips endpoint-protection software in exactly the regulated
environments this product targets, and would break the LGPL relinking
right by hiding the Qt libraries from the user.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent

# Qt modules outside PySide6-Essentials, plus GUI toolkits and developer
# tooling that would otherwise be pulled in transitively.
EXCLUDED = [
    "PySide6.Qt3DCore",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PyQt5",
    "PyQt6",
    "tkinter",
    "pytest",
    "_pytest",
    "IPython",
    "notebook",
    "sphinx",
    "setuptools",
    "pip",
]

# matplotlib ships many backends; only the Qt Agg backend is ever used.
EXCLUDED += [
    "matplotlib.backends.backend_gtk3agg",
    "matplotlib.backends.backend_gtk4agg",
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_webagg",
]

datas = [
    (str(ROOT / "assets" / "duddysheet.ico"), "assets"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "EULA.md"), "."),
    (str(ROOT / "PRIVACY.md"), "."),
    (str(ROOT / "THIRD-PARTY-NOTICES.md"), "."),
    (str(ROOT / "README.md"), "."),
]

licenses_dir = ROOT / "licenses"
if licenses_dir.is_dir():
    for licence_file in sorted(licenses_dir.iterdir()):
        if licence_file.is_file():
            datas.append((str(licence_file), "licenses"))

# Python's own TLS stack is unused: the product makes no network calls, and
# licence verification is offline. Dropping it also removes a second copy of
# OpenSSL, since cryptography ships its own.
EXCLUDED += ["ssl", "_ssl", "http", "urllib.request", "xmlrpc"]

#: Binaries PyInstaller collects that this application never loads.
#:
#: opengl32sw.dll is Qt's 20 MB software OpenGL fallback. Qt Widgets paints
#: through the raster engine on Windows and no OpenGL widget is used.
#: Qt6Network is likewise unused, and removing it makes the product's "no
#: network access" claim structurally true rather than merely a policy.
EXCLUDED_BINARIES = {
    "opengl32sw.dll",
    "qt6network.dll",
    "qt6qml.dll",
    "qt6quick.dll",
    "d3dcompiler_47.dll",
}

analysis = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("duddysheet"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED,
    noarchive=False,
    optimize=0,
)

analysis.binaries = TOC(
    entry
    for entry in analysis.binaries
    if Path(entry[0]).name.lower() not in EXCLUDED_BINARIES
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="DuddySpreadsheet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "duddysheet.ico"),
    version=str(SPEC_DIR / "version_info.txt"),
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DuddySpreadsheet",
)
