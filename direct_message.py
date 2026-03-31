# Copyright (c) 2025, 2026 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Direct Message Dialog for CommStat
Allows sending a free-form message directly to a specific callsign via backbone.
"""

import base64
import re
import sqlite3  # used by _get_my_callsign
import threading
import urllib.request
import urllib.parse
from typing import Optional, TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QDialog, QMessageBox

from id_utils import generate_time_based_id

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

DATABASE_FILE = "traffic.db3"

_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED = _BACKBONE + "/datafeed-808585.php"

FONT_FAMILY = "Arial"
FONT_SIZE = 12
DATA_BACKGROUND = "#F8F6F4"


# =============================================================================
# Direct Message Dialog
# =============================================================================

class DirectMessageDialog(QDialog):
    """Dialog for sending a direct message to a specific callsign via backbone."""

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
        """Build the user interface."""
        self.setWindowTitle("Direct Message")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.setMinimumWidth(520)

        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        self.setStyleSheet(f"""
            QDialog {{ background-color: {DATA_BACKGROUND}; }}
            QLabel {{ color: #333333; }}
            QLineEdit {{
                background-color: white; color: #333333;
                border: 1px solid #cccccc; border-radius: 4px; padding: 2px 4px;
            }}
            QPlainTextEdit {{
                background-color: white; color: #333333;
                border: 1px solid #cccccc; border-radius: 4px; padding: 4px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QtWidgets.QLabel("Direct Message")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold))
        title.setStyleSheet("color: #333; margin-bottom: 6px;")
        layout.addWidget(title)

        callsign_label = QtWidgets.QLabel("Callsign:")
        callsign_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        layout.addWidget(callsign_label)

        self.callsign_input = QtWidgets.QLineEdit()
        self.callsign_input.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.callsign_input.setFixedWidth(200)
        self.callsign_input.setMinimumHeight(28)
        self.callsign_input.setPlaceholderText("e.g. N0CALL")
        self.callsign_input.textChanged.connect(self._on_callsign_changed)
        layout.addWidget(self.callsign_input)

        # Message text box (~8 rows)
        self.message_box = QtWidgets.QPlainTextEdit()
        self.message_box.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        font_metrics = QtGui.QFontMetrics(self.message_box.font())
        row_height = font_metrics.lineSpacing()
        self.message_box.setMinimumHeight(row_height * 8 + 16)
        self.message_box.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.message_box)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()

        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.clear_btn.setStyleSheet(self._button_style("#17a2b8"))
        self.clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self.clear_btn)

        self.send_btn = QtWidgets.QPushButton("Send")
        self.send_btn.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.send_btn.setStyleSheet(self._button_style("#007bff"))
        self.send_btn.clicked.connect(self._on_send)
        btn_row.addWidget(self.send_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.cancel_btn.setStyleSheet(self._button_style("#dc3545"))
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _button_style(self, color: str) -> str:
        """Generate button stylesheet matching statrep style."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11pt;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """

    def _get_my_callsign(self) -> str:
        """Retrieve operator callsign from controls table."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT callsign FROM controls WHERE id = 1")
                row = cursor.fetchone()
                return (row[0] or "").strip().upper() if row else ""
        except Exception:
            return ""

    def _on_callsign_changed(self, text: str) -> None:
        """Force uppercase on callsign input."""
        upper = text.upper()
        if upper != text:
            pos = self.callsign_input.cursorPosition()
            self.callsign_input.blockSignals(True)
            self.callsign_input.setText(upper)
            self.callsign_input.blockSignals(False)
            self.callsign_input.setCursorPosition(pos)

    def _sanitize_message(self, text: str) -> str:
        """Normalize message text for over-the-air transmission."""
        text = text.replace('\r', '')           # remove carriage returns
        text = text.replace('\n', '||')         # newlines → "||"
        text = re.sub(r'[^\x20-\x7E]', '', text)  # keep only printable ASCII
        return text.strip()

    def _show_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Direct Message", msg)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _on_clear(self) -> None:
        """Clear all input fields."""
        self.callsign_input.clear()
        self.message_box.clear()

    def _on_send(self) -> None:
        """Validate, build, save, and submit the direct message."""
        target = self.callsign_input.text().strip().upper()
        if not target:
            self._show_error("Please enter a target callsign.")
            self.callsign_input.setFocus()
            return

        raw_text = self.message_box.toPlainText()
        text = self._sanitize_message(raw_text)
        if not text:
            self._show_error("Please enter a message.")
            self.message_box.setFocus()
            return

        if not self.callsign:
            self._show_error("No operator callsign configured in User Settings.")
            return

        now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
        msg_id = generate_time_based_id()

        # Build message in backbone format:
        # MYCALL: TARGET MSG ,MSGID,TEXT,{^%3}
        message_data = f"{self.callsign}: {target} MSG ,{msg_id},{text},{{^%3}}"

        # data string: datetime\tfreq\toffset\tsnr\tmessage_data
        data_string = f"DM:{now}\t0\t0\t30\t{message_data}"

        self._submit_to_backbone_async(data_string)

        QMessageBox.information(self, "Direct Message", f"Message sent to {target}.")
        self.accept()

    # -------------------------------------------------------------------------
    # Backbone submission
    # -------------------------------------------------------------------------

    def _submit_to_backbone_async(self, data_string: str) -> None:
        """Submit message to backbone server in a background daemon thread."""
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
