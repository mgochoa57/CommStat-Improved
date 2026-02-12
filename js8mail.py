# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 Email Dialog for CommStat
Allows sending emails via JS8Call APRS gateway.
"""

import os
import re
from configparser import ConfigParser
from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


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


def make_uppercase(field):
    """Force uppercase input on a QLineEdit."""
    def to_upper(text):
        if text != text.upper():
            pos = field.cursorPosition()
            field.blockSignals(True)
            field.setText(text.upper())
            field.blockSignals(False)
            field.setCursorPosition(pos)
    field.textChanged.connect(to_upper)


# =============================================================================
# JS8Mail Dialog
# =============================================================================

class JS8MailDialog(QDialog):
    """Modern JS8 Email form for sending emails via APRS gateway."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        parent=None
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager

        self.setWindowTitle("CommStat JS8Mail")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT + 40)
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

        # Build UI
        self._setup_ui()

        # Load rigs
        self._load_rigs()

    def _load_rigs(self) -> None:
        """Load connected rigs into the rig dropdown.

        Auto-selects only if exactly 1 rig is connected.
        If multiple rigs are connected, user must select one.
        """
        if not self.tcp_pool:
            return

        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        # Get connected rigs
        connected_rigs = self.tcp_pool.get_connected_rig_names()

        if not connected_rigs:
            # No connected rigs - show all configured rigs as disconnected
            all_rigs = self.tcp_pool.get_all_rig_names()
            if all_rigs:
                self.rig_combo.addItem("")  # Empty first item
                for rig_name in all_rigs:
                    self.rig_combo.addItem(f"{rig_name} (disconnected)")
        elif len(connected_rigs) == 1:
            # Exactly 1 connected rig - auto-select it
            self.rig_combo.addItem(connected_rigs[0])
        else:
            # Multiple connected rigs - require user selection
            self.rig_combo.addItem("")  # Empty first item
            for rig_name in connected_rigs:
                self.rig_combo.addItem(rig_name)

        self.rig_combo.blockSignals(False)

        # Trigger rig changed to populate mode/frequency (only if a rig is selected)
        current_text = self.rig_combo.currentText()
        if current_text and "(disconnected)" not in current_text:
            self._on_rig_changed(current_text)

    def _setup_ui(self) -> None:
        """Build the user interface."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QtWidgets.QLabel("CommStat JS8 Email")
        title.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 5px;")
        layout.addWidget(title)

        # Rig selection
        rig_layout = QtWidgets.QHBoxLayout()
        rig_label = QtWidgets.QLabel("Rig:")
        rig_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.rig_combo.setMinimumWidth(150)
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        rig_layout.addWidget(rig_label)
        rig_layout.addWidget(self.rig_combo)
        # Mode dropdown
        mode_label = QtWidgets.QLabel("Mode:")
        mode_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        rig_layout.addWidget(mode_label)
        rig_layout.addWidget(self.mode_combo)
        # Frequency field
        freq_label = QtWidgets.QLabel("Freq:")
        freq_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field.setMaximumWidth(80)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet("background-color: #f0f0f0;")
        rig_layout.addWidget(freq_label)
        rig_layout.addWidget(self.freq_field)
        rig_layout.addStretch()
        layout.addLayout(rig_layout)

        # Warning
        warning = QtWidgets.QLabel("Sending email depends on APRS services being available.")
        warning.setAlignment(Qt.AlignCenter)
        warning.setFont(QtGui.QFont(FONT_FAMILY, 10, QtGui.QFont.Bold))
        warning.setStyleSheet("color: #dc3545;")
        layout.addWidget(warning)

        # Input field style
        input_style = "padding: 8px;"

        # Email field
        email_layout = QtWidgets.QVBoxLayout()
        email_layout.setSpacing(2)
        email_label = QtWidgets.QLabel("Email Address:")
        email_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.email_field = QtWidgets.QLineEdit()
        self.email_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.email_field.setMinimumHeight(36)
        self.email_field.setMinimumWidth(300)
        self.email_field.setStyleSheet(input_style)
        self.email_field.setMaxLength(40)
        self.email_field.setPlaceholderText("recipient@example.com")
        make_uppercase(self.email_field)
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
        self.subject_field.setMinimumWidth(500)
        self.subject_field.setStyleSheet(input_style)
        self.subject_field.setMaxLength(MAX_SUBJECT_LENGTH)
        self.subject_field.setPlaceholderText("Your message here (max 67 characters)")
        make_uppercase(self.subject_field)
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
        btn_cancel.setStyleSheet(self._button_style("#dc3545"))
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
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - update mode/frequency display."""
        if not rig_name or "(disconnected)" in rig_name:
            self.freq_field.setText("")
            return

        if not self.tcp_pool:
            return

        # Disconnect frequency signal from all clients to avoid duplicates
        for client_name in self.tcp_pool.get_all_rig_names():
            client = self.tcp_pool.get_client(client_name)
            if client:
                try:
                    client.frequency_received.disconnect(self._on_frequency_received)
                except TypeError:
                    pass

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Connect frequency signal for this client
            client.frequency_received.connect(self._on_frequency_received)

            # Populate mode dropdown with current mode preselected
            speed_name = (client.speed_name or "").upper()
            mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3}
            idx = mode_map.get(speed_name, 1)  # Default to Normal
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(idx)
            self.mode_combo.blockSignals(False)

            # Populate frequency field with cached value initially
            frequency = client.frequency
            if frequency:
                self.freq_field.setText(f"{frequency:.3f}")
            else:
                self.freq_field.setText("")

            # Request fresh frequency from JS8Call
            client.get_frequency()
        else:
            self.freq_field.setText("")

    def _on_frequency_received(self, rig_name: str, dial_freq: int) -> None:
        """Handle frequency received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            frequency_mhz = dial_freq / 1000000
            self.freq_field.setText(f"{frequency_mhz:.3f}")

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode dropdown change - send MODE.SET_SPEED to JS8Call."""
        rig_name = self.rig_combo.currentText()
        if not rig_name or "(disconnected)" in rig_name:
            return

        if not self.tcp_pool:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})
            print(f"[JS8Mail] Set mode to {self.mode_combo.currentText()} (speed={speed_value})")

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat Error")
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

        rig_name = self.rig_combo.currentText()
        if "(disconnected)" in rig_name:
            self._show_error("Cannot transmit: rig is disconnected")
            return

        if not self.tcp_pool:
            self._show_error("Cannot transmit: TCP pool not available")
            return

        client = self.tcp_pool.get_client(rig_name)
        if not client or not client.is_connected():
            self._show_error("Cannot transmit: not connected to rig")
            return

        email = self.email_field.text().strip()
        subject = self.subject_field.text().strip()

        # Build and store message for transmission after check
        self._pending_message = f"@APRSIS CMD :EMAIL-2  :{email} {subject}{{03}}"
        self._pending_email = email
        self._pending_subject = subject

        # First check if a call is selected in JS8Call
        try:
            client.call_selected_received.disconnect(self._on_call_selected_for_transmit)
        except TypeError:
            pass
        client.call_selected_received.connect(self._on_call_selected_for_transmit)
        client.get_call_selected()

    def _on_call_selected_for_transmit(self, rig_name: str, selected_call: str) -> None:
        """Handle call selected response - check if clear to transmit."""
        if self.rig_combo.currentText() != rig_name:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client:
            try:
                client.call_selected_received.disconnect(self._on_call_selected_for_transmit)
            except TypeError:
                pass

        # If a call is selected, show error and abort
        if selected_call:
            QMessageBox.critical(
                self, "ERROR",
                f"JS8Call has {selected_call} selected.\n\n"
                "Go to JS8Call and click the \"Deselect\" button."
            )
            return

        # No call selected - proceed with transmission
        try:
            client.send_tx_message(self._pending_message)

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"JS8MAIL TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  Rig:      {rig_name}")
            print(f"  To:       {self._pending_email}")
            print(f"  Message:  {self._pending_subject}")
            print(f"  Full TX:  {self._pending_message}")
            print(f"{'='*60}\n")

            self.accept()

        except Exception as e:
            self._show_error(f"Failed to transmit: {e}")


# =============================================================================
# Standalone Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    from connector_manager import ConnectorManager
    from js8_tcp_client import TCPConnectionPool

    app = QtWidgets.QApplication(sys.argv)

    # Initialize dependencies
    connector_manager = ConnectorManager()
    connector_manager.init_connectors_table()
    tcp_pool = TCPConnectionPool(connector_manager)
    tcp_pool.connect_all()

    dialog = JS8MailDialog(tcp_pool, connector_manager)
    dialog.show()
    sys.exit(app.exec_())
