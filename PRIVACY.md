# Privacy Statement

**Duddy Spreadsheet 1.0.0 — effective 27 July 2026**

## The short version

Duddy Spreadsheet does not collect anything. It has no telemetry, no
analytics, no crash reporting, no update pings, and no account. It makes no
network connection during normal operation. Your workbooks never leave your
machine.

This is a deliberate design property, not a policy promise: the application
ships no networking code for these purposes, and the licence activation
described below is verified offline.

## What stays on your device

The application writes only to your own machine:

| Data | Location | Purpose |
|---|---|---|
| Your workbooks | Wherever you save them | Your documents |
| Crash-recovery snapshots | `%LOCALAPPDATA%\DuddySpreadsheet\autosave` | Restoring unsaved work |
| Diagnostic logs | `%LOCALAPPDATA%\DuddySpreadsheet\logs` | Local troubleshooting |
| Preferences and recent files | `%LOCALAPPDATA%\DuddySpreadsheet\settings.json` | Restoring your setup |
| Licence key and trial state | `%LOCALAPPDATA%\DuddySpreadsheet` | Activation |

Logs record application events, not workbook contents. Nothing in this table
is transmitted anywhere. You may delete any of it at any time; the
application recreates what it needs.

## Licence activation

Licence keys are cryptographically signed and verified **offline** against a
public key embedded in the application. Activating does not contact us and
does not require an internet connection. We therefore do not learn when,
where, how often, or on what hardware you run the software.

## What we receive

Only what you deliberately send us:

- **Email support.** If you email support we receive your message and
  anything you attach. Attach a workbook only if you intend us to see it. We
  retain support correspondence for up to 24 months.
- **Purchases.** Payment is handled by our payment processor, who collects
  the billing details needed to complete the sale and remit tax. We receive
  your name, email, and country. We never receive your card number.

## Third parties

The application bundles third-party libraries (see
THIRD-PARTY-NOTICES.md). None of them are configured to transmit data, and
the application does not initialise any network stack.

Following a hyperlink in a workbook opens your default browser and is a
normal web request to that destination, subject to that site's practices
rather than ours. This only happens when you click a link.

## Your rights

Because we hold almost no personal data, most access and deletion requests
concern support correspondence and purchase records. Email
support@duddysoftware.com and we will respond within 30 days. Where the GDPR
or comparable law applies, you have rights of access, rectification,
erasure, restriction, portability, and objection, and may complain to your
supervisory authority.

## Regulated and air-gapped environments

Duddy Spreadsheet is intended to be safe to run where cloud tooling is
prohibited. It functions fully with no network adapter present, and it will
not degrade, nag, or disable features when offline. If your environment
requires written confirmation of this for an assessment, email us and we
will provide it.

## Changes

Material changes to this statement will be published with the release that
introduces them and reflected in the version and date above. This statement
covers the version named above; it does not retroactively change what an
earlier version did.

## Contact

Duddy Software — support@duddysoftware.com — https://duddysoftware.com
