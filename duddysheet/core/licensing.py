"""Offline licence keys and trial state.

Licence keys are Ed25519-signed by the vendor's private key and verified
against a public key compiled into the application. Verification is therefore
entirely offline, which is what lets the product keep its promise of making no
network connection and function in air-gapped environments.

This module is Qt-free and takes its storage directory as an argument so the
whole activation lifecycle can be tested without touching a real profile.

A note on what this does and does not achieve: signature verification stops
key forgery and casual key sharing. It cannot stop someone patching the
binary. That is the accepted trade-off for offline activation, and it is the
same trade-off every offline-licensed desktop product makes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: Number of days a fresh installation may be evaluated without a licence.
TRIAL_DAYS = 30

#: Prefix identifying the key format, so a future format can be told apart.
KEY_PREFIX = "DS1"

#: Vendor Ed25519 public key, base64url encoded.
#:
#: Replace this with your real public key before release; generate the pair
#: with ``python tools/licence_admin.py keygen``. The private key must never
#: be committed or shipped. The placeholder below is a well-known test key and
#: is deliberately obvious, so shipping it unchanged fails the release check.
VENDOR_PUBLIC_KEY = "PLACEHOLDER-REPLACE-BEFORE-RELEASE"

_TRIAL_FILENAME = "trial.json"
_LICENCE_FILENAME = "licence.json"


class Edition(str, Enum):
    """Licensed product editions."""

    PERSONAL = "personal"
    BUSINESS = "business"
    SITE = "site"


class LicenseStatus(str, Enum):
    """The outcome of evaluating the installation's entitlement."""

    LICENSED = "licensed"
    TRIAL = "trial"
    TRIAL_EXPIRED = "trial_expired"
    LICENCE_EXPIRED = "licence_expired"
    INVALID = "invalid"

    @property
    def allows_use(self) -> bool:
        """Return whether the product may be used normally."""
        return self in (LicenseStatus.LICENSED, LicenseStatus.TRIAL)


class LicenseError(ValueError):
    """Raised when a licence key cannot be read."""


