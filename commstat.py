# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
CommStat-Improved v2.5.0 - Rebuilt with best practices

A PyQt5 application for monitoring JS8Call communications,
displaying status reports, bulletins, and live data feeds.
"""

import sys
import os
import io
import sqlite3
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import tempfile
import webbrowser
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
from settings import SettingsDialog
from colors import ColorsDialog
from filter import FilterDialog
from groups import GroupsDialog
from js8mail import JS8MailDialog
from js8sms import JS8SMSDialog
from marquee import Ui_FormMarquee
from bulletin import Ui_FormBull
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
DEFAULT_FILTER_END = "2030-01-01"

# Group settings
MAX_GROUP_NAME_LENGTH = 15
DEFAULT_GROUPS = ["MAGNET", "AMRRON", "PREPPERNET"]

# Map and layout dimensions
MAP_WIDTH = 604
MAP_HEIGHT = 340
FILTER_HEIGHT = 20
SLIDESHOW_INTERVAL = 1  # Minutes between image changes
PLAYLIST_URL = "https://js8call-improved.com/playlist.php"

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
        self.user_info: Dict[str, str] = {}
        self.directed_config: Dict[str, str] = {}
        self.filter_settings: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load all configuration sections from file."""
        if not self.config_path.exists():
            print(f"Warning: Config file '{self.config_path}' not found. Using defaults.")
            return

        config = ConfigParser()
        config.read(self.config_path)

        self._load_user_info(config)
        self._load_directed_config(config)
        self._load_filter_settings(config)
        self._load_colors(config)

    def _load_user_info(self, config: ConfigParser) -> None:
        """Load user information section."""
        if config.has_section("USERINFO"):
            self.user_info = {
                'callsign': config.get("USERINFO", "callsign", fallback=""),
                'callsign_suffix': config.get("USERINFO", "callsignsuffix", fallback=""),
                'grid': config.get("USERINFO", "grid", fallback=""),
            }

    def _load_directed_config(self, config: ConfigParser) -> None:
        """Load display configuration section."""
        if config.has_section("DIRECTEDCONFIG"):
            self.directed_config = {
                'state': config.get("DIRECTEDCONFIG", "state", fallback=""),
                'hide_heartbeat': config.getboolean("DIRECTEDCONFIG", "hide_heartbeat", fallback=False),
                'show_all_groups': config.getboolean("DIRECTEDCONFIG", "show_all_groups", fallback=False),
                'hide_map': config.getboolean("DIRECTEDCONFIG", "hide_map", fallback=False),
            }
        else:
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': False, 'hide_map': False}

    def _load_filter_settings(self, config: ConfigParser) -> None:
        """Load filter settings section."""
        if config.has_section("FILTER"):
            self.filter_settings = {
                'start': config.get("FILTER", "start", fallback=DEFAULT_FILTER_START),
                'end': config.get("FILTER", "end", fallback=DEFAULT_FILTER_END)
            }

    def _load_colors(self, config: ConfigParser) -> None:
        """Load color scheme from config, using defaults for missing values."""
        needs_save = False

        if not config.has_section("COLORS"):
            config.add_section("COLORS")
            needs_save = True

        for key in self.colors:
            if config.has_option("COLORS", key):
                self.colors[key] = config.get("COLORS", key)
            else:
                # Missing key - add default to config
                config.set("COLORS", key, self.colors[key])
                needs_save = True

        # Write defaults to config.ini if any were missing
        if needs_save:
            try:
                with open(CONFIG_FILE, 'w') as f:
                    config.write(f)
                print("Rebuilt missing colors in config.ini")
            except IOError as e:
                print(f"Warning: Could not save colors to config: {e}")

    def get_color(self, key: str) -> str:
        """
        Get a color value by key with validation.

        Args:
            key: The color key name

        Returns:
            The hex color value, or default if invalid
        """
        color = self.colors.get(key, '#FFFFFF')
        if not QColor(color).isValid():
            default = DEFAULT_COLORS.get(key, '#FFFFFF')
            print(f"Warning: Invalid color '{color}' for '{key}', using default '{default}'")
            return default
        return color

    def get_callsign(self) -> str:
        """Get the user's callsign with optional suffix."""
        callsign = self.user_info.get('callsign', '')
        suffix = self.user_info.get('callsign_suffix', '')
        if suffix:
            return f"{callsign}/{suffix}"
        return callsign

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
        group: Optional[str],
        start: str,
        end: str
    ) -> List[Tuple]:
        """
        Fetch StatRep data from database.

        Args:
            group: Selected group name, or None for all groups
            start/end: Date range filter

        Returns:
            List of tuples containing StatRep records
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                if group:
                    query = """
                        SELECT datetime, groupname, callsign, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM StatRep_Data
                        WHERE groupname = ?
                          AND datetime BETWEEN ? AND ?
                    """
                    params = [group, start, end]
                else:
                    query = """
                        SELECT datetime, groupname, callsign, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM StatRep_Data
                        WHERE datetime BETWEEN ? AND ?
                    """
                    params = [start, end]
                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_bulletin_data(
        self,
        group: Optional[str],
        start: str,
        end: str
    ) -> List[Tuple]:
        """
        Fetch bulletin data from database.

        Args:
            group: Selected group name, or None for all groups
            start/end: Date range filter

        Returns:
            List of tuples containing bulletin records
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                if group:
                    cursor.execute(
                        """SELECT datetime, groupid, callsign, message
                           FROM bulletins_Data
                           WHERE groupid = ? AND datetime BETWEEN ? AND ?""",
                        [group, start, end]
                    )
                else:
                    cursor.execute(
                        """SELECT datetime, groupid, callsign, message
                           FROM bulletins_Data
                           WHERE datetime BETWEEN ? AND ?""",
                        [start, end]
                    )
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_latest_marquee(self, group: Optional[str]) -> Optional[Tuple]:
        """
        Fetch the latest marquee message for a group.

        Args:
            group: Selected group name, or None for all groups

        Returns:
            Tuple containing marquee data or None
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                if group:
                    cursor.execute(
                        "SELECT idnum, callsign, groupname, date, color, message FROM marquees_data WHERE groupname = ? ORDER BY date DESC LIMIT 1",
                        [group]
                    )
                else:
                    cursor.execute(
                        "SELECT idnum, callsign, groupname, date, color, message FROM marquees_data ORDER BY date DESC LIMIT 1"
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
                        is_active INTEGER DEFAULT 0
                    )
                """)
                connection.commit()

                # Check if table is empty
                cursor.execute("SELECT COUNT(*) FROM Groups")
                if cursor.fetchone()[0] == 0:
                    # Seed default groups, first one is active
                    for i, group_name in enumerate(DEFAULT_GROUPS):
                        cursor.execute(
                            "INSERT INTO Groups (name, is_active) VALUES (?, ?)",
                            (group_name.upper(), 1 if i == 0 else 0)
                        )
                    connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing Groups table: {error}")

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

    def get_active_group(self) -> str:
        """Get the currently active group name."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM Groups WHERE is_active = 1")
                result = cursor.fetchone()
                return result[0] if result else ""
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return ""

    def set_active_group(self, group_name: str) -> bool:
        """Set a group as the active group."""
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

    def add_group(self, group_name: str) -> bool:
        """Add a new group. Returns True if successful."""
        name = group_name.strip().upper()[:MAX_GROUP_NAME_LENGTH]
        if not name:
            return False
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO Groups (name, is_active) VALUES (?, 0)",
                    (name,)
                )
                connection.commit()
                return True
        except sqlite3.IntegrityError:
            # Duplicate name
            return False
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return False

    def remove_group(self, group_name: str) -> bool:
        """Remove a group. Returns False if it's the last group."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                # Check if this is the last group
                cursor.execute("SELECT COUNT(*) FROM Groups")
                if cursor.fetchone()[0] <= 1:
                    return False
                # Check if this group is active
                cursor.execute(
                    "SELECT is_active FROM Groups WHERE name = ?",
                    (group_name.upper(),)
                )
                result = cursor.fetchone()
                was_active = result and result[0] == 1
                # Delete the group
                cursor.execute(
                    "DELETE FROM Groups WHERE name = ?",
                    (group_name.upper(),)
                )
                # If deleted group was active, activate another one
                if was_active and cursor.rowcount > 0:
                    cursor.execute(
                        "UPDATE Groups SET is_active = 1 WHERE id = (SELECT MIN(id) FROM Groups)"
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



# =============================================================================
# MainWindow - Main application window
# =============================================================================

class MainWindow(QtWidgets.QMainWindow):
    """Main application window for CommStat-Improved."""

    def __init__(self, config: ConfigManager, db: DatabaseManager):
        """
        Initialize the main window.

        Args:
            config: ConfigManager instance with loaded settings
            db: DatabaseManager instance for database operations
        """
        super().__init__()
        self.config = config
        self.db = db

        # Initialize JS8Call connector manager and TCP connection pool
        self.connector_manager = ConnectorManager()
        self.connector_manager.init_connectors_table()
        self.connector_manager.add_frequency_columns()
        self.tcp_pool = TCPConnectionPool(self.connector_manager, self)
        self.tcp_pool.any_message_received.connect(self._handle_tcp_message)
        self.tcp_pool.any_connection_changed.connect(self._handle_connection_changed)

        # Live feed message buffer (stores messages from all TCP connections)
        self.feed_messages: List[str] = []
        self.max_feed_messages = 500  # Limit buffer size

        # Add "Connecting..." messages for each configured rig before connecting
        connectors = self.connector_manager.get_all_connectors()
        for conn in connectors:
            self.feed_messages.append(f"[{conn['rig_name']}] Connecting...")

        # Now initiate connections
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
        """Save window position before closing."""
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

        # Row stretches: header and labels don't stretch
        self.main_layout.setRowStretch(0, 0)  # Header
        self.main_layout.setRowStretch(1, 1)  # StatRep table (50%)
        self.main_layout.setRowStretch(2, 1)  # Feed text (50%)
        self.main_layout.setRowStretch(3, 0)  # Map row 1 / Filter (fixed)
        self.main_layout.setRowStretch(4, 0)  # Map row 2 / Bulletin (fixed)

        # Setup components
        self._setup_menu()
        self._setup_header()
        self._setup_statrep_table()
        self._setup_filter_labels()
        self._setup_map_widget()
        self._setup_live_feed()
        self._setup_bulletin_table()
        self._setup_timers()

        # Load initial data
        self._load_statrep_data()
        self._load_marquee()
        self._load_map()
        self._load_live_feed()
        self._load_bulletin_data()

        # Check playlist on startup for Force/Skip commands
        self._check_playlist_on_startup()

    def _setup_menu(self) -> None:
        """Create the menu bar with all actions."""
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 886, 24))
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
        self.setMenuBar(self.menubar)

        # Create the main menu
        self.menu = QtWidgets.QMenu("Menu", self.menubar)
        self.menubar.addMenu(self.menu)

        # Define menu actions: (name, text, handler)
        menu_items = [
            ("statrep", "STATREP", self._on_statrep),
            ("flash_bulletin", "FLASH BULLETIN", self._on_flash_bulletin),
            ("new_marquee", "NEW MARQUEE", self._on_new_marquee),
            ("js8email", "JS8 EMAIL", self._on_js8email),
            ("js8sms", "JS8 SMS", self._on_js8sms),
            None,  # Separator
            ("statrep_ack", "STATREP ACK", self._on_statrep_ack),
            ("net_roster", "NET MANAGER", self._on_net_roster),
            ("net_check_in", "NET CHECK IN", self._on_net_check_in),
            ("member_list", "MEMBER LIST", self._on_member_list),
            None,  # Separator
            ("groups", "MANAGE GROUPS", self._on_groups),
            ("js8_connectors", "JS8 CONNECTORS", self._on_js8_connectors),
            ("settings", "SETTINGS", self._on_settings),
            ("colors", "COLORS", self._on_colors),
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

        # Add checkable toggle for hiding heartbeat messages
        self.hide_heartbeat_action = QtWidgets.QAction("HIDE CQ & HEARTBEAT", self)
        self.hide_heartbeat_action.setCheckable(True)
        self.hide_heartbeat_action.setChecked(self.config.get_hide_heartbeat())
        self.hide_heartbeat_action.triggered.connect(self._on_toggle_heartbeat)
        self.menu.addAction(self.hide_heartbeat_action)
        self.actions["hide_heartbeat"] = self.hide_heartbeat_action

        # Add checkable toggle for showing all groups
        self.show_all_groups_action = QtWidgets.QAction("SHOW ALL GROUPS", self)
        self.show_all_groups_action.setCheckable(True)
        self.show_all_groups_action.setChecked(self.config.get_show_all_groups())
        self.show_all_groups_action.triggered.connect(self._on_toggle_show_all_groups)
        self.menu.addAction(self.show_all_groups_action)
        self.actions["show_all_groups"] = self.show_all_groups_action

        # Add checkable toggle for hiding map and showing videos
        self.hide_map_action = QtWidgets.QAction("HIDE MAP", self)
        self.hide_map_action.setCheckable(True)
        self.hide_map_action.setChecked(self.config.get_hide_map())
        self.hide_map_action.triggered.connect(self._on_toggle_hide_map)
        self.menu.addAction(self.hide_map_action)
        self.actions["hide_map"] = self.hide_map_action

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

        # Add About, Help, Exit directly to menu bar
        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self._on_about)
        self.menubar.addAction(about_action)
        self.actions["about"] = about_action

        help_action = QtWidgets.QAction("Help", self)
        help_action.triggered.connect(self._on_help)
        self.menubar.addAction(help_action)
        self.actions["help"] = help_action

        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.triggered.connect(qApp.quit)
        self.menubar.addAction(exit_action)
        self.actions["exit"] = exit_action

        # Add status bar
        self.statusbar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.statusbar)

    def _setup_header(self) -> None:
        """Create the header row with Active Group, Marquee, and Time."""
        # Header container widget with horizontal layout
        self.header_widget = QtWidgets.QWidget(self.central_widget)
        self.header_widget.setFixedHeight(38)
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        fg_color = self.config.get_color('program_foreground')

        # Active Group label
        self.label_active_group = QtWidgets.QLabel(self.header_widget)
        self.label_active_group.setStyleSheet(f"color: {fg_color};")
        self.label_active_group.setText(f"Active Group: {self.db.get_active_group()}")
        font = QtGui.QFont("Arial", 12, QtGui.QFont.Bold)
        self.label_active_group.setFont(font)
        self.header_layout.addWidget(self.label_active_group)

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

        # Add header to main layout (row 0, spans all columns)
        self.main_layout.addWidget(self.header_widget, 0, 0, 1, 2)

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

        # Add to layout (row 1, spans all columns)
        self.main_layout.addWidget(self.statrep_table, 1, 0, 1, 2)

    def _setup_filter_labels(self) -> None:
        """Create the filter status labels below the StatRep table."""
        filters = self.config.filter_settings
        fg_color = self.config.get_color('program_foreground')
        font = QtGui.QFont("Arial", 9)

        # Size policy that allows labels to shrink
        shrink_policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Ignored,
            QtWidgets.QSizePolicy.Preferred
        )

        # Filter label (date range only) - positioned above bulletin
        self.label_filter = QtWidgets.QLabel(self.central_widget)
        self.label_filter.setFont(font)
        self.label_filter.setStyleSheet(f"color: {fg_color};")
        self.label_filter.setText(
            f"Bulletin Filter:   Start Date: {filters.get('start', '')}  |  End Date: {filters.get('end', '')}"
        )
        self.label_filter.setSizePolicy(shrink_policy)
        self.label_filter.setFixedHeight(FILTER_HEIGHT)
        self.main_layout.addWidget(self.label_filter, 3, 1, 1, 1)

    def _setup_map_widget(self) -> None:
        """Create the map widget using QWebEngineView."""
        self.map_widget = QWebEngineView(self.central_widget)
        self.map_widget.setObjectName("mapWidget")
        self.map_widget.setFixedSize(MAP_WIDTH, MAP_HEIGHT)

        # Set custom page to handle statrep links
        custom_page = CustomWebEnginePage(self)
        self.map_widget.setPage(custom_page)

        # Add to layout (row 3-4, column 0 only, spanning 2 rows)
        self.main_layout.addWidget(self.map_widget, 3, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Set column stretches: map column fixed, bulletin column stretches
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
        self.main_layout.addWidget(self.map_disabled_label, 3, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Image slideshow state: list of (image_path, click_url) tuples
        self.slideshow_items: List[Tuple[str, Optional[str]]] = []
        self.slideshow_index: int = 0
        self.playlist_message: Optional[str] = None  # Message from playlist to display

        # Timer for slideshow
        self.slideshow_timer = QtCore.QTimer(self)
        self.slideshow_timer.timeout.connect(self._show_next_image)
        self.slideshow_timer.setInterval(SLIDESHOW_INTERVAL * 60000)  # Convert minutes to ms

    def _check_playlist_on_startup(self) -> None:
        """Check playlist on startup for Force command (runs in background thread)."""
        thread = threading.Thread(target=self._check_playlist_for_force_async, daemon=True)
        thread.start()

    def _check_playlist_for_force_async(self) -> None:
        """Background thread version of Force check - emits signal to update UI."""
        import re
        from datetime import datetime
        try:
            with urllib.request.urlopen(PLAYLIST_URL, timeout=10) as response:
                content = response.read().decode('utf-8')

                # Extract content between <pre> tags if present
                pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
                if pre_match:
                    content = pre_match.group(1)

                content = content.strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]

                print(f"Playlist lines: {lines[:3]}")  # Debug output

                if not lines:
                    return

                # Line 1: Check for expiration date (case-insensitive)
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    today = datetime.now().date()
                    print(f"Playlist date: {expiry_date}, Today: {today}")  # Debug
                    if expiry_date < today:
                        # Date has passed - skip all playlist rules including Force
                        print("Playlist expired, skipping Force check")
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
            self.hide_map_action.setChecked(True)
            self.map_widget.hide()
            self.map_disabled_label.show()
            self._start_slideshow()

    def _fetch_remote_playlist(self) -> List[Tuple[str, Optional[str]]]:
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
        self.playlist_message = None  # Reset message

        try:
            with urllib.request.urlopen(PLAYLIST_URL, timeout=10) as response:
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
                        print(f"Playlist expired on {expiry_date}, skipping rules")
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
                    self.playlist_message = msg_match.group(1)
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
        remote_items = self._fetch_remote_playlist()

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
        if self.playlist_message:
            self._display_playlist_message()
            self.slideshow_timer.start()  # Keep timer running to check for changes
        elif self.slideshow_items:
            self._show_current_image()
            self.slideshow_timer.start()
        else:
            # No images and no message - show "Map Disabled"
            self.map_disabled_label.setPixmap(QtGui.QPixmap())
            self.map_disabled_label.setText("Map Disabled")

    @QtCore.pyqtSlot()
    def _display_playlist_message(self) -> None:
        """Display the playlist message centered in the label."""
        if not self.playlist_message:
            return

        # Clear any existing pixmap
        self.map_disabled_label.setPixmap(QtGui.QPixmap())

        # Set text with center alignment (both horizontal and vertical)
        self.map_disabled_label.setText(self.playlist_message)
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
        thread = threading.Thread(target=self._check_playlist_content_async, daemon=True)
        thread.start()

        # If showing a message, just keep displaying it (will be updated by async check)
        if self.playlist_message:
            return

        # Otherwise advance to next image
        if not self.slideshow_items:
            return

        self.slideshow_index = (self.slideshow_index + 1) % len(self.slideshow_items)
        self._show_current_image()

    def _check_playlist_content_async(self) -> None:
        """Background thread to check playlist for message changes."""
        import re
        from datetime import datetime
        try:
            with urllib.request.urlopen(PLAYLIST_URL, timeout=10) as response:
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
                        if self.playlist_message:
                            self.playlist_message = None
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
                    if new_message != self.playlist_message:
                        self.playlist_message = new_message
                        QtCore.QMetaObject.invokeMethod(
                            self, "_display_playlist_message",
                            QtCore.Qt.QueuedConnection
                        )
                elif self.playlist_message:
                    # Message was removed from playlist
                    self.playlist_message = None
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
        if self.playlist_message:
            self._display_playlist_message()
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

        # Add to layout (row 2, full width)
        self.main_layout.addWidget(self.feed_text, 2, 0, 1, 2)

    def _load_live_feed(self) -> None:
        """Initialize the live feed display from buffer."""
        self._update_feed_display()

    def _update_feed_display(self) -> None:
        """Update the live feed display from the message buffer."""
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

    def _setup_bulletin_table(self) -> None:
        """Create the bulletin data table."""
        self.bulletin_table = QtWidgets.QTableWidget(self.central_widget)
        self.bulletin_table.setObjectName("bulletinTable")
        self.bulletin_table.setColumnCount(4)
        self.bulletin_table.setRowCount(0)

        # Apply styling
        title_bg = self.config.get_color('title_bar_background')
        title_fg = self.config.get_color('title_bar_foreground')
        data_bg = self.config.get_color('data_background')
        data_fg = self.config.get_color('data_foreground')

        self.bulletin_table.setStyleSheet(f"""
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
        self.bulletin_table.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                padding: 4px;
            }}
        """)

        # Set headers
        self.bulletin_table.setHorizontalHeaderLabels([
            "Date Time UTC", "Group", "Callsign", "Bulletin"
        ])

        # Configure header behavior
        header = self.bulletin_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.bulletin_table.verticalHeader().setVisible(False)
        self.bulletin_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.bulletin_table.setFixedHeight(MAP_HEIGHT - FILTER_HEIGHT)

        # Add to layout (row 4, column 1)
        self.main_layout.addWidget(self.bulletin_table, 4, 1, 1, 1)

    def _load_bulletin_data(self) -> None:
        """Load bulletin data from database into the table."""
        filters = self.config.filter_settings
        group = None if self.config.get_show_all_groups() else self.db.get_active_group()
        data = self.db.get_bulletin_data(
            group=group,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', DEFAULT_FILTER_END)
        )

        # Clear and populate table
        self.bulletin_table.setRowCount(0)
        for row_num, row_data in enumerate(data):
            self.bulletin_table.insertRow(row_num)
            for col_num, value in enumerate(row_data):
                item = QTableWidgetItem(str(value) if value is not None else "")
                self.bulletin_table.setItem(row_num, col_num, item)

        # Sort by datetime descending
        self.bulletin_table.sortItems(0, QtCore.Qt.DescendingOrder)

    def _load_map(self) -> None:
        """Generate and display the folium map with StatRep pins."""
        filters = self.config.filter_settings
        group = self.db.get_active_group()

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
                group=group,
                start=filters.get('start', DEFAULT_FILTER_START),
                end=filters.get('end', DEFAULT_FILTER_END)
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
        group = None if self.config.get_show_all_groups() else self.db.get_active_group()

        # Fetch data from database
        data = self.db.get_statrep_data(
            group=group,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', DEFAULT_FILTER_END)
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

        # Data refresh timer - updates every 20 seconds
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(20000)

        # Marquee animation timeline
        self.marquee_timeline = QtCore.QTimeLine()
        self.marquee_timeline.setCurveShape(QtCore.QTimeLine.LinearCurve)
        self.marquee_timeline.frameChanged.connect(self._update_marquee_text)
        self.marquee_timeline.finished.connect(self._next_marquee)

        # Marquee state
        self.marquee_text = ""
        self.marquee_chars = 0

    def _refresh_data(self) -> None:
        """Refresh StatRep, bulletin data, and map from database."""
        # Reload data from database (TCP handler inserts data directly)
        self._load_statrep_data()
        self._load_bulletin_data()

        # Save map position before refresh, then reload map
        self._save_map_position(callback=self._load_map)

        # Check playlist for Force command in background (even when map is shown)
        thread = threading.Thread(target=self._check_playlist_for_force_async, daemon=True)
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
        group = self.db.get_active_group()
        result = self.db.get_latest_marquee(group)

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

    def _on_flash_bulletin(self) -> None:
        """Open Flash Bulletin window."""
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormBull(self.tcp_pool, self.connector_manager)
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_filter(self) -> None:
        """Open Display Filter window."""
        dialog = FilterDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Reload config and refresh data
            self.config = ConfigManager()
            self._setup_filter_labels()
            self._load_statrep_data()
            self._load_bulletin_data()
            # Save map position before refresh, then reload map
            self._save_map_position(callback=self._load_map)

    def _reset_filter_date(self, days_ago: int) -> None:
        """Reset filter start date to specified days ago and apply."""
        from datetime import datetime, timedelta

        # Calculate new start date
        new_start = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        new_end = "2030-01-01"

        # Update config.ini
        config = ConfigParser()
        config.read(CONFIG_FILE)

        if not config.has_section("FILTER"):
            config.add_section("FILTER")

        config.set("FILTER", "start", new_start)
        config.set("FILTER", "end", new_end)

        with open(CONFIG_FILE, 'w') as f:
            config.write(f)

        # Reload config and refresh data
        self.config = ConfigManager()
        self._setup_filter_labels()
        self._load_statrep_data()
        self._load_bulletin_data()
        self._save_map_position(callback=self._load_map)

        print(f"Filter reset: start={new_start}, end={new_end}")

    def _on_toggle_heartbeat(self, checked: bool) -> None:
        """Toggle heartbeat message filtering in live feed."""
        self.config.set_hide_heartbeat(checked)
        self._load_live_feed()

    def _on_toggle_show_all_groups(self, checked: bool) -> None:
        """Toggle showing data from all groups."""
        self.config.set_show_all_groups(checked)
        self._load_statrep_data()
        self._load_bulletin_data()
        self._load_marquee()

    def _on_toggle_hide_map(self, checked: bool) -> None:
        """Toggle between map and image slideshow."""
        self.config.set_hide_map(checked)
        if checked:
            self.map_widget.hide()
            self.map_disabled_label.show()
            self._start_slideshow()
        else:
            self._stop_slideshow()
            self.playlist_message = None  # Clear any message
            self.map_disabled_label.hide()
            self.map_widget.show()

    def _on_groups(self) -> None:
        """Open Manage Groups window."""
        dialog = GroupsDialog(self.db, self)
        dialog.exec_()
        # Refresh header to show new active group
        self._update_active_group_label()
        # Refresh data for new group
        self._load_statrep_data()
        self._load_bulletin_data()
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
            status_line = f"[{rig_name}] Connected!"
        else:
            status_line = f"[{rig_name}] Disconnected"

        # Insert at beginning (newest first)
        self.feed_messages.insert(0, status_line)
        self._update_feed_display()

    def _handle_tcp_message(self, rig_name: str, message: dict) -> None:
        """
        Handle incoming TCP message from JS8Call.

        Args:
            rig_name: Name of the rig that received the message.
            message: Parsed JSON message from JS8Call.
        """
        from datetime import datetime

        msg_type = message.get("type", "")
        value = message.get("value", "")
        params = message.get("params", {})

        # Handle RX.DIRECTED messages
        if msg_type == "RX.DIRECTED":
            from_call = params.get("FROM", "")
            to_call = params.get("TO", "")
            grid = params.get("GRID", "")
            freq = params.get("FREQ", 0)
            snr = params.get("SNR", 0)
            utc_ms = params.get("UTC", 0)

            # Convert UTC milliseconds to datetime string
            utc_str = datetime.utcfromtimestamp(utc_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")

            # Format feed line similar to DIRECTED.TXT format
            # Format: UTC  SNR  FREQ  FROM: VALUE
            freq_khz = freq / 1000 if freq else 0
            feed_line = f"{utc_str}\t{snr:+d}\t{freq_khz:.1f}\t{from_call}: {value}"

            # Add to feed buffer (newest first)
            self._add_to_feed(feed_line, rig_name)

            print(f"[{rig_name}] RX.DIRECTED: {from_call} -> {to_call}: {value}")

            # Process the message for database insertion
            processed = self._process_directed_message(
                rig_name, value, from_call, to_call, grid, freq, snr, utc_str
            )

            if processed:
                self._refresh_data()

        # Handle RX.ACTIVITY messages (band activity for live feed)
        elif msg_type == "RX.ACTIVITY":
            from_call = params.get("FROM", "")
            freq = params.get("FREQ", 0)
            snr = params.get("SNR", 0)
            utc_ms = params.get("UTC", 0)

            if value and from_call:
                utc_str = datetime.utcfromtimestamp(utc_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
                freq_khz = freq / 1000 if freq else 0
                feed_line = f"{utc_str}\t{snr:+d}\t{freq_khz:.1f}\t{from_call}: {value}"
                self._add_to_feed(feed_line, rig_name)

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
    ) -> bool:
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
            True if message was processed and inserted into database.
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
            if MSG_BULLETIN in value:
                # Parse bulletin: {^%} ID,MESSAGE
                match = re.search(r'\{\^\%\}\s*(.+)', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 2:
                        id_num = fields[0].strip()
                        bulletin = ",".join(fields[1:]).strip()

                        cursor.execute(
                            "INSERT OR REPLACE INTO bulletins_Data "
                            "(datetime, idnum, groupid, callsign, message, frequency) "
                            "VALUES(?, ?, ?, ?, ?, ?)",
                            (utc, id_num, group, callsign, bulletin, freq)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added Bulletin from: {callsign} ID: {id_num}\033[0m")
                        conn.close()
                        return True

            elif MSG_FORWARDED_STATREP in value:
                # Parse forwarded statrep: {F%} GRID,PREC,SRID,SRCODE,COMMENTS,ORIG_CALL
                match = re.search(r'\{F\%\}\s*(.+)', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 6:
                        curgrid = fields[0].strip()
                        prec1 = fields[1].strip()
                        srid = fields[2].strip()
                        srcode = fields[3].strip()
                        comments = fields[4].strip() if len(fields) > 4 else ""
                        orig_call = fields[5].strip() if len(fields) > 5 else callsign

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
                            return True

            elif MSG_STATREP in value:
                # Parse statrep: {&%} GRID,PREC,SRID,SRCODE,COMMENTS
                match = re.search(r'\{&\%\}\s*(.+)', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 4:
                        curgrid = fields[0].strip()
                        prec1 = fields[1].strip()
                        srid = fields[2].strip()
                        srcode = fields[3].strip()
                        comments = fields[4].strip() if len(fields) > 4 else ""

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
                            return True

            elif MSG_MARQUEE in value:
                # Parse marquee: {*%} ID,COLOR,MESSAGE
                match = re.search(r'\{\*\%\}\s*(.+)', value)
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
                        return True

            elif MSG_CHECKIN in value:
                # Parse checkin: {~%} TRAFFIC,STATE,GRID
                match = re.search(r'\{~\%\}\s*(.+)', value)
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
                        return True

            conn.close()

        except sqlite3.Error as e:
            print(f"\033[91m[{rig_name}] Database error: {e}\033[0m")
        except Exception as e:
            print(f"\033[91m[{rig_name}] Error processing message: {e}\033[0m")

        return False

    def _update_active_group_label(self) -> None:
        """Update the Active Group label in the header."""
        self.label_active_group.setText(f"Active Group: {self.db.get_active_group()}")

    def _on_settings(self) -> None:
        """Open Settings window."""
        dialog = SettingsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Reload config after settings are saved
            self.config = ConfigManager()

    def _on_colors(self) -> None:
        """Open Colors customization window."""
        dialog = ColorsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Reload config - colors apply on restart
            self.config = ConfigManager()
            QtWidgets.QMessageBox.information(
                self, "Colors Saved",
                "Color changes will apply when you restart the application."
            )

    def _on_help(self) -> None:
        """Open Help documentation."""
        pdf_path = Path("CommStat_Help.pdf").resolve()
        if pdf_path.exists():
            os.startfile(str(pdf_path))
        else:
            QtWidgets.QMessageBox.warning(
                self, "Help Not Found",
                "CommStat_Help.pdf not found in application directory."
            )

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
    app = QtWidgets.QApplication(sys.argv)

    # Load configuration and database
    config = ConfigManager()
    db = DatabaseManager()

    # Initialize Groups table (creates if needed, seeds defaults)
    db.init_groups_table()

    # Create and show main window
    window = MainWindow(config, db)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
