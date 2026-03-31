# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
StatRep Dialog for CommStat
Allows creating and transmitting AMRRON Status Reports via JS8Call.
"""

import base64
import os
import re
import subprocess
import sqlite3
import sys
import urllib.request
import urllib.parse
import threading
from configparser import ConfigParser
from typing import Optional, Dict, List, TYPE_CHECKING
from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog, QComboBox

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

DATABASE_FILE = "traffic.db3"

# Backbone server (base64 encoded)
_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_DATAFEED = _BACKBONE + "/datafeed-808585.php"

# Debug mode via --debug-mode command line flag
_DEBUG_MODE = "--debug-mode" in sys.argv

# Status codes
STATUS_GREEN = "1"
STATUS_YELLOW = "2"
STATUS_RED = "3"
STATUS_UNKNOWN = "4"

# Status display names and their codes
STATUS_OPTIONS = [
    ("", ""),           # Empty/unselected
    ("Green", STATUS_GREEN),
    ("Yellow", STATUS_YELLOW),
    ("Red", STATUS_RED),
    ("Unknown", STATUS_UNKNOWN),
]

# Scope options
SCOPE_OPTIONS = [
    ("My Location", "1"),
    ("My Community", "2"),
    ("My County", "3"),
    ("My Region", "4"),
    ("Other Location", "5"),
]

# Status categories in display order (label, internal_name)
# Note: internal_name is used as dictionary key in the form, not the DB column name
STATUS_CATEGORIES = [
    ("Overall Status", "status"),
    ("Power", "power"),
    ("Water", "water"),
    ("Medical", "medical"),
    ("Comms", "comms"),
    ("Travel", "travel"),
    ("Internet", "internet"),
    ("Fuel", "fuel"),
    ("Food", "food"),
    ("Crime", "crime"),
    ("Civil", "civil"),
    ("Political", "political"),
]

# Colors for status indicators
STATUS_COLORS = {
    "Green": "#28a745",
    "Yellow": "#ffc107",
    "Red": "#dc3545",
    "Unknown": "#6c757d",
}

# Styling
FONT_FAMILY = "Arial"
FONT_SIZE = 12
WINDOW_WIDTH = 700
WINDOW_HEIGHT = 640
WINDOW_HEIGHT_EXPANDED = 760  # Height when Internet Only (expanded remarks)
INTERNET_RIG = "INTERNET ONLY"
REMARKS_MAX_RADIO = 60
REMARKS_MAX_INTERNET = 300  # ~5 lines worth of text
NEWLINE_PLACEHOLDER = "||"
DATA_BACKGROUND = "#F8F6F4"   # matches little_gucci.py 'data_background'


# =============================================================================
# Utility Functions
# =============================================================================

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


def get_state_from_connector(connector_manager, rig_name: str) -> str:
    """Get the state abbreviation from connector table for a specific rig.

    Args:
        connector_manager: ConnectorManager instance for database access.
        rig_name: Name of the rig to look up.

    Returns:
        State abbreviation from connector, or empty string if not found.
    """
    if not connector_manager or not rig_name:
        return ""
    try:
        connector = connector_manager.get_connector_by_name(rig_name)
        if connector and connector.get("state"):
            return connector["state"].strip().upper()
    except Exception:
        pass
    return ""


# =============================================================================
# StatRep Dialog
# =============================================================================

class StatRepDialog(QDialog):
    """Modern StatRep form for creating and transmitting status reports."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool",
        connector_manager: "ConnectorManager",
        parent=None,
        backbone_debug: bool = False,
        panel_background: str = DATA_BACKGROUND,
        data_background: str = DATA_BACKGROUND
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager
        self.backbone_debug = backbone_debug  # Command line override for debug mode
        self.panel_background = panel_background
        self.data_background = data_background

        self.setWindowTitle("CommStat STATREP")
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
        self.callsign = ""
        self.grid = ""
        self.selected_group = ""
        self.statrep_id = ""
        self._pending_frequency = 0  # For storing frequency during transmit

        # Status combo boxes
        self.status_combos: Dict[str, QComboBox] = {}

        # Load config
        self._load_config()

        # Build UI
        self._setup_ui()

        # Load rigs and select default
        self._load_rigs()

    def _load_config(self) -> None:
        """Load configuration from database."""
        # Get active group from database
        self.selected_group = self._get_active_group_from_db()
        # Callsign and grid will be loaded from JS8Call when rig is selected

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

    def _get_default_remarks(self) -> str:
        """Get default remarks with state from the selected rig's connector.

        Returns the state from the connector table, or empty if not set.
        """
        # Get the currently selected rig
        if hasattr(self, 'rig_combo'):
            rig_name = self.rig_combo.currentText()
            if rig_name and "(disconnected)" not in rig_name:
                state = get_state_from_connector(self.connector_manager, rig_name)
                if state:
                    return state
        return ""

    def _is_internet_only(self) -> bool:
        """Check if the current rig selection is Internet Only."""
        return hasattr(self, 'rig_combo') and self.rig_combo.currentText() == INTERNET_RIG

    def _get_remarks_text(self) -> str:
        """Get remarks text from whichever widget is currently active."""
        if self._is_internet_only() and hasattr(self, 'remarks_expanded'):
            return self.remarks_expanded.toPlainText().strip()
        return self.remarks_field.text().strip()

    def _set_remarks_text(self, text: str) -> None:
        """Set remarks text on whichever widget is currently active."""
        if self._is_internet_only() and hasattr(self, 'remarks_expanded'):
            self.remarks_expanded.setPlainText(text)
        else:
            self.remarks_field.setText(text)

    def _swap_remarks_widget(self, internet_only: bool) -> None:
        """Swap between single-line and multi-line remarks field."""
        if not hasattr(self, 'remarks_expanded'):
            return

        # Transfer text between widgets
        if internet_only:
            current_text = self.remarks_field.text().strip()
            self.remarks_field.hide()
            self.remarks_expanded.setPlainText(current_text)
            self.remarks_expanded.show()
            self.setFixedHeight(WINDOW_HEIGHT_EXPANDED)
        else:
            current_text = self.remarks_expanded.toPlainText().strip()
            self.remarks_expanded.hide()
            # Collapse multi-line to single line, truncate if needed
            single_line = current_text.replace('\n', ' ').replace('\r', '')
            self.remarks_field.setText(single_line[:REMARKS_MAX_RADIO])
            self.remarks_field.show()
            self.setFixedHeight(WINDOW_HEIGHT)

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

    def _is_backbone_enabled(self) -> bool:
        """Check if backbone submission is enabled.

        Returns:
            True if enabled (always enabled, can be controlled via config.ini if needed)
        """
        # Always enabled by default. Could read from config.ini if user wants control.
        return True

    def _submit_to_backbone_async(self, frequency: int) -> None:
        """Start background thread to submit statrep to backbone server."""
        if not self._is_backbone_enabled():
            return

        # Capture current state for the thread
        callsign = self.callsign
        message = self._pending_message
        now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
        debug = _DEBUG_MODE or self.backbone_debug

        def submit_thread():
            """Background thread that performs the HTTP POST."""
            try:
                # Format data string: datetime\tfreq_hz\t0\t30\tmessage
                data_string = f"{now}\t{frequency}\t0\t30\t{message}"

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
                if debug:
                    if result == "1":
                        print(f"[Backbone] Statrep submitted successfully (response: {result})")
                    else:
                        print(f"[Backbone] Statrep submission failed - server returned: {result}")

            except Exception as e:
                # Silent failure - only log to terminal in debug mode
                if debug:
                    print(f"[Backbone] Failed to submit statrep: {e}")

        # Start daemon thread (won't block app shutdown)
        thread = threading.Thread(target=submit_thread, daemon=True)
        thread.start()

    def _load_rigs(self) -> None:
        """Load enabled connectors into the rig dropdown, plus Internet option."""
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        enabled_connectors = self.connector_manager.get_all_connectors(enabled_only=True) if self.connector_manager else []
        connected_rigs = self.tcp_pool.get_connected_rig_names() if self.tcp_pool else []
        available_connectors = [c for c in enabled_connectors if c['rig_name'] in connected_rigs]
        available_count = len(available_connectors)

        if available_count == 0:
            # No available connectors — Internet is the only/preselected option
            self.rig_combo.addItem(INTERNET_RIG)
        else:
            # Connectors available — require explicit selection; Internet at bottom
            self.rig_combo.addItem("")  # empty first
            for c in available_connectors:
                self.rig_combo.addItem(c['rig_name'])
            self.rig_combo.addItem(INTERNET_RIG)

        self.rig_combo.blockSignals(False)

        current_text = self.rig_combo.currentText()
        if current_text:
            self._on_rig_changed(current_text)

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - fetch callsign and grid from JS8Call."""
        if not rig_name or "(disconnected)" in rig_name:
            self.callsign = ""
            self.grid = ""
            if hasattr(self, 'from_field'):
                self.from_field.setText("")
                self.grid_field.setText("")
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

        # Swap remarks widget based on rig type
        self._swap_remarks_widget(is_internet)

        if rig_name == INTERNET_RIG:
            callsign, grid, state = self._get_internet_user_settings()
            self.callsign = callsign
            self.grid = grid
            if hasattr(self, 'from_field'):
                self.from_field.setText(callsign)
                self.grid_field.setText(grid)
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")
            if hasattr(self, 'mode_combo'):
                self.mode_combo.setEnabled(False)
                self.mode_combo.setCurrentIndex(-1)
            if state:
                self._set_remarks_text(state)
            return

        # Re-enable mode combo for real rig
        if hasattr(self, 'mode_combo'):
            self.mode_combo.setEnabled(True)
            if self.mode_combo.currentIndex() == -1:
                self.mode_combo.setCurrentIndex(0)

        # Update remarks with state from connector
        state = get_state_from_connector(self.connector_manager, rig_name)
        if state:
            self._set_remarks_text(state)

        if not self.tcp_pool:
            print("[StatRep] No TCP pool available")
            return

        # Disconnect signals from ALL clients to avoid duplicates
        for client_name in self.tcp_pool.get_all_rig_names():
            client = self.tcp_pool.get_client(client_name)
            if client:
                try:
                    client.callsign_received.disconnect(self._on_callsign_received)
                except TypeError:
                    pass
                try:
                    client.grid_received.disconnect(self._on_grid_received)
                except TypeError:
                    pass
                try:
                    client.frequency_received.disconnect(self._on_frequency_received)
                except TypeError:
                    pass

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Connect signals for this client
            client.callsign_received.connect(self._on_callsign_received)
            client.grid_received.connect(self._on_grid_received)
            client.frequency_received.connect(self._on_frequency_received)

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

            # Request callsign, grid, and frequency from JS8Call
            # Small delay between requests to avoid race condition
            print(f"[StatRep] Requesting callsign, grid, and frequency from {rig_name}")
            client.get_callsign()
            QtCore.QTimer.singleShot(100, client.get_grid)  # 100ms delay for grid request
            QtCore.QTimer.singleShot(200, client.get_frequency)  # 200ms delay for frequency request
        else:
            print(f"[StatRep] Client not available or not connected for {rig_name}")
            if hasattr(self, 'freq_field'):
                self.freq_field.setText("")

    def _get_internet_user_settings(self) -> tuple:
        """Get callsign, grid, and state from User Settings for internet-only transmission."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT callsign, gridsquare, state FROM controls WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return (
                        (row[0] or "").strip().upper(),
                        (row[1] or "").strip(),
                        (row[2] or "").strip().upper(),
                    )
        except sqlite3.Error:
            pass
        return ("", "", "")

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
            print(f"[StatRep] Set mode to {self.mode_combo.currentText()} (speed={speed_value})")

    def _on_delivery_changed(self, delivery: str) -> None:
        """Handle delivery dropdown change."""
        pass

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        """Handle callsign received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            if hasattr(self, 'from_field'):
                self.from_field.setText(callsign)

    def _on_grid_received(self, rig_name: str, grid: str) -> None:
        """Handle grid received from JS8Call."""
        print(f"[StatRep] Grid received from {rig_name}: {grid}")
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            self.grid = grid
            if hasattr(self, 'grid_field'):
                self.grid_field.setText(grid)
            # Update remarks with state derived from grid
            if hasattr(self, 'remarks_field'):
                self._set_remarks_text(self._get_default_remarks())

    def _on_frequency_received(self, rig_name: str, dial_freq: int) -> None:
        """Handle frequency received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            frequency_mhz = dial_freq / 1000000
            print(f"[StatRep] Frequency received from {rig_name}: {frequency_mhz:.3f} MHz")
            if hasattr(self, 'freq_field'):
                self.freq_field.setText(f"{frequency_mhz:.3f}")

    def _on_from_field_changed(self, text: str) -> None:
        """Handle user editing the From (callsign) field."""
        self.callsign = text.upper()

    def _on_grid_field_changed(self, text: str) -> None:
        """Handle user editing the Grid field."""
        raw = text.strip()
        formatted = raw.upper()
        self.grid = formatted
        if text != formatted:
            pos = self.grid_field.cursorPosition()
            self.grid_field.blockSignals(True)
            self.grid_field.setText(formatted)
            self.grid_field.blockSignals(False)
            self.grid_field.setCursorPosition(pos)

    def _generate_statrep_id(self) -> None:
        """Generate a time-based StatRep ID from current UTC time."""
        if not self.statrep_id:
            from id_utils import generate_time_based_id
            self.statrep_id = generate_time_based_id()

    def _setup_ui(self) -> None:
        """Build the user interface."""
        self.setStyleSheet(f"""
            QDialog {{ background-color: {self.panel_background}; }}
            QLabel {{ color: #333333; }}
            QLineEdit {{ background-color: white; color: #333333; border: 1px solid #cccccc; border-radius: 4px; padding: 2px 4px; }}
            QComboBox {{ background-color: white; color: #333333; border: 1px solid #cccccc; border-radius: 4px; padding: 2px 4px; }}
            QComboBox:disabled {{ background-color: #e9ecef; color: #999999; border: 1px solid #cccccc; }}
            QComboBox QAbstractItemView {{ background-color: white; color: #333333; selection-background-color: #0078d7; selection-color: white; }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QtWidgets.QLabel("CommStat Status Report 5.1")
        title.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 10px;")
        layout.addWidget(title)

        # Rig / Mode / Freq / Delivery row (label above control)
        rig_row = QtWidgets.QHBoxLayout()

        rig_col = QtWidgets.QVBoxLayout()
        rig_label = QtWidgets.QLabel("Rig:")
        rig_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.rig_combo.setMinimumWidth(180)
        self.rig_combo.setMinimumHeight(28)
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        rig_col.addWidget(rig_label)
        rig_col.addWidget(self.rig_combo)
        rig_row.addLayout(rig_col)

        mode_col = QtWidgets.QVBoxLayout()
        mode_label = QtWidgets.QLabel("Mode:")
        mode_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo.setMinimumHeight(28)
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_col.addWidget(mode_label)
        mode_col.addWidget(self.mode_combo)
        rig_row.addLayout(mode_col)

        freq_col = QtWidgets.QVBoxLayout()
        freq_label = QtWidgets.QLabel("Freq:")
        freq_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field.setMinimumHeight(28)
        self.freq_field.setMaximumWidth(100)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet("background-color: #f0f0f0;")
        freq_col.addWidget(freq_label)
        freq_col.addWidget(self.freq_field)
        rig_row.addLayout(freq_col)

        delivery_col = QtWidgets.QVBoxLayout()
        delivery_label = QtWidgets.QLabel("Delivery:")
        delivery_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.delivery_combo = QtWidgets.QComboBox()
        self.delivery_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.delivery_combo.setMinimumHeight(28)
        self.delivery_combo.addItem("Maximum Reach")
        self.delivery_combo.addItem("Limited Reach")
        self.delivery_combo.currentTextChanged.connect(self._on_delivery_changed)
        delivery_col.addWidget(delivery_label)
        delivery_col.addWidget(self.delivery_combo)
        rig_row.addLayout(delivery_col)

        rig_row.addStretch()
        layout.addLayout(rig_row)

        # Header info (From, To, Grid, Scope) - all on one line
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(10)

        # From (Callsign)
        from_layout = QtWidgets.QVBoxLayout()
        from_label = QtWidgets.QLabel("From:")
        from_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.from_field = QtWidgets.QLineEdit(self.callsign)
        self.from_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.from_field.setMinimumHeight(28)
        self.from_field.textChanged.connect(self._on_from_field_changed)
        make_uppercase(self.from_field)
        from_layout.addWidget(from_label)
        from_layout.addWidget(self.from_field)
        header_layout.addLayout(from_layout)

        # To (Group) - dropdown with all groups
        # Auto-selects only if exactly 1 group exists.
        # If multiple groups exist, user must select one.
        to_layout = QtWidgets.QVBoxLayout()
        to_label = QtWidgets.QLabel("To:")
        to_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.to_combo = QtWidgets.QComboBox()
        self.to_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.to_combo.setMinimumHeight(28)
        # Populate with all groups
        all_groups = self._get_all_groups_from_db()
        if len(all_groups) == 1:
            # Exactly 1 group - auto-select it
            self.to_combo.addItem(all_groups[0])
        else:
            # Multiple groups or no groups - require user selection
            self.to_combo.addItem("")  # Empty first item
            for group in all_groups:
                self.to_combo.addItem(group)
        to_layout.addWidget(to_label)
        to_layout.addWidget(self.to_combo)
        header_layout.addLayout(to_layout)

        # Grid
        grid_layout = QtWidgets.QVBoxLayout()
        grid_label = QtWidgets.QLabel("Grid:")
        grid_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.grid_field = QtWidgets.QLineEdit(self.grid)
        self.grid_field.setMaxLength(6)
        self.grid_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.grid_field.setMinimumHeight(28)
        self.grid_field.textChanged.connect(self._on_grid_field_changed)
        grid_layout.addWidget(grid_label)
        grid_layout.addWidget(self.grid_field)
        header_layout.addLayout(grid_layout)

        # Scope
        scope_layout = QtWidgets.QVBoxLayout()
        scope_label = QtWidgets.QLabel("Scope:")
        scope_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.scope_combo.setMinimumHeight(28)
        for display, code in SCOPE_OPTIONS:
            self.scope_combo.addItem(display, code)
        scope_layout.addWidget(scope_label)
        scope_layout.addWidget(self.scope_combo)
        header_layout.addLayout(scope_layout)

        layout.addLayout(header_layout)

        # Legend
        legend = QtWidgets.QLabel(
            "<b>Maximum Reach</b> = RF + Internet | <b>Limited Reach</b> = RF Only"
            "<br><b>Green</b> = Normal | "
            "<b>Yellow</b> = Limited | "
            "<b>Red</b> = Collapsed/None"
        )
        legend.setAlignment(Qt.AlignCenter)
        legend.setFont(QtGui.QFont(FONT_FAMILY, 10))
        legend.setStyleSheet(
            "background-color: #f8f9fa; padding: 8px; border-radius: 4px; margin: 5px 0;"
        )
        layout.addWidget(legend)

        # Status grid (4 columns x 3 rows)
        status_grid = QtWidgets.QGridLayout()
        status_grid.setSpacing(10)

        for i, (label, name) in enumerate(STATUS_CATEGORIES):
            label_row = (i // 4) * 2
            combo_row = label_row + 1
            col = i % 4

            cell_label = QtWidgets.QLabel(label)
            cell_label.setFont(QtGui.QFont(FONT_FAMILY, 12))
            cell_label.setAlignment(Qt.AlignCenter)
            status_grid.addWidget(cell_label, label_row, col)

            combo = self._create_status_combo()
            self.status_combos[name] = combo
            status_grid.addWidget(combo, combo_row, col)

        layout.addLayout(status_grid)

        # Remarks
        remarks_layout = QtWidgets.QVBoxLayout()
        remarks_label = QtWidgets.QLabel("Remarks:")
        remarks_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))

        # Single-line remarks (default, for radio)
        self.remarks_field = QtWidgets.QLineEdit()
        self.remarks_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.remarks_field.setMinimumHeight(36)
        self.remarks_field.setMaxLength(REMARKS_MAX_RADIO)
        self.remarks_field.setPlaceholderText(f"Optional - max {REMARKS_MAX_RADIO} characters")
        self.remarks_field.setText(self._get_default_remarks())

        # Multi-line remarks (for Internet Only, hidden by default)
        self.remarks_expanded = QtWidgets.QPlainTextEdit()
        self.remarks_expanded.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.remarks_expanded.setFixedHeight(110)  # ~5 lines
        self.remarks_expanded.setPlaceholderText(f"Optional - max {REMARKS_MAX_INTERNET} characters, multiple lines allowed")
        self.remarks_expanded.hide()

        remarks_layout.addWidget(remarks_label)
        remarks_layout.addWidget(self.remarks_field)
        remarks_layout.addWidget(self.remarks_expanded)
        layout.addLayout(remarks_layout)

        # Spacer
        layout.addStretch()

        # Buttons — two rows sharing the same 5-column grid so widths align
        btn_grid = QtWidgets.QGridLayout()
        btn_grid.setSpacing(10)
        for col in range(5):
            btn_grid.setColumnStretch(col, 1)

        # Row 0: Grid Finder (col 3) and Brevity (col 4)
        btn_grid_finder = QtWidgets.QPushButton("Grid Finder")
        btn_grid_finder.clicked.connect(self._on_grid_finder)
        btn_grid_finder.setStyleSheet(self._button_style("#28a745"))
        btn_grid.addWidget(btn_grid_finder, 0, 3)

        btn_brevity = QtWidgets.QPushButton("Brevity")
        btn_brevity.clicked.connect(self._on_brevity)
        btn_brevity.setStyleSheet(self._button_style("#6f42c1"))
        btn_grid.addWidget(btn_brevity, 0, 4)

        # Row 1: all five main buttons
        btn_all_green = QtWidgets.QPushButton("All Green")
        btn_all_green.clicked.connect(self._on_all_green)
        btn_all_green.setStyleSheet(self._button_style("#28a745"))
        btn_grid.addWidget(btn_all_green, 1, 0)

        btn_all_gray = QtWidgets.QPushButton("All Gray")
        btn_all_gray.clicked.connect(self._on_all_gray)
        btn_all_gray.setStyleSheet(self._button_style("#6c757d"))
        btn_grid.addWidget(btn_all_gray, 1, 1)

        btn_save = QtWidgets.QPushButton("Save Only")
        btn_save.clicked.connect(self._on_save_only)
        btn_save.setStyleSheet(self._button_style("#17a2b8"))
        btn_grid.addWidget(btn_save, 1, 2)

        btn_transmit = QtWidgets.QPushButton("Transmit")
        btn_transmit.clicked.connect(self._on_transmit)
        btn_transmit.setStyleSheet(self._button_style("#007bff"))
        btn_grid.addWidget(btn_transmit, 1, 3)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_cancel.setStyleSheet(self._button_style("#dc3545"))
        btn_grid.addWidget(btn_cancel, 1, 4)

        layout.addLayout(btn_grid)

    def _create_status_combo(self) -> QComboBox:
        """Create a status dropdown with color-coded options."""
        combo = QtWidgets.QComboBox()
        combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        combo.setMinimumWidth(130)
        combo.setMinimumHeight(28)

        for display, code in STATUS_OPTIONS:
            combo.addItem(display, code)

        # Update color when selection changes
        combo.currentTextChanged.connect(
            lambda text, c=combo: self._update_combo_color(c, text)
        )

        return combo

    def _update_combo_color(self, combo: QComboBox, text: str) -> None:
        """Update combo box background color based on selection."""
        color = STATUS_COLORS.get(text, "#ffffff")
        if text in ("Green", "Yellow", "Red", "Unknown"):
            text_color = "#000" if text == "Yellow" else "#fff"
            combo.setStyleSheet(
                f"background-color: {color}; color: {text_color}; font-weight: bold;"
            )
        else:
            combo.setStyleSheet("")

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
                font-size: 11pt;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _show_info(self, message: str) -> None:
        """Display an info message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat")
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate(self) -> bool:
        """Validate all form fields. Returns True if valid."""
        # Check rig is selected
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == "":
            self._show_error("Please select a Rig")
            self.rig_combo.setFocus()
            return False

        # Check group is selected
        group_name = self.to_combo.currentText()
        if not group_name or group_name == "":
            self._show_error("Please select a Group")
            self.to_combo.setFocus()
            return False

        # Check all status fields are selected
        for label, name in STATUS_CATEGORIES:
            combo = self.status_combos[name]
            if not combo.currentData():
                self._show_error(f"Please select a status for '{label}'")
                combo.setFocus()
                return False

        # Check grid format
        grid = self.grid.strip()
        if not grid or len(grid) not in (4, 6):
            self._show_error("Please enter a valid grid square (4 or 6 characters).")
            self.grid_field.setFocus()
            return False
        grid_upper = grid.upper()
        if not (grid_upper[0] in 'ABCDEFGHIJKLMNOPQR' and
                grid_upper[1] in 'ABCDEFGHIJKLMNOPQR' and
                grid_upper[2].isdigit() and grid_upper[3].isdigit()):
            self._show_error("Please enter a valid Maidenhead grid square (e.g., EM83 or EM83cv).")
            self.grid_field.setFocus()
            return False

        # Check remarks length
        remarks = self._get_remarks_text()
        max_len = REMARKS_MAX_INTERNET if self._is_internet_only() else REMARKS_MAX_RADIO
        if len(remarks) > max_len:
            self._show_error(f"Remarks too long (max {max_len} characters)")
            return False

        return True

    def _get_status_values(self) -> Dict[str, str]:
        """Collect all status values as codes."""
        values = {}
        for _, name in STATUS_CATEGORIES:
            values[name] = self.status_combos[name].currentData() or ""
        return values

    def prefill(self, data: dict) -> None:
        """Pre-populate fields from a previously received statrep for forwarding."""
        _MAP = [
            ("map",       "status"),
            ("power",     "power"),
            ("water",     "water"),
            ("med",       "medical"),
            ("telecom",   "comms"),
            ("travel",    "travel"),
            ("internet",  "internet"),
            ("fuel",      "fuel"),
            ("food",      "food"),
            ("crime",     "crime"),
            ("civil",     "civil"),
            ("political", "political"),
        ]
        for db_key, combo_key in _MAP:
            code = data.get(db_key, "")
            if code:
                combo = self.status_combos[combo_key]
                idx = combo.findData(code)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        if data.get("grid"):
            self.grid_field.setText(data["grid"])

        comments = (data.get("comments") or "").replace("||", "\n")
        self.remarks_field.setText(comments[:self.remarks_field.maxLength()])
        self.remarks_expanded.setPlainText(comments)

        if data.get("sr_id"):
            self.statrep_id = data["sr_id"]

        if data.get("origin_callsign"):
            self._forward_origin = data["origin_callsign"]

    def _set_all_status(self, status_name: str) -> None:
        """Set all status dropdowns to the specified status."""
        for _, name in STATUS_CATEGORIES:
            combo = self.status_combos[name]
            index = combo.findText(status_name)
            if index >= 0:
                combo.setCurrentIndex(index)

    def _on_brevity(self) -> None:
        """Launch Brevity modal over StatRep; Copy Code inserts into remarks field."""
        from brevity import BrevityApp
        self._brevity_window = BrevityApp(self.panel_background, "#333333", parent=self)
        self._brevity_window.setWindowModality(QtCore.Qt.WindowModal)
        self._brevity_window.code_selected.connect(self._on_brevity_code_selected)
        self._brevity_window.show()

    def _on_brevity_code_selected(self, code: str) -> None:
        """Insert selected brevity code into the remarks field and close Brevity."""
        padded = f" {code} "
        if self.remarks_field.isVisible():
            current = self.remarks_field.text()
            self.remarks_field.setText(current + padded)
            self.remarks_field.setCursorPosition(len(self.remarks_field.text()))
        else:
            self.remarks_expanded.insertPlainText(padded)
        if hasattr(self, '_brevity_window'):
            self._brevity_window.close()

    def _on_grid_finder(self) -> None:
        """Launch Grid Finder and wire selected grid back to the grid field."""
        from gridfinder import GridFinderApp
        self._grid_finder = GridFinderApp(
            self.panel_background, "#333333", self.data_background, "#000000", parent=self
        )
        self._grid_finder.setWindowModality(QtCore.Qt.WindowModal)
        self._grid_finder.grid_selected.connect(self._on_grid_finder_selected)
        self._grid_finder.show()

    def _on_grid_finder_selected(self, grid: str) -> None:
        """Receive grid from Grid Finder, populate the grid field, and close the finder."""
        self.grid_field.setText(grid)
        self._on_grid_field_changed(grid)
        if hasattr(self, '_grid_finder'):
            self._grid_finder.close()

    def _on_all_green(self) -> None:
        """Set all statuses to Green."""
        self._set_all_status("Green")

    def _on_all_gray(self) -> None:
        """Set all statuses to Unknown (Gray)."""
        self._set_all_status("Unknown")

    def _build_message(self) -> str:
        """Build the StatRep message string for transmission."""
        values = self._get_status_values()
        scope_code = self.scope_combo.currentData()
        raw_remarks = self._get_remarks_text()
        remarks = raw_remarks

        # Replace newlines with || for storage/transmission
        remarks = remarks.replace('\r\n', NEWLINE_PLACEHOLDER).replace('\n', NEWLINE_PLACEHOLDER).replace('\r', NEWLINE_PLACEHOLDER)

        # Clean remarks - only alphanumeric, spaces, hyphens, asterisks, and pipe chars
        remarks = re.sub(r"[^A-Za-z0-9*\-\s|.?!'/:()#@+=&]+", " ", remarks)

        # Build status string (all 12 values concatenated)
        status_str = "".join([
            values["status"],
            values["power"],
            values["water"],
            values["medical"],
            values["comms"],
            values["travel"],
            values["internet"],
            values["fuel"],
            values["food"],
            values["crime"],
            values["civil"],
            values["political"],
        ])

        # Compress all-green status to "+" to save bandwidth
        if status_str == "111111111111":
            status_str = "+"

        # Format: CALLSIGN: @GROUP ,GRID,SCOPE,ID,STATUSES,REMARKS,{&%}
        group = f"@{self.to_combo.currentText()}"
        if getattr(self, "_forward_origin", None):
            marker = "{F%}"
            message = f"{self.callsign.upper()}: {group} ,{self.grid},{scope_code},{self.statrep_id},{status_str},{remarks},{self._forward_origin},{marker}"
        else:
            marker = "{&%3}" if self.rig_combo.currentText() == INTERNET_RIG else "{&%}"
            message = f"{self.callsign.upper()}: {group} ,{self.grid},{scope_code},{self.statrep_id},{status_str},{remarks},{marker}"

        return message

    def _save_to_database(self, frequency: int = 0) -> None:
        """Save StatRep to database.

        Args:
            frequency: The frequency in Hz at the time of transmission.
        """
        values = self._get_status_values()
        scope_text = self.scope_combo.currentText()
        remarks = self._get_remarks_text()

        # Replace newlines with || for storage
        remarks = remarks.replace('\r\n', NEWLINE_PLACEHOLDER).replace('\n', NEWLINE_PLACEHOLDER).replace('\r', NEWLINE_PLACEHOLDER)
        remarks = re.sub(r"[^A-Za-z0-9*\-\s|.?!'/:()#@+=&]+", " ", remarks)

        now = QDateTime.currentDateTimeUtc()
        date = now.toString("yyyy-MM-dd HH:mm:ss")
        date_only = now.toString("yyyy-MM-dd")

        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO statrep(
                        datetime, date, freq, db, source, sr_id, from_callsign, target, grid, scope,
                        map, power, water, med, telecom, travel, internet,
                        fuel, food, crime, civil, political, comments
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    date_only,
                    frequency,
                    30,  # db (SNR): set to 30 for manual entries
                    3 if self.rig_combo.currentText() == INTERNET_RIG else 1,  # source: 1=Radio, 3=Internet
                    self.statrep_id,
                    self.callsign.upper(),
                    '@' + self.to_combo.currentText().upper(),
                    self.grid.upper(),
                    scope_text,
                    values["status"],      # -> map column
                    values["power"],       # -> power column
                    values["water"],       # -> water column
                    values["medical"],     # -> med column
                    values["comms"],       # -> telecom column
                    values["travel"],      # -> travel column
                    values["internet"],    # -> internet column
                    values["fuel"],        # -> fuel column
                    values["food"],        # -> food column
                    values["crime"],       # -> crime column
                    values["civil"],       # -> civil column
                    values["political"],   # -> political column
                    remarks,
                ))
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database error saving StatRep: {e}")
            raise

    def _refresh_parent_data(self) -> None:
        """Refresh the parent window's StatRep table, map, and messages."""
        parent = self.parent()
        if parent:
            if hasattr(parent, '_load_statrep_data'):
                parent._load_statrep_data()
            if hasattr(parent, '_load_map'):
                parent._load_map()
            if hasattr(parent, '_load_message_data'):
                parent._load_message_data()

    def _on_save_only(self) -> None:
        """Validate and save without transmitting."""
        self._generate_statrep_id()
        if not self._validate():
            return

        try:
            self._save_to_database()
            message = self._build_message()

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"STATREP SAVED - {now} UTC")
            print(f"{'='*60}")
            print(f"  ID:       {self.statrep_id}")
            print(f"  To:       {self.to_combo.currentText()}")
            print(f"  From:     {self.callsign}")
            print(f"  Grid:     {self.grid}")
            print(f"  Scope:    {self.scope_combo.currentText()}")
            print(f"  Message:  {message}")
            print(f"{'='*60}\n")

            self._show_info(f"StatRep saved:\n{message}")
            self._refresh_parent_data()
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to save StatRep: {e}")

    def _on_transmit(self) -> None:
        """Validate, check for selected call, get frequency, transmit, and save."""
        self._generate_statrep_id()
        if not self._validate():
            return

        rig_name = self.rig_combo.currentText()

        if rig_name == INTERNET_RIG:
            callsign, _, _ = self._get_internet_user_settings()
            if not callsign:
                self._show_error(
                    "No callsign configured.\n\nPlease set your callsign in Settings → User Settings."
                )
                return
            self.callsign = callsign
            self._pending_message = self._build_message()
            self._save_to_database(0)
            self._submit_to_backbone_async(0)
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"STATREP TRANSMITTED (Internet) - {now} UTC")
            print(f"{'='*60}")
            print(f"  ID:       {self.statrep_id}")
            print(f"  To:       {self.to_combo.currentText()}")
            print(f"  From:     {self.callsign}")
            print(f"  Grid:     {self.grid}")
            print(f"  Scope:    {self.scope_combo.currentText()}")
            print(f"  Message:  {self._pending_message}")
            print(f"{'='*60}\n")
            self._refresh_parent_data()
            self.accept()
            return

        if "(disconnected)" in rig_name:
            self._show_error("Cannot transmit: rig is disconnected")
            return

        client = self.tcp_pool.get_client(rig_name)
        if not client or not client.is_connected():
            self._show_error("Cannot transmit: not connected to rig")
            return

        # Store the message to transmit
        self._pending_message = self._build_message()

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
                self, "ERROR",
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
            self._save_to_database(frequency)

            # Submit to backbone server (asynchronous, non-blocking)
            if self.delivery_combo.currentText() != "Limited Reach":
                self._submit_to_backbone_async(frequency)

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            freq_mhz = frequency / 1000000.0 if frequency else 0
            print(f"\n{'='*60}")
            print(f"STATREP TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  ID:       {self.statrep_id}")
            print(f"  To:       {self.to_combo.currentText()}")
            print(f"  From:     {self.callsign}")
            print(f"  Grid:     {self.grid}")
            print(f"  Scope:    {self.scope_combo.currentText()}")
            print(f"  Freq:     {freq_mhz:.6f} MHz")
            print(f"  Message:  {self._pending_message}")
            print(f"{'='*60}\n")

            self._refresh_parent_data()
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to transmit StatRep: {e}")


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

    dialog = StatRepDialog(tcp_pool, connector_manager)
    dialog.show()
    sys.exit(app.exec_())
