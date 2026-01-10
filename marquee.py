# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Marquee Dialog for CommStat
Allows creating and transmitting marquee messages via JS8Call.
"""

import os
import re
import random
import sqlite3
from configparser import ConfigParser
from typing import Optional, TYPE_CHECKING

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from js8_tcp_client import TCPConnectionPool
    from connector_manager import ConnectorManager


# Constants
MIN_CALLSIGN_LENGTH = 4
MAX_CALLSIGN_LENGTH = 8
MIN_MESSAGE_LENGTH = 12
MAX_MESSAGE_LENGTH = 67
DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"

# Callsign pattern for US amateur radio
CALLSIGN_PATTERN = re.compile(r'[AKNW][A-Z]{0,2}[0-9][A-Z]{1,3}')


class Ui_FormMarquee:
    """Marquee form for creating and transmitting marquee messages."""

    def __init__(
        self,
        tcp_pool: "TCPConnectionPool" = None,
        connector_manager: "ConnectorManager" = None
    ):
        self.tcp_pool = tcp_pool
        self.connector_manager = connector_manager
        self.MainWindow: Optional[QtWidgets.QWidget] = None
        self.callsign: str = ""
        self.grid: str = ""
        self.selected_group: str = ""
        self.marq_id: str = ""
        self._pending_message: str = ""
        self._pending_color: str = ""

    def setupUi(self, FormMarquee: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormMarquee
        FormMarquee.setObjectName("FormMarquee")
        FormMarquee.resize(835, 305)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        FormMarquee.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormMarquee.setWindowIcon(icon)

        # Rig dropdown
        self.rig_label = QtWidgets.QLabel(FormMarquee)
        self.rig_label.setGeometry(QtCore.QRect(15, 15, 60, 20))
        self.rig_label.setFont(font)
        self.rig_label.setText("Rig:")
        self.rig_label.setObjectName("rig_label")

        self.rig_combo = QtWidgets.QComboBox(FormMarquee)
        self.rig_combo.setGeometry(QtCore.QRect(80, 15, 150, 22))
        self.rig_combo.setFont(font)
        self.rig_combo.setObjectName("rig_combo")

        # Color selection label
        self.label = QtWidgets.QLabel(FormMarquee)
        self.label.setGeometry(QtCore.QRect(15, 80, 146, 20))
        self.label.setFont(font)
        self.label.setObjectName("label")

        # Radio buttons for color selection
        self.radioButton_Green = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Green.setGeometry(QtCore.QRect(185, 50, 89, 20))
        self.radioButton_Green.setObjectName("radioButton_Green")

        self.radioButton_Yellow = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Yellow.setGeometry(QtCore.QRect(185, 80, 89, 20))
        self.radioButton_Yellow.setObjectName("radioButton_Yellow")

        self.radioButton_Red = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Red.setGeometry(QtCore.QRect(185, 110, 89, 20))
        self.radioButton_Red.setObjectName("radioButton_Red")

        # Group dropdown
        self.group_label = QtWidgets.QLabel(FormMarquee)
        self.group_label.setGeometry(QtCore.QRect(300, 80, 60, 20))
        self.group_label.setFont(font)
        self.group_label.setText("Group:")
        self.group_label.setObjectName("group_label")

        self.group_combo = QtWidgets.QComboBox(FormMarquee)
        self.group_combo.setGeometry(QtCore.QRect(360, 80, 150, 22))
        self.group_combo.setFont(font)
        self.group_combo.setObjectName("group_combo")

        # Callsign input (read-only, from JS8Call)
        self.label_3 = QtWidgets.QLabel(FormMarquee)
        self.label_3.setGeometry(QtCore.QRect(70, 150, 146, 20))
        self.label_3.setFont(font)
        self.label_3.setObjectName("label3")

        self.lineEdit_3 = QtWidgets.QLineEdit(FormMarquee)
        self.lineEdit_3.setGeometry(QtCore.QRect(171, 151, 60, 22))
        self.lineEdit_3.setFont(font)
        self.lineEdit_3.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.lineEdit_3.setReadOnly(True)
        self.lineEdit_3.setStyleSheet("background-color: #e9ecef;")
        self.lineEdit_3.setObjectName("lineEdit_3")

        # Message input
        self.label_2 = QtWidgets.QLabel(FormMarquee)
        self.label_2.setGeometry(QtCore.QRect(45, 180, 126, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        self.lineEdit_2 = QtWidgets.QLineEdit(FormMarquee)
        self.lineEdit_2.setGeometry(QtCore.QRect(171, 181, 481, 22))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(MAX_MESSAGE_LENGTH)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Character limit note
        self.note_label = QtWidgets.QLabel(FormMarquee)
        self.note_label.setGeometry(QtCore.QRect(171, 207, 481, 20))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(9)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #666666;")
        self.note_label.setText("Marquee messages are limited to 67 characters.")
        self.note_label.setObjectName("note_label")

        # Buttons
        self.pushButton_3 = QtWidgets.QPushButton(FormMarquee)
        self.pushButton_3.setGeometry(QtCore.QRect(441, 250, 75, 24))
        self.pushButton_3.setFont(font)
        self.pushButton_3.setObjectName("pushButton_3")
        self.pushButton_3.clicked.connect(self._save_only)

        self.pushButton = QtWidgets.QPushButton(FormMarquee)
        self.pushButton.setGeometry(QtCore.QRect(541, 250, 75, 24))
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self._transmit)

        self.pushButton_2 = QtWidgets.QPushButton(FormMarquee)
        self.pushButton_2.setGeometry(QtCore.QRect(641, 250, 75, 24))
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)

        self.retranslateUi(FormMarquee)
        QtCore.QMetaObject.connectSlotsByName(FormMarquee)

        # Load config and initialize
        self._generate_marq_id()
        self._load_config()

        # Connect rig combo signal
        self.rig_combo.currentTextChanged.connect(self._on_rig_changed)

        # Load rigs into dropdown
        self._load_rigs()

        self.MainWindow.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

    def retranslateUi(self, FormMarquee: QtWidgets.QWidget) -> None:
        """Set UI text labels."""
        _translate = QtCore.QCoreApplication.translate
        FormMarquee.setWindowTitle(_translate("FormMarquee", "CommStat Marquee"))
        self.label.setText(_translate("FormMarquee", "Select Marquee Color : "))
        self.label_2.setText(_translate("FormMarquee", "Marquee Message : "))
        self.label_3.setText(_translate("FormMarquee", "From Callsign :"))
        self.pushButton.setText(_translate("FormMarquee", "Transmit"))
        self.pushButton_2.setText(_translate("FormMarquee", "Cancel"))
        self.pushButton_3.setText(_translate("FormMarquee", "Save Only"))
        self.radioButton_Green.setText(_translate("FormMarquee", "Green"))
        self.radioButton_Yellow.setText(_translate("FormMarquee", "Yellow"))
        self.radioButton_Red.setText(_translate("FormMarquee", "Red"))

    def _load_config(self) -> None:
        """Load configuration from database.

        Auto-selects group only if exactly 1 group exists.
        If multiple groups exist, user must select one.
        """
        # Get active group from database
        self.selected_group = self._get_active_group_from_db()

        # Populate group dropdown
        all_groups = self._get_all_groups_from_db()
        if len(all_groups) == 1:
            # Exactly 1 group - auto-select it
            self.group_combo.addItem(all_groups[0])
        else:
            # Multiple groups or no groups - require user selection
            self.group_combo.addItem("")  # Empty first item
            for group in all_groups:
                self.group_combo.addItem(group)
        # Callsign will be loaded from JS8Call when rig is selected

    def _load_rigs(self) -> None:
        """Load connected rigs into the rig dropdown.

        Auto-selects only if exactly 1 rig is connected.
        If multiple rigs are connected, user must select one.
        """
        if not self.tcp_pool:
            return

        self.rig_combo.blockSignals(True)
        self.rig_combo.clear()

        # Get connected rigs
        connected_rigs = self.tcp_pool.get_connected_rig_names()

        if not connected_rigs:
            # No connected rigs - show all configured rigs as disconnected
            all_rigs = self.tcp_pool.get_all_rig_names()
            if all_rigs:
                self.rig_combo.addItem("")  # Empty first item
                for rig_name in all_rigs:
                    self.rig_combo.addItem(f"{rig_name} (disconnected)")
        elif len(connected_rigs) == 1:
            # Exactly 1 connected rig - auto-select it
            self.rig_combo.addItem(connected_rigs[0])
        else:
            # Multiple connected rigs - require user selection
            self.rig_combo.addItem("")  # Empty first item
            for rig_name in connected_rigs:
                self.rig_combo.addItem(rig_name)

        self.rig_combo.blockSignals(False)

        # Trigger rig changed to load callsign (only if a rig is selected)
        current_text = self.rig_combo.currentText()
        if current_text and "(disconnected)" not in current_text:
            self._on_rig_changed(current_text)

    def _on_rig_changed(self, rig_name: str) -> None:
        """Handle rig selection change - fetch callsign from JS8Call."""
        if not rig_name or "(disconnected)" in rig_name or not self.tcp_pool:
            self.callsign = ""
            self.lineEdit_3.setText("")
            return

        client = self.tcp_pool.get_client(rig_name)
        if client and client.is_connected():
            # Connect signal for this client (disconnect any existing first)
            try:
                client.callsign_received.disconnect(self._on_callsign_received)
            except TypeError:
                pass

            client.callsign_received.connect(self._on_callsign_received)

            # Request callsign from JS8Call
            client.get_callsign()

    def _on_callsign_received(self, rig_name: str, callsign: str) -> None:
        """Handle callsign received from JS8Call."""
        # Only update if this is the currently selected rig
        if self.rig_combo.currentText() == rig_name:
            self.callsign = callsign
            self.lineEdit_3.setText(callsign)

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

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _show_info(self, message: str) -> None:
        """Display an info message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat TX")
        msg.setText(message)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _get_selected_color(self) -> Optional[str]:
        """Get the selected color code, or None if none selected."""
        if self.radioButton_Green.isChecked():
            return "1"
        elif self.radioButton_Yellow.isChecked():
            return "2"
        elif self.radioButton_Red.isChecked():
            return "3"
        return None

    def _validate_input(self, validate_callsign: bool = True) -> Optional[tuple]:
        """
        Validate form input.

        Returns (callsign, message, color) tuple if valid, None otherwise.
        """
        # Check rig is selected
        rig_name = self.rig_combo.currentText()
        if not rig_name or rig_name == "":
            self._show_error("Please select a Rig")
            self.rig_combo.setFocus()
            return None

        # Check group is selected
        group_name = self.group_combo.currentText()
        if not group_name or group_name == "":
            self._show_error("Please select a Group")
            self.group_combo.setFocus()
            return None

        # Get and clean message
        message_raw = self.lineEdit_2.text()
        message = re.sub(r"[^ -~]+", " ", message_raw).upper()

        # Validate callsign if required
        if validate_callsign:
            call = self.lineEdit_3.text().upper()

            if len(call) < MIN_CALLSIGN_LENGTH:
                self._show_error("Callsign too short")
                return None

            if len(call) > MAX_CALLSIGN_LENGTH:
                self._show_error("Callsign too long")
                return None

            if not CALLSIGN_PATTERN.match(call):
                self._show_error("Callsign entered does not meet callsign structure requirements!")
                return None
        else:
            call = self.callsign

        # Validate message length
        if len(message) < MIN_MESSAGE_LENGTH:
            self._show_error("Marquee text too short")
            return None

        # Validate color selection
        color = self._get_selected_color()
        if color is None:
            self._show_error("Color selection is required!")
            return None

        return (call, message, color)

    def _build_message(self, color: str, message: str) -> str:
        """Build the marquee message string for transmission."""
        group = "@" + self.group_combo.currentText()
        return f"{group} ,{self.marq_id},{color},{message},{{*%}}"

    def _save_to_database(self, callsign: str, color: str, message: str, frequency: int = 0) -> None:
        """Save marquee to database.

        Args:
            callsign: The callsign of the sender.
            color: The color code (1=green, 2=yellow, 3=red).
            message: The marquee message.
            frequency: The frequency in Hz at the time of transmission.
        """
        now = QDateTime.currentDateTime()
        date = now.toUTC().toString("yyyy-MM-dd HH:mm")

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO marquees_Data "
                "(idnum, callsign, groupname, date, color, message, frequency) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (self.marq_id, callsign, self.group_combo.currentText(), date, color, message, frequency)
            )
            conn.commit()
            freq_mhz = frequency / 1000000.0 if frequency else 0
            print(f"{date}, {self.group_combo.currentText()}, {self.marq_id}, {callsign}, {message}, {freq_mhz:.6f} MHz")
        finally:
            conn.close()

    def _save_only(self) -> None:
        """Validate and save marquee to database without transmitting."""
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return

        callsign, message, color = result
        self._save_to_database(callsign, color, message)
        self.MainWindow.close()

    def _transmit(self) -> None:
        """Validate, get frequency, transmit, and save marquee message."""
        result = self._validate_input(validate_callsign=False)
        if result is None:
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

        callsign, message, color = result

        # Store pending values for transmission after frequency is received
        self._pending_message = self._build_message(color, message)
        self._pending_color = color

        # Connect frequency signal and request frequency
        try:
            client.frequency_received.disconnect(self._on_frequency_for_transmit)
        except TypeError:
            pass
        client.frequency_received.connect(self._on_frequency_for_transmit)

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

            self._show_info(f"CommStat will transmit:\n{self._pending_message}")

            # Save to database with frequency
            message = self.lineEdit_2.text()
            message = re.sub(r"[^ -~]+", " ", message).upper()
            self._save_to_database(self.callsign, self._pending_color, message, frequency)

            # Clear the copy file to trigger refresh
            with open("copyDIRECTED.TXT", "w") as f:
                f.write("blank line \n")

            self.MainWindow.close()
        except Exception as e:
            self._show_error(f"Failed to transmit marquee: {e}")

    def _generate_marq_id(self) -> None:
        """Generate a unique marquee ID that doesn't exist in the database."""
        self.marq_id = str(random.randint(100, 999))

        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT idnum FROM marquees_Data")
            existing_ids = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()

            if self.marq_id in existing_ids:
                # ID already exists, generate a new one
                self._generate_marq_id()

        except sqlite3.Error as error:
            print(f"Failed to read data from sqlite table: {error}")


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

    FormMarquee = QtWidgets.QWidget()
    ui = Ui_FormMarquee(tcp_pool, connector_manager)
    ui.setupUi(FormMarquee)
    FormMarquee.show()
    sys.exit(app.exec_())
