# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Marquee Dialog for CommStat-Improved
Allows creating and transmitting marquee messages via JS8Call.
"""

import os
import re
import random
import sqlite3
from configparser import ConfigParser
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import QMessageBox
import js8callAPIsupport


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

    def __init__(self):
        self.MainWindow: Optional[QtWidgets.QWidget] = None
        self.server_ip: str = "127.0.0.1"
        self.server_port: str = "2242"
        self.callsign: str = ""
        self.grid: str = ""
        self.selected_group: str = ""
        self.marq_id: str = ""
        self.api: Optional[js8callAPIsupport.js8CallUDPAPICalls] = None

    def setupUi(self, FormMarquee: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormMarquee
        FormMarquee.setObjectName("FormMarquee")
        FormMarquee.resize(835, 275)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        FormMarquee.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormMarquee.setWindowIcon(icon)

        # Color selection label
        self.label = QtWidgets.QLabel(FormMarquee)
        self.label.setGeometry(QtCore.QRect(15, 55, 146, 20))
        self.label.setFont(font)
        self.label.setObjectName("label")

        # Radio buttons for color selection
        self.radioButton_Green = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Green.setGeometry(QtCore.QRect(185, 25, 89, 20))
        self.radioButton_Green.setObjectName("radioButton_Green")

        self.radioButton_Yellow = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Yellow.setGeometry(QtCore.QRect(185, 55, 89, 20))
        self.radioButton_Yellow.setObjectName("radioButton_Yellow")

        self.radioButton_Red = QtWidgets.QRadioButton(FormMarquee)
        self.radioButton_Red.setGeometry(QtCore.QRect(185, 85, 89, 20))
        self.radioButton_Red.setObjectName("radioButton_Red")

        # Callsign input
        self.label_3 = QtWidgets.QLabel(FormMarquee)
        self.label_3.setGeometry(QtCore.QRect(70, 125, 146, 20))
        self.label_3.setFont(font)
        self.label_3.setObjectName("label3")

        self.lineEdit_3 = QtWidgets.QLineEdit(FormMarquee)
        self.lineEdit_3.setGeometry(QtCore.QRect(171, 126, 60, 22))
        self.lineEdit_3.setFont(font)
        self.lineEdit_3.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.lineEdit_3.setObjectName("lineEdit_3")

        # Message input
        self.label_2 = QtWidgets.QLabel(FormMarquee)
        self.label_2.setGeometry(QtCore.QRect(45, 155, 126, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        self.lineEdit_2 = QtWidgets.QLineEdit(FormMarquee)
        self.lineEdit_2.setGeometry(QtCore.QRect(171, 156, 481, 22))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(MAX_MESSAGE_LENGTH)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Character limit note
        self.note_label = QtWidgets.QLabel(FormMarquee)
        self.note_label.setGeometry(QtCore.QRect(171, 182, 481, 20))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(9)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #666666;")
        self.note_label.setText("Marquee messages are limited to 67 characters.")
        self.note_label.setObjectName("note_label")

        # Buttons
        self.pushButton_3 = QtWidgets.QPushButton(FormMarquee)
        self.pushButton_3.setGeometry(QtCore.QRect(441, 220, 75, 24))
        self.pushButton_3.setFont(font)
        self.pushButton_3.setObjectName("pushButton_3")
        self.pushButton_3.clicked.connect(self._save_only)

        self.pushButton = QtWidgets.QPushButton(FormMarquee)
        self.pushButton.setGeometry(QtCore.QRect(541, 220, 75, 24))
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self._transmit)

        self.pushButton_2 = QtWidgets.QPushButton(FormMarquee)
        self.pushButton_2.setGeometry(QtCore.QRect(641, 220, 75, 24))
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)

        self.retranslateUi(FormMarquee)
        QtCore.QMetaObject.connectSlotsByName(FormMarquee)

        # Load config and initialize
        self._generate_marq_id()
        self._load_config()
        self.api = js8callAPIsupport.js8CallUDPAPICalls(
            self.server_ip, int(self.server_port)
        )

        # Set callsign in input field
        self.lineEdit_3.setText(self.callsign)

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
        FormMarquee.setWindowTitle(_translate("FormMarquee", "CommStat-Improved Marquee"))
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
        """Load configuration from config.ini."""
        if not os.path.exists(CONFIG_FILE):
            return

        config = ConfigParser()
        config.read(CONFIG_FILE)

        if "USERINFO" in config:
            userinfo = config["USERINFO"]
            self.callsign = userinfo.get("callsign", "")
            self.grid = userinfo.get("grid", "")

        if "DIRECTEDCONFIG" in config:
            systeminfo = config["DIRECTEDCONFIG"]
            self.server_ip = systeminfo.get("server", "127.0.0.1")
            self.server_port = systeminfo.get("UDP_port", "2242")

        # Get active group from database (not config.ini)
        self.selected_group = self._get_active_group_from_db()

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

    def _show_error(self, message: str) -> None:
        """Display an error message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat-Improved Error")
        msg.setText(message)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        msg.exec_()

    def _show_info(self, message: str) -> None:
        """Display an info message box."""
        msg = QMessageBox()
        msg.setWindowTitle("CommStat-Improved TX")
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
        group = "@" + self.selected_group
        return f"{group} ,{self.marq_id},{color},{message},{{*%}}"

    def _save_to_database(self, callsign: str, color: str, message: str) -> None:
        """Save marquee to database."""
        now = QDateTime.currentDateTime()
        date = now.toUTC().toString("yyyy-MM-dd HH:mm")

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO marquees_Data "
                "(idnum, callsign, groupname, date, color, message) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (self.marq_id, callsign, self.selected_group, date, color, message)
            )
            conn.commit()
            print(f"{date}, {self.selected_group}, {self.marq_id}, {callsign}, {message}")
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
        """Validate, transmit, and save marquee message."""
        result = self._validate_input(validate_callsign=False)
        if result is None:
            return

        callsign, message, color = result

        # Build and send message
        tx_message = self._build_message(color, message)
        self.api.sendMessage(js8callAPIsupport.TYPE_TX_SEND, tx_message)

        self._show_info(f"CommStat-Improved will transmit:\n{tx_message}")

        # Save to database
        self._save_to_database(self.callsign, color, message)

        # Clear the copy file to trigger refresh
        with open("copyDIRECTED.TXT", "w") as f:
            f.write("blank line \n")

        self.MainWindow.close()

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
    app = QtWidgets.QApplication(sys.argv)
    FormMarquee = QtWidgets.QWidget()
    ui = Ui_FormMarquee()
    ui.setupUi(FormMarquee)
    FormMarquee.show()
    sys.exit(app.exec_())
