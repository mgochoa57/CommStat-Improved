# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Manage Groups Dialog for CommStat-Improved
Add, remove, and set active groups.
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QGroupBox
)


# Constants
MAX_GROUP_NAME_LENGTH = 15


class GroupsDialog(QDialog):
    """Dialog for managing groups."""

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("CommStat-Improved Manage Groups")
        self.setFixedSize(350, 400)
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
        self._load_groups()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Groups list
        list_group = QGroupBox("Groups")
        list_layout = QVBoxLayout(list_group)

        self.groups_list = QListWidget()
        self.groups_list.setMinimumHeight(200)
        self.groups_list.itemClicked.connect(self._on_group_selected)
        list_layout.addWidget(self.groups_list)

        # Set Active button
        self.set_active_btn = QPushButton("Set as Active")
        self.set_active_btn.clicked.connect(self._set_active)
        self.set_active_btn.setEnabled(False)
        list_layout.addWidget(self.set_active_btn)

        # Remove button
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self._remove_group)
        self.remove_btn.setEnabled(False)
        list_layout.addWidget(self.remove_btn)

        layout.addWidget(list_group)

        # Add new group section
        add_group = QGroupBox("Add New Group")
        add_layout = QHBoxLayout(add_group)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(MAX_GROUP_NAME_LENGTH)
        self.name_input.setPlaceholderText("Group name (max 15 chars)")
        self.name_input.returnPressed.connect(self._add_group)
        self.name_input.textChanged.connect(self._on_name_input_changed)
        add_layout.addWidget(self.name_input)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._add_group)
        self.add_btn.setEnabled(False)
        add_layout.addWidget(self.add_btn)

        layout.addWidget(add_group)

        # Save and Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _load_groups(self) -> None:
        """Load groups from database into the list."""
        self.groups_list.clear()
        groups = self.db.get_all_groups()
        active_group = self.db.get_active_group()

        for group_name in groups:
            item = QListWidgetItem(group_name)
            if group_name == active_group:
                item.setText(f"{group_name} (Active)")
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.groups_list.addItem(item)

        self._update_buttons()

    def _on_group_selected(self, item: QListWidgetItem) -> None:
        """Handle group selection."""
        self._update_buttons()

    def _on_name_input_changed(self, text: str) -> None:
        """Enable/disable Add button based on input text."""
        self.add_btn.setEnabled(bool(text.strip()))

    def _update_buttons(self) -> None:
        """Update button states based on selection."""
        selected = self.groups_list.currentItem()
        has_selection = selected is not None

        # Check if selected is active (has "(Active)" suffix)
        is_active = has_selection and "(Active)" in selected.text()

        self.set_active_btn.setEnabled(has_selection and not is_active)

        # Can only remove if not active and more than 1 group exists
        can_remove = has_selection and not is_active and self.db.get_group_count() > 1
        self.remove_btn.setEnabled(can_remove)

    def _get_selected_group_name(self) -> str:
        """Get the clean group name from selection (without Active suffix)."""
        selected = self.groups_list.currentItem()
        if selected:
            return selected.text().replace(" (Active)", "")
        return ""

    def _set_active(self) -> None:
        """Set selected group as active."""
        group_name = self._get_selected_group_name()
        if group_name:
            if self.db.set_active_group(group_name):
                self._load_groups()
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to set active group."
                )

    def _add_group(self) -> None:
        """Add a new group."""
        name = self.name_input.text().strip().upper()
        if not name:
            return

        if len(name) > MAX_GROUP_NAME_LENGTH:
            QMessageBox.warning(
                self, "Invalid Name",
                f"Group name must be {MAX_GROUP_NAME_LENGTH} characters or less."
            )
            return

        if self.db.add_group(name):
            self.name_input.clear()
            self._load_groups()
        else:
            QMessageBox.warning(
                self, "Error",
                "Failed to add group. Name may already exist."
            )

    def _remove_group(self) -> None:
        """Remove selected group."""
        group_name = self._get_selected_group_name()
        if not group_name:
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Remove group '{group_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.db.remove_group(group_name):
                self._load_groups()
            else:
                QMessageBox.warning(
                    self, "Cannot Remove",
                    "Cannot remove the last group."
                )


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    # Note: Requires a DatabaseManager instance to run standalone
    print("This dialog requires a DatabaseManager instance.")
    sys.exit(1)
