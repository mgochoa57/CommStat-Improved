# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
CommStat-Improved v2.5.0 - Rebuilt with best practices

A PyQt5 application for monitoring JS8Call communications,
displaying status reports, messages, and live data feeds.
"""

import sys
import os
import io
import base64
import socket
import sqlite3
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import ssl
import tempfile
import webbrowser
from datetime import datetime, timezone, timedelta
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import folium
import maidenhead as mh

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import QTimer, QDateTime, Qt
from PyQt5.QtWidgets import qApp
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from about import Ui_FormAbout
from filter import FilterDialog
from groups import GroupsDialog
from debug_features import DebugFeatures
from js8mail import JS8MailDialog
from js8sms import JS8SMSDialog
from marquee import Ui_FormMarquee
from message import Ui_FormMessage
from statrep import StatRepDialog
from connector_manager import ConnectorManager
from js8_tcp_client import TCPConnectionPool
from js8_connectors import JS8ConnectorsDialog


# =============================================================================
# Constants
# =============================================================================

VERSION = "2.5.0"
WINDOW_TITLE = f"CommStat-Improved (v{VERSION}) by N0DDK"
WINDOW_SIZE = (1440, 832)
CONFIG_FILE = "config.ini"
ICON_FILE = "radiation-32.png"
DATABASE_FILE = "traffic.db3"

# Default filter date range
DEFAULT_FILTER_START = "2023-01-01"

# Group settings
MAX_GROUP_NAME_LENGTH = 15
DEFAULT_GROUPS = ["MAGNET", "AMRRON", "PREPPERNET"]

# Map and layout dimensions
MAP_WIDTH = 604
MAP_HEIGHT = 340
FILTER_HEIGHT = 24
SLIDESHOW_INTERVAL = 1  # Minutes between image changes
_GUCCI = [
    "TGl0dGxlIEd1Y2NpIHdhcyB0aGUgYmVzdCE=",
    "QWxiZXJ0IEVpbnN0ZWluIHdhcyBnZW5pdXM=",
    "QmFydCBTaW1wc29uIGVhdCBteSBzaG9ydHMh",
    "SXNhYWMgTmV3dG9uIHNhdyB0aGUgYXBwbGU=",
    "TW96YXJ0IGNvbXBvc2VkIG1hc3RlcnBpZWNlcw==",
    "SG9tZXIgU2ltcHNvbiBsb3ZlcyBkb251dHM=",
    "TGVvbmFyZG8gcGFpbnRlZCBNb25hIExpc2E=",
    "U2hha2VzcGVhcmUgd3JvdGUgdGhlIHBsYXlz",
    "TGlzYSBTaW1wc29uIHBsYXlzIHRoZSBzYXg=",
    "QnJ1Y2UgTGVlIHdhcyBhIGxlZ2VuZCBub3c=",
    "QWJyYWhhbSBMaW5jb2xuIHdhcyBob25lc3Q=",
    "TWFyZ2UgU2ltcHNvbiBoYXMgYmx1ZSBoYWly",
    "U3RldmUgSm9icyBjaGFuZ2VkIGl0IGFsbA==",
    "TWFyaWUgQ3VyaWUgZGlzY292ZXJlZCBtb3Jl",
    "TWFnZ2llIFNpbXBzb24gbmV2ZXIgc3BlYWtz",
    "Tmlrb2xhIFRlc2xhIHdhcyB2aXNpb25hcnk=",
    "TWFyayBUd2FpbiB0b2xkIGdyZWF0IHRhbGVz",
    "V2FsdCBEaXNuZXkgbWFkZSB1cyBkcmVhbQ==",
    "QmVuamFtaW4gRnJhbmtsaW4gd2FzIHdpc2U=",
    "aHR0cHM6Ly9qczhjYWxsLWltcHJvdmVkLmNvbQ==",
]
_BACKBONE = base64.b64decode(_GUCCI[-1]).decode()
_PING = _BACKBONE + "/playlist.php"

# Internet connectivity check interval (30 minutes in ms)
INTERNET_CHECK_INTERVAL = 30 * 60 * 1000


def check_internet() -> bool:
    """
    Check internet connectivity by attempting to connect to DNS servers.

    Returns:
        True if internet is available, False otherwise.
    """
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            sock = socket.create_connection((host, 53), timeout=3)
            sock.close()
            return True
        except (socket.timeout, socket.error):
            continue
    return False


# Map and layout dimensions defaults
# MAP_WIDTH = 604
# MAP_HEIGHT = 350
# FILTER_HEIGHT = 20

# StatRep table column headers
STATREP_HEADERS = [
    "Date Time UTC", "Group", "Callsign", "Grid", "Scope", "Map Pin",
    "Powr", "H2O", "Med", "Comm", "Trvl", "Inet", "Fuel", "Food",
    "Crime", "Civil", "Pol", "Remarks"
]

# Default color scheme
DEFAULT_COLORS: Dict[str, str] = {
    'program_background': '#A52A2A',
    'program_foreground': '#FFFFFF',
    'menu_background': '#3050CC',
    'menu_foreground': '#FFFFFF',
    'title_bar_background': '#F07800',
    'title_bar_foreground': '#FFFFFF',
    'marquee_background': '#242424',
    'marquee_foreground_green': '#00FF00',
    'marquee_foreground_yellow': '#FFFF00',
    'marquee_foreground_red': '#FF00FF',
    'time_background': '#282864',
    'time_foreground': '#88CCFF',
    'condition_green': '#108010',
    'condition_yellow': '#FFFF77',
    'condition_red': '#BB0000',
    'condition_gray': '#808080',
    'data_background': '#EEEEEE',
    'data_foreground': '#000000',
    'feed_background': '#000000',
    'feed_foreground': '#FFFFFF',
}


# =============================================================================
# Tile Server for Map
# =============================================================================

class TileHandler(http.server.SimpleHTTPRequestHandler):
    """Serves map tiles from the tilesPNG2 directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="tilesPNG2", **kwargs)

    def log_message(self, format, *args):
        """Suppress logging to keep console clean."""
        pass


def start_local_server(port: int = 8000) -> Optional[int]:
    """Start a local tile server on the specified port."""
    ports = [port, port + 1]
    for p in ports:
        try:
            with socketserver.TCPServer(("", p), TileHandler) as httpd:
                print(f"Tile server running on port {p}")
                httpd.serve_forever()
            return p
        except OSError as e:
            # Address already in use: 48=macOS, 98=Linux, 10048=Windows
            if e.errno in (48, 98, 10048):
                print(f"Port {p} in use, trying next...")
                continue
            raise
    print("Failed to start tile server")
    return None


# =============================================================================
# Clickable Label for Slideshow
# =============================================================================

class ClickableLabel(QtWidgets.QLabel):
    """A QLabel that emits a clicked signal when clicked."""
    clicked = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# =============================================================================
# Custom Web Engine Page for Map Links
# =============================================================================

class CustomWebEnginePage(QWebEnginePage):
    """Handles navigation requests from the map and video player."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        """Intercept custom URL schemes for statrep links and video events."""
        url_str = url.toString()

        # Handle video-ended event
        if url_str == "commstat://video-ended":
            if hasattr(self.parent_widget, '_on_video_skip'):
                self.parent_widget._on_video_skip()
            return False  # Prevent navigation

        # Handle statrep links
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


# =============================================================================
# ConfigManager - Handles all configuration loading
# =============================================================================

class ConfigManager:
    """Manages application configuration from config.ini."""

    def __init__(self, config_path: str = CONFIG_FILE):
        """
        Initialize ConfigManager.

        Args:
            config_path: Path to the configuration file
        """
        self.config_path = Path(config_path)
        self.colors = DEFAULT_COLORS.copy()
        self.directed_config: Dict[str, str] = {}
        self.filter_settings: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file."""
        # Initialize filter settings (always reset on startup)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        self.filter_settings = {
            'start': today,
            'end': ''
        }

        # Load toggle settings from config if it exists
        if not self.config_path.exists():
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': False, 'show_every_group': False, 'hide_map': False}
            return

        config = ConfigParser()
        config.read(self.config_path)

        if config.has_section("DIRECTEDCONFIG"):
            self.directed_config = {
                'hide_heartbeat': config.getboolean("DIRECTEDCONFIG", "hide_heartbeat", fallback=False),
                'show_all_groups': config.getboolean("DIRECTEDCONFIG", "show_all_groups", fallback=False),
                'show_every_group': config.getboolean("DIRECTEDCONFIG", "show_every_group", fallback=False),
                'hide_map': config.getboolean("DIRECTEDCONFIG", "hide_map", fallback=False),
            }
        else:
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': False, 'show_every_group': False, 'hide_map': False}

    def get_color(self, key: str) -> str:
        """Get a color value by key."""
        return self.colors.get(key, '#FFFFFF')

    def get_hide_heartbeat(self) -> bool:
        """Get the hide heartbeat setting."""
        return self.directed_config.get('hide_heartbeat', False)

    def set_hide_heartbeat(self, value: bool) -> None:
        """Set and save the hide heartbeat setting."""
        self.directed_config['hide_heartbeat'] = value
        # Save to config file
        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section("DIRECTEDCONFIG"):
            config.add_section("DIRECTEDCONFIG")
        config.set("DIRECTEDCONFIG", "hide_heartbeat", str(value))
        with open(self.config_path, 'w') as f:
            config.write(f)

    def get_show_all_groups(self) -> bool:
        """Get the show all groups setting."""
        return self.directed_config.get('show_all_groups', False)

    def set_show_all_groups(self, value: bool) -> None:
        """Set and save the show all groups setting."""
        self.directed_config['show_all_groups'] = value
        # Save to config file
        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section("DIRECTEDCONFIG"):
            config.add_section("DIRECTEDCONFIG")
        config.set("DIRECTEDCONFIG", "show_all_groups", str(value))
        with open(self.config_path, 'w') as f:
            config.write(f)

    def get_hide_map(self) -> bool:
        """Get the hide map setting."""
        return self.directed_config.get('hide_map', False)

    def set_hide_map(self, value: bool) -> None:
        """Set and save the hide map setting."""
        self.directed_config['hide_map'] = value
        # Save to config file
        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section("DIRECTEDCONFIG"):
            config.add_section("DIRECTEDCONFIG")
        config.set("DIRECTEDCONFIG", "hide_map", str(value))
        with open(self.config_path, 'w') as f:
            config.write(f)

    def get_show_every_group(self) -> bool:
        """Get the show every group setting."""
        return self.directed_config.get('show_every_group', False)

    def set_show_every_group(self, value: bool) -> None:
        """Set and save the show every group setting."""
        self.directed_config['show_every_group'] = value
        # Save to config file
        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section("DIRECTEDCONFIG"):
            config.add_section("DIRECTEDCONFIG")
        config.set("DIRECTEDCONFIG", "show_every_group", str(value))
        with open(self.config_path, 'w') as f:
            config.write(f)


# =============================================================================
# DatabaseManager - Handles all database operations
# =============================================================================

