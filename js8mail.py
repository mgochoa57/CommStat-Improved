# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 Email Dialog for CommStat-Improved
Allows sending emails via JS8Call APRS gateway.
"""

import os
import re
from configparser import ConfigParser

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog
import js8callAPIsupport


# =============================================================================
# Constants
# =============================================================================

CONFIG_FILE = "config.ini"
MIN_EMAIL_LENGTH = 8
MIN_SUBJECT_LENGTH = 8
MAX_SUBJECT_LENGTH = 67
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

FONT_FAMILY = "Arial"
FONT_SIZE = 12
WINDOW_WIDTH = 550
WINDOW_HEIGHT = 340


# =============================================================================
# JS8Mail Dialog
# =============================================================================

class JS8MailDialog(QDialog):
    """Modern JS8 Email form for sending emails via APRS gateway."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CommStat-Improved JS8Mail")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        # Set window icon
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        # Configuration
        self.server_ip = "127.0.0.1"
        self.server_port = "2242"

        # Load config and initialize API
        self._load_config()
        self.api = js8callAPIsupport.js8CallUDPAPICalls(
            self.server_ip, int(self.server_port)
        )

        # Build UI
        self._setup_ui()

    def _load_config(self) -> None:
        """Load configuration from config.ini."""
        if not os.path.exists(CONFIG_FILE):
            return

        config = ConfigParser()
        config.read(CONFIG_FILE)

        if "DIRECTEDCONFIG" in config:
            dirconfig = config["DIRECTEDCONFIG"]
            self.server_ip = dirconfig.get("server", "127.0.0.1")
            self.server_port = dirconfig.get("udp_port", "2242")

    def _setup_ui(self) -> None:
        """Build the user interface."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 20, 25, 20)

        # Title
        title = QtWidgets.QLabel("JS8Call Email")
        title.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 5px;")
        layout.addWidget(title)

        # Warning
        warning = QtWidgets.QLabel("Sending email depends on APRS services being available.")
        warning.setAlignment(Qt.AlignCenter)
        warning.setFont(QtGui.QFont(FONT_FAMILY, 10, QtGui.QFont.Bold))
        warning.setStyleSheet("color: #dc3545;")
        layout.addWidget(warning)

        # Input field style
        input_style = "padding: 8px; font-size: 13px;"

        # Email field
        email_layout = QtWidgets.QVBoxLayout()
        email_layout.setSpacing(2)
        email_label = QtWidgets.QLabel("Email Address:")
        email_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.email_field = QtWidgets.QLineEdit()
        self.email_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.email_field.setMinimumHeight(36)
        self.email_field.setStyleSheet(input_style)
        self.email_field.setMaxLength(40)
        self.email_field.setPlaceholderText("recipient@example.com")
        email_layout.addWidget(email_label)
        email_layout.addWidget(self.email_field)
        layout.addLayout(email_layout)

        # Subject field
        subject_layout = QtWidgets.QVBoxLayout()
        subject_layout.setSpacing(2)
        subject_label = QtWidgets.QLabel("Message (Subject Line):")
        subject_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.subject_field = QtWidgets.QLineEdit()
        self.subject_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.subject_field.setMinimumHeight(36)
        self.subject_field.setStyleSheet(input_style)
        self.subject_field.setMaxLength(MAX_SUBJECT_LENGTH)
        self.subject_field.setPlaceholderText("Your message here (max 67 characters)")
        subject_layout.addWidget(subject_label)
        subject_layout.addWidget(self.subject_field)
        layout.addLayout(subject_layout)

        # Note
        note = QtWidgets.QLabel(
            "APRS emails are sent in the subject line. Replies are not supported."
        )
        note.setAlignment(Qt.AlignCenter)
        note.setFont(QtGui.QFont(FONT_FAMILY, 10))
        note.setStyleSheet(
            "color: #856404; background-color: #fff3cd; "
            "padding: 10px; border-radius: 4px;"
        )
        layout.addWidget(note)

        # Spacer
        layout.addStretch()

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)

        button_layout.addStretch()

        btn_transmit = QtWidgets.QPushButton("Transmit")
        btn_transmit.clicked.connect(self._on_transmit)
        btn_transmit.setStyleSheet(self._button_style("#007bff"))
        btn_transmit.setMinimumWidth(100)
        button_layout.addWidget(btn_transmit)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_cancel.setStyleSheet(self._button_style("#6c757d"))
        btn_cancel.setMinimumWidth(100)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

    def _button_style(self, color: str) -> str:
        """Generate button stylesheet."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat-Improved Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate(self) -> bool:
        """Validate form fields. Returns True if valid."""
        email = self.email_field.text().strip()
        subject = self.subject_field.text().strip()

        if len(email) < MIN_EMAIL_LENGTH or not re.match(EMAIL_PATTERN, email):
            self._show_error("Please enter a valid email address.")
            self.email_field.setFocus()
            return False

        if len(subject) < MIN_SUBJECT_LENGTH:
            self._show_error(f"Message is too short (minimum {MIN_SUBJECT_LENGTH} characters).")
            self.subject_field.setFocus()
            return False

        return True

    def _on_transmit(self) -> None:
        """Validate and transmit the email."""
        if not self._validate():
            return

        email = self.email_field.text().strip()
        subject = self.subject_field.text().strip()

        # Build message
        message = f"@APRSIS CMD :EMAIL-2  :{email} {subject}{{03}}"

        try:
            self.api.sendMessage(js8callAPIsupport.TYPE_TX_SETMESSAGE, message)

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"JS8MAIL TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  To:       {email}")
            print(f"  Message:  {subject}")
            print(f"  Full TX:  {message}")
            print(f"{'='*60}\n")

            self.accept()

        except Exception as e:
            self._show_error(f"Failed to transmit: {e}")


# =============================================================================
# Standalone Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = JS8MailDialog()
    dialog.show()
    sys.exit(app.exec_())