@dataclass(frozen=True)
class License:
    """A verified licence."""

    licensee: str
    email: str
    edition: Edition
    seats: int
    issued: date
    expires: date | None = None
    key_id: str = ""

    def is_expired(self, today: date | None = None) -> bool:
        """Return whether the licence has lapsed."""
        if self.expires is None:
            return False
        return (today or _today()) > self.expires

    def to_payload(self) -> dict[str, Any]:
        """Return the signed payload form."""
        return {
            "licensee": self.licensee,
            "email": self.email,
            "edition": self.edition.value,
            "seats": self.seats,
            "issued": self.issued.isoformat(),
            "expires": self.expires.isoformat() if self.expires else None,
            "key_id": self.key_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> License:
        """Rebuild a licence from its signed payload."""
        try:
            return cls(
                licensee=str(payload["licensee"]),
                email=str(payload["email"]),
                edition=Edition(payload["edition"]),
                seats=int(payload["seats"]),
                issued=date.fromisoformat(payload["issued"]),
                expires=(
                    date.fromisoformat(payload["expires"])
                    if payload.get("expires")
                    else None
                ),
                key_id=str(payload.get("key_id", "")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise LicenseError("Licence contents are not valid") from error


@dataclass(frozen=True)
class Entitlement:
    """What the installation is currently entitled to do."""

    status: LicenseStatus
    license: License | None = None
    trial_days_remaining: int = 0

    @property
    def allows_use(self) -> bool:
        """Return whether the product may be used normally."""
        return self.status.allows_use

    @property
    def summary(self) -> str:
        """Return a short user-facing description of the entitlement."""
        if self.status is LicenseStatus.LICENSED and self.license is not None:
            return f"Licensed to {self.license.licensee}"
        if self.status is LicenseStatus.TRIAL:
            days = self.trial_days_remaining
            return f"Trial - {days} day{'s' if days != 1 else ''} remaining"
        if self.status is LicenseStatus.TRIAL_EXPIRED:
            return "Trial expired"
        if self.status is LicenseStatus.LICENCE_EXPIRED:
            return "Licence expired"
        return "Unlicensed"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _canonical(payload: dict[str, Any]) -> bytes:
    """Return the exact bytes that are signed.

    Signing a canonical encoding rather than the transmitted text means the
    signature cannot be invalidated by insignificant key ordering or spacing.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def issue_license(license: License, private_key_base64: str) -> str:
    """Sign a licence and return its key text. Vendor-side only."""
    private_key = Ed25519PrivateKey.from_private_bytes(
        _b64decode(private_key_base64)
    )
    payload = _canonical(license.to_payload())
    signature = private_key.sign(payload)
    return f"{KEY_PREFIX}-{_b64encode(payload)}.{_b64encode(signature)}"


def verify_license(
    key_text: str,
    public_key_base64: str | None = None,
) -> License:
    """Verify a licence key and return it, or raise :class:`LicenseError`."""
    public_key_base64 = public_key_base64 or VENDOR_PUBLIC_KEY
    cleaned = "".join(key_text.split())
    if not cleaned:
        raise LicenseError("Enter a licence key")

    prefix, separator, remainder = cleaned.partition("-")
    if separator != "-" or prefix.upper() != KEY_PREFIX:
        raise LicenseError("This does not look like a Duddy Spreadsheet key")

    encoded_payload, separator, encoded_signature = remainder.partition(".")
    if separator != "." or not encoded_payload or not encoded_signature:
        raise LicenseError("The licence key is incomplete")

    try:
        payload = _b64decode(encoded_payload)
        signature = _b64decode(encoded_signature)
    except (ValueError, TypeError) as error:
        raise LicenseError("The licence key is damaged") from error

    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            _b64decode(public_key_base64)
        )
    except (ValueError, TypeError) as error:
        raise LicenseError(
            "This build has no valid vendor key and cannot be activated"
        ) from error

    try:
        public_key.verify(signature, payload)
    except InvalidSignature as error:
        raise LicenseError("This licence key is not genuine") from error

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LicenseError("The licence key is damaged") from error
    if not isinstance(decoded, dict):
        raise LicenseError("The licence key is damaged")

    return License.from_payload(decoded)


def _machine_secret() -> bytes:
    """Return a stable per-machine value used to bind trial state.

    This deters copying a fresh trial file between machines or resetting the
    clock by hand. It is a deterrent, not a security boundary.
    """
    parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()


def _sign_trial(data: dict[str, Any]) -> str:
    return hmac.new(
        _machine_secret(), _canonical(data), hashlib.sha256
    ).hexdigest()


class LicenseManager:
    """Reads and writes activation state under a storage directory."""

    def __init__(
        self,
        directory: Path,
        *,
        public_key: str | None = None,
        trial_days: int = TRIAL_DAYS,
    ) -> None:
        self.directory = Path(directory)
        self.public_key = public_key or VENDOR_PUBLIC_KEY
        self.trial_days = trial_days

    @property
    def trial_path(self) -> Path:
        return self.directory / _TRIAL_FILENAME

    @property
    def licence_path(self) -> Path:
        return self.directory / _LICENCE_FILENAME

    def stored_license(self) -> License | None:
        """Return the activated licence, or None when absent or invalid."""
        try:
            raw = json.loads(self.licence_path.read_text(encoding="utf-8"))
            return verify_license(raw["key"], self.public_key)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def activate(self, key_text: str) -> License:
        """Verify and persist a licence key, returning the licence."""
        license = verify_license(key_text, self.public_key)
        if license.is_expired():
            raise LicenseError(
                f"This licence expired on {license.expires:%d %B %Y}"
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        self.licence_path.write_text(
            json.dumps({"key": "".join(key_text.split())}, indent=2),
            encoding="utf-8",
        )
        return license

    def deactivate(self) -> None:
        """Remove the stored licence."""
        self.licence_path.unlink(missing_ok=True)

    def trial_started_on(self) -> date | None:
        """Return when the trial began, or None if it has not or was tampered."""
        try:
            stored = json.loads(self.trial_path.read_text(encoding="utf-8"))
            signature = stored.pop("signature", "")
            if not hmac.compare_digest(signature, _sign_trial(stored)):
                return None
            return date.fromisoformat(stored["started"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def begin_trial(self, today: date | None = None) -> date:
        """Start the trial if it has not started, returning its start date."""
        existing = self.trial_started_on()
        if existing is not None:
            return existing
        started = today or _today()
        record = {"started": started.isoformat()}
        record["signature"] = _sign_trial({"started": record["started"]})
        self.directory.mkdir(parents=True, exist_ok=True)
        self.trial_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return started

    def entitlement(self, today: date | None = None) -> Entitlement:
        """Return what this installation is currently entitled to do."""
        today = today or _today()

        license = self.stored_license()
        if license is not None:
            if license.is_expired(today):
                return Entitlement(LicenseStatus.LICENCE_EXPIRED, license)
            return Entitlement(LicenseStatus.LICENSED, license)

        started = self.trial_started_on()
        if started is None:
            # A tampered or missing trial record starts a fresh trial rather
            # than locking the user out of a product they may have paid for.
            started = self.begin_trial(today)

        elapsed = (today - started).days
        if elapsed < 0:
            # The clock moved backwards; treat the trial as beginning today.
            elapsed = 0
        remaining = self.trial_days - elapsed
        if remaining <= 0:
            return Entitlement(LicenseStatus.TRIAL_EXPIRED, None, 0)
        return Entitlement(LicenseStatus.TRIAL, None, remaining)


def has_vendor_key(public_key: str | None = None) -> bool:
    """Return whether this build carries a usable vendor public key."""
    candidate = public_key or VENDOR_PUBLIC_KEY
    try:
        Ed25519PublicKey.from_public_bytes(_b64decode(candidate))
    except (ValueError, TypeError):
        return False
    return True


def generate_key_pair() -> tuple[str, str]:
    """Return a fresh (private, public) base64url key pair. Vendor-side only."""
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64encode(private_raw), _b64encode(public_raw)


def trial_expiry(started: date, trial_days: int = TRIAL_DAYS) -> date:
    """Return the last day of a trial that began on a given date."""
    return started + timedelta(days=trial_days)
