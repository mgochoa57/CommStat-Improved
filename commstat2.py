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
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import folium
import maidenhead as mh
import datareader

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import QTimer, QDateTime, Qt
from PyQt5.QtWidgets import qApp
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
from about import Ui_FormAbout
from settings2 import SettingsDialog
from colors import ColorsDialog
from filter2 import FilterDialog
from groups import GroupsDialog
from js8mail import Ui_FormJS8Mail
from js8sms import Ui_FormJS8SMS


# =============================================================================
# Constants
# =============================================================================

VERSION = "2.5.0"
WINDOW_TITLE = f"CommStat-Improved (v{VERSION}) by N0DDK"
WINDOW_SIZE = (1400, 818)
CONFIG_FILE = "config.ini"
ICON_FILE = "radiation-32.jpg"
DATABASE_FILE = "traffic.db3"

# Default filter date range
DEFAULT_FILTER_START = "2023-01-01"
DEFAULT_FILTER_END = "2030-01-01"

# Group settings
MAX_GROUP_NAME_LENGTH = 15
DEFAULT_GROUPS = ["MAGNET", "AMRRON", "PREPPERNET"]

# Map and layout dimensions
MAP_WIDTH = 620
MAP_HEIGHT = 340
FILTER_HEIGHT = 20

# Map and layout dimensions defaults
# MAP_WIDTH = 640
# MAP_HEIGHT = 350
# FILTER_HEIGHT = 20

