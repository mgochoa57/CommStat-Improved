# Modified to display the full report (Brevity Report + Detailed Narrative) with bolded field names in Brevity Decode section
import sys
import sqlite3
import webbrowser
import os
import re
from datetime import datetime
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QGridLayout, QFormLayout, QLabel, QFrame, QScrollArea, QWidget, QMessageBox, QPushButton, QHBoxLayout, QTextEdit
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import html
import brevity1

class StatRepDialog(QDialog):
    def __init__(self, srid):
        super().__init__()
        self.srid = srid
        self.setupUi()

    def setupUi(self):
        self.setWindowTitle(f"CommStat - StatRep Details (SRid: {self.srid})")
        self.setMinimumSize(560, 600)
        self.resize(650, 600)
        self.setStyleSheet("background-color: rgb(255, 255, 255);")
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(5) # Tighter layout
        # General Information section
        general_frame = QFrame()
        general_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        general_frame.setStyleSheet("border: 1px solid rgb(255, 255, 255);")
        general_layout = QVBoxLayout(general_frame)
        general_header = QLabel("General Information")
        general_header.setFont(QFont("Arial", 11, QFont.Bold))
        general_header.setStyleSheet("color: rgb(0, 0, 0); background-color: rgb(255, 255, 255);")
        general_header.setAlignment(Qt.AlignCenter)
        general_layout.addWidget(general_header)
        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(10)
        font = QFont("Arial", 11)
        font_bold = QFont("Arial", 11, QFont.Bold)
        label_style = "color: rgb(0, 0, 0); background-color: rgb(255, 255, 255);"
        self.datetime_label = QLabel()
        self.datetime_label.setFont(font)
        self.datetime_label.setStyleSheet(label_style)
        datetime_label = QLabel("Date Time UTC:")
        datetime_label.setFont(font_bold)
        datetime_label.setStyleSheet(label_style)
        datetime_label.setAlignment(Qt.AlignRight)
        form_layout.addWidget(datetime_label, 0, 0)
        form_layout.addWidget(self.datetime_label, 0, 1)
        self.callsign_label = QLabel()
        self.callsign_label.setFont(font)
        self.callsign_label.setStyleSheet(label_style)
        callsign_label = QLabel("Callsign:")
        callsign_label.setFont(font_bold)
        callsign_label.setStyleSheet(label_style)
        callsign_label.setAlignment(Qt.AlignRight)
        form_layout.addWidget(callsign_label, 1, 0)
        form_layout.addWidget(self.callsign_label, 1, 1)
        self.prec_label = QLabel()
        self.prec_label.setFont(font)
        self.prec_label.setStyleSheet(label_style)
        prec_label = QLabel("Scope:")
        prec_label.setFont(font_bold)
        prec_label.setStyleSheet(label_style)
        prec_label.setAlignment(Qt.AlignRight)
        form_layout.addWidget(prec_label, 2, 0)
        form_layout.addWidget(self.prec_label, 2, 1)
        self.srid_label = QLabel()
        self.srid_label.setFont(font)
        self.srid_label.setStyleSheet(label_style)
        srid_label = QLabel("ID:")
        srid_label.setFont(font_bold)
        srid_label.setStyleSheet(label_style)
        srid_label.setAlignment(Qt.AlignRight)
        form_layout.addWidget(srid_label, 0, 2)
        form_layout.addWidget(self.srid_label, 0, 3)
        self.grid_label = QLabel()
        self.grid_label.setFont(font)
        self.grid_label.setStyleSheet(label_style)
        grid_label = QLabel("Grid:")
        grid_label.setFont(font_bold)
        grid_label.setStyleSheet(label_style)
        grid_label.setAlignment(Qt.AlignRight)
        form_layout.addWidget(grid_label, 1, 2)
        form_layout.addWidget(self.grid_label, 1, 3)
        general_layout.addLayout(form_layout)
        scroll_layout.addWidget(general_frame)
        # Situational Status section (no title)
        situational_frame = QFrame()
        situational_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        situational_frame.setStyleSheet("border: 1px solid rgb(255, 255, 255);")
        situational_layout = QVBoxLayout(situational_frame)
        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(3)
        situational_fields = [
            ("Map Pin", "status"),
            ("Pow", "commpwr"),
            ("H2O", "pubwtr"),
            ("Med", "med"),
            ("Com", "ota"),
            ("Trv", "trav"),
            ("Int", "net"),
            ("Fuel", "fuel"),
            ("Food", "food"),
            ("Cri", "crime"),
            ("Civ", "civil"),
            ("Pol", "political")
        ]
        self.situational_labels = {}
        self.situational_values = {}
        for idx, (label_text, field) in enumerate(situational_fields):
            name_label = QLabel(label_text)
            name_label.setFont(font)
            name_label.setStyleSheet(label_style)
            name_label.setAlignment(Qt.AlignCenter)
            grid_layout.addWidget(name_label, 0, idx * 2)
            value_label = QLabel()
            value_label.setFont(font)
            value_label.setFixedSize(30, 30)
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("border: 2px solid black;")
            grid_layout.addWidget(value_label, 1, idx * 2)
            self.situational_labels[field] = value_label
        situational_layout.addLayout(grid_layout)
        scroll_layout.addWidget(situational_frame)
        # Remarks section
        remarks_frame = QFrame()
        remarks_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        remarks_frame.setStyleSheet("border: 1px solid rgb(255, 255, 255);")
        remarks_layout = QVBoxLayout(remarks_frame)
        remarks_form_layout = QFormLayout()
        remarks_form_layout.setLabelAlignment(Qt.AlignRight)
        remarks_form_layout.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        remarks_form_layout.setSpacing(10)
        self.remarks_label = QLabel()
        self.remarks_label.setFont(QFont("Arial", 11))
        self.remarks_label.setStyleSheet("color: rgb(0, 0, 0); background-color: rgb(240, 240, 240);")
        self.remarks_label.setWordWrap(True)
        remarks_label = QLabel("Remarks:")
        remarks_label.setFont(font_bold)
        remarks_label.setStyleSheet(label_style)
        remarks_form_layout.addRow(remarks_label, self.remarks_label)
        remarks_layout.addLayout(remarks_form_layout)
        scroll_layout.addWidget(remarks_frame)
        # Brevity Decode section
        brevity_frame = QFrame()
        brevity_frame.setFrameStyle(QFrame.Box | QFrame.Plain)
        brevity_frame.setStyleSheet("border: 1px solid rgb(255, 255, 255);")
        brevity_layout = QVBoxLayout(brevity_frame)
        brevity_form_layout = QFormLayout()
        brevity_form_layout.setLabelAlignment(Qt.AlignRight)
        brevity_form_layout.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        brevity_form_layout.setSpacing(10)
        self.brevity_text = QTextEdit()
        self.brevity_text.setFont(QFont("Arial", 11))
        self.brevity_text.setStyleSheet("color: rgb(0, 0, 0); background-color: rgb(240, 240, 240);")
        # Removed setAcceptRichText(False) to allow HTML rendering
        self.brevity_text.setPlaceholderText("Brevity codes decoded here...")
        brevity_label = QLabel("Brevity Decode:")
        brevity_label.setFont(font_bold)
        brevity_label.setStyleSheet(label_style)
        brevity_form_layout.addRow(brevity_label, self.brevity_text)
        brevity_layout.addLayout(brevity_form_layout)
        scroll_layout.addWidget(brevity_frame)
        # View/Save HTML Button
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        self.view_html_button = QPushButton("View/Save HTML")
        self.view_html_button.setFont(QFont("Arial", 11))
        self.view_html_button.setStyleSheet(
            "QPushButton { border: 1px solid rgb(100, 100, 100); background-color: rgb(0, 0, 255); color: rgb(255, 255, 255); padding: 5px; }"
            "QPushButton:hover { background-color: rgb(0, 0, 200); }"
        )
        self.view_html_button.clicked.connect(self.viewHTML)
        button_layout.addWidget(self.view_html_button)
        scroll_layout.addLayout(button_layout)
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
        self.setLayout(main_layout)
        self.loadData()

    def loadData(self):
        try:
            with sqlite3.connect('traffic.db3', timeout=10) as connection:
                cursor = connection.cursor()
                query = ("SELECT datetime, SRid, callsign, grid, prec, status, commpwr, pubwtr, med, ota, trav, net, "
                         "fuel, food, crime, civil, political, comments FROM StatRep_Data WHERE SRid = ?")
                cursor.execute(query, (self.srid,))
                result = cursor.fetchone()
                if result:
                    self.datetime_label.setText(str(result[0]))
                    self.srid_label.setText(str(result[1]))
                    self.callsign_label.setText(str(result[2]))
                    self.grid_label.setText(str(result[3]))
                    self.prec_label.setText(str(result[4]))
                    for idx, field in enumerate(["status", "commpwr", "pubwtr", "med", "ota", "trav", "net", "fuel",
                                               "food", "crime", "civil", "political"]):
                        value = str(result[5 + idx])
                        label = self.situational_labels[field]
                        label.setText(value)
                        self.situational_values[field] = value
                        tooltip = ""
                        if value == "1":
                            label.setStyleSheet("background-color: rgb(0, 128, 0); color: rgb(0, 128, 0); border: 2px solid black;")
                            tooltip = "Green: Normal"
                        elif value == "2":
                            label.setStyleSheet("background-color: rgb(255, 255, 0); color: rgb(255, 255, 0); border: 2px solid black;")
                            tooltip = "Yellow: Warning"
                        elif value == "3":
                            label.setStyleSheet("background-color: rgb(255, 0, 0); color: rgb(255, 0, 0); border: 2px solid black;")
                            tooltip = "Red: Critical"
                        elif value == "4":
                            label.setStyleSheet("background-color: rgb(128, 128, 128); color: rgb(128, 128, 128); border: 2px solid black;")
                            tooltip = "Gray: Unknown"
                        else:
                            label.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); border: 2px solid black;")
                            tooltip = "No status"
                        label.setToolTip(tooltip)
                    remarks = str(result[17]) or "No remarks"
                    self.remarks_label.setText(remarks)
                    # Decode brevity codes from remarks to include both Brevity Report and Detailed Narrative with bolded field names
                    brevity_codes = re.findall(r'\b[0-9][A-Z]{5}\b', remarks)
                    decoded_html = ""
                    if brevity_codes:
                        try:
                            decoded_reports = []
                            for code in brevity_codes:
                                # Get Brevity Report
                                brevity_report = brevity1.decode_to_report(code)
                                if brevity_report.startswith("Error") or brevity_report.startswith("Invalid"):
                                    decoded_reports.append(f"<p>{html.escape(code)}: {html.escape(brevity_report)}</p>")
                                    continue
                                # Extract components from code
                                list_id = code[0]
                                emergency_code = code[1]
                                status_code = code[2]
                                primary_code = code[3]
                                secondary_code = code[4]
                                severity_code = code[5]
                                # Get description parts (replicating decode_code logic)
                                positions = brevity1.positions
                                emergency_data = None
                                emergency_group = "Unknown"
                                has_groups = any(k.startswith("***") for k in positions["emergency_type"].keys())
                                if has_groups:
                                    for group, sub_emergencies in positions["emergency_type"].items():
                                        if group.startswith("***") and emergency_code in sub_emergencies:
                                            emergency_data = sub_emergencies[emergency_code]
                                            emergency_group = group
                                            break
                                        elif group == emergency_code:
                                            emergency_data = positions["emergency_type"][emergency_code]
                                            emergency_group = "Unknown"
                                            break
                                else:
                                    if emergency_code in positions["emergency_type"]:
                                        emergency_data = positions["emergency_type"][emergency_code]
                                        emergency_group = "Unknown"
                                impacts = positions.get("shared_impacts", {})
                                valid_primary_code = False
                                primary_impact_name = "Unknown"
                                impact_group = "Unknown"
                                if isinstance(impacts, dict):
                                    if primary_code in impacts and isinstance(impacts[primary_code], dict) and "name" in impacts[primary_code]:
                                        valid_primary_code = True
                                        primary_impact_name = impacts[primary_code]["name"]
                                        impact_group = impacts[primary_code].get("group", "Unknown")
                                    else:
                                        for group, sub_impacts in impacts.items():
                                            if isinstance(sub_impacts, dict) and "items" in sub_impacts:
                                                if primary_code in sub_impacts["items"] and primary_code in impacts:
                                                    valid_primary_code = True
                                                    primary_impact_name = impacts[primary_code]["name"]
                                                    impact_group = group
                                                    break
                                description_parts = [
                                    emergency_data["name"] if emergency_code != "A" else None,
                                    primary_impact_name if primary_code != "A" else None,
                                    positions["public_reaction"][secondary_code]["name"] if secondary_code != "A" else None,
                                    positions["station_response"][severity_code]["name"] if severity_code != "A" else None,
                                    positions["status_codes"][status_code]["name"] if status_code in positions["status_codes"] else "Unknown"
                                ]
                                # Get Detailed Narrative
                                narrative = brevity1.generate_narrative(description_parts, emergency_code, primary_code, secondary_code, severity_code, status_code, code, list_id)
                                # Get gui_titles for field names
                                gui_titles = positions.get("gui_titles", {})
                                emergency_title = gui_titles.get("emergency", "Event:")
                                status_title = gui_titles.get("status", "Status or Target:")
                                primary_title = gui_titles.get("primary", "Impact:")
                                secondary_title = gui_titles.get("secondary", "Response:")
                                severity_title = gui_titles.get("severity", "Station Status:")
                                # Format Brevity Report with bold field names
                                brevity_lines = brevity_report.split('\n')
                                formatted_brevity = []
                                for line in brevity_lines:
                                    if line.startswith("Brevity Code:"):
                                        parts = line.split("File:", 1)
                                        code_part = parts[0].strip()
                                        file_part = f"File: {parts[1]}" if len(parts) > 1 else ""
                                        formatted_line = f"<b>Brevity Code:</b> {html.escape(code_part[13:].strip())}"
                                        if file_part:
                                            formatted_line += f" &nbsp;&nbsp;&nbsp;&nbsp; <b>File:</b> {html.escape(file_part[5:].strip())}"
                                        formatted_brevity.append(formatted_line)
                                    elif line.startswith(emergency_title):
                                        formatted_brevity.append(f"<b>{html.escape(emergency_title)}</b> {html.escape(line[len(emergency_title):].strip())}")
                                    elif line.startswith(status_title):
                                        formatted_brevity.append(f"<b>{html.escape(status_title)}</b> {html.escape(line[len(status_title):].strip())}")
                                    elif line.startswith(primary_title):
                                        formatted_brevity.append(f"<b>{html.escape(primary_title)}</b> {html.escape(line[len(primary_title):].strip())}")
                                    elif line.startswith(secondary_title):
                                        formatted_brevity.append(f"<b>{html.escape(secondary_title)}</b> {html.escape(line[len(secondary_title):].strip())}")
                                    elif line.startswith(severity_title):
                                        formatted_brevity.append(f"<b>{html.escape(severity_title)}</b> {html.escape(line[len(severity_title):].strip())}")
                                    else:
                                        formatted_brevity.append(html.escape(line))
                                formatted_brevity_html = "<br>".join(formatted_brevity)
                                # Format Detailed Narrative with bold field names
                                narrative_lines = narrative.split('\n')
                                formatted_narrative = []
                                for line in narrative_lines:
                                    if line.startswith("Brevity Code:"):
                                        formatted_narrative.append(f"<b>Brevity Code:</b> {html.escape(line[13:].strip())}")
                                    elif line.startswith(emergency_title.rstrip(':')):
                                        formatted_narrative.append(f"<b>{html.escape(emergency_title.rstrip(':'))}:</b> {html.escape(line[len(emergency_title.rstrip(':')):].strip())}")
                                    elif line.startswith(status_title.rstrip(':')):
                                        formatted_narrative.append(f"<b>{html.escape(status_title.rstrip(':'))}:</b> {html.escape(line[len(status_title.rstrip(':')):].strip())}")
                                    elif line.startswith(primary_title.rstrip(':')):
                                        formatted_narrative.append(f"<b>{html.escape(primary_title.rstrip(':'))}:</b> {html.escape(line[len(primary_title.rstrip(':')):].strip())}")
                                    elif line.startswith(secondary_title.rstrip(':')):
                                        formatted_narrative.append(f"<b>{html.escape(secondary_title.rstrip(':'))}:</b> {html.escape(line[len(secondary_title.rstrip(':')):].strip())}")
                                    elif line.startswith(severity_title.rstrip(':')):
                                        formatted_narrative.append(f"<b>{html.escape(severity_title.rstrip(':'))}:</b> {html.escape(line[len(severity_title.rstrip(':')):].strip())}")
                                    else:
                                        formatted_narrative.append(html.escape(line))
                                formatted_narrative_html = "<br>".join(formatted_narrative)
                                # Combine full report
                                full_report_html = f"<b>{html.escape(code)}:</b><br>{formatted_brevity_html}<br><br><b>Detailed Narrative:</b><br>{formatted_narrative_html}"
                                decoded_reports.append(full_report_html)
                            decoded_html = "<br><br>".join(decoded_reports)
                        except Exception as e:
                            decoded_html = f"<p>Error decoding brevity codes: {html.escape(str(e))}</p>"
                    else:
                        decoded_html = "<p>No Brevity found</p>"
                    self.brevity_text.setHtml(decoded_html)
                else:
                    QtWidgets.QMessageBox.critical(self, "Error", f"No StatRep found with SRid: {self.srid}")
                    self.close()
        except sqlite3.Error as error:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load StatRep data: {error}")
            self.close()

    def viewHTML(self):
        try:
            general_info = {
                "Date Time UTC": self.datetime_label.text(),
                "ID": self.srid_label.text(),
                "Callsign": self.callsign_label.text(),
                "Grid": self.grid_label.text(),
                "Scope": self.prec_label.text()
            }
            situational_status = [
                ("Map Pin", self.situational_values.get("status", "")),
                ("Pow", self.situational_values.get("commpwr", "")),
                ("H2O", self.situational_values.get("pubwtr", "")),
                ("Med", self.situational_values.get("med", "")),
                ("Com", self.situational_values.get("ota", "")),
                ("Trv", self.situational_values.get("trav", "")),
                ("Int", self.situational_values.get("net", "")),
                ("Fuel", self.situational_values.get("fuel", "")),
                ("Food", self.situational_values.get("food", "")),
                ("Cri", self.situational_values.get("crime", "")),
                ("Civ", self.situational_values.get("civil", "")),
                ("Pol", self.situational_values.get("political", ""))
            ]
            remarks = self.remarks_label.text()
            brevity_decode = self.brevity_text.toHtml()
            # Use the HTML from QTextEdit for consistency
            brevity_html = brevity_decode if brevity_decode and "<p>No Brevity found</p>" not in brevity_decode and "Error decoding" not in brevity_decode else "<p>No brevity decode provided</p>"
            if "Error decoding" in brevity_decode:
                brevity_html = f"<p>{html.escape(brevity_decode)}</p>"
        
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>CommStat - StatRep Details (SRid: {self.srid})</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    h1 {{ color: #008000; text-align: center; }}
                    h2 {{ color: #000000; }}
                    h3 {{ color: #000000; margin-top: 15px; }}
                    table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                    th, td {{ border: 1px solid #000; padding: 8px; text-align: left; width: 25%; }}
                    th {{ font-weight: bold; }}
                    .status-box {{ display: inline-block; width: 20px; height: 20px; border: 2px solid black; vertical-align: middle; }}
                    .status-1 {{ background-color: #008000; }}
                    .status-2 {{ background-color: #FFFF00; }}
                    .status-3 {{ background-color: #FF0000; }}
                    .status-4 {{ background-color: #808080; }}
                    .status-none {{ background-color: #FFFFFF; }}
                    p {{ margin: 10px 0; }}
                    pre {{ margin: 10px 0; padding: 10px; background-color: #f0f0f0; white-space: pre-wrap; }}
                </style>
            </head>
            <body>
                <h1>CommStat - StatRep Details (SRid: {self.srid})</h1>
                <h2>General Information</h2>
                <table>
                    <tr><th>Date Time UTC</th><td>{general_info['Date Time UTC']}</td></tr>
                    <tr><th>ID</th><td>{general_info['ID']}</td></tr>
                    <tr><th>Callsign</th><td>{general_info['Callsign']}</td></tr>
                    <tr><th>Grid</th><td>{general_info['Grid']}</td></tr>
                    <tr><th>Scope</th><td>{general_info['Scope']}</td></tr>
                </table>
                <h2>Situational Status</h2>
                <table>
                    <tr>
                        <th>Indicator</th>
                        <th>Status</th>
                        <th>Indicator</th>
                        <th>Status</th>
                    </tr>
            """
            # Pair indicators (first 6 and last 6) for 6 rows
            for i in range(6):
                left_label, left_value = situational_status[i]
                right_label, right_value = situational_status[i + 6] if i + 6 < len(situational_status) else ("", "")
                left_color_class = f"status-{left_value}" if left_value in ["1", "2", "3", "4"] else "status-none"
                left_status_text = {"1": "Normal", "2": "Warning", "3": "Critical", "4": "Unknown"}.get(left_value, "No status")
                right_color_class = f"status-{right_value}" if right_value in ["1", "2", "3", "4"] else "status-none"
                right_status_text = {"1": "Normal", "2": "Warning", "3": "Critical", "4": "Unknown"}.get(right_value, "No status")
                html_content += f"""
                    <tr>
                        <td>{left_label}</td>
                        <td><span class="status-box {left_color_class}"></span> {left_status_text}</td>
                        <td>{right_label}</td>
                        <td><span class="status-box {right_color_class}"></span> {right_status_text}</td>
                    </tr>
                """
            html_content += f"""
                </table>
                <h2>Remarks</h2>
                <p>{html.escape(remarks)}</p>
                <h2>Brevity Decode</h2>
                {brevity_html}
            </body>
            </html>
            """
            # Create html_output directory if it doesn't exist
            os.makedirs("html_output", exist_ok=True)
            # Generate timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_file = os.path.join("html_output", f"statrep_{self.srid}_{timestamp}.html")
            with open(html_file, "w") as f:
                f.write(html_content)
            # Use absolute path for webbrowser.open
            absolute_path = os.path.abspath(html_file)
            webbrowser.open(f"file:///{absolute_path}")
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to generate or open HTML: {error}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: SRid not provided")
        sys.exit(1)
    app = QtWidgets.QApplication(sys.argv)
    dialog = StatRepDialog(sys.argv[1])
    dialog.show()
    sys.exit(app.exec_())