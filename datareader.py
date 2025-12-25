# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
"""
datareader.py - Message parser for CommStat-Improved

Parses DIRECTED.TXT from JS8Call and writes structured data to traffic.db3.
Identifies message types by markers and extracts relevant fields.
"""

import os
import platform
import shutil
import sqlite3
import sys
import subprocess
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QDateTime
import maidenhead as mh

# Initialize Windows terminal colors
os.system('')

# Message type markers
MSG_BULLETIN = "{^%}"
MSG_STATREP = "{&%}"
MSG_FORWARDED_STATREP = "{F%}"
MSG_MARQUEE = "{*%}"
MSG_CHECKIN = "{~%}"
MSG_CS_REQUEST = "CS?"

# Field count requirements for each message type
FIELD_COUNT_BULLETIN = 9
FIELD_COUNT_STATREP = 12
FIELD_COUNT_FORWARDED_STATREP = 13
FIELD_COUNT_MARQUEE = 10
FIELD_COUNT_CHECKIN = 10

# Valid values for condition fields
VALID_CONDITIONS = ["1", "2", "3", "4"]
VALID_STATUS = ["1", "2", "3"]
VALID_PRECEDENCE = ["1", "2", "3", "4", "5"]

# Precedence code to description mapping
PRECEDENCE_MAP = {
    "1": "My Location",
    "2": "My Community",
    "3": "My County",
    "4": "My Region",
    "5": "Other Location"
}

# Database file
DATABASE_FILE = "traffic.db3"
CONFIG_FILE = "config.ini"
DIRECTED_COPY = "copyDIRECTED.TXT"


