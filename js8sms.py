# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 SMS Dialog for CommStat-Improved
Allows sending SMS messages via JS8Call APRS gateway.
"""

import os
from configparser import ConfigParser

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog
import js8callAPIsupport


# =============================================================================
# Constants
# =============================================================================

CONFIG_FILE = "config.ini"
MIN_PHONE_LENGTH = 10  # 10 digits
MIN_MESSAGE_LENGTH = 8
MAX_MESSAGE_LENGTH = 67

FONT_FAMILY = "Arial"
FONT_SIZE = 12
WINDOW_WIDTH = 550
WINDOW_HEIGHT = 380


# =============================================================================
# JS8SMS Dialog
# =============================================================================

class JS8SMSDialog(QDialog):
    """Modern JS8 SMS form for sending text messages via APRS gateway."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CommStat-Improved JS8SMS")
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
        title = QtWidgets.QLabel("JS8Call SMS")
        title.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 5px;")
        layout.addWidget(title)

        # Warning
        warning = QtWidgets.QLabel("Sending SMS depends on APRS services being available.")
        warning.setAlignment(Qt.AlignCenter)
        warning.setFont(QtGui.QFont(FONT_FAMILY, 10, QtGui.QFont.Bold))
        warning.setStyleSheet("color: #dc3545;")
        layout.addWidget(warning)

        # Input field style
        input_style = "padding: 8px; font-size: 13px;"

        # Phone field
        phone_layout = QtWidgets.QVBoxLayout()
        phone_layout.setSpacing(2)
        phone_label = QtWidgets.QLabel("Phone Number:")
        phone_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.phone_field = QtWidgets.QLineEdit()
        self.phone_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.phone_field.setMinimumHeight(36)
        self.phone_field.setStyleSheet(input_style)
        self.phone_field.setInputMask("999-999-9999")
        self.phone_field.setPlaceholderText("xxx-xxx-xxxx")
        phone_layout.addWidget(phone_label)
        phone_layout.addWidget(self.phone_field)
        layout.addLayout(phone_layout)

        # Message field
        message_layout = QtWidgets.QVBoxLayout()
        message_layout.setSpacing(2)
        message_label = QtWidgets.QLabel("Text Message:")
        message_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.message_field = QtWidgets.QLineEdit()
        self.message_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.message_field.setMinimumHeight(36)
        self.message_field.setStyleSheet(input_style)
        self.message_field.setMaxLength(MAX_MESSAGE_LENGTH)
        self.message_field.setPlaceholderText("Your message here (max 67 characters)")
        message_layout.addWidget(message_label)
        message_layout.addWidget(self.message_field)
        layout.addLayout(message_layout)

        # Note
        note = QtWidgets.QLabel(
            "Recipients must often opt-in on the SMS gateway before delivery will work.\n"
            "SMS delivery is highly unreliable."
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
        phone = self.phone_field.text().replace("-", "").strip()
        message = self.message_field.text().strip()

        if len(phone) < MIN_PHONE_LENGTH:
            self._show_error("Please enter a valid 10-digit phone number.")
            self.phone_field.setFocus()
            return False

        if len(message) < MIN_MESSAGE_LENGTH:
            self._show_error(f"Message is too short (minimum {MIN_MESSAGE_LENGTH} characters).")
            self.message_field.setFocus()
            return False

        return True

    def _on_transmit(self) -> None:
        """Validate and transmit the SMS."""
        if not self._validate():
            return

        phone = self.phone_field.text().strip()
        message_text = self.message_field.text().strip()

        # Build message
        message = f"@APRSIS CMD :SMSGTE   :@{phone}  {message_text} {{04}}"

        try:
            self.api.sendMessage(js8callAPIsupport.TYPE_TX_SETMESSAGE, message)

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"JS8SMS TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  To:       {phone}")
            print(f"  Message:  {message_text}")
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
    dialog = JS8SMSDialog()
    dialog.show()
    sys.exit(app.exec_())
