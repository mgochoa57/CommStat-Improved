import os
import sqlite3
from configparser import ConfigParser
import re
from time import strftime
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QDateTime, Qt
from PyQt5.QtWidgets import QMessageBox
from PyQt5 import QtCore, QtGui, QtWidgets
import random
import datetime
import js8callAPIsupport
import folium
import sqlite3
import io
from datetime import timedelta
serverip = ""
serverport = ""
callsign = ""
grid = ""
selectedgroup = ""
mapper = ""

class Ui_FormMembers(object):
    def setupUi(self, FormMembers):
        #self.MainWindow = FormMembers
        FormMembers.setObjectName("FormMembers")
        FormMembers.resize(950, 678)
        font = QtGui.QFont()
        font.setPointSize(10)
        FormMembers.setFont(font)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        FormMembers.setWindowIcon(icon)
        self.gridLayout_2 = QtWidgets.QGridLayout(FormMembers)
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        self.widget = QtWidgets.QWidget(FormMembers)
        self.widget.setObjectName("widget")
        self.gridLayout.addWidget(self.widget, 0, 3, 1, 1, QtCore.Qt.AlignRight)
        self.tableWidget = QtWidgets.QTableWidget(FormMembers)
        self.tableWidget.setObjectName("tableWidget")
        #self.tableWidget.setColumnCount(0)
        #self.tableWidget.setRowCount(0)
        #self.gridLayout.addWidget(self.tableWidget, 0, 1, 1, 1)
        self.label = QtWidgets.QLabel(FormMembers)
        self.label.setObjectName("label")
        self.gridLayout.addWidget(self.label, 0, 1, 1, 1)
        self.gridLayout_2.addLayout(self.gridLayout, 0, 0, 1, 2)
        self.getConfig()
        print("loading members and mapper widget")

        self.mapperWidget()
        self.loadmembers()

        #self.MainWindow.setWindowFlags(
        #    QtCore.Qt.Window |
        #    QtCore.Qt.CustomizeWindowHint |
        #    QtCore.Qt.WindowTitleHint |
        #    QtCore.Qt.WindowCloseButtonHint |
        #    QtCore.Qt.WindowStaysOnTopHint
        #)

        self.retranslateUi(FormMembers)
        QtCore.QMetaObject.connectSlotsByName(FormMembers)





    def retranslateUi(self, FormMembers):
        _translate = QtCore.QCoreApplication.translate
        FormMembers.setWindowTitle(_translate("FormMembers", "CommStat Group Members List"))
        #self.label.setText(_translate("FormMembers", labeltext))
        

    def _get_active_group_from_db(self):
        """Get the active group from the database."""
        try:
            conn = sqlite3.connect("commstat.db")
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM Groups WHERE is_active = 1")
            result = cursor.fetchone()
            cursor.close()
            conn.close()
            if result:
                return result[0]
        except sqlite3.Error as e:
            print(f"Error reading active group from database: {e}")
        return ""

    def getConfig(self):
        global serverip
        global serverport
        global grid
        global callsign
        global selectedgroup
        if os.path.exists("config.ini"):
            config_object = ConfigParser()
            config_object.read("config.ini")
            userinfo = config_object["USERINFO"]
            systeminfo = config_object["DIRECTEDCONFIG"]
            callsign = format(userinfo["callsign"])
            callsignSuffix = format(userinfo["callsignsuffix"])
            grid = format(userinfo["grid"])
            path = format(systeminfo["path"])
            serverip = format(systeminfo["server"])
            serverport = format(systeminfo["UDP_port"])
            selectedgroup = self._get_active_group_from_db()
            labeltext = ("Currently Active Group : " + selectedgroup)
            print(labeltext)
            self.label.setText("net tezt here")
            #self.gridLayout.addWidget(self.label, 0, 2, 1, 1)
            self.label.setText( labeltext)




    def mapperWidget(self):
        global mapper
        flag = ""
        print("starting mapping")
        mapper = QWebEngineView()
        coordinate = (38.8199286, -90.4782551)

        # Create map with NO default tiles
        m = folium.Map(
            location=coordinate,
            zoom_start=4,
            tiles=None  # Disable Folium's default OpenStreetMap tiles
        )

        # Add LOCAL tile layer (tilesPNG2 directory)
        folium.raster_layers.TileLayer(
            tiles='http://localhost:8000/{z}/{x}/{y}.png',
            name='Local Tiles',
            attr='Local Tiles',
            max_zoom=8,  # Local tiles only up to zoom level 8
            control=False  # Hide layer toggle
        ).add_to(m)

        # Add ONLINE tile layer (OpenTopoMap) for zoom > 8
        folium.raster_layers.TileLayer(
            tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            name='OpenStreetMap',
            attr='OpenStreetMap',
            min_zoom=8,  # Online tiles only from zoom level 8
            control=False  # Hide layer toggle
        ).add_to(m)

        # Add map markers from database
        try:
            print("starting data pull for map")
            sqliteConnection = sqlite3.connect('traffic.db3')
            cursor = sqliteConnection.cursor()

            sqlite_select_query = 'SELECT gridlat, gridlong, callsign, date FROM members_Data WHERE groupname1=? OR groupname2=?'
            cursor.execute(sqlite_select_query, (selectedgroup, selectedgroup,))
            items = cursor.fetchall()

            for item in items:
                glat = item[0]
                glon = item[1]
                call = item[2]
                utc = item[3]

                now = QDateTime.currentDateTime()
                recent = now.addSecs(-60 * 60)
                date = recent.toUTC().toString("yyyy-MM-dd HH:mm:ss")
                flag = "N"

                if utc > date:
                    flag = "Y"

                pinstring = "Last Heard:"
                html = f'''
                <HTML><BODY>
                    <p style="color:blue;font-size:14px;">
                        {call}<br>{pinstring}<br>{utc}
                    </p>
                </BODY></HTML>
                '''
                iframe = folium.IFrame(html, width=160, height=70)
                popup = folium.Popup(iframe, min_width=100, max_width=160)

                if flag == "Y":
                    folium.CircleMarker(
                        color="green",
                        radius=10,
                        fill=True,
                        fill_color="green",
                        location=[glat, glon],
                        popup=popup
                    ).add_to(m)
                else:
                    folium.CircleMarker(
                        radius=6,
                        fill=True,
                        fill_color="darkblue",
                        location=[glat, glon],
                        popup=popup
                    ).add_to(m)

            cursor.close()

        except sqlite3.Error as error:
            print("Failed to read data from sqlite table", error)
        finally:
            if sqliteConnection:
                sqliteConnection.close()

        # Render map into QWebEngineView
        data = io.BytesIO()
        m.save(data, close_file=False)
        mapper.setHtml(data.getvalue().decode())
        self.gridLayout_2.addWidget(mapper, 2, 0, 1, 2)
        print("Mapping completed")
        self.loadmembers()

    def run_mapper(self):
        global mapper
        mapper.deleteLater()
        print("stopped previous map")
        self.mapperWidget()


    def loadmembers(self):
        #self.tableWidget = QtWidgets.QTableWidget(self.centralwidget)
        connection = sqlite3.connect('traffic.db3')
        query = "SELECT date, callsign, state, grid FROM members_Data where groupname1 = ? OR groupname2=?"
        result = connection.execute(query, (selectedgroup,selectedgroup,))

        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(4)
        for row_number, row_data in enumerate(result):
            self.tableWidget.insertRow(row_number)
            for column_number, data in enumerate(row_data):
                self.tableWidget.setItem(row_number, column_number, QtWidgets.QTableWidgetItem(str(data)))

        table = self.tableWidget

        table.setHorizontalHeaderLabels(
            str("Date Time UTC ;Callsign ;State ;Grid ").split(
                ";"))
        header = table.horizontalHeader()
        header.resizeSection(0, 220)
        header.resizeSection(1, 220)
        #header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        #header.setStretchLastSection(True)
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        # header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        # self.tableWidget = QtWidgets.QTableWidget()
        # self.addWidget(QTableWidget(table),0, 0, 1, 2)
        # self.tableWidget = QtWidgets.QTableWidget()
        #self.tableWidget.resizeColumnsToContents()
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.sortItems(0, QtCore.Qt.DescendingOrder)
        self.gridLayout.addWidget(self.tableWidget, 2, 1, 1, 3)

        #print("Load Bulletins & Marquee Completed")
        #QtCore.QTimer.singleShot(30000, self.loadbulletins)






if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    FormMembers = QtWidgets.QWidget()
    ui = Ui_FormMembers()
    ui.setupUi(FormMembers)
    FormMembers.show()
    sys.exit(app.exec_())
