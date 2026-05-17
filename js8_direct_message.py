# Copyright (c) 2025, 2026 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 Direct Message Dialog for CommStat
Point-to-point JS8 message to a single callsign, sent directly or via a relay
that has been observed hearing the target.
"""

import os
import re
import sqlite3
from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPlainTextEdit,
    QMessageBox,
)

from constants import (
    DEFAULT_COLORS,
    COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_DISABLED_BG, COLOR_DISABLED_TEXT,
    COLOR_BTN_BLUE, COLOR_BTN_RED, COLOR_BTN_CYAN,
)
from id_utils import generate_time_based_id
from qrz_client import get_qrz_cached
from ui_helpers import make_button

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

DATABASE_FILE = "traffic.db3"

MIN_MESSAGE_LENGTH = 1
MAX_MESSAGE_LENGTH = 250

WINDOW_WIDTH  = 600
WINDOW_HEIGHT = 460

QRZ_MISS_TEXT = "Callsign not found in local cache"

NO_RELAY_LABEL = "NO-RELAY"
UNKNOWN_SNR_SENTINEL = -99

# Loose JS8 callsign shape — accepts base calls and slash suffixes
# (KO4BIA, K2DHS, W3BFO/P, KO4BIA/QRP). Validates typed entries in the
# Target / Relay combos so the Transmit button only enables on something
# that looks like a callsign.
_CALLSIGN_PATTERN = re.compile(r"^[A-Z0-9/]{3,12}$")

_PROG_BG    = DEFAULT_COLORS.get("program_background",   "#A52A2A")
_PROG_FG    = DEFAULT_COLORS.get("program_foreground",   "#FFFFFF")
_PANEL_BG   = DEFAULT_COLORS.get("module_background",    "#DDDDDD")
_PANEL_FG   = DEFAULT_COLORS.get("module_foreground",    "#FFFFFF")
_COL_HELP   = "#e83e8c"  # matches StatRep help button
_COL_CANCEL = "#555555"


# =============================================================================
# JS8 Direct Message Dialog
# =============================================================================

class JS8DirectMessageDialog(QDialog):
    """Send a JS8 directed message to a single callsign, optionally via a relay."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        parent=None
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager

        self._current_freq_mhz = None
        self._pending_payload = ""

        self.setWindowTitle("JS8 Direct Message")
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        self._setup_ui()
        self._load_rigs()
        self._update_transmit_state()

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"QDialog {{ background-color:{_PANEL_BG}; }}"
            f"QLabel {{ color:{_PANEL_FG}; font-family:Roboto; font-size:13px; }}"
            f"QLineEdit {{ background-color:white; color:{COLOR_INPUT_TEXT};"
            f" border:1px solid {COLOR_INPUT_BORDER}; border-radius:4px; padding:2px 4px;"
            f" font-family:'Kode Mono'; font-size:13px; }}"
            f"QPlainTextEdit {{ background-color:white; color:{COLOR_INPUT_TEXT};"
            f" border:1px solid {COLOR_INPUT_BORDER}; border-radius:4px; padding:4px;"
            f" font-family:'Kode Mono'; font-size:13px; }}"
            f"QComboBox {{ background-color:white; color:{COLOR_INPUT_TEXT};"
            f" border:1px solid {COLOR_INPUT_BORDER}; border-radius:4px; padding:2px 4px;"
            f" font-family:'Kode Mono'; font-size:13px; combobox-popup:0; }}"
            f"QComboBox:disabled {{ background-color:{COLOR_DISABLED_BG}; color:{COLOR_DISABLED_TEXT}; }}"
            f"QComboBox QAbstractItemView {{ background-color:white; color:{COLOR_INPUT_TEXT};"
            f" selection-background-color:#cce5ff; selection-color:#000000; }}"
            f"QComboBox QAbstractItemView::item {{ min-height:22px; padding:0 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("JS8 Direct Message")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color:{_PROG_BG}; color:{_PROG_FG};"
            f" font-family:'Roboto Slab'; font-size:16px; font-weight:900;"
            f" padding-top:9px; padding-bottom:9px; }}"
        )
        layout.addWidget(title)
        layout.addSpacing(4)

        # Row 1: Rig / Mode / Freq
        rig_row = QHBoxLayout()
        rig_row.setSpacing(10)

        self.rig_combo = QComboBox()
        self.rig_combo.setMinimumWidth(150)
        self.rig_combo.setMaxVisibleItems(30)
        self.rig_combo.setItemDelegate(QtWidgets.QStyledItemDelegate(self.rig_combo))
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        rig_row.addLayout(self._labeled_col("Rig:", self.rig_combo))

        self.mode_combo = QComboBox()
        self.mode_combo.setFixedWidth(130)
        self.mode_combo.setMaxVisibleItems(30)
        self.mode_combo.setItemDelegate(QtWidgets.QStyledItemDelegate(self.mode_combo))
        self.mode_combo.addItem("Slow",   4)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast",   1)
        self.mode_combo.addItem("Turbo",  2)
        self.mode_combo.addItem("Ultra",  8)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        rig_row.addLayout(self._labeled_col("Mode:", self.mode_combo))

        self.freq_field = QLineEdit()
        self.freq_field.setFixedWidth(90)
        self.freq_field.setReadOnly(True)
        rig_row.addLayout(self._labeled_col("Freq:", self.freq_field))

        rig_row.addStretch()
        layout.addLayout(rig_row)

        # Row 2: Target / Relay
        sta_row = QHBoxLayout()
        sta_row.setSpacing(10)

        self.target_combo = QComboBox()
        self.target_combo.setFixedWidth(150)
        self.target_combo.setEditable(True)
        self.target_combo.setInsertPolicy(QComboBox.NoInsert)
        self.target_combo.setMaxVisibleItems(30)
        self.target_combo.setItemDelegate(QtWidgets.QStyledItemDelegate(self.target_combo))
        self.target_combo.currentTextChanged.connect(self._on_target_changed)
        self._wire_uppercase(self.target_combo)
        sta_row.addLayout(self._labeled_col("Target:", self.target_combo))

        self.relay_combo = QComboBox()
        self.relay_combo.setFixedWidth(220)
        self.relay_combo.setEditable(True)
        self.relay_combo.setInsertPolicy(QComboBox.NoInsert)
        self.relay_combo.setMaxVisibleItems(30)
        self.relay_combo.setItemDelegate(QtWidgets.QStyledItemDelegate(self.relay_combo))
        self.relay_combo.setModel(QStandardItemModel(self.relay_combo))
        self.relay_combo.currentTextChanged.connect(lambda _t: self._update_transmit_state())
        self._wire_uppercase(self.relay_combo)
        sta_row.addLayout(self._labeled_col("Relay:", self.relay_combo))

        self.btn_refresh = make_button("Refresh", COLOR_BTN_CYAN, min_w=90)
        self.btn_refresh.clicked.connect(self._on_refresh_targets)
        sta_row.addLayout(self._labeled_col(" ", self.btn_refresh))

        sta_row.addStretch()
        layout.addLayout(sta_row)

        # QRZ info for selected Target (cache-only lookup)
        self.qrz_info_label = QLabel("")
        self.qrz_info_label.setFixedHeight(22)
        self.qrz_info_label.setTextFormat(Qt.PlainText)
        self.qrz_info_label.setStyleSheet(
            "QLabel { background-color:transparent; color:#000000;"
            " padding-left:2px; font-size:13px; }"
        )
        layout.addWidget(self.qrz_info_label)

        # Message body (~4 visual rows)
        msg_label = QLabel("Message:")
        msg_label.setStyleSheet("QLabel { font-family:Roboto; font-size:13px; font-weight:bold; }")
        layout.addWidget(msg_label)

        self.body = QPlainTextEdit()
        self.body.setFixedHeight(96)
        self.body.textChanged.connect(self._update_transmit_state)
        layout.addWidget(self.body)

        layout.addStretch()

        # Buttons: Help (left) · Clear · Transmit · Cancel (right)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_help = make_button("Help", _COL_HELP, min_w=90)
        self.btn_help.clicked.connect(self._on_help_clicked)
        btn_row.addWidget(self.btn_help)

        btn_row.addStretch()

        self.btn_clear = make_button("Clear", COLOR_BTN_CYAN, min_w=100)
        self.btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self.btn_clear)

        self.btn_transmit = make_button("Transmit", COLOR_BTN_BLUE, min_w=100)
        self.btn_transmit.clicked.connect(self._on_transmit)
        btn_row.addWidget(self.btn_transmit)

        self.btn_cancel = make_button("Cancel", COLOR_BTN_RED, min_w=100)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        layout.addLayout(btn_row)

    def _labeled_col(self, lbl_text: str, ctrl) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl = QLabel(lbl_text)
        lbl.setStyleSheet("QLabel { font-family:Roboto; font-size:13px; font-weight:bold; }")
        col.addWidget(lbl)
        col.addWidget(ctrl)
        return col

    @staticmethod
    def _wire_uppercase(combo: QComboBox) -> None:
        """Force the combo's editable line edit to uppercase as the user types."""
        line = combo.lineEdit()
        if line is None:
            return

        def to_upper(text: str) -> None:
            if text == text.upper():
                return
            pos = line.cursorPosition()
            line.blockSignals(True)
            line.setText(text.upper())
            line.blockSignals(False)
            line.setCursorPosition(pos)

        line.textChanged.connect(to_upper)

    def _effective_target_cs(self) -> str:
        """Target callsign currently in the dropdown — typed or selected."""
        return self.target_combo.currentText().strip().upper()

    def _update_qrz_info(self, target_cs: str) -> None:
        """
        Refresh the QRZ info label for *target_cs* from the local cache.

        Only hits the cache (no network) — keeps every keystroke cheap and
        leaves online lookups to the standalone QRZ Lookup dialog.
        """
        cs = (target_cs or "").strip().upper()
        if not cs:
            self.qrz_info_label.clear()
            return
        if not _CALLSIGN_PATTERN.match(cs):
            self.qrz_info_label.clear()
            return

        cached = get_qrz_cached(cs, include_stale=True)
        if not cached:
            self.qrz_info_label.setText(QRZ_MISS_TEXT)
            self.qrz_info_label.setStyleSheet(
                "QLabel { background-color:transparent; color:#000000;"
                " padding-left:2px; font-family:'Roboto'; font-size:13px;"
                " font-weight:bold; }"
            )
            return

        name    = (cached.get("name")    or "").strip()
        country = (cached.get("country") or "").strip()
        if name and country:
            text = f"{name} | {country}"
        else:
            text = name or country
        if not text:
            self.qrz_info_label.setText(QRZ_MISS_TEXT)
            self.qrz_info_label.setStyleSheet(
                "QLabel { background-color:transparent; color:#000000;"
                " padding-left:2px; font-family:'Roboto'; font-size:13px;"
                " font-weight:bold; }"
            )
            return

        self.qrz_info_label.setText(text)
        self.qrz_info_label.setStyleSheet(
            "QLabel { background-color:transparent; color:#000000;"
            " padding-left:2px; font-family:'Kode Mono'; font-size:13px; }"
        )

    def _effective_relay_cs(self) -> str:
        """
        Relay callsign currently in the dropdown.

        Dropdown items store the bare callsign in Qt.UserRole — display text
        may be 'KO4BIA  +05' or the bold 'NO-RELAY' label. For typed entries
        (no UserRole data) we fall back to the first whitespace-delimited
        token of the visible text so the user can paste 'KO4BIA  +05' and
        still have it interpreted correctly.
        """
        data = self.relay_combo.currentData(Qt.UserRole)
        if data:
            return str(data).strip().upper()
        text = self.relay_combo.currentText().strip().upper()
        if not text:
            return ""
        return text.split()[0]

    # -------------------------------------------------------------------------
    # Rig wiring
    # -------------------------------------------------------------------------

    def _load_rigs(self) -> None:
        """Populate rig dropdown with connected radio rigs only (no INTERNET ONLY)."""
        if not self.tcp_pool:
            return

        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        enabled = (self.connector_manager.get_all_connectors(enabled_only=True)
                   if self.connector_manager else [])
        connected = set(self.tcp_pool.get_connected_rig_names())
        available = [c['rig_name'] for c in enabled if c['rig_name'] in connected]

        if not available:
            pass
        elif len(available) == 1:
            self.rig_combo.addItem(available[0])
        else:
            self.rig_combo.addItem("")
            for name in available:
                self.rig_combo.addItem(name)

        self.rig_combo.blockSignals(False)

        current = self.rig_combo.currentText()
        if current:
            self._on_rig_changed(current)

    def _on_rig_changed(self, rig_name: str) -> None:
        if not rig_name or not self.tcp_pool:
            self.freq_field.setText("")
            self._current_freq_mhz = None
            self._populate_targets([])
            return

        # Disconnect from prior clients to avoid double-fires
        for client_name in self.tcp_pool.get_all_rig_names():
            client = self.tcp_pool.get_client(client_name)
            if client:
                try:
                    client.frequency_received.disconnect(self._on_frequency_received)
                except TypeError:
                    pass

        client = self.tcp_pool.get_client(rig_name)
        if not (client and client.is_connected()):
            self.freq_field.setText("")
            self._current_freq_mhz = None
            self._populate_targets([])
            self._update_transmit_state()
            return

        client.frequency_received.connect(self._on_frequency_received)

        # Sync mode dropdown from rig's current speed
        speed_name = (client.speed_name or "").upper()
        mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3, "ULTRA": 4}
        idx = mode_map.get(speed_name, 1)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.blockSignals(False)

        # Use cached freq if available, then request a fresh one
        freq = client.frequency
        if freq:
            self.freq_field.setText(f"{freq:.3f}")
            self._current_freq_mhz = float(freq)
            self._load_targets(self._current_freq_mhz)
        else:
            self.freq_field.setText("")
            self._current_freq_mhz = None
            self._populate_targets([])

        client.get_frequency()
        self._update_transmit_state()

    def _on_frequency_received(self, rig_name: str, dial_freq: int) -> None:
        if self.rig_combo.currentText() != rig_name:
            return
        freq_mhz = dial_freq / 1_000_000
        self.freq_field.setText(f"{freq_mhz:.3f}")
        self._current_freq_mhz = float(freq_mhz)
        self._load_targets(self._current_freq_mhz)

    def _on_mode_changed(self, _index: int) -> None:
        rig_name = self.rig_combo.currentText()
        if not rig_name or not self.tcp_pool:
            return
        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})

    # -------------------------------------------------------------------------
    # Contacts queries
    # -------------------------------------------------------------------------

    def _load_targets(self, freq_mhz: float) -> None:
        rows = []
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cur = conn.execute(
                    "SELECT DISTINCT target_cs FROM contacts "
                    "WHERE freq = ? ORDER BY target_cs",
                    (freq_mhz,),
                )
                rows = [r[0] for r in cur.fetchall() if r[0]]
        except sqlite3.Error as e:
            print(f"[JS8DirectMessage] target query failed: {e}")
        self._populate_targets(rows)

    def _populate_targets(self, target_list) -> None:
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem("")
        for cs in target_list:
            self.target_combo.addItem(cs)
        self.target_combo.blockSignals(False)
        self._populate_relays([], "")
        self._update_transmit_state()

    def _on_target_changed(self, target_cs: str) -> None:
        target_cs = (target_cs or "").strip()
        self._update_qrz_info(target_cs)
        if not target_cs or self._current_freq_mhz is None:
            self._populate_relays([], "")
            self._update_transmit_state()
            return

        rows = []
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cur = conn.execute(
                    "SELECT relay_cs, target_snr FROM contacts "
                    "WHERE target_cs = ? AND freq = ? "
                    "ORDER BY target_snr DESC",
                    (target_cs, self._current_freq_mhz),
                )
                rows = cur.fetchall()
        except sqlite3.Error as e:
            print(f"[JS8DirectMessage] relay query failed: {e}")

        self._populate_relays(rows, target_cs)

    def _populate_relays(self, rows, target_cs: str) -> None:
        model: QStandardItemModel = self.relay_combo.model()
        self.relay_combo.blockSignals(True)
        model.clear()

        blank = QStandardItem("")
        blank.setData("", Qt.UserRole)
        model.appendRow(blank)

        for relay_cs, target_snr in rows:
            if not relay_cs:
                continue
            try:
                snr_int = int(target_snr)
            except (TypeError, ValueError):
                snr_int = 0

            if relay_cs == target_cs:
                item = QStandardItem(f"{NO_RELAY_LABEL}  {snr_int:+d}")
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            else:
                item = QStandardItem(f"{relay_cs}  {snr_int:+d}")
            item.setData(relay_cs, Qt.UserRole)
            model.appendRow(item)

        self.relay_combo.setCurrentIndex(0)
        self.relay_combo.blockSignals(False)
        self._update_transmit_state()

    # -------------------------------------------------------------------------
    # Transmit state + actions
    # -------------------------------------------------------------------------

    def _update_transmit_state(self) -> None:
        target_ok = bool(_CALLSIGN_PATTERN.match(self._effective_target_cs()))
        relay_ok = bool(_CALLSIGN_PATTERN.match(self._effective_relay_cs()))
        body_ok = bool(self.body.toPlainText().strip())
        rig_ok = self._rig_client_connected()
        self.btn_transmit.setEnabled(target_ok and relay_ok and body_ok and rig_ok)

    def _rig_client_connected(self) -> bool:
        if not self.tcp_pool:
            return False
        rig_name = self.rig_combo.currentText()
        if not rig_name:
            return False
        client = self.tcp_pool.get_client(rig_name)
        return bool(client and client.is_connected())

    def _show_error(self, message: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("JS8 Direct Message")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _on_help_clicked(self) -> None:
        """Show a styled help dialog explaining how JS8 Direct Message works."""
        dlg = QDialog(self)
        dlg.setWindowTitle("JS8 Direct Message Help")
        dlg.setWindowFlags(
            Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint
        )
        if os.path.exists("radiation-32.png"):
            dlg.setWindowIcon(QtGui.QIcon("radiation-32.png"))
        dlg.setFixedWidth(880)

        dlg.setStyleSheet(
            f"QDialog {{ background-color:{_PANEL_BG}; }}"
            f"QLabel  {{ color:{_PANEL_FG}; background-color:transparent; font-size:13px; }}"
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("JS8 Direct Message Help")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color:{_PROG_BG}; color:{_PROG_FG};"
            f" font-family:'Roboto Slab'; font-size:16px; font-weight:900;"
            f" padding-top:9px; padding-bottom:9px; }}"
        )
        layout.addWidget(title)

        def _section_header(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "QLabel { background-color:transparent; color:#000000;"
                " font-family:'Roboto'; font-size:13px; font-weight:bold;"
                " padding-bottom:2px; border-bottom:1px solid #999999; }"
            )
            return lbl

        def _body_label(html: str) -> QLabel:
            lbl = QLabel(html)
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "QLabel { background-color:transparent; color:#000000;"
                " font-family:'Roboto'; font-size:13px; padding-left:8px; }"
            )
            return lbl

        # Two-column body layout
        cols = QHBoxLayout()
        cols.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(10)
        right = QVBoxLayout()
        right.setSpacing(10)

        # Left column: How It Works · Target & Relay · Refresh
        left.addWidget(_section_header("How It Works"))
        left.addWidget(_body_label(
            "CommStat continuously monitors the JS8Call live feed and builds a "
            "roster of callsigns that have been recently heard on the air. "
            "This dialog lets you pick a destination from that roster and send "
            "a point-to-point JS8 directed message &mdash; no typing of "
            "callsigns required."
        ))

        left.addWidget(_section_header("Target & Relay"))
        left.addWidget(_body_label(
            "<b>Target</b> &mdash; the callsign you want to reach.<br>"
            "<b>Relay</b> &mdash; a station that has recently been heard "
            "hearing your Target. Pick a Relay when you can't reach the "
            "Target directly &mdash; CommStat builds the standard JS8 relay "
            "payload (<i>RELAY&gt; TARGET MSG ...</i>) for you.<br>"
            f"<b>{NO_RELAY_LABEL}</b> &mdash; appears in the "
            "Relay list (in bold) whenever the Target itself has been heard "
            "directly. Selecting it sends a non-relayed transmission "
            "straight to the Target.<br>"
            "Both dropdowns are <b>editable</b> &mdash; type a callsign "
            "manually when the station you want isn't in the roster yet. "
            "To send a non-relayed transmission to a typed Target, type "
            "the same callsign in the Relay box."
        ))

        left.addWidget(_section_header("Refresh"))
        left.addWidget(_body_label(
            "Re-queries the contacts roster at the current rig frequency and "
            "rebuilds the Target dropdown. Use it to pick up callsigns that "
            "have come on the air since you opened this dialog. The Relay "
            "dropdown is cleared so you re-pick a relay after the Target."
        ))
        left.addStretch()

        # Right column: Signal Reports · Mode · Tips
        right.addWidget(_section_header("Signal Reports (SNR)"))
        right.addWidget(_body_label(
            "The number next to each Relay entry is the SNR at which the "
            "Relay reported hearing the Target &mdash; higher is better. "
            f"An SNR of <b>{UNKNOWN_SNR_SENTINEL:+d}</b> is a placeholder "
            "meaning the SNR is unknown. This happens when the roster row "
            "came from a HEARING report (e.g., <i>W3BFO: KC1OSZ HEARING "
            "K4KBT NY5V K2DHS</i>), which lists stations but carries no "
            "signal numbers."
        ))

        right.addWidget(_section_header("Mode"))
        right.addWidget(_body_label(
            "<table cellspacing='2' cellpadding='1'>"
            "<tr><td><b>Slow</b></td><td>&nbsp;&nbsp;8 WPM</td></tr>"
            "<tr><td><b>Normal</b></td><td>&nbsp;&nbsp;16 WPM</td></tr>"
            "<tr><td><b>Fast</b></td><td>&nbsp;&nbsp;24 WPM</td></tr>"
            "<tr><td><b>Turbo</b></td><td>&nbsp;&nbsp;40 WPM</td></tr>"
            "<tr><td><b>Ultra</b></td><td>&nbsp;&nbsp;60 WPM&nbsp;&nbsp;<b>(Use only for JS8Call 3.0.1)</b></td></tr>"
            "</table>"
            "Changing Mode here also re-tunes the selected rig."
        ))

        right.addWidget(_section_header("Tips"))
        right.addWidget(_body_label(
            "&bull; The Rig dropdown only lists radios that are currently "
            "connected &mdash; <i>INTERNET ONLY</i>&nbsp;&nbsp;is intentionally excluded.<br>"
            "&bull; Frequency is read live from the rig and is read-only "
            "here; change it in JS8Call if you need a different band.<br>"
            f"&bull; Messages are capped at {MAX_MESSAGE_LENGTH} characters; "
            "non-printable characters are stripped on transmit.<br>"
            "&bull; <b>Clear</b> wipes only the message body &mdash; Rig, "
            "Mode, Target, and Relay are preserved so you can fire off "
            "several messages in a row."
        ))
        right.addStretch()

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        layout.addLayout(cols)

        layout.addSpacing(4)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = make_button("Close", _COL_CANCEL)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec_()

    def _on_clear(self) -> None:
        """Clear message body only; preserve rig/mode/target/relay."""
        self.body.clear()

    def _on_refresh_targets(self) -> None:
        """Re-query the contacts table for the current rig frequency and repopulate Target."""
        if self._current_freq_mhz is None:
            self._populate_targets([])
            return
        self._load_targets(self._current_freq_mhz)

    def _on_transmit(self) -> None:
        if not self._rig_client_connected():
            self._show_error("Cannot transmit: rig is not connected.")
            return

        target = self._effective_target_cs()
        relay_cs = self._effective_relay_cs()
        if not _CALLSIGN_PATTERN.match(target):
            self._show_error("Enter or pick a valid Target callsign.")
            return
        if not _CALLSIGN_PATTERN.match(relay_cs):
            self._show_error("Enter or pick a valid Relay callsign (or use NO-RELAY).")
            return

        raw = self.body.toPlainText().strip()
        text = re.sub(r"[^ -~]+", " ", raw).strip()
        if len(text) < MIN_MESSAGE_LENGTH:
            self._show_error("Message is empty.")
            return
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH]

        msg_id = generate_time_based_id()
        if relay_cs == target:
            payload = f"{target} MSG ,{msg_id},{text},{{^%}}"
        else:
            payload = f"{relay_cs}> {target} MSG ,{msg_id},{text},{{^%}}"

        rig_name = self.rig_combo.currentText()
        client = self.tcp_pool.get_client(rig_name)
        try:
            client.send_tx_message(payload)

            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"RF DIRECT MESSAGE TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  Rig:      {rig_name}")
            print(f"  Target:   {target}")
            print(f"  Relay:    {'(direct)' if relay_cs == target else relay_cs}")
            print(f"  Msg ID:   {msg_id}")
            print(f"  Full TX:  {payload}")
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

    connector_manager = ConnectorManager()
    connector_manager.init_connectors_table()
    tcp_pool = TCPConnectionPool(connector_manager)
    tcp_pool.connect_all()

    dialog = JS8DirectMessageDialog(tcp_pool, connector_manager)
    dialog.show()
    sys.exit(app.exec_())
