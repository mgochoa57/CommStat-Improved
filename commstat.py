
# comment: mod to make directed not wrap but scroll. Only mod and have not updated versions on the CS Responder as I wait to see if I add more mods. Changed "zoom_start..." to 3 to see if full USA map holds as CS refreshes. Map size has been increased and recentered and zoomed now 1.0.7.4
# comment: 2.0.0 offline map for Net Manager and Members list.
# comment: 2.1.0 added a click to view_statrep. Click on a map pin or statrep.
# 2.1.1 added a text filed to a displayed statrep. Allowing a brevity report to be pasted in then saved to the html output
# comment: 2.2 added brevity entry and decode
# comment: 2.3 added GridFinder
import subprocess
import sys
import webbrowser
from random import randint
import feedparser
from file_read_backwards import FileReadBackwards
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QIcon, QColor, QCursor
from PyQt5.QtWidgets import QApplication, QGridLayout, QMainWindow, QPlainTextEdit, QWidget, QTableWidget, QTableWidgetItem, QMenu, \
    QAction, qApp, QScrollArea, QLabel, QDialog, QInputDialog, QMessageBox
from PyQt5.QtCore import QUrl, QTime, QTimer, QDateTime, Qt, pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile, QWebEnginePage
import io
import folium
import sqlite3
import os
import socket
import settings
from settings import Ui_FormSettings
from configparser import ConfigParser
import threading
from subprocess import call
import time
from js8mail import Ui_FormJS8Mail
from js8sms import Ui_FormJS8SMS
from statrep import Ui_FormStatRep
from bulletin import Ui_FormBull
from marquee import Ui_FormMarquee
from checkin import Ui_FormCheckin
from members import Ui_FormMembers
from heardlist import Ui_FormHeard
from statack import Ui_FormStatack
from about import Ui_FormAbout
import platform
import maidenhead as mh
import http.server
import socketserver

# Define the handler to serve files from the 'tilesPNG2' directory
class TileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="tilesPNG2", **kwargs)

# Function to start the local server
def start_local_server(port=8000):
    ports = [port, port + 1]  # Try default port and next port
    for p in ports:
        try:
            with socketserver.TCPServer(("", p), TileHandler) as httpd:
                print(f"Serving at port {p}")
                httpd.serve_forever()
            return p  # Return the successful port
        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"Port {p} is in use, trying next port...")
                continue
            raise
    print("Failed to start server: all ports in use")
    return None

callsign = ""
callsignSuffix = ""
group1 = ""
group2 = ""
grid = ""
path = ""
selectedgroup = ""
counter = 0
directedcounter = 0
statreprwcnt = 0
bulletinrwcnt = 0
marqueerwcnt = 0
heardrwcnt = 0
dbcounter = 0
mapper = ""
directedsize = 0
data = ""
map_flag = 0
OS = ""
bull1 = 1
bull2 = 3
OS_Directed = ""

statelist = ['AP', 'AO', 'BO', 'CN', 'CM', 'CO', 'DN', 'DM', 'DL', 'DO', 'EN', 'EM','EL','EO','FN','FM','FO']
start = '2023-01-01 05:00'
end = '2030-02-23 00:56'
green = True
yellow = True
red = True
grids = statelist
loadflag = 0

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.path().startswith("/statrep/"):
            srid = url.path().replace("/statrep/", "").strip()
            if srid:
                try:
                    view_statrep_path = os.path.join(os.getcwd(), "view_statrep.py")
                    subprocess.Popen([sys.executable, view_statrep_path, srid])
                    print(f"Launched view_statrep.py with SRid: {srid}")
                except Exception as e:
                    print(f"Failed to launch view_statrep.py: {e}")
            return False  # Prevent navigation
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

