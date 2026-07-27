"""Licence key verification, trial lifecycle, and activation UI."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from duddysheet.core.licensing import (
    TRIAL_DAYS,
    Edition,
    License,
    LicenseError,
    LicenseManager,
    LicenseStatus,
    generate_key_pair,
    has_vendor_key,
    issue_license,
    trial_expiry,
    verify_license,
)
from duddysheet.core.licensing import _b64decode, _b64encode, _canonical
from duddysheet.ui.dialogs.activation import ActivationDialog


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def keys() -> tuple[str, str]:
    return generate_key_pair()


@pytest.fixture
def license() -> License:
    return License(
        licensee="Jordan Blake",
        email="jordan@example.com",
        edition=Edition.BUSINESS,
        seats=1,
        issued=date(2026, 7, 27),
    )


@pytest.fixture
def manager(tmp_path, keys) -> LicenseManager:
    return LicenseManager(tmp_path / "state", public_key=keys[1])


def test_genuine_key_verifies(keys, license) -> None:
    private_key, public_key = keys

    verified = verify_license(issue_license(license, private_key), public_key)

    assert verified == license


def test_key_survives_whitespace_and_line_breaks(keys, license) -> None:
    private_key, public_key = keys
    key = issue_license(license, private_key)
    mangled = f"  {key[:40]}\n{key[40:80]}\r\n {key[80:]}  "

    assert verify_license(mangled, public_key) == license


def test_tampered_payload_is_rejected(keys, license) -> None:
    """Editing the entitlement inside a key must invalidate it."""
    private_key, public_key = keys
    key = issue_license(license, private_key)
    body, _, signature = key.partition(".")
    payload = json.loads(_b64decode(body.split("-", 1)[1]))
    payload["edition"] = Edition.SITE.value
    payload["seats"] = 9999
    forged = f"DS1-{_b64encode(_canonical(payload))}.{signature}"

    with pytest.raises(LicenseError, match="not genuine"):
        verify_license(forged, public_key)


def test_key_from_another_vendor_is_rejected(keys, license) -> None:
    _, public_key = keys
    foreign_private, _ = generate_key_pair()

    with pytest.raises(LicenseError, match="not genuine"):
        verify_license(issue_license(license, foreign_private), public_key)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "Enter a licence key"),
        ("   ", "Enter a licence key"),
        ("hello", "does not look like"),
        ("XX1-abc.def", "does not look like"),
        ("DS1-", "incomplete"),
        ("DS1-onlypayload", "incomplete"),
        ("DS1-abc.def", "not genuine"),
    ],
)
def test_malformed_keys_are_rejected_with_guidance(keys, text, message) -> None:
    _, public_key = keys

    with pytest.raises(LicenseError, match=message):
        verify_license(text, public_key)


def test_build_without_a_vendor_key_cannot_activate(license) -> None:
    private_key, _ = generate_key_pair()
    key = issue_license(license, private_key)

    with pytest.raises(LicenseError, match="no valid vendor key"):
        verify_license(key, "PLACEHOLDER-REPLACE-BEFORE-RELEASE")


def test_shipped_placeholder_key_is_detected() -> None:
    """The release check depends on the placeholder being unusable."""
    assert has_vendor_key("PLACEHOLDER-REPLACE-BEFORE-RELEASE") is False
    assert has_vendor_key(generate_key_pair()[1]) is True


def test_expiring_licence_reports_expiry(keys) -> None:
    private_key, public_key = keys
    expired = License(
        licensee="Sam",
        email="sam@example.com",
        edition=Edition.PERSONAL,
        seats=1,
        issued=date(2025, 1, 1),
        expires=date(2025, 12, 31),
    )

    verified = verify_license(issue_license(expired, private_key), public_key)

    assert verified.is_expired(date(2026, 1, 1)) is True
    assert verified.is_expired(date(2025, 6, 1)) is False


def test_perpetual_licence_never_expires(keys, license) -> None:
    assert license.expires is None
    assert license.is_expired(date(2099, 1, 1)) is False


def test_fresh_install_starts_a_trial(manager) -> None:
    entitlement = manager.entitlement()

    assert entitlement.status is LicenseStatus.TRIAL
    assert entitlement.trial_days_remaining == TRIAL_DAYS
    assert entitlement.allows_use is True


def test_trial_counts_down(manager) -> None:
    started = date(2026, 7, 1)
    manager.begin_trial(started)

    midway = manager.entitlement(started + timedelta(days=10))

    assert midway.status is LicenseStatus.TRIAL
    assert midway.trial_days_remaining == TRIAL_DAYS - 10


def test_trial_expires_after_the_period(manager) -> None:
    started = date(2026, 7, 1)
    manager.begin_trial(started)

    expired = manager.entitlement(started + timedelta(days=TRIAL_DAYS))

    assert expired.status is LicenseStatus.TRIAL_EXPIRED
    assert expired.allows_use is False
    assert expired.trial_days_remaining == 0


def test_trial_start_date_is_not_reset_by_relaunch(manager) -> None:
    first = manager.begin_trial(date(2026, 7, 1))
    second = manager.begin_trial(date(2026, 7, 20))

    assert first == second == date(2026, 7, 1)


def test_editing_the_trial_file_invalidates_it(manager) -> None:
    """A hand-edited start date must not silently extend the trial."""
    manager.begin_trial(date(2026, 7, 1))
    record = json.loads(manager.trial_path.read_text(encoding="utf-8"))
    record["started"] = "2099-01-01"
    manager.trial_path.write_text(json.dumps(record), encoding="utf-8")

    assert manager.trial_started_on() is None


def test_clock_rollback_does_not_extend_the_trial(manager) -> None:
    started = date(2026, 7, 20)
    manager.begin_trial(started)

    earlier = manager.entitlement(date(2026, 7, 1))

    assert earlier.status is LicenseStatus.TRIAL
    assert earlier.trial_days_remaining == TRIAL_DAYS


def test_activation_stores_and_reloads_the_licence(manager, keys, license) -> None:
    private_key, _ = keys
    key = issue_license(license, private_key)

    activated = manager.activate(key)
    reloaded = LicenseManager(manager.directory, public_key=manager.public_key)

    assert activated == license
    assert reloaded.stored_license() == license
    assert reloaded.entitlement().status is LicenseStatus.LICENSED


def test_activated_licence_overrides_an_expired_trial(manager, keys, license) -> None:
    manager.begin_trial(date(2026, 1, 1))
    manager.activate(issue_license(license, keys[0]))

    entitlement = manager.entitlement(date(2026, 12, 31))

    assert entitlement.status is LicenseStatus.LICENSED
    assert entitlement.allows_use is True


def test_activating_an_expired_licence_is_refused(manager, keys) -> None:
    expired = License(
        licensee="Sam",
        email="sam@example.com",
        edition=Edition.PERSONAL,
        seats=1,
        issued=date(2020, 1, 1),
        expires=date(2020, 12, 31),
    )

    with pytest.raises(LicenseError, match="expired"):
        manager.activate(issue_license(expired, keys[0]))
    assert manager.stored_license() is None


def test_stored_licence_that_later_lapses_reports_expiry(manager, keys) -> None:
    """A licence valid at activation must stop entitling use once it lapses."""
    licence = License(
        licensee="Sam",
        email="sam@example.com",
        edition=Edition.PERSONAL,
        seats=1,
        issued=date(2026, 1, 1),
        expires=date(2026, 6, 30),
    )
    # Written directly because activate() rightly refuses an expired key; this
    # reproduces a subscription that lapsed after it was activated.
    manager.directory.mkdir(parents=True, exist_ok=True)
    manager.licence_path.write_text(
        json.dumps({"key": issue_license(licence, keys[0])}), encoding="utf-8"
    )

    assert manager.entitlement(date(2026, 5, 1)).status is LicenseStatus.LICENSED
    lapsed = manager.entitlement(date(2026, 12, 1))

    assert lapsed.status is LicenseStatus.LICENCE_EXPIRED
    assert lapsed.allows_use is False
    assert lapsed.summary == "Licence expired"


def test_deactivation_removes_the_licence(manager, keys, license) -> None:
    manager.activate(issue_license(license, keys[0]))

    manager.deactivate()

    assert manager.stored_license() is None
    assert manager.entitlement().status is LicenseStatus.TRIAL


def test_corrupt_licence_file_falls_back_to_trial(manager) -> None:
    manager.directory.mkdir(parents=True, exist_ok=True)
    manager.licence_path.write_text("{ not json", encoding="utf-8")

    assert manager.stored_license() is None
    assert manager.entitlement().status is LicenseStatus.TRIAL


def test_entitlement_summaries_are_user_readable(manager, keys, license) -> None:
    assert "day" in manager.entitlement().summary

    manager.activate(issue_license(license, keys[0]))
    assert manager.entitlement().summary == "Licensed to Jordan Blake"


def test_trial_expiry_date_is_reported() -> None:
    assert trial_expiry(date(2026, 7, 1), 30) == date(2026, 7, 31)


def test_activation_dialog_accepts_a_genuine_key(
    application, manager, keys, license
) -> None:
    dialog = ActivationDialog(manager)
    try:
        dialog.key_edit.setPlainText(issue_license(license, keys[0]))
        dialog.activate()

        assert manager.stored_license() == license
        assert "Jordan Blake" in dialog.status_label.text()
    finally:
        dialog.deleteLater()


def test_activation_dialog_reports_a_bad_key(application, manager) -> None:
    dialog = ActivationDialog(manager)
    try:
        dialog.key_edit.setPlainText("DS1-nonsense.nonsense")
        dialog.activate()

        assert manager.stored_license() is None
        assert "not genuine" in dialog.message_label.text()
    finally:
        dialog.deleteLater()


def test_activation_dialog_deactivates_when_confirmed(
    application, manager, keys, license, monkeypatch
) -> None:
    manager.activate(issue_license(license, keys[0]))
    dialog = ActivationDialog(manager)
    try:
        monkeypatch.setattr(dialog, "_confirm", lambda question: True)
        assert dialog.deactivate() is True
        assert manager.stored_license() is None
    finally:
        dialog.deleteLater()


def test_activation_dialog_keeps_licence_when_cancelled(
    application, manager, keys, license, monkeypatch
) -> None:
    manager.activate(issue_license(license, keys[0]))
    dialog = ActivationDialog(manager)
    try:
        monkeypatch.setattr(dialog, "_confirm", lambda question: False)
        assert dialog.deactivate() is False
        assert manager.stored_license() == license
    finally:
        dialog.deleteLater()


def test_activation_dialog_shows_trial_status(application, manager) -> None:
    manager.begin_trial(date.today())
    dialog = ActivationDialog(manager)
    try:
        assert "Trial" in dialog.status_label.text()
        assert dialog.deactivate_button.isEnabled() is False
    finally:
        dialog.deleteLater()
