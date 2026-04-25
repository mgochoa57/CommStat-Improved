# Copyright (c) 2025, 2026 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

import sys
import sqlite3
import webbrowser
import os
import re
from datetime import datetime
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QWidget, QMessageBox, QPushButton, QTextEdit,
)
from PyQt5.QtCore import Qt
import html
import brevity1

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER, COLOR_BTN_BLUE,
)

# =============================================================================
# Constants
# =============================================================================

_PROG_BG     = DEFAULT_COLORS.get("program_background", "#000000")
_PROG_FG     = DEFAULT_COLORS.get("program_foreground", "#FFFFFF")
_DATA_BG     = DEFAULT_COLORS.get("data_background",    "#F8F6F4")
_COND_GREEN  = DEFAULT_COLORS.get("condition_green",    "#28A745")
_COND_YELLOW = DEFAULT_COLORS.get("condition_yellow",   "#FFFF77")
_COND_RED    = DEFAULT_COLORS.get("condition_red",      "#DC3534")
_COND_GRAY   = DEFAULT_COLORS.get("condition_gray",     "#6C757D")


# =============================================================================
# Helpers
# =============================================================================

def _lbl_font() -> QtGui.QFont:
    return QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)


def _mono_font() -> QtGui.QFont:
    return QtGui.QFont("Kode Mono")


def _btn(label: str, color: str, min_w: int = 120) -> QPushButton:
    b = QPushButton(label)
    b.setMinimumWidth(min_w)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; border:none;"
        f" padding:6px 14px; border-radius:4px; font-family:Roboto; font-size:15px;"
        f" font-weight:bold; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
    )
    return b


# =============================================================================
# StatRep Detail Dialog
# =============================================================================

