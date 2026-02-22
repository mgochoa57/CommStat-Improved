# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Group Alert Dialog for CommStat
Allows creating and transmitting group alerts via JS8Call.
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
MAX_TITLE_LENGTH = 20
MAX_MESSAGE_LENGTH = 80
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

# Color options: (name, value, background_color, text_color)
COLOR_OPTIONS = [
    ("Yellow", 1, "#e8e800", "#000000"),
    ("Orange", 2, "#ff8c00", "#ffffff"),
    ("Red", 3, "#dc3545", "#ffffff"),
    ("Black", 4, "#000000", "#ffffff"),
]


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


class Ui_FormAlert:
    """Alert form for creating and transmitting group alerts."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        on_alert_saved: callable = None
    ):
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager
        self.on_alert_saved = on_alert_saved
        self.MainWindow: Optional[QtWidgets.QWidget] = None
        self.callsign: str = ""
        self.grid: str = ""
        self.selected_group: str = ""
        self.alert_id: str = ""
        self._pending_message: str = ""
        self._pending_callsign: str = ""

    def setupUi(self, FormAlert: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormAlert
        FormAlert.setObjectName("FormAlert")
        FormAlert.resize(900, 404)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Roboto")
        font.setPointSize(12)
        FormAlert.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormAlert.setWindowIcon(icon)

        # Title
        self.title_label = QtWidgets.QLabel(FormAlert)
        self.title_label.setGeometry(QtCore.QRect(58, 10, 400, 30))
        title_font = QtGui.QFont("Roboto", 16, QtGui.QFont.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setText("CommStat Group Alert")
        self.title_label.setStyleSheet("color: #333;")
        self.title_label.setObjectName("title_label")

        # Settings row label (left column, vertically centered in row)
        self.settings_label = QtWidgets.QLabel(FormAlert)
        self.settings_label.setGeometry(QtCore.QRect(58, 72, 120, 20))
        self.settings_label.setFont(font)
        self.settings_label.setText("Settings:")
        self.settings_label.setObjectName("settings_label")

        # Rig dropdown (label above control, aligned with other controls at x=190)
        self.rig_label = QtWidgets.QLabel(FormAlert)
        self.rig_label.setGeometry(QtCore.QRect(190, 46, 150, 20))
        self.rig_label.setFont(font)
        self.rig_label.setText("Rig:")
        self.rig_label.setObjectName("rig_label")

        self.rig_combo = QtWidgets.QComboBox(FormAlert)
        self.rig_combo.setGeometry(QtCore.QRect(190, 72, 150, 26))
        self.rig_combo.setFont(font)
        self.rig_combo.setObjectName("rig_combo")

        # Mode dropdown (label above control)
        self.mode_label = QtWidgets.QLabel(FormAlert)
        self.mode_label.setGeometry(QtCore.QRect(350, 46, 100, 20))
        self.mode_label.setFont(font)
        self.mode_label.setText("Mode:")
        self.mode_label.setObjectName("mode_label")

        self.mode_combo = QtWidgets.QComboBox(FormAlert)
        self.mode_combo.setGeometry(QtCore.QRect(350, 72, 100, 26))
        self.mode_combo.setFont(font)
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.setObjectName("mode_combo")

        # Frequency field (label above control)
        self.freq_label = QtWidgets.QLabel(FormAlert)
        self.freq_label.setGeometry(QtCore.QRect(460, 46, 80, 20))
        self.freq_label.setFont(font)
        self.freq_label.setText("Freq:")
        self.freq_label.setObjectName("freq_label")

        self.freq_field = QtWidgets.QLineEdit(FormAlert)
        self.freq_field.setGeometry(QtCore.QRect(460, 72, 80, 26))
        self.freq_field.setFont(font)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet("background-color: #f0f0f0;")
        self.freq_field.setObjectName("freq_field")

        # Delivery dropdown (label above control)
        self.delivery_label = QtWidgets.QLabel(FormAlert)
        self.delivery_label.setGeometry(QtCore.QRect(550, 46, 150, 20))
        self.delivery_label.setFont(font)
        self.delivery_label.setText("Delivery:")
        self.delivery_label.setObjectName("delivery_label")

        self.delivery_combo = QtWidgets.QComboBox(FormAlert)
        self.delivery_combo.setGeometry(QtCore.QRect(550, 72, 150, 26))
        self.delivery_combo.setFont(font)
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        self.delivery_combo.setObjectName("delivery_combo")

        # Group dropdown
        self.group_label = QtWidgets.QLabel(FormAlert)
        self.group_label.setGeometry(QtCore.QRect(58, 107, 120, 20))
        self.group_label.setFont(font)
        self.group_label.setText("Group:")
        self.group_label.setObjectName("group_label")

        self.group_combo = QtWidgets.QComboBox(FormAlert)
        self.group_combo.setGeometry(QtCore.QRect(190, 107, 150, 26))
        self.group_combo.setFont(font)
        self.group_combo.setObjectName("group_combo")

        # Callsign input (read-only, from JS8Call)
        self.callsign_label = QtWidgets.QLabel(FormAlert)
        self.callsign_label.setGeometry(QtCore.QRect(58, 142, 120, 20))
        self.callsign_label.setFont(font)
        self.callsign_label.setText("From Callsign:")
        self.callsign_label.setObjectName("callsign_label")

        self.callsign_field = QtWidgets.QLineEdit(FormAlert)
        self.callsign_field.setGeometry(QtCore.QRect(190, 142, 100, 26))
        self.callsign_field.setFont(font)
        self.callsign_field.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.callsign_field.setReadOnly(True)
        self.callsign_field.setStyleSheet("background-color: #e9ecef;")
        self.callsign_field.setObjectName("callsign_field")

        # Color dropdown
        self.color_label = QtWidgets.QLabel(FormAlert)
        self.color_label.setGeometry(QtCore.QRect(58, 177, 120, 20))
        self.color_label.setFont(font)
        self.color_label.setText("Color:")
        self.color_label.setObjectName("color_label")

        self.color_combo = QtWidgets.QComboBox(FormAlert)
        self.color_combo.setGeometry(QtCore.QRect(190, 177, 100, 26))
        self.color_combo.setFont(font)
        self.color_combo.setObjectName("color_combo")

        # Populate color dropdown
        for name, value, bg_color, text_color in COLOR_OPTIONS:
            self.color_combo.addItem(name, value)

        # Set default color to 1 (Red/Emergency) and hide color selection
        self.color_combo.setCurrentIndex(0)  # Index 0 = color value 1
        self.color_label.hide()
        self.color_combo.hide()

        # Color sample boxes (80x28 each, with "Sample" text)
        sample_start_x = 310
        sample_y = 174
        sample_width = 80
        sample_height = 28
        sample_spacing = 10

        self.color_samples = []
        for i, (name, value, bg_color, text_color) in enumerate(COLOR_OPTIONS):
            sample = QtWidgets.QLabel(FormAlert)
            sample.setGeometry(QtCore.QRect(
                sample_start_x + i * (sample_width + sample_spacing),
                sample_y,
                sample_width,
                sample_height
            ))
            sample.setText("Sample")
            sample.setAlignment(QtCore.Qt.AlignCenter)
            sample.setStyleSheet(f"""
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid #333;
                font-size: 12px;
                font-weight: bold;
            """)
            sample.setObjectName(f"color_sample_{name.lower()}")
            self.color_samples.append(sample)
            sample.hide()  # Hide color samples

        # Title input
        self.title_input_label = QtWidgets.QLabel(FormAlert)
        self.title_input_label.setGeometry(QtCore.QRect(58, 212, 120, 20))
        self.title_input_label.setFont(font)
        self.title_input_label.setText("Title:")
        self.title_input_label.setObjectName("title_input_label")

        self.title_field = QtWidgets.QLineEdit(FormAlert)
        self.title_field.setGeometry(QtCore.QRect(190, 212, 200, 26))
        self.title_field.setFont(font)
        self.title_field.setMaxLength(MAX_TITLE_LENGTH)
        self.title_field.setObjectName("title_field")

        # Message input
        self.message_label = QtWidgets.QLabel(FormAlert)
        self.message_label.setGeometry(QtCore.QRect(58, 247, 120, 20))
        self.message_label.setFont(font)
        self.message_label.setText("Message:")
        self.message_label.setObjectName("message_label")

        self.message_field = QtWidgets.QLineEdit(FormAlert)
        self.message_field.setGeometry(QtCore.QRect(190, 247, 530, 26))
        self.message_field.setFont(font)
        self.message_field.setMaxLength(MAX_MESSAGE_LENGTH)
        self.message_field.setObjectName("message_field")

        # Character limit note
        self.note_label = QtWidgets.QLabel(FormAlert)
        self.note_label.setGeometry(QtCore.QRect(190, 277, 530, 20))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(10)
        note_font.setBold(True)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #AA0000;")
        self.note_label.setText("Title: 20 chars max. Message: 80 chars max.")
        self.note_label.setObjectName("note_label")

        # Delivery legend
        self.delivery_legend_label = QtWidgets.QLabel(FormAlert)
        self.delivery_legend_label.setGeometry(QtCore.QRect(190, 299, 530, 20))
        self.delivery_legend_label.setFont(note_font)
        self.delivery_legend_label.setStyleSheet("color: #AA0000;")
        self.delivery_legend_label.setText("Delivery: Maximum Reach = RF + Internet | Limited Reach = RF Only")
        self.delivery_legend_label.setObjectName("delivery_legend_label")

        # Buttons
        self.save_button = QtWidgets.QPushButton(FormAlert)
        self.save_button.setGeometry(QtCore.QRect(410, 334, 100, 32))
        self.save_button.setText("Save Only")
        self.save_button.setObjectName("save_button")
        self.save_button.clicked.connect(self._save_only)
        self.save_button.setStyleSheet(self._button_style("#17a2b8"))

        self.transmit_button = QtWidgets.QPushButton(FormAlert)
        self.transmit_button.setGeometry(QtCore.QRect(520, 334, 100, 32))
        self.transmit_button.setText("Transmit")
        self.transmit_button.setObjectName("transmit_button")
        self.transmit_button.clicked.connect(self._transmit)
        self.transmit_button.setStyleSheet(self._button_style("#007bff"))

        self.cancel_button = QtWidgets.QPushButton(FormAlert)
        self.cancel_button.setGeometry(QtCore.QRect(630, 334, 100, 32))
        self.cancel_button.setText("Cancel")
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.clicked.connect(self.MainWindow.close)
        self.cancel_button.setStyleSheet(self._button_style("#dc3545"))

        QtCore.QMetaObject.connectSlotsByName(FormAlert)

        # Generate alert ID
        self._generate_alert_id()

        # Load config and initialize
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
            self.callsign_field.setText("")
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
            self.callsign_field.setText(callsign)
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

            # Connect signal for this client (disconnect any existing first)
            try:
                client.callsign_received.disconnect(self._on_callsign_received)
            except TypeError:
                pass

            client.callsign_received.connect(self._on_callsign_received)

            # Request callsign from JS8Call
            client.get_callsign()
        else:
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        """Handle callsign received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            self.callsign_field.setText(callsign)

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
            print(f"[Alert] Set mode to {self.mode_combo.currentText()} (speed={speed_value})")

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

        Returns (callsign, color, title, message) tuple if valid, None otherwise.
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

        # Get color value
        color_value = self.color_combo.currentData()

        # Get and clean title
        title_raw = self.title_field.text()
        title = re.sub(r"[^ -~]+", " ", title_raw).strip()

        # Validate title
        if len(title) < 1:
            self._show_error("Title is required")
            self.title_field.setFocus()
            return None

        # Get and clean message
        message_raw = self.message_field.text()
        message = re.sub(r"[^ -~]+", " ", message_raw).strip()

        # Validate message length
        if len(message) < 1:
            self._show_error("Message is required")
            self.message_field.setFocus()
            return None

        # Validate callsign if required
        if validate_callsign:
            call = self.callsign_field.text().upper()

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

        return (call, color_value, title, message)

    def _generate_alert_id(self) -> None:
        """Generate a time-based alert ID from current UTC time."""
        from id_utils import generate_time_based_id
        self.alert_id = generate_time_based_id()

    def _build_message(self, callsign: str, color: int, title: str, message: str) -> str:
        """Build the message string for transmission."""
        group = "@" + self.group_combo.currentText()
        return f"{callsign}: {group} ,{self.alert_id},{color},{title},{message},{{%%}}"

    def _submit_to_backbone_async(self, frequency: int, callsign: str, alert_data: str, now: str) -> None:
        """Start background thread to submit alert to backbone server.

        Args:
            frequency: Frequency in Hz
            callsign: Sender callsign
            alert_data: The full alert string to send
            now: UTC datetime string
        """
        def submit_thread():
            """Background thread that performs the HTTP POST."""
            try:
                # Format data string: datetime\tfreq_hz\t0\t30\talert_message
                data_string = f"{now}\t{frequency}\t0\t30\t{alert_data}"

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
                        print(f"[Backbone] Alert submitted successfully (response: {result})")
                    else:
                        print(f"[Backbone] Alert submission failed - server returned: {result}")

            except Exception as e:
                if _DEBUG_MODE:
                    print(f"[Backbone] Error submitting alert: {e}")

        # Start background thread
        thread = threading.Thread(target=submit_thread, daemon=True)
        thread.start()

    def _save_to_database(self, callsign: str, color: int, title: str, message: str, frequency: int = 0, db: int = 30) -> None:
        """Save alert to database.

        Args:
            callsign: The callsign of the sender.
            color: The color code (1-4).
            title: The alert title.
            message: The alert message content.
            frequency: The frequency in Hz at the time of transmission.
            db: Signal strength in decibels (default 30 for manual entries).
        """
        now = QDateTime.currentDateTime()
        datetime_str = now.toUTC().toString("yyyy-MM-dd HH:mm:ss")
        date_only = now.toUTC().toString("yyyy-MM-dd")
        group = "@" + self.group_combo.currentText()

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO alerts "
                "(datetime, date, freq, db, source, alert_id, from_callsign, target, color, title, message) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime_str, date_only, frequency, db, 3 if self.rig_combo.currentText() == INTERNET_RIG else 1, self.alert_id, callsign, group, color, title, message)
            )
            conn.commit()
            freq_mhz = frequency / 1000000.0 if frequency else 0
            print(f"[Alert] Saved: {datetime_str}, {group}, {self.alert_id}, {callsign}, color={color}, title={title}, {freq_mhz:.6f} MHz")
        finally:
            conn.close()

        # Submit to backbone server if transmitted (has frequency)
        if frequency > 0:
            if self.delivery_combo.currentText() != "Limited Reach":
                # Format: CALLSIGN: @GROUP ,ALERT_ID,COLOR,TITLE,MESSAGE,{%%}
                alert_data = f"{callsign}: {group} ,{self.alert_id},{color},{title},{message},{{%%}}"
                self._submit_to_backbone_async(frequency, callsign, alert_data, datetime_str)

    def _save_only(self) -> None:
        """Validate and save alert to database without transmitting."""
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return

        callsign, color, title, message = result

        self._save_to_database(callsign, color, title, message)
        self.MainWindow.close()
        if self.on_alert_saved:
            self.on_alert_saved()

    def _transmit(self) -> None:
        """Validate, check for selected call, get frequency, transmit, and save alert."""
        result = self._validate_input(validate_callsign=False)
        if result is None:
            return

        rig_name = self.rig_combo.currentText()
        callsign, color, title, message = result

        if rig_name == INTERNET_RIG:
            callsign = self._get_internet_callsign()
            if not callsign:
                self._show_error(
                    "No callsign configured.\n\nPlease set your callsign in Settings → User Settings."
                )
                return
            self.callsign = callsign
            self._pending_callsign = callsign
            self._pending_message = self._build_message(callsign, color, title, message)
            self._save_to_database(callsign, color, title, message, frequency=0)
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            self._submit_to_backbone_async(0, callsign, self._pending_message, now)
            self.MainWindow.close()
            if self.on_alert_saved:
                self.on_alert_saved()
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
        self._pending_message = self._build_message(callsign, color, title, message)
        self._pending_callsign = callsign
        self._pending_color = color
        self._pending_title = title
        self._pending_alert_message = message

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
            self._save_to_database(
                self._pending_callsign,
                self._pending_color,
                self._pending_title,
                self._pending_alert_message,
                frequency
            )

            self.MainWindow.close()
            if self.on_alert_saved:
                self.on_alert_saved()
        except Exception as e:
            self._show_error(f"Failed to transmit alert: {e}")


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

    FormAlert = QtWidgets.QWidget()
    ui = Ui_FormAlert(tcp_pool, connector_manager)
    ui.setupUi(FormAlert)
    FormAlert.show()
    sys.exit(app.exec_())
