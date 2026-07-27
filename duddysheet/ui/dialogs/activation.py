"""Licence activation and trial status.

The dialog performs no network access: keys are verified against the vendor
public key compiled into the build, which is what allows activation to work in
air-gapped environments.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from duddysheet.branding import PRODUCT_NAME, SUPPORT_EMAIL, WEBSITE
from duddysheet.core.licensing import (
    Entitlement,
    LicenseError,
    LicenseManager,
    LicenseStatus,
)


class ActivationDialog(QDialog):
    """Show entitlement status and accept a licence key."""

    def __init__(
        self,
        manager: LicenseManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle(f"Activate {PRODUCT_NAME}")
        self.resize(560, 380)

        layout = QVBoxLayout(self)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        instructions = QLabel(
            "Paste your licence key below. Activation is offline: no "
            "connection is made and no information leaves this computer.",
            self,
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.key_edit = QPlainTextEdit(self)
        self.key_edit.setPlaceholderText("DS1-...")
        self.key_edit.setMaximumHeight(110)
        layout.addWidget(self.key_edit)

        self.message_label = QLabel("", self)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        purchase = QLabel(
            f'Need a licence? Visit <a href="{WEBSITE}">{WEBSITE}</a> '
            f'or email <a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>.',
            self,
        )
        purchase.setOpenExternalLinks(True)
        purchase.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        purchase.setWordWrap(True)
        layout.addWidget(purchase)

        buttons = QDialogButtonBox(self)
        self.activate_button = buttons.addButton(
            "Activate", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.deactivate_button = buttons.addButton(
            "Deactivate", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.activate_button.clicked.connect(self.activate)
        self.deactivate_button.clicked.connect(self.deactivate)
        layout.addWidget(buttons)

        self.refresh()

    def refresh(self) -> None:
        """Update the status text from current entitlement."""
        entitlement = self.manager.entitlement()
        self.status_label.setText(f"<b>{entitlement.summary}</b>")
        self.deactivate_button.setEnabled(
            entitlement.status is LicenseStatus.LICENSED
        )

    def activate(self) -> bool:
        """Verify and store the entered key, reporting the outcome inline."""
        try:
            license = self.manager.activate(self.key_edit.toPlainText())
        except LicenseError as error:
            self.message_label.setText(f"<span style='color:#b00020'>{error}</span>")
            return False

        self.message_label.setText(
            f"<span style='color:#1b5e20'>Thank you. {PRODUCT_NAME} is "
            f"licensed to {license.licensee}.</span>"
        )
        self.key_edit.clear()
        self.refresh()
        return True

    def deactivate(self) -> bool:
        """Remove the stored licence after confirming."""
        if not self._confirm(
            "Remove the licence from this computer? You will need the key "
            "again to reactivate."
        ):
            return False
        self.manager.deactivate()
        self.key_edit.clear()
        self.message_label.setText("Licence removed from this computer.")
        self.refresh()
        return True

    def _confirm(self, question: str) -> bool:
        """Ask the user to confirm a destructive action."""
        return (
            QMessageBox.question(self, "Deactivate", question)
            == QMessageBox.StandardButton.Yes
        )


def prompt_when_trial_expired(
    entitlement: Entitlement,
    manager: LicenseManager,
    parent: QWidget | None = None,
) -> bool:
    """Show activation when the entitlement has lapsed.

    Returns whether the product may be used. Expiry is never allowed to
    destroy work: the caller keeps the application open and read-only rather
    than closing over unsaved changes.
    """
    if entitlement.allows_use:
        return True

    dialog = ActivationDialog(manager, parent)
    dialog.message_label.setText(
        "<span style='color:#b00020'>Your evaluation period has ended. "
        "Enter a licence key to continue.</span>"
    )
    dialog.exec()
    return manager.entitlement().allows_use
