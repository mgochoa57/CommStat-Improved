# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Bulletin Dialog for CommStat-Improved
Allows creating and transmitting flash bulletins via JS8Call.
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
MIN_MESSAGE_LENGTH = 4
MAX_MESSAGE_LENGTH = 67
DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"

# Callsign pattern for US amateur radio
CALLSIGN_PATTERN = re.compile(r'[AKNW][A-Z]{0,2}[0-9][A-Z]{1,3}')


class Ui_FormBull:
    """Bulletin form for creating and transmitting flash bulletins."""

    def __init__(self):
        self.MainWindow: Optional[QtWidgets.QWidget] = None
        self.server_ip: str = "127.0.0.1"
        self.server_port: str = "2242"
        self.callsign: str = ""
        self.grid: str = ""
        self.selected_group: str = ""
        self.bull_id: str = ""
        self.api: Optional[js8callAPIsupport.js8CallUDPAPICalls] = None

    def setupUi(self, FormBull: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormBull
        FormBull.setObjectName("FormBull")
        FormBull.resize(835, 215)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        FormBull.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormBull.setWindowIcon(icon)

        # Callsign input
        self.label_3 = QtWidgets.QLabel(FormBull)
        self.label_3.setGeometry(QtCore.QRect(58, 65, 100, 20))
        self.label_3.setFont(font)
        self.label_3.setObjectName("label_3")

        self.lineEdit_3 = QtWidgets.QLineEdit(FormBull)
        self.lineEdit_3.setGeometry(QtCore.QRect(160, 65, 81, 22))
        self.lineEdit_3.setFont(font)
        self.lineEdit_3.setMaxLength(MAX_CALLSIGN_LENGTH)
        self.lineEdit_3.setObjectName("lineEdit_3")

        # Bulletin message input
        self.label_2 = QtWidgets.QLabel(FormBull)
        self.label_2.setGeometry(QtCore.QRect(30, 100, 148, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        self.lineEdit_2 = QtWidgets.QLineEdit(FormBull)
        self.lineEdit_2.setGeometry(QtCore.QRect(160, 100, 481, 22))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(MAX_MESSAGE_LENGTH)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Character limit note
        self.note_label = QtWidgets.QLabel(FormBull)
        self.note_label.setGeometry(QtCore.QRect(160, 125, 481, 20))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(9)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #666666;")
        self.note_label.setText("Bulletins are limited to 67 characters.")
        self.note_label.setObjectName("note_label")

        # Buttons
        self.pushButton_3 = QtWidgets.QPushButton(FormBull)
        self.pushButton_3.setGeometry(QtCore.QRect(430, 150, 75, 24))
        self.pushButton_3.setFont(font)
        self.pushButton_3.setObjectName("pushButton_3")
        self.pushButton_3.clicked.connect(self._save_only)

        self.pushButton = QtWidgets.QPushButton(FormBull)
        self.pushButton.setGeometry(QtCore.QRect(530, 150, 75, 24))
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self._transmit)

        self.pushButton_2 = QtWidgets.QPushButton(FormBull)
        self.pushButton_2.setGeometry(QtCore.QRect(630, 150, 75, 24))
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)

        self.retranslateUi(FormBull)
        QtCore.QMetaObject.connectSlotsByName(FormBull)

        # Load config and initialize
        self._generate_bull_id()
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

    def retranslateUi(self, FormBull: QtWidgets.QWidget) -> None:
        """Set UI text labels."""
        _translate = QtCore.QCoreApplication.translate
        FormBull.setWindowTitle(_translate("FormBull", "CommStat-Improved Bulletin"))
        self.label_2.setText(_translate("FormBull", "Bulletin to transmit : "))
        self.label_3.setText(_translate("FormBull", "From Callsign : "))
        self.pushButton.setText(_translate("FormBull", "Transmit"))
        self.pushButton_2.setText(_translate("FormBull", "Cancel"))
        self.pushButton_3.setText(_translate("FormBull", "Save Only"))

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
            systeminfo = config["DIRECTEDCONFIG"]
            self.server_ip = systeminfo.get("server", "127.0.0.1")
            self.server_port = systeminfo.get("UDP_port", "2242")

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

    def _validate_input(self, validate_callsign: bool = True) -> Optional[tuple]:
        """
        Validate form input.

        Returns (callsign, message) tuple if valid, None otherwise.
        """
        # Get and clean message
        message_raw = self.lineEdit_2.text()
        message = re.sub(r"[^ -~]+", " ", message_raw)

        # Validate message length
        if len(message) < MIN_MESSAGE_LENGTH:
            self._show_error("Bulletin too short")
            return None

        # Validate callsign if required
        if validate_callsign:
            call = self.lineEdit_3.text().upper()

            if len(call) < MIN_CALLSIGN_LENGTH:
                self._show_error("Callsign too short (minimum 4 characters)")
                return None

            if len(call) > MAX_CALLSIGN_LENGTH:
                self._show_error("Callsign too long (maximum 8 characters)")
                return None

            if not CALLSIGN_PATTERN.match(call):
                self._show_error("Does not meet callsign structure!")
                return None
        else:
            call = self.callsign

        return (call, message)

    def _build_message(self, message: str) -> str:
        """Build the bulletin message string for transmission."""
        group = "@" + self.selected_group
        return f"{group} MSG ,{self.bull_id},{message},{{^%}}"

    def _save_to_database(self, callsign: str, message: str) -> None:
        """Save bulletin to database."""
        now = QDateTime.currentDateTime()
        date = now.toUTC().toString("yyyy-MM-dd HH:mm:ss")

        conn = sqlite3.connect(DATABASE_FILE)
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO bulletins_Data "
                "(datetime, groupid, idnum, callsign, message) "
                "VALUES(?, ?, ?, ?, ?)",
                (date, self.selected_group, self.bull_id, callsign, message)
            )
            conn.commit()
            print(f"{date}, {self.selected_group}, {self.bull_id}, {callsign}, {message}")
        finally:
            conn.close()

    def _save_only(self) -> None:
        """Validate and save bulletin to database without transmitting."""
        result = self._validate_input(validate_callsign=True)
        if result is None:
            return

        callsign, message = result

        # Build message for display
        tx_message = self._build_message(message)
        self._show_info(f"CommStat-Improved has saved:\n{tx_message}")

        self._save_to_database(callsign, message)
        self.MainWindow.close()

    def _transmit(self) -> None:
        """Validate, transmit, and save bulletin message."""
        result = self._validate_input(validate_callsign=False)
        if result is None:
            return

        callsign, message = result

        # Build and send message
        tx_message = self._build_message(message)
        self.api.sendMessage(js8callAPIsupport.TYPE_TX_SEND, tx_message)

        # Save to database
        self._save_to_database(self.callsign, message)

        # Clear the copy file to trigger refresh
        with open("copyDIRECTED.TXT", "w") as f:
            f.write("blank line \n")

        self.MainWindow.close()

    def _generate_bull_id(self) -> None:
        """Generate a unique bulletin ID that doesn't exist in the database."""
        self.bull_id = str(random.randint(100, 999))

        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT idnum FROM bulletins_Data")
            existing_ids = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            conn.close()

            if self.bull_id in existing_ids:
                # ID already exists, generate a new one
                self._generate_bull_id()

        except sqlite3.Error as error:
            print(f"Failed to read data from sqlite table: {error}")


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    FormBull = QtWidgets.QWidget()
    ui = Ui_FormBull()
    ui.setupUi(FormBull)
    FormBull.show()
    sys.exit(app.exec_())
