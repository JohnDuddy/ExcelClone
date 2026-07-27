"""Refuse to release a build that is not distributable.

Several release blockers are invisible at runtime during development: a
placeholder signing key still works locally, and missing licence texts only
matter once the product reaches a customer. This script fails loudly on each
of them so they cannot reach a paying user.

Run it before packaging::

    python tools/release_check.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duddysheet.branding import (  # noqa: E402
    SUPPORT_EMAIL,
    VERSION,
    WEBSITE,
)
from duddysheet.core.licensing import has_vendor_key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DOCUMENTS = (
    "LICENSE",
    "EULA.md",
    "PRIVACY.md",
    "THIRD-PARTY-NOTICES.md",
    "README.md",
)

#: Values that must be replaced before the product is sold.
PLACEHOLDER_MARKERS = ("example.com", "PLACEHOLDER", "REPLACE")


def check_vendor_key() -> list[str]:
    """The build must carry a real signing key or no licence can be activated."""
    if has_vendor_key():
        return []
    return [
        "VENDOR_PUBLIC_KEY in duddysheet/core/licensing.py is still the "
        "placeholder. Run 'python tools/licence_admin.py keygen' and paste the "
        "public key in. Without it, no customer can activate."
    ]


def check_documents() -> list[str]:
    """Every legal document must be present and non-empty."""
    problems = []
    for name in REQUIRED_DOCUMENTS:
        path = ROOT / name
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            problems.append(f"{name} is missing or empty.")
    return problems


def check_licence_texts() -> list[str]:
    """Delegate to the licence collector, which enforces the GNU texts."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "collect_licenses.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    problems = [
        line.strip().removeprefix("!!").strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("!!")
    ]
    return problems or [
        "Licence collection failed; run tools/collect_licenses.py for detail."
    ]


def check_contact_details() -> list[str]:
    """Support and website details must be real before customers see them."""
    problems = []
    for label, value in (("SUPPORT_EMAIL", SUPPORT_EMAIL), ("WEBSITE", WEBSITE)):
        if any(marker in value for marker in PLACEHOLDER_MARKERS):
            problems.append(
                f"branding.{label} is still a placeholder ({value}). "
                f"Customers will be told to contact it."
            )
    return problems


def check_version() -> list[str]:
    """A shipped build must not carry a development version."""
    if VERSION.startswith("0."):
        return [
            f"Version {VERSION} looks like a pre-release. Set a release "
            f"version in duddysheet/branding.py."
        ]
    return []


CHECKS = (
    ("Vendor signing key", check_vendor_key),
    ("Legal documents", check_documents),
    ("Third-party licence texts", check_licence_texts),
    ("Contact details", check_contact_details),
    ("Version", check_version),
)


def main() -> int:
    """Run every release check and report the outcome."""
    failures: list[str] = []

    for label, check in CHECKS:
        problems = check()
        status = "ok  " if not problems else "FAIL"
        print(f"  {status}  {label}")
        failures.extend(problems)

    if failures:
        print(f"\n{len(failures)} blocker(s) prevent release:\n")
        for problem in failures:
            print(f"  !!  {problem}")
        print("\nThis build must NOT be distributed.")
        return 1

    print(f"\nRelease checks passed for version {VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
