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
from typing import Optional, Dict, List
from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox, QDialog, QComboBox
import js8callAPIsupport


# =============================================================================
# Constants
# =============================================================================

DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"

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
WINDOW_WIDTH = 520
WINDOW_HEIGHT = 480


# =============================================================================
# StatRep Dialog
# =============================================================================

class StatRepDialog(QDialog):
    """Modern StatRep form for creating and transmitting status reports."""

    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.server_ip = "127.0.0.1"
        self.server_port = "2242"
        self.callsign = ""
        self.grid = ""
        self.selected_group = ""
        self.statrep_id = ""

        # Status combo boxes
        self.status_combos: Dict[str, QComboBox] = {}

        # Load config and generate ID
        self._load_config()
        self._generate_statrep_id()

        # Initialize API
        self.api = js8callAPIsupport.js8CallUDPAPICalls(
            self.server_ip, int(self.server_port)
        )

        # Build UI
        self._setup_ui()

    def _load_config(self) -> None:
        """Load configuration from config.ini."""
        if not os.path.exists(CONFIG_FILE):
            return

        config = ConfigParser()
        config.read(CONFIG_FILE)

        if "USERINFO" in config:
            userinfo = config["USERINFO"]
            self.callsign = userinfo.get("callsign", "")
            self.grid = userinfo.get("grid", "")
            self.selected_group = userinfo.get("selectedgroup", "")

        if "DIRECTEDCONFIG" in config:
            dirconfig = config["DIRECTEDCONFIG"]
            self.server_ip = dirconfig.get("server", "127.0.0.1")
            self.server_port = dirconfig.get("udp_port", "2242")

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

        # Header info (To, From, Grid)
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(15)

        # To (Group)
        to_layout = QtWidgets.QVBoxLayout()
        to_label = QtWidgets.QLabel("To:")
        to_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.to_field = QtWidgets.QLineEdit(self.selected_group)
        self.to_field.setReadOnly(True)
        self.to_field.setStyleSheet("background-color: #e9ecef;")
        to_layout.addWidget(to_label)
        to_layout.addWidget(self.to_field)
        header_layout.addLayout(to_layout)

        # From (Callsign)
        from_layout = QtWidgets.QVBoxLayout()
        from_label = QtWidgets.QLabel("From:")
        from_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.from_field = QtWidgets.QLineEdit(self.callsign)
        self.from_field.setReadOnly(True)
        self.from_field.setStyleSheet("background-color: #e9ecef;")
        from_layout.addWidget(from_label)
        from_layout.addWidget(self.from_field)
        header_layout.addLayout(from_layout)

        # Grid
        grid_layout = QtWidgets.QVBoxLayout()
        grid_label = QtWidgets.QLabel("Grid:")
        grid_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.grid_field = QtWidgets.QLineEdit(self.grid)
        self.grid_field.setReadOnly(True)
        self.grid_field.setStyleSheet("background-color: #e9ecef;")
        self.grid_field.setMaximumWidth(80)
        grid_layout.addWidget(grid_label)
        grid_layout.addWidget(self.grid_field)
        header_layout.addLayout(grid_layout)

        layout.addLayout(header_layout)

        # Scope dropdown
        scope_layout = QtWidgets.QHBoxLayout()
        scope_label = QtWidgets.QLabel("Scope:")
        scope_label.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE, QtGui.QFont.Bold))
        self.scope_combo = QtWidgets.QComboBox()
        self.scope_combo.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        for display, code in SCOPE_OPTIONS:
            self.scope_combo.addItem(display, code)
        scope_layout.addWidget(scope_label)
        scope_layout.addWidget(self.scope_combo)
        scope_layout.addStretch()
        layout.addLayout(scope_layout)

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
        self.remarks_field.setMaxLength(60)
        self.remarks_field.setPlaceholderText("Optional - max 60 characters")
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
        combo.setMinimumWidth(90)

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
        self.remarks_field.setText("NTR")

    def _on_all_gray(self) -> None:
        """Set all statuses to Unknown (Gray)."""
        self._set_all_status("Unknown")
        self.remarks_field.setText("NTR")

    def _build_message(self) -> str:
        """Build the StatRep message string for transmission."""
        values = self._get_status_values()
        scope_code = self.scope_combo.currentData()
        remarks = self.remarks_field.text().strip().upper()
        if not remarks:
            remarks = "NTR"

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

        # Format: @GROUP ,GRID,SCOPE,ID,STATUSES,REMARKS,{&%}
        group = f"@{self.selected_group}"
        message = f"{group} ,{self.grid},{scope_code},{self.statrep_id},{status_str},{remarks},{{&%}}"

        return message

    def _save_to_database(self) -> None:
        """Save StatRep to database."""
        values = self._get_status_values()
        scope_text = self.scope_combo.currentText()
        remarks = self.remarks_field.text().strip().upper() or "NTR"
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
                        fuel, food, crime, civil, political, comments
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    self.callsign.upper(),
                    self.selected_group.upper(),
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
                ))
                conn.commit()
        except sqlite3.Error as e:
            print(f"Database error saving StatRep: {e}")
            raise

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
            print(f"  To:       {self.selected_group}")
            print(f"  From:     {self.callsign}")
            print(f"  Grid:     {self.grid}")
            print(f"  Scope:    {self.scope_combo.currentText()}")
            print(f"  Message:  {message}")
            print(f"{'='*60}\n")

            self._show_info(f"StatRep saved:\n{message}")
            self._clear_copy_file()
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to save StatRep: {e}")

    def _on_transmit(self) -> None:
        """Validate, transmit, and save."""
        if not self._validate():
            return

        try:
            message = self._build_message()
            self.api.sendMessage(js8callAPIsupport.TYPE_TX_SEND, message)
            self._save_to_database()

            # Print to terminal
            now = QDateTime.currentDateTimeUtc().toString("yyyy-MM-dd HH:mm:ss")
            print(f"\n{'='*60}")
            print(f"STATREP TRANSMITTED - {now} UTC")
            print(f"{'='*60}")
            print(f"  ID:       {self.statrep_id}")
            print(f"  To:       {self.selected_group}")
            print(f"  From:     {self.callsign}")
            print(f"  Grid:     {self.grid}")
            print(f"  Scope:    {self.scope_combo.currentText()}")
            print(f"  Message:  {message}")
            print(f"{'='*60}\n")

            self._clear_copy_file()
            self.accept()
        except Exception as e:
            self._show_error(f"Failed to transmit StatRep: {e}")


# =============================================================================
# Standalone Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = StatRepDialog()
    dialog.show()
    sys.exit(app.exec_())
