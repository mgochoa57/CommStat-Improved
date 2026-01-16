# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
"""
js8_connectors.py - JS8Call Connector Management Dialog

Dialog for adding, editing, and removing JS8Call TCP connectors.
Supports up to 3 connectors with one designated as default.
"""

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QGroupBox, QTextEdit
)

from connector_manager import ConnectorManager, MAX_CONNECTORS
from js8_tcp_client import TCPConnectionPool


# UI Constants
FONT_FAMILY = "Arial"
FONT_SIZE = 10


class JS8ConnectorsDialog(QDialog):
    """Dialog for managing JS8Call TCP connectors."""

    def __init__(
        self,
        connector_manager: ConnectorManager,
        tcp_pool: TCPConnectionPool,
        parent=None
    ):
        """
        Initialize the connectors dialog.

        Args:
            connector_manager: ConnectorManager for database access.
            tcp_pool: TCPConnectionPool for connection management.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.connector_manager = connector_manager
        self.tcp_pool = tcp_pool
        self._selected_id = None

        self._setup_window()
        self._setup_ui()
        self._load_connectors()
        self._update_buttons()

    def _setup_window(self) -> None:
        """Configure window properties."""
        self.setWindowTitle("CommStat - JS8 Connectors")
        self.setFixedSize(500, 590)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(
            QtGui.QPixmap("radiation-32.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off
        )
        self.setWindowIcon(icon)

        # Set font
        font = QtGui.QFont()
        font.setFamily(FONT_FAMILY)
        font.setPointSize(FONT_SIZE)
        self.setFont(font)

    def _setup_ui(self) -> None:
        """Build the user interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Connectors list section
        list_group = QGroupBox("Configured Connectors")
        list_layout = QVBoxLayout(list_group)

        self.connectors_list = QListWidget()
        self.connectors_list.setMinimumHeight(150)
        self.connectors_list.itemClicked.connect(self._on_connector_selected)
        self.connectors_list.itemDoubleClicked.connect(self._on_connector_double_clicked)
        list_layout.addWidget(self.connectors_list)

        # List action buttons
        list_btn_layout = QHBoxLayout()

        self.set_default_btn = QPushButton("Set as Default")
        self.set_default_btn.clicked.connect(self._set_default)
        self.set_default_btn.setEnabled(False)
        list_btn_layout.addWidget(self.set_default_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_connector)
        self.remove_btn.setEnabled(False)
        list_btn_layout.addWidget(self.remove_btn)

        self.reconnect_btn = QPushButton("Reconnect")
        self.reconnect_btn.clicked.connect(self._reconnect)
        self.reconnect_btn.setEnabled(False)
        list_btn_layout.addWidget(self.reconnect_btn)

        list_layout.addLayout(list_btn_layout)
        layout.addWidget(list_group)

        # Add/Edit section
        edit_group = QGroupBox("Add New Connector")
        edit_layout = QGridLayout(edit_group)
        edit_layout.setSpacing(10)
        edit_layout.setContentsMargins(15, 20, 15, 15)

        # Rig Name
        edit_layout.addWidget(QLabel("Rig Name:"), 0, 0)
        self.rig_name_edit = QLineEdit()
        self.rig_name_edit.setMaxLength(8)
        self.rig_name_edit.setPlaceholderText("e.g., IC-7300, FTDX10")
        self.rig_name_edit.setMinimumHeight(28)
        self.rig_name_edit.textChanged.connect(self._on_input_changed)
        edit_layout.addWidget(self.rig_name_edit, 0, 1)

        # TCP Port
        edit_layout.addWidget(QLabel("TCP Port:"), 1, 0)
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("e.g., 2442")
        self.port_edit.setMinimumHeight(28)
        edit_layout.addWidget(self.port_edit, 1, 1)

        # State
        edit_layout.addWidget(QLabel("State:"), 2, 0)
        self.state_edit = QLineEdit()
        self.state_edit.setMaxLength(2)
        self.state_edit.setPlaceholderText("e.g., TX")
        self.state_edit.setMinimumHeight(28)
        self.state_edit.textChanged.connect(
            lambda text: self.state_edit.setText(text.upper())
        )
        edit_layout.addWidget(self.state_edit, 2, 1)

        # Comment
        edit_layout.addWidget(QLabel("Comment:"), 3, 0)
        self.comment_edit = QLineEdit()
        self.comment_edit.setMaxLength(50)
        self.comment_edit.setPlaceholderText("Optional description")
        self.comment_edit.setMinimumHeight(28)
        edit_layout.addWidget(self.comment_edit, 3, 1)

        # Add button
        self.add_btn = QPushButton("Add Connector")
        self.add_btn.clicked.connect(self._add_connector)
        self.add_btn.setEnabled(False)
        edit_layout.addWidget(self.add_btn, 4, 0, 1, 2)

        layout.addWidget(edit_group)

        # Info section
        info_group = QGroupBox("Information")
        info_group.setStyleSheet("QGroupBox::title { color: #AA0000; }")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            f"<b>Server:</b> 127.0.0.1 (localhost only)<br>"
            f"<b>Maximum:</b> {MAX_CONNECTORS} connectors<br>"
            f"<b>Default Port:</b> 2442 (JS8Call TCP API)<br><br>"
            f"<i><span style='color: #AA0000;'>Tip:</span> Enable both TCP settings in JS8Call under File > Settings > Reporting</i><br>"
            f"<i><span style='color: #AA0000;'>Note:</span> Each connector requires a unique port</i>"
        )
        info_text.setWordWrap(True)
        info_text.setFont(QtGui.QFont(FONT_FAMILY, FONT_SIZE))
        info_text.setStyleSheet("color: #000000;")
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_connectors(self) -> None:
        """Load connectors from database into the list."""
        self.connectors_list.clear()
        connectors = self.connector_manager.get_all_connectors()
        connection_status = self.tcp_pool.get_connection_status()

        for conn in connectors:
            rig_name = conn["rig_name"]
            tcp_port = conn["tcp_port"]
            state = conn.get("state", "") or ""
            is_default = conn["is_default"]
            is_enabled = conn.get("enabled", 1) == 1
            comment = conn.get("comment", "")

            # Get connection status
            is_connected = connection_status.get(rig_name, False)
            if not is_enabled:
                status_str = "Disabled"
            elif is_connected:
                status_str = "Connected"
            else:
                status_str = "Disconnected"

            # Build display text
            if state:
                text = f"{rig_name} (Port {tcp_port}, {state})"
            else:
                text = f"{rig_name} (Port {tcp_port})"
            if is_default:
                text += " [DEFAULT]"
            if not is_enabled:
                text += " [DISABLED]"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, conn)  # Store full connector data

            # Style based on status
            if is_default:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            # Gray out disabled connectors
            if not is_enabled:
                item.setForeground(QtGui.QColor("#888888"))

            # Add tooltip with more info
            tooltip = f"Status: {status_str}\nPort: {tcp_port}"
            if state:
                tooltip += f"\nState: {state}"
            if comment:
                tooltip += f"\nComment: {comment}"
            tooltip += f"\nAdded: {conn.get('date_added', 'Unknown')}"
            item.setToolTip(tooltip)

            self.connectors_list.addItem(item)

        # Update add button based on count
        count = self.connector_manager.get_connector_count()
        can_add = count < MAX_CONNECTORS and bool(self.rig_name_edit.text().strip())
        self.add_btn.setEnabled(can_add)

        # Clear selection
        self._selected_id = None
        self._update_buttons()

    def _on_connector_selected(self, item: QListWidgetItem) -> None:
        """Handle connector selection in list."""
        conn = item.data(Qt.UserRole)
        self._selected_id = conn["id"]
        self._update_buttons()

    def _on_connector_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click to populate edit fields."""
        conn = item.data(Qt.UserRole)
        self.rig_name_edit.setText(conn["rig_name"])
        self.port_edit.setText(str(conn["tcp_port"]))
        self.state_edit.setText(conn.get("state", "") or "")
        self.comment_edit.setText(conn.get("comment", ""))

    def _on_input_changed(self) -> None:
        """Handle changes to input fields."""
        count = self.connector_manager.get_connector_count()
        has_name = bool(self.rig_name_edit.text().strip())
        self.add_btn.setEnabled(count < MAX_CONNECTORS and has_name)

    def _update_buttons(self) -> None:
        """Update button states based on selection."""
        has_selection = self._selected_id is not None

        if has_selection:
            conn = self.connector_manager.get_connector_by_id(self._selected_id)
            if conn:
                is_default = conn["is_default"]
                count = self.connector_manager.get_connector_count()

                self.set_default_btn.setEnabled(not is_default)
                self.remove_btn.setEnabled(not is_default and count > 1)
                self.reconnect_btn.setEnabled(True)  # Always available - will enable if disabled
                return

        # No valid selection
        self.set_default_btn.setEnabled(False)
        self.remove_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)

    def _add_connector(self) -> None:
        """Add a new connector."""
        rig_name = self.rig_name_edit.text().strip()
        if not rig_name:
            QMessageBox.warning(
                self, "Validation Error",
                "Rig name is required."
            )
            return

        # Check max limit
        if self.connector_manager.get_connector_count() >= MAX_CONNECTORS:
            QMessageBox.warning(
                self, "Limit Reached",
                f"Maximum of {MAX_CONNECTORS} connectors allowed."
            )
            return

        # Validate port
        port_text = self.port_edit.text().strip()
        if not port_text:
            tcp_port = 2442  # Default port
        else:
            try:
                tcp_port = int(port_text)
                if tcp_port < 1024 or tcp_port > 65535:
                    raise ValueError("Port out of range")
            except ValueError:
                QMessageBox.warning(
                    self, "Validation Error",
                    "TCP Port must be a number between 1024 and 65535."
                )
                return

        state = self.state_edit.text().strip()
        comment = self.comment_edit.text().strip()

        # Check if first connector (will be default)
        is_first = not self.connector_manager.has_connectors()

        if self.connector_manager.add_connector(rig_name, tcp_port, state, comment, is_first):
            # Refresh TCP connections
            self.tcp_pool.refresh_connections()

            # Clear input fields
            self.rig_name_edit.clear()
            self.port_edit.clear()
            self.state_edit.clear()
            self.comment_edit.clear()

            # Reload list
            self._load_connectors()

            QMessageBox.information(
                self, "Success",
                f"Connector '{rig_name}' added successfully."
            )
        else:
            QMessageBox.warning(
                self, "Error",
                f"Failed to add connector. The name '{rig_name}' may already exist."
            )

    def _remove_connector(self) -> None:
        """Remove the selected connector."""
        if self._selected_id is None:
            return

        conn = self.connector_manager.get_connector_by_id(self._selected_id)
        if not conn:
            return

        rig_name = conn["rig_name"]

        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Remove connector '{rig_name}'?\n\n"
            "This will disconnect from JS8Call.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.connector_manager.remove_connector(self._selected_id):
                # Refresh TCP connections
                self.tcp_pool.refresh_connections()
                self._load_connectors()
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to remove connector."
                )

    def _set_default(self) -> None:
        """Set the selected connector as default."""
        if self._selected_id is None:
            return

        if self.connector_manager.set_default(self._selected_id):
            self._load_connectors()
        else:
            QMessageBox.warning(
                self, "Error",
                "Failed to set default connector."
            )

    def _reconnect(self) -> None:
        """Reconnect the selected connector (enables if disabled, resets attempt counter)."""
        if self._selected_id is None:
            return

        conn = self.connector_manager.get_connector_by_id(self._selected_id)
        if not conn:
            return

        rig_name = conn["rig_name"]
        is_enabled = conn.get("enabled", 1) == 1

        # Enable the connector if it was disabled
        if not is_enabled:
            self.connector_manager.set_enabled(self._selected_id, True)
            # Refresh connections to create the client (this also starts connecting)
            self.tcp_pool.refresh_connections()
            msg = f"Connector '{rig_name}' has been enabled.\n\nAttempting to connect..."
            QMessageBox.information(self, "Reconnecting", msg)
        else:
            # Already enabled - just trigger manual reconnect
            client = self.tcp_pool.get_client(rig_name)
            if client:
                client.manual_reconnect()
                msg = f"Attempting to reconnect to '{rig_name}'...\n\nAuto-reconnect has been re-enabled."
                QMessageBox.information(self, "Reconnecting", msg)

        # Reload to show updated status
        # (Note: Status may not update immediately due to async connection)
        QtCore.QTimer.singleShot(1000, self._load_connectors)

