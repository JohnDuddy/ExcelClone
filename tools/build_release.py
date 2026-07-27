"""Build a signed, distributable Windows release.

The pipeline is:

1. release checks, which refuse a build that cannot lawfully be distributed
2. collect third-party licence texts
3. write the Windows version resource from the branding module
4. freeze the application with PyInstaller
5. sign the executable, if a certificate is configured
6. build the installer with Inno Setup
7. sign the installer, if a certificate is configured

Signing is skipped with a loud warning when no certificate is supplied. An
unsigned installer triggers SmartScreen and reads as malware to buyers, so a
release build should never be published unsigned.

Usage::

    python tools/build_release.py
    python tools/build_release.py --sign-cert mycert.pfx --sign-password-env CERT_PW
    python tools/build_release.py --skip-installer      # freeze only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duddysheet.branding import (  # noqa: E402
    COPYRIGHT,
    PRODUCT_NAME,
    PRODUCT_TAGLINE,
    VENDOR_NAME,
    VERSION,
)

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
FROZEN_DIR = DIST / "DuddySpreadsheet"
FROZEN_EXE = FROZEN_DIR / "DuddySpreadsheet.exe"

#: Common install locations for the Inno Setup compiler.
ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)

#: Common install locations for the Windows SDK signing tool.
SIGNTOOL_GLOBS = (
    r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
    r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
)

VERSION_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', {vendor!r}),
            StringStruct('FileDescription', {description!r}),
            StringStruct('FileVersion', {version!r}),
            StringStruct('InternalName', 'DuddySpreadsheet'),
            StringStruct('LegalCopyright', {copyright!r}),
            StringStruct('OriginalFilename', 'DuddySpreadsheet.exe'),
            StringStruct('ProductName', {product!r}),
            StringStruct('ProductVersion', {version!r}),
          ],
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


class BuildError(RuntimeError):
    """Raised when a build step fails."""


def run(command: list[str], *, label: str) -> None:
    """Run a subprocess, raising :class:`BuildError` when it fails."""
    print(f"\n>>> {label}")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise BuildError(f"{label} failed with exit code {result.returncode}")


def write_version_resource() -> Path:
    """Generate the Windows version resource from the branding module."""
    parts = (VERSION.split(".") + ["0", "0", "0"])[:3]
    major, minor, patch = (int(part) for part in parts)
    target = PACKAGING / "version_info.txt"
    target.write_text(
        VERSION_TEMPLATE.format(
            major=major,
            minor=minor,
            patch=patch,
            vendor=VENDOR_NAME,
            description=PRODUCT_TAGLINE,
            version=VERSION,
            copyright=COPYRIGHT,
            product=PRODUCT_NAME,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {target.relative_to(ROOT)}")
    return target


def find_signtool() -> Path | None:
    """Locate signtool.exe from the Windows SDK."""
    for pattern in SIGNTOOL_GLOBS:
        matches = sorted(Path().glob(pattern.replace("\\", "/")), reverse=True)
        if matches:
            return matches[0]
    located = shutil.which("signtool")
    return Path(located) if located else None


def sign(target: Path, arguments: argparse.Namespace) -> None:
    """Authenticode-sign a file, or explain why it was not signed."""
    if not arguments.sign_cert:
        print(
            f"  !! NOT SIGNED: {target.name}\n"
            f"     Windows SmartScreen will warn users that this is an "
            f"unrecognised app, and many will not proceed. Obtain a code "
            f"signing certificate (an OV or EV certificate from a CA such as "
            f"DigiCert, Sectigo, or SSL.com) and rerun with --sign-cert."
        )
        return

    signtool = find_signtool()
    if signtool is None:
        raise BuildError(
            "signtool.exe was not found. Install the Windows SDK signing "
            "tools, or pass --skip-signing to build unsigned."
        )

    password = None
    if arguments.sign_password_env:
        password = os.environ.get(arguments.sign_password_env)
        if not password:
            raise BuildError(
                f"Environment variable {arguments.sign_password_env} is not "
                f"set, so the signing certificate cannot be opened."
            )

    command = [
        str(signtool),
        "sign",
        "/fd",
        "sha256",
        "/td",
        "sha256",
        "/tr",
        arguments.timestamp_url,
        "/f",
        str(arguments.sign_cert),
    ]
    if password:
        command += ["/p", password]
    command.append(str(target))

    # The password is not printed, so the command is described rather than
    # echoed by run().
    print(f"\n>>> Signing {target.name}")
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise BuildError(f"Signing {target.name} failed")


def find_iscc(explicit: str | None) -> Path | None:
    """Locate the Inno Setup compiler."""
    if explicit:
        return Path(explicit)
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    located = shutil.which("iscc")
    return Path(located) if located else None


def build(arguments: argparse.Namespace) -> int:
    """Run the release pipeline."""
    print(f"Building {PRODUCT_NAME} {VERSION}")

    if not arguments.skip_checks:
        run(
            [sys.executable, str(ROOT / "tools" / "release_check.py")],
            label="Release checks",
        )

    licences = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "collect_licenses.py")],
        cwd=ROOT,
        check=False,
    )
    if licences.returncode != 0:
        if not arguments.skip_checks:
            raise BuildError(
                "Third-party licences are incomplete, so this build cannot be "
                "distributed. Resolve the problems above, or pass "
                "--skip-checks to produce a development build that must not "
                "be shared."
            )
        print(
            "\n  !! Licences are incomplete. This is a DEVELOPMENT build and "
            "must not be distributed."
        )

    print("\n>>> Writing version resource")
    write_version_resource()

    if FROZEN_DIR.exists():
        shutil.rmtree(FROZEN_DIR)
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build"),
            str(PACKAGING / "duddysheet.spec"),
        ],
        label="Freezing the application",
    )

    if not FROZEN_EXE.is_file():
        raise BuildError(f"PyInstaller did not produce {FROZEN_EXE}")

    size_mb = sum(
        path.stat().st_size for path in FROZEN_DIR.rglob("*") if path.is_file()
    ) / (1024 * 1024)
    print(f"  frozen build is {size_mb:.0f} MB")

    print("\n>>> Verifying the frozen build")
    verification = subprocess.run(
        [str(FROZEN_EXE), "--self-test"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(verification.stdout.rstrip() or verification.stderr.rstrip())
    if verification.returncode != 0:
        raise BuildError(
            "The frozen build failed its own self-test. Packaging has broken "
            "something the source tests cannot see; do not ship this build."
        )

    if not arguments.skip_signing:
        sign(FROZEN_EXE, arguments)

    if arguments.skip_installer:
        print("\nSkipping the installer as requested.")
        return 0

    iscc = find_iscc(arguments.iscc)
    if iscc is None or not iscc.is_file():
        print(
            "\n  !! Inno Setup was not found, so no installer was built.\n"
            "     Install it (free) from https://jrsoftware.org/isdl.php, or "
            "pass --iscc with its path. The frozen application in "
            f"{FROZEN_DIR.relative_to(ROOT)} is complete and runnable."
        )
        return 0

    run(
        [str(iscc), f"/DAppVersion={VERSION}", str(PACKAGING / "installer.iss")],
        label="Building the installer",
    )

    installer = DIST / f"DuddySpreadsheet-{VERSION}-Setup.exe"
    if installer.is_file() and not arguments.skip_signing:
        sign(installer, arguments)

    if installer.is_file():
        megabytes = installer.stat().st_size / (1024 * 1024)
        print(f"\nInstaller ready: {installer} ({megabytes:.0f} MB)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sign-cert", help="path to a .pfx code signing certificate")
    parser.add_argument(
        "--sign-password-env",
        help="environment variable holding the certificate password",
    )
    parser.add_argument(
        "--timestamp-url",
        default="http://timestamp.digicert.com",
        help="RFC 3161 timestamp server",
    )
    parser.add_argument("--iscc", help="path to the Inno Setup compiler")
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="skip release checks (development builds only)",
    )
    parser.add_argument("--skip-signing", action="store_true")
    parser.add_argument("--skip-installer", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    arguments = build_parser().parse_args(argv)
    try:
        return build(arguments)
    except BuildError as error:
        print(f"\nBUILD FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