# StatRep table column headers
STATREP_HEADERS = [
    "Date Time UTC", "ID", "Callsign", "Grid", "Scope", "Map Pin",
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
            if e.errno in (98, 10048):  # Address already in use (Linux/Windows)
                print(f"Port {p} in use, trying next...")
                continue
            raise
    print("Failed to start tile server")
    return None


# =============================================================================
# Custom Web Engine Page for Map Links
# =============================================================================

class CustomWebEnginePage(QWebEnginePage):
    """Handles navigation requests from the map, launching view_statrep.py for statrep links."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        """Intercept statrep links and launch external viewer."""
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
        """Load directed configuration section."""
        if config.has_section("DIRECTEDCONFIG"):
            self.directed_config = {
                'path': config.get("DIRECTEDCONFIG", "path", fallback=""),
                'server': config.get("DIRECTEDCONFIG", "server", fallback="127.0.0.1"),
                'UDP_port': config.get("DIRECTEDCONFIG", "UDP_port", fallback="2442"),
                'state': config.get("DIRECTEDCONFIG", "state", fallback=""),
            }

    def _load_filter_settings(self, config: ConfigParser) -> None:
        """Load filter settings section."""
        if config.has_section("FILTER"):
            self.filter_settings = {
                'start': config.get("FILTER", "start", fallback=DEFAULT_FILTER_START),
                'end': config.get("FILTER", "end", fallback=DEFAULT_FILTER_END)
            }

    def _load_colors(self, config: ConfigParser) -> None:
        """Load color scheme from config, using defaults for missing values."""
        if config.has_section("COLORS"):
            for key in self.colors:
                if config.has_option("COLORS", key):
                    self.colors[key] = config.get("COLORS", key)

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
        group: str,
        start: str,
        end: str
    ) -> List[Tuple]:
        """
        Fetch StatRep data from database.

        Args:
            group: Selected group name
            start/end: Date range filter

        Returns:
            List of tuples containing StatRep records
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                query = """
                    SELECT datetime, SRid, callsign, grid, prec, status,
                           commpwr, pubwtr, med, ota, trav, net,
                           fuel, food, crime, civil, political, comments
                    FROM StatRep_Data
                    WHERE groupname = ?
                      AND datetime BETWEEN ? AND ?
                """

                params = [group, start, end]
                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_bulletin_data(self, group: str) -> List[Tuple]:
        """
        Fetch bulletin data from database.

        Args:
            group: Selected group name

        Returns:
            List of tuples containing bulletin records
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT datetime, idnum, callsign, message FROM bulletins_Data WHERE groupid = ?",
                    [group]
                )
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def get_latest_marquee(self, group: str) -> Optional[Tuple]:
        """
        Fetch the latest marquee message for a group.

        Args:
            group: Selected group name

        Returns:
            Tuple containing marquee data or None
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT idnum, callsign, groupname, date, color, message FROM marquees_data WHERE groupname = ? ORDER BY date DESC LIMIT 1",
                    [group]
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

        # Initialize datareader for parsing DIRECTED.TXT
        self.datareader_config = datareader.Config()
        self.datareader_parser = datareader.MessageParser(self.datareader_config)

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

        # Set window icon
        icon_path = Path(ICON_FILE)
        if icon_path.exists():
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(str(icon_path)), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.setWindowIcon(icon)

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

        # Row stretches: header doesn't stretch, others do
        self.main_layout.setRowStretch(0, 0)  # Header
        self.main_layout.setRowStretch(1, 1)  # StatRep table (50%)
        self.main_layout.setRowStretch(2, 1)  # Live feed (50%)
        self.main_layout.setRowStretch(3, 0)  # Map row 1 / Filter (fixed heights)
        self.main_layout.setRowStretch(4, 0)  # Map row 2 / Bulletin (fixed heights)

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
            ("js8email", "JS8EMAIL", self._on_js8email),
            ("js8sms", "JS8SMS", self._on_js8sms),
            ("statrep", "STATREP", self._on_statrep),
            ("net_check_in", "NET CHECK IN", self._on_net_check_in),
            ("member_list", "MEMBER LIST", self._on_member_list),
            None,  # Separator
            ("statrep_ack", "STATREP ACK", self._on_statrep_ack),
            ("net_roster", "NET MANAGER", self._on_net_roster),
            ("new_marquee", "NEW MARQUEE", self._on_new_marquee),
            ("flash_bulletin", "FLASH BULLETIN", self._on_flash_bulletin),
            None,  # Separator
            ("filter", "DISPLAY FILTER", self._on_filter),
            ("groups", "MANAGE GROUPS", self._on_groups),
            ("settings", "SETTINGS", self._on_settings),
            ("colors", "COLORS", self._on_colors),
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
        self.main_layout.addWidget(self.header_widget, 0, 0, 1, 5)

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
        self.main_layout.addWidget(self.statrep_table, 1, 0, 1, 5)

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
        self.main_layout.addWidget(self.label_filter, 3, 3, 1, 2)

    def _setup_map_widget(self) -> None:
        """Create the map widget using QWebEngineView."""
        self.map_widget = QWebEngineView(self.central_widget)
        self.map_widget.setObjectName("mapWidget")
        self.map_widget.setMinimumWidth(MAP_WIDTH)
        self.map_widget.setFixedHeight(MAP_HEIGHT)

        # Set custom page to handle statrep links
        custom_page = CustomWebEnginePage(self)
        self.map_widget.setPage(custom_page)

        # Add to layout (row 3-4, columns 0-2, spanning 2 rows)
        self.main_layout.addWidget(self.map_widget, 3, 0, 2, 3)

        # Set column stretches for proportional resizing
        self.main_layout.setColumnStretch(0, 2)
        self.main_layout.setColumnStretch(1, 2)
        self.main_layout.setColumnStretch(2, 2)
        self.main_layout.setColumnStretch(3, 3)
        self.main_layout.setColumnStretch(4, 3)

    def _setup_live_feed(self) -> None:
        """Create the live feed container with title and text area."""
        # Container widget
        self.feed_container = QtWidgets.QWidget(self.central_widget)
        self.feed_layout = QtWidgets.QVBoxLayout(self.feed_container)
        self.feed_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_layout.setSpacing(0)

        # Feed title label
        self.label_feed_title = QtWidgets.QLabel(self.feed_container)
        self.label_feed_title.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
        self.label_feed_title.setStyleSheet(
            f"color: {self.config.get_color('program_foreground')};"
        )
        self.label_feed_title.setText(" JS8Call Live Data Feed")
        self.feed_layout.addWidget(self.label_feed_title)

        # Feed text area
        self.feed_text = QtWidgets.QPlainTextEdit(self.feed_container)
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

        self.feed_layout.addWidget(self.feed_text)

        # Add to layout (row 2, full width)
        self.main_layout.addWidget(self.feed_container, 2, 0, 1, 5)

    def _load_live_feed(self) -> None:
        """Load DIRECTED.TXT content into the live feed (reversed order)."""
        directed_path = self.config.directed_config.get('path', '')
        if not directed_path:
            self.feed_text.setPlainText("No DIRECTED.TXT path configured")
            return

        # Build full path to DIRECTED.TXT
        full_path = os.path.join(directed_path, "DIRECTED.TXT")

        try:
            with open(full_path, 'r') as f:
                lines = f.readlines()
            # Reverse the lines so newest is at top
            reversed_text = ''.join(reversed(lines))
            self.feed_text.setPlainText(reversed_text)
        except FileNotFoundError:
            self.feed_text.setPlainText(f"File not found: {full_path}")
        except Exception as e:
            self.feed_text.setPlainText(f"Error reading feed: {e}")

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
            "Date Time UTC", "ID", "Callsign", "Bulletin"
        ])

        # Configure header behavior
        header = self.bulletin_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.bulletin_table.verticalHeader().setVisible(False)
        self.bulletin_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.bulletin_table.setFixedHeight(MAP_HEIGHT - FILTER_HEIGHT)

        # Add to layout (row 4, columns 3-4)
        self.main_layout.addWidget(self.bulletin_table, 4, 3, 1, 2)

    def _load_bulletin_data(self) -> None:
        """Load bulletin data from database into the table."""
        group = self.db.get_active_group()
        data = self.db.get_bulletin_data(group)

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
        group = self.db.get_active_group()

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
        """Run datareader and refresh StatRep, live feed, and bulletin data."""
        # Parse new messages from DIRECTED.TXT (only processes new lines)
        if self.datareader_parser.copy_directed():
            new_count = self.datareader_parser.parse()
            if new_count > 0:
                print(f"Processed {new_count} new lines")

        # Reload data from database
        self._load_statrep_data()
        self._load_live_feed()
        self._load_bulletin_data()

        # Save map position before refresh, then reload map
        self._save_map_position(callback=self._load_map)

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
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormJS8Mail()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_js8sms(self) -> None:
        """Open JS8 SMS window."""
        dialog = QtWidgets.QDialog()
        dialog.ui = Ui_FormJS8SMS()
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_statrep(self) -> None:
        """Open StatRep window."""
        print("STATREP clicked - window not yet implemented")

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
        print("NEW MARQUEE clicked - window not yet implemented")

    def _on_flash_bulletin(self) -> None:
        """Open Flash Bulletin window."""
        print("FLASH BULLETIN clicked - window not yet implemented")

    def _on_filter(self) -> None:
        """Open Display Filter window."""
        dialog = FilterDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Reload config and refresh data
            self.config = ConfigManager()
            self._setup_filter_labels()
            self._load_statrep_data()
            # Save map position before refresh, then reload map
            self._save_map_position(callback=self._load_map)

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
