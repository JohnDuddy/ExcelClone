"""Sheet and workbook protection compatible with Excel's password hashing.

Excel 2013+ stores a protection password as SHA-512 over a random salt and
the UTF-16LE password, re-hashed ``spin_count`` times with a little-endian
iteration counter. The stored form here is ``SHA-512$spin$salt$hash`` with
base64 salt and hash, which maps directly onto the XLSX attributes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from duddysheet.core.cell import SheetProtection
from duddysheet.core.sheet import Sheet

ALGORITHM = "SHA-512"
DEFAULT_SPIN_COUNT = 100_000


def excel_hash(password: str, salt: bytes, spin_count: int) -> bytes:
    """Return Excel's iterated SHA-512 digest of a password."""
    digest = hashlib.sha512(salt + password.encode("utf-16-le")).digest()
    for iteration in range(spin_count):
        digest = hashlib.sha512(digest + iteration.to_bytes(4, "little")).digest()
    return digest


def hash_password(password: str, *, spin_count: int = DEFAULT_SPIN_COUNT) -> str:
    """Return the stored protection string for a password ('' for none)."""
    if not password:
        return ""
    salt = os.urandom(16)
    digest = excel_hash(password, salt, spin_count)
    return "$".join(
        (
            ALGORITHM,
            str(spin_count),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(stored: str, password: str) -> bool:
    """Return whether a password unlocks a stored protection string."""
    if not stored:
        return True
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == ALGORITHM:
        try:
            spin_count = int(parts[1])
            salt = base64.b64decode(parts[2])
            expected = base64.b64decode(parts[3])
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(excel_hash(password, salt, spin_count), expected)
    if len(parts) == 2 and parts[0] == "LEGACY":
        return legacy_hash(password) == parts[1].upper()
    return False


def legacy_hash(password: str) -> str:
    """Return Excel's pre-2013 16-bit password verifier as four hex digits."""
    value = 0
    for index, character in enumerate(password[:15], start=1):
        code = ord(character) & 0x7FFF
        rotated = ((code << index) | (code >> (15 - index))) & 0x7FFF
        value ^= rotated
    value ^= len(password)
    value ^= 0xCE4B
    return f"{value:04X}"


def stored_from_xlsx(
    algorithm: str | None,
    hash_value: str | None,
    salt_value: str | None,
    spin_count: int | None,
    legacy_password: str | None,
) -> str:
    """Build a stored protection string from XLSX protection attributes."""
    if algorithm and hash_value and salt_value:
        if algorithm.upper().replace("_", "-") != ALGORITHM:
            return ""
        return "$".join((ALGORITHM, str(spin_count or DEFAULT_SPIN_COUNT), salt_value, hash_value))
    if legacy_password:
        return f"LEGACY${legacy_password}"
    return ""


def xlsx_attributes(stored: str) -> dict[str, object]:
    """Return XLSX hashing attributes for a stored protection string."""
    parts = stored.split("$")
    if len(parts) == 4 and parts[0] == ALGORITHM:
        return {
            "algorithmName": ALGORITHM,
            "spinCount": int(parts[1]),
            "saltValue": parts[2],
            "hashValue": parts[3],
        }
    if len(parts) == 2 and parts[0] == "LEGACY":
        return {"password": parts[1]}
    return {}


def can_edit_cell(sheet: Sheet, row: int, column: int) -> bool:
    """Return whether protection allows changing a cell's contents."""
    if sheet.protection is None:
        return True
    return not sheet.effective_format(row, column).locked


def permits(sheet: Sheet, action: str) -> bool:
    """Return whether a protected sheet allows an action such as 'insert_rows'."""
    protection = sheet.protection
    if protection is None:
        return True
    return bool(getattr(protection, action, False))


PROTECTION_OPTIONS = tuple(
    name for name in SheetProtection.__dataclass_fields__ if name != "password_hash"
)
