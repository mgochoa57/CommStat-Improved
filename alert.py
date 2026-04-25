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

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_DISABLED_BG, COLOR_DISABLED_TEXT,
    COLOR_ERROR, COLOR_BTN_BLUE, COLOR_BTN_CYAN,
)

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

MIN_CALLSIGN_LENGTH = 4
MAX_CALLSIGN_LENGTH = 8
MAX_TITLE_LENGTH    = 20
MAX_MESSAGE_LENGTH  = 80
DATABASE_FILE       = "traffic.db3"
CONFIG_FILE         = "config.ini"

_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED = _BACKBONE + "/datafeed-808585.php"

INTERNET_RIG = "INTERNET ONLY"

_PROG_BG = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG = DEFAULT_COLORS.get("data_background",    "#F8F6F4")

_COL_CANCEL = "#555555"

CALLSIGN_PATTERN = re.compile(r'[A-Z0-9]{1,3}[0-9][A-Z]{1,3}')

COLOR_OPTIONS = [
    ("Yellow", 1, "#e8e800", "#000000"),
    ("Orange", 2, "#ff8c00", "#ffffff"),
    ("Red",    3, "#dc3545", "#ffffff"),
    ("Black",  4, "#000000", "#ffffff"),
]


# =============================================================================
# Helpers
# =============================================================================

def _lbl_font() -> QtGui.QFont:
    return QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)


def _mono_font() -> QtGui.QFont:
    return QtGui.QFont("Kode Mono")


def _btn(label: str, color: str, min_w: int = 100) -> QtWidgets.QPushButton:
    b = QtWidgets.QPushButton(label)
    b.setMinimumWidth(min_w)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; border:none;"
        f" padding:6px 14px; border-radius:4px; font-family:Roboto; font-size:15px;"
        f" font-weight:bold; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
        f"QPushButton:disabled {{ background-color:#cccccc; color:#888888; }}"
    )
    return b


def make_uppercase(field: QtWidgets.QLineEdit) -> None:
    def to_upper(text):
        if text != text.upper():
            pos = field.cursorPosition()
            field.blockSignals(True)
            field.setText(text.upper())
            field.blockSignals(False)
            field.setCursorPosition(pos)
    field.textChanged.connect(to_upper)


# =============================================================================
# Alert Form
# =============================================================================

