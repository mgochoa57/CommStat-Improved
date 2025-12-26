# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
JS8 SMS Dialog for CommStat-Improved
Allows sending SMS messages via JS8Call APRS gateway.
"""

import os
from configparser import ConfigParser
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMessageBox
import js8callAPIsupport


# Constants
MIN_PHONE_LENGTH = 11  # 10 digits + 2 dashes (xxx-xxx-xxxx)
MIN_MESSAGE_LENGTH = 8


class Ui_FormJS8SMS:
    """JS8 SMS form for sending text messages via APRS gateway."""

    def setupUi(self, FormJS8SMS: QtWidgets.QWidget) -> None:
        """Initialize the UI components."""
        self.MainWindow = FormJS8SMS
        FormJS8SMS.setObjectName("FormJS8SMS")
        FormJS8SMS.resize(835, 280)

        # Set font
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        FormJS8SMS.setFont(font)

        # Set icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.jpg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormJS8SMS.setWindowIcon(icon)

        # Warning message
        self.warning_label = QtWidgets.QLabel(FormJS8SMS)
        self.warning_label.setGeometry(QtCore.QRect(58, 15, 700, 25))
        bold_font = QtGui.QFont()
        bold_font.setFamily("Arial")
        bold_font.setPointSize(12)
        bold_font.setBold(True)
        self.warning_label.setFont(bold_font)
        self.warning_label.setText("Sending SMS depends on APRS services being available.")
        self.warning_label.setObjectName("warning_label")

        # Phone number input
        self.lineEdit = QtWidgets.QLineEdit(FormJS8SMS)
        self.lineEdit.setGeometry(QtCore.QRect(160, 55, 113, 22))
        self.lineEdit.setFont(font)
        self.lineEdit.setObjectName("lineEdit")

        # Text message input
        self.lineEdit_2 = QtWidgets.QLineEdit(FormJS8SMS)
        self.lineEdit_2.setGeometry(QtCore.QRect(160, 105, 481, 22))
        self.lineEdit_2.setFont(font)
        self.lineEdit_2.setMaxLength(67)
        self.lineEdit_2.setObjectName("lineEdit_2")

        # Labels
        self.label = QtWidgets.QLabel(FormJS8SMS)
        self.label.setGeometry(QtCore.QRect(58, 55, 101, 20))
        self.label.setFont(font)
        self.label.setObjectName("label")

        self.label_2 = QtWidgets.QLabel(FormJS8SMS)
        self.label_2.setGeometry(QtCore.QRect(58, 105, 101, 20))
        self.label_2.setFont(font)
        self.label_2.setObjectName("label_2")

        # Note about SMS carrier opt-in
        self.note_label = QtWidgets.QLabel(FormJS8SMS)
        self.note_label.setGeometry(QtCore.QRect(58, 145, 700, 40))
        note_font = QtGui.QFont()
        note_font.setFamily("Arial")
        note_font.setPointSize(9)
        note_font.setBold(True)
        self.note_label.setFont(note_font)
        self.note_label.setStyleSheet("color: #990000;")
        self.note_label.setText(
            "Because of carrier policy, recipients must often opt in on the SMS gateway page "
            "before SMS delivery will work. This means that SMS message delivery is highly unreliable."
        )
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("note_label")

        # APRS SMS info link
        self.link_label = QtWidgets.QLabel(FormJS8SMS)
        self.link_label.setGeometry(QtCore.QRect(58, 195, 700, 24))
        self.link_label.setFont(font)
        self.link_label.setText(
            'Learn more about APRS SMS here: '
            '<a href="https://aprs.wiki/howto/">https://aprs.wiki/howto/</a>'
        )
        self.link_label.setOpenExternalLinks(True)
        self.link_label.setObjectName("link_label")

        # Transmit button
        self.pushButton = QtWidgets.QPushButton(FormJS8SMS)
        self.pushButton.setGeometry(QtCore.QRect(510, 235, 111, 24))
        self.pushButton.setFont(font)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.clicked.connect(self.transmit)

        # Cancel button
        self.pushButton_2 = QtWidgets.QPushButton(FormJS8SMS)
        self.pushButton_2.setGeometry(QtCore.QRect(630, 235, 75, 24))
        self.pushButton_2.setFont(font)
        self.pushButton_2.setObjectName("pushButton_2")
        self.pushButton_2.clicked.connect(self.MainWindow.close)

        self.retranslateUi(FormJS8SMS)
        QtCore.QMetaObject.connectSlotsByName(FormJS8SMS)

        # Load config and initialize API
        self._load_config()
        self.api = js8callAPIsupport.js8CallUDPAPICalls(
            self.server_ip, int(self.server_port)
        )

        self.MainWindow.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.CustomizeWindowHint |
            QtCore.Qt.WindowTitleHint |
            QtCore.Qt.WindowCloseButtonHint |
            QtCore.Qt.WindowStaysOnTopHint
        )

    def retranslateUi(self, FormJS8SMS: QtWidgets.QWidget) -> None:
        """Set UI text labels."""
        _translate = QtCore.QCoreApplication.translate
        FormJS8SMS.setWindowTitle(_translate("FormJS8SMS", "CommStat-Improved JS8SMS"))
        self.lineEdit.setInputMask(_translate("FormJS8SMS", "999-999-9999"))
        self.label.setText(_translate("FormJS8SMS", "Phone Number : "))
        self.label_2.setText(_translate("FormJS8SMS", "Text Message : "))
        self.pushButton.setText(_translate("FormJS8SMS", "Transmit"))
        self.pushButton_2.setText(_translate("FormJS8SMS", "Cancel"))

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
        """Validate and transmit the SMS message."""
        phone = self.lineEdit.text().strip()
        message_text = self.lineEdit_2.text().strip()

        # Validate phone number (format: xxx-xxx-xxxx = 12 chars with dashes)
        if len(phone) < MIN_PHONE_LENGTH:
            self._show_error("Phone number is not valid!")
            return

        # Validate message length
        if len(message_text) < MIN_MESSAGE_LENGTH:
            self._show_error(f"Text message is too short (minimum {MIN_MESSAGE_LENGTH} characters)!")
            return

        # Build and send message
        sms_cmd = "@APRSIS CMD :SMSGTE   :@"
        sms_tail = "{04}"
        message = f"{sms_cmd}{phone}  {message_text} {sms_tail}"

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
    FormJS8SMS = QtWidgets.QWidget()
    ui = Ui_FormJS8SMS()
    ui.setupUi(FormJS8SMS)
    FormJS8SMS.show()
    sys.exit(app.exec_())
