"""Assemble the shippable ``licenses/`` folder from installed metadata.

Distributing Duddy Spreadsheet requires shipping the licence text of every
bundled dependency. Qt in particular is used under LGPL-3.0, which obliges us
to deliver the licence text and a written offer of source. This script builds
that folder and refuses to succeed when anything required is missing, so a
non-compliant build fails loudly instead of shipping quietly.

Usage::

    python tools/collect_licenses.py            # build and verify
    python tools/collect_licenses.py --check    # verify only, no writes
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LICENSE_DIR = ROOT / "licenses"

#: Runtime distributions that must contribute a licence text.
REQUIRED_DISTRIBUTIONS = (
    "PySide6-Essentials",
    "shiboken6",
    "matplotlib",
    "numpy",
    "openpyxl",
    "et_xmlfile",
    "pillow",
    "python-dateutil",
    "six",
    "contourpy",
    "cycler",
    "fonttools",
    "kiwisolver",
    "packaging",
    "pyparsing",
    "cryptography",
)

#: Copyleft texts that no wheel ships and that must be vendored by hand.
#: Qt is consumed under LGPL-3.0, which incorporates GPL-3.0 by reference.
VENDORED_TEXTS = {
    "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
    "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
}

#: Minimum plausible size of a real copyleft text, to catch empty placeholders.
MINIMUM_VENDORED_BYTES = 4000


def _display_path(path: Path) -> str:
    """Return a repository-relative path when possible, else an absolute one."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _license_files(distribution: metadata.Distribution) -> list[Path]:
    """Return licence files shipped inside a distribution's metadata."""
    found: list[Path] = []
    for entry in distribution.files or ():
        path = Path(str(entry))
        if path.suffix.lower() in (".py", ".pyc", ".pyd", ".so", ".dll"):
            continue
        name = path.name.lower()
        in_license_dir = path.parent.name.lower() == "licenses"
        named_license = name.startswith(("license", "licence", "copying", "notice"))
        if named_license or in_license_dir:
            resolved = Path(distribution.locate_file(entry))
            if resolved.is_file():
                found.append(resolved)
    return found


def collect(write: bool) -> tuple[list[str], list[str]]:
    """Collect licence texts, returning written names and problems found."""
    problems: list[str] = []
    written: list[str] = []

    if write:
        LICENSE_DIR.mkdir(exist_ok=True)

    for name in REQUIRED_DISTRIBUTIONS:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            problems.append(f"{name}: not installed, cannot collect its licence")
            continue

        sources = _license_files(distribution)
        if not sources:
            problems.append(f"{name}: ships no discoverable licence text")
            continue

        for source in sources:
            target_name = f"{name}-{source.name}"
            written.append(target_name)
            if write:
                shutil.copyfile(source, LICENSE_DIR / target_name)

    for filename, url in VENDORED_TEXTS.items():
        target = LICENSE_DIR / filename
        if not target.is_file():
            problems.append(
                f"{filename}: missing. Download it from {url} and save it to "
                f"{_display_path(target)}. It is not shipped by any wheel and "
                f"is required to distribute Qt under LGPL-3.0."
            )
        elif target.stat().st_size < MINIMUM_VENDORED_BYTES:
            problems.append(
                f"{filename}: only {target.stat().st_size} bytes, which is too "
                f"short to be the real text. Re-download it from {url}."
            )
        else:
            written.append(filename)

    return written, problems


def main(argv: list[str] | None = None) -> int:
    """Build or verify the licences folder and report compliance problems."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify without writing any files",
    )
    arguments = parser.parse_args(argv)

    written, problems = collect(write=not arguments.check)

    for name in sorted(set(written)):
        print(f"  ok  {name}")

    if problems:
        print(f"\n{len(problems)} licence problem(s) block distribution:\n")
        for problem in problems:
            print(f"  !!  {problem}")
        print(
            "\nThe build is NOT distributable until these are resolved. "
            "Shipping Qt without the LGPL-3.0 text violates its licence."
        )
        return 1

    print(f"\n{len(set(written))} licence files ready in {LICENSE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
