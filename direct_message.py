# Copyright (c) 2025, 2026 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Direct Message Dialog for CommStat
Allows sending a free-form message directly to a specific callsign via backbone.
"""

import base64
import os
import re
import sqlite3
import threading
import urllib.request
import urllib.parse
from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QDialog, QMessageBox

from id_utils import generate_time_based_id
from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_BTN_BLUE, COLOR_BTN_CYAN,
)

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

DATABASE_FILE = "traffic.db3"

_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED  = _BACKBONE + "/datafeed-808585.php"

_PROG_BG = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG = DEFAULT_COLORS.get("data_background",    "#F8F6F4")

_COL_CANCEL = "#555555"


# =============================================================================
# Helpers
# =============================================================================

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
        f"QPushButton:disabled {{ background-color:#cccccc; color:#888888; }}"
    )
    return b


# =============================================================================
# Direct Message Dialog
# =============================================================================

class DirectMessageDialog(QDialog):
    """Dialog for sending a direct message to a specific callsign via backbone."""

    last_seen_updated = QtCore.pyqtSignal(str)

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        target_callsign: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager
        self.callsign: str = self._get_my_callsign()
        self._target_callsign = target_callsign.strip().upper()

        self._setup_ui()
        if self._target_callsign:
            self.callsign_input.setText(self._target_callsign)

    # -------------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setWindowTitle("Direct Message")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.setMinimumSize(520, 420)
        self.resize(520, 420)

        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        self.setStyleSheet(f"""
            QDialog {{ background-color: {_DATA_BG}; }}
            QLabel {{ color: {COLOR_INPUT_TEXT}; font-size: 13px; }}
            QLineEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 2px 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
            QPlainTextEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QtWidgets.QLabel("DIRECT MESSAGE")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # Callsign row
        callsign_label = QtWidgets.QLabel("Callsign:")
        callsign_label.setFont(_lbl_font())
        layout.addWidget(callsign_label)

        callsign_row = QtWidgets.QHBoxLayout()
        callsign_row.setSpacing(8)

        self.callsign_input = QtWidgets.QLineEdit()
        self.callsign_input.setFont(_mono_font())
        self.callsign_input.setFixedWidth(120)
        self.callsign_input.setMinimumHeight(28)
        self.callsign_input.setMaxLength(12)
        self.callsign_input.setPlaceholderText("e.g. N0CALL")
        self.callsign_input.textChanged.connect(self._on_callsign_changed)
        callsign_row.addWidget(self.callsign_input)

        ls_title = QtWidgets.QLabel("Last Seen:")
        ls_title.setFont(_lbl_font())
        callsign_row.addWidget(ls_title)

        self.last_seen_label = QtWidgets.QLabel("—")
        self.last_seen_label.setFont(_mono_font())
        callsign_row.addWidget(self.last_seen_label)
        callsign_row.addStretch()
        layout.addLayout(callsign_row)

        # Timer for debouncing last-seen lookups
        self._last_seen_timer = QtCore.QTimer(self)
        self._last_seen_timer.setSingleShot(True)
        self._last_seen_timer.timeout.connect(self._trigger_last_seen_lookup)
        self.last_seen_updated.connect(self._on_last_seen_updated)

        # Message
        message_label = QtWidgets.QLabel("Message:")
        message_label.setFont(_lbl_font())
        layout.addWidget(message_label)

        self.message_box = QtWidgets.QPlainTextEdit()
        self.message_box.setFont(_mono_font())
        font_metrics = QtGui.QFontMetrics(self.message_box.font())
        self.message_box.setMinimumHeight(font_metrics.lineSpacing() * 8 + 16)
        self.message_box.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.message_box)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        self.clear_btn = _btn("Clear", COLOR_BTN_CYAN)
        self.clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self.clear_btn)

        self.send_btn = _btn("Send", COLOR_BTN_BLUE)
        self.send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self.send_btn)

        self.cancel_btn = _btn("Cancel", _COL_CANCEL)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def set_message_text(self, text: str) -> None:
        """Pre-fill the message box with the given text."""
        self.message_box.setPlainText(text)
        cursor = self.message_box.textCursor()
        cursor.movePosition(cursor.Start)
        self.message_box.setTextCursor(cursor)
        self.message_box.setFocus()

    def _get_my_callsign(self) -> str:
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT callsign FROM controls WHERE id = 1")
                row = cursor.fetchone()
                return (row[0] or "").strip().upper() if row else ""
        except Exception:
            return ""

    def _on_callsign_changed(self, text: str) -> None:
        upper = text.upper()
        if upper != text:
            pos = self.callsign_input.cursorPosition()
            self.callsign_input.blockSignals(True)
            self.callsign_input.setText(upper)
            self.callsign_input.blockSignals(False)
            self.callsign_input.setCursorPosition(pos)
        self._last_seen_timer.stop()
        if len(upper.strip()) >= 3:
            self.last_seen_label.setText("…")
            self._last_seen_timer.start(600)
        else:
            self.last_seen_label.setText("—")

    def _trigger_last_seen_lookup(self) -> None:
        target = self.callsign_input.text().strip().upper()
        if len(target) < 3 or not self.callsign:
            self.last_seen_label.setText("—")
            return
        threading.Thread(
            target=self._fetch_last_seen_thread,
            args=(target,),
            daemon=True,
        ).start()

    def _fetch_last_seen_thread(self, target: str) -> None:
        try:
            url = (
                f"{_BACKBONE}/get-last-seen-808585.php"
                f"?cs={urllib.parse.quote(self.callsign)}"
                f"&lookup={urllib.parse.quote(target)}"
            )
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = resp.read().decode("utf-8").strip()
            self.last_seen_updated.emit(result if result else "—")
        except Exception as e:
            print(f"[DirectMessage] last-seen error: {e}")
            self.last_seen_updated.emit("—")

    def _on_last_seen_updated(self, value: str) -> None:
        self.last_seen_label.setText(value)

    def _sanitize_message(self, text: str) -> str:
        text = text.replace('\r', '')
        text = text.replace('\n', '||')
        text = re.sub(r'[^\x20-\x7E]', '', text)
        return text.strip()

    def _show_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Direct Message", msg)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _on_clear(self) -> None:
        self.message_box.clear()

    def _on_send(self) -> None:
        target = self.callsign_input.text().strip().upper()
        if not target:
            self._show_error("Please enter a target callsign.")
            self.callsign_input.setFocus()
            return

        text = self._sanitize_message(self.message_box.toPlainText())
        if not text:
            self._show_error("Please enter a message.")
            self.message_box.setFocus()
            return

        if not self.callsign:
            self._show_error("No operator callsign configured in User Settings.")
            return

        now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
        msg_id = generate_time_based_id()

        message_data = f"{self.callsign}: {target} MSG ,{msg_id},{text},{{^%3}}"
        data_string  = f"DM:{now}\t0\t0\t30\t{message_data}"

        self._submit_to_backbone_async(data_string)

        QMessageBox.information(self, "Direct Message", f"Message sent to {target}.")
        self.accept()

    # -------------------------------------------------------------------------
    # Backbone submission
    # -------------------------------------------------------------------------

    def _submit_to_backbone_async(self, data_string: str) -> None:
        callsign = self.callsign

        def submit_thread():
            try:
                post_data = urllib.parse.urlencode({
                    'cs': callsign,
                    'data': data_string,
                }).encode('utf-8')
                req = urllib.request.Request(_DATAFEED, data=post_data, method='POST')
                with urllib.request.urlopen(req, timeout=10) as response:
                    result = response.read().decode('utf-8').strip()
                if result != "1":
                    print(f"[DirectMessage] Backbone returned: {result}")
            except Exception as e:
                print(f"[DirectMessage] Backbone error: {e}")

        threading.Thread(target=submit_thread, daemon=True).start()
