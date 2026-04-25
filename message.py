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

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_DISABLED_BG, COLOR_DISABLED_TEXT,
    COLOR_BTN_CYAN, COLOR_BTN_BLUE, COLOR_ERROR,
)

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

MIN_CALLSIGN_LENGTH = 4
MAX_CALLSIGN_LENGTH = 8
MIN_MESSAGE_LENGTH = 4
MAX_MESSAGE_LENGTH = 67
MAX_MESSAGE_LENGTH_INTERNET = 500
DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"

_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED = _BACKBONE + "/datafeed-808585.php"

INTERNET_RIG = "INTERNET ONLY"

_PROG_BG    = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG    = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG    = DEFAULT_COLORS.get("data_background",    "#F8F6F4")
_COL_CANCEL = "#555555"

CALLSIGN_PATTERN = re.compile(r'[A-Z0-9]{1,3}[0-9][A-Z]{1,3}')


# =============================================================================
# Helpers
# =============================================================================

def make_uppercase(field):
    def to_upper(text):
        if text != text.upper():
            pos = field.cursorPosition()
            field.blockSignals(True)
            field.setText(text.upper())
            field.blockSignals(False)
            field.setCursorPosition(pos)
    field.textChanged.connect(to_upper)


def _lbl_font() -> QtGui.QFont:
    return QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)


def _mono_font() -> QtGui.QFont:
    return QtGui.QFont("Kode Mono")


def _btn(label: str, color: str, min_w: int = 90) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(label)
    b.setMinimumWidth(min_w)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; border:none;"
        f" padding:6px 14px; border-radius:4px; font-family:Roboto; font-size:15px;"
        f" font-weight:bold; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
    )
    return b


# =============================================================================
# Message Dialog
# =============================================================================