class DatabaseManager:
    """Manages SQLite database operations."""

    def __init__(self, db_path: str = DATABASE_FILE):
        """
        Initialize DatabaseManager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path

    def get_statrep_data(
        self,
        groups: List[str],
        start: str,
        end: str = '',
        show_all: bool = False
    ) -> List[Tuple]:
        """
        Fetch StatRep data from database.

        Args:
            groups: List of active group names (empty list returns no data unless show_all)
            start: Start date filter (required)
            end: End date filter (optional, empty string means no upper limit)
            show_all: If True, return all statreps regardless of group

        Returns:
            List of tuples containing StatRep records
        """
        # If no active groups and not showing all, return empty list
        if not groups and not show_all:
            return []

        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()

                # Build date condition based on whether end date is provided
                if end:
                    date_condition = "datetime BETWEEN ? AND ?"
                    date_params = [start, end]
                else:
                    date_condition = "datetime >= ?"
                    date_params = [start]

                # Build query based on whether we're showing all or filtering by groups
                if show_all:
                    query = f"""
                        SELECT datetime, groupname, callsign, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM StatRep_Data
                        WHERE {date_condition}
                    """
                    params = date_params
                else:
                    # Build group filter for multiple groups
                    placeholders = ",".join("?" * len(groups))
                    query = f"""
                        SELECT datetime, groupname, callsign, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM StatRep_Data
                        WHERE groupname IN ({placeholders}) AND {date_condition}
                    """
                    params = list(groups) + date_params

                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_message_data(
        self,
        groups: List[str],
        start: str,
        end: str = '',
        show_all: bool = False
    ) -> List[Tuple]:
        """
        Fetch message data from database.

        Args:
            groups: List of active group names
            start: Start date filter (required)
            end: End date filter (optional, empty string means no upper limit)
            show_all: If True, return all messages regardless of group

        Returns:
            List of tuples containing message records
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()

                # Build date condition based on whether end date is provided
                if end:
                    date_condition = "datetime BETWEEN ? AND ?"
                    date_params = [start, end]
                else:
                    date_condition = "datetime >= ?"
                    date_params = [start]

                if show_all:
                    # Show all messages regardless of group
                    query = f"""SELECT datetime, groupid, callsign, message
                               FROM messages_Data
                               WHERE {date_condition}"""
                    params = date_params
                elif groups:
                    # Filter by active groups
                    placeholders = ",".join("?" * len(groups))
                    query = f"""SELECT datetime, groupid, callsign, message
                               FROM messages_Data
                               WHERE groupid IN ({placeholders}) AND {date_condition}"""
                    params = list(groups) + date_params
                else:
                    # No groups and not show_all - return empty
                    return []

                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_latest_marquee(self, groups: List[str]) -> Optional[Tuple]:
        """
        Fetch the latest marquee message for active groups.

        Args:
            groups: List of active group names (empty list returns None)

        Returns:
            Tuple containing marquee data or None
        """
        # If no active groups, return None
        if not groups:
            return None

        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                placeholders = ",".join("?" * len(groups))
                cursor.execute(
                    f"SELECT idnum, callsign, groupname, date, color, message FROM marquees_data WHERE groupname IN ({placeholders}) ORDER BY date DESC LIMIT 1",
                    groups
                )
                return cursor.fetchone()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return None

    def init_groups_table(self) -> None:
        """Create Groups table if it doesn't exist and seed default groups."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS Groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        comment TEXT,
                        url1 TEXT,
                        url2 TEXT,
                        date_added TEXT,
                        is_active INTEGER DEFAULT 0
                    )
                """)
                connection.commit()

                # Migrate existing table if needed (add new columns)
                self._migrate_groups_table(cursor, connection)

                # Check if table is empty
                cursor.execute("SELECT COUNT(*) FROM Groups")
                if cursor.fetchone()[0] == 0:
                    # Seed default groups, first one is active
                    today = datetime.now().strftime("%Y-%m-%d")
                    for i, group_name in enumerate(DEFAULT_GROUPS):
                        cursor.execute(
                            "INSERT INTO Groups (name, date_added, is_active) VALUES (?, ?, ?)",
                            (group_name.upper(), today, 1 if i == 0 else 0)
                        )
                    connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing Groups table: {error}")

    def _migrate_groups_table(self, cursor, connection) -> None:
        """Add new columns to Groups table if they don't exist."""
        cursor.execute("PRAGMA table_info(Groups)")
        columns = [col[1] for col in cursor.fetchall()]

        new_columns = [
            ("comment", "TEXT"),
            ("url1", "TEXT"),
            ("url2", "TEXT"),
            ("date_added", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE Groups ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to Groups table")

        connection.commit()

    def get_all_groups(self) -> List[str]:
        """Get all group names."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM Groups ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_all_groups_with_status(self) -> List[Tuple[str, bool]]:
        """Get all groups with their active status."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name, is_active FROM Groups ORDER BY name")
                return [(row[0], bool(row[1])) for row in cursor.fetchall()]
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_active_groups(self) -> List[str]:
        """Get list of all active group names."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM Groups WHERE is_active = 1 ORDER BY name")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_active_group(self) -> str:
        """Get the first active group name (for backwards compatibility)."""
        groups = self.get_active_groups()
        return groups[0] if groups else ""

    def set_group_active(self, group_name: str, active: bool) -> bool:
        """Set a group's active status (doesn't affect other groups)."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE Groups SET is_active = ? WHERE name = ?",
                    (1 if active else 0, group_name.upper())
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def set_active_group(self, group_name: str) -> bool:
        """Set a group as the only active group (deactivates others)."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                # Deactivate all groups
                cursor.execute("UPDATE Groups SET is_active = 0")
                # Activate the selected group
                cursor.execute(
                    "UPDATE Groups SET is_active = 1 WHERE name = ?",
                    (group_name.upper(),)
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def add_group(self, group_name: str, comment: str = "", url1: str = "", url2: str = "") -> bool:
        """Add a new group with optional fields. Returns True if successful."""
        name = group_name.strip().upper()[:MAX_GROUP_NAME_LENGTH]
        if not name:
            return False
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                cursor.execute(
                    "INSERT INTO Groups (name, comment, url1, url2, date_added, is_active) VALUES (?, ?, ?, ?, ?, 0)",
                    (name, comment.strip(), url1.strip(), url2.strip(), today)
                )
                connection.commit()
                return True
        except sqlite3.IntegrityError:
            # Duplicate name
            return False
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def update_group(self, group_name: str, comment: str = "", url1: str = "", url2: str = "") -> bool:
        """Update an existing group's fields. Returns True if successful."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE Groups SET comment = ?, url1 = ?, url2 = ? WHERE name = ?",
                    (comment.strip(), url1.strip(), url2.strip(), group_name.upper())
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def get_group_details(self, group_name: str) -> Optional[Dict]:
        """Get full details of a group."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT name, comment, url1, url2, date_added, is_active FROM Groups WHERE name = ?",
                    (group_name.upper(),)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "name": row[0],
                        "comment": row[1] or "",
                        "url1": row[2] or "",
                        "url2": row[3] or "",
                        "date_added": row[4] or "",
                        "is_active": bool(row[5])
                    }
                return None
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return None

    def get_all_groups_details(self) -> List[Dict]:
        """Get full details of all groups, sorted by name."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT name, comment, url1, url2, date_added FROM Groups ORDER BY name"
                )
                rows = cursor.fetchall()
                return [
                    {
                        "name": row[0],
                        "comment": row[1] or "",
                        "url1": row[2] or "",
                        "url2": row[3] or "",
                        "date_added": row[4] or ""
                    }
                    for row in rows
                ]
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def remove_group(self, group_name: str) -> bool:
        """Remove a group. Returns True if successful."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                # Delete the group (no longer require at least one group)
                cursor.execute(
                    "DELETE FROM Groups WHERE name = ?",
                    (group_name.upper(),)
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def get_group_count(self) -> int:
        """Get the number of groups."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM Groups")
                return cursor.fetchone()[0]
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return 0

    def init_db_version_table(self) -> None:
        """Create db_version table if it doesn't exist and seed initial version."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS db_version (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        version INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT
                    )
                """)
                connection.commit()

                # Check if table is empty
                cursor.execute("SELECT COUNT(*) FROM db_version")
                if cursor.fetchone()[0] == 0:
                    # Seed initial version
                    from datetime import datetime
                    cursor.execute(
                        "INSERT INTO db_version (id, version, updated_at) VALUES (1, 1, ?)",
                        (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),)
                    )
                    connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing db_version table: {error}")

    def get_db_version(self) -> int:
        """Get the current database version."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT version FROM db_version WHERE id = 1")
                result = cursor.fetchone()
                return result[0] if result else 1
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return 1

    def set_db_version(self, version: int) -> bool:
        """Update the database version."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                from datetime import datetime
                cursor.execute(
                    "UPDATE db_version SET version = ?, updated_at = ? WHERE id = 1",
                    (version, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def execute_migration(self, sql: str) -> bool:
        """Execute a SQL migration statement."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.executescript(sql)
                connection.commit()
                return True
        except sqlite3.Error as error:
            print(f"Migration error: {error}")
            return False

    def init_qrz_table(self) -> None:
        """Create QRZ settings table if it doesn't exist (single record only)."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS qrz_settings (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        username TEXT,
                        password TEXT,
                        is_active INTEGER DEFAULT 0
                    )
                """)
                connection.commit()

                # Check if table is empty and seed with empty record
                cursor.execute("SELECT COUNT(*) FROM qrz_settings")
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        "INSERT INTO qrz_settings (id, username, password, is_active) VALUES (1, '', '', 0)"
                    )
                    connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing qrz_settings table: {error}")

    def get_qrz_settings(self) -> Tuple[str, str, bool]:
        """
        Get QRZ settings from database.

        Returns:
            Tuple of (username, password, is_active)
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT username, password, is_active FROM qrz_settings WHERE id = 1")
                result = cursor.fetchone()
                if result:
                    return (result[0] or "", result[1] or "", bool(result[2]))
                return ("", "", False)
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return ("", "", False)

    def set_qrz_settings(self, username: str, password: str, is_active: bool) -> bool:
        """
        Save QRZ settings to database.

        Args:
            username: QRZ.com username
            password: QRZ.com password
            is_active: Whether QRZ lookups are enabled

        Returns:
            True if successful
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE qrz_settings SET username = ?, password = ?, is_active = ? WHERE id = 1",
                    (username, password, 1 if is_active else 0)
                )
                if cursor.rowcount == 0:
                    # No row exists, insert one
                    cursor.execute(
                        "INSERT INTO qrz_settings (id, username, password, is_active) VALUES (1, ?, ?, ?)",
                        (username, password, 1 if is_active else 0)
                    )
                connection.commit()
                return True
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def set_qrz_active(self, is_active: bool) -> bool:
        """
        Toggle QRZ active status.

        Args:
            is_active: Whether QRZ lookups are enabled

        Returns:
            True if successful
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "UPDATE qrz_settings SET is_active = ? WHERE id = 1",
                    (1 if is_active else 0,)
                )
                connection.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False


# =============================================================================
# MainWindow - Main application window
# =============================================================================

