# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Modern Settings Dialog for CommStat-Improved
User settings only - colors are in a separate dialog.
"""

import os
import sys
import platform
from configparser import ConfigParser
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox,
    QGridLayout, QMessageBox
)




class SettingsDialog(QDialog):
    """Modern settings dialog for user configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CommStat-Improved Settings")
        self.setFixedSize(550, 350)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        # Set window icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        # Set font size to match main program
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        self.setFont(font)

        # Detect OS for path separator
        self._detect_os()

        # Setup UI
        self._setup_ui()

        # Load current settings
        self._load_config()

    def _detect_os(self):
        """Detect operating system for path handling."""
        if sys.platform == 'win32':
            self.os_directed = r"\DIRECTED.TXT"
            self.default_path = os.path.expandvars(r"%LOCALAPPDATA%\JS8Call")
        elif sys.platform == 'darwin':
            self.os_directed = "/DIRECTED.TXT"
            self.default_path = os.path.expanduser("~/Library/Application Support/JS8Call")
        else:  # Linux
            self.os_directed = "/DIRECTED.TXT"
            self.default_path = os.path.expanduser("~/.local/share/JS8Call")

    def _setup_ui(self):
        """Setup the main UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Station Info Group
        station_group = QGroupBox("Station Information")
        station_layout = QGridLayout(station_group)
        station_layout.setSpacing(10)
        station_layout.setContentsMargins(15, 20, 15, 15)

        # Callsign
        station_layout.addWidget(QLabel("Callsign:"), 0, 0)
        self.callsign_edit = QLineEdit()
        self.callsign_edit.setMaxLength(6)
        self.callsign_edit.setMinimumHeight(28)
        self.callsign_edit.setPlaceholderText("e.g., W1ABC")
        station_layout.addWidget(self.callsign_edit, 0, 1)

        # Suffix
        station_layout.addWidget(QLabel("Suffix:"), 0, 2)
        self.suffix_edit = QLineEdit()
        self.suffix_edit.setMaxLength(2)
        self.suffix_edit.setFixedWidth(60)
        self.suffix_edit.setMinimumHeight(28)
        station_layout.addWidget(self.suffix_edit, 0, 3)

        # Grid
        station_layout.addWidget(QLabel("Grid Square:"), 1, 0)
        self.grid_edit = QLineEdit()
        self.grid_edit.setMaxLength(6)
        self.grid_edit.setMinimumHeight(28)
        self.grid_edit.setPlaceholderText("e.g., EM83")
        station_layout.addWidget(self.grid_edit, 1, 1)

        # State/Province
        station_layout.addWidget(QLabel("State/Province:"), 2, 0)
        self.state_edit = QLineEdit()
        self.state_edit.setMaxLength(8)
        self.state_edit.setMinimumHeight(28)
        self.state_edit.setPlaceholderText("e.g., GA")
        station_layout.addWidget(self.state_edit, 2, 1)

        layout.addWidget(station_group)

        # Connection Settings
        connection_group = QGroupBox("Connection Settings")
        connection_layout = QGridLayout(connection_group)
        connection_layout.setSpacing(10)
        connection_layout.setContentsMargins(15, 20, 15, 15)

        connection_layout.addWidget(QLabel("Server:"), 0, 0)
        self.server_edit = QLineEdit()
        self.server_edit.setMinimumHeight(28)
        self.server_edit.setPlaceholderText("127.0.0.1")
        connection_layout.addWidget(self.server_edit, 0, 1)

        connection_layout.addWidget(QLabel("UDP Port:"), 0, 2)
        self.port_edit = QLineEdit()
        self.port_edit.setFixedWidth(80)
        self.port_edit.setMinimumHeight(28)
        self.port_edit.setPlaceholderText("2242")
        connection_layout.addWidget(self.port_edit, 0, 3)

        connection_layout.addWidget(QLabel("JS8Call Path:"), 1, 0)
        self.path_edit = QLineEdit()
        self.path_edit.setMinimumHeight(28)
        self.path_edit.setPlaceholderText(self.default_path)
        connection_layout.addWidget(self.path_edit, 1, 1, 1, 3)

        layout.addWidget(connection_group)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("saveButton")
        self.save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelButton")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_config(self):
        """Load settings from config.ini."""
        if not os.path.exists("config.ini"):
            # Set default path for new installations
            self.path_edit.setText(self.default_path)
            return

        config = ConfigParser()
        config.read("config.ini")

        # Load user info
        if "USERINFO" in config:
            userinfo = config["USERINFO"]
            self.callsign_edit.setText(userinfo.get("callsign", ""))
            self.suffix_edit.setText(userinfo.get("callsignsuffix", ""))
            self.grid_edit.setText(userinfo.get("grid", ""))

        # Load connection settings
        if "DIRECTEDCONFIG" in config:
            dirconfig = config["DIRECTEDCONFIG"]
            self.path_edit.setText(dirconfig.get("path", ""))
            self.server_edit.setText(dirconfig.get("server", "127.0.0.1"))
            self.port_edit.setText(dirconfig.get("UDP_port", "2242"))
            self.state_edit.setText(dirconfig.get("state", ""))

    def _save_settings(self):
        """Validate and save settings to config.ini."""
        # Validation
        callsign = self.callsign_edit.text().strip().upper()
        if len(callsign) < 4:
            self._show_error("Callsign must be at least 4 characters!")
            return

        grid = self.grid_edit.text().strip().upper()
        if len(grid) < 4:
            self._show_error("Grid must be at least 4 characters!")
            return

        path = self.path_edit.text().strip()
        if len(path) < 8:
            self._show_error("Path must be populated with JS8Call folder path!")
            return

        # Check if DIRECTED.TXT exists
        directed_path = path + self.os_directed
        if not os.path.exists(directed_path):
            self._show_error(f"JS8Call DIRECTED.TXT not found at:\n{directed_path}")
            return

        # Load existing config to preserve other sections
        config = ConfigParser()
        if os.path.exists("config.ini"):
            config.read("config.ini")

        config["USERINFO"] = {
            "callsign": callsign,
            "callsignsuffix": self.suffix_edit.text().strip().upper(),
            "grid": grid,
        }

        config["DIRECTEDCONFIG"] = {
            "path": path,
            "server": self.server_edit.text().strip() or "127.0.0.1",
            "UDP_port": self.port_edit.text().strip() or "2242",
            "state": self.state_edit.text().strip().upper()
        }

        # Write to file
        with open("config.ini", "w") as f:
            config.write(f)

        # Create reports folder if needed
        if not os.path.exists("reports"):
            os.makedirs("reports")

        self.accept()

    def _show_error(self, message: str):
        """Show an error message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle("CommStat-Improved Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.exec_()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = SettingsDialog()
    dialog.show()
    sys.exit(app.exec_())