class TerminalColors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[00m"


def print_green(text: str) -> None:
    """Print text in green."""
    print(f"{TerminalColors.GREEN}{text}{TerminalColors.RESET}")


def print_yellow(text: str) -> None:
    """Print text in yellow."""
    print(f"{TerminalColors.YELLOW}{text}{TerminalColors.RESET}")


def print_red(text: str) -> None:
    """Print text in red."""
    print(f"{TerminalColors.RED}{text}{TerminalColors.RESET}")


class Config:
    """Application configuration loaded from config.ini."""

    def __init__(self):
        self.callsign: str = ""
        self.callsign_suffix: str = ""
        self.group1: str = ""
        self.group2: str = ""
        self.grid: str = ""
        self.path: str = ""
        self.selected_group: str = ""
        self._log_os_info()
        self.load()

    def _log_os_info(self) -> None:
        """Log operating system information."""
        print(f"Datareader: {platform.system()} OS detected")

    def load(self) -> bool:
        """Load configuration from config.ini."""
        if not os.path.exists(CONFIG_FILE):
            msg = QMessageBox()
            msg.setWindowTitle("CommStat-Improved error")
            msg.setText("Config file is missing!")
            msg.setIcon(QMessageBox.Critical)
            msg.exec_()
            return False

        config = ConfigParser()
        config.read(CONFIG_FILE)

        userinfo = config["USERINFO"]
        self.callsign = userinfo.get("callsign", "")
        self.callsign_suffix = userinfo.get("callsignsuffix", "")
        self.group1 = userinfo.get("group1", "")
        self.group2 = userinfo.get("group2", "")
        self.grid = userinfo.get("grid", "")
        self.selected_group = userinfo.get("selectedgroup", "")

        # If group2 is too short, use group1
        if len(self.group2) < 4:
            self.group2 = self.group1

        systeminfo = config["DIRECTEDCONFIG"]
        self.path = systeminfo.get("path", "")

        return True

    @property
    def directed_path(self) -> str:
        """Full path to DIRECTED.TXT file."""
        return os.path.join(self.path, "DIRECTED.TXT")


class MessageParser:
    """Parses JS8Call directed messages and writes to database."""

    def __init__(self, config: Config):
        self.config = config
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self.last_processed_time: Optional[str] = None  # Track last processed timestamp

    def _open_db(self) -> None:
        """Open database connection."""
        self.conn = sqlite3.connect(DATABASE_FILE)
        self.cursor = self.conn.cursor()

    def _close_db(self) -> None:
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        self.conn = None
        self.cursor = None

    @staticmethod
    def extract_callsign(message_part: str) -> str:
        """
        Extract callsign from message component.

        Handles formats like 'CALLSIGN/SUFFIX: ...' or 'CALLSIGN: ...'
        """
        # Split by colon to get callsign portion
        parts = message_part.split(':')
        callsign_with_suffix = parts[0] if parts else ""

        # Split by slash to remove suffix
        parts = callsign_with_suffix.split('/')
        return parts[0] if parts else ""

    @staticmethod
    def validate_field(value: str, valid_values: List[str], field_name: str,
                       message: str, is_forwarded: bool = False) -> bool:
        """
        Validate a field value against allowed values.

        Returns True if valid, False otherwise.
        """
        if value not in valid_values:
            prefix = "Forwarded " if is_forwarded else ""
            print_red(f"{prefix}StatRep failed for null {field_name} field: {message}\n")
            return False
        return True

    @staticmethod
    def parse_statrep_fields(srcode: str) -> Optional[Dict[str, str]]:
        """
        Parse the 12-character status code into individual fields.

        Returns dict of field values or None if invalid.
        """
        if len(srcode) < 12:
            return None

        fields = list(srcode)
        return {
            'status': fields[0],
            'commpwr': fields[1],
            'pubwtr': fields[2],
            'med': fields[3],
            'ota': fields[4],
            'trav': fields[5],
            'net': fields[6],
            'fuel': fields[7],
            'food': fields[8],
            'crime': fields[9],
            'civil': fields[10],
            'pol': fields[11]
        }

    def validate_statrep_fields(self, fields: Dict[str, str], message: str,
                                 is_forwarded: bool = False) -> bool:
        """Validate all statrep condition fields."""
        # Status has different valid values for regular vs forwarded
        status_valid = VALID_CONDITIONS if is_forwarded else VALID_STATUS

        validations = [
            (fields['status'], status_valid, 'status'),
            (fields['commpwr'], VALID_CONDITIONS, 'commpwr'),
            (fields['pubwtr'], VALID_CONDITIONS, 'pubwtr'),
            (fields['med'], VALID_CONDITIONS, 'med'),
            (fields['ota'], VALID_CONDITIONS, 'ota'),
            (fields['trav'], VALID_CONDITIONS, 'trav'),
            (fields['net'], VALID_CONDITIONS, 'net'),
            (fields['fuel'], VALID_CONDITIONS, 'fuel'),
            (fields['food'], VALID_CONDITIONS, 'food'),
            (fields['crime'], VALID_CONDITIONS, 'crime'),
            (fields['civil'], VALID_CONDITIONS, 'civil'),
            (fields['pol'], VALID_CONDITIONS, 'pol'),
        ]

        for value, valid_values, field_name in validations:
            if not self.validate_field(value, valid_values, field_name, message, is_forwarded):
                return False

        return True

    def copy_directed(self) -> bool:
        """Copy DIRECTED.TXT to working copy."""
        try:
            shutil.copy2(self.config.directed_path, DIRECTED_COPY)
            return True
        except Exception as e:
            print_red(f"Failed to copy DIRECTED.TXT: {e}")
            return False

    def _get_line_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from the beginning of a line."""
        try:
            parts = line.split('\t')
            if parts:
                return parts[0]
        except Exception:
            pass
        return None

    def parse(self) -> int:
        """
        Parse the copied DIRECTED.TXT file and write to database.

        Returns:
            Number of new lines processed
        """
        if not os.path.exists(DIRECTED_COPY):
            print_red(f"{DIRECTED_COPY} not found")
            return 0

        self._open_db()
        new_lines_processed = 0
        newest_time = self.last_processed_time

        try:
            with open(DIRECTED_COPY, "r") as f:
                lines = f.readlines()

            # Process last 50 lines
            last_lines = lines[-50:]

            for line in last_lines:
                # Get timestamp from line
                line_time = self._get_line_timestamp(line)

                # Skip if already processed (timestamp <= last_processed_time)
                if line_time and self.last_processed_time:
                    if line_time <= self.last_processed_time:
                        continue

                # Process this line
                self._process_line(line)
                new_lines_processed += 1

                # Track the newest timestamp we've seen
                if line_time:
                    if newest_time is None or line_time > newest_time:
                        newest_time = line_time

        except Exception as e:
            print_red(f"Error parsing directed file: {e}")

        finally:
            self._close_db()

        # Update last processed time
        if newest_time:
            self.last_processed_time = newest_time

        return new_lines_processed

    def _process_line(self, line: str) -> None:
        """Process a single line from DIRECTED.TXT."""
        try:
            # Check if line contains selected group
            if self.config.selected_group not in line:
                self._handle_non_group_message(line)
                return

            current_group = self.config.selected_group

            # Determine message type and process
            if MSG_BULLETIN in line:
                self._process_bulletin(line, current_group)
            elif MSG_FORWARDED_STATREP in line:
                self._process_forwarded_statrep(line, current_group)
            elif MSG_STATREP in line:
                self._process_statrep(line, current_group)
            elif MSG_MARQUEE in line:
                self._process_marquee(line, current_group)
            elif MSG_CS_REQUEST in line:
                self._process_cs_request(line)
            elif MSG_CHECKIN in line:
                self._process_checkin(line, current_group)
            else:
                self._handle_unrecognized_message(line)

        except IndexError:
            print_red(line.rstrip())
            print(f"Received string failed index criteria, msg not parsed into database\n")

    def _parse_base_fields(self, line: str) -> Tuple[str, List[str], str]:
        """
        Parse common fields from a message line.

        Returns (utc, arr2, callsign) tuple.
        """
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')
        callsign = self.extract_callsign(arr2[0])
        return utc, arr2, callsign

    def _process_bulletin(self, line: str, group: str) -> None:
        """Process a bulletin message."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != FIELD_COUNT_BULLETIN:
            return

        id_num = arr2[1]
        callsign = self.extract_callsign(arr2[0])
        bulletin = arr2[2]

        self.cursor.execute(
            "INSERT OR REPLACE INTO bulletins_Data (datetime, idnum, groupid, callsign, message) "
            "VALUES(?, ?, ?, ?, ?)",
            (utc, id_num, group, callsign, bulletin)
        )
        self.conn.commit()

        print_green(line.rstrip())
        print_green(f"Added Bulletin from: {callsign} ID: {id_num}")
        print_yellow(f"Attempting to add callsign: {callsign} to members list")

    def _process_statrep(self, line: str, group: str) -> None:
        """Process a statrep message."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != FIELD_COUNT_STATREP:
            print_red(f"StatRep message failed field count, missing fields\n{line}\n")
            return

        callsign = self.extract_callsign(arr2[0])
        curgrid = arr2[1]
        prec1 = arr2[2]

        # Validate precedence
        if prec1 not in VALID_PRECEDENCE:
            print_red(f"StatRep failed for null precedence field: {line}\n")
            return

        prec = PRECEDENCE_MAP.get(prec1, "Unknown")
        srid = arr2[3]
        srcode = arr2[4]

        # Parse and validate condition fields
        fields = self.parse_statrep_fields(srcode)
        if not fields:
            print_red(f"StatRep failed - invalid status code: {line}\n")
            return

        if not self.validate_statrep_fields(fields, line, is_forwarded=False):
            return

        comments = arr2[5] if len(arr2) > 5 else ""

        self.cursor.execute(
            "INSERT OR REPLACE INTO Statrep_Data "
            "(datetime, callsign, groupname, grid, SRid, prec, status, commpwr, pubwtr, "
            "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (utc, callsign, group, curgrid, srid, prec, fields['status'], fields['commpwr'],
             fields['pubwtr'], fields['med'], fields['ota'], fields['trav'], fields['net'],
             fields['fuel'], fields['food'], fields['crime'], fields['civil'], fields['pol'], comments)
        )
        self.conn.commit()

        print_green(line.rstrip())
        print_green(f"Added StatRep from: {callsign} ID: {srid}")

    def _process_forwarded_statrep(self, line: str, group: str) -> None:
        """Process a forwarded statrep message."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != FIELD_COUNT_FORWARDED_STATREP:
            print_red(f"StatRep forwarded message failed field count, missing fields\n{line}\n")
            return

        callsign = self.extract_callsign(arr2[0])
        curgrid = arr2[1]
        prec1 = arr2[2]
        orig_call = arr2[6]

        # Validate precedence
        if prec1 not in VALID_PRECEDENCE:
            print_red(f"Forwarded StatRep failed for null precedence field: {line}\n")
            return

        prec = PRECEDENCE_MAP.get(prec1, "Unknown")
        srid = arr2[3]
        srcode = arr2[4]

        # Parse and validate condition fields
        fields = self.parse_statrep_fields(srcode)
        if not fields:
            print_red(f"Forwarded StatRep failed - invalid status code: {line}\n")
            return

        if not self.validate_statrep_fields(fields, line, is_forwarded=True):
            return

        comments = arr2[5] if len(arr2) > 5 else ""

        self.cursor.execute(
            "INSERT OR REPLACE INTO Statrep_Data "
            "(datetime, callsign, groupname, grid, SRid, prec, status, commpwr, pubwtr, "
            "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (utc, orig_call, group, curgrid, srid, prec, fields['status'], fields['commpwr'],
             fields['pubwtr'], fields['med'], fields['ota'], fields['trav'], fields['net'],
             fields['fuel'], fields['food'], fields['crime'], fields['civil'], fields['pol'], comments)
        )
        self.conn.commit()

        print_green(line.rstrip())
        print_green(f"Added Forwarded StatRep from: {orig_call} ID: {srid}")

    def _process_marquee(self, line: str, group: str) -> None:
        """Process a marquee message."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != FIELD_COUNT_MARQUEE:
            return

        id_num = arr2[1]
        callsign = self.extract_callsign(arr2[0])
        color = arr2[2]
        marquee = arr2[3]

        print_yellow(f"Received marquee to be written - id: {id_num} callsign: {callsign} "
                     f"groupname: {group} time: {utc} color: {color} message: {marquee}")

        self.cursor.execute(
            "INSERT OR REPLACE INTO marquees_Data (idnum, callsign, groupname, date, color, message) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (id_num, callsign, group, utc, color, marquee)
        )
        self.conn.commit()

        print_green(line.rstrip())
        print_green(f"Added Marquee from: {callsign} ID: {id_num}")

    def _process_cs_request(self, line: str) -> None:
        """Process a CS (CommStat-Improved) request."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != 6:
            return

        callsign = self.extract_callsign(arr2[0])
        print_yellow(f"Received CS Request to be responded to - from {callsign}")

        subprocess.run([sys.executable, "csresponder.py", utc])

    def _process_checkin(self, line: str, group: str) -> None:
        """Process a check-in message."""
        arr = line.split('\t')
        utc = arr[0]
        callsignmix = arr[4]
        arr2 = callsignmix.split(',')

        # Validate field count
        count = len(arr) + len(arr2)
        if count != FIELD_COUNT_CHECKIN:
            print_red(line.rstrip())
            print_red(f"Check in field count: {count} - 10 fields required, CommStat-Improved cannot process this check in\n")
            return

        callsign = self.extract_callsign(arr2[0])
        traffic = arr2[1]
        state = arr2[2]
        grid = arr2[3]

        # Convert grid to coordinates
        if len(grid) == 6:
            coords = mh.to_location(grid)
        else:
            coords = mh.to_location(grid, center=True)

        testlat = float(coords[0])
        testlong = float(coords[1])

        # Check for duplicate grids and offset
        rows_query = f"SELECT Count() FROM members_Data WHERE grid = '{grid}'"
        self.cursor.execute(rows_query)
        num_rows = self.cursor.fetchone()[0]

        if num_rows > 1:
            testlat = testlat + (num_rows * 0.010)
            testlong = testlong + (num_rows * 0.010)

        # Insert into members_Data
        self.cursor.execute(
            "INSERT OR REPLACE INTO members_Data "
            "(date, callsign, groupname1, groupname2, gridlat, gridlong, state, grid) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (utc, callsign, self.config.group1, self.config.group2, testlat, testlong, state, grid)
        )
        self.conn.commit()

        # Insert into checkins_Data
        self.cursor.execute(
            "INSERT OR IGNORE INTO checkins_Data "
            "(date, callsign, groupname, traffic, gridlat, gridlong, state, grid) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (utc, callsign, group, traffic, testlat, testlong, state, grid)
        )
        self.conn.commit()

        print_green(line.rstrip())
        print_green(f"Added Check in from callsign: {callsign}")
        print_yellow("Attempting to add or update callsign to members list")

    def _handle_non_group_message(self, line: str) -> None:
        """Handle messages that don't match the selected group."""
        try:
            arr = line.split('\t')
            if len(arr) > 4:
                callsignmix = arr[4]
                arr2 = callsignmix.split(',')
                callsign = self.extract_callsign(arr2[0])

                if 3 < len(callsign) < 7:
                    print_red(line.rstrip())
                    print_red("Failed CommStat-Improved msg criteria, incorrect group or possibly not a CommStat-Improved msg")
        except Exception:
            print(line)
            print("An exception occurred with the above string, nothing could be done with this")

    def _handle_unrecognized_message(self, line: str) -> None:
        """Handle messages that don't match any known type."""
        try:
            arr = line.split('\t')
            if len(arr) > 4:
                callsignmix = arr[4]
                arr2 = callsignmix.split(',')
                callsign = self.extract_callsign(arr2[0])

                if 3 < len(callsign) < 7:
                    print_red(line.rstrip())
                    print_red("Failed CommStat-Improved criteria, probably not a CommStat-Improved msg")
                else:
                    print_red(line.rstrip())
                    print_red("Failed callsign structure criteria, msg not parsed into database\n")
        except IndexError:
            print_red(line.rstrip())
            print_red(f"Failed CommStat-Improved index criteria, probably not a CommStat-Improved msg not parsed into database")


def run() -> None:
    """Main entry point - copy and parse DIRECTED.TXT."""
    config = Config()
    parser = MessageParser(config)

    if parser.copy_directed():
        parser.parse()

    now = QDateTime.currentDateTime()
    now_str = now.toUTC().toString("yyyy-MM-dd HH:mm:ss")
    print(f"Datareader stopped: {now_str}")


if __name__ == "__main__":
    run()
