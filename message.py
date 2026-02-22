# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Message Dialog for CommStat
Allows creating and transmitting messages via JS8Call.
"""

import base64
import os
import re
import sqlite3
import sys
import threading
import urllib.parse
import urllib.request
from typing import Optional, TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# Constants
MIN_CALLSIGN_LENGTH = 4
MAX_CALLSIGN_LENGTH = 8
MIN_MESSAGE_LENGTH = 4
MAX_MESSAGE_LENGTH = 67
DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"

# Backbone server (base64 encoded)
_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED = _BACKBONE + "/datafeed-808585.php"

# Debug mode via --debug-mode command line flag
_DEBUG_MODE = "--debug-mode" in sys.argv

INTERNET_RIG = "INTERNET ONLY"

# Callsign pattern for international amateur radio
CALLSIGN_PATTERN = re.compile(r'[A-Z0-9]{1,3}[0-9][A-Z]{1,3}')


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


class Ui_FormMessage:
    """Message form for creating and transmitting messages."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        refresh_callback = None
    ):
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager
        self.refresh_callback = refresh_callback
        self.MainWindow: Optional[QtWidgets.QWidget] = None
        self.callsign: str = ""
        self.grid: str = ""
        self.selected_group: str = ""
        self.msg_id: str = ""
        self._pending_message: str = ""
        self._pending_callsign: str = ""

    def setupUi(self, FormMessage: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormMessage
        FormMessage.setObjectName("FormMessage")
        FormMessage.resize(835, 344)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(12)
        FormMessage.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormMessage.setWindowIcon(icon)

        # Title
        self.title_label = QtWidgets.QLabel(FormMessage)
        self.title_label.setGeometry(QtCore.QRect(58, 10, 400, 30))
        title_font = QtGui.QFont("Arial", 16, QtGui.QFont.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setText("CommStat Group Message")
        self.title_label.setStyleSheet("color: #333;")
        self.title_label.setObjectName("title_label")

        # Settings row label (left column, vertically centered in row)
        self.settings_label = QtWidgets.QLabel(FormMessage)
        self.settings_label.setGeometry(QtCore.QRect(58, 72, 120, 20))
        self.settings_label.setFont(font)
        self.settings_label.setText("Settings:")
        self.settings_label.setObjectName("settings_label")

        # Rig dropdown (label above control, aligned with other controls at x=190)
        self.rig_label = QtWidgets.QLabel(FormMessage)
        self.rig_label.setGeometry(QtCore.QRect(190, 46, 150, 20))
        self.rig_label.setFont(font)
        self.rig_label.setText("Rig:")
        self.rig_label.setObjectName("rig_label")

        self.rig_combo = QtWidgets.QComboBox(FormMessage)
        self.rig_combo.setGeometry(QtCore.QRect(190, 72, 150, 26))
        self.rig_combo.setFont(font)
        self.rig_combo.setObjectName("rig_combo")

        # Mode dropdown (label above control)
        self.mode_label = QtWidgets.QLabel(FormMessage)
        self.mode_label.setGeometry(QtCore.QRect(350, 46, 100, 20))
        self.mode_label.setFont(font)
        self.mode_label.setText("Mode:")
        self.mode_label.setObjectName("mode_label")

        self.mode_combo = QtWidgets.QComboBox(FormMessage)
        self.mode_combo.setGeometry(QtCore.QRect(350, 72, 100, 26))
        self.mode_combo.setFont(font)
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.setObjectName("mode_combo")

        # Frequency field (label above control)
        self.freq_label = QtWidgets.QLabel(FormMessage)
        self.freq_label.setGeometry(QtCore.QRect(460, 46, 80, 20))
        self.freq_label.setFont(font)
        self.freq_label.setText("Freq:")
        self.freq_label.setObjectName("freq_label")

        self.freq_field = QtWidgets.QLineEdit(FormMessage)
        self.freq_field.setGeometry(QtCore.QRect(460, 72, 80, 26))
        self.freq_field.setFont(font)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet("background-color: #f0f0f0;")
        self.freq_field.setObjectName("freq_field")

        # Delivery dropdown (label above control)
        self.delivery_label = QtWidgets.QLabel(FormMessage)
        self.delivery_label.setGeometry(QtCore.QRect(550, 46, 150, 20))
        self.delivery_label.setFont(font)
        self.delivery_label.setText("Delivery:")
        self.delivery_label.setObjectName("delivery_label")

        self.delivery_combo = QtWidgets.QComboBox(FormMessage)
        self.delivery_combo.setGeometry(QtCore.QRect(550, 72, 150, 26))
        self.delivery_combo.setFont(font)
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        self.delivery_combo.setObjectName("delivery_combo")

        # Group dropdown
        self.group_label = QtWidgets.QLabel(FormMessage)
        self.group_label.setGeometry(QtCore.QRect(58, 107, 120, 20))
        self.group_label.setFont(font)
        self.group_label.setText("Group:")
        self.group_label.setObjectName("group_label")

        self.group_combo = QtWidgets.QComboBox(FormMessage)
        self.group_combo.setGeometry(QtCore.QRect(190, 107, 150, 26))
        self.group_combo.setFont(font)
        self.group_combo.setObjectName("group_combo")

        # Callsign input (read-only, from JS8Call)
        self.label_3 = QtWidgets.QLabel(FormMessage)
        self.label_3.setGeometry(QtCore.QRect(58, 142, 120, 20))
        self.label_3.setFont(font)
        self.label_3.setObjectName("label_3")

        self.lineEdit_3 = QtWidgets.QLineEdit(FormMessage)
        self.lineEdit_3.setGeometry(QtCore.QRect(190, 142, 100, 26))
        self.lineEdit_3.setFont(font)
        self.lineEdit_3.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.lineEdit_3.setReadOnly(True)
        self.lineEdit_3.setStyleSheet("background-color: #e9ecef;")
        self.lineEdit_3.setObjectName("lineEdit_3")

        # Message input
        self.label_2 = QtWidgets.QLabel(FormMessage)
        self.label_2.setGeometry(QtCore.QRect(58, 177, 120, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        self.lineEdit_2 = QtWidgets.QLineEdit(FormMessage)
        self.lineEdit_2.setGeometry(QtCore.QRect(190, 177, 530, 26))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(MAX_MESSAGE_LENGTH)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Character limit note
        self.note_label = QtWidgets.QLabel(FormMessage)
        self.note_label.setGeometry(QtCore.QRect(190, 207, 481, 20))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(10)
        note_font.setBold(True)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #AA0000;")
        self.note_label.setText("Messages are limited to 67 characters.")
        self.note_label.setObjectName("note_label")

        # Delivery legend
        self.delivery_legend_label = QtWidgets.QLabel(FormMessage)
        self.delivery_legend_label.setGeometry(QtCore.QRect(190, 229, 481, 20))
        self.delivery_legend_label.setFont(note_font)
        self.delivery_legend_label.setStyleSheet("color: #AA0000;")
        self.delivery_legend_label.setText("Delivery: Maximum Reach = RF + Internet | Limited Reach = RF Only")
        self.delivery_legend_label.setObjectName("delivery_legend_label")

        # Buttons
        self.pushButton_3 = QtWidgets.QPushButton(FormMessage)
        self.pushButton_3.setGeometry(QtCore.QRect(410, 264, 100, 32))
        self.pushButton_3.setObjectName("pushButton_3")
        self.pushButton_3.clicked.connect(self._save_only)
        self.pushButton_3.setStyleSheet(self._button_style("#17a2b8"))

        self.pushButton = QtWidgets.QPushButton(FormMessage)
        self.pushButton.setGeometry(QtCore.QRect(520, 264, 100, 32))
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self._transmit)
        self.pushButton.setStyleSheet(self._button_style("#007bff"))

        self.pushButton_2 = QtWidgets.QPushButton(FormMessage)
        self.pushButton_2.setGeometry(QtCore.QRect(630, 264, 100, 32))
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)
        self.pushButton_2.setStyleSheet(self._button_style("#dc3545"))

        self.retranslateUi(FormMessage)
        QtCore.QMetaObject.connectSlotsByName(FormMessage)

        # Load config and initialize
        self._generate_msg_id()
        self._load_config()

        # Connect rig combo signal
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)

        # Connect mode combo signal
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        # Load rigs into dropdown
        self._load_rigs()

        self.MainWindow.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

    def retranslateUi(self, FormMessage: QtWidgets.QWidget) -> None:
        """Set UI text labels."""
        _translate = QtCore.QCoreApplication.translate
        FormMessage.setWindowTitle(_translate("FormMessage", "CommStat Send Message"))
        self.label_2.setText(_translate("FormMessage", "Message:"))
        self.label_3.setText(_translate("FormMessage", "From Callsign:"))
        self.pushButton.setText(_translate("FormMessage", "Transmit"))
        self.pushButton_2.setText(_translate("FormMessage", "Cancel"))
        self.pushButton_3.setText(_translate("FormMessage", "Save Only"))

    def _load_config(self) -> None:
        """Load configuration from database.

        Auto-selects group only if exactly 1 group exists.
        If multiple groups exist, user must select one.
        """
        # Get active group from database
        self.selected_group = self._get_active_group_from_db()

        # Populate group dropdown
        all_groups = self._get_all_groups_from_db()
        if len(all_groups) == 1:
            # Exactly 1 group - auto-select it
            self.group_combo.addItem(all_groups[0])
        else:
            # Multiple groups or no groups - require user selection
            self.group_combo.addItem("")  # Empty first item
            for group in all_groups:
                self.group_combo.addItem(group)
        # Callsign will be loaded from JS8Call when rig is selected

    def _load_rigs(self) -> None:
        """Load enabled connectors into the rig dropdown, plus Internet option."""
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        enabled_connectors = self.connector_manager.get_all_connectors(enabled_only=True) if self.connector_manager else []
        connected_rigs = self.tcp_pool.get_connected_rig_names() if self.tcp_pool else []
        enabled_count = len(enabled_connectors)

        if enabled_count == 0:
            # No enabled connectors — Internet is the only/preselected option
            self.rig_combo.addItem(INTERNET_RIG)
        elif enabled_count == 1:
            # 1 enabled connector — preselect it; Internet still available
            rig_name = enabled_connectors[0]['rig_name']
            label = rig_name if rig_name in connected_rigs else f"{rig_name} (disconnected)"
            self.rig_combo.addItem(label)
            self.rig_combo.addItem(INTERNET_RIG)
        else:
            # Multiple enabled connectors — require selection; Internet at bottom
            self.rig_combo.addItem("")  # empty first
            for c in enabled_connectors:
                rig_name = c['rig_name']
                label = rig_name if rig_name in connected_rigs else f"{rig_name} (disconnected)"
                self.rig_combo.addItem(label)
            self.rig_combo.addItem(INTERNET_RIG)

        self.rig_combo.blockSignals(False)

        current_text = self.rig_combo.currentText()
        if current_text:
            self._on_rig_changed(current_text)

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - fetch callsign from JS8Call."""
        if not rig_name or "(disconnected)" in rig_name:
            self.callsign = ""
            self.lineEdit_3.setText("")
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")
            return

        is_internet = (rig_name == INTERNET_RIG)
        if hasattr(self, 'delivery_combo'):
            self.delivery_combo.blockSignals(True)
            self.delivery_combo.clear()
            self.delivery_combo.addItem("Maximum Reach")
            if not is_internet:
                self.delivery_combo.addItem("Limited Reach")
            self.delivery_combo.blockSignals(False)

        if rig_name == INTERNET_RIG:
            callsign = self._get_internet_callsign()
            self.callsign = callsign
            self.lineEdit_3.setText(callsign)
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")
            if hasattr(self, 'mode_combo'):
                self.mode_combo.setEnabled(False)
            return

        if not self.tcp_pool:
            return

        # Re-enable mode combo for real rig
        if hasattr(self, 'mode_combo'):
            self.mode_combo.setEnabled(True)

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Populate mode dropdown with current mode preselected
            if hasattr(self, 'mode_combo'):
                speed_name = (client.speed_name or "").upper()
                mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3}
                idx = mode_map.get(speed_name, 1)  # Default to Normal
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(idx)
                self.mode_combo.blockSignals(False)

            # Populate frequency field
            if hasattr(self, 'freq_field'):
                frequency = client.frequency
                if frequency:
                    self.freq_field.setText(f"{frequency:.3f}")
                else:
                    self.freq_field.setText("")

            # Connect signals for this client (disconnect any existing first)
            try:
                client.callsign_received.disconnect(self._on_callsign_received)
            except TypeError:
                pass
            try:
                client.frequency_received.disconnect(self._on_frequency_received)
            except TypeError:
                pass

            client.callsign_received.connect(self._on_callsign_received)
            client.frequency_received.connect(self._on_frequency_received)

            # Request callsign and frequency from JS8Call
            client.get_callsign()
            QtCore.QTimer.singleShot(100, client.get_frequency)
        else:
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        """Handle callsign received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            self.lineEdit_3.setText(callsign)

    def _on_frequency_received(self, rig_name: str, dial_freq: int) -> None:
        """Handle frequency received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            frequency_mhz = dial_freq / 1000000
            if hasattr(self, 'freq_field'):
                self.freq_field.setText(f"{frequency_mhz:.3f}")

    def _get_internet_callsign(self) -> str:
        """Get callsign from User Settings for internet-only transmission."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT callsign FROM controls WHERE id = 1")
                row = cursor.fetchone()
                return (row[0] or "").strip().upper() if row else ""
        except sqlite3.Error:
            return ""

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode dropdown change - send MODE.SET_SPEED to JS8Call."""
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == INTERNET_RIG or "(disconnected)" in rig_name:
            return

        if not self.tcp_pool:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})
            print(f"[Message] Set mode to {self.mode_combo.currentText()} (speed={speed_value})")

    def _get_active_group_from_db(self) -> str:
        """Get the active group from the database."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups WHERE is_active = 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
        except sqlite3.Error as e:
            print(f"Error reading active group from database: {e}")
        return ""

    def _get_all_groups_from_db(self) -> list:
        """Get all groups from the database."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Error reading groups from database: {e}")
        return []

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

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
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """

    def _show_info(self, message: str) -> None:
        """Display an info message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat TX")
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate_input(self, validate_callsign: bool = True) -> Optional[tuple]:
        """
        Validate form input.

        Returns (callsign, message) tuple if valid, None otherwise.
        """
        # Check rig is selected
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == "":
            self._show_error("Please select a Rig")
            self.rig_combo.setFocus()
            return None

        # Check group is selected
        group_name = self.group_combo.currentText()
        if not group_name or group_name == "":
            self._show_error("Please select a Group")
            self.group_combo.setFocus()
            return None

        # Get and clean message
        message_raw = self.lineEdit_2.text()
        message = re.sub(r"[^ -~]+", " ", message_raw)

        # Validate message length
        if len(message) < MIN_MESSAGE_LENGTH:
            self._show_error("Message too short")
            return None

        # Validate callsign if required
        if validate_callsign:
            call = self.lineEdit_3.text().upper()

            if len(call) < MIN_CALLSIGN_LENGTH:
                self._show_error("Callsign too short (minimum 4 characters)")
                return None

            if len(call) > MAX_CALLSIGN_LENGTH:
                self._show_error("Callsign too long (maximum 8 characters)")
                return None

            if not CALLSIGN_PATTERN.match(call):
                self._show_error("Does not meet callsign structure!")
                return None
        else:
            call = self.callsign

        return (call, message)

    def _build_message(self, message: str) -> str:
        """Build the message string for transmission."""
        group = "@" + self.group_combo.currentText()
        return f"{group} MSG ,{self.msg_id},{message},{{^%}}"

    def _submit_to_backbone_async(self, frequency: int, callsign: str, message_data: str, now: str) -> None:
        """Start background thread to submit message to backbone server.

        Args:
            frequency: Frequency in Hz
            callsign: Sender callsign
            message_data: The full message string to send
            now: UTC datetime string
        """
        def submit_thread():
            """Background thread that performs the HTTP POST."""
            try:
                # Format data string: datetime\tfreq_hz\t0\t30\tmessage
                data_string = f"{now}\t{frequency}\t0\t30\t{message_data}"

                # Build POST data
                post_data = urllib.parse.urlencode({
                    'cs': callsign,
                    'data': data_string
                }).encode('utf-8')

                # Create and send request with 10-second timeout
                req = urllib.request.Request(_DATAFEED, data=post_data, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = response.read().decode('utf-8').strip()

                # Check server response: "1" = success, other = failure (only log in debug mode)
                if _DEBUG_MODE:
                    if result == "1":
                        print(f"[Backbone] Message submitted successfully (response: {result})")
                    else:
                        print(f"[Backbone] Message submission failed - server returned: {result}")

            except Exception as e:
                if _DEBUG_MODE:
                    print(f"[Backbone] Error submitting message: {e}")

        # Start background thread
        thread = threading.Thread(target=submit_thread, daemon=True)
        thread.start()

    def _save_to_database(self, callsign: str, message: str, frequency: int = 0) -> None:
        """Save message to database.

        Args:
            callsign: The callsign of the sender.
            message: The message content.
            frequency: The frequency in Hz at the time of transmission.
        """
        now = QDateTime.currentDateTime()
        datetime_str = now.toUTC().toString("yyyy-MM-dd HH:mm:ss")
        date_only = now.toUTC().toString("yyyy-MM-dd")

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO messages "
                "(datetime, date, freq, db, source, msg_id, from_callsign, target, message) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime_str, date_only, frequency, 30, 3 if self.rig_combo.currentText() == INTERNET_RIG else 1, self.msg_id, callsign, "@" + self.group_combo.currentText(), message)
            )
            conn.commit()
            freq_mhz = frequency / 1000000.0 if frequency else 0
            print(f"{datetime_str}, @{self.group_combo.currentText()}, {self.msg_id}, {callsign}, {message}, {freq_mhz:.6f} MHz")
        finally:
            conn.close()

        # Submit to backbone server if transmitted (has frequency)
        if frequency > 0:
            if self.delivery_combo.currentText() != "Limited Reach":
                group = "@" + self.group_combo.currentText()
                # Format: CALLSIGN: @GROUP MSG ,ID,MESSAGE,{^%}
                message_data = f"{callsign}: {group} MSG ,{self.msg_id},{message},{{^%}}"
                self._submit_to_backbone_async(frequency, callsign, message_data, datetime_str)

    def _save_only(self) -> None:
        """Validate and save message to database without transmitting."""
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return

        callsign, message = result

        # Build message for display
        tx_message = self._build_message(message)
        self._show_info(f"CommStat has saved:\n{tx_message}")

        self._save_to_database(callsign, message)

        # Trigger refresh callback if provided
        if self.refresh_callback:
            self.refresh_callback()

        self.MainWindow.close()

    def _transmit(self) -> None:
        """Validate, check for selected call, get frequency, transmit, and save message."""
        result = self._validate_input(validate_callsign=False)
        if result is None:
            return

        rig_name = self.rig_combo.currentText()
        callsign, message = result

        if rig_name == INTERNET_RIG:
            callsign = self._get_internet_callsign()
            if not callsign:
                self._show_error(
                    "No callsign configured.\n\nPlease set your callsign in Settings → User Settings."
                )
                return
            self.callsign = callsign
            self._pending_callsign = callsign
            self._pending_message = self._build_message(message)
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            message_data = f"{callsign}: @{self.group_combo.currentText()} MSG ,{self.msg_id},{message},{{^%}}"
            self._save_to_database(callsign, message, frequency=0)
            self._submit_to_backbone_async(0, callsign, message_data, now)
            if self.refresh_callback:
                self.refresh_callback()
            self.MainWindow.close()
            return

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

        # Store pending values for transmission after frequency is received
        self._pending_message = self._build_message(message)
        self._pending_callsign = callsign

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
            QtWidgets.QMessageBox.critical(
                self.MainWindow, "ERROR",
                f"JS8Call has {selected_call} selected.\n\n"
                "Go to JS8Call and click the \"Deselect\" button."
            )
            return

        # No call selected - proceed with getting frequency and transmitting
        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError:
                pass
            client.frequency_received.connect(self._on_frequency_for_transmit)
            client.get_frequency()

    def _on_frequency_for_transmit(self, rig_name: str, frequency: int) -> None:
        """Handle frequency received - now transmit and save."""
        # Only process if this is the currently selected rig
        if self.rig_combo.currentText() != rig_name:
            return

        # Disconnect signal to prevent multiple calls
        client = self.tcp_pool.get_client(rig_name)
        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError:
                pass

        try:
            # Transmit via TCP
            client.send_tx_message(self._pending_message)

            # Save to database with frequency
            # Extract message content from the built message
            message = self.lineEdit_2.text()
            message = re.sub(r"[^ -~]+", " ", message)
            self._save_to_database(self.callsign, message, frequency)

            # Trigger refresh callback if provided
            if self.refresh_callback:
                self.refresh_callback()

            self.MainWindow.close()
        except Exception as e:
            self._show_error(f"Failed to transmit message: {e}")

    def _generate_msg_id(self) -> None:
        """Generate a time-based message ID from current UTC time."""
        from id_utils import generate_time_based_id
        self.msg_id = generate_time_based_id()


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

    FormMessage = QtWidgets.QWidget()
    ui = Ui_FormMessage(tcp_pool, connector_manager)
    ui.setupUi(FormMessage)
    FormMessage.show()
    sys.exit(app.exec_())
