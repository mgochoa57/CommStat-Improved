# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
StatRep Dialog for CommStat-Improved
Allows creating and transmitting AMRRON Status Reports via JS8Call.
"""

import os
import re
import random
import sqlite3
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
CONFIG_FILE = "config.ini"
GRID_CSV_FILE = "GridSearchData1_preprocessed.csv"

# Cache for grid-to-state mapping (loaded on first use)
_grid_to_state_cache: dict = {}


def _load_grid_to_state_mapping() -> dict:
    """Load grid-to-state mapping from CSV file.

    Returns a dict mapping 4-character grid prefixes to state abbreviations.
    """
    global _grid_to_state_cache
    if _grid_to_state_cache:
        return _grid_to_state_cache

    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, GRID_CSV_FILE)

    if not os.path.exists(csv_path):
        print(f"[StatRep] Grid CSV not found: {csv_path}")
        return {}

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            next(f)  # Skip header
            for line in f:
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    state = parts[1].strip().strip('"')
                    grid = parts[2].strip().strip('"')
                    if len(grid) >= 4 and len(state) == 2:
                        grid_prefix = grid[:4].upper()
                        if grid_prefix not in _grid_to_state_cache:
                            _grid_to_state_cache[grid_prefix] = state.upper()
        print(f"[StatRep] Loaded {len(_grid_to_state_cache)} grid-to-state mappings")
    except Exception as e:
        print(f"[StatRep] Error loading grid CSV: {e}")

    return _grid_to_state_cache


def get_state_from_grid(grid: str) -> str:
    """Get US state abbreviation from a Maidenhead grid square.

    Args:
        grid: 4 or 6 character Maidenhead grid (e.g., "EM79" or "EM79qk")

    Returns:
        2-letter state abbreviation (e.g., "MI") or empty string if not found.
    """
    if not grid or len(grid) < 4:
        return ""

    mapping = _load_grid_to_state_mapping()
    grid_prefix = grid[:4].upper()
    return mapping.get(grid_prefix, "")

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
FONT_SIZE = 10
WINDOW_WIDTH = 700
WINDOW_HEIGHT = 580


# =============================================================================
# StatRep Dialog
# =============================================================================

class StatRepDialog(QDialog):
    """Modern StatRep form for creating and transmitting status reports."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool",
        connector_manager: "ConnectorManager",
        parent=None
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager

        self.setWindowTitle("CommStat-Improved STATREP")
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

        # Load config and generate ID
        self._load_config()
        self._generate_statrep_id()

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
                cursor.execute("SELECT name FROM Groups WHERE is_active = 1")
                result = cursor.fetchone()
                if result:
                    return result[0]
        except sqlite3.Error as e:
            print(f"Error reading active group from database: {e}")
        return ""

    def _get_default_remarks(self) -> str:
        """Get default remarks with state prefix derived from grid."""
        state = get_state_from_grid(self.grid)
        if state:
            return f"{state} - NTR"
        return "NTR"

    def _get_all_groups_from_db(self) -> list:
        """Get all groups from the database."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM Groups ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Error reading groups from database: {e}")
        return []

    def _load_rigs(self) -> None:
        """Load connected rigs into the rig dropdown."""
        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        # Add all connected rigs
        connected_rigs = self.tcp_pool.get_connected_rig_names()
        for rig_name in connected_rigs:
            self.rig_combo.addItem(rig_name)

        # If no connected rigs, add all configured rigs (disconnected)
        if not connected_rigs:
            all_rigs = self.tcp_pool.get_all_rig_names()
            for rig_name in all_rigs:
                self.rig_combo.addItem(f"{rig_name} (disconnected)")

        # Select default rig
        default = self.connector_manager.get_default_connector()
        if default:
            idx = self.rig_combo.findText(default["rig_name"])
            if idx >= 0:
                self.rig_combo.setCurrentIndex(idx)

        self.rig_combo.blockSignals(False)

        # Trigger rig changed to load callsign/grid
        if self.rig_combo.count() > 0:
            self._on_rig_changed(self.rig_combo.currentText())

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - fetch callsign and grid from JS8Call."""
        if not rig_name or "(disconnected)" in rig_name:
            self.callsign = ""
            self.grid = ""
            if hasattr(self, 'from_field'):
                self.from_field.setText("")
                self.grid_field.setText("")
            return

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

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Connect signals for this client
            client.callsign_received.connect(self._on_callsign_received)
            client.grid_received.connect(self._on_grid_received)

            # Request callsign and grid from JS8Call
            # Small delay between requests to avoid race condition
            print(f"[StatRep] Requesting callsign and grid from {rig_name}")
            client.get_callsign()
            QtCore.QTimer.singleShot(100, client.get_grid)  # 100ms delay for grid request
        else:
            print(f"[StatRep] Client not available or not connected for {rig_name}")

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
                self.remarks_field.setText(self._get_default_remarks())

    def _on_from_field_changed(self, text: str) -> None:
        """Handle user editing the From (callsign) field."""
        self.callsign = text.upper()

    def _on_grid_field_changed(self, text: str) -> None:
        """Handle user editing the Grid field."""
        self.grid = text.upper()

    def _generate_statrep_id(self) -> None:
        """Generate a unique StatRep ID that doesn't exist in the database."""
        self.statrep_id = str(random.randint(100, 999))

        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT SRid FROM StatRep_Data")
                existing_ids = [str(row[0]) for row in cursor.fetchall()]

                while self.statrep_id in existing_ids:
                    self.statrep_id = str(random.randint(100, 999))

        except sqlite3.Error as e:
            print(f"Database error generating StatRep ID: {e}")

    def _setup_ui(self) -> None:
        """Build the user interface."""
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

        # Rig selection
        rig_layout = QtWidgets.QHBoxLayout()
        rig_label = QtWidgets.QLabel("Rig:")
        rig_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.rig_combo.setMinimumWidth(180)
        self.rig_combo.setMinimumHeight(28)
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        rig_layout.addWidget(rig_label)
        rig_layout.addWidget(self.rig_combo)
        rig_layout.addStretch()
        layout.addLayout(rig_layout)

        # Header info (From, To, Grid, Scope) - all on one line
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(10)

        # From (Callsign)
        from_layout = QtWidgets.QVBoxLayout()
        from_label = QtWidgets.QLabel("From:")
        from_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.from_field = QtWidgets.QLineEdit(self.callsign)
        self.from_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.from_field.setMinimumHeight(28)
        self.from_field.textChanged.connect(self._on_from_field_changed)
        from_layout.addWidget(from_label)
        from_layout.addWidget(self.from_field)
        header_layout.addLayout(from_layout)

        # To (Group) - dropdown with all groups
        to_layout = QtWidgets.QVBoxLayout()
        to_label = QtWidgets.QLabel("To:")
        to_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.to_combo = QtWidgets.QComboBox()
        self.to_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.to_combo.setMinimumHeight(28)
        # Populate with all groups
        all_groups = self._get_all_groups_from_db()
        for group in all_groups:
            self.to_combo.addItem(group)
        # Pre-select active group
        if self.selected_group:
            index = self.to_combo.findText(self.selected_group)
            if index >= 0:
                self.to_combo.setCurrentIndex(index)
        to_layout.addWidget(to_label)
        to_layout.addWidget(self.to_combo)
        header_layout.addLayout(to_layout)

        # Grid
        grid_layout = QtWidgets.QVBoxLayout()
        grid_label = QtWidgets.QLabel("Grid:")
        grid_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.grid_field = QtWidgets.QLineEdit(self.grid)
        self.grid_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.grid_field.setMinimumHeight(28)
        self.grid_field.textChanged.connect(self._on_grid_field_changed)
        grid_layout.addWidget(grid_label)
        grid_layout.addWidget(self.grid_field)
        header_layout.addLayout(grid_layout)

        # Scope
        scope_layout = QtWidgets.QVBoxLayout()
        scope_label = QtWidgets.QLabel("Scope:")
        scope_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
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
            "<b>Green</b> = Normal | "
            "<b>Yellow</b> = Limited | "
            "<b>Red</b> = Collapsed/None"
        )
        legend.setAlignment(Qt.AlignCenter)
        legend.setStyleSheet(
            "background-color: #f8f9fa; padding: 8px; border-radius: 4px; margin: 5px 0;"
        )
        layout.addWidget(legend)

        # Status grid (4 columns x 3 rows)
        status_grid = QtWidgets.QGridLayout()
        status_grid.setSpacing(10)

        for i, (label, name) in enumerate(STATUS_CATEGORIES):
            row = i // 4
            col = i % 4

            cell_layout = QtWidgets.QVBoxLayout()
            cell_label = QtWidgets.QLabel(label)
            cell_label.setFont(QtGui.QFont(FONT_FAMILY, 9))
            cell_label.setAlignment(Qt.AlignCenter)

            combo = self._create_status_combo()
            self.status_combos[name] = combo

            cell_layout.addWidget(cell_label)
            cell_layout.addWidget(combo)
            status_grid.addLayout(cell_layout, row, col)

        layout.addLayout(status_grid)

        # Remarks
        remarks_layout = QtWidgets.QVBoxLayout()
        remarks_label = QtWidgets.QLabel("Remarks:")
        remarks_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.remarks_field = QtWidgets.QLineEdit()
        self.remarks_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.remarks_field.setMinimumHeight(36)
        self.remarks_field.setMaxLength(60)
        self.remarks_field.setPlaceholderText("Optional - max 60 characters")
        self.remarks_field.setText(self._get_default_remarks())
        remarks_layout.addWidget(remarks_label)
        remarks_layout.addWidget(self.remarks_field)
        layout.addLayout(remarks_layout)

        # Spacer
        layout.addStretch()

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)

        btn_all_green = QtWidgets.QPushButton("All Green")
        btn_all_green.clicked.connect(self._on_all_green)
        btn_all_green.setStyleSheet(self._button_style("#28a745"))
        button_layout.addWidget(btn_all_green)

        btn_all_gray = QtWidgets.QPushButton("All Gray")
        btn_all_gray.clicked.connect(self._on_all_gray)
        btn_all_gray.setStyleSheet(self._button_style("#6c757d"))
        button_layout.addWidget(btn_all_gray)

        btn_save = QtWidgets.QPushButton("Save Only")
        btn_save.clicked.connect(self._on_save_only)
        btn_save.setStyleSheet(self._button_style("#17a2b8"))
        button_layout.addWidget(btn_save)

        btn_transmit = QtWidgets.QPushButton("Transmit")
        btn_transmit.clicked.connect(self._on_transmit)
        btn_transmit.setStyleSheet(self._button_style("#007bff"))
        button_layout.addWidget(btn_transmit)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_cancel.setStyleSheet(self._button_style("#dc3545"))
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

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
                font-size: 10px;
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
        msg.setWindowTitle("CommStat-Improved Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _show_info(self, message: str) -> None:
        """Display an info message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat-Improved")
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate(self) -> bool:
        """Validate all form fields. Returns True if valid."""
        # Check all status fields are selected
        for label, name in STATUS_CATEGORIES:
            combo = self.status_combos[name]
            if not combo.currentData():
                self._show_error(f"Please select a status for '{label}'")
                combo.setFocus()
                return False

        # Check remarks length
        remarks = self.remarks_field.text().strip()
        if len(remarks) > 60:
            self._show_error("Remarks too long (max 60 characters)")
            return False

        return True

    def _get_status_values(self) -> Dict[str, str]:
        """Collect all status values as codes."""
        values = {}
        for _, name in STATUS_CATEGORIES:
            values[name] = self.status_combos[name].currentData() or ""
        return values

    def _set_all_status(self, status_name: str) -> None:
        """Set all status dropdowns to the specified status."""
        for _, name in STATUS_CATEGORIES:
            combo = self.status_combos[name]
            index = combo.findText(status_name)
            if index >= 0:
                combo.setCurrentIndex(index)

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
        remarks = self.remarks_field.text().strip().upper()

        # Clean remarks - only alphanumeric, spaces, hyphens, asterisks
        remarks = re.sub(r"[^A-Za-z0-9*\-\s]+", " ", remarks)

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

        # TODO: REVERT LATER - Compression disabled for legacy compatibility with CommStatOne
        # When enabled, this compresses all-green status (111111111111) to "+" to save bandwidth
        # Uncomment these lines when Dan's users have upgraded to CommStat-Improved:
        # if status_str == "111111111111":
        #     status_str = "+"

        # Format: @GROUP,GRID,SCOPE,ID,STATUSES,REMARKS{&%}
        # Note: {&%} appended directly to remarks (no comma) for CommStatOne compatibility
        group = f"@{self.to_combo.currentText()}"
        message = f"{group},{self.grid},{scope_code},{self.statrep_id},{status_str},{remarks}{{&%}}"

        return message

    def _save_to_database(self, frequency: int = 0) -> None:
        """Save StatRep to database.

        Args:
            frequency: The frequency in Hz at the time of transmission.
        """
        values = self._get_status_values()
        scope_text = self.scope_combo.currentText()
        remarks = self.remarks_field.text().strip().upper()
        remarks = re.sub(r"[^A-Za-z0-9*\-\s]+", " ", remarks)

        now = QDateTime.currentDateTimeUtc()
        date = now.toString("yyyy-MM-dd HH:mm:ss")

        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO StatRep_Data(
                        datetime, callsign, groupname, grid, SRid, prec,
                        status, commpwr, pubwtr, med, ota, trav, net,
                        fuel, food, crime, civil, political, comments, source, frequency
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    self.callsign.upper(),
                    self.to_combo.currentText().upper(),
                    self.grid.upper(),
                    self.statrep_id,
                    scope_text,
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
                    remarks,
                    "1",  # source: 1=Radio, 2=Internet
                    frequency,
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

    def _clear_copy_file(self) -> None:
        """Clear the copy file to trigger refresh."""
        try:
            with open("copyDIRECTED.TXT", "w") as f:
                f.write("blank line \n")
        except Exception as e:
            print(f"Error clearing copy file: {e}")

    def _on_save_only(self) -> None:
        """Validate and save without transmitting."""
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
            self._clear_copy_file()
            self._refresh_parent_data()
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to save StatRep: {e}")

    def _on_transmit(self) -> None:
        """Validate, get frequency, transmit, and save."""
        if not self._validate():
            return

        rig_name = self.rig_combo.currentText()
        if "(disconnected)" in rig_name:
            self._show_error("Cannot transmit: rig is disconnected")
            return

        client = self.tcp_pool.get_client(rig_name)
        if not client or not client.is_connected():
            self._show_error("Cannot transmit: not connected to rig")
            return

        # Connect frequency signal and request frequency
        try:
            client.frequency_received.disconnect(self._on_frequency_for_transmit)
        except TypeError:
            pass
        client.frequency_received.connect(self._on_frequency_for_transmit)

        # Store the message to transmit after we get frequency
        self._pending_message = self._build_message()
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

            self._clear_copy_file()
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