class MainWindow(QtWidgets.QMainWindow):
    """Main application window for CommStat-Improved."""

    def __init__(self, config: ConfigManager, db: DatabaseManager, debug_mode: bool = False):
        """
        Initialize the main window.

        Args:
            config: ConfigManager instance with loaded settings
            db: DatabaseManager instance for database operations
            debug_mode: Enable debug features when True
        """
        super().__init__()
        self.config = config
        self.db = db
        self.debug_mode = debug_mode

        # Internet connectivity state
        self._internet_available = False
        self._check_internet_on_startup()

        # Initialize JS8Call connector manager and TCP connection pool
        self.connector_manager = ConnectorManager()
        self.connector_manager.init_connectors_table()
        self.connector_manager.add_frequency_columns()
        self.tcp_pool = TCPConnectionPool(self.connector_manager, self)
        self.tcp_pool.any_message_received.connect(self._handle_tcp_message)
        self.tcp_pool.any_connection_changed.connect(self._handle_connection_changed)
        self.tcp_pool.any_status_message.connect(self._handle_status_message)
        self.tcp_pool.any_callsign_received.connect(self._handle_callsign_received)

        # Store callsigns by rig name (persists even if connection is lost)
        self.rig_callsigns: Dict[str, str] = {}

        # Active groups (currently single, but list for future multi-group support)
        self.active_groups: List[str] = [self.db.get_active_group()]

        # Live feed message buffer (stores messages from all TCP connections)
        self.feed_messages: List[str] = []
        self.max_feed_messages = 500  # Limit buffer size

        # Initiate TCP connections (Connecting... messages come via status_message signal)
        self.tcp_pool.connect_all()

        # Start tile server for map
        self.server_thread = threading.Thread(target=start_local_server, daemon=True)
        self.server_thread.start()

        # Map state
        self.map_loaded = False

        self._setup_window()
        self._setup_ui()

    def _setup_window(self) -> None:
        """Configure window properties (size, title, icon)."""
        self.setObjectName("MainWindow")
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(*WINDOW_SIZE)

        # Restore window position from config
        self._restore_window_position()

        # Set window icon
        icon_path = Path(ICON_FILE)
        if icon_path.exists():
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(str(icon_path)), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.setWindowIcon(icon)

    def _restore_window_position(self) -> None:
        """Restore window position from config.ini."""
        config = ConfigParser()
        if not os.path.exists(CONFIG_FILE):
            return

        config.read(CONFIG_FILE)

        if config.has_section("WINDOW"):
            try:
                x = config.getint("WINDOW", "x", fallback=None)
                y = config.getint("WINDOW", "y", fallback=None)
                width = config.getint("WINDOW", "width", fallback=None)
                height = config.getint("WINDOW", "height", fallback=None)

                if x is not None and y is not None:
                    self.move(x, y)
                if width is not None and height is not None:
                    self.resize(width, height)
            except (ValueError, TypeError):
                pass  # Use defaults if config is invalid

    def closeEvent(self, event) -> None:
        """Clean up resources and save window position before closing."""
        # Stop all timers
        if hasattr(self, 'clock_timer'):
            self.clock_timer.stop()
        if hasattr(self, 'slideshow_timer'):
            self.slideshow_timer.stop()
        if hasattr(self, 'ping_timer'):
            self.ping_timer.stop()
        if hasattr(self, 'internet_timer'):
            self.internet_timer.stop()

        # Disconnect all TCP connections gracefully
        if hasattr(self, 'tcp_pool'):
            print("Closing TCP connections...")
            self.tcp_pool.disconnect_all()

        # Save window position
        self._save_window_position()
        event.accept()

    def _save_window_position(self) -> None:
        """Save window position to config.ini."""
        config = ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE)

        if not config.has_section("WINDOW"):
            config.add_section("WINDOW")

        pos = self.pos()
        size = self.size()
        config.set("WINDOW", "x", str(pos.x()))
        config.set("WINDOW", "y", str(pos.y()))
        config.set("WINDOW", "width", str(size.width()))
        config.set("WINDOW", "height", str(size.height()))

        try:
            with open(CONFIG_FILE, 'w') as f:
                config.write(f)
        except IOError as e:
            print(f"Warning: Could not save window position: {e}")

    def _setup_ui(self) -> None:
        """Build the user interface."""
        # Create central widget with background color
        self.central_widget = QtWidgets.QWidget(self)
        self.central_widget.setStyleSheet(
            f"background-color: {self.config.get_color('program_background')};"
        )
        self.setCentralWidget(self.central_widget)

        # Main layout
        self.main_layout = QtWidgets.QGridLayout(self.central_widget)
        self.main_layout.setObjectName("mainLayout")

        # Row stretches: menu bar row 0, then content rows
        self.main_layout.setRowStretch(0, 0)  # Menu bar (fixed)
        self.main_layout.setRowStretch(1, 0)  # Header
        self.main_layout.setRowStretch(2, 1)  # StatRep table (50%)
        self.main_layout.setRowStretch(3, 1)  # Feed text (50%)
        self.main_layout.setRowStretch(4, 0)  # Map row 1 / Filter (fixed)
        self.main_layout.setRowStretch(5, 0)  # Map row 2 / Messages (fixed)

        # Setup components
        self._setup_menu()
        self._setup_header()
        self._setup_statrep_table()
        self._setup_placeholder_area()
        self._setup_map_widget()
        self._setup_live_feed()
        self._setup_message_table()
        self._setup_timers()

        # Populate the Groups menu with checkable items
        self._populate_groups_menu()

        # Load initial data
        self._load_statrep_data()
        self._load_marquee()
        self._load_map()
        self._load_live_feed()
        self._load_message_data()

        # Check ping on startup for Force/Skip commands (only if internet available)
        if self._internet_available:
            self._check_ping_on_startup()

    def _check_internet_on_startup(self) -> None:
        """Check internet connectivity at startup."""
        self._internet_available = check_internet()
        if self._internet_available:
            print("Internet connectivity: Available")
        else:
            print("Internet connectivity: Not available (will retry in 30 minutes)")

    def _retry_internet_check(self) -> None:
        """Retry internet connectivity check (called by timer)."""
        was_available = self._internet_available
        self._internet_available = check_internet()

        if self._internet_available and not was_available:
            # Internet just became available
            print("Internet connectivity: Now available")
            self.internet_timer.stop()
            # Start ping timer and do initial ping check
            self.ping_timer.start(60000)
            self._check_ping_on_startup()
        elif not self._internet_available:
            print("Internet connectivity: Still not available (will retry in 30 minutes)")

    def _setup_menu(self) -> None:
        """Create the menu bar with all actions."""
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setNativeMenuBar(False)  # Use Qt menu bar, not native (fixes Linux)
        self.menubar.setVisible(True)
        self.menubar.setFixedHeight(24)
        menu_bg = self.config.get_color('menu_background')
        menu_fg = self.config.get_color('menu_foreground')
        self.menubar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {menu_bg};
                color: {menu_fg};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {menu_bg};
            }}
            QMenu {{
                background-color: {menu_bg};
                color: {menu_fg};
            }}
            QMenu::item:selected {{
                background-color: {menu_bg};
            }}
        """)
        # Add menu bar to layout row 0 (fixes Linux global menu issues)
        self.main_layout.addWidget(self.menubar, 0, 0, 1, 2)

        # Create the main menu
        self.menu = QtWidgets.QMenu("Menu", self.menubar)
        self.menubar.addMenu(self.menu)

        # Define menu actions: (name, text, handler)
        menu_items = [
            ("statrep", "STATREP", self._on_statrep),
            ("send_message", "GROUP MESSAGE", self._on_send_message),
            ("new_marquee", "NEW MARQUEE", self._on_new_marquee),
            ("js8email", "JS8 EMAIL", self._on_js8email),
            ("js8sms", "JS8 SMS", self._on_js8sms),
            None,  # Separator
            ("statrep_ack", "STATREP ACK", self._on_statrep_ack),
            ("net_roster", "NET MANAGER", self._on_net_roster),
            ("net_check_in", "NET CHECK IN", self._on_net_check_in),
            ("member_list", "MEMBER LIST", self._on_member_list),
            None,  # Separator
            ("js8_connectors", "JS8 CONNECTORS", self._on_js8_connectors),
            ("qrz_enable", "QRZ ENABLE", self._on_qrz_enable),
            None,  # Separator
        ]

        # Create actions for dropdown menu
        self.actions: Dict[str, QtWidgets.QAction] = {}
        for item in menu_items:
            if item is None:
                self.menu.addSeparator()
            else:
                name, text, handler = item
                action = QtWidgets.QAction(text, self)
                action.triggered.connect(handler)
                self.menu.addAction(action)
                self.actions[name] = action

        # Create the Groups menu (with checkable group items)
        self.groups_menu = QtWidgets.QMenu("Groups", self.menubar)
        self.menubar.addMenu(self.groups_menu)

        # Add Manage Groups option at top
        manage_groups_action = QtWidgets.QAction("Manage Groups", self)
        manage_groups_action.triggered.connect(self._on_manage_groups)
        self.groups_menu.addAction(manage_groups_action)
        self.actions["manage_groups"] = manage_groups_action

        # Add Show Groups option
        show_groups_action = QtWidgets.QAction("Show Groups", self)
        show_groups_action.triggered.connect(self._on_show_groups)
        self.groups_menu.addAction(show_groups_action)
        self.actions["show_groups"] = show_groups_action

        self.groups_menu.addSeparator()

        # Populate group checkboxes (will be called after menu setup)
        # Deferred to after db initialization in __init__

        # Create the Filter menu
        self.filter_menu = QtWidgets.QMenu("Filter", self.menubar)
        self.menubar.addMenu(self.filter_menu)

        # Add Display Filter option
        filter_action = QtWidgets.QAction("DISPLAY FILTER", self)
        filter_action.triggered.connect(self._on_filter)
        self.filter_menu.addAction(filter_action)
        self.actions["filter"] = filter_action

        self.filter_menu.addSeparator()

        # Add reset date options
        reset_1day = QtWidgets.QAction("Reset to 1 day ago", self)
        reset_1day.triggered.connect(lambda: self._reset_filter_date(1))
        self.filter_menu.addAction(reset_1day)

        reset_1month = QtWidgets.QAction("Reset to 1 month ago", self)
        reset_1month.triggered.connect(lambda: self._reset_filter_date(30))
        self.filter_menu.addAction(reset_1month)

        reset_6months = QtWidgets.QAction("Reset to 6 months ago", self)
        reset_6months.triggered.connect(lambda: self._reset_filter_date(180))
        self.filter_menu.addAction(reset_6months)

        reset_1year = QtWidgets.QAction("Reset to 1 year ago", self)
        reset_1year.triggered.connect(lambda: self._reset_filter_date(365))
        self.filter_menu.addAction(reset_1year)

        # Add Data Filters section
        self.filter_menu.addSeparator()
        data_filter_label = QtWidgets.QAction("DATA FILTERS", self)
        data_filter_label.setEnabled(False)  # Disabled as a section title
        self.filter_menu.addAction(data_filter_label)

        # Add checkable toggle for hiding heartbeat messages (menu stays open)
        self.hide_heartbeat_checkbox = QtWidgets.QCheckBox("HIDE CQ & HEARTBEAT")
        self.hide_heartbeat_checkbox.setChecked(self.config.get_hide_heartbeat())
        self.hide_heartbeat_checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        self.hide_heartbeat_checkbox.stateChanged.connect(
            lambda state: self._on_toggle_heartbeat(state == Qt.Checked))
        hide_heartbeat_action = QtWidgets.QWidgetAction(self)
        hide_heartbeat_action.setDefaultWidget(self.hide_heartbeat_checkbox)
        self.filter_menu.addAction(hide_heartbeat_action)

        # Add checkable toggle for hiding map (menu stays open)
        self.hide_map_checkbox = QtWidgets.QCheckBox("HIDE MAP")
        self.hide_map_checkbox.setChecked(self.config.get_hide_map())
        self.hide_map_checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        self.hide_map_checkbox.stateChanged.connect(
            lambda state: self._on_toggle_hide_map(state == Qt.Checked))
        hide_map_action = QtWidgets.QWidgetAction(self)
        hide_map_action.setDefaultWidget(self.hide_map_checkbox)
        self.filter_menu.addAction(hide_map_action)

        # Add checkable toggle for showing all registered groups (menu stays open)
        self.show_all_groups_checkbox = QtWidgets.QCheckBox("SHOW ALL MY GROUPS")
        self.show_all_groups_checkbox.setChecked(self.config.get_show_all_groups())
        self.show_all_groups_checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        self.show_all_groups_checkbox.stateChanged.connect(
            lambda state: self._on_toggle_show_all_groups(state == Qt.Checked))
        show_all_groups_action = QtWidgets.QWidgetAction(self)
        show_all_groups_action.setDefaultWidget(self.show_all_groups_checkbox)
        self.filter_menu.addAction(show_all_groups_action)

        # Add checkable toggle for showing every group (no filtering) (menu stays open)
        self.show_every_group_checkbox = QtWidgets.QCheckBox("SHOW EVERY GROUP")
        self.show_every_group_checkbox.setChecked(self.config.get_show_every_group())
        self.show_every_group_checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
        self.show_every_group_checkbox.stateChanged.connect(
            lambda state: self._on_toggle_show_every_group(state == Qt.Checked))
        show_every_group_action = QtWidgets.QWidgetAction(self)
        show_every_group_action.setDefaultWidget(self.show_every_group_checkbox)
        self.filter_menu.addAction(show_every_group_action)

        # Create Tools dropdown menu
        self.tools_menu = QtWidgets.QMenu("Tools", self.menubar)
        self.menubar.addMenu(self.tools_menu)

        # Band Conditions option
        band_conditions_action = QtWidgets.QAction("Band Conditions", self)
        band_conditions_action.triggered.connect(self._on_band_conditions)
        self.tools_menu.addAction(band_conditions_action)
        self.actions["band_conditions"] = band_conditions_action

        # Solar Flux option
        solar_flux_action = QtWidgets.QAction("Solar Flux", self)
        solar_flux_action.triggered.connect(self._on_solar_flux)
        self.tools_menu.addAction(solar_flux_action)
        self.actions["solar_flux"] = solar_flux_action

        # World Map option (current solar conditions)
        world_map_action = QtWidgets.QAction("World Map", self)
        world_map_action.triggered.connect(self._on_world_map)
        self.tools_menu.addAction(world_map_action)
        self.actions["world_map"] = world_map_action

        # About (left of Exit)
        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self._on_about)
        self.menubar.addAction(about_action)
        self.actions["about"] = about_action

        # Exit
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.triggered.connect(qApp.quit)
        self.menubar.addAction(exit_action)
        self.actions["exit"] = exit_action

        # Debug menu (right of Exit, only visible in debug mode)
        if self.debug_mode:
            self.debug_features = DebugFeatures(self)
            self.debug_features.setup_debug_menu()

        # Add status bar
        self.statusbar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.statusbar)

    def _setup_header(self) -> None:
        """Create the header row with Marquee and Time."""
        # Header container widget with horizontal layout
        self.header_widget = QtWidgets.QWidget(self.central_widget)
        self.header_widget.setFixedHeight(38)
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        fg_color = self.config.get_color('program_foreground')
        font = QtGui.QFont("Arial", 12, QtGui.QFont.Bold)

        # Spacer to push marquee to center
        self.header_layout.addStretch()

        # Marquee label
        self.label_marquee = QtWidgets.QLabel(self.header_widget)
        self.label_marquee.setStyleSheet(f"color: {fg_color};")
        self.label_marquee.setText("Marquee:")
        self.label_marquee.setFont(font)
        self.header_layout.addWidget(self.label_marquee)

        # Marquee banner (scrolling text)
        self.marquee_label = QtWidgets.QLabel(self.header_widget)
        self.marquee_label.setFixedSize(600, 32)
        self.marquee_label.setFont(QtGui.QFont("Arial", 12))
        self.marquee_label.setStyleSheet(
            f"background-color: {self.config.get_color('marquee_background')};"
            f"color: {self.config.get_color('marquee_foreground_green')};"
        )
        self.header_layout.addWidget(self.marquee_label)

        # Spacer to push time to right
        self.header_layout.addStretch()

        # Time label
        self.label_time_prefix = QtWidgets.QLabel(self.header_widget)
        self.label_time_prefix.setStyleSheet(f"color: {fg_color};")
        self.label_time_prefix.setText("Time:")
        self.label_time_prefix.setFont(font)
        self.header_layout.addWidget(self.label_time_prefix)

        # Time display
        self.time_label = QtWidgets.QLabel(self.header_widget)
        self.time_label.setFixedSize(240, 32)
        self.time_label.setFont(QtGui.QFont("Arial", 12))
        self.time_label.setStyleSheet(
            f"background-color: {self.config.get_color('time_background')};"
            f"color: {self.config.get_color('time_foreground')};"
        )
        self.time_label.setAlignment(QtCore.Qt.AlignCenter)
        self.header_layout.addWidget(self.time_label)

        # Add header to main layout (row 1, spans all columns)
        self.main_layout.addWidget(self.header_widget, 1, 0, 1, 2)

    def _setup_statrep_table(self) -> None:
        """Create the StatRep data table."""
        self.statrep_table = QtWidgets.QTableWidget(self.central_widget)
        self.statrep_table.setObjectName("statrepTable")
        self.statrep_table.setColumnCount(18)
        self.statrep_table.setRowCount(0)

        # Apply styling
        title_bg = self.config.get_color('title_bar_background')
        title_fg = self.config.get_color('title_bar_foreground')
        data_bg = self.config.get_color('data_background')
        data_fg = self.config.get_color('data_foreground')

        self.statrep_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {data_bg};
                color: {data_fg};
            }}
            QTableWidget QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                padding: 4px;
                border: 1px solid {title_bg};
            }}
        """)

        # Explicitly style the horizontal header
        self.statrep_table.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                padding: 4px;
            }}
        """)

        # Set headers
        self.statrep_table.setHorizontalHeaderLabels(STATREP_HEADERS)

        # Configure header behavior
        header = self.statrep_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.statrep_table.verticalHeader().setVisible(False)

        # Connect click handler
        self.statrep_table.itemClicked.connect(self._on_statrep_click)

        # Add to layout (row 2, spans all columns)
        self.main_layout.addWidget(self.statrep_table, 2, 0, 1, 2)

    def _setup_placeholder_area(self) -> None:
        """Create placeholder area above message table (for future use)."""
        fg_color = self.config.get_color('program_foreground')

        # Size policy that allows area to shrink
        shrink_policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Preferred
        )

        self.placeholder_area = QtWidgets.QLabel(self.central_widget)
        self.placeholder_area.setStyleSheet(f"color: {fg_color};")
        self.placeholder_area.setText("")
        self.placeholder_area.setSizePolicy(shrink_policy)
        self.placeholder_area.setFixedHeight(FILTER_HEIGHT)
        self.main_layout.addWidget(self.placeholder_area, 4, 1, 1, 1)

    def _setup_map_widget(self) -> None:
        """Create the map widget using QWebEngineView."""
        self.map_widget = QWebEngineView(self.central_widget)
        self.map_widget.setObjectName("mapWidget")
        self.map_widget.setFixedSize(MAP_WIDTH, MAP_HEIGHT)

        # Set custom page to handle statrep links
        custom_page = CustomWebEnginePage(self)
        self.map_widget.setPage(custom_page)

        # Add to layout (row 4-5, column 0 only, spanning 2 rows)
        self.main_layout.addWidget(self.map_widget, 4, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Set column stretches: map column fixed, message column stretches
        self.main_layout.setColumnStretch(0, 0)  # Map (fixed)

        # Setup map disabled label (hidden by default)
        self._setup_map_disabled_label()

        # Apply initial hide_map setting
        if self.config.get_hide_map():
            self.map_widget.hide()
            self.map_disabled_label.show()
            self._start_slideshow()
        else:
            self.map_disabled_label.hide()

    def _setup_map_disabled_label(self) -> None:
        """Create the label/image display shown when map is hidden."""
        self.map_disabled_label = ClickableLabel(self.central_widget)
        self.map_disabled_label.setFixedSize(MAP_WIDTH, MAP_HEIGHT)
        self.map_disabled_label.setAlignment(Qt.AlignCenter)
        self.map_disabled_label.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.map_disabled_label.clicked.connect(self._on_slideshow_click)

        # Use feed colors for background
        bg_color = self.config.get_color('feed_background')
        fg_color = self.config.get_color('feed_foreground')
        self.map_disabled_label.setStyleSheet(
            f"background-color: {bg_color}; color: {fg_color}; font-size: 18px; font-weight: bold;"
        )

        # Add to same layout position as map
        self.main_layout.addWidget(self.map_disabled_label, 4, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Image slideshow state: list of (image_path, click_url) tuples
        self.slideshow_items: List[Tuple[str, Optional[str]]] = []
        self.slideshow_index: int = 0
        self.ping_message: Optional[str] = None  # Message from ping to display

        # Timer for slideshow
        self.slideshow_timer = QtCore.QTimer(self)
        self.slideshow_timer.timeout.connect(self._show_next_image)
        self.slideshow_timer.setInterval(SLIDESHOW_INTERVAL * 60000)  # Convert minutes to ms

    def _check_ping_on_startup(self) -> None:
        """Check playlist on startup for Force command (runs in background thread)."""
        thread = threading.Thread(target=self._check_ping_for_force_async, daemon=True)
        thread.start()

    def _check_ping_for_force_async(self) -> None:
        """Background thread version of Force check - emits signal to update UI."""
        import re
        from datetime import datetime
        try:
            with urllib.request.urlopen(_PING, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Extract content between <pre> tags if present
                pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
                if pre_match:
                    content = pre_match.group(1)

                content = content.strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]

                if not lines:
                    return

                # Line 1: Check for expiration date (case-insensitive)
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    today = datetime.now().date()
                    if expiry_date < today:
                        # Date has passed - skip all playlist rules including Force
                        print(f"Action Date = {expiry_date}. No actions to perform")
                        return
                    # Remove date line
                    lines = lines[1:]

                # Line 2: Check for Force command
                if lines and lines[0].startswith("Force"):
                    print("Force command detected, hiding map")  # Debug
                    # Schedule UI update on main thread
                    QtCore.QMetaObject.invokeMethod(
                        self, "_apply_force_hide_map",
                        QtCore.Qt.QueuedConnection
                    )

        except Exception as e:
            print(f"Failed to check playlist: {e}")

    @QtCore.pyqtSlot()
    def _apply_force_hide_map(self) -> None:
        """Apply force hide map from background thread signal (runs on main thread)."""
        if not self.config.get_hide_map():
            self.config.set_hide_map(True)
            self.hide_map_checkbox.setChecked(True)
            self.map_widget.hide()
            self.map_disabled_label.show()
            self._start_slideshow()

    def _fetch_remote_ping(self) -> List[Tuple[str, Optional[str]]]:
        """Fetch and parse the remote playlist, download images to temp files.

        Playlist format:
        - Line 1: Date: YYYY-MM-DD (expiration date - if passed, ignore playlist)
        - Line 2: Force or nothing (Force hides map on startup)
        - Remaining: MESSAGE START/END block or image URLs

        Returns empty list if date expired or if showing a message.
        """
        import re
        from datetime import datetime
        items = []
        self.ping_message = None  # Reset message

        try:
            with urllib.request.urlopen(_PING, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Extract content between <pre> tags if present
                pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
                if pre_match:
                    content = pre_match.group(1)

                content = content.strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]

                if not lines:
                    return []

                # Line 1: Check for expiration date (case-insensitive)
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    today = datetime.now().date()
                    if expiry_date < today:
                        # Date has passed - skip all playlist rules
                        print(f"Action Date = {expiry_date}. No actions to perform")
                        return []
                    # Remove date line
                    lines = lines[1:]

                # Check for Force command - remove it from lines
                if lines and lines[0].startswith("Force"):
                    lines = lines[1:]

                # Rebuild content for MESSAGE check
                content = '\n'.join(lines)

                # Check for MESSAGE START/END block
                msg_match = re.search(r'MESSAGE START\s*\n(.*?)\nMESSAGE END', content, re.DOTALL)
                if msg_match:
                    self.ping_message = msg_match.group(1)
                    return []  # Don't load images when showing message

                for line in lines:
                    # Skip MESSAGE markers
                    if line in ("MESSAGE START", "MESSAGE END"):
                        continue

                    # Find all URLs in the line
                    urls = re.findall(r'https?://[^\s]+', line)
                    if not urls:
                        continue

                    image_url = urls[0]
                    click_url = urls[1] if len(urls) > 1 else None

                    # Download image to temp file
                    try:
                        temp_path = self._download_image(image_url)
                        if temp_path:
                            items.append((temp_path, click_url))
                    except Exception as e:
                        print(f"Failed to download {image_url}: {e}")

        except Exception as e:
            print(f"Failed to fetch playlist: {e}")

        return items

    def _download_image(self, url: str) -> Optional[str]:
        """Download an image from URL to a temp file, return the path."""
        try:
            # Get file extension from URL
            ext = os.path.splitext(url)[1] or '.png'
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)

            with urllib.request.urlopen(url, timeout=10) as response:
                temp_file.write(response.read())
            temp_file.close()
            return temp_file.name
        except Exception as e:
            print(f"Failed to download image {url}: {e}")
            return None

    def _load_slideshow_images(self) -> None:
        """Load images with priority: URL > my_images > images > 00-default.png."""
        self.slideshow_items = []
        self.slideshow_index = 0
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        # Priority 1: Fetch remote playlist
        remote_items = self._fetch_remote_ping()

        if remote_items:
            # Use remote playlist only
            self.slideshow_items.extend(remote_items)
            return

        # Priority 2: Check my_images folder
        my_images_folder = os.path.join(os.getcwd(), "my_images")
        if os.path.isdir(my_images_folder):
            files = sorted(os.listdir(my_images_folder))
            for filename in files:
                if filename.lower().endswith(valid_extensions):
                    image_path = os.path.join(my_images_folder, filename)
                    self.slideshow_items.append((image_path, None))

        if self.slideshow_items:
            return

        # Priority 3: Check images folder
        images_folder = os.path.join(os.getcwd(), "images")
        if os.path.isdir(images_folder):
            files = sorted(os.listdir(images_folder))
            for filename in files:
                if filename.lower().endswith(valid_extensions):
                    image_path = os.path.join(images_folder, filename)
                    self.slideshow_items.append((image_path, None))

        if self.slideshow_items:
            return

        # Priority 4: Use default image
        default_image = os.path.join(os.getcwd(), "00-default.png")
        if os.path.isfile(default_image):
            self.slideshow_items.append((default_image, None))

    def _start_slideshow(self) -> None:
        """Start the image slideshow or display playlist message."""
        self._load_slideshow_images()

        # Check if we have a message to display
        if self.ping_message:
            self._display_ping_message()
            self.slideshow_timer.start()  # Keep timer running to check for changes
        elif self.slideshow_items:
            self._show_current_image()
            self.slideshow_timer.start()
        else:
            # No images and no message - show "Map Disabled"
            self.map_disabled_label.setPixmap(QtGui.QPixmap())
            self.map_disabled_label.setText("Map Disabled")

    @QtCore.pyqtSlot()
    def _display_ping_message(self) -> None:
        """Display the playlist message centered in the label."""
        if not self.ping_message:
            return

        # Clear any existing pixmap
        self.map_disabled_label.setPixmap(QtGui.QPixmap())

        # Set text with center alignment (both horizontal and vertical)
        self.map_disabled_label.setText(self.ping_message)
        self.map_disabled_label.setAlignment(Qt.AlignCenter)
        self.map_disabled_label.setWordWrap(True)

    def _stop_slideshow(self) -> None:
        """Stop the image slideshow."""
        self.slideshow_timer.stop()

    def _show_current_image(self) -> None:
        """Display the current slideshow image."""
        if not self.slideshow_items:
            return

        image_path, _ = self.slideshow_items[self.slideshow_index]
        pixmap = QtGui.QPixmap(image_path)

        # Scale to fit while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            MAP_WIDTH, MAP_HEIGHT,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.map_disabled_label.setPixmap(scaled_pixmap)
        self.map_disabled_label.setText("")

    def _show_next_image(self) -> None:
        """Advance to the next image in the slideshow or refresh message."""
        # Check playlist for updates in background (at each interval)
        thread = threading.Thread(target=self._check_ping_content_async, daemon=True)
        thread.start()

        # If showing a message, just keep displaying it (will be updated by async check)
        if self.ping_message:
            return

        # Otherwise advance to next image
        if not self.slideshow_items:
            return

        self.slideshow_index = (self.slideshow_index + 1) % len(self.slideshow_items)
        self._show_current_image()

    def _check_ping_content_async(self) -> None:
        """Background thread to check playlist for message changes."""
        import re
        from datetime import datetime
        try:
            with urllib.request.urlopen(_PING, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Extract content between <pre> tags if present
                pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
                if pre_match:
                    content = pre_match.group(1)

                content = content.strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]

                if not lines:
                    return

                # Line 1: Check for expiration date (case-insensitive)
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    today = datetime.now().date()
                    if expiry_date < today:
                        # Date has passed - skip all playlist rules, clear any message
                        if self.ping_message:
                            self.ping_message = None
                            QtCore.QMetaObject.invokeMethod(
                                self, "_reload_slideshow",
                                QtCore.Qt.QueuedConnection
                            )
                        return
                    # Remove date line
                    lines = lines[1:]

                # Check for Force command - remove it from lines
                if lines and lines[0].startswith("Force"):
                    lines = lines[1:]

                # Rebuild content for MESSAGE check
                content = '\n'.join(lines)

                # Check for MESSAGE START/END block
                msg_match = re.search(r'MESSAGE START\s*\n(.*?)\nMESSAGE END', content, re.DOTALL)
                if msg_match:
                    new_message = msg_match.group(1)
                    # Only update if message changed
                    if new_message != self.ping_message:
                        self.ping_message = new_message
                        QtCore.QMetaObject.invokeMethod(
                            self, "_display_ping_message",
                            QtCore.Qt.QueuedConnection
                        )
                elif self.ping_message:
                    # Message was removed from playlist
                    self.ping_message = None
                    QtCore.QMetaObject.invokeMethod(
                        self, "_reload_slideshow",
                        QtCore.Qt.QueuedConnection
                    )

        except Exception as e:
            print(f"Failed to check playlist content: {e}")

    @QtCore.pyqtSlot()
    def _reload_slideshow(self) -> None:
        """Reload the slideshow (called from background thread via signal)."""
        self._load_slideshow_images()
        if self.ping_message:
            self._display_ping_message()
        elif self.slideshow_items:
            self.slideshow_index = 0
            self._show_current_image()
        else:
            self.map_disabled_label.setPixmap(QtGui.QPixmap())
            self.map_disabled_label.setText("Map Disabled")

    def _on_slideshow_click(self) -> None:
        """Handle click on slideshow image - open associated URL if any."""
        if not self.slideshow_items:
            return

        _, click_url = self.slideshow_items[self.slideshow_index]
        if click_url:
            webbrowser.open(click_url)

    def _setup_live_feed(self) -> None:
        """Create the live feed text area."""
        # Feed text area
        self.feed_text = QtWidgets.QPlainTextEdit(self.central_widget)
        self.feed_text.setObjectName("feedText")
        self.feed_text.setFont(QtGui.QFont("Source Code Pro", 10))
        self.feed_text.setStyleSheet(
            f"background-color: {self.config.get_color('feed_background')};"
            f"color: {self.config.get_color('feed_foreground')};"
        )
        self.feed_text.setReadOnly(True)

        # No word wrap, always show scrollbars
        self.feed_text.setWordWrapMode(QtGui.QTextOption.NoWrap)
        self.feed_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.feed_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        # Add to layout (row 3, full width)
        self.main_layout.addWidget(self.feed_text, 3, 0, 1, 2)

    def _load_live_feed(self) -> None:
        """Initialize the live feed display from buffer."""
        self._update_feed_display()

    def _update_feed_display(self) -> None:
        """Update the live feed display from the message buffer."""
        # Safety check - feed_text may not exist during startup
        if not hasattr(self, 'feed_text'):
            return

        if not self.feed_messages:
            # No connectors configured
            self.feed_text.setPlainText(
                "No JS8Call connectors configured.\n\n"
                "Use Menu > JS8 CONNECTORS to add a connection."
            )
            return

        # Filter messages based on settings
        messages = self.feed_messages
        if self.config.get_hide_heartbeat():
            messages = [
                msg for msg in messages
                if 'HEARTBEAT' not in msg.upper()
                and '@ALLCALL CQ' not in msg.upper()
            ]

        # Join messages (already in newest-first order)
        self.feed_text.setPlainText('\n'.join(messages))

    def _setup_message_table(self) -> None:
        """Create the message data table."""
        self.message_table = QtWidgets.QTableWidget(self.central_widget)
        self.message_table.setObjectName("messageTable")
        self.message_table.setColumnCount(4)
        self.message_table.setRowCount(0)

        # Apply styling
        title_bg = self.config.get_color('title_bar_background')
        title_fg = self.config.get_color('title_bar_foreground')
        data_bg = self.config.get_color('data_background')
        data_fg = self.config.get_color('data_foreground')

        self.message_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {data_bg};
                color: {data_fg};
            }}
            QTableWidget QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                padding: 4px;
                border: 1px solid {title_bg};
            }}
        """)

        # Explicitly style the horizontal header
        self.message_table.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                padding: 4px;
            }}
        """)

        # Set headers
        self.message_table.setHorizontalHeaderLabels([
            "Date Time UTC", "Group", "Callsign", "Message"
        ])

        # Configure header behavior
        header = self.message_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.message_table.verticalHeader().setVisible(False)
        self.message_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.message_table.setFixedHeight(MAP_HEIGHT - FILTER_HEIGHT)

        # Add to layout (row 5, column 1)
        self.main_layout.addWidget(self.message_table, 5, 1, 1, 1)

    def _load_message_data(self) -> None:
        """Load message data from database into the table."""
        filters = self.config.filter_settings
        # Determine group filtering mode
        show_every = self.config.get_show_every_group()
        if show_every:
            groups = []
            show_all = True
        elif self.config.get_show_all_groups():
            groups = self.db.get_all_groups()
            show_all = False
        else:
            groups = self.db.get_active_groups()
            show_all = False
        data = self.db.get_message_data(
            groups=groups,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', ''),
            show_all=show_all
        )

        # Clear and populate table
        self.message_table.setRowCount(0)
        for row_num, row_data in enumerate(data):
            self.message_table.insertRow(row_num)
            for col_num, value in enumerate(row_data):
                item = QTableWidgetItem(str(value) if value is not None else "")
                self.message_table.setItem(row_num, col_num, item)

        # Sort by datetime descending
        self.message_table.sortItems(0, QtCore.Qt.DescendingOrder)

    def _load_map(self) -> None:
        """Generate and display the folium map with StatRep pins."""
        filters = self.config.filter_settings
        # Determine group filtering mode
        show_every = self.config.get_show_every_group()
        if show_every:
            groups = []
            show_all = True
        elif self.config.get_show_all_groups():
            groups = self.db.get_all_groups()
            show_all = False
        else:
            groups = self.db.get_active_groups()
            show_all = False

        # Use saved map position or default to US center
        if not hasattr(self, 'map_center'):
            self.map_center = (38.8199286, -96.7782551)
            self.map_zoom = 4

        m = folium.Map(zoom_start=self.map_zoom, location=self.map_center)

        # Add local tile layer
        folium.raster_layers.TileLayer(
            tiles='http://localhost:8000/{z}/{x}/{y}.png',
            name='Local Tiles',
            attr='Local Tiles',
            max_zoom=19,
            control=True
        ).add_to(m)

        # Get StatRep data for pins
        try:
            data = self.db.get_statrep_data(
                groups=groups,
                start=filters.get('start', DEFAULT_FILTER_START),
                end=filters.get('end', ''),
                show_all=show_all
            )

            gridlist = []
            for row in data:
                callsign = row[2]
                srid = row[1]
                status = str(row[5])
                grid = row[3]

                # Convert grid to coordinates
                try:
                    coords = mh.to_location(grid, center=True)
                    lat = float(coords[0])
                    lon = float(coords[1])

                    # Offset duplicate grids
                    count = gridlist.count(grid)
                    if count > 0:
                        lat += count * 0.01
                        lon += count * 0.01
                    gridlist.append(grid)

                    # Create popup HTML
                    html = f'''<HTML>
                        <BODY>
                            <p style="color:blue;font-size:14px;">
                                Callsign: {callsign}<br>
                                StatRep ID: {srid}<br>
                                <button onclick="window.location.href='http://localhost/statrep/{srid}'"
                                    style="color:#0000FF;font-family:Arial;font-size:12px;font-weight:bold;
                                    cursor:pointer;border:1px solid #000;padding:2px 5px;">
                                    View StatRep
                                </button>
                            </p>
                        </BODY>
                    </HTML>'''
                    iframe = folium.IFrame(html, width=160, height=100)
                    popup = folium.Popup(iframe, min_width=100, max_width=160)

                    # Determine pin color and size
                    if status == "1":
                        color = "green"
                        radius = 5
                    elif status == "2":
                        color = "orange"
                        radius = 10
                    elif status == "3":
                        color = "red"
                        radius = 10
                    else:
                        color = "black"
                        radius = 5

                    folium.CircleMarker(
                        radius=radius,
                        fill=True,
                        color=color,
                        fill_color=color,
                        location=[lat, lon],
                        popup=popup
                    ).add_to(m)
                except Exception as e:
                    print(f"Error adding pin for grid {grid}: {e}")

        except Exception as e:
            print(f"Error loading map data: {e}")

        # Save map to bytes and display
        map_data = io.BytesIO()
        m.save(map_data, close_file=False)

        # Always set new HTML content (reload() only refreshes cached content)
        self.map_widget.setHtml(map_data.getvalue().decode())
        self.map_loaded = True

    def _save_map_position(self, callback=None) -> None:
        """Save current map center and zoom via JavaScript."""
        if not self.map_loaded:
            if callback:
                callback()
            return

        js_code = """
        (function() {
            try {
                var mapId = Object.keys(window).find(k => k.startsWith('map_'));
                if (mapId && window[mapId]) {
                    var map = window[mapId];
                    var center = map.getCenter();
                    var zoom = map.getZoom();
                    return JSON.stringify({lat: center.lat, lng: center.lng, zoom: zoom});
                }
            } catch(e) {}
            return null;
        })();
        """

        def handle_result(result):
            if result:
                try:
                    import json
                    data = json.loads(result)
                    self.map_center = (data['lat'], data['lng'])
                    self.map_zoom = data['zoom']
                except:
                    pass
            if callback:
                callback()

        self.map_widget.page().runJavaScript(js_code, handle_result)

    def _load_statrep_data(self) -> None:
        """Load StatRep data from database into the table."""
        # Get filter settings
        filters = self.config.filter_settings
        # Determine group filtering mode
        show_every = self.config.get_show_every_group()
        if show_every:
            groups = []
            show_all = True
        elif self.config.get_show_all_groups():
            groups = self.db.get_all_groups()
            show_all = False
        else:
            groups = self.db.get_active_groups()
            show_all = False

        # Fetch data from database
        data = self.db.get_statrep_data(
            groups=groups,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', ''),
            show_all=show_all
        )

        # Clear and populate table
        self.statrep_table.setRowCount(0)
        for row_num, row_data in enumerate(data):
            self.statrep_table.insertRow(row_num)
            for col_num, value in enumerate(row_data):
                item = QTableWidgetItem(str(value) if value is not None else "")

                # Apply color coding for status columns (values 1-4)
                if value in ["1", "2", "3", "4"]:
                    if value == "1":
                        color = QColor(self.config.get_color('condition_green'))
                    elif value == "2":
                        color = QColor(self.config.get_color('condition_yellow'))
                    elif value == "3":
                        color = QColor(self.config.get_color('condition_red'))
                    else:  # "4"
                        color = QColor(self.config.get_color('condition_gray'))
                    item.setBackground(color)
                    item.setForeground(color)

                self.statrep_table.setItem(row_num, col_num, item)

        # Sort by datetime descending
        self.statrep_table.sortItems(0, QtCore.Qt.DescendingOrder)

    def _on_statrep_click(self, item: QTableWidgetItem) -> None:
        """Handle click on StatRep table row."""
        row = item.row()
        sr_id = self.statrep_table.item(row, 1)  # Column 1 is the ID
        if sr_id:
            print(f"StatRep clicked: ID = {sr_id.text()}")

    def _setup_timers(self) -> None:
        """Setup timers for clock, data refresh, and marquee animation."""
        # Clock timer - updates every second
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_time)
        self.clock_timer.start(1000)
        self._update_time()  # Initial display

        # Ping timer - runs every 60 seconds (only when internet available)
        self.ping_timer = QTimer(self)
        self.ping_timer.timeout.connect(self._check_ping)
        if self._internet_available:
            self.ping_timer.start(60000)

        # Internet check timer - retries every 30 minutes if offline
        self.internet_timer = QTimer(self)
        self.internet_timer.timeout.connect(self._retry_internet_check)
        if not self._internet_available:
            self.internet_timer.start(INTERNET_CHECK_INTERVAL)

        # Marquee animation timeline
        self.marquee_timeline = QtCore.QTimeLine()
        self.marquee_timeline.setCurveShape(QtCore.QTimeLine.LinearCurve)
        self.marquee_timeline.frameChanged.connect(self._update_marquee_text)
        self.marquee_timeline.finished.connect(self._next_marquee)

        # Marquee state
        self.marquee_text = ""
        self.marquee_chars = 0

    def _refresh_data(self) -> None:
        """Refresh StatRep, message data, and map from database."""
        # Reload data from database (TCP handler inserts data directly)
        self._load_statrep_data()
        self._load_message_data()

        # Save map position before refresh, then reload map
        self._save_map_position(callback=self._load_map)

    def _check_ping(self) -> None:
        """Check playlist for Force command in background."""
        if not self._internet_available:
            return
        thread = threading.Thread(target=self._check_ping_for_force_async, daemon=True)
        thread.start()

    def _update_time(self) -> None:
        """Update the time display with current UTC time."""
        current_time = QDateTime.currentDateTimeUtc()
        self.time_label.setText(current_time.toString("yyyy-MM-dd hh:mm:ss") + " UTC")

    def _update_marquee_text(self, frame: int) -> None:
        """Update marquee display for current animation frame."""
        if frame < self.marquee_chars:
            start = 0
        else:
            start = frame - self.marquee_chars
        text = self.marquee_text[start:frame]
        self.marquee_label.setText(text)

    def _next_marquee(self) -> None:
        """Called when marquee animation completes - reload and restart."""
        self._load_marquee()

    def _load_marquee(self) -> None:
        """Load the latest marquee message from database and start animation."""
        if self.config.get_show_all_groups():
            groups = self.db.get_all_groups()
        else:
            groups = self.db.get_active_groups()
        result = self.db.get_latest_marquee(groups)

        if result:
            # Extract marquee data (idnum, callsign, groupname, date, color, message)
            try:
                sr_id = result[0] if len(result) > 0 else ""
                callsign = result[1] if len(result) > 1 else ""
                msg_group = result[2] if len(result) > 2 else ""
                date = result[3] if len(result) > 3 else ""
                color = str(result[4]) if len(result) > 4 else "1"
                msg = result[5] if len(result) > 5 else ""

                # Set marquee color based on status
                if color == "3":
                    fg_color = self.config.get_color('marquee_foreground_red')
                elif color == "2":
                    fg_color = self.config.get_color('marquee_foreground_yellow')
                else:
                    fg_color = self.config.get_color('marquee_foreground_green')

                self.marquee_label.setStyleSheet(
                    f"background-color: {self.config.get_color('marquee_background')};"
                    f"color: {fg_color};"
                )

                # Build marquee text
                marquee_text = f" ID: {sr_id} | Received: {date} | From: {msg_group} | By: {callsign} | MSG: {msg}"

                # Calculate how many characters fit in the marquee width
                fm = self.marquee_label.fontMetrics()
                self.marquee_chars = int(self.marquee_label.width() / fm.averageCharWidth())

                # Add padding spaces
                padding = ' ' * self.marquee_chars
                self.marquee_text = marquee_text + "      +++      " + padding

                # Setup and start animation
                text_length = len(self.marquee_text)
                self.marquee_timeline.setDuration(20000)
                self.marquee_timeline.setFrameRange(0, text_length)
                self.marquee_timeline.start()
            except (IndexError, TypeError) as e:
                print(f"Error loading marquee: {e}")
        else:
            # No marquee data - show placeholder
            self.marquee_label.setText("  No marquee messages")

    # -------------------------------------------------------------------------
    # Menu Action Handlers (placeholders for now)
    # -------------------------------------------------------------------------

    def _on_js8email(self) -> None:
        """Open JS8 Email window."""
        dialog = JS8MailDialog(self.tcp_pool, self.connector_manager, self)
        dialog.exec_()

    def _on_js8sms(self) -> None:
        """Open JS8 SMS window."""
        dialog = JS8SMSDialog(self.tcp_pool, self.connector_manager, self)
        dialog.exec_()

    def _on_statrep(self) -> None:
        """Open StatRep window."""
        dialog = StatRepDialog(self.tcp_pool, self.connector_manager, self)
        dialog.exec_()

    def _on_net_check_in(self) -> None:
        """Open Net Check In window."""
        print("NET CHECK IN clicked - window not yet implemented")

    def _on_member_list(self) -> None:
        """Open Member List window."""
        print("MEMBER LIST clicked - window not yet implemented")

    def _on_statrep_ack(self) -> None:
        """Open StatRep Acknowledgment window."""
        print("STATREP ACK clicked - window not yet implemented")

    def _on_net_roster(self) -> None:
        """Open Net Manager window."""
        print("NET MANAGER clicked - window not yet implemented")

    def _on_new_marquee(self) -> None:
        """Open New Marquee window."""
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormMarquee(self.tcp_pool, self.connector_manager)
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_send_message(self) -> None:
        """Open Send Message window."""
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormMessage(self.tcp_pool, self.connector_manager)
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_filter(self) -> None:
        """Open Display Filter window."""
        dialog = FilterDialog(self.config.filter_settings, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Update filter settings directly
            self.config.filter_settings = dialog.get_filters()
            # Refresh data with new filters
            self._load_statrep_data()
            self._load_message_data()
            # Save map position before refresh, then reload map
            self._save_map_position(callback=self._load_map)

    def _reset_filter_date(self, days_ago: int) -> None:
        """Reset filter start date to specified days ago and apply."""
        from datetime import datetime, timedelta

        # Calculate new start date
        new_start = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        # Update in-memory filter settings
        self.config.filter_settings = {
            'start': new_start,
            'end': ''  # No end date
        }

        # Refresh data with new filters
        self._load_statrep_data()
        self._load_message_data()
        self._save_map_position(callback=self._load_map)

        print(f"Filter reset: start={new_start}")

    def _on_toggle_heartbeat(self, checked: bool) -> None:
        """Toggle heartbeat message filtering in live feed."""
        self.config.set_hide_heartbeat(checked)
        self._load_live_feed()

    def _on_toggle_hide_map(self, checked: bool) -> None:
        """Toggle between map and image slideshow."""
        self.config.set_hide_map(checked)
        if checked:
            self.map_widget.hide()
            self.map_disabled_label.show()
            self._start_slideshow()
        else:
            self._stop_slideshow()
            self.ping_message = None  # Clear any message
            self.map_disabled_label.hide()
            self.map_widget.show()

    def _on_toggle_show_all_groups(self, checked: bool) -> None:
        """Toggle showing all groups data regardless of active groups."""
        self.config.set_show_all_groups(checked)
        # Refresh all data views
        self._load_statrep_data()
        self._load_message_data()
        self._load_marquee()
        self._save_map_position(callback=self._load_map)

    def _on_toggle_show_every_group(self, checked: bool) -> None:
        """Toggle showing every group's data (no filtering at all)."""
        self.config.set_show_every_group(checked)
        # Refresh data views (not marquee - per user request)
        self._load_statrep_data()
        self._load_message_data()
        self._save_map_position(callback=self._load_map)

    def _on_manage_groups(self) -> None:
        """Open Manage Groups window."""
        dialog = GroupsDialog(self.db, self)
        dialog.exec_()
        # Refresh the groups menu after dialog closes
        self._populate_groups_menu()
        # Refresh all data
        self._load_statrep_data()
        self._load_message_data()
        self._load_marquee()
        self._save_map_position(callback=self._load_map)

    def _on_show_groups(self) -> None:
        """Show Groups dialog displaying all groups in a table."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Groups")
        dialog.setMinimumSize(700, 400)
        dialog.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create table widget
        table = QtWidgets.QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Group Name", "Comment", "URL #1", "URL #2", "Date Added"])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setStretchLastSection(True)

        # Get all groups
        groups = self.db.get_all_groups_details()
        table.setRowCount(len(groups))

        for row, group in enumerate(groups):
            # Group Name
            name_item = QtWidgets.QTableWidgetItem(group["name"])
            table.setItem(row, 0, name_item)

            # Comment
            comment_item = QtWidgets.QTableWidgetItem(group["comment"])
            table.setItem(row, 1, comment_item)

            # URL #1 - show shortened text, full URL in tooltip
            url1 = group["url1"]
            if url1:
                url1_display = "Link" if len(url1) > 30 else url1
                url1_item = QtWidgets.QTableWidgetItem(url1_display)
                url1_item.setToolTip(url1)
                url1_item.setForeground(QtGui.QColor("#0066CC"))
            else:
                url1_item = QtWidgets.QTableWidgetItem("")
            table.setItem(row, 2, url1_item)

            # URL #2 - show shortened text, full URL in tooltip
            url2 = group["url2"]
            if url2:
                url2_display = "Link" if len(url2) > 30 else url2
                url2_item = QtWidgets.QTableWidgetItem(url2_display)
                url2_item.setToolTip(url2)
                url2_item.setForeground(QtGui.QColor("#0066CC"))
            else:
                url2_item = QtWidgets.QTableWidgetItem("")
            table.setItem(row, 3, url2_item)

            # Date Added
            date_item = QtWidgets.QTableWidgetItem(group["date_added"])
            table.setItem(row, 4, date_item)

        # Resize columns to content
        table.resizeColumnsToContents()

        layout.addWidget(table)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        dialog.exec_()

    def _populate_groups_menu(self) -> None:
        """Populate the Groups menu with checkable group items."""
        # Remove existing group actions (keep Manage Groups, Show Groups, and separator)
        actions = self.groups_menu.actions()
        for action in actions[3:]:  # Skip Manage Groups, Show Groups, and separator
            self.groups_menu.removeAction(action)

        # Add groups alphabetically with checkboxes (menu stays open when clicked)
        groups = self.db.get_all_groups_with_status()
        for name, is_active in groups:  # Already sorted by name from DB
            checkbox = QtWidgets.QCheckBox(name)
            checkbox.setChecked(is_active)
            checkbox.setStyleSheet("QCheckBox { padding: 4px 8px; }")
            checkbox.stateChanged.connect(lambda state, n=name: self._toggle_group(n, state == Qt.Checked))
            widget_action = QtWidgets.QWidgetAction(self)
            widget_action.setDefaultWidget(checkbox)
            self.groups_menu.addAction(widget_action)

    def _toggle_group(self, group_name: str, active: bool) -> None:
        """Toggle a group's active status."""
        self.db.set_group_active(group_name, active)
        # Refresh all data to show/hide based on new active groups
        self._load_statrep_data()
        self._load_message_data()
        self._load_marquee()
        self._save_map_position(callback=self._load_map)

    def _on_js8_connectors(self) -> None:
        """Open JS8 Connectors management window."""
        dialog = JS8ConnectorsDialog(self.connector_manager, self.tcp_pool, self)
        dialog.exec_()

    def _handle_connection_changed(self, rig_name: str, is_connected: bool) -> None:
        """
        Handle TCP connection status changes.

        Args:
            rig_name: Name of the rig.
            is_connected: True if connected, False if disconnected.
        """
        if is_connected:
            # Request callsign from JS8Call when connected
            client = self.tcp_pool.get_client(rig_name)
            if client:
                client.get_callsign()
        else:
            # For disconnects, add the message here
            from datetime import datetime, timezone
            utc_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d   %H:%M:%S")
            status_line = f"{utc_str}\t[{rig_name}] Disconnected"
            self.feed_messages.insert(0, status_line)
            self._update_feed_display()

    def _handle_callsign_received(self, rig_name: str, callsign: str) -> None:
        """
        Handle callsign received from JS8Call.

        Args:
            rig_name: Name of the rig.
            callsign: Callsign configured in JS8Call.
        """
        if callsign:
            self.rig_callsigns[rig_name] = callsign
            print(f"[{rig_name}] Callsign: {callsign}")

    def get_callsign_for_rig(self, rig_name: str) -> str:
        """
        Get cached callsign for a rig.

        Args:
            rig_name: Name of the rig.

        Returns:
            Callsign string or empty string if not known.
        """
        return self.rig_callsigns.get(rig_name, "")

    def _handle_status_message(self, rig_name: str, message: str) -> None:
        """
        Handle status message from TCP client (for live feed display).

        Args:
            rig_name: Name of the rig.
            message: Status message to display.
        """
        from datetime import datetime, timezone

        # Format timestamp with 3 spaces between date and time (matches RX.DIRECTED format)
        utc_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d   %H:%M:%S")
        timestamped_message = f"{utc_str}\t{message}"

        # Insert at beginning (newest first)
        self.feed_messages.insert(0, timestamped_message)

        # Trim buffer if needed
        if len(self.feed_messages) > self.max_feed_messages:
            self.feed_messages = self.feed_messages[:self.max_feed_messages]

        self._update_feed_display()

    def _handle_tcp_message(self, rig_name: str, message: dict) -> None:
        """
        Handle incoming TCP message from JS8Call.

        Args:
            rig_name: Name of the rig that received the message.
            message: Parsed JSON message from JS8Call.
        """
        from datetime import datetime, timezone

        msg_type = message.get("type", "")
        value = message.get("value", "")
        params = message.get("params", {})

        # Handle RX.DIRECTED messages
        if msg_type == "RX.DIRECTED":
            from_call = params.get("FROM", "")
            to_call = params.get("TO", "")
            grid = params.get("GRID", "")
            freq = params.get("FREQ", 0)
            offset = params.get("OFFSET", 0)
            snr = params.get("SNR", 0)
            utc_ms = params.get("UTC", 0)

            # Convert UTC milliseconds to datetime string (3 spaces between date and time)
            utc_str = datetime.fromtimestamp(utc_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d   %H:%M:%S")

            # Format feed line to match DIRECTED.TXT format:
            # DATETIME    FREQ_MHZ    OFFSET    SNR    CALLSIGN: MESSAGE
            # FREQ from JS8Call is dial + offset, so subtract offset to get dial frequency
            dial_freq_mhz = (freq - offset) / 1000000 if freq else 0
            feed_line = f"{utc_str}\t{dial_freq_mhz:.3f}\t{offset}\t{snr:+03d}\t{from_call}: {value}"

            # Add to feed buffer (newest first)
            self._add_to_feed(feed_line, rig_name)

            print(f"[{rig_name}] RX.DIRECTED: {from_call} -> {to_call}: {value}")

            # Process the message for database insertion
            data_type = self._process_directed_message(
                rig_name, value, from_call, to_call, grid, freq, snr, utc_str
            )

            # Refresh only the relevant UI component
            if data_type == "statrep":
                self._load_statrep_data()
                self._save_map_position(callback=self._load_map)
            elif data_type == "message":
                self._load_message_data()
            elif data_type == "marquee":
                self._load_marquee()
            elif data_type == "checkin":
                self._save_map_position(callback=self._load_map)

        # Handle RX.ACTIVITY messages (band activity for live feed)
        elif msg_type == "RX.ACTIVITY":
            from_call = params.get("FROM", "")
            freq = params.get("FREQ", 0)
            offset = params.get("OFFSET", 0)
            snr = params.get("SNR", 0)
            utc_ms = params.get("UTC", 0)

            if value and from_call:
                utc_str = datetime.utcfromtimestamp(utc_ms / 1000).strftime("%Y-%m-%d   %H:%M:%S")
                dial_freq_mhz = (freq - offset) / 1000000 if freq else 0
                feed_line = f"{utc_str}\t{dial_freq_mhz:.3f}\t{offset}\t{snr:+03d}\t{from_call}: {value}"
                self._add_to_feed(feed_line, rig_name)

        # Handle RX.CALL_ACTIVITY response (debug feature)
        elif msg_type == "RX.CALL_ACTIVITY":
            if hasattr(self, 'debug_features'):
                self.debug_features.handle_call_activity_response(rig_name, message)

    def _add_to_feed(self, line: str, rig_name: str) -> None:
        """
        Add a message line to the live feed buffer.

        Args:
            line: Formatted message line.
            rig_name: Name of the rig (unused, frequency identifies rig).
        """
        # Insert at beginning (newest first)
        self.feed_messages.insert(0, line)

        # Trim buffer if too large
        if len(self.feed_messages) > self.max_feed_messages:
            self.feed_messages = self.feed_messages[:self.max_feed_messages]

        # Update display
        self._update_feed_display()

    def _process_directed_message(
        self,
        rig_name: str,
        value: str,
        from_call: str,
        to_call: str,
        grid: str,
        freq: int,
        snr: int,
        utc: str
    ) -> str:
        """
        Process a directed message received via TCP.

        Args:
            rig_name: Name of the rig that received the message.
            value: The message text content.
            from_call: Sender callsign.
            to_call: Recipient (callsign or @GROUP).
            grid: Sender's grid square.
            freq: Frequency in Hz.
            snr: Signal-to-noise ratio.
            utc: UTC timestamp string.

        Returns:
            Message type string ("statrep", "message", "marquee", "checkin") or empty string.
        """
        import re
        import maidenhead as mh

        # Message type markers (same as datareader)
        MSG_BULLETIN = "{^%}"
        MSG_STATREP = "{&%}"
        MSG_FORWARDED_STATREP = "{F%}"
        MSG_MARQUEE = "{*%}"
        MSG_CHECKIN = "{~%}"

        # Precedence mapping
        PRECEDENCE_MAP = {
            "1": "My Location",
            "2": "My Community",
            "3": "My County",
            "4": "My Region",
            "5": "Other Location"
        }

        # Extract group from to_call (e.g., "@MAGNET" -> "MAGNET")
        group = ""
        if to_call.startswith("@"):
            group = to_call[1:]

        # Extract callsign (remove suffix like /P)
        callsign = from_call.split("/")[0] if from_call else ""

        try:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()

            # Determine message type and process
            # Old CommStat format has marker at END: ,DATA,FIELDS,{MARKER}
            # Extract content BEFORE the marker, strip leading comma

            if MSG_BULLETIN in value:
                # Parse message: ,ID,MESSAGE,{^%}
                match = re.search(r',(.+?)\{\^\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 2:
                        id_num = fields[0].strip()
                        message_text = ",".join(fields[1:]).strip()

                        cursor.execute(
                            "INSERT OR REPLACE INTO messages_Data "
                            "(datetime, idnum, groupid, callsign, message, frequency) "
                            "VALUES(?, ?, ?, ?, ?, ?)",
                            (utc, id_num, group, callsign, message_text, freq)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added Message from: {callsign} ID: {id_num}\033[0m")
                        conn.close()
                        return "message"

            elif MSG_FORWARDED_STATREP in value:
                # Parse forwarded statrep: ,GRID,PREC,SRID,SRCODE,COMMENTS,ORIG_CALL,{F%}
                match = re.search(r',(.+?)\{F\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 6:
                        curgrid = fields[0].strip()
                        prec1 = fields[1].strip()
                        srid = fields[2].strip()
                        srcode = fields[3].strip()
                        comments = fields[4].strip() if len(fields) > 4 else ""
                        orig_call = fields[5].strip() if len(fields) > 5 else callsign

                        # Expand compressed "+" to all green (111111111111)
                        if srcode == "+":
                            srcode = "111111111111"

                        prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                        if len(srcode) >= 12:
                            sr_fields = list(srcode)
                            cursor.execute(
                                "INSERT OR IGNORE INTO Statrep_Data "
                                "(datetime, callsign, groupname, grid, SRid, prec, status, commpwr, pubwtr, "
                                "med, ota, trav, net, fuel, food, crime, civil, political, comments, source, frequency) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (utc, orig_call, group, curgrid, srid, prec,
                                 sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                                 sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                                 sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                                 comments, "1", freq)
                            )
                            conn.commit()
                            print(f"\033[92m[{rig_name}] Added Forwarded StatRep from: {orig_call} ID: {srid}\033[0m")
                            conn.close()
                            return "statrep"

            elif MSG_STATREP in value:
                # Parse statrep: ,GRID,PREC,SRID,SRCODE,COMMENTS,{&%}
                match = re.search(r',(.+?)\{&\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 4:
                        curgrid = fields[0].strip()
                        prec1 = fields[1].strip()
                        srid = fields[2].strip()
                        srcode = fields[3].strip()
                        comments = fields[4].strip() if len(fields) > 4 else ""

                        # Expand compressed "+" to all green (111111111111)
                        if srcode == "+":
                            srcode = "111111111111"

                        prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                        if len(srcode) >= 12:
                            sr_fields = list(srcode)
                            cursor.execute(
                                "INSERT OR IGNORE INTO Statrep_Data "
                                "(datetime, callsign, groupname, grid, SRid, prec, status, commpwr, pubwtr, "
                                "med, ota, trav, net, fuel, food, crime, civil, political, comments, source, frequency) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (utc, callsign, group, curgrid, srid, prec,
                                 sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                                 sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                                 sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                                 comments, "1", freq)
                            )
                            conn.commit()
                            print(f"\033[92m[{rig_name}] Added StatRep from: {callsign} ID: {srid}\033[0m")
                            conn.close()
                            return "statrep"

            elif MSG_MARQUEE in value:
                # Parse marquee: ,ID,COLOR,MESSAGE,{*%}
                match = re.search(r',(.+?)\{\*\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 3:
                        id_num = fields[0].strip()
                        color = fields[1].strip()
                        marquee = ",".join(fields[2:]).strip()

                        cursor.execute(
                            "INSERT OR REPLACE INTO marquees_Data "
                            "(idnum, callsign, groupname, date, color, message, frequency) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?)",
                            (id_num, callsign, group, utc, color, marquee, freq)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added Marquee from: {callsign} ID: {id_num}\033[0m")
                        conn.close()
                        return "marquee"

            elif MSG_CHECKIN in value:
                # Parse checkin: ,TRAFFIC,STATE,GRID,{~%}
                match = re.search(r',(.+?)\{~\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 3:
                        traffic = fields[0].strip()
                        state = fields[1].strip()
                        checkin_grid = fields[2].strip()

                        # Convert grid to coordinates
                        try:
                            if len(checkin_grid) == 6:
                                coords = mh.to_location(checkin_grid)
                            else:
                                coords = mh.to_location(checkin_grid, center=True)
                            testlat = float(coords[0])
                            testlong = float(coords[1])
                        except Exception:
                            testlat = 0.0
                            testlong = 0.0

                        # Check for duplicate grids and offset
                        cursor.execute("SELECT Count() FROM members_Data WHERE grid = ?", (checkin_grid,))
                        num_rows = cursor.fetchone()[0]
                        if num_rows > 1:
                            testlat = testlat + (num_rows * 0.010)
                            testlong = testlong + (num_rows * 0.010)

                        # Get active group
                        active_group = self.db.get_active_group()

                        # Insert into members_Data
                        cursor.execute(
                            "INSERT OR REPLACE INTO members_Data "
                            "(date, callsign, groupname1, groupname2, gridlat, gridlong, state, grid) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, callsign, active_group, active_group, testlat, testlong, state, checkin_grid)
                        )

                        # Insert into checkins_Data
                        cursor.execute(
                            "INSERT OR IGNORE INTO checkins_Data "
                            "(date, callsign, groupname, traffic, gridlat, gridlong, state, grid) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, callsign, group, traffic, testlat, testlong, state, checkin_grid)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added Check-in from: {callsign}\033[0m")
                        conn.close()
                        return "checkin"

            # =================================================================
            # Pattern-based detection (no markers required)
            # =================================================================

            # StatRep pattern: GRID,PREC,SRID,SRCODE[,COMMENTS]
            # - GRID: 4-6 char maidenhead (AA00 or AA00aa)
            # - PREC: 1-5 (precedence)
            # - SRID: numeric ID
            # - SRCODE: + or 12 digits [1-4]
            # - COMMENTS: optional
            # Only process if sent to a group (@GROUP)
            if to_call.startswith("@"):
                statrep_pattern = re.match(
                    r'^([A-Z]{2}\d{2}[a-z]{0,2}),([1-5]),(\d+),(\+|[1-4]{12})(?:,(.*))?$',
                    value.strip(),
                    re.IGNORECASE
                )
                if statrep_pattern:
                    curgrid = statrep_pattern.group(1).upper()
                    prec1 = statrep_pattern.group(2)
                    srid = statrep_pattern.group(3)
                    srcode = statrep_pattern.group(4)
                    comments = statrep_pattern.group(5).strip() if statrep_pattern.group(5) else ""

                    # Expand compressed "+" to all green (111111111111)
                    if srcode == "+":
                        srcode = "111111111111"

                    prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                    if len(srcode) >= 12:
                        sr_fields = list(srcode)
                        cursor.execute(
                            "INSERT OR IGNORE INTO Statrep_Data "
                            "(datetime, callsign, groupname, grid, SRid, prec, status, commpwr, pubwtr, "
                            "med, ota, trav, net, fuel, food, crime, civil, political, comments, source, frequency) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, callsign, group, curgrid, srid, prec,
                             sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                             sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                             sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                             comments, "1", freq)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added StatRep (pattern) from: {callsign} ID: {srid}\033[0m")
                        conn.close()
                        return "statrep"

            # Check for standard JS8Call MSG format (no special marker)
            # Format: " MSG " with spaces on both sides
            # Save if: to group OR to one of user's callsigns
            if " MSG " in value:
                # Check if this message should be saved
                is_to_group = to_call.startswith("@")
                is_to_user = to_call in self.rig_callsigns.values()

                if is_to_group or is_to_user:
                    # Extract message text after "MSG "
                    msg_match = re.search(r'\bMSG\s+(.+)', value)
                    if msg_match:
                        message_text = msg_match.group(1).strip()

                        # Generate a simple ID based on timestamp
                        import time
                        id_num = str(int(time.time()) % 100000)

                        cursor.execute(
                            "INSERT OR REPLACE INTO messages_Data "
                            "(datetime, idnum, groupid, callsign, message, frequency) "
                            "VALUES(?, ?, ?, ?, ?, ?)",
                            (utc, id_num, group, callsign, message_text, freq)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added MSG from: {callsign} to: {to_call}\033[0m")
                        conn.close()
                        return "message"

            conn.close()

        except sqlite3.Error as e:
            print(f"\033[91m[{rig_name}] Database error: {e}\033[0m")
        except Exception as e:
            print(f"\033[91m[{rig_name}] Error processing message: {e}\033[0m")

        return ""

    def _on_qrz_enable(self) -> None:
        """Open QRZ Enable dialog for managing QRZ.com credentials."""
        # Get current settings
        username, password, is_active = self.db.get_qrz_settings()

        # Create dialog
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("QRZ Enable")
        dialog.setFixedWidth(400)
        layout = QtWidgets.QVBoxLayout(dialog)

        # Warning message
        warning_label = QtWidgets.QLabel(
            "NOTE: You must have a QRZ XML subscription for this feature to work.\n"
            "Visit qrz.com to subscribe."
        )
        warning_label.setStyleSheet("color: #FF6600; font-weight: bold;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        layout.addSpacing(10)

        # Enable checkbox
        enable_checkbox = QtWidgets.QCheckBox("Enable QRZ Lookups")
        enable_checkbox.setChecked(is_active)
        layout.addWidget(enable_checkbox)

        layout.addSpacing(10)

        # Form layout for credentials
        form_layout = QtWidgets.QFormLayout()

        username_input = QtWidgets.QLineEdit()
        username_input.setText(username)
        username_input.setPlaceholderText("QRZ.com username")
        form_layout.addRow("Username:", username_input)

        password_input = QtWidgets.QLineEdit()
        password_input.setText(password)
        password_input.setPlaceholderText("QRZ.com password")
        password_input.setEchoMode(QtWidgets.QLineEdit.Password)
        form_layout.addRow("Password:", password_input)

        layout.addLayout(form_layout)

        layout.addSpacing(20)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save")
        cancel_btn = QtWidgets.QPushButton("Cancel")

        save_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Save settings
            new_username = username_input.text().strip()
            new_password = password_input.text()
            new_active = enable_checkbox.isChecked()

            if self.db.set_qrz_settings(new_username, new_password, new_active):
                status = "enabled" if new_active else "disabled"
                QtWidgets.QMessageBox.information(
                    self, "QRZ Settings",
                    f"QRZ settings saved. Lookups are {status}."
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Error",
                    "Failed to save QRZ settings."
                )

    def _on_band_conditions(self) -> None:
        """Show Band Conditions dialog with N0NBH solar-terrestrial data."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Band Conditions")
        dialog.setMinimumSize(480, 200)
        dialog.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image label
        image_label = QtWidgets.QLabel("Loading band conditions...")
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

        # Link label
        link_label = QtWidgets.QLabel(
            '<a href="https://www.hamqsl.com/solar.html">Solar-Terrestrial Data provided by N0NBH</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(link_label)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # Storage for fetched data
        fetch_result = {'data': None, 'error': None}

        def fetch_image():
            try:
                url = "https://www.hamqsl.com/solar101pic.php"
                request = urllib.request.Request(url, headers={'User-Agent': 'CommStat-Improved/2.5'})
                # Create SSL context that bypasses certificate verification
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(request, timeout=15, context=ssl_context) as response:
                    fetch_result['data'] = response.read()
            except Exception as e:
                fetch_result['error'] = str(e)

        def update_ui():
            if fetch_result['data']:
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(fetch_result['data'])
                image_label.setPixmap(pixmap)
                dialog.adjustSize()
            elif fetch_result['error']:
                image_label.setText(f"Failed to load band conditions: {fetch_result['error']}")
            else:
                # Still loading, check again
                QTimer.singleShot(100, update_ui)

        # Start fetch in background thread
        thread = threading.Thread(target=fetch_image, daemon=True)
        thread.start()

        # Start polling for result
        QTimer.singleShot(100, update_ui)

        dialog.exec_()

    def _on_solar_flux(self) -> None:
        """Show Solar Flux dialog with N0NBH solar flux chart."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Solar Flux")
        dialog.setMinimumSize(480, 200)
        dialog.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image label
        image_label = QtWidgets.QLabel("Loading solar flux data...")
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

        # Link label
        link_label = QtWidgets.QLabel(
            '<a href="https://www.hamqsl.com/solar.html">Solar-Terrestrial Data provided by N0NBH</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(link_label)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # Storage for fetched data
        fetch_result = {'data': None, 'error': None}

        def fetch_image():
            try:
                url = "https://www.hamqsl.com/marston.php"
                request = urllib.request.Request(url, headers={'User-Agent': 'CommStat-Improved/2.5'})
                # Create SSL context that bypasses certificate verification
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(request, timeout=15, context=ssl_context) as response:
                    fetch_result['data'] = response.read()
            except Exception as e:
                fetch_result['error'] = str(e)

        def update_ui():
            if fetch_result['data']:
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(fetch_result['data'])
                image_label.setPixmap(pixmap)
                dialog.adjustSize()
            elif fetch_result['error']:
                image_label.setText(f"Failed to load solar flux data: {fetch_result['error']}")
            else:
                # Still loading, check again
                QTimer.singleShot(100, update_ui)

        # Start fetch in background thread
        thread = threading.Thread(target=fetch_image, daemon=True)
        thread.start()

        # Start polling for result
        QTimer.singleShot(100, update_ui)

        dialog.exec_()

    def _on_world_map(self) -> None:
        """Show World Map dialog."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("World Map")
        dialog.setMinimumSize(480, 200)
        dialog.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image label
        image_label = QtWidgets.QLabel("Loading solar conditions...")
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

        # Link label
        link_label = QtWidgets.QLabel(
            '<a href="https://www.hamqsl.com/solar.html">View more at hamqsl.com</a>'
        )
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(link_label)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # Storage for fetched data
        fetch_result = {'data': None, 'error': None}

        def fetch_image():
            try:
                url = "https://www.hamqsl.com/solarmuf.php"
                request = urllib.request.Request(url, headers={'User-Agent': 'CommStat-Improved/2.5'})
                # Create SSL context that bypasses certificate verification
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(request, timeout=15, context=ssl_context) as response:
                    fetch_result['data'] = response.read()
            except Exception as e:
                fetch_result['error'] = str(e)

        def update_ui():
            if fetch_result['data']:
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(fetch_result['data'])
                image_label.setPixmap(pixmap)
                dialog.adjustSize()
            elif fetch_result['error']:
                image_label.setText(f"Failed to load solar data: {fetch_result['error']}")
            else:
                # Still loading, check again
                QTimer.singleShot(100, update_ui)

        # Start fetch in background thread
        thread = threading.Thread(target=fetch_image, daemon=True)
        thread.start()

        # Start polling for result
        QTimer.singleShot(100, update_ui)

        dialog.exec_()

    def _on_about(self) -> None:
        """Open About window."""
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormAbout()
        dialog.ui.setupUi(dialog)
        dialog.exec_()


# =============================================================================
# Application Entry Point
# =============================================================================

def main() -> None:
    """Application entry point."""
    # Check for debug mode
    debug_mode = "--debug" in sys.argv

    # Check for pending update - refuse to run if update.zip exists
    update_zip = Path(__file__).parent / "updates" / "update.zip"
    if update_zip.exists():
        app = QtWidgets.QApplication(sys.argv)
        QtWidgets.QMessageBox.critical(
            None,
            "Update Pending",
            "An update is waiting to be applied.\n\n"
            "Please run startup.py instead of commstat.py\n"
            "to apply the update."
        )
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)

    # Load configuration and database
    config = ConfigManager()
    db = DatabaseManager()

    # Initialize Groups table (creates if needed, seeds defaults)
    db.init_groups_table()

    # Initialize db_version table (creates if needed, seeds version 1)
    db.init_db_version_table()

    # Initialize QRZ settings table (creates if needed)
    db.init_qrz_table()

    # Create and show main window
    window = MainWindow(config, db, debug_mode=debug_mode)
    window.show()

    if debug_mode:
        print("Debug mode enabled")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