class StatRepDialog(QDialog):
    def __init__(self, srid):
        super().__init__()
        self.srid = srid
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("StatRep Details")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.setMinimumSize(560, 600)
        self.resize(650, 640)

        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        self.setStyleSheet(f"""
            QDialog {{ background-color: {_DATA_BG}; }}
            QScrollArea {{ background-color: {_DATA_BG}; border: none; }}
            QWidget#scroll_widget {{ background-color: {_DATA_BG}; }}
            QFrame {{ background-color: {_DATA_BG}; border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; }}
            QLabel {{ color: {COLOR_INPUT_TEXT}; background-color: transparent; font-size: 13px; }}
            QTextEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px; padding: 4px;
                font-family: 'Kode Mono'; font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("STATREP DETAILS")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setObjectName("scroll_widget")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(8)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # ── General Information ────────────────────────────────────────────────
        general_frame = QFrame()
        general_layout = QVBoxLayout(general_frame)

        general_header = QLabel("General Information")
        general_header.setFont(_lbl_font())
        general_header.setAlignment(Qt.AlignCenter)
        general_layout.addWidget(general_header)

        form_layout = QGridLayout()
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)

        def _field_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(_lbl_font())
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return lbl

        def _data_label() -> QLabel:
            lbl = QLabel()
            lbl.setFont(_mono_font())
            return lbl

        self.datetime_label = _data_label()
        form_layout.addWidget(_field_label("Date Time UTC:"), 0, 0)
        form_layout.addWidget(self.datetime_label, 0, 1)

        self.callsign_label = _data_label()
        form_layout.addWidget(_field_label("Callsign:"), 1, 0)
        form_layout.addWidget(self.callsign_label, 1, 1)

        self.scope_label = _data_label()
        form_layout.addWidget(_field_label("Scope:"), 2, 0)
        form_layout.addWidget(self.scope_label, 2, 1)

        self.srid_label = _data_label()
        form_layout.addWidget(_field_label("ID:"), 0, 2)
        form_layout.addWidget(self.srid_label, 0, 3)

        self.grid_label = _data_label()
        form_layout.addWidget(_field_label("Grid:"), 1, 2)
        form_layout.addWidget(self.grid_label, 1, 3)

        general_layout.addLayout(form_layout)
        scroll_layout.addWidget(general_frame)

        # ── Situational Status ─────────────────────────────────────────────────
        situational_frame = QFrame()
        situational_layout = QVBoxLayout(situational_frame)

        situational_fields = [
            ("Map Pin", "map"), ("Pow", "power"), ("H2O", "water"),
            ("Med", "med"),     ("Com", "telecom"), ("Trv", "travel"),
            ("Int", "internet"), ("Fuel", "fuel"),  ("Food", "food"),
            ("Cri", "crime"),   ("Civ", "civil"),   ("Pol", "political"),
        ]
        self.situational_labels = {}
        self.situational_values = {}

        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(3)

        for idx, (label_text, field) in enumerate(situational_fields):
            name_label = QLabel(label_text)
            name_label.setFont(_lbl_font())
            name_label.setAlignment(Qt.AlignCenter)
            grid_layout.addWidget(name_label, 0, idx)

            value_label = QLabel()
            value_label.setFont(_mono_font())
            value_label.setFixedSize(30, 30)
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet("border: 2px solid black; border-radius: 2px;")
            grid_layout.addWidget(value_label, 1, idx)
            self.situational_labels[field] = value_label

        situational_layout.addLayout(grid_layout)
        scroll_layout.addWidget(situational_frame)

        # ── Remarks ────────────────────────────────────────────────────────────
        remarks_frame = QFrame()
        remarks_layout = QVBoxLayout(remarks_frame)

        remarks_header = QLabel("Remarks:")
        remarks_header.setFont(_lbl_font())
        remarks_layout.addWidget(remarks_header)

        self.remarks_label = QLabel()
        self.remarks_label.setFont(_mono_font())
        self.remarks_label.setWordWrap(True)
        self.remarks_label.setStyleSheet(
            f"background-color: white; border: 1px solid {COLOR_INPUT_BORDER};"
            f" border-radius: 4px; padding: 4px; color: {COLOR_INPUT_TEXT};"
        )
        remarks_layout.addWidget(self.remarks_label)
        scroll_layout.addWidget(remarks_frame)

        # ── Brevity Decode ─────────────────────────────────────────────────────
        brevity_frame = QFrame()
        brevity_layout = QVBoxLayout(brevity_frame)

        brevity_header = QLabel("Brevity Decode:")
        brevity_header.setFont(_lbl_font())
        brevity_layout.addWidget(brevity_header)

        self.brevity_text = QTextEdit()
        self.brevity_text.setFont(_mono_font())
        self.brevity_text.setPlaceholderText("Brevity codes decoded here...")
        self.brevity_text.setMinimumHeight(120)
        brevity_layout.addWidget(self.brevity_text)
        scroll_layout.addWidget(brevity_frame)

        # ── Button row ─────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.view_html_button = _btn("View/Save HTML", COLOR_BTN_BLUE)
        self.view_html_button.clicked.connect(self._view_html)
        btn_row.addWidget(self.view_html_button)
        scroll_layout.addLayout(btn_row)

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self._load_data()

    # -------------------------------------------------------------------------
    # Data loading
    # -------------------------------------------------------------------------

    def _load_data(self):
        try:
            with sqlite3.connect('traffic.db3', timeout=10) as connection:
                cursor = connection.cursor()
                query = (
                    "SELECT datetime, sr_id, from_callsign, grid, scope, map, power, water, med, telecom, travel, internet, "
                    "fuel, food, crime, civil, political, comments FROM statrep WHERE id = ?"
                )
                cursor.execute(query, (self.srid,))
                result = cursor.fetchone()
                if result:
                    self.datetime_label.setText(str(result[0]))
                    self.srid_label.setText(str(result[1]))
                    self.callsign_label.setText(str(result[2]))
                    self.grid_label.setText(str(result[3]))
                    self.scope_label.setText(str(result[4]))

                    for idx, field in enumerate(["map", "power", "water", "med", "telecom", "travel",
                                                 "internet", "fuel", "food", "crime", "civil", "political"]):
                        value = str(result[5 + idx])
                        label = self.situational_labels[field]
                        label.setText(value)
                        self.situational_values[field] = value
                        if value == "1":
                            label.setStyleSheet(f"background-color:{_COND_GREEN}; color:{_COND_GREEN}; border:2px solid black; border-radius:2px;")
                            label.setToolTip("Green: Normal")
                        elif value == "2":
                            label.setStyleSheet(f"background-color:{_COND_YELLOW}; color:{_COND_YELLOW}; border:2px solid black; border-radius:2px;")
                            label.setToolTip("Yellow: Warning")
                        elif value == "3":
                            label.setStyleSheet(f"background-color:{_COND_RED}; color:{_COND_RED}; border:2px solid black; border-radius:2px;")
                            label.setToolTip("Red: Critical")
                        elif value == "4":
                            label.setStyleSheet(f"background-color:{_COND_GRAY}; color:{_COND_GRAY}; border:2px solid black; border-radius:2px;")
                            label.setToolTip("Gray: Unknown")
                        else:
                            label.setStyleSheet(f"background-color:white; color:{COLOR_INPUT_TEXT}; border:2px solid black; border-radius:2px;")
                            label.setToolTip("No status")

                    remarks = str(result[17]) or "No remarks"
                    self.remarks_label.setText(remarks)

                    # Decode brevity codes
                    brevity_codes = re.findall(r'\b[0-9][A-Z]{5}\b', remarks)
                    decoded_html = ""
                    if brevity_codes:
                        try:
                            decoded_reports = []
                            for code in brevity_codes:
                                brevity_report = brevity1.decode_to_report(code)
                                if brevity_report.startswith("Error") or brevity_report.startswith("Invalid"):
                                    decoded_reports.append(f"<p>{html.escape(code)}: {html.escape(brevity_report)}</p>")
                                    continue
                                list_id = code[0]
                                emergency_code = code[1]
                                status_code = code[2]
                                primary_code = code[3]
                                secondary_code = code[4]
                                severity_code = code[5]
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
                                narrative = brevity1.generate_narrative(description_parts, emergency_code, primary_code, secondary_code, severity_code, status_code, code, list_id)
                                gui_titles = positions.get("gui_titles", {})
                                emergency_title = gui_titles.get("emergency", "Event:")
                                status_title    = gui_titles.get("status",    "Status or Target:")
                                primary_title   = gui_titles.get("primary",   "Impact:")
                                secondary_title = gui_titles.get("secondary", "Response:")
                                severity_title  = gui_titles.get("severity",  "Station Status:")
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
                                full_report_html = (
                                    f"<b>{html.escape(code)}:</b><br>"
                                    f"{formatted_brevity_html}<br><br>"
                                    f"<b>Detailed Narrative:</b><br>{formatted_narrative_html}"
                                )
                                decoded_reports.append(full_report_html)
                            decoded_html = "<br><br>".join(decoded_reports)
                        except Exception as e:
                            decoded_html = f"<p>Error decoding brevity codes: {html.escape(str(e))}</p>"
                    else:
                        decoded_html = "<p>No Brevity found</p>"
                    self.brevity_text.setHtml(decoded_html)
                else:
                    QtWidgets.QMessageBox.critical(self, "Error", f"No StatRep found with id: {self.srid}")
                    self.close()
        except sqlite3.Error as error:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load StatRep data: {error}")
            self.close()

    # -------------------------------------------------------------------------
    # HTML export
    # -------------------------------------------------------------------------

    def _view_html(self):
        try:
            general_info = {
                "Date Time UTC": self.datetime_label.text(),
                "ID":            self.srid_label.text(),
                "Callsign":      self.callsign_label.text(),
                "Grid":          self.grid_label.text(),
                "Scope":         self.scope_label.text(),
            }
            situational_status = [
                ("Map Pin", self.situational_values.get("map",      "")),
                ("Pow",     self.situational_values.get("power",    "")),
                ("H2O",     self.situational_values.get("water",    "")),
                ("Med",     self.situational_values.get("med",      "")),
                ("Com",     self.situational_values.get("telecom",  "")),
                ("Trv",     self.situational_values.get("travel",   "")),
                ("Int",     self.situational_values.get("internet", "")),
                ("Fuel",    self.situational_values.get("fuel",     "")),
                ("Food",    self.situational_values.get("food",     "")),
                ("Cri",     self.situational_values.get("crime",    "")),
                ("Civ",     self.situational_values.get("civil",    "")),
                ("Pol",     self.situational_values.get("political","")),
            ]
            remarks = self.remarks_label.text()
            brevity_decode = self.brevity_text.toHtml()
            if "<p>No Brevity found</p>" in brevity_decode or "Error decoding" in brevity_decode:
                brevity_html = "<p>No brevity decode provided</p>"
            else:
                brevity_html = brevity_decode

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>CommStat - StatRep Details (sr_id: {self.srid})</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #008000; text-align: center; }}
        h2, h3 {{ color: #000000; margin-top: 15px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #000; padding: 8px; text-align: left; width: 25%; }}
        th {{ font-weight: bold; }}
        .status-box {{ display: inline-block; width: 20px; height: 20px; border: 2px solid black; vertical-align: middle; }}
        .status-1 {{ background-color: {_COND_GREEN}; }}
        .status-2 {{ background-color: {_COND_YELLOW}; }}
        .status-3 {{ background-color: {_COND_RED}; }}
        .status-4 {{ background-color: {_COND_GRAY}; }}
        .status-none {{ background-color: #FFFFFF; }}
        p {{ margin: 10px 0; }}
        pre {{ margin: 10px 0; padding: 10px; background-color: #f0f0f0; white-space: pre-wrap; }}
    </style>
</head>
<body>
    <h1>CommStat - StatRep Details (sr_id: {self.srid})</h1>
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
        <tr><th>Indicator</th><th>Status</th><th>Indicator</th><th>Status</th></tr>
"""
            for i in range(6):
                left_label, left_value   = situational_status[i]
                right_label, right_value = situational_status[i + 6] if i + 6 < len(situational_status) else ("", "")
                left_cls   = f"status-{left_value}"  if left_value  in ["1","2","3","4"] else "status-none"
                right_cls  = f"status-{right_value}" if right_value in ["1","2","3","4"] else "status-none"
                _status_text = {"1":"Normal","2":"Warning","3":"Critical","4":"Unknown"}
                left_txt   = _status_text.get(left_value,  "No status")
                right_txt  = _status_text.get(right_value, "No status")
                html_content += (
                    f"        <tr>"
                    f"<td>{left_label}</td><td><span class=\"status-box {left_cls}\"></span> {left_txt}</td>"
                    f"<td>{right_label}</td><td><span class=\"status-box {right_cls}\"></span> {right_txt}</td>"
                    f"</tr>\n"
                )

            html_content += f"""    </table>
    <h2>Remarks</h2>
    <p>{html.escape(remarks)}</p>
    <h2>Brevity Decode</h2>
    {brevity_html}
</body>
</html>
"""
            os.makedirs("html_output", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_file = os.path.join("html_output", f"statrep_{self.srid}_{timestamp}.html")
            with open(html_file, "w") as f:
                f.write(html_content)
            webbrowser.open(f"file:///{os.path.abspath(html_file)}")
        except Exception as error:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to generate or open HTML: {error}")

    # Keep legacy method name for any callers
    def viewHTML(self):
        self._view_html()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Error: sr_id not provided")
        sys.exit(1)
    app = QtWidgets.QApplication(sys.argv)
    dialog = StatRepDialog(sys.argv[1])
    dialog.show()
    sys.exit(app.exec_())
