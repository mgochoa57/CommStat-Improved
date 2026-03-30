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
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox
from theme_manager import theme

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
        """Initialize the UI components using Layouts."""
        self.MainWindow = FormAlert
        FormAlert.setObjectName("FormAlert")
        FormAlert.resize(900, 480)

        # Set font
        font = QtGui.QFont()
        font.setFamily(theme.font_family)
        font.setPointSize(theme.font_size)
        FormAlert.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        if os.path.exists("radiation-32.png"):
            icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            FormAlert.setWindowIcon(icon)

        # Apply theme stylesheet
        FormAlert.setStyleSheet(f"""
            QWidget {{ 
                background-color: {theme.color('base')}; 
                color: {theme.color('text')};
            }}
            QLabel {{ 
                color: {theme.color('text')}; 
            }}
            QLineEdit {{ 
                background-color: {theme.color('base')}; 
                color: {theme.color('text')}; 
                border: 1px solid {theme.color('mid')}; 
                border-radius: 4px; 
                padding: 2px 4px; 
            }}
            {theme.combo_data_style()}
            {theme.combo_list_data_style()}
        """)

        # Main Layout
        main_layout = QtWidgets.QVBoxLayout(FormAlert)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(30, 20, 30, 20)

        # Title
        self.title_label = QtWidgets.QLabel("CommStat Group Alert")
        title_font = QtGui.QFont(theme.font_family, 16, QtGui.QFont.Bold)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(theme.dialog_title_style_compact())
        main_layout.addWidget(self.title_label)

        # Settings Row (Rig, Mode, Freq, Delivery)
        settings_container = QtWidgets.QHBoxLayout()
        settings_container.setSpacing(15)

        field_style = theme.field_title_style()

        # Rig
        rig_col = QtWidgets.QVBoxLayout()
        self.rig_label = QtWidgets.QLabel("Rig:")
        self.rig_label.setStyleSheet(field_style)
        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFont(font)
        self.rig_combo.setMinimumWidth(180)
        self.rig_combo.setMinimumHeight(28)
        rig_col.addWidget(self.rig_label)
        rig_col.addWidget(self.rig_combo)
        settings_container.addLayout(rig_col)

        # Mode
        mode_col = QtWidgets.QVBoxLayout()
        self.mode_label = QtWidgets.QLabel("Mode:")
        self.mode_label.setStyleSheet(field_style)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setFont(font)
        self.mode_combo.setMinimumHeight(28)
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        mode_col.addWidget(self.mode_label)
        mode_col.addWidget(self.mode_combo)
        settings_container.addLayout(mode_col)

        # Freq
        freq_col = QtWidgets.QVBoxLayout()
        self.freq_label = QtWidgets.QLabel("Freq:")
        self.freq_label.setStyleSheet(field_style)
        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setFont(font)
        self.freq_field.setReadOnly(True)
        self.freq_field.setMinimumHeight(28)
        self.freq_field.setMaximumWidth(100)
        self.freq_field.setStyleSheet(theme.input_readonly_style())
        freq_col.addWidget(self.freq_label)
        freq_col.addWidget(self.freq_field)
        settings_container.addLayout(freq_col)

        # Delivery
        delivery_col = QtWidgets.QVBoxLayout()
        self.delivery_label = QtWidgets.QLabel("Delivery:")
        self.delivery_label.setStyleSheet(field_style)
        self.delivery_combo = QtWidgets.QComboBox()
        self.delivery_combo.setFont(font)
        self.delivery_combo.setMinimumHeight(28)
        self.delivery_combo.setMinimumWidth(150)
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        delivery_col.addWidget(self.delivery_label)
        delivery_col.addWidget(self.delivery_combo)
        settings_container.addLayout(delivery_col)

        settings_container.addStretch()
        main_layout.addLayout(settings_container)

        # Group and From Callsign row
        form_row = QtWidgets.QHBoxLayout()
        
        # Group
        group_layout = QtWidgets.QVBoxLayout()
        self.group_label = QtWidgets.QLabel("Group:")
        self.group_label.setStyleSheet(field_style)
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setFont(font)
        self.group_combo.setMinimumWidth(180)
        self.group_combo.setMinimumHeight(28)
        group_layout.addWidget(self.group_label)
        group_layout.addWidget(self.group_combo)
        form_row.addLayout(group_layout)

        # From Callsign
        callsign_layout = QtWidgets.QVBoxLayout()
        self.callsign_label = QtWidgets.QLabel("From Callsign:")
        self.callsign_label.setStyleSheet(field_style)
        self.callsign_field = QtWidgets.QLineEdit()
        self.callsign_field.setFont(font)
        self.callsign_field.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.callsign_field.setReadOnly(True)
        self.callsign_field.setMinimumHeight(28)
        self.callsign_field.setMaximumWidth(120)
        self.callsign_field.setStyleSheet(theme.input_readonly_style())
        callsign_layout.addWidget(self.callsign_label)
        callsign_layout.addWidget(self.callsign_field)
        form_row.addLayout(callsign_layout)
        
        form_row.addStretch()
        main_layout.addLayout(form_row)

        # Color and Samples (Initially hidden but layout maintained)
        color_layout = QtWidgets.QHBoxLayout()
        self.color_label = QtWidgets.QLabel("Color:")
        self.color_label.setStyleSheet(field_style)
        self.color_combo = QtWidgets.QComboBox()
        self.color_combo.setFont(font)
        self.color_combo.setMinimumHeight(28)
        self.color_combo.setFixedWidth(100)
        for name, value, bg_color, text_color in COLOR_OPTIONS:
            self.color_combo.addItem(name, value)
        self.color_combo.setCurrentIndex(0)
        
        color_layout.addWidget(self.color_label)
        color_layout.addWidget(self.color_combo)
        
        self.color_samples = []
        for name, value, bg_color, text_color in COLOR_OPTIONS:
            sample = QtWidgets.QLabel("Sample")
            sample.setFixedSize(80, 28)
            sample.setAlignment(Qt.AlignCenter)
            sample.setStyleSheet(f"""
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {theme.color('mid')};
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
            """)
            color_layout.addWidget(sample)
            self.color_samples.append(sample)
            sample.hide()

        self.color_label.hide()
        self.color_combo.hide()
        color_layout.addStretch()
        main_layout.addLayout(color_layout)

        # Title and Message inputs
        input_layout = QtWidgets.QVBoxLayout()
        input_layout.setSpacing(10)

        # Title Input
        title_input_col = QtWidgets.QVBoxLayout()
        self.title_input_label = QtWidgets.QLabel("Title:")
        self.title_input_label.setStyleSheet(field_style)
        self.title_field = QtWidgets.QLineEdit()
        self.title_field.setFont(font)
        self.title_field.setMaxLength(MAX_TITLE_LENGTH)
        self.title_field.setMinimumHeight(28)
        title_input_col.addWidget(self.title_input_label)
        title_input_col.addWidget(self.title_field)
        input_layout.addLayout(title_input_col)

        # Message Input
        message_input_col = QtWidgets.QVBoxLayout()
        self.message_label = QtWidgets.QLabel("Message:")
        self.message_label.setStyleSheet(field_style)
        self.message_field = QtWidgets.QLineEdit()
        self.message_field.setFont(font)
        self.message_field.setMaxLength(MAX_MESSAGE_LENGTH)
        self.message_field.setMinimumHeight(32)
        message_input_col.addWidget(self.message_label)
        message_input_col.addWidget(self.message_field)
        input_layout.addLayout(message_input_col)
        
        main_layout.addLayout(input_layout)

        # Legend/Notes
        legend_layout = QtWidgets.QVBoxLayout()
        self.note_label = QtWidgets.QLabel("Title: 20 chars max. Message: 80 chars max.")
        note_font = QtGui.QFont(theme.font_family, 10, QtGui.QFont.Bold)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #AA0000;")
        legend_layout.addWidget(self.note_label)

        self.delivery_legend_label = QtWidgets.QLabel("Delivery: Maximum Reach = RF + Internet | Limited Reach = RF Only")
        self.delivery_legend_label.setFont(note_font)
        self.delivery_legend_label.setStyleSheet("color: #AA0000;")
        legend_layout.addWidget(self.delivery_legend_label)
        main_layout.addLayout(legend_layout)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        self.save_button = QtWidgets.QPushButton("Save Only")
        self.save_button.setMinimumSize(100, 32)
        self.save_button.setStyleSheet(theme.button_style("#17a2b8"))
        self.save_button.clicked.connect(self._save_only)
        button_layout.addWidget(self.save_button)

        self.transmit_button = QtWidgets.QPushButton("Transmit")
        self.transmit_button.setMinimumSize(100, 32)
        self.transmit_button.setStyleSheet(theme.button_style("#007bff"))
        self.transmit_button.clicked.connect(self._transmit)
        button_layout.addWidget(self.transmit_button)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setMinimumSize(100, 32)
        self.cancel_button.setStyleSheet(theme.button_style("#dc3545"))
        self.cancel_button.clicked.connect(self.MainWindow.close)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

        # Connect signals
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        # Initialize Data
        self._generate_alert_id()
        self._load_config()
        self._load_rigs()

        self.MainWindow.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

    def _load_config(self) -> None:
        """Load configuration from database."""
        self.selected_group = self._get_active_group_from_db()
        all_groups = self._get_all_groups_from_db()
        self.group_combo.clear()
        if len(all_groups) == 1:
            self.group_combo.addItem(all_groups[0])
        else:
            self.group_combo.addItem("")
            for group in all_groups:
                self.group_combo.addItem(group)

    def _load_rigs(self) -> None:
        """Load enabled connectors into the rig dropdown, plus Internet option."""
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        enabled_connectors = self.connector_manager.get_all_connectors(enabled_only=True) if self.connector_manager else []
        connected_rigs = self.tcp_pool.get_connected_rig_names() if self.tcp_pool else []
        enabled_count = len(enabled_connectors)

        if enabled_count == 0:
            self.rig_combo.addItem(INTERNET_RIG)
        elif enabled_count == 1:
            rig_name = enabled_connectors[0]['rig_name']
            label = rig_name if rig_name in connected_rigs else f"{rig_name} (disconnected)"
            self.rig_combo.addItem(label)
            self.rig_combo.addItem(INTERNET_RIG)
        else:
            self.rig_combo.addItem("")
            for c in enabled_connectors:
                rig_name = c['rig_name']
                label = rig_name if rig_name in connected_rigs else f"{rig_name} (disconnected)"
                self.rig_combo.addItem(label)
            self.rig_combo.addItem(INTERNET_RIG)

        self.rig_combo.blockSignals(False)

        current_text = self.rig_combo.currentText()
        if current_text and "(disconnected)" not in current_text:
            self._on_rig_changed(current_text)

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change."""
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

        if hasattr(self, 'mode_combo'):
            self.mode_combo.setEnabled(True)

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            if hasattr(self, 'mode_combo'):
                speed_name = (client.speed_name or "").upper()
                mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3}
                idx = mode_map.get(speed_name, 1)
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(idx)
                self.mode_combo.blockSignals(False)

            if hasattr(self, 'freq_field'):
                frequency = client.frequency
                if frequency:
                    self.freq_field.setText(f"{frequency:.3f}")
                else:
                    self.freq_field.setText("")

            try:
                client.callsign_received.disconnect(self._on_callsign_received)
            except TypeError: pass

            client.callsign_received.connect(self._on_callsign_received)
            client.get_callsign()
        else:
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            self.callsign_field.setText(callsign)

    def _get_internet_callsign(self) -> str:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT callsign FROM controls WHERE id = 1")
                row = cursor.fetchone()
                return (row[0] or "").strip().upper() if row else ""
        except sqlite3.Error:
            return ""

    def _on_mode_changed(self, index: int) -> None:
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == INTERNET_RIG or "(disconnected)" in rig_name or not self.tcp_pool:
            return
        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})

    def _get_active_group_from_db(self) -> str:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups WHERE is_active = 1")
                result = cursor.fetchone()
                return result[0] if result else ""
        except sqlite3.Error:
            return ""

    def _get_all_groups_from_db(self) -> list:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error:
            return []

    def _show_error(self, message: str) -> None:
        msg = QMessageBox()
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _button_style(self, color: str) -> str:
        return theme.button_style(color)

    def _show_info(self, message: str) -> None:
        msg = QMessageBox()
        msg.setWindowTitle("CommStat TX")
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate_input(self, validate_callsign: bool = True) -> Optional[tuple]:
        rig_name = self.rig_combo.currentText()
        if not rig_name:
            self._show_error("Please select a Rig")
            return None
        group_name = self.group_combo.currentText()
        if not group_name:
            self._show_error("Please select a Group")
            return None
        color_value = self.color_combo.currentData()
        title_raw = self.title_field.text()
        title = re.sub(r"[^ -~]+", " ", title_raw).strip()
        if len(title) < 1:
            self._show_error("Title is required")
            return None
        message_raw = self.message_field.text()
        message = re.sub(r"[^ -~]+", " ", message_raw).strip()
        if len(message) < 1:
            self._show_error("Message is required")
            return None
        if validate_callsign:
            call = self.callsign_field.text().upper()
            if len(call) < MIN_CALLSIGN_LENGTH:
                self._show_error("Callsign too short")
                return None
            if not CALLSIGN_PATTERN.match(call):
                self._show_error("Does not meet callsign structure!")
                return None
        else:
            call = self.callsign
        return (call, color_value, title, message)

    def _generate_alert_id(self) -> None:
        from id_utils import generate_time_based_id
        self.alert_id = generate_time_based_id()

    def _build_message(self, callsign: str, color: int, title: str, message: str) -> str:
        group = "@" + self.group_combo.currentText()
        marker = "{%%3}" if self.rig_combo.currentText() == INTERNET_RIG else "{%%}"
        return f"{callsign}: {group} ,{self.alert_id},{color},{title},{message},{marker}"

    def _submit_to_backbone_async(self, frequency: int, callsign: str, alert_data: str, now: str) -> None:
        def submit_thread():
            try:
                data_string = f"{now}\t{frequency}\t0\t30\t{alert_data}"
                post_data = urllib.parse.urlencode({'cs': callsign, 'data': data_string}).encode('utf-8')
                req = urllib.request.Request(_DATAFEED, data=post_data, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = response.read().decode('utf-8').strip()
                if _DEBUG_MODE: print(f"[Backbone] Result: {result}")
            except Exception as e:
                if _DEBUG_MODE: print(f"[Backbone] Error: {e}")
        threading.Thread(target=submit_thread, daemon=True).start()

    def _save_to_database(self, callsign: str, color: int, title: str, message: str, frequency: int = 0, db: int = 30) -> None:
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
        finally:
            conn.close()

        if frequency > 0:
            if self.delivery_combo.currentText() != "Limited Reach":
                alert_data = f"{callsign}: {group} ,{self.alert_id},{color},{title},{message},{{%%}}"
                self._submit_to_backbone_async(frequency, callsign, alert_data, datetime_str)

    def _save_only(self) -> None:
        result = self._validate_input(validate_callsign=True)
        if result:
            self._save_to_database(*result)
            self.MainWindow.close()
            if self.on_alert_saved: self.on_alert_saved()

    def _transmit(self) -> None:
        result = self._validate_input(validate_callsign=False)
        if not result: return
        rig_name = self.rig_combo.currentText()
        callsign, color, title, message = result

        if rig_name == INTERNET_RIG:
            callsign = self._get_internet_callsign()
            if not callsign:
                self._show_error("No callsign configured.")
                return
            self.callsign = callsign
            self._pending_message = self._build_message(callsign, color, title, message)
            self._save_to_database(callsign, color, title, message, frequency=0)
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            self._submit_to_backbone_async(0, callsign, self._pending_message, now)
            self.MainWindow.close()
            if self.on_alert_saved: self.on_alert_saved()
            return

        if "(disconnected)" in rig_name:
            self._show_error("Rig disconnected")
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            self._pending_message = self._build_message(callsign, color, title, message)
            self._pending_callsign = callsign
            self._pending_color = color
            self._pending_title = title
            self._pending_alert_message = message
            try:
                client.call_selected_received.disconnect(self._on_call_selected_for_transmit)
            except TypeError: pass
            client.call_selected_received.connect(self._on_call_selected_for_transmit)
            client.get_call_selected()
        else:
            self._show_error("Not connected to rig")

    def _on_call_selected_for_transmit(self, rig_name: str, selected_call: str) -> None:
        if self.rig_combo.currentText() != rig_name: return
        client = self.tcp_pool.get_client(rig_name)
        if client:
            try:
                client.call_selected_received.disconnect(self._on_call_selected_for_transmit)
            except TypeError: pass
        if selected_call:
            QtWidgets.QMessageBox.critical(self.MainWindow, "ERROR", f"JS8Call has {selected_call} selected. Deselect it first.")
            return
        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError: pass
            client.frequency_received.connect(self._on_frequency_for_transmit)
            client.get_frequency()

    def _on_frequency_for_transmit(self, rig_name: str, frequency: int) -> None:
        if self.rig_combo.currentText() != rig_name: return
        client = self.tcp_pool.get_client(rig_name)
        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError: pass
        try:
            client.send_tx_message(self._pending_message)
            self._save_to_database(self._pending_callsign, self._pending_color, self._pending_title, self._pending_alert_message, frequency)
            self.MainWindow.close()
            if self.on_alert_saved: self.on_alert_saved()
        except Exception as e:
            self._show_error(f"Failed to transmit: {e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    from connector_manager import ConnectorManager
    from js8_tcp_client import TCPConnectionPool
    cm = ConnectorManager()
    cm.init_connectors_table()
    tp = TCPConnectionPool(cm)
    tp.connect_all()
    FormAlert = QtWidgets.QWidget()
    ui = Ui_FormAlert(tp, cm)
    ui.setupUi(FormAlert)
    FormAlert.show()
    sys.exit(app.exec_())
