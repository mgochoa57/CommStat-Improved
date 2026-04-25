# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Manage Groups Dialog for CommStat
Add, edit, and remove groups with extended fields.
"""

import os

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QGroupBox,
)

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_ERROR, COLOR_BTN_GREEN, COLOR_BTN_BLUE, COLOR_BTN_RED,
)

MAX_GROUP_NAME_LENGTH = 15

_PROG_BG = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG = DEFAULT_COLORS.get("data_background",    "#F8F6F4")

_COL_CLOSE  = "#555555"
_COL_CANCEL = "#555555"


def _lbl_font() -> QtGui.QFont:
    return QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)


def _mono_font() -> QtGui.QFont:
    return QtGui.QFont("Kode Mono")


def _btn(label: str, color: str, min_w: int = 90) -> QPushButton:
    b = QPushButton(label)
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


class GroupsDialog(QDialog):
    """Dialog for managing groups."""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Manage Groups")
        self.setFixedSize(450, 580)
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
            QLineEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px;
                padding: 2px 4px; font-family: 'Kode Mono'; font-size: 13px;
            }}
            QLineEdit:disabled {{
                background-color: #e9ecef; color: #999999;
            }}
            QListWidget {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
            QListWidget::item:selected {{
                background-color: #cce5ff; color: #000000;
            }}
            QGroupBox {{
                font-family: Roboto; font-size: 13px; font-weight: bold;
                color: {COLOR_INPUT_TEXT}; border: 1px solid {COLOR_INPUT_BORDER};
                border-radius: 4px; margin-top: 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                left: 10px; padding: 2px 4px; background-color: {_DATA_BG};
            }}
        """)

        self._editing_group = None
        self._setup_ui()
        self._load_groups()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("MANAGE GROUPS")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # Add / Edit group section
        form_group = QGroupBox("Add / Edit Group")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(MAX_GROUP_NAME_LENGTH)
        self.name_input.setPlaceholderText("Group name (max 15 chars)")
        self.name_input.textChanged.connect(self._on_input_changed)
        form_layout.addRow("Group Name:", self.name_input)

        name_hint = QLabel("Note: The @ symbol is not required (e.g., enter MAGNET, not @MAGNET)")
        name_hint.setStyleSheet(
            f"color: {COLOR_ERROR}; font-family: Roboto; font-size: 10px; font-weight: bold;"
        )
        name_hint.setWordWrap(True)
        form_layout.addRow("", name_hint)

        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("Optional description")
        form_layout.addRow("Comment:", self.comment_input)

        self.url1_input = QLineEdit()
        self.url1_input.setPlaceholderText("Optional URL")
        form_layout.addRow("URL 1:", self.url1_input)

        self.url2_input = QLineEdit()
        self.url2_input.setPlaceholderText("Optional URL")
        form_layout.addRow("URL 2:", self.url2_input)

        # Form action buttons (right-aligned per standard)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.add_btn = _btn("Add", COLOR_BTN_GREEN)
        self.add_btn.clicked.connect(self._add_group)
        self.add_btn.setEnabled(False)
        btn_layout.addWidget(self.add_btn)

        self.update_btn = _btn("Update", COLOR_BTN_BLUE)
        self.update_btn.clicked.connect(self._update_group)
        self.update_btn.setEnabled(False)
        self.update_btn.hide()
        btn_layout.addWidget(self.update_btn)

        self.cancel_edit_btn = _btn("Cancel Edit", _COL_CANCEL)
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        self.cancel_edit_btn.hide()
        btn_layout.addWidget(self.cancel_edit_btn)

        form_layout.addRow("", btn_layout)
        layout.addWidget(form_group)

        # Groups list
        list_group = QGroupBox("Groups")
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(8)

        self.groups_list = QListWidget()
        self.groups_list.setMinimumHeight(180)
        self.groups_list.itemClicked.connect(self._on_group_selected)
        self.groups_list.itemDoubleClicked.connect(self._edit_group)
        list_layout.addWidget(self.groups_list)

        list_btn_layout = QHBoxLayout()
        list_btn_layout.addStretch()

        self.edit_btn = _btn("Edit", COLOR_BTN_BLUE)
        self.edit_btn.clicked.connect(self._edit_group)
        self.edit_btn.setEnabled(False)
        list_btn_layout.addWidget(self.edit_btn)

        self.remove_btn = _btn("Remove", COLOR_BTN_RED)
        self.remove_btn.clicked.connect(self._remove_group)
        self.remove_btn.setEnabled(False)
        list_btn_layout.addWidget(self.remove_btn)

        list_layout.addLayout(list_btn_layout)
        layout.addWidget(list_group)

        # Close button
        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_btn = _btn("Close", _COL_CLOSE)
        self.close_btn.clicked.connect(self.accept)
        close_row.addWidget(self.close_btn)
        layout.addLayout(close_row)

    def _load_groups(self) -> None:
        self.groups_list.clear()
        groups = self.db.get_all_groups()
        for group_name in groups:
            self.groups_list.addItem(QListWidgetItem(group_name))
        self._update_buttons()

    def _on_group_selected(self, item: QListWidgetItem) -> None:
        self._update_buttons()

    def _on_input_changed(self, text: str) -> None:
        has_name = bool(text.strip())
        if self._editing_group:
            self.update_btn.setEnabled(has_name)
        else:
            self.add_btn.setEnabled(has_name)

    def _update_buttons(self) -> None:
        has_selection = self.groups_list.currentItem() is not None
        self.edit_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)

    def _get_selected_group_name(self) -> str:
        selected = self.groups_list.currentItem()
        return selected.text() if selected else ""

    def _add_group(self) -> None:
        name = self.name_input.text().strip().upper()
        if name.startswith("@"):
            name = name[1:]
        if not name:
            return
        if len(name) > MAX_GROUP_NAME_LENGTH:
            QMessageBox.warning(
                self, "Invalid Name",
                f"Group name must be {MAX_GROUP_NAME_LENGTH} characters or less."
            )
            return
        comment = self.comment_input.text().strip()
        url1 = self.url1_input.text().strip()
        url2 = self.url2_input.text().strip()
        if self.db.add_group(name, comment, url1, url2):
            self._clear_form()
            self._load_groups()
        else:
            QMessageBox.warning(self, "Error", "Failed to add group. Name may already exist.")

    def _edit_group(self) -> None:
        group_name = self._get_selected_group_name()
        if not group_name:
            return
        details = self.db.get_group_details(group_name)
        if details:
            self._editing_group = group_name
            self.name_input.setText(details["name"])
            self.name_input.setEnabled(False)
            self.comment_input.setText(details["comment"])
            self.url1_input.setText(details["url1"])
            self.url2_input.setText(details["url2"])
            self.add_btn.hide()
            self.update_btn.show()
            self.update_btn.setEnabled(True)
            self.cancel_edit_btn.show()

    def _update_group(self) -> None:
        if not self._editing_group:
            return
        comment = self.comment_input.text().strip()
        url1 = self.url1_input.text().strip()
        url2 = self.url2_input.text().strip()
        if self.db.update_group(self._editing_group, comment, url1, url2):
            self._cancel_edit()
            self._load_groups()
        else:
            QMessageBox.warning(self, "Error", "Failed to update group.")

    def _cancel_edit(self) -> None:
        self._editing_group = None
        self._clear_form()
        self.name_input.setEnabled(True)
        self.add_btn.show()
        self.update_btn.hide()
        self.cancel_edit_btn.hide()

    def _clear_form(self) -> None:
        self.name_input.clear()
        self.comment_input.clear()
        self.url1_input.clear()
        self.url2_input.clear()
        self.add_btn.setEnabled(False)

    def _remove_group(self) -> None:
        group_name = self._get_selected_group_name()
        if not group_name:
            return
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Remove group '{group_name}'?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.db.remove_group(group_name):
                self._load_groups()
            else:
                QMessageBox.warning(self, "Error", "Failed to remove group.")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    print("This dialog requires a DatabaseManager instance.")
    sys.exit(1)