class Ui_FormMessage:
    """Message form for creating and transmitting messages."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        refresh_callback=None
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
        self._message_is_expanded: bool = False

    def setupUi(self, FormMessage: QtWidgets.QWidget) -> None:
        self.MainWindow = FormMessage
        FormMessage.setObjectName("FormMessage")
        FormMessage.setWindowTitle("GROUP MESSAGE")
        FormMessage.resize(835, 370)

        FormMessage.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

        if os.path.exists("radiation-32.png"):
            FormMessage.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        FormMessage.setStyleSheet(f"""
            QWidget {{ background-color: {_DATA_BG}; }}
            QLabel {{ color: {COLOR_INPUT_TEXT}; background-color: transparent; font-size: 13px; }}
            QLineEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
            QComboBox {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
            QComboBox:disabled {{
                background-color: {COLOR_DISABLED_BG}; color: {COLOR_DISABLED_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER};
            }}
            QComboBox QAbstractItemView {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                selection-background-color: #cce5ff; selection-color: #000000;
            }}
            QPlainTextEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(FormMessage)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Title
        title = QtWidgets.QLabel("GROUP MESSAGE")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # Settings row: Rig | Mode | Freq | Delivery
        def _labeled_col(lbl_text, ctrl):
            col = QtWidgets.QVBoxLayout()
            col.setSpacing(2)
            lbl = QtWidgets.QLabel(lbl_text)
            lbl.setFont(_lbl_font())
            col.addWidget(lbl)
            col.addWidget(ctrl)
            return col

        settings_row = QtWidgets.QHBoxLayout()
        settings_row.setSpacing(8)

        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFixedWidth(150)
        self.rig_combo.setObjectName("rig_combo")
        settings_row.addLayout(_labeled_col("Rig:", self.rig_combo))

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setFixedWidth(100)
        self.mode_combo.addItem("Slow",   4)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast",   1)
        self.mode_combo.addItem("Turbo",  2)
        self.mode_combo.addItem("Ultra",  8)
        self.mode_combo.setObjectName("mode_combo")
        settings_row.addLayout(_labeled_col("Mode:", self.mode_combo))

        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setFixedWidth(90)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet(
            f"background-color: {COLOR_DISABLED_BG}; color: {COLOR_DISABLED_TEXT};"
            f" border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px;"
        )
        self.freq_field.setObjectName("freq_field")
        settings_row.addLayout(_labeled_col("Freq:", self.freq_field))

        self.delivery_combo = QtWidgets.QComboBox()
        self.delivery_combo.setFixedWidth(160)
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        self.delivery_combo.setObjectName("delivery_combo")
        settings_row.addLayout(_labeled_col("Delivery:", self.delivery_combo))

        settings_row.addStretch()
        layout.addLayout(settings_row)

        # Group row
        group_row = QtWidgets.QHBoxLayout()
        group_row.setSpacing(8)
        group_lbl = QtWidgets.QLabel("Group:")
        group_lbl.setFont(_lbl_font())
        group_lbl.setFixedWidth(110)
        group_row.addWidget(group_lbl)
        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setFixedWidth(180)
        self.group_combo.setObjectName("group_combo")
        group_row.addWidget(self.group_combo)
        group_row.addStretch()
        layout.addLayout(group_row)

        # From Callsign row
        callsign_row = QtWidgets.QHBoxLayout()
        callsign_row.setSpacing(8)
        self.label_3 = QtWidgets.QLabel("From Callsign:")
        self.label_3.setFont(_lbl_font())
        self.label_3.setFixedWidth(110)
        callsign_row.addWidget(self.label_3)
        self.lineEdit_3 = QtWidgets.QLineEdit()
        self.lineEdit_3.setFont(_mono_font())
        self.lineEdit_3.setFixedWidth(120)
        self.lineEdit_3.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.lineEdit_3.setReadOnly(True)
        self.lineEdit_3.setStyleSheet(
            f"background-color: {COLOR_DISABLED_BG}; color: {COLOR_INPUT_TEXT};"
            f" border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px;"
        )
        self.lineEdit_3.setObjectName("lineEdit_3")
        callsign_row.addWidget(self.lineEdit_3)
        callsign_row.addStretch()
        layout.addLayout(callsign_row)

        # Message label + inputs
        self.label_2 = QtWidgets.QLabel("Message:")
        self.label_2.setFont(_lbl_font())
        layout.addWidget(self.label_2)

        self.lineEdit_2 = QtWidgets.QLineEdit()
        self.lineEdit_2.setFont(_mono_font())
        self.lineEdit_2.setMaxLength(MAX_MESSAGE_LENGTH)
        self.lineEdit_2.setObjectName("lineEdit_2")
        layout.addWidget(self.lineEdit_2)

        self.message_expanded = QtWidgets.QPlainTextEdit()
        self.message_expanded.setFont(_mono_font())
        self.message_expanded.setMinimumHeight(100)
        self.message_expanded.hide()
        layout.addWidget(self.message_expanded)

        # Note labels
        _note_style = f"color: {COLOR_ERROR}; font-family: Roboto; font-size: 10px; font-weight: bold;"

        self.note_label = QtWidgets.QLabel("Messages are limited to 67 characters.")
        self.note_label.setStyleSheet(_note_style)
        layout.addWidget(self.note_label)

        self.delivery_legend_label = QtWidgets.QLabel(
            "Delivery: Maximum Reach = RF + Internet | Limited Reach = RF Only"
        )
        self.delivery_legend_label.setStyleSheet(_note_style)
        layout.addWidget(self.delivery_legend_label)

        layout.addStretch()

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.pushButton_3 = _btn("Save Only", COLOR_BTN_CYAN)
        self.pushButton_3.setObjectName("pushButton_3")
        self.pushButton_3.clicked.connect(self._save_only)
        btn_row.addWidget(self.pushButton_3)

        self.pushButton = _btn("Transmit", COLOR_BTN_BLUE)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self._transmit)
        btn_row.addWidget(self.pushButton)

        self.pushButton_2 = _btn("Cancel", _COL_CANCEL)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)
        btn_row.addWidget(self.pushButton_2)

        layout.addLayout(btn_row)

        # Signals
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._generate_msg_id()
        self._load_config()
        self._load_rigs()

    # -------------------------------------------------------------------------
    # Data / config loading
    # -------------------------------------------------------------------------

    def _load_config(self) -> None:
        """Load configuration from database.

        Auto-selects group only if exactly 1 group exists.
        If multiple groups exist, user must select one.
        """
        self.selected_group = self._get_active_group_from_db()

        all_groups = self._get_all_groups_from_db()
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
        available_connectors = [c for c in enabled_connectors if c['rig_name'] in connected_rigs]
        available_count = len(available_connectors)

        if available_count == 0:
            self.rig_combo.addItem(INTERNET_RIG)
        else:
            self.rig_combo.addItem("")
            for c in available_connectors:
                self.rig_combo.addItem(c['rig_name'])
            self.rig_combo.addItem(INTERNET_RIG)

        self.rig_combo.blockSignals(False)

        current_text = self.rig_combo.currentText()
        if current_text:
            self._on_rig_changed(current_text)

    # -------------------------------------------------------------------------
    # Signal handlers
    # -------------------------------------------------------------------------

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
        if hasattr(self, 'message_expanded'):
            self._swap_message_widget(is_internet)

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

        if hasattr(self, 'mode_combo'):
            self.mode_combo.setEnabled(True)

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            if hasattr(self, 'mode_combo'):
                speed_name = (client.speed_name or "").upper()
                mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3, "ULTRA": 4}
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
            except TypeError:
                pass
            try:
                client.frequency_received.disconnect(self._on_frequency_received)
            except TypeError:
                pass

            client.callsign_received.connect(self._on_callsign_received)
            client.frequency_received.connect(self._on_frequency_received)

            client.get_callsign()
            QtCore.QTimer.singleShot(100, client.get_frequency)
        else:
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        """Handle callsign received from JS8Call."""
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            self.lineEdit_3.setText(callsign)

    def _on_frequency_received(self, rig_name: str, dial_freq: int) -> None:
        """Handle frequency received from JS8Call."""
        if self.rig_combo.currentText() == rig_name:
            frequency_mhz = dial_freq / 1000000
            if hasattr(self, 'freq_field'):
                self.freq_field.setText(f"{frequency_mhz:.3f}")

    def _swap_message_widget(self, internet_only: bool) -> None:
        """Swap between single-line and multi-line message field."""
        if internet_only == self._message_is_expanded:
            return
        self._message_is_expanded = internet_only
        if internet_only:
            text = self.lineEdit_2.text()
            self.lineEdit_2.hide()
            self.message_expanded.setPlainText(text)
            self.message_expanded.show()
            self.note_label.setText(
                f"Internet Only: messages support up to {MAX_MESSAGE_LENGTH_INTERNET} characters."
            )
        else:
            text = self.message_expanded.toPlainText()
            self.message_expanded.hide()
            self.lineEdit_2.setText(text[:MAX_MESSAGE_LENGTH])
            self.lineEdit_2.show()
            self.note_label.setText("Messages are limited to 67 characters.")
        self.MainWindow.adjustSize()

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

    # -------------------------------------------------------------------------
    # Database helpers
    # -------------------------------------------------------------------------

    def _get_active_group_from_db(self) -> str:
        """Get the first group from the database."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups ORDER BY name LIMIT 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
        except sqlite3.Error as e:
            print(f"Error reading group from database: {e}")
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

    # -------------------------------------------------------------------------
    # Validation / messaging helpers
    # -------------------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

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
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == "":
            self._show_error("Please select a Rig")
            self.rig_combo.setFocus()
            return None

        group_name = self.group_combo.currentText()
        if not group_name or group_name == "":
            self._show_error("Please select a Group")
            self.group_combo.setFocus()
            return None

        if self._message_is_expanded and hasattr(self, 'message_expanded'):
            message_raw = self.message_expanded.toPlainText()
        else:
            message_raw = self.lineEdit_2.text()
        message = re.sub(r"[^ -~]+", " ", message_raw)

        if len(message) < MIN_MESSAGE_LENGTH:
            self._show_error("Message too short")
            return None

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
        marker = "{^%3}" if self.rig_combo.currentText() == INTERNET_RIG else "{^%}"
        return f"{group} MSG ,{self.msg_id},{message},{marker}"

    # -------------------------------------------------------------------------
    # Backbone / database
    # -------------------------------------------------------------------------

    def _submit_to_backbone_async(self, frequency: int, callsign: str, message_data: str, now: str) -> None:
        """Start background thread to submit message to backbone server."""
        def submit_thread():
            try:
                data_string = f"{now}\t{frequency}\t0\t30\t{message_data}"
                post_data = urllib.parse.urlencode({
                    'cs': callsign,
                    'data': data_string
                }).encode('utf-8')
                req = urllib.request.Request(_DATAFEED, data=post_data, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = response.read().decode('utf-8').strip()
                if result == "1":
                    print(f"[Backbone] Message submitted successfully (response: {result})")
                else:
                    print(f"[Backbone] Message submission failed - server returned: {result}")
            except Exception as e:
                print(f"[Backbone] Error submitting message: {e}")

        threading.Thread(target=submit_thread, daemon=True).start()

    def _save_to_database(self, callsign: str, message: str, frequency: int = 0) -> None:
        """Save message to database."""
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
                (datetime_str, date_only, frequency, 30,
                 3 if self.rig_combo.currentText() == INTERNET_RIG else 1,
                 self.msg_id, callsign, "@" + self.group_combo.currentText(), message)
            )
            conn.commit()
            freq_mhz = frequency / 1000000.0 if frequency else 0
            print(f"{datetime_str}, @{self.group_combo.currentText()}, {self.msg_id}, {callsign}, {message}, {freq_mhz:.6f} MHz")
        finally:
            conn.close()

        if frequency > 0:
            if self.delivery_combo.currentText() != "Limited Reach":
                group = "@" + self.group_combo.currentText()
                message_data = f"{callsign}: {group} MSG ,{self.msg_id},{message},{{^%}}"
                self._submit_to_backbone_async(frequency, callsign, message_data, datetime_str)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _save_only(self) -> None:
        """Validate and save message to database without transmitting."""
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return

        callsign, message = result

        tx_message = self._build_message(message)
        self._show_info(f"CommStat has saved:\n{tx_message}")

        self._save_to_database(callsign, message)

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
            message_data = f"{callsign}: @{self.group_combo.currentText()} MSG ,{self.msg_id},{message},{{^%3}}"
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

        self._pending_message = self._build_message(message)
        self._pending_callsign = callsign

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

        if selected_call:
            QtWidgets.QMessageBox.critical(
                self.MainWindow, "ERROR",
                f"JS8Call has {selected_call} selected.\n\n"
                "Go to JS8Call and click the \"Deselect\" button."
            )
            return

        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError:
                pass
            client.frequency_received.connect(self._on_frequency_for_transmit)
            client.get_frequency()

    def _on_frequency_for_transmit(self, rig_name: str, frequency: int) -> None:
        """Handle frequency received - now transmit and save."""
        if self.rig_combo.currentText() != rig_name:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client:
            try:
                client.frequency_received.disconnect(self._on_frequency_for_transmit)
            except TypeError:
                pass

        try:
            client.send_tx_message(self._pending_message)

            message = self.lineEdit_2.text()
            message = re.sub(r"[^ -~]+", " ", message)
            self._save_to_database(self.callsign, message, frequency)

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

    connector_manager = ConnectorManager()
    connector_manager.init_connectors_table()
    tcp_pool = TCPConnectionPool(connector_manager)
    tcp_pool.connect_all()

    FormMessage = QtWidgets.QWidget()
    ui = Ui_FormMessage(tcp_pool, connector_manager)
    ui.setupUi(FormMessage)
    FormMessage.show()
    sys.exit(app.exec_())