class Ui_FormAlert:
    """Alert form for creating and transmitting group alerts."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        on_alert_saved: callable = None,
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
        self.MainWindow = FormAlert
        FormAlert.setWindowTitle("Group Alert")
        FormAlert.setFixedSize(900, 415)

        if os.path.exists("radiation-32.png"):
            FormAlert.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        _readonly_style = (
            f"background-color: {COLOR_DISABLED_BG}; color: {COLOR_DISABLED_TEXT}; "
            f"border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px; "
            "font-family: 'Kode Mono'; font-size: 13px;"
        )

        FormAlert.setStyleSheet(f"""
            QWidget {{ background-color: {_DATA_BG}; }}
            QLabel {{ color: {COLOR_INPUT_TEXT}; font-size: 13px; }}
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
        """)

        layout = QtWidgets.QVBoxLayout(FormAlert)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # ── Title ──────────────────────────────────────────────────────────────
        title = QtWidgets.QLabel("GROUP ALERT")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # ── Settings row ───────────────────────────────────────────────────────
        def _labeled_col(lbl_text, widget):
            col = QtWidgets.QVBoxLayout()
            col.setSpacing(2)
            lbl = QtWidgets.QLabel(lbl_text)
            lbl.setFont(_lbl_font())
            col.addWidget(lbl)
            col.addWidget(widget)
            return col

        settings_row = QtWidgets.QHBoxLayout()
        settings_row.setSpacing(12)

        settings_lbl = QtWidgets.QLabel("Settings:")
        settings_lbl.setFont(_lbl_font())
        settings_row.addWidget(settings_lbl)

        self.rig_combo = QtWidgets.QComboBox()
        settings_row.addLayout(_labeled_col("Rig:", self.rig_combo))

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Slow", 4)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.addItem("Ultra", 8)
        settings_row.addLayout(_labeled_col("Mode:", self.mode_combo))

        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setReadOnly(True)
        self.freq_field.setFixedWidth(90)
        self.freq_field.setStyleSheet(_readonly_style)
        settings_row.addLayout(_labeled_col("Freq:", self.freq_field))

        self.delivery_combo = QtWidgets.QComboBox()
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        settings_row.addLayout(_labeled_col("Delivery:", self.delivery_combo))

        settings_row.addStretch()
        layout.addLayout(settings_row)

        # ── Target row ─────────────────────────────────────────────────────────
        target_row = QtWidgets.QHBoxLayout()
        target_row.setSpacing(8)

        target_lbl = QtWidgets.QLabel("Target:")
        target_lbl.setFont(_lbl_font())
        target_row.addWidget(target_lbl)

        self.group_combo = QtWidgets.QComboBox()
        self.group_combo.setMinimumWidth(150)
        target_row.addWidget(self.group_combo)

        or_lbl = QtWidgets.QLabel("OR Callsign")
        or_lbl.setFont(_lbl_font())
        target_row.addWidget(or_lbl)

        self.target_call_field = QtWidgets.QLineEdit()
        self.target_call_field.setMaxLength(12)
        self.target_call_field.setPlaceholderText("e.g. N0CALL")
        self.target_call_field.setFixedWidth(130)
        target_row.addWidget(self.target_call_field)
        target_row.addStretch()
        layout.addLayout(target_row)

        # ── From Callsign row ──────────────────────────────────────────────────
        callsign_row = QtWidgets.QHBoxLayout()
        callsign_row.setSpacing(8)

        cs_lbl = QtWidgets.QLabel("From Callsign:")
        cs_lbl.setFont(_lbl_font())
        callsign_row.addWidget(cs_lbl)

        self.callsign_field = QtWidgets.QLineEdit()
        self.callsign_field.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.callsign_field.setReadOnly(True)
        self.callsign_field.setFixedWidth(110)
        self.callsign_field.setStyleSheet(_readonly_style)
        callsign_row.addWidget(self.callsign_field)
        callsign_row.addStretch()
        layout.addLayout(callsign_row)

        # ── Color combo (functional, not displayed) ────────────────────────────
        self.color_combo = QtWidgets.QComboBox()
        for name, value, _bg, _fg in COLOR_OPTIONS:
            self.color_combo.addItem(name, value)
        self.color_combo.setCurrentIndex(0)
        self.color_samples = []

        # ── Title field row ────────────────────────────────────────────────────
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(8)

        title_input_lbl = QtWidgets.QLabel("Title:")
        title_input_lbl.setFont(_lbl_font())
        title_input_lbl.setFixedWidth(110)
        title_row.addWidget(title_input_lbl)

        self.title_field = QtWidgets.QLineEdit()
        self.title_field.setMaxLength(MAX_TITLE_LENGTH)
        self.title_field.setFixedWidth(230)
        title_row.addWidget(self.title_field)
        title_row.addStretch()
        layout.addLayout(title_row)

        # ── Message field row ──────────────────────────────────────────────────
        message_row = QtWidgets.QHBoxLayout()
        message_row.setSpacing(8)

        message_lbl = QtWidgets.QLabel("Message:")
        message_lbl.setFont(_lbl_font())
        message_lbl.setFixedWidth(110)
        message_row.addWidget(message_lbl)

        self.message_field = QtWidgets.QLineEdit()
        self.message_field.setMaxLength(MAX_MESSAGE_LENGTH)
        message_row.addWidget(self.message_field)
        layout.addLayout(message_row)

        # ── Notes ──────────────────────────────────────────────────────────────
        _note_style = (
            f"color: {COLOR_ERROR}; font-family: Roboto; font-size: 10px; font-weight: bold;"
        )

        note_lbl = QtWidgets.QLabel("Title: 20 chars max. Message: 80 chars max.")
        note_lbl.setStyleSheet(_note_style)
        layout.addWidget(note_lbl)

        legend_lbl = QtWidgets.QLabel("Delivery: Maximum Reach = RF + Internet | Limited Reach = RF Only")
        legend_lbl.setStyleSheet(_note_style)
        layout.addWidget(legend_lbl)

        layout.addStretch()

        # ── Buttons ────────────────────────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        self.save_button = _btn("Save Only", COLOR_BTN_CYAN)
        self.save_button.clicked.connect(self._save_only)
        btn_row.addWidget(self.save_button)

        self.transmit_button = _btn("Transmit", COLOR_BTN_BLUE)
        self.transmit_button.clicked.connect(self._transmit)
        btn_row.addWidget(self.transmit_button)

        self.cancel_button = _btn("Cancel", _COL_CANCEL)
        self.cancel_button.clicked.connect(self.MainWindow.close)
        btn_row.addWidget(self.cancel_button)

        layout.addLayout(btn_row)

        QtCore.QMetaObject.connectSlotsByName(FormAlert)

        self._generate_alert_id()
        self._load_config()

        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        self.target_call_field.textChanged.connect(self._on_target_callsign_changed)
        make_uppercase(self.target_call_field)

        self._load_rigs()

        FormAlert.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

    # =========================================================================
    # Config / DB
    # =========================================================================

    def _load_config(self) -> None:
        self.selected_group = self._get_active_group_from_db()
        all_groups = self._get_all_groups_from_db()
        self.group_combo.addItem("")
        for group in all_groups:
            self.group_combo.addItem(group)

    def _load_rigs(self) -> None:
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        enabled_connectors = self.connector_manager.get_all_connectors(enabled_only=True) if self.connector_manager else []
        connected_rigs     = self.tcp_pool.get_connected_rig_names() if self.tcp_pool else []
        available          = [c for c in enabled_connectors if c['rig_name'] in connected_rigs]

        if not available:
            self.rig_combo.addItem(INTERNET_RIG)
        else:
            self.rig_combo.addItem("")
            for c in available:
                self.rig_combo.addItem(c['rig_name'])
            self.rig_combo.addItem(INTERNET_RIG)

        self.rig_combo.blockSignals(False)

        current = self.rig_combo.currentText()
        if current:
            self._on_rig_changed(current)

    def _on_rig_changed(self, rig_name: str) -> None:
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

        if hasattr(self, 'mode_combo'):
            self.mode_combo.setEnabled(True)

        if not self.tcp_pool:
            return

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
                self.freq_field.setText(f"{frequency:.3f}" if frequency else "")

            try:
                client.callsign_received.disconnect(self._on_callsign_received)
            except TypeError:
                pass
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
        if not rig_name or rig_name == INTERNET_RIG or "(disconnected)" in rig_name:
            return
        if not self.tcp_pool:
            return
        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})

    def _get_active_group_from_db(self) -> str:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups ORDER BY name LIMIT 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
        except sqlite3.Error as e:
            print(f"Error reading active group from database: {e}")
        return ""

    def _get_all_groups_from_db(self) -> list:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM groups ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Error reading groups from database: {e}")
        return []

    def _on_group_changed(self, group: str) -> None:
        if group:
            self.target_call_field.blockSignals(True)
            self.target_call_field.clear()
            self.target_call_field.blockSignals(False)

    def _on_target_callsign_changed(self, text: str) -> None:
        if text:
            self.group_combo.blockSignals(True)
            self.group_combo.setCurrentIndex(0)
            self.group_combo.blockSignals(False)

    def _get_target(self) -> str:
        call_target = self.target_call_field.text().strip().upper()
        if call_target:
            return call_target
        group = self.group_combo.currentText()
        if group:
            return "@" + group
        return ""

    def _show_error(self, message: str) -> None:
        msg = QMessageBox()
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

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
            self.rig_combo.setFocus()
            return None

        if not self._get_target():
            self._show_error("Please select a Group or enter a Target Callsign")
            self.group_combo.setFocus()
            return None

        color_value = self.color_combo.currentData()

        title = re.sub(r"[^ -~]+", " ", self.title_field.text()).strip()
        if len(title) < 1:
            self._show_error("Title is required")
            self.title_field.setFocus()
            return None

        message = re.sub(r"[^ -~]+", " ", self.message_field.text()).strip()
        if len(message) < 1:
            self._show_error("Message is required")
            self.message_field.setFocus()
            return None

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
        from id_utils import generate_time_based_id
        self.alert_id = generate_time_based_id()

    def _build_message(self, callsign: str, color: int, title: str, message: str) -> str:
        target = self._get_target()
        marker = "{%%3}" if self.rig_combo.currentText() == INTERNET_RIG else "{%%}"
        return f"{callsign}: {target} ,{self.alert_id},{color},{title},{message},{marker}"

    def _submit_to_backbone_async(self, frequency: int, callsign: str, alert_data: str, now: str) -> None:
        def submit_thread():
            try:
                data_string = f"{now}\t{frequency}\t0\t30\t{alert_data}"
                post_data = urllib.parse.urlencode({
                    'cs': callsign, 'data': data_string
                }).encode('utf-8')
                req = urllib.request.Request(_DATAFEED, data=post_data, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = response.read().decode('utf-8').strip()
                if result != "1":
                    print(f"[Backbone] Alert submission failed - server returned: {result}")
            except Exception as e:
                print(f"[Backbone] Error submitting alert: {e}")

        threading.Thread(target=submit_thread, daemon=True).start()

    def _save_to_database(self, callsign: str, color: int, title: str, message: str,
                          frequency: int = 0, db: int = 30) -> None:
        now = QDateTime.currentDateTime()
        datetime_str = now.toUTC().toString("yyyy-MM-dd HH:mm:ss")
        date_only    = now.toUTC().toString("yyyy-MM-dd")
        target       = self._get_target()
        source       = 3 if self.rig_combo.currentText() == INTERNET_RIG else 1

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO alerts "
                "(datetime, date, freq, db, source, alert_id, from_callsign, target, color, title, message) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime_str, date_only, frequency, db, source, self.alert_id,
                 callsign, target, color, title, message)
            )
            conn.commit()
        finally:
            conn.close()

        if frequency > 0:
            if self.delivery_combo.currentText() != "Limited Reach":
                alert_data = f"{callsign}: {target} ,{self.alert_id},{color},{title},{message},{{%%}}"
                self._submit_to_backbone_async(frequency, callsign, alert_data, datetime_str)

    def _save_only(self) -> None:
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return
        callsign, color, title, message = result
        self._save_to_database(callsign, color, title, message)
        self.MainWindow.close()
        if self.on_alert_saved:
            self.on_alert_saved()

    def _transmit(self) -> None:
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
            self._pending_message  = self._build_message(callsign, color, title, message)
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

        self._pending_message       = self._build_message(callsign, color, title, message)
        self._pending_callsign      = callsign
        self._pending_color         = color
        self._pending_title         = title
        self._pending_alert_message = message

        try:
            client.call_selected_received.disconnect(self._on_call_selected_for_transmit)
        except TypeError:
            pass
        client.call_selected_received.connect(self._on_call_selected_for_transmit)
        client.get_call_selected()

    def _on_call_selected_for_transmit(self, rig_name: str, selected_call: str) -> None:
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
            self._save_to_database(
                self._pending_callsign,
                self._pending_color,
                self._pending_title,
                self._pending_alert_message,
                frequency,
            )
            self.MainWindow.close()
            if self.on_alert_saved:
                self.on_alert_saved()
        except Exception as e:
            self._show_error(f"Failed to transmit alert: {e}")


if __name__ == "__main__":
    from connector_manager import ConnectorManager
    from js8_tcp_client import TCPConnectionPool

    app = QtWidgets.QApplication(sys.argv)
    connector_manager = ConnectorManager()
    connector_manager.init_connectors_table()
    tcp_pool = TCPConnectionPool(connector_manager)
    tcp_pool.connect_all()

    FormAlert = QtWidgets.QWidget()
    ui = Ui_FormAlert(tcp_pool, connector_manager)
    ui.setupUi(FormAlert)
    FormAlert.show()
    sys.exit(app.exec_())