class Ui_MainWindow(QWidget):
    def __init__(self):
        super(Ui_MainWindow, self).__init__()
        # Start the server in a separate thread
        self.server_thread = threading.Thread(target=start_local_server)
        self.server_thread.daemon = True  # Daemonize thread to ensure it exits when the main program does
        self.server_thread.start()

    def setupUi(self, MainWindow):
        global marqueecolor
        global bull1
        global bull2
        global green
        global yellow
        global red
        global start
        global end
        global grids

        self.oscheck()
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1480, 788)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("USA-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        MainWindow.setWindowIcon(icon)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout_2 = QtWidgets.QGridLayout(self.centralwidget)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.label = QtWidgets.QLabel(self.centralwidget)
        self.label.setMinimumSize(QtCore.QSize(400, 30))
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(12)
        font.setBold(False)
        self.label.setFont(font)
        self.label.setAutoFillBackground(False)

        self.label.setStyleSheet("background-color: rgb(0, 0, 0);\n"
                                   "color: rgb(0, 200, 0);")

        self.label.setObjectName("label")
        self.gridLayout_2.addWidget(self.label, 0,0, 1, 3, QtCore.Qt.AlignCenter)
        self.label_2 = QtWidgets.QLabel(self.centralwidget)

        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(12)
        font.setBold(False)
        self.label_2.setFont(font)
        self.label_2.setAutoFillBackground(False)
        self.label_2.setStyleSheet("background-color: rgb(0, 0, 0);\n"
                                   "color: rgb(0, 200, 0);")
        self.label_2.setObjectName("label_2")

        # Time label
        self.label_time = QtWidgets.QLabel(self.centralwidget)
        font_time = QtGui.QFont()
        font_time.setFamily("Arial")
        font_time.setPointSize(10)
        font_time.setBold(True)
        self.label_time.setFont(font_time)
        self.label_time.setStyleSheet("color: rgb(0, 0, 0);")
        self.label_time.setText("Time:        ")
        self.gridLayout_2.addWidget(self.label_time, 0, 2, 1, 1, QtCore.Qt.AlignRight)
        self.gridLayout_2.addWidget(self.label_2, 0, 3, 1, 1)
        self.label_3 = QtWidgets.QLabel(self.centralwidget)
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        font.setBold(True)
        self.label_3.setFont(font)
        self.label_3.setObjectName("label_3")
        self.gridLayout_2.addWidget(self.label_3, 0, 0, 1, 1)
        self.label_3.setText("Current Group : AMMRRON")

        self.readconfig()

        self.tableWidget = QtWidgets.QTableWidget(self.centralwidget)
        self.tableWidget.setObjectName("tableWidget")
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(0)
        # Connect itemClicked signal for left-click with chooser
        self.tableWidget.itemClicked.connect(self.handleTableClick)
        self.gridLayout_2.addWidget(self.tableWidget, 1, 0, 1, 5)

        if "1" in green:
            greenstat = "ON"
        else:
            greenstat = "OFF"
        if "2" in yellow:
            yellowstat = "ON"
        else:
            yellowstat = "OFF"
        if "3" in red:
            redstat = "ON"
        else:
            redstat = "OFF"

        self.label_start = QtWidgets.QLabel(self.centralwidget)
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(9)
        font.setBold(False)
        self.label_start.setFont(font)
        self.label_start.setObjectName("label_start")
        self.gridLayout_2.addWidget(self.label_start, 2, 0, 1, 1)
        self.label_start.setText("Filters : Start : "+start+"  |  End : "+end+"| Green : "+greenstat+" |  Yellow : "+yellowstat+" |")

        self.label_filters = QtWidgets.QLabel(self.centralwidget)
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(9)
        font.setBold(False)
        self.label_filters.setFont(font)
        self.label_filters.setObjectName("label_start")
        self.gridLayout_2.addWidget(self.label_filters, 2, 1, 1, 3)
        self.label_filters.setText(" Red : "+redstat+" |  Grids : "+grids)

        self.plainTextEdit = QtWidgets.QPlainTextEdit(self.centralwidget)
        self.plainTextEdit.setObjectName("plainTextEdit")
        self.plainTextEdit.setFont(font)

        # Set word wrap mode to NoWrap
        self.plainTextEdit.setWordWrapMode(QtGui.QTextOption.NoWrap)

        # Enable vertical and horizontal scrollbars
        self.plainTextEdit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.plainTextEdit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.gridLayout_2.addWidget(self.plainTextEdit, 3, 2, 1, 3)

        self.widget = QWebEngineView(self.centralwidget)
        self.setObjectName("widget")
        # Set custom QWebEnginePage to handle statrep URLs
        custom_page = CustomWebEnginePage(self)
        self.widget.setPage(custom_page)
        self.gridLayout_2.addWidget(self.widget, 3, 0, 2, 2)

        self.tableWidget_2 = QtWidgets.QTableWidget(self.centralwidget)
        self.tableWidget_2.setObjectName("tableWidget_2")
        self.tableWidget_2.setColumnCount(0)
        self.tableWidget_2.setRowCount(0)
        self.gridLayout_2.addWidget(self.tableWidget_2, 4, 2, 1, 3)

        self.gridLayout_2.setRowStretch(0, 0)
        self.gridLayout_2.setRowStretch(1, 1)
        self.gridLayout_2.setRowStretch(4, 1)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 886, 22))
        self.menubar.setObjectName("menubar")
        self.menuEXIT = QtWidgets.QMenu(self.menubar)
        self.menuEXIT.setObjectName("menuEXIT")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.actionJS8EMAIL = QtWidgets.QAction(MainWindow)
        self.actionJS8EMAIL.setObjectName("actionJS8EMAIL")
        self.actionJS8SMS = QtWidgets.QAction(MainWindow)
        self.actionJS8SMS.setObjectName("actionJS8SMS")
        self.actionSTATREP = QtWidgets.QAction(MainWindow)
        self.actionSTATREP.setObjectName("actionSTATREP")

        self.actionNET_CHECK_IN = QtWidgets.QAction(MainWindow)
        self.actionNET_CHECK_IN.setObjectName("actionNET_CHECK_IN")

        self.actionFilter = QtWidgets.QAction(MainWindow)
        self.actionFilter.setObjectName("actionFilter")

        self.actionData = QtWidgets.QAction(MainWindow)
        self.actionData.setObjectName("actionData")

        self.actionMEMBER_LIST = QtWidgets.QAction(MainWindow)
        self.actionMEMBER_LIST.setObjectName("actionMEMBER_LIST")

        self.actionSTATREP_ACK = QtWidgets.QAction(MainWindow)
        self.actionSTATREP_ACK.setObjectName("actionSTATREP_ACK")
        self.actionNET_ROSTER = QtWidgets.QAction(MainWindow)
        self.actionNET_ROSTER.setObjectName("actionNET_ROSTER")
        self.actionNEW_MARQUEE = QtWidgets.QAction(MainWindow)
        self.actionNEW_MARQUEE.setObjectName("actionNEW_MARQUEE")
        self.actionFLASH_BULLETIN = QtWidgets.QAction(MainWindow)
        self.actionFLASH_BULLETIN.setObjectName("actionFLASH_BULLETIN")
        self.actionSETTINGS = QtWidgets.QAction(MainWindow)
        self.actionSETTINGS.setObjectName("actionSETTINGS")
        
        self.actionHELP = QtWidgets.QAction(MainWindow)
        self.actionHELP.setObjectName("actionHELP")
        self.actionABOUT = QtWidgets.QAction(MainWindow)
        self.actionABOUT.setObjectName("actionABOUT")

        self.actionEXIT_2 = QtWidgets.QAction(MainWindow)
        self.actionEXIT_2.setObjectName("actionEXIT_2")

        self.menuEXIT.addAction(self.actionJS8EMAIL)
        self.actionJS8EMAIL.triggered.connect(self.js8email_window)
        self.menuEXIT.addAction(self.actionJS8SMS)
        self.actionJS8SMS.triggered.connect(self.js8sms_window)
        self.menuEXIT.addAction(self.actionSTATREP)
        self.actionSTATREP.triggered.connect(self.statrep_window)
        self.menuEXIT.addAction(self.actionNET_CHECK_IN)
        self.actionNET_CHECK_IN.triggered.connect(self.checkin_window)

        self.menuEXIT.addAction(self.actionMEMBER_LIST)
        self.actionMEMBER_LIST.triggered.connect(self.members_window)

        self.menuEXIT.addSeparator()
        self.menuEXIT.addAction(self.actionSTATREP_ACK)
        self.actionSTATREP_ACK.triggered.connect(self.statack_window)
        self.menuEXIT.addAction(self.actionNET_ROSTER)
        self.actionNET_ROSTER.triggered.connect(self.thread_netmanage)
        self.menuEXIT.addAction(self.actionNEW_MARQUEE)
        self.actionNEW_MARQUEE.triggered.connect(self.marquee_window)
        self.menuEXIT.addAction(self.actionFLASH_BULLETIN)
        self.actionFLASH_BULLETIN.triggered.connect(self.bull_window)
        self.menuEXIT.addSeparator()

        self.menuEXIT.addAction(self.actionFilter)
        self.actionFilter.triggered.connect(self.filter_window)

        self.menuEXIT.addAction(self.actionData)
        self.actionData.triggered.connect(self.data_window)

        self.menuEXIT.addAction(self.actionSETTINGS)
        self.actionSETTINGS.triggered.connect(self.settings_window)

        self.menuEXIT.addAction(self.actionHELP)
        self.actionHELP.triggered.connect(self.open_webbrowser)
        self.menuEXIT.addAction(self.actionABOUT)
        self.actionABOUT.triggered.connect(self.about_window)

        self.menuEXIT.addSeparator()
        self.menuEXIT.addAction(self.actionEXIT_2)
        self.actionEXIT_2.triggered.connect(qApp.quit)
        self.menubar.addAction(self.menuEXIT.menuAction())

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        timer = QTimer(self)
        timer.timeout.connect(self.showTime)
        timer.start(1000) # update every second
        self.showTime()

        self.timeLine = QtCore.QTimeLine()
        self.timeLine.setCurveShape(QtCore.QTimeLine.LinearCurve)
        self.timeLine.frameChanged.connect(self.setText)
        self.timeLine.finished.connect(self.nextNews)
        self.signalMapper = QtCore.QSignalMapper(self)
        
        self.oscheck()

        self.feed()
        self.filetest()

    def handleTableClick(self, item):
        """Handle left-click on tableWidget with a chooser dialog positioned near the mouse."""
        row = item.row()
        if row >= 0:
            srid = self.tableWidget.item(row, 1).text()
            msg = QMessageBox()
            msg.setWindowTitle("View StatRep")
            msg.setText(f"View StatRep for SRid {srid}?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.Yes)
            # Position dialog near mouse cursor
            mouse_pos = QCursor.pos()
            msg.move(mouse_pos.x() + 10, mouse_pos.y() + 10)  # Offset slightly for visibility
            response = msg.exec_()
            if response == QMessageBox.Yes:
                try:
                    view_statrep_path = os.path.join(os.getcwd(), "view_statrep.py")
                    subprocess.Popen([sys.executable, view_statrep_path, srid])
                    print(f"Launched view_statrep.py with SRid: {srid}")
                except Exception as e:
                    print(f"Failed to launch view_statrep.py: {e}")

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "CommStat-Improved V 2.3.1 / Modified by N0DDK"))
        self.actionFilter.setText(_translate("MainWindow", "DISPLAY FILTER"))
        self.actionData.setText(_translate("MainWindow", "DATA MANAGER"))
        self.label.setText(_translate("MainWindow", "TextLabel Marquee"))
        self.label_2.setText(_translate("MainWindow", "TextLabel Clock"))
        self.menuEXIT.setTitle(_translate("MainWindow", "MENU"))
        self.actionJS8EMAIL.setText(_translate("MainWindow", "JS8EMAIL"))
        self.actionJS8SMS.setText(_translate("MainWindow", "JS8SMS"))
        self.actionSTATREP.setText(_translate("MainWindow", "STATREP"))
        self.actionNET_CHECK_IN.setText(_translate("MainWindow", "NET CHECK IN"))
        self.actionMEMBER_LIST.setText(_translate("MainWindow", "MEMBER LIST"))
        self.actionSTATREP_ACK.setText(_translate("MainWindow", "STATREP ACK"))
        self.actionNET_ROSTER.setText(_translate("MainWindow", "NET MANAGER"))
        self.actionNEW_MARQUEE.setText(_translate("MainWindow", "NEW MARQUEE"))
        self.actionFLASH_BULLETIN.setText(_translate("MainWindow", "FLASH BULLETIN"))
        self.actionSETTINGS.setText(_translate("MainWindow", "SETTINGS"))
        self.actionHELP.setText(_translate("MainWindow", "HELP"))
        self.actionABOUT.setText(_translate("MainWindow", "ABOUT"))
        self.actionEXIT_2.setText(_translate("MainWindow", "EXIT"))

    def oscheck(self):
        global OS
        global bull1
        global bull2
        global OS_Directed
        pios = "aarch64"
        winos = "Windows"
        linuxos = "Linux"
        if pios in (platform.platform()):
            print("Commstat this is Pi 64bit OS")
            OS = "pi"
            bull1 = 0
            bull2 = 4
        if winos in (platform.platform()):
            print("Commstat this is Windows OS")
            OS_Directed = r"\DIRECTED.TXT"
        if linuxos in (platform.platform()):
            print("Commstat this is Linux OS")
            OS_Directed = "/DIRECTED.TXT"
        else:
            print("Commstat operating System is :" + platform.platform())
            print("Commstat Python version is :" + platform.python_version())

    def readconfig(self):
        config_object = ConfigParser()
        config_object.read("config.ini")
        global callsign
        global callsignSuffix
        global group1
        global group2
        global grid
        global path
        global selectedgroup
        global OS_Directed
        global start
        global end
        global green
        global yellow
        global red
        global grids

        userinfo = config_object["USERINFO"]
        systeminfo = config_object["DIRECTEDCONFIG"]
        filter = config_object["FILTER"]

        callsign = format(userinfo["callsign"])
        callsignSuffix = format(userinfo["callsignsuffix"])
        group1 = format(userinfo["group1"])
        group2 = format(userinfo["group2"])
        grid = format(userinfo["grid"])
        path1 = format(systeminfo["path"])
        path = (path1+""+OS_Directed)
        selectedgroup = format(userinfo["selectedgroup"])
        start = format(filter["start"])
        end = format(filter["end"])
        green = format(filter["green"])
        yellow = format(filter["yellow"])
        red = format(filter["red"])
        grids = format(filter["grids"])

        if (callsign =="NOCALL"):
            self.settings_window()

    def filetest(self):
        global path
        global directedsize
        pathlocal = path
        status = os.stat(path)
        statussize = status.st_size
        if statussize != directedsize:
            directedsize = statussize
            self.directed()
            QtCore.QTimer.singleShot(3000, self.directed)
            QtCore.QTimer.singleShot(30000, self.filetest)
        else:
            QtCore.QTimer.singleShot(30000, self.filetest)

    def help_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormSettings()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def settings_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormSettings()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def js8email_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormJS8Mail()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def js8sms_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormJS8SMS()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def statrep_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormStatRep()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def bull_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormBull()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def marquee_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormMarquee()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def checkin_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormCheckin()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def filter_window(self):
        result = subprocess.run([sys.executable, "filter.py"])
        print(result)
        self.loadData()
        self.run_mapper()

    def data_window(self):
        result = subprocess.run([sys.executable, "commdata.py"])
        print(result)

    def members_window(self):
        subprocess.call([sys.executable, "members.py"])

    def statack_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormStatack()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def thread_netmanage(self):
        t5 = threading.Thread(target=self.netmanager_window)
        t5.start()

    def netmanager_window(self):
        subprocess.call([sys.executable, "netmanager.py"])

    def about_window(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormAbout()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    
    def loadData(self):
        self.readconfig()
        global statelist
        global start
        global end
        global green
        global yellow
        global red
        global grids
        global selectedgroup
        print(start)
        print(end)
        print("colors :" + red + " " + yellow + " " + green)
        if "1" in green:
            greenstat = "ON"
        else:
            greenstat = "OFF"
        if "2" in yellow:
            yellowstat = "ON"
        else:
            yellowstat = "OFF"
        if "3" in red:
            redstat = "ON"
        else:
            redstat = "OFF"

        self.label_start.setText("Filters : Start : " + start + "  |  End : " + end + "| Green : " + greenstat + " |  Yellow : " + yellowstat + " |")
        self.label_filters.setText(" Red : " + redstat + " |  Grids : " + grids)

        try:
            with sqlite3.connect('traffic.db3', timeout=10) as connection:
                cursor = connection.cursor()
                query = ("""
                    SELECT StatRep_Data.datetime, StatRep_Data.SRid, StatRep_Data.callsign, StatRep_Data.grid,
                           StatRep_Data.prec, StatRep_Data.status, StatRep_Data.commpwr, StatRep_Data.pubwtr,
                           StatRep_Data.med, StatRep_Data.ota, StatRep_Data.trav, StatRep_Data.net,
                           StatRep_Data.fuel, StatRep_Data.food, StatRep_Data.crime, StatRep_Data.civil,
                           StatRep_Data.political, StatRep_Data.comments
                    FROM StatRep_Data
                    WHERE StatRep_Data.groupname = ? AND (StatRep_Data.status = ? OR StatRep_Data.status = ? OR StatRep_Data.status = ?)
                    AND StatRep_Data.datetime BETWEEN ? AND ? AND substr(StatRep_Data.grid, 1, 2) IN ({})
                """.format(', '.join('?' for _ in statelist)))
                cursor.execute(query, [selectedgroup, green, yellow, red, start, end] + statelist)
                result = cursor.fetchall()

                self.tableWidget.setRowCount(0)
                self.tableWidget.setColumnCount(18)
                for row_number, row_data in enumerate(result):
                    self.tableWidget.insertRow(row_number)
                    for column_number, data in enumerate(row_data):  # Include all columns
                        item = QTableWidgetItem(str(data) if data is not None else "")
                        # Apply existing color logic for status columns
                        if data in ["1", "2", "3", "4"]:
                            if data == "1":
                                item.setBackground(QColor(0, 128, 0))
                                item.setForeground(QColor(0, 128, 0))
                            elif data == "2":
                                item.setBackground(QColor(255, 255, 0))
                                item.setForeground(QColor(255, 255, 0))
                            elif data == "3":
                                item.setBackground(QColor(255, 0, 0))
                                item.setForeground(QColor(255, 0, 0))
                            elif data == "4":
                                item.setBackground(QColor(128, 128, 128))
                                item.setForeground(QColor(128, 128, 128))
                        self.tableWidget.setItem(row_number, column_number, item)

                table = self.tableWidget
                table.setHorizontalHeaderLabels(
                    str("Date Time UTC ;ID ;Callsign; Grid ; Scope; Map Pin; Pow; H2O; Med; Com; Trv; Int; Fuel; Food; Cri; Civ; Pol; Remarks").split(";"))
                header = table.horizontalHeader()
                header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
                header.setStretchLastSection(True)
                self.tableWidget.verticalHeader().setVisible(False)
                self.tableWidget.sortItems(0, QtCore.Qt.DescendingOrder)
        except sqlite3.Error as error:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load StatRep data: {error}")


    def directedpi(self):
        global directedcounter
        with open(path) as f, open('output.txt', 'w') as fout:
            fout.writelines(reversed(f.readlines()))
        text = open('output.txt').read()
        text_edit_widget = QPlainTextEdit(text)
        if directedcounter > 1:
            self.plainTextEdit.setPlainText(text)
        else:
            self.plainTextEdit.setPlainText(text)
        directedcounter += 1
        print("Directed completed : counter :" + str(directedcounter))

        self.loadbulletins()
        self.loadData()
        self.run_mapper()
        self.thread()

        self.label_3.setText(" Active Group: " + selectedgroup)

    def directed(self):
        global directedcounter
        with open(path) as f, open('output.txt', 'w') as fout:
            fout.writelines(reversed(f.readlines()))
        text = open('output.txt').read()
        text_edit_widget = QPlainTextEdit(text)
        if directedcounter > 1:
            self.plainTextEdit.setPlainText(text)
        else:
            self.plainTextEdit.setPlainText(text)
        directedcounter += 1
        print("Directed completed : counter :" + str(directedcounter))

        self.loadbulletins()
        self.loadData()
        self.run_mapper()
        self.thread()

        self.label_3.setText(" Active Group : " + selectedgroup)

    def mapperWidget(self):
        global mapper
        global data
        global map_flag
        global statelist
        global start
        global end
        global green
        global yellow
        global red
        global grids
        global selectedgroup

        gridlist = []
        coordinate = (38.8199286, -96.7782551)
        m = folium.Map(
            zoom_start=4,
            location=coordinate
        )

        # Add local tile layer
        folium.raster_layers.TileLayer(
            tiles='http://localhost:8000/{z}/{x}/{y}.png',
            name='Local Tiles',
            attr='Local Tiles',
            max_zoom=19,
            control=True
        ).add_to(m)

        try:
            connection = sqlite3.connect('traffic.db3')
            cursor = connection.cursor()
            query = (
                "SELECT callsign, SRid, status, grid FROM StatRep_Data WHERE groupname = ? AND (status = ? OR status = ? OR status = ?) AND datetime BETWEEN ? AND ? AND substr(grid,1,2) IN ({})".format(
                    ', '.join('?' for _ in statelist)))
            cursor = connection.execute(query, [selectedgroup, green, yellow, red, start, end] + statelist)
            items = cursor.fetchall()

            for item in items:
                call = item[0]
                srid = item[1]
                status = item[2]
                grid = item[3]
                coords = mh.to_location(grid, center=True)
                testlat = float(coords[0])
                testlong = float(coords[1])
                count = gridlist.count(grid)
                if count > 0:
                    testlat = testlat + (count * .010)
                    testlong = testlong + (count * .010)
                gridlist.append(grid)
                testlat = float(testlat)
                testlong = float(testlong)

                glat = testlat
                glon = testlong

                pinstring = ("Callsign :")
                html = '''<HTML>
                            <BODY>
                                <p style="color:blue;font-size:14px;">
                                    %s %s<br>
                                    StatRep ID: %s<br>
                                    <button onclick="window.location.href='http://localhost/statrep/%s'" style="color:#0000FF;font-family:Arial;font-size:12px;font-weight:bold;cursor:pointer;border:1px solid #000;padding:2px 5px;">View StatRep</button>
                                </p>
                            </BODY>
                          </HTML>''' % (pinstring, call, srid, srid)
                iframe = folium.IFrame(html, width=160, height=100)
                popup = folium.Popup(iframe, min_width=100, max_width=160)

                color = "black"  # Default color
                radius = 5
                filler = True

                if status == "1":
                    color = "green"
                    radius = 5
                elif status == "2":
                    color = "orange"
                    radius = 10
                elif status == "3":
                    color = "red"
                    radius = 10

                folium.CircleMarker(radius=radius, fill=filler, color=color, fill_color=color, location=[glat, glon], popup=popup).add_to(m)

            cursor.close()

        except sqlite3.Error as error:
            print("Failed to read data from sqlite table", error)
        finally:
            if (connection):
                connection.close()

        data = io.BytesIO()
        m.save(data, close_file=False)

        if map_flag == 1:
            self.widget.reload()
        else:
            self.widget.setHtml(data.getvalue().decode())
            map_flag = 0

    def run_mapper(self):
        global mapper
        global data
        global os
        if "Pi" in OS:
            print("\n \n OS is Pi map is removed \n \n ")
        else:
            self.mapperWidget()
            print("\n \n OS is not Pi \n \n ")

    def loadbulletins(self):
        self.readconfig()
        connection = sqlite3.connect('traffic.db3')
        query = "SELECT datetime, idnum, callsign, message FROM bulletins_Data where groupid = ?"
        result = connection.execute(query, (selectedgroup,))
        self.tableWidget_2.setRowCount(0)
        self.tableWidget_2.setColumnCount(4)
        for row_number, row_data in enumerate(result):
            self.tableWidget_2.insertRow(row_number)
            for column_number, data in enumerate(row_data):
                self.tableWidget_2.setItem(row_number, column_number, QTableWidgetItem(str(data)))
        table = self.tableWidget_2
        table.setHorizontalHeaderLabels(
            str("Date Time UTC ;ID ;Callsign; Bulletin ;").split(
                ";"))
        header = table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.tableWidget_2.verticalHeader().setVisible(False)
        self.tableWidget_2.sortItems(0, QtCore.Qt.DescendingOrder)
        connection.close()

    def thread_second():
        call(["python", "datareader.py"])

    def showTime(self):
        now = QDateTime.currentDateTime()
        displayTxt = now.toUTC().toString(" yyyy-MM-dd   hh:mm:ss 'Z'")
        self.label_2.setText(" " + displayTxt + " ")

    def thread(self):
        t1 = threading.Thread(target=self.Operation)
        t1.start()

    def Operation(self):
        global counter
        now = QDateTime.currentDateTime()
        displayTxt = (now.toUTC().toString(Qt.ISODate))
        print("Time Datatreader Start :" + displayTxt)
        counter += 1
        print("Thread counter = " + str(counter))
        subprocess.call([sys.executable, "datareader.py"])

    def feed(self):
        marqueegreen = "color: rgb(0, 200, 0);"
        marqueeyellow = "color: rgb(255, 255, 0);"
        marqueered = "color: rgb(255, 0, 0);"
        connection = sqlite3.connect('traffic.db3')
        query = "SELECT * FROM marquees_data WHERE groupname = ? ORDER BY date DESC LIMIT 1"
        result = connection.execute(query, (selectedgroup,))
        result = result.fetchall()

        callSend = (result[0][2])
        id = (result[0][1])
        group = (result[0][3])
        date = (result[0][4])
        msg = (result[0][6])
        color = (result[0][5])
        if (color == "2"):
            self.label.setStyleSheet("background-color: rgb(0, 0, 0);\n"
                                     "" + marqueered + "")
        elif (color == "1"):
            self.label.setStyleSheet("background-color: rgb(0, 0, 0);\n"
                                     "" + marqueeyellow + "")
        else:
            self.label.setStyleSheet("background-color: rgb(0, 0, 0);\n"
                                     "" + marqueegreen + "")

        marqueetext = (" ID " + id + " Received  : " + date + "  From : " + group + " by : " + callSend + " MSG : " + msg)
        connection.close()
        fm = self.label.fontMetrics()
        self.nl = int(self.label.width() / fm.averageCharWidth())
        news = [marqueetext]
        appendix = ' ' * self.nl
        news.append(appendix)
        delimiter = '      +++      '
        self.news = delimiter.join(news)
        newsLength = len(self.news)
        lps = 5
        dur = newsLength * 500 / lps
        self.timeLine.setDuration(20000)
        self.timeLine.setFrameRange(0, newsLength)
        self.timeLine.start()

    def setText(self, number_of_frame):
        if number_of_frame < self.nl:
            start = 0
        else:
            start = number_of_frame - self.nl
        text = '{}'.format(self.news[start:number_of_frame])
        self.label.setText(text)
        self.label.setFixedWidth(400)

    def nextNews(self):
        self.feed()
        self.timeLine.start()

    def setTlText(self, text):
        string = '{} pressed'.format(text)
        self.textLabel.setText(string)

    def open_webbrowser(self):
        webbrowser.open('CommStat_Help.pdf')

if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())