# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Net Check-In Dialog for CommStat
Allows sending net check-in messages via JS8Call.
"""

import os
from configparser import ConfigParser
from typing import TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# =============================================================================
# Constants
# =============================================================================

CONFIG_FILE = "config.ini"
DATABASE_FILE = "traffic.db3"

FONT_FAMILY = "Arial"
FONT_SIZE = 12
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 380


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


def get_state_from_config() -> str:
    """Get the state abbreviation from config.ini."""
    try:
        config = ConfigParser()
        config.read(CONFIG_FILE)
        if config.has_option("STATION", "state"):
            return config.get("STATION", "state").strip().upper()
    except Exception:
        pass
    return ""


def get_active_group_from_db() -> str:
    """Get the first active group from the database."""
    import sqlite3
    try:
        with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM groups WHERE is_active = 1 ORDER BY name LIMIT 1"
            )
            result = cursor.fetchone()
            return result[0] if result else ""
    except Exception:
        return ""


# =============================================================================
# NetCheckInDialog
# =============================================================================

class NetCheckInDialog(QDialog):
    """Net Check-In form for sending check-in messages via JS8Call."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None,
        parent=None
    ):
        super().__init__(parent)
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager

        self.setWindowTitle("CommStat Net Check-In")
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

        # Build UI
        self._setup_ui()

        # Load rigs and populate fields
        self._load_rigs()
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default values from config and database."""
        # Load state from config
        state = get_state_from_config()
        if state:
            self.state_field.setText(state)

        # Load active group
        group = get_active_group_from_db()
        if group:
            self.group_field.setText(group)

    def _load_rigs(self) -> None:
        """Load connected rigs into the rig dropdown."""
        if not self.tcp_pool:
            return

        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        connected_rigs = self.tcp_pool.get_connected_rig_names()

        if not connected_rigs:
            all_rigs = self.tcp_pool.get_all_rig_names()
            if all_rigs:
                self.rig_combo.addItem("")
                for rig_name in all_rigs:
                    self.rig_combo.addItem(f"{rig_name} (disconnected)")
        elif len(connected_rigs) == 1:
            self.rig_combo.addItem(connected_rigs[0])
        else:
            self.rig_combo.addItem("")
            for rig_name in connected_rigs:
                self.rig_combo.addItem(rig_name)

        self.rig_combo.blockSignals(False)

        current_text = self.rig_combo.currentText()
        if current_text and "(disconnected)" not in current_text:
            self._on_rig_changed(current_text)

    def _setup_ui(self) -> None:
        """Build the user interface."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QtWidgets.QLabel("CommStat Net Check-In")
        title.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont(FONT_FAMILY, 16, QtGui.QFont.Bold)
        title.setFont(title_font)
        title.setStyleSheet("color: #333; margin-bottom: 5px;")
        layout.addWidget(title)

        # Rig selection row
        rig_layout = QtWidgets.QHBoxLayout()
        rig_label = QtWidgets.QLabel("Rig:")
        rig_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.rig_combo = QtWidgets.QComboBox()
        self.rig_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.rig_combo.setMinimumWidth(150)
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)
        rig_layout.addWidget(rig_label)
        rig_layout.addWidget(self.rig_combo)

        # Mode dropdown
        mode_label = QtWidgets.QLabel("Mode:")
        mode_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.mode_combo.addItem("Slow", 3)
        self.mode_combo.addItem("Normal", 0)
        self.mode_combo.addItem("Fast", 1)
        self.mode_combo.addItem("Turbo", 2)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        rig_layout.addWidget(mode_label)
        rig_layout.addWidget(self.mode_combo)

        # Frequency field
        freq_label = QtWidgets.QLabel("Freq:")
        freq_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field = QtWidgets.QLineEdit()
        self.freq_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.freq_field.setMaximumWidth(80)
        self.freq_field.setReadOnly(True)
        self.freq_field.setStyleSheet("background-color: #f0f0f0;")
        rig_layout.addWidget(freq_label)
        rig_layout.addWidget(self.freq_field)
        rig_layout.addStretch()
        layout.addLayout(rig_layout)

        # Input field style
        input_style = "padding: 8px;"

        # Group field
        group_layout = QtWidgets.QHBoxLayout()
        group_label = QtWidgets.QLabel("Group:")
        group_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        group_label.setMinimumWidth(80)
        self.group_field = QtWidgets.QLineEdit()
        self.group_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.group_field.setMinimumHeight(36)
        self.group_field.setStyleSheet(input_style)
        self.group_field.setMaxLength(15)
        self.group_field.setPlaceholderText("Group name (e.g., AMRRON)")
        make_uppercase(self.group_field)
        group_layout.addWidget(group_label)
        group_layout.addWidget(self.group_field)
        layout.addLayout(group_layout)

        # Traffic field
        traffic_layout = QtWidgets.QHBoxLayout()
        traffic_label = QtWidgets.QLabel("Traffic:")
        traffic_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        traffic_label.setMinimumWidth(80)
        self.traffic_field = QtWidgets.QLineEdit()
        self.traffic_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.traffic_field.setMinimumHeight(36)
        self.traffic_field.setStyleSheet(input_style)
        self.traffic_field.setMaxLength(20)
        self.traffic_field.setText("NTR")  # Default: No Traffic to Report
        self.traffic_field.setPlaceholderText("NTR = No Traffic to Report")
        make_uppercase(self.traffic_field)
        traffic_layout.addWidget(traffic_label)
        traffic_layout.addWidget(self.traffic_field)
        layout.addLayout(traffic_layout)

        # State field
        state_layout = QtWidgets.QHBoxLayout()
        state_label = QtWidgets.QLabel("State:")
        state_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        state_label.setMinimumWidth(80)
        self.state_field = QtWidgets.QLineEdit()
        self.state_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.state_field.setMinimumHeight(36)
        self.state_field.setStyleSheet(input_style)
        self.state_field.setMaxLength(2)
        self.state_field.setPlaceholderText("2-letter state code")
        make_uppercase(self.state_field)
        state_layout.addWidget(state_label)
        state_layout.addWidget(self.state_field)
        layout.addLayout(state_layout)

        # Grid field
        grid_layout = QtWidgets.QHBoxLayout()
        grid_label = QtWidgets.QLabel("Grid:")
        grid_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        grid_label.setMinimumWidth(80)
        self.grid_field = QtWidgets.QLineEdit()
        self.grid_field.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        self.grid_field.setMinimumHeight(36)
        self.grid_field.setStyleSheet(input_style)
        self.grid_field.setMaxLength(6)
        self.grid_field.setPlaceholderText("4 or 6 char grid (e.g., EM15ab)")
        make_uppercase(self.grid_field)
        grid_layout.addWidget(grid_label)
        grid_layout.addWidget(self.grid_field)
        layout.addLayout(grid_layout)

        # Note
        note = QtWidgets.QLabel(
            "Check-in format: @GROUP ,TRAFFIC,STATE,GRID,{~%}\n"
            "NTR = No Traffic to Report"
        )
        note.setAlignment(Qt.AlignCenter)
        note.setFont(QtGui.QFont(FONT_FAMILY, 10))
        note.setStyleSheet(
            "color: #856404; background-color: #fff3cd; "
            "padding: 10px; border-radius: 4px;"
        )
        layout.addWidget(note)

        # Spacer
        layout.addStretch()

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        btn_transmit = QtWidgets.QPushButton("Transmit")
        btn_transmit.clicked.connect(self._on_transmit)
        btn_transmit.setStyleSheet(self._button_style("#007bff"))
        btn_transmit.setMinimumWidth(100)
        button_layout.addWidget(btn_transmit)

        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        btn_cancel.setStyleSheet(self._button_style("#dc3545"))
        btn_cancel.setMinimumWidth(100)
        button_layout.addWidget(btn_cancel)

        layout.addLayout(button_layout)

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
        """

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - update mode/frequency and grid."""
        if not rig_name or "(disconnected)" in rig_name:
            self.freq_field.setText("")
            return

        if not self.tcp_pool:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Update mode dropdown
            speed_name = (client.speed_name or "").upper()
            mode_map = {"SLOW": 0, "NORMAL": 1, "FAST": 2, "TURBO": 3}
            idx = mode_map.get(speed_name, 1)
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(idx)
            self.mode_combo.blockSignals(False)

            # Update frequency
            frequency = client.frequency
            if frequency:
                self.freq_field.setText(f"{frequency:.3f}")
            else:
                self.freq_field.setText("")

            # Update grid from JS8Call if available
            grid = client.grid
            if grid and not self.grid_field.text():
                self.grid_field.setText(grid.upper())
        else:
            self.freq_field.setText("")

    def _on_mode_changed(self, index: int) -> None:
        """Handle mode dropdown change - send MODE.SET_SPEED to JS8Call."""
        rig_name = self.rig_combo.currentText()
        if not rig_name or "(disconnected)" in rig_name:
            return

        if not self.tcp_pool:
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            speed_value = self.mode_combo.currentData()
            client.send_message("MODE.SET_SPEED", "", {"SPEED": speed_value})
            print(f"[NetCheckIn] Set mode to {self.mode_combo.currentText()} (speed={speed_value})")

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _validate(self) -> bool:
        """Validate form fields. Returns True if valid."""
        group = self.group_field.text().strip()
        traffic = self.traffic_field.text().strip()
        state = self.state_field.text().strip()
        grid = self.grid_field.text().strip()

        if not group:
            self._show_error("Please enter a group name.")
            self.group_field.setFocus()
            return False

        if not traffic:
            self._show_error("Please enter traffic status (e.g., NTR).")
            self.traffic_field.setFocus()
            return False

        if len(state) != 2:
            self._show_error("Please enter a valid 2-letter state code.")
            self.state_field.setFocus()
            return False

        if len(grid) < 4:
            self._show_error("Please enter a valid grid square (4 or 6 characters).")
            self.grid_field.setFocus()
            return False

        return True

    def _on_transmit(self) -> None:
        """Validate and transmit the check-in."""
        if not self._validate():
            return

        rig_name = self.rig_combo.currentText()
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

        group = self.group_field.text().strip()
        traffic = self.traffic_field.text().strip()
        state = self.state_field.text().strip()
        grid = self.grid_field.text().strip()

        # Build message: @GROUP ,TRAFFIC,STATE,GRID,{~%}
        self._pending_message = f"@{group} ,{traffic},{state},{grid},{{~%}}"
        self._pending_group = group
        self._pending_traffic = traffic
        self._pending_state = state
        self._pending_grid = grid

        # Check if a call is selected in JS8Call
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
            QMessageBox.critical(
                self, "ERROR",
                f"JS8Call has {selected_call} selected.\n\n"
                "Go to JS8Call and click the \"Deselect\" button."
            )
            return

        # No call selected - proceed with transmission
        try:
            client.send_tx_message(self._pending_message)

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"NET CHECK-IN TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  Rig:      {rig_name}")
            print(f"  Group:    {self._pending_group}")
            print(f"  Traffic:  {self._pending_traffic}")
            print(f"  State:    {self._pending_state}")
            print(f"  Grid:     {self._pending_grid}")
            print(f"  Full TX:  {self._pending_message}")
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

    # Initialize dependencies
    connector_manager = ConnectorManager()
    connector_manager.init_connectors_table()
    tcp_pool = TCPConnectionPool(connector_manager)
    tcp_pool.connect_all()

    dialog = NetCheckInDialog(tcp_pool, connector_manager)
    dialog.show()
    sys.exit(app.exec_())
