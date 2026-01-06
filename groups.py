# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Manage Groups Dialog for CommStat-Improved
Add, edit, and remove groups with extended fields.
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
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
        self.setWindowTitle("Manage Groups")
        self.setFixedSize(450, 530)
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

        self._editing_group = None  # Track which group is being edited
        self._setup_ui()
        self._load_groups()

    def _setup_ui(self) -> None:
        """Setup the UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Add/Edit group section
        form_group = QGroupBox("Add / Edit Group")
        form_layout = QFormLayout(form_group)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(MAX_GROUP_NAME_LENGTH)
        self.name_input.setPlaceholderText("Group name (max 15 chars)")
        self.name_input.textChanged.connect(self._on_input_changed)
        form_layout.addRow("Group Name:", self.name_input)

        # Help note about @ symbol (JS8Call requires it, CommStat does not)
        name_hint = QLabel("Note: The @ symbol is not required (e.g., enter MAGNET, not @MAGNET)")
        name_hint.setStyleSheet("color: #CC0000; font-size: 10px; font-weight: bold;")
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

        # Buttons row
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._add_group)
        self.add_btn.setEnabled(False)
        btn_layout.addWidget(self.add_btn)

        self.update_btn = QPushButton("Update")
        self.update_btn.clicked.connect(self._update_group)
        self.update_btn.setEnabled(False)
        self.update_btn.hide()  # Hidden until editing
        btn_layout.addWidget(self.update_btn)

        self.cancel_edit_btn = QPushButton("Cancel Edit")
        self.cancel_edit_btn.clicked.connect(self._cancel_edit)
        self.cancel_edit_btn.hide()  # Hidden until editing
        btn_layout.addWidget(self.cancel_edit_btn)

        btn_layout.addStretch()
        form_layout.addRow("", btn_layout)

        layout.addWidget(form_group)

        # Groups list
        list_group = QGroupBox("Groups")
        list_layout = QVBoxLayout(list_group)

        self.groups_list = QListWidget()
        self.groups_list.setMinimumHeight(180)
        self.groups_list.itemClicked.connect(self._on_group_selected)
        self.groups_list.itemDoubleClicked.connect(self._edit_group)
        list_layout.addWidget(self.groups_list)

        # List action buttons
        list_btn_layout = QHBoxLayout()

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._edit_group)
        self.edit_btn.setEnabled(False)
        list_btn_layout.addWidget(self.edit_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_group)
        self.remove_btn.setEnabled(False)
        list_btn_layout.addWidget(self.remove_btn)

        list_btn_layout.addStretch()
        list_layout.addLayout(list_btn_layout)

        layout.addWidget(list_group)

        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def _load_groups(self) -> None:
        """Load groups from database into the list."""
        self.groups_list.clear()
        groups = self.db.get_all_groups()

        for group_name in groups:
            item = QListWidgetItem(group_name)
            self.groups_list.addItem(item)

        self._update_buttons()

    def _on_group_selected(self, item: QListWidgetItem) -> None:
        """Handle group selection."""
        self._update_buttons()

    def _on_input_changed(self, text: str) -> None:
        """Enable/disable Add button based on input text."""
        has_name = bool(text.strip())
        if self._editing_group:
            self.update_btn.setEnabled(has_name)
        else:
            self.add_btn.setEnabled(has_name)

    def _update_buttons(self) -> None:
        """Update button states based on selection."""
        selected = self.groups_list.currentItem()
        has_selection = selected is not None

        self.edit_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)

    def _get_selected_group_name(self) -> str:
        """Get the group name from selection."""
        selected = self.groups_list.currentItem()
        if selected:
            return selected.text()
        return ""

    def _add_group(self) -> None:
        """Add a new group."""
        name = self.name_input.text().strip().upper()

        # Strip @ symbol if user included it (JS8Call uses @GROUP, CommStat doesn't)
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
            QMessageBox.warning(
                self, "Error",
                "Failed to add group. Name may already exist."
            )

    def _edit_group(self) -> None:
        """Load selected group into form for editing."""
        group_name = self._get_selected_group_name()
        if not group_name:
            return

        details = self.db.get_group_details(group_name)
        if details:
            self._editing_group = group_name
            self.name_input.setText(details["name"])
            self.name_input.setEnabled(False)  # Can't change name
            self.comment_input.setText(details["comment"])
            self.url1_input.setText(details["url1"])
            self.url2_input.setText(details["url2"])

            # Switch to edit mode
            self.add_btn.hide()
            self.update_btn.show()
            self.update_btn.setEnabled(True)
            self.cancel_edit_btn.show()

    def _update_group(self) -> None:
        """Update the currently editing group."""
        if not self._editing_group:
            return

        comment = self.comment_input.text().strip()
        url1 = self.url1_input.text().strip()
        url2 = self.url2_input.text().strip()

        if self.db.update_group(self._editing_group, comment, url1, url2):
            self._cancel_edit()
            self._load_groups()
        else:
            QMessageBox.warning(
                self, "Error",
                "Failed to update group."
            )

    def _cancel_edit(self) -> None:
        """Cancel editing and return to add mode."""
        self._editing_group = None
        self._clear_form()
        self.name_input.setEnabled(True)
        self.add_btn.show()
        self.update_btn.hide()
        self.cancel_edit_btn.hide()

    def _clear_form(self) -> None:
        """Clear all input fields."""
        self.name_input.clear()
        self.comment_input.clear()
        self.url1_input.clear()
        self.url2_input.clear()
        self.add_btn.setEnabled(False)

    def _remove_group(self) -> None:
        """Remove selected group."""
        group_name = self._get_selected_group_name()
        if not group_name:
            return

        # Confirm deletion
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
                QMessageBox.warning(
                    self, "Error",
                    "Failed to remove group."
                )


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    # Note: Requires a DatabaseManager instance to run standalone
    print("This dialog requires a DatabaseManager instance.")
    sys.exit(1)
