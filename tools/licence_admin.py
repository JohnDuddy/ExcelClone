"""Vendor-side licence administration.

This tool is for the seller, not the customer. It generates the signing key
pair and issues licence keys. Ship neither this file nor the private key.

Typical use::

    python tools/licence_admin.py keygen --out vendor-keys.json
    # paste the printed public key into duddysheet/core/licensing.py

    python tools/licence_admin.py issue \\
        --private-key-file vendor-keys.json \\
        --licensee "Jordan Blake" --email jordan@example.com \\
        --edition business --seats 1

    python tools/licence_admin.py verify --key DS1-...
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from duddysheet.core.licensing import (  # noqa: E402
    Edition,
    License,
    LicenseError,
    generate_key_pair,
    issue_license,
    verify_license,
)


def command_keygen(arguments: argparse.Namespace) -> int:
    """Create a signing key pair."""
    private_key, public_key = generate_key_pair()
    payload = {"private_key": private_key, "public_key": public_key}

    if arguments.out:
        destination = Path(arguments.out)
        if destination.exists() and not arguments.force:
            print(
                f"{destination} already exists. Refusing to overwrite a signing "
                f"key; pass --force only if you are certain.",
                file=sys.stderr,
            )
            return 1
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {destination}")

    print("\nPublic key (paste into duddysheet/core/licensing.py):\n")
    print(f'VENDOR_PUBLIC_KEY = "{public_key}"\n')
    print("Private key (KEEP SECRET, never commit, never ship):\n")
    print(private_key)
    print(
        "\nAnyone holding the private key can mint licences. Store it in a "
        "password manager or secrets store, and back it up: losing it means "
        "you can no longer issue keys that existing builds accept."
    )
    return 0


def _load_private_key(arguments: argparse.Namespace) -> str:
    if arguments.private_key:
        return arguments.private_key
    data = json.loads(Path(arguments.private_key_file).read_text(encoding="utf-8"))
    return str(data["private_key"])


def command_issue(arguments: argparse.Namespace) -> int:
    """Sign and print a licence key."""
    expires = None
    if arguments.expires:
        expires = date.fromisoformat(arguments.expires)
    elif arguments.valid_days:
        expires = date.today() + timedelta(days=arguments.valid_days)

    license = License(
        licensee=arguments.licensee,
        email=arguments.email,
        edition=Edition(arguments.edition),
        seats=arguments.seats,
        issued=date.today(),
        expires=expires,
        key_id=arguments.key_id or "",
    )

    key = issue_license(license, _load_private_key(arguments))
    print(key)
    return 0


def command_verify(arguments: argparse.Namespace) -> int:
    """Check a licence key against a public key."""
    try:
        license = verify_license(arguments.key, arguments.public_key)
    except LicenseError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1

    print("VALID")
    for field, value in license.to_payload().items():
        print(f"  {field:10} {value}")
    if license.is_expired():
        print("\nNote: this licence has expired.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="create a signing key pair")
    keygen.add_argument("--out", help="write the key pair to this JSON file")
    keygen.add_argument(
        "--force", action="store_true", help="overwrite an existing key file"
    )
    keygen.set_defaults(handler=command_keygen)

    issue = commands.add_parser("issue", help="issue a licence key")
    source = issue.add_mutually_exclusive_group(required=True)
    source.add_argument("--private-key", help="base64url private key")
    source.add_argument("--private-key-file", help="JSON file from keygen")
    issue.add_argument("--licensee", required=True, help="name on the licence")
    issue.add_argument("--email", required=True, help="purchaser email")
    issue.add_argument(
        "--edition",
        default=Edition.PERSONAL.value,
        choices=[edition.value for edition in Edition],
    )
    issue.add_argument("--seats", type=int, default=1)
    issue.add_argument("--expires", help="expiry date as YYYY-MM-DD")
    issue.add_argument("--valid-days", type=int, help="expire this many days out")
    issue.add_argument("--key-id", help="your order or invoice reference")
    issue.set_defaults(handler=command_issue)

    verify = commands.add_parser("verify", help="check a licence key")
    verify.add_argument("--key", required=True)
    verify.add_argument(
        "--public-key",
        help="public key to check against, defaulting to this build's",
    )
    verify.set_defaults(handler=command_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the licence administration tool."""
    arguments = build_parser().parse_args(argv)
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
