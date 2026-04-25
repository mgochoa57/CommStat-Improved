# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Display Filter Dialog for CommStat
Filter StatRep and map data by date range.
"""

import os

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QDateEdit, QPushButton,
)

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER, COLOR_BTN_GREEN,
)

_PROG_BG = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG = DEFAULT_COLORS.get("data_background",    "#F8F6F4")

_COL_SAVE   = COLOR_BTN_GREEN
_COL_CANCEL = "#555555"


def _lbl_font() -> QtGui.QFont:
    return QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)


def _btn(label: str, color: str) -> QPushButton:
    b = QPushButton(label)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; border:none;"
        f" padding:6px 14px; border-radius:4px; font-family:Roboto; font-size:15px;"
        f" font-weight:bold; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
    )
    return b


class FilterDialog(QDialog):
    """Simple filter dialog for date range."""

    def __init__(self, current_filters: dict = None, parent=None):
        super().__init__(parent)
        self.current_filters = current_filters or {}
        self.result_filters = {}

        self.setWindowTitle("Display Filter")
        self.setFixedSize(500, 185)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        self.setStyleSheet(f"""
            QDialog {{ background-color: {_DATA_BG}; }}
            QLabel {{
                color: {COLOR_INPUT_TEXT}; font-family: Roboto;
                font-size: 13px; font-weight: bold;
            }}
            QDateEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px;
                padding: 2px 4px; font-family: 'Kode Mono'; font-size: 13px;
            }}
        """)

        self._setup_ui()
        self._load_from_current()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("DISPLAY FILTER")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # Date range row
        date_row = QHBoxLayout()
        date_row.setSpacing(8)

        start_lbl = QLabel("Start Date:")
        start_lbl.setFont(_lbl_font())
        date_row.addWidget(start_lbl)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setMinimumSize(130, 28)
        date_row.addWidget(self.start_date)

        date_row.addSpacing(12)

        end_lbl = QLabel("End Date:")
        end_lbl.setFont(_lbl_font())
        date_row.addWidget(end_lbl)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setMinimumSize(130, 28)
        date_row.addWidget(self.end_date)

        date_row.addStretch()
        layout.addLayout(date_row)

        layout.addStretch()

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.save_btn = _btn("Save", _COL_SAVE)
        self.save_btn.clicked.connect(self._save_filter)
        button_row.addWidget(self.save_btn)

        self.cancel_btn = _btn("Cancel", _COL_CANCEL)
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_btn)

        layout.addLayout(button_row)

    def _load_from_current(self) -> None:
        self.start_date.setDate(QDate.currentDate())
        self.end_date.setDate(QDate(2030, 12, 31))

        start_str = self.current_filters.get('start', '')
        if start_str:
            start_date = QDate.fromString(start_str[:10], "yyyy-MM-dd")
            if start_date.isValid():
                self.start_date.setDate(start_date)

        end_str = self.current_filters.get('end', '')
        if end_str:
            end_date = QDate.fromString(end_str[:10], "yyyy-MM-dd")
            if end_date.isValid():
                self.end_date.setDate(end_date)

    def _save_filter(self) -> None:
        self.result_filters = {
            'start': self.start_date.date().toString("yyyy-MM-dd"),
            'end': self.end_date.date().toString("yyyy-MM-dd")
        }
        self.accept()

    def get_filters(self) -> dict:
        return self.result_filters


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = FilterDialog()
    dialog.show()
    sys.exit(app.exec_())
