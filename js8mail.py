# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 Email Dialog for CommStat-Improved
Allows sending emails via JS8Call APRS gateway.
"""

import re
import os
from configparser import ConfigParser
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox
import js8callAPIsupport


# Constants
MIN_EMAIL_LENGTH = 8
MIN_SUBJECT_LENGTH = 8
EMAIL_PATTERN = r"^.+@(\[?)[a-zA-Z0-9-.]+\.([a-zA-Z]{2,3}|[0-9]{1,3})(]?)$"


class Ui_FormJS8Mail:
    """JS8 Email form for sending emails via APRS gateway."""

    def setupUi(self, FormJS8Mail: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormJS8Mail
        FormJS8Mail.setObjectName("FormJS8Mail")
        FormJS8Mail.resize(835, 260)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        FormJS8Mail.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormJS8Mail.setWindowIcon(icon)

        # Warning message
        self.warning_label = QtWidgets.QLabel(FormJS8Mail)
        self.warning_label.setGeometry(QtCore.QRect(58, 15, 700, 25))
        bold_font = QtGui.QFont()
        bold_font.setFamily("Arial")
        bold_font.setPointSize(12)
        bold_font.setBold(True)
        self.warning_label.setFont(bold_font)
        self.warning_label.setText("Sending email depends on APRS services being available.")
        self.warning_label.setObjectName("warning_label")

        # Email address input
        self.lineEdit = QtWidgets.QLineEdit(FormJS8Mail)
        self.lineEdit.setGeometry(QtCore.QRect(160, 55, 221, 22))
        self.lineEdit.setFont(font)
        self.lineEdit.setInputMethodHints(QtCore.Qt.ImhEmailCharactersOnly)
        self.lineEdit.setMaxLength(40)
        self.lineEdit.setObjectName("lineEdit")

        # Email body input
        self.lineEdit_2 = QtWidgets.QLineEdit(FormJS8Mail)
        self.lineEdit_2.setGeometry(QtCore.QRect(160, 105, 481, 22))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(60)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Labels
        self.label = QtWidgets.QLabel(FormJS8Mail)
        self.label.setGeometry(QtCore.QRect(58, 55, 91, 20))
        self.label.setFont(font)
        self.label.setObjectName("label")

        self.label_2 = QtWidgets.QLabel(FormJS8Mail)
        self.label_2.setGeometry(QtCore.QRect(58, 105, 91, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        # Note about APRS email limitations
        self.note_label = QtWidgets.QLabel(FormJS8Mail)
        self.note_label.setGeometry(QtCore.QRect(58, 145, 700, 30))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(9)
        note_font.setBold(True)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #990000;")
        self.note_label.setText(
            "APRS email messages are transmitted in the subject line and are limited to 67 characters. "
            "Replies to APRS emails are not supported."
        )
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("note_label")

        # APRS email info link
        self.link_label = QtWidgets.QLabel(FormJS8Mail)
        self.link_label.setGeometry(QtCore.QRect(58, 185, 412, 24))
        self.link_label.setFont(font)
        self.link_label.setText(
            'Learn more about APRS email here: '
            '<a href="https://www.aprs-is.net/email.aspx">https://www.aprs-is.net/email.aspx</a>'
        )
        self.link_label.setOpenExternalLinks(True)
        self.link_label.setObjectName("link_label")

        # Transmit button
        self.pushButton = QtWidgets.QPushButton(FormJS8Mail)
        self.pushButton.setGeometry(QtCore.QRect(510, 220, 111, 24))
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self.transmit)

        # Cancel button
        self.pushButton_2 = QtWidgets.QPushButton(FormJS8Mail)
        self.pushButton_2.setGeometry(QtCore.QRect(630, 220, 75, 24))
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)

        self.retranslateUi(FormJS8Mail)
        QtCore.QMetaObject.connectSlotsByName(FormJS8Mail)

        # Load config and initialize API
        self._load_config()
        self.api = js8callAPIsupport.js8CallUDPAPICalls(
            self.server_ip, int(self.server_port)
        )

    def retranslateUi(self, FormJS8Mail: QtWidgets.QWidget) -> None:
        """Set UI text labels."""
        _translate = QtCore.QCoreApplication.translate
        FormJS8Mail.setWindowTitle(_translate("FormJS8Mail", "CommStat-Improved JS8Mail"))
        self.label.setText(_translate("FormJS8Mail", "Email Address : "))
        self.label_2.setText(_translate("FormJS8Mail", "Subject :"))
        self.pushButton.setText(_translate("FormJS8Mail", "Transmit"))
        self.pushButton_2.setText(_translate("FormJS8Mail", "Cancel"))

    def _load_config(self) -> None:
        """Load server configuration from config.ini."""
        self.server_ip = "127.0.0.1"
        self.server_port = "2242"

        if os.path.exists("config.ini"):
            config = ConfigParser()
            config.read("config.ini")
            if "DIRECTEDCONFIG" in config:
                self.server_ip = config["DIRECTEDCONFIG"].get("server", "127.0.0.1")
                self.server_port = config["DIRECTEDCONFIG"].get("UDP_port", "2242")

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

    def transmit(self) -> None:
        """Validate and transmit the email."""
        email = self.lineEdit.text().strip()
        body = self.lineEdit_2.text().strip()

        # Validate email address
        if len(email) < MIN_EMAIL_LENGTH or not re.match(EMAIL_PATTERN, email):
            self._show_error("Email address is not valid!")
            return

        # Validate subject length
        if len(body) < MIN_SUBJECT_LENGTH:
            self._show_error(f"Subject is too short (minimum {MIN_SUBJECT_LENGTH} characters)!")
            return

        # Build and send message
        email_cmd = "@APRSIS CMD :EMAIL-2  :"
        email_tail = "{03}"
        message = f"{email_cmd}{email} {body}{email_tail}"

        message_type = js8callAPIsupport.TYPE_TX_SETMESSAGE
        self._send_message(message_type, message)

        self._show_info(f"CommStat-Improved will transmit:\n{message}")
        self.MainWindow.close()

    def _send_message(self, message_type: str, message_text: str) -> None:
        """Send message via JS8Call API."""
        self.api.sendMessage(message_type, message_text)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    FormJS8Mail = QtWidgets.QWidget()
    ui = Ui_FormJS8Mail()
    ui.setupUi(FormJS8Mail)
    FormJS8Mail.show()
    sys.exit(app.exec_())
