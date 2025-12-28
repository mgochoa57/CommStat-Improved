# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Display Filter Dialog for CommStat-Improved
Filter StatRep and map data by date range.
"""

import os
from configparser import ConfigParser
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDateEdit, QPushButton, QGroupBox
)


class FilterDialog(QDialog):
    """Simple filter dialog for date range."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CommStat-Improved Display Filter")
        self.setFixedSize(400, 150)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        # Set window icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        self.setFont(font)

        self._setup_ui()
        self._load_config()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Date Range Group
        date_group = QGroupBox("Date Range")
        date_layout = QGridLayout(date_group)
        date_layout.setSpacing(10)
        date_layout.setContentsMargins(15, 20, 15, 15)

        date_layout.addWidget(QLabel("Start Date:"), 0, 0)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setMinimumHeight(28)
        date_layout.addWidget(self.start_date, 0, 1)

        date_layout.addWidget(QLabel("End Date:"), 0, 2)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setMinimumHeight(28)
        date_layout.addWidget(self.end_date, 0, 3)

        layout.addWidget(date_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save Filter")
        self.save_btn.clicked.connect(self._save_filter)
        button_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_config(self) -> None:
        """Load current filter settings from config.ini."""
        # Set defaults
        self.start_date.setDate(QDate(2023, 1, 1))
        self.end_date.setDate(QDate(2030, 12, 31))

        if not os.path.exists("config.ini"):
            return

        config = ConfigParser()
        config.read("config.ini")

        if "FILTER" in config:
            filters = config["FILTER"]

            # Parse start date
            start_str = filters.get("start", "2023-01-01")
            start_date = QDate.fromString(start_str[:10], "yyyy-MM-dd")
            if start_date.isValid():
                self.start_date.setDate(start_date)

            # Parse end date
            end_str = filters.get("end", "2030-12-31")
            end_date = QDate.fromString(end_str[:10], "yyyy-MM-dd")
            if end_date.isValid():
                self.end_date.setDate(end_date)

    def _save_filter(self) -> None:
        """Save filter settings to config.ini."""
        config = ConfigParser()
        if os.path.exists("config.ini"):
            config.read("config.ini")

        config["FILTER"] = {
            "start": self.start_date.date().toString("yyyy-MM-dd"),
            "end": self.end_date.date().toString("yyyy-MM-dd")
        }

        with open("config.ini", "w") as f:
            config.write(f)

        self.accept()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = FilterDialog()
    dialog.show()
    sys.exit(app.exec_())
