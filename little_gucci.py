# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
CommStat v2.5.1 - Rebuilt with best practices

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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from configparser import ConfigParser
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Set

import folium
import maidenhead as mh

# Optional: PyEnchant for smart title case (acronym detection)
try:
    import enchant
    ENCHANT_AVAILABLE = True
except ImportError:
    ENCHANT_AVAILABLE = False

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
from message import Ui_FormMessage
from alert import Ui_FormAlert
from statrep import StatRepDialog
from connector_manager import ConnectorManager
from js8_tcp_client import TCPConnectionPool
from js8_connectors import JS8ConnectorsDialog


# =============================================================================
# Constants
# =============================================================================

VERSION = "2.5.1"
WINDOW_TITLE = f"CommStat (v{VERSION}) by N0DDK"
WINDOW_SIZE = (1440, 832)
CONFIG_FILE = "config.ini"
ICON_FILE = "radiation-32.png"
DATABASE_FILE = "traffic.db3"

# Default filter date range
DEFAULT_FILTER_START = "2023-01-01"

# Group settings
MAX_GROUP_NAME_LENGTH = 15

# Map and layout dimensions
MAP_WIDTH = 604
MAP_HEIGHT = 340
SLIDESHOW_INTERVAL = 1  # Minutes between image changes

# Backbone server for remote announcements and slideshow images
# This allows the developer to push messages/images to all CommStat users
_BACKBONE = base64.b64decode("aHR0cHM6Ly9qczhjYWxsLWltcHJvdmVkLmNvbQ==").decode()
_PING = _BACKBONE + "/heartbeat.php"

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


def expand_abbreviations(text: str, abbreviations: Dict[str, str] = None) -> str:
    """Expand common JS8Call abbreviations to full words.

    Args:
        text: Input text with possible abbreviations.
        abbreviations: Dictionary mapping abbreviations to expansions.
                      If None, no expansion is performed.

    Returns:
        Text with abbreviations expanded.
    """
    if not text or not abbreviations:
        return text

    words = text.split()
    result = []

    for word in words:
        # Preserve punctuation
        prefix = ""
        suffix = ""
        clean_word = word

        # Extract leading punctuation
        while clean_word and not clean_word[0].isalnum():
            prefix += clean_word[0]
            clean_word = clean_word[1:]

        # Extract trailing punctuation
        while clean_word and not clean_word[-1].isalnum():
            suffix = clean_word[-1] + suffix
            clean_word = clean_word[:-1]

        # Check for abbreviation (case-insensitive)
        upper_word = clean_word.upper()
        if upper_word in abbreviations:
            expanded = abbreviations[upper_word]
            result.append(prefix + expanded + suffix)
        else:
            result.append(word)

    return ' '.join(result)


def smart_title_case(text: str, abbreviations: Dict[str, str] = None, apply_normalization: bool = True) -> str:
    """Convert text to smart title case with acronym detection.

    First expands JS8Call abbreviations, then applies title case rules:
    - Words 1-2 chars stay lowercase (e.g., "a", "of", "to"), EXCEPT at sentence start
    - Dictionary words get title case
    - Non-dictionary words become ALL CAPS (treated as acronyms)
    - First word of each sentence is always capitalized
    - All-caps words from abbreviation expansion are preserved (e.g., SC, NY, TX)

    Args:
        text: Input text to format.
        abbreviations: Dictionary mapping abbreviations to expansions.
        apply_normalization: If False, returns text unchanged. Defaults to True.

    Returns:
        Formatted text with abbreviations expanded and smart title case (if enabled).
    """
    # If normalization is disabled, return text as-is
    if not apply_normalization:
        return text

    # First expand abbreviations
    text = expand_abbreviations(text, abbreviations)
    if not text:
        return text

    # Identify words that are all-caps (2+ letters) after abbreviation expansion
    # These should be preserved as-is (e.g., state abbreviations like SC, NY)
    preserved_caps = set()
    for word in text.split():
        clean = ''.join(c for c in word if c.isalnum())
        if len(clean) >= 2 and clean.isupper():
            preserved_caps.add(clean.upper())

    # Initialize dictionary if available
    dictionary = None
    if ENCHANT_AVAILABLE:
        try:
            dictionary = enchant.Dict("en_US")
        except Exception:
            pass

    words = text.lower().split()
    result = []

    for i, word in enumerate(words):
        # Strip punctuation for checking, preserve for output
        clean_word = ''.join(c for c in word if c.isalnum())

        # Check if this word should be preserved as all-caps
        if clean_word.upper() in preserved_caps:
            # Reconstruct word with original punctuation but uppercase letters
            rebuilt = ""
            for c in word:
                rebuilt += c.upper() if c.isalnum() else c
            result.append(rebuilt)
            continue

        # Check if this is the start of a sentence
        is_sentence_start = (i == 0)  # First word
        if i > 0:
            # Check if previous word ends with sentence-ending punctuation
            prev_word = result[-1]
            if prev_word.rstrip().endswith(('.', '!', '?')):
                is_sentence_start = True

        if is_sentence_start:
            # Always capitalize first letter of sentence, even if 1-2 chars
            if dictionary and not dictionary.check(clean_word) and not dictionary.check(clean_word.capitalize()):
                # Not in dictionary - treat as acronym
                result.append(word.upper())
            else:
                # Regular word or short word at sentence start - capitalize
                result.append(word.capitalize())
        elif len(clean_word) <= 2:
            # Short words stay lowercase (mid-sentence)
            result.append(word)
        elif dictionary and not dictionary.check(clean_word) and not dictionary.check(clean_word.capitalize()):
            # Not in dictionary - treat as acronym
            result.append(word.upper())
        else:
            # Regular word - title case
            result.append(word.capitalize())

    return ' '.join(result)


# StatRep table column headers
STATREP_HEADERS = [
    "", "Date Time", "Freq", "From", "To", "Grid", "Scope", "Map Pin",
    "Powr", "H2O", "Med", "Comm", "Trvl", "Inet", "Fuel", "Food",
    "Crime", "Civil", "Pol", "Remarks"
]

# Default color scheme for UI elements
# These colors can be customized via config.ini in the future
DEFAULT_COLORS: Dict[str, str] = {
    # Main window colors
    'program_background': '#A52A2A',   # Brown/maroon
    'program_foreground': '#FFFFFF',
    'menu_background': '#3050CC',       # Blue
    'menu_foreground': '#FFFFFF',
    'title_bar_background': '#F07800',  # Orange
    'title_bar_foreground': '#FFFFFF',
    # News feed marquee colors
    'newsfeed_background': '#242424',   # Dark gray
    'newsfeed_foreground': '#00FF00',   # Green text
    # Clock display colors
    'time_background': '#282864',       # Navy blue
    'time_foreground': '#88CCFF',       # Light blue
    # StatRep condition indicator colors (traffic light system)
    'condition_green': '#108010',       # Good/normal status
    'condition_yellow': '#FFFF77',      # Caution/degraded status
    'condition_red': '#BB0000',         # Critical/emergency status
    'condition_gray': '#808080',        # Unknown/no data
    # Data table colors
    'data_background': '#FFF0D4',
    'data_foreground': '#000000',
    # Live feed display colors
    'feed_background': '#000000',
    'feed_foreground': '#FFFFFF',
}

# Default RSS news feeds
DEFAULT_RSS_FEEDS: Dict[str, str] = {
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "AP News": "https://feedx.net/rss/ap.xml",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "CNN Top": "http://rss.cnn.com/rss/cnn_topstories.rss",
    "Fox News": "https://moxie.foxnews.com/google-publisher/latest.xml",
    "NPR News": "https://feeds.npr.org/1001/rss.xml",
}


# =============================================================================
# Helper Functions
# =============================================================================

def create_insecure_ssl_context():
    """Create SSL context that bypasses certificate verification.

    Some ham radio sites and RSS feeds have certificate issues,
    so we need to disable verification for those requests.
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


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
        default_feed = list(DEFAULT_RSS_FEEDS.keys())[0]
        if not self.config_path.exists():
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': False, 'show_every_group': False, 'hide_map': False, 'show_alerts': False, 'selected_rss_feed': default_feed}
            return

        config = ConfigParser()
        config.read(self.config_path)

        if config.has_section("DIRECTEDCONFIG"):
            self.directed_config = {
                'hide_heartbeat': config.getboolean("DIRECTEDCONFIG", "hide_heartbeat", fallback=False),
                'show_all_groups': config.getboolean("DIRECTEDCONFIG", "show_all_groups", fallback=False),
                'show_every_group': config.getboolean("DIRECTEDCONFIG", "show_every_group", fallback=False),
                'hide_map': config.getboolean("DIRECTEDCONFIG", "hide_map", fallback=False),
                'show_alerts': config.getboolean("DIRECTEDCONFIG", "show_alerts", fallback=False),
                'selected_rss_feed': config.get("DIRECTEDCONFIG", "selected_rss_feed", fallback=default_feed),
            }
        else:
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': False, 'show_every_group': False, 'hide_map': False, 'show_alerts': False, 'selected_rss_feed': default_feed}

    def get_color(self, key: str) -> str:
        """Get a color value by key."""
        return self.colors.get(key, '#FFFFFF')

    def _save_setting(self, key: str, value) -> None:
        """Save a setting to both memory and config file."""
        self.directed_config[key] = value
        config = ConfigParser()
        config.read(self.config_path)
        if not config.has_section("DIRECTEDCONFIG"):
            config.add_section("DIRECTEDCONFIG")
        config.set("DIRECTEDCONFIG", key, str(value))
        with open(self.config_path, 'w') as f:
            config.write(f)

    def get_hide_heartbeat(self) -> bool:
        return self.directed_config.get('hide_heartbeat', False)

    def set_hide_heartbeat(self, value: bool) -> None:
        self._save_setting('hide_heartbeat', value)

    def get_show_all_groups(self) -> bool:
        return self.directed_config.get('show_all_groups', False)

    def set_show_all_groups(self, value: bool) -> None:
        self._save_setting('show_all_groups', value)

    def get_hide_map(self) -> bool:
        return self.directed_config.get('hide_map', False)

    def set_hide_map(self, value: bool) -> None:
        self._save_setting('hide_map', value)

    def get_show_every_group(self) -> bool:
        return self.directed_config.get('show_every_group', False)

    def set_show_every_group(self, value: bool) -> None:
        self._save_setting('show_every_group', value)

    def get_show_alerts(self) -> bool:
        return self.directed_config.get('show_alerts', False)

    def set_show_alerts(self, value: bool) -> None:
        self._save_setting('show_alerts', value)

    def get_apply_text_normalization(self) -> bool:
        return self.directed_config.get('apply_text_normalization', True)

    def set_apply_text_normalization(self, value: bool) -> None:
        self._save_setting('apply_text_normalization', value)

    def get_selected_rss_feed(self) -> str:
        return self.directed_config.get('selected_rss_feed', list(DEFAULT_RSS_FEEDS.keys())[0])

    def set_selected_rss_feed(self, feed_name: str) -> None:
        self._save_setting('selected_rss_feed', feed_name)


# =============================================================================
# RSSFetcher - Fetches and parses RSS news feeds
# =============================================================================

class RSSFetcher:
    """Fetches and caches RSS news headlines."""

    def __init__(self):
        """Initialize the RSS fetcher with empty cache."""
        self._headlines: List[str] = []
        self._cache_time: Optional[datetime] = None
        self._cache_duration = timedelta(minutes=5)
        self._current_url: str = ""
        self._fetching = False

    def get_headlines(self, feed_url: str, force_refresh: bool = False) -> List[str]:
        """
        Get headlines from the specified RSS feed.

        Args:
            feed_url: URL of the RSS feed
            force_refresh: If True, bypass cache and fetch fresh data

        Returns:
            List of headline strings
        """
        # Check if we need to refresh
        now = datetime.now()
        cache_valid = (
            self._cache_time is not None
            and self._current_url == feed_url
            and (now - self._cache_time) < self._cache_duration
            and not force_refresh
        )

        if cache_valid and self._headlines:
            return self._headlines

        # Return cached data if currently fetching
        if self._fetching:
            return self._headlines

        # Fetch new data
        self._current_url = feed_url
        self._fetch_feed(feed_url)
        return self._headlines

    def _fetch_feed(self, feed_url: str) -> None:
        """Fetch and parse the RSS feed."""
        self._fetching = True
        try:
            request = urllib.request.Request(
                feed_url,
                headers={'User-Agent': 'CommStat/2.5'}
            )

            with urllib.request.urlopen(request, timeout=10, context=create_insecure_ssl_context()) as response:
                content = response.read().decode('utf-8', errors='replace')

            # Parse RSS XML
            root = ET.fromstring(content)
            headlines = []

            # Try RSS 2.0 format first (most common)
            for item in root.findall('.//item'):
                title = item.find('title')
                if title is not None and title.text:
                    headlines.append(title.text.strip())

            # Try Atom format if no RSS items found
            if not headlines:
                # Atom uses namespace
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('.//atom:entry', ns):
                    title = entry.find('atom:title', ns)
                    if title is not None and title.text:
                        headlines.append(title.text.strip())

                # Also try without namespace
                for entry in root.findall('.//entry'):
                    title = entry.find('title')
                    if title is not None and title.text:
                        headlines.append(title.text.strip())

            self._headlines = headlines[:20]  # Limit to 20 headlines
            self._cache_time = datetime.now()

        except Exception as e:
            print(f"Error fetching RSS feed: {e}")
            # Keep old headlines if fetch fails
            if not self._headlines:
                self._headlines = ["Unable to fetch news - check internet connection"]

        finally:
            self._fetching = False

    def fetch_async(self, feed_url: str, callback=None) -> None:
        """
        Fetch RSS feed in background thread.

        Args:
            feed_url: URL of the RSS feed
            callback: Optional callback function to call when done
        """
        def fetch_thread():
            self._fetch_feed(feed_url)
            if callback:
                callback()

        thread = threading.Thread(target=fetch_thread, daemon=True)
        thread.start()

    def clear_cache(self) -> None:
        """Clear the cached headlines."""
        self._headlines = []
        self._cache_time = None
        self._current_url = ""


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

    def _execute(self, operation, default=None):
        """Execute a database operation with error handling.

        Args:
            operation: Callable that takes (cursor, connection) and returns result
            default: Value to return on error

        Returns:
            Result of operation, or default on error
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                return operation(cursor, connection)
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return default

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
                        SELECT db, datetime, freq, from_callsign, groupname, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM statrep
                        WHERE {date_condition}
                    """
                    params = date_params
                else:
                    # Build group filter for multiple groups (add @ prefix for matching)
                    groups_with_at = ["@" + g for g in groups]
                    placeholders = ",".join("?" * len(groups_with_at))
                    query = f"""
                        SELECT db, datetime, freq, from_callsign, groupname, grid, prec, status,
                               commpwr, pubwtr, med, ota, trav, net,
                               fuel, food, crime, civil, political, comments
                        FROM statrep
                        WHERE groupname IN ({placeholders}) AND {date_condition}
                    """
                    params = groups_with_at + date_params

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
                    query = f"""SELECT db, datetime, freq, from_callsign, target, message
                               FROM messages
                               WHERE {date_condition}"""
                    params = date_params
                elif groups:
                    # Filter by active groups (add @ prefix for matching)
                    groups_with_at = ["@" + g for g in groups]
                    placeholders = ",".join("?" * len(groups_with_at))
                    query = f"""SELECT db, datetime, freq, from_callsign, target, message
                               FROM messages
                               WHERE target IN ({placeholders}) AND {date_condition}"""
                    params = groups_with_at + date_params
                else:
                    # No groups and not show_all - return empty
                    return []

                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as error:
            print(f"Database error: {error}")
            return []

    def init_groups_table(self) -> None:
        """Create Groups table if it doesn't exist and migrate schema if needed."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS groups (
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
        except sqlite3.Error as error:
            print(f"Database error initializing Groups table: {error}")

    def _migrate_groups_table(self, cursor, connection) -> None:
        """Add new columns to Groups table if they don't exist."""
        cursor.execute("PRAGMA table_info(groups)")
        columns = [col[1] for col in cursor.fetchall()]

        new_columns = [
            ("comment", "TEXT"),
            ("url1", "TEXT"),
            ("url2", "TEXT"),
            ("date_added", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE groups ADD COLUMN {col_name} {col_type}")
                print(f"Added column {col_name} to Groups table")

        connection.commit()

    def get_all_groups(self) -> List[str]:
        """Get all group names."""
        def op(cursor, conn):
            cursor.execute("SELECT name FROM groups ORDER BY name")
            return [row[0] for row in cursor.fetchall()]
        return self._execute(op, [])

    def get_all_groups_with_status(self) -> List[Tuple[str, bool]]:
        """Get all groups with their active status."""
        def op(cursor, conn):
            cursor.execute("SELECT name, is_active FROM groups ORDER BY name")
            return [(row[0], bool(row[1])) for row in cursor.fetchall()]
        return self._execute(op, [])

    def get_active_groups(self) -> List[str]:
        """Get list of all active group names."""
        def op(cursor, conn):
            cursor.execute("SELECT name FROM groups WHERE is_active = 1 ORDER BY name")
            return [row[0] for row in cursor.fetchall()]
        return self._execute(op, [])

    def get_active_group(self) -> str:
        """Get the first active group name (for backwards compatibility)."""
        groups = self.get_active_groups()
        return groups[0] if groups else ""

    def set_group_active(self, group_name: str, active: bool) -> bool:
        """Set a group's active status (doesn't affect other groups)."""
        def op(cursor, conn):
            cursor.execute(
                "UPDATE groups SET is_active = ? WHERE name = ?",
                (1 if active else 0, group_name.upper())
            )
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

    def set_active_group(self, group_name: str) -> bool:
        """Set a group as the only active group (deactivates others)."""
        def op(cursor, conn):
            cursor.execute("UPDATE groups SET is_active = 0")
            cursor.execute(
                "UPDATE groups SET is_active = 1 WHERE name = ?",
                (group_name.upper(),)
            )
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

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
                    "INSERT INTO groups (name, comment, url1, url2, date_added, is_active) VALUES (?, ?, ?, ?, ?, 0)",
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
        def op(cursor, conn):
            cursor.execute(
                "UPDATE groups SET comment = ?, url1 = ?, url2 = ? WHERE name = ?",
                (comment.strip(), url1.strip(), url2.strip(), group_name.upper())
            )
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

    def get_group_details(self, group_name: str) -> Optional[Dict]:
        """Get full details of a group."""
        def op(cursor, conn):
            cursor.execute(
                "SELECT name, comment, url1, url2, date_added, is_active FROM groups WHERE name = ?",
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
        return self._execute(op, None)

    def get_all_groups_details(self) -> List[Dict]:
        """Get full details of all groups, sorted by name."""
        def op(cursor, conn):
            cursor.execute(
                "SELECT name, comment, url1, url2, date_added FROM groups ORDER BY name"
            )
            return [
                {
                    "name": row[0],
                    "comment": row[1] or "",
                    "url1": row[2] or "",
                    "url2": row[3] or "",
                    "date_added": row[4] or ""
                }
                for row in cursor.fetchall()
            ]
        return self._execute(op, [])

    def remove_group(self, group_name: str) -> bool:
        """Remove a group. Returns True if successful."""
        def op(cursor, conn):
            cursor.execute("DELETE FROM groups WHERE name = ?", (group_name.upper(),))
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

    def get_group_count(self) -> int:
        """Get the number of groups."""
        def op(cursor, conn):
            cursor.execute("SELECT COUNT(*) FROM groups")
            return cursor.fetchone()[0]
        return self._execute(op, 0)

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

    def init_alerts_table(self) -> None:
        """Create alerts table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        datetime TEXT,
                        freq DOUBLE,
                        db TEXT,
                        source INTEGER,
                        from_callsign TEXT,
                        groupname TEXT,
                        color INTEGER,
                        title TEXT,
                        message TEXT
                    )
                """)
                connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing alerts table: {error}")

    def init_statrep_table(self) -> None:
        """Create statrep table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS statrep (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        datetime TEXT,
                        freq DOUBLE,
                        db INTEGER,
                        source INTEGER,
                        SRid INTEGER,
                        from_callsign TEXT,
                        groupname TEXT,
                        grid TEXT,
                        prec TEXT,
                        status TEXT,
                        commpwr TEXT,
                        pubwtr TEXT,
                        med TEXT,
                        ota TEXT,
                        trav TEXT,
                        net TEXT,
                        fuel TEXT,
                        food TEXT,
                        crime TEXT,
                        civil TEXT,
                        political TEXT,
                        comments TEXT
                    )
                """)
                connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing statrep table: {error}")
        # Migrate existing databases from TEXT to INTEGER
        self._migrate_db_column_to_integer('statrep')

    def init_messages_table(self) -> None:
        """Create messages table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        datetime TEXT,
                        freq DOUBLE,
                        db INTEGER,
                        source INTEGER,
                        SRid INTEGER,
                        from_callsign TEXT,
                        target TEXT,
                        message TEXT
                    )
                """)
                connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing messages table: {error}")
        # Migrate existing databases from TEXT to INTEGER
        self._migrate_db_column_to_integer('messages')

    def _migrate_db_column_to_integer(self, table_name: str) -> None:
        """Migrate the db column from TEXT to INTEGER for existing databases.

        SQLite doesn't support ALTER COLUMN, so we use a temp table approach:
        1. Check if db column is TEXT type
        2. Create temp table with INTEGER type
        3. Copy data with CAST
        4. Drop old table and rename temp
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()

                # Check current column type
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()

                db_column = None
                for col in columns:
                    if col[1] == 'db':  # col[1] is column name
                        db_column = col
                        break

                if db_column is None:
                    return  # No db column found, nothing to migrate

                # col[2] is the type - check if it's TEXT (case-insensitive)
                if db_column[2].upper() != 'TEXT':
                    return  # Already INTEGER or other type, no migration needed

                print(f"Migrating {table_name}.db column from TEXT to INTEGER...")

                # Get the full CREATE TABLE statement to understand table structure
                cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                result = cursor.fetchone()
                if not result:
                    return

                # Get all column names for the table
                column_names = [col[1] for col in columns]
                columns_str = ', '.join(column_names)

                # Create columns string for new table, replacing db TEXT with db INTEGER
                new_columns = []
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    if col_name == 'id':
                        new_columns.append('id INTEGER PRIMARY KEY AUTOINCREMENT')
                    elif col_name == 'db':
                        new_columns.append('db INTEGER')
                    else:
                        new_columns.append(f'{col_name} {col_type}')
                new_columns_def = ', '.join(new_columns)

                # Perform migration in a transaction
                cursor.execute("BEGIN TRANSACTION")
                try:
                    # Create temp table with new schema
                    cursor.execute(f"CREATE TABLE {table_name}_temp ({new_columns_def})")

                    # Build insert with CAST for db column
                    insert_columns = []
                    for col_name in column_names:
                        if col_name == 'db':
                            insert_columns.append('CAST(db AS INTEGER)')
                        else:
                            insert_columns.append(col_name)
                    insert_str = ', '.join(insert_columns)

                    cursor.execute(f"INSERT INTO {table_name}_temp ({columns_str}) SELECT {insert_str} FROM {table_name}")

                    # Drop old table and rename temp
                    cursor.execute(f"DROP TABLE {table_name}")
                    cursor.execute(f"ALTER TABLE {table_name}_temp RENAME TO {table_name}")

                    cursor.execute("COMMIT")
                    print(f"Successfully migrated {table_name}.db column to INTEGER")
                except sqlite3.Error as e:
                    cursor.execute("ROLLBACK")
                    raise e

        except sqlite3.Error as error:
            print(f"Database error migrating {table_name}.db column: {error}")

    def init_abbreviations_table(self) -> None:
        """Create abbreviations table if it doesn't exist and populate with defaults."""
        # Default JS8Call abbreviations
        default_abbreviations = {
            "ABT": "ABOUT", "AGN": "AGAIN", "ANI": "ANY", "BECUZ": "BECAUSE",
            "B4": "BEFORE", "BK": "BACK", "BTR": "BETTER", "BTW": "BY THE WAY",
            "C": "SEE", "CK": "CHECK", "CUD": "COULD", "CUL": "SEE YOU LATER",
            "CUZ": "BECAUSE", "DA": "THE", "DAT": "THAT", "DIS": "THIS",
            "DNT": "DON'T", "DX": "DISTANCE", "EM": "THEM", "EVE": "EVENING",
            "EVRY": "EVERY", "FB": "FINE BUSINESS", "FER": "FOR", "FRM": "FROM",
            "GD": "GOOD", "GM": "GOOD MORNING", "GN": "GOOD NIGHT", "GRT": "GREAT",
            "GUD": "GOOD", "HAV": "HAVE", "HM": "HOME", "HPE": "HOPE",
            "HR": "HERE", "HRD": "HEARD", "HV": "HAVE", "HW": "HOW",
            "INFO": "INFORMATION", "JUS": "JUST", "K": "OKAY", "KNW": "KNOW",
            "LK": "LIKE", "LKN": "LOOKING", "LTR": "LATER", "LV": "LOVE",
            "MBE": "MAYBE", "MORN": "MORNING", "MSG": "MESSAGE", "MTG": "MEETING",
            "NITE": "NIGHT", "NR": "NEAR", "NW": "NOW", "NXT": "NEXT",
            "OPR": "OPERATOR", "OT": "OUT", "OVR": "OVER", "PLS": "PLEASE",
            "PLZ": "PLEASE", "PWR": "POWER", "QRT": "CLOSING STATION",
            "QRZ": "WHO IS CALLING", "QSL": "CONFIRMED", "QSO": "CONTACT",
            "QSY": "CHANGE FREQUENCY", "QTH": "LOCATION", "QUIETR": "QUIETER",
            "R": "ARE", "RCVD": "RECEIVED", "RDY": "READY", "RIG": "RADIO",
            "SEEMD": "SEEMED", "SED": "SAID", "SHUD": "SHOULD", "SIG": "SIGNAL",
            "SM": "SOME", "SMBDY": "SOMEBODY", "SMTH": "SOMETHING",
            "SMTHN": "SOMETHING", "SN": "SOON", "SPOZ": "SUPPOSE", "SRI": "SORRY",
            "STN": "STATION", "THGHT": "THOUGHT", "THN": "THAN", "THNK": "THINK",
            "THNKS": "THANKS", "THOT": "THOUGHT", "THT": "THAT", "THX": "THANKS",
            "TK": "TAKE", "TKN": "TAKEN", "TME": "TIME", "TMRW": "TOMORROW",
            "TNX": "THANKS", "TONITE": "TONIGHT", "TU": "THANK YOU", "U": "YOU",
            "UR": "YOUR", "VY": "VERY", "W": "WITH", "WK": "WEEK",
            "WKEND": "WEEKEND", "WKN": "WEEKEND", "WL": "WILL", "WN": "WHEN",
            "WRK": "WORK", "WUD": "WOULD", "WX": "WEATHER", "XMTR": "TRANSMITTER",
            "XTRA": "EXTRA", "YALL": "Y'ALL", "YR": "YOUR", "YRS": "YOURS",
            "73": "BEST REGARDS", "88": "LOVE AND KISSES",
            # US State abbreviations (preserved as all-caps)
            "AL": "AL", "AK": "AK", "AZ": "AZ", "AR": "AR", "CA": "CA",
            "CO": "CO", "CT": "CT", "DE": "DE", "FL": "FL", "GA": "GA",
            "HI": "HI", "ID": "ID", "IL": "IL", "IN": "IN", "IA": "IA",
            "KS": "KS", "KY": "KY", "LA": "LA", "ME": "ME", "MD": "MD",
            "MA": "MA", "MI": "MI", "MN": "MN", "MS": "MS", "MO": "MO",
            "MT": "MT", "NE": "NE", "NV": "NV", "NH": "NH", "NJ": "NJ",
            "NM": "NM", "NY": "NY", "NC": "NC", "ND": "ND", "OH": "OH",
            "OK": "OK", "OR": "OR", "PA": "PA", "RI": "RI", "SC": "SC",
            "SD": "SD", "TN": "TN", "TX": "TX", "UT": "UT", "VT": "VT",
            "VA": "VA", "WA": "WA", "WV": "WV", "WI": "WI", "WY": "WY",
            # US Territories
            "DC": "DC", "PR": "PR", "VI": "VI", "GU": "GU", "AS": "AS",
        }

        try:
            with sqlite3.connect(self.db_path, timeout=10) as connection:
                cursor = connection.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS abbreviations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        abbrev TEXT UNIQUE NOT NULL,
                        expansion TEXT NOT NULL
                    )
                """)
                connection.commit()

                # Check if table is empty and populate with defaults
                cursor.execute("SELECT COUNT(*) FROM abbreviations")
                count = cursor.fetchone()[0]
                if count == 0:
                    for abbrev, expansion in default_abbreviations.items():
                        cursor.execute(
                            "INSERT OR IGNORE INTO abbreviations (abbrev, expansion) VALUES (?, ?)",
                            (abbrev.upper(), expansion)
                        )
                    connection.commit()
                    print(f"Populated abbreviations table with {len(default_abbreviations)} defaults")
                else:
                    # For existing databases, ensure state abbreviations are present
                    # Define state abbreviations separately for migration
                    state_abbreviations = {
                        "AL": "AL", "AK": "AK", "AZ": "AZ", "AR": "AR", "CA": "CA",
                        "CO": "CO", "CT": "CT", "DE": "DE", "FL": "FL", "GA": "GA",
                        "HI": "HI", "ID": "ID", "IL": "IL", "IN": "IN", "IA": "IA",
                        "KS": "KS", "KY": "KY", "LA": "LA", "ME": "ME", "MD": "MD",
                        "MA": "MA", "MI": "MI", "MN": "MN", "MS": "MS", "MO": "MO",
                        "MT": "MT", "NE": "NE", "NV": "NV", "NH": "NH", "NJ": "NJ",
                        "NM": "NM", "NY": "NY", "NC": "NC", "ND": "ND", "OH": "OH",
                        "OK": "OK", "OR": "OR", "PA": "PA", "RI": "RI", "SC": "SC",
                        "SD": "SD", "TN": "TN", "TX": "TX", "UT": "UT", "VT": "VT",
                        "VA": "VA", "WA": "WA", "WV": "WV", "WI": "WI", "WY": "WY",
                        "DC": "DC", "PR": "PR", "VI": "VI", "GU": "GU", "AS": "AS",
                    }
                    for abbrev, expansion in state_abbreviations.items():
                        cursor.execute(
                            "INSERT OR IGNORE INTO abbreviations (abbrev, expansion) VALUES (?, ?)",
                            (abbrev.upper(), expansion)
                        )
                    connection.commit()
        except sqlite3.Error as error:
            print(f"Database error initializing abbreviations table: {error}")

    def get_abbreviations(self) -> Dict[str, str]:
        """Get all abbreviations from database as a dictionary."""
        def op(cursor, conn):
            cursor.execute("SELECT abbrev, expansion FROM abbreviations ORDER BY abbrev")
            return {row[0]: row[1] for row in cursor.fetchall()}
        return self._execute(op, {})

    def add_abbreviation(self, abbrev: str, expansion: str) -> bool:
        """Add or update an abbreviation. Returns True if successful."""
        abbrev = abbrev.strip().upper()
        expansion = expansion.strip()
        if not abbrev or not expansion:
            return False
        def op(cursor, conn):
            cursor.execute(
                "INSERT OR REPLACE INTO abbreviations (abbrev, expansion) VALUES (?, ?)",
                (abbrev, expansion)
            )
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

    def remove_abbreviation(self, abbrev: str) -> bool:
        """Remove an abbreviation. Returns True if successful."""
        def op(cursor, conn):
            cursor.execute("DELETE FROM abbreviations WHERE abbrev = ?", (abbrev.upper(),))
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)

    def get_qrz_settings(self) -> Tuple[str, str, bool]:
        """Get QRZ settings from database. Returns (username, password, is_active)."""
        def op(cursor, conn):
            cursor.execute("SELECT username, password, is_active FROM qrz_settings WHERE id = 1")
            result = cursor.fetchone()
            if result:
                return (result[0] or "", result[1] or "", bool(result[2]))
            return ("", "", False)
        return self._execute(op, ("", "", False))

    def set_qrz_settings(self, username: str, password: str, is_active: bool) -> bool:
        """Save QRZ settings to database."""
        def op(cursor, conn):
            cursor.execute(
                "UPDATE qrz_settings SET username = ?, password = ?, is_active = ? WHERE id = 1",
                (username, password, 1 if is_active else 0)
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    "INSERT INTO qrz_settings (id, username, password, is_active) VALUES (1, ?, ?, ?)",
                    (username, password, 1 if is_active else 0)
                )
            conn.commit()
            return True
        return self._execute(op, False)

    def set_qrz_active(self, is_active: bool) -> bool:
        """Toggle QRZ active status."""
        def op(cursor, conn):
            cursor.execute(
                "UPDATE qrz_settings SET is_active = ? WHERE id = 1",
                (1 if is_active else 0,)
            )
            conn.commit()
            return cursor.rowcount > 0
        return self._execute(op, False)


# =============================================================================
# MainWindow - Main application window
# =============================================================================

class MainWindow(QtWidgets.QMainWindow):
    """Main application window for CommStat."""

    def __init__(self, config: ConfigManager, db: DatabaseManager, debug_mode: bool = False, demo_mode: bool = False, demo_version: int = 1, demo_duration: int = 60):
        """
        Initialize the main window.

        Args:
            config: ConfigManager instance with loaded settings
            db: DatabaseManager instance for database operations
            debug_mode: Enable debug features when True
            demo_mode: Enable demo mode with simulated disaster data
            demo_version: Demo scenario version (1, 2, 3, etc.)
            demo_duration: Demo playback duration in seconds (default 60)
        """
        super().__init__()
        self.config = config
        self.db = db
        self.debug_mode = debug_mode
        self.demo_mode = demo_mode
        self.demo_version = demo_version
        self.demo_duration = demo_duration
        self.demo_runner = None

        # Internet connectivity state
        self._internet_available = False
        self._check_internet_on_startup()

        # Initialize JS8Call connector manager and TCP connection pool
        self.connector_manager = ConnectorManager()
        self.connector_manager.init_connectors_table()
        self.tcp_pool = TCPConnectionPool(self.connector_manager, self)
        self.tcp_pool.any_message_received.connect(self._handle_tcp_message)
        self.tcp_pool.any_connection_changed.connect(self._handle_connection_changed)
        self.tcp_pool.any_status_message.connect(self._handle_status_message)
        self.tcp_pool.any_callsign_received.connect(self._handle_callsign_received)
        self.tcp_pool.any_grid_received.connect(self._handle_grid_received)

        # Store station info by rig name (persists even if connection is lost)
        self.rig_callsigns: Dict[str, str] = {}
        self.rig_grids: Dict[str, str] = {}
        self.rig_states: Dict[str, str] = {}
        self.rig_status_logged: Set[str] = set()  # Track which rigs have logged initial status

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
        if hasattr(self, 'internet_timer'):
            self.internet_timer.stop()
        if hasattr(self, 'backbone_timer'):
            self.backbone_timer.stop()

        # Disconnect all TCP connections gracefully
        if hasattr(self, 'tcp_pool'):
            print("Closing TCP connections...")
            self.tcp_pool.disconnect_all()

        # Demo mode cleanup - ask user if they want to delete demo data from traffic.db3
        if self.demo_mode:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Demo Mode",
                "Delete demo data from database before exiting?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes
            )
            if reply == QtWidgets.QMessageBox.Yes:
                from demo_mode import cleanup_demo_data_from_traffic
                cleanup_demo_data_from_traffic()
                print("Demo data deleted from traffic.db3")

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

        # Row stretches (menu bar handled by QMainWindow.setMenuBar)
        self.main_layout.setRowStretch(0, 0)  # Unused (was menu bar)
        self.main_layout.setRowStretch(1, 0)  # Header
        self.main_layout.setRowStretch(2, 1)  # StatRep table (50%)
        self.main_layout.setRowStretch(3, 1)  # Feed text (50%)
        self.main_layout.setRowStretch(4, 0)  # Map row 1 / Filter (fixed)
        self.main_layout.setRowStretch(5, 0)  # Map row 2 / Messages (fixed)

        # Setup components
        self._setup_menu()
        self._setup_header()
        self._setup_statrep_table()
        self._setup_map_widget()
        self._setup_live_feed()
        self._setup_message_table()
        self._setup_timers()

        # Populate the Groups menu with checkable items
        self._populate_groups_menu()

        # Load initial data
        self._load_statrep_data()
        self._load_map()
        self._load_live_feed()
        self._load_message_data()

        # Initial backbone check
        if self._internet_available:
            self._check_backbone()

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
            self.backbone_timer.start(60000)
        elif not self._internet_available:
            print("Internet connectivity: Still not available (will retry in 30 minutes)")

    def _setup_menu(self) -> None:
        """Create the menu bar with all actions."""
        self.menubar = QtWidgets.QMenuBar(self)
        self.menubar.setNativeMenuBar(False)  # Use Qt menu bar, not native (fixes Linux)
        self.setMenuBar(self.menubar)  # Explicitly set as main window's menu bar
        self.menubar.setVisible(True)
        # Clear corner widgets that may interfere with menu layout on Linux
        self.menubar.setCornerWidget(None, Qt.TopLeftCorner)
        self.menubar.setCornerWidget(None, Qt.TopRightCorner)
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

        # Create the main menu
        self.menu = QtWidgets.QMenu("Menu", self.menubar)
        self.menubar.addMenu(self.menu)

        # Define menu actions: (name, text, handler)
        menu_items = [
            ("statrep", "Status Report", self._on_statrep),
            ("group_alert", "Group Alert", self._on_group_alert),
            ("send_message", "Group Message", self._on_send_message),
            ("js8email", "JS8 Email", self._on_js8email),
            ("js8sms", "JS8 SMS", self._on_js8sms),
            None,  # Separator
            ("js8_connectors", "JS8 Connectors", self._on_js8_connectors),
            ("qrz_enable", "QRZ Enable", self._on_qrz_enable),
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

        # Helper to create styled menu checkboxes
        def create_menu_checkbox(menu, label, is_checked, handler):
            menu_bg = self.config.get_color('menu_background')
            menu_fg = self.config.get_color('menu_foreground')
            checkbox = QtWidgets.QCheckBox(label)
            checkbox.setChecked(is_checked)
            checkbox.setStyleSheet(f"QCheckBox {{ padding: 4px 8px; background-color: {menu_bg}; color: {menu_fg}; }}")
            checkbox.stateChanged.connect(lambda state: handler(state == Qt.Checked))
            action = QtWidgets.QWidgetAction(self)
            action.setDefaultWidget(checkbox)
            menu.addAction(action)
            return checkbox

        # DATE FILTERING section
        date_filter_label = QtWidgets.QAction("DATE FILTERING", self)
        date_filter_label.setEnabled(False)  # Disabled as a section title
        self.filter_menu.addAction(date_filter_label)

        reset_midnight = QtWidgets.QAction("Reset to Midnight", self)
        reset_midnight.triggered.connect(lambda: self._reset_filter_date(0))
        self.filter_menu.addAction(reset_midnight)

        reset_1day = QtWidgets.QAction("Reset to 1 day ago", self)
        reset_1day.triggered.connect(lambda: self._reset_filter_date(1))
        self.filter_menu.addAction(reset_1day)

        reset_1week = QtWidgets.QAction("Reset to 1 week ago", self)
        reset_1week.triggered.connect(lambda: self._reset_filter_date(7))
        self.filter_menu.addAction(reset_1week)

        reset_1month = QtWidgets.QAction("Reset to 1 month ago", self)
        reset_1month.triggered.connect(lambda: self._reset_filter_date(30))
        self.filter_menu.addAction(reset_1month)

        reset_3months = QtWidgets.QAction("Reset to 3 months ago", self)
        reset_3months.triggered.connect(lambda: self._reset_filter_date(90))
        self.filter_menu.addAction(reset_3months)

        reset_6months = QtWidgets.QAction("Reset to 6 months ago", self)
        reset_6months.triggered.connect(lambda: self._reset_filter_date(180))
        self.filter_menu.addAction(reset_6months)

        reset_1year = QtWidgets.QAction("Reset to 1 year ago", self)
        reset_1year.triggered.connect(lambda: self._reset_filter_date(365))
        self.filter_menu.addAction(reset_1year)

        custom_date_action = QtWidgets.QAction("Custom Date Range...", self)
        custom_date_action.triggered.connect(self._on_filter)
        self.filter_menu.addAction(custom_date_action)
        self.actions["filter"] = custom_date_action

        # LIVE FEED section
        self.filter_menu.addSeparator()
        live_feed_label = QtWidgets.QAction("LIVE FEED", self)
        live_feed_label.setEnabled(False)  # Disabled as a section title
        self.filter_menu.addAction(live_feed_label)

        self.hide_heartbeat_checkbox = create_menu_checkbox(
            self.filter_menu, "Hide CQ & Heartbeat",
            self.config.get_hide_heartbeat(), self._on_toggle_heartbeat)

        # STATREP & MESSAGES section
        self.filter_menu.addSeparator()
        statrep_messages_label = QtWidgets.QAction("STATUS REPORTS && MESSAGES", self)
        statrep_messages_label.setEnabled(False)  # Disabled as a section title
        self.filter_menu.addAction(statrep_messages_label)

        self.apply_text_normalization_checkbox = create_menu_checkbox(
            self.filter_menu, "Apply Text Normalization",
            self.config.get_apply_text_normalization(), self._on_toggle_text_normalization)
        self.show_all_groups_checkbox = create_menu_checkbox(
            self.filter_menu, "Show All My Groups",
            self.config.get_show_all_groups(), self._on_toggle_show_all_groups)
        self.show_every_group_checkbox = create_menu_checkbox(
            self.filter_menu, "Show Every Group",
            self.config.get_show_every_group(), self._on_toggle_show_every_group)

        # MAP OPTION section
        self.filter_menu.addSeparator()
        map_option_label = QtWidgets.QAction("MAP OPTION", self)
        map_option_label.setEnabled(False)  # Disabled as a section title
        self.filter_menu.addAction(map_option_label)

        self.hide_map_checkbox = create_menu_checkbox(
            self.filter_menu, "Hide Map",
            self.config.get_hide_map(), self._on_toggle_hide_map)
        self.show_alerts_checkbox = create_menu_checkbox(
            self.filter_menu, "Show Alerts",
            self.config.get_show_alerts(), self._on_toggle_show_alerts)

        # Create Tools dropdown menu
        self.tools_menu = QtWidgets.QMenu("Tools", self.menubar)
        self.menubar.addMenu(self.tools_menu)

        # Helper to create menu actions
        def create_action(menu, label, key, handler):
            action = QtWidgets.QAction(label, self)
            action.triggered.connect(handler)
            menu.addAction(action)
            self.actions[key] = action

        # Tools menu items
        create_action(self.tools_menu, "Band Conditions", "band_conditions", self._on_band_conditions)
        create_action(self.tools_menu, "Solar Flux", "solar_flux", self._on_solar_flux)
        create_action(self.tools_menu, "World Map", "world_map", self._on_world_map)

        # Menubar items
        create_action(self.menubar, "About", "about", self._on_about)
        create_action(self.menubar, "Exit", "exit", qApp.quit)

        # Debug menu (right of Exit, only visible in debug mode)
        if self.debug_mode:
            self.debug_features = DebugFeatures(self)
            self.debug_features.setup_debug_menu()

        # Demo mode - start after window is shown
        if self.demo_mode:
            from demo_mode import DemoRunner
            self.demo_runner = DemoRunner(self, self.demo_version, self.demo_duration)
            QTimer.singleShot(1000, self.demo_runner.start)

        # Add status bar
        self.statusbar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.statusbar)

        # Add "Rig Status:" label (no sunken effect, permanent on left)
        rig_status_header = QtWidgets.QLabel(" Rig Status: ")
        self.statusbar.addWidget(rig_status_header)

        # Dictionary to hold status widgets for each rig
        self.rig_status_widgets: Dict[str, Tuple[QtWidgets.QLabel, QtWidgets.QLabel]] = {}

    def _setup_header(self) -> None:
        """Create the header row with News Feed and Time."""
        # Header container widget with horizontal layout
        self.header_widget = QtWidgets.QWidget(self.central_widget)
        self.header_widget.setFixedHeight(38)
        self.header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        fg_color = self.config.get_color('program_foreground')
        menu_bg = self.config.get_color('menu_background')
        menu_fg = self.config.get_color('menu_foreground')
        font = QtGui.QFont("Arial", 12, QtGui.QFont.Bold)

        # Connected rigs label
        self.label_connected_prefix = QtWidgets.QLabel(self.header_widget)
        self.label_connected_prefix.setStyleSheet(f"color: {fg_color};")
        self.label_connected_prefix.setText("Connected:")
        self.label_connected_prefix.setFont(font)
        self.header_layout.addWidget(self.label_connected_prefix)

        # Connected rigs display
        self.connected_rigs_label = QtWidgets.QLabel(self.header_widget)
        self.connected_rigs_label.setStyleSheet(f"color: {fg_color};")
        self.connected_rigs_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        self.header_layout.addWidget(self.connected_rigs_label)

        # Spacer to push news feed to center
        self.header_layout.addStretch()

        # News label
        self.label_newsfeed = QtWidgets.QLabel(self.header_widget)
        self.label_newsfeed.setStyleSheet(f"color: {fg_color};")
        self.label_newsfeed.setText("News:")
        self.label_newsfeed.setFont(font)
        self.header_layout.addWidget(self.label_newsfeed)

        # RSS Feed selector dropdown
        self.feed_combo = QtWidgets.QComboBox(self.header_widget)
        self.feed_combo.setFixedSize(120, 28)
        self.feed_combo.setFont(QtGui.QFont("Arial", 10))
        self.feed_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {menu_bg};
                color: {menu_fg};
                border: 1px solid {menu_fg};
                padding: 2px 5px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        # Style the dropdown list view directly
        combo_view = QtWidgets.QListView()
        combo_view.setStyleSheet(f"""
            QListView {{
                background-color: {menu_bg};
                color: {menu_fg};
                outline: none;
            }}
            QListView::item {{
                background-color: {menu_bg};
                color: {menu_fg};
                padding: 4px;
            }}
        """)
        self.feed_combo.setView(combo_view)
        # Populate with feed names
        for feed_name in DEFAULT_RSS_FEEDS.keys():
            self.feed_combo.addItem(feed_name)
        # Set to saved selection
        saved_feed = self.config.get_selected_rss_feed()
        index = self.feed_combo.findText(saved_feed)
        if index >= 0:
            self.feed_combo.setCurrentIndex(index)
        # Connect signal
        self.feed_combo.currentTextChanged.connect(self._on_feed_changed)
        self.header_layout.addWidget(self.feed_combo)

        # News ticker (scrolling text)
        self.newsfeed_label = QtWidgets.QLabel(self.header_widget)
        self.newsfeed_label.setFixedSize(550, 32)
        self.newsfeed_label.setFont(QtGui.QFont("Arial", 12))
        self.newsfeed_label.setStyleSheet(
            f"background-color: {self.config.get_color('newsfeed_background')};"
            f"color: {self.config.get_color('newsfeed_foreground')};"
        )
        self.header_layout.addWidget(self.newsfeed_label)

        # Last 20 button - shows last 20 news headlines
        self.last20_button = QtWidgets.QPushButton("Last 20", self.header_widget)
        self.last20_button.setFixedSize(60, 28)
        self.last20_button.setFont(QtGui.QFont("Arial", 10))
        self.last20_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {menu_bg};
                color: {menu_fg};
                border: 1px solid {menu_fg};
                padding: 2px 5px;
            }}
            QPushButton:hover {{
                background-color: {menu_fg};
                color: {menu_bg};
            }}
        """)
        self.last20_button.clicked.connect(self._on_last20_clicked)
        self.header_layout.addWidget(self.last20_button)

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
        self.time_label.setFixedSize(120, 32)
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
        self.statrep_table.setColumnCount(20)
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
        header.setMinimumSectionSize(10)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(0, 10)
        header.setStretchLastSection(True)
        self.statrep_table.verticalHeader().setVisible(False)

        # Connect click handler
        self.statrep_table.itemClicked.connect(self._on_statrep_click)

        # Add to layout (row 2, spans all columns)
        self.main_layout.addWidget(self.statrep_table, 2, 0, 1, 2)

    def _setup_map_widget(self) -> None:
        """Create the map widget using QWebEngineView."""
        self.map_widget = QWebEngineView(self.central_widget)
        self.map_widget.setObjectName("mapWidget")
        self.map_widget.setFixedSize(MAP_WIDTH, MAP_HEIGHT)

        # Set custom page to handle statrep links
        custom_page = CustomWebEnginePage(self)
        self.map_widget.setPage(custom_page)

        # Add to layout (row 4, column 0)
        self.main_layout.addWidget(self.map_widget, 4, 0, 1, 1, Qt.AlignLeft | Qt.AlignTop)

        # Set column stretches: map column fixed, message column stretches
        self.main_layout.setColumnStretch(0, 0)  # Map (fixed)

        # Setup map disabled label (hidden by default)
        self._setup_map_disabled_label()

        # Apply initial hide_map and show_alerts settings
        if self.config.get_hide_map():
            self.map_widget.hide()
            if self.config.get_show_alerts():
                # Show alerts mode - don't show slideshow
                self.map_disabled_label.hide()
            else:
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

        # Setup alert display widget
        self._setup_alert_display()

    def _setup_alert_display(self) -> None:
        """Create the alert display widget shown when Show Alerts is enabled."""
        self.alert_display = QtWidgets.QWidget(self.central_widget)
        self.alert_display.setFixedSize(MAP_WIDTH, MAP_HEIGHT)

        # Track current alert index (0 = most recent)
        self.alert_index = 0

        # Use vertical layout for centering
        alert_layout = QtWidgets.QVBoxLayout(self.alert_display)
        alert_layout.setAlignment(Qt.AlignCenter)

        # Spacer at top to push content toward center
        alert_layout.addStretch(1)

        # Title label (first line)
        self.alert_title_label = QtWidgets.QLabel()
        self.alert_title_label.setAlignment(Qt.AlignCenter)
        title_font = QtGui.QFont("Arial", 24, QtGui.QFont.Bold)
        self.alert_title_label.setFont(title_font)
        alert_layout.addWidget(self.alert_title_label)

        # Message label (second line)
        self.alert_message_label = QtWidgets.QLabel()
        self.alert_message_label.setAlignment(Qt.AlignCenter)
        self.alert_message_label.setWordWrap(True)
        message_font = QtGui.QFont("Arial", 18)
        self.alert_message_label.setFont(message_font)
        alert_layout.addWidget(self.alert_message_label)

        # Spacer between message and date
        alert_layout.addStretch(1)

        # Date received label (at bottom)
        self.alert_date_label = QtWidgets.QLabel()
        self.alert_date_label.setAlignment(Qt.AlignCenter)
        date_font = QtGui.QFont("Arial", 12)
        self.alert_date_label.setFont(date_font)
        alert_layout.addWidget(self.alert_date_label)

        # Navigation buttons row
        nav_layout = QtWidgets.QHBoxLayout()
        nav_layout.setAlignment(Qt.AlignCenter)

        self.alert_prev_btn = QtWidgets.QPushButton("<")
        self.alert_prev_btn.setFixedSize(40, 30)
        self.alert_prev_btn.setStyleSheet("QPushButton { font-size: 16px; font-weight: bold; }")
        self.alert_prev_btn.clicked.connect(self._alert_show_newer)
        nav_layout.addWidget(self.alert_prev_btn)

        nav_layout.addSpacing(20)

        self.alert_next_btn = QtWidgets.QPushButton(">")
        self.alert_next_btn.setFixedSize(40, 30)
        self.alert_next_btn.setStyleSheet("QPushButton { font-size: 16px; font-weight: bold; }")
        self.alert_next_btn.clicked.connect(self._alert_show_older)
        nav_layout.addWidget(self.alert_next_btn)

        alert_layout.addLayout(nav_layout)

        # Default styling (will be updated when alert is displayed)
        self.alert_display.setStyleSheet("background-color: #333333;")
        self.alert_title_label.setStyleSheet("color: #ffffff;")
        self.alert_message_label.setStyleSheet("color: #ffffff;")
        self.alert_date_label.setStyleSheet("color: #ffffff;")

        # Add to same layout position as map
        self.main_layout.addWidget(self.alert_display, 4, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Hidden by default
        self.alert_display.hide()

        # Apply initial show_alerts setting
        if self.config.get_show_alerts():
            self._show_alert_display()

    def _show_alert_display(self) -> None:
        """Show the alert display with the current alert from database."""
        # Get total alert count and fetch alert at current index
        alert_count = self._get_alert_count()
        alert = self._get_alert_at_offset(self.alert_index)

        # Update navigation button states
        self.alert_prev_btn.setEnabled(self.alert_index > 0)
        self.alert_next_btn.setEnabled(self.alert_index < alert_count - 1)

        if alert:
            title, message, color, date_received, from_callsign = alert
            # Set colors based on alert color
            color_map = {
                1: ("#e8e800", "#000000"),  # Yellow
                2: ("#E07000", "#ffffff"),  # Orange
                3: ("#dc3545", "#ffffff"),  # Red
                4: ("#000000", "#ffffff"),  # Black
            }
            bg_color, text_color = color_map.get(color, ("#333333", "#ffffff"))

            # Format date to remove seconds (e.g., "2026-01-15 11:00:00" -> "2026-01-15 11:00")
            date_formatted = date_received[:16] if len(date_received) > 16 else date_received

            # Build date/callsign line
            date_line = f"Date Received: {date_formatted}"
            if from_callsign:
                date_line += f"   By: {from_callsign}"

            self.alert_display.setStyleSheet(f"background-color: {bg_color};")
            self.alert_title_label.setStyleSheet(f"color: {text_color};")
            self.alert_message_label.setStyleSheet(f"color: {text_color};")
            self.alert_date_label.setStyleSheet(f"color: {text_color};")
            self.alert_title_label.setText(title)
            self.alert_message_label.setText(message)
            self.alert_date_label.setText(date_line)
        else:
            # No alerts - show placeholder
            self.alert_display.setStyleSheet("background-color: #333333;")
            self.alert_title_label.setStyleSheet("color: #ffffff;")
            self.alert_message_label.setStyleSheet("color: #ffffff;")
            self.alert_date_label.setStyleSheet("color: #ffffff;")
            self.alert_title_label.setText("No Alerts")
            self.alert_message_label.setText("")
            self.alert_date_label.setText("")

        self.alert_display.show()

    def _alert_show_newer(self) -> None:
        """Show the next newer alert."""
        if self.alert_index > 0:
            self.alert_index -= 1
            self._show_alert_display()

    def _alert_show_older(self) -> None:
        """Show the next older alert."""
        alert_count = self._get_alert_count()
        if self.alert_index < alert_count - 1:
            self.alert_index += 1
            self._show_alert_display()

    def _get_alert_count(self) -> int:
        """Get the total number of alerts in the database."""
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM alerts")
                result = cursor.fetchone()
                return result[0] if result else 0
        except sqlite3.Error as e:
            print(f"Error getting alert count: {e}")
        return 0

    def _get_alert_at_offset(self, offset: int) -> Optional[Tuple[str, str, int, str, str]]:
        """Get an alert at the specified offset from most recent.

        Args:
            offset: 0 for most recent, 1 for second most recent, etc.

        Returns:
            Tuple of (title, message, color, datetime, from_callsign) or None if not found.
        """
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, message, color, datetime, from_callsign FROM alerts ORDER BY datetime DESC LIMIT 1 OFFSET ?",
                    (offset,)
                )
                result = cursor.fetchone()
                if result:
                    return (result[0], result[1], result[2], result[3], result[4] or "")
        except sqlite3.Error as e:
            print(f"Error fetching alert at offset {offset}: {e}")
        return None

    def _fetch_backbone_content(self) -> Optional[str]:
        """Fetch and extract content from backbone server.

        Returns:
            Extracted content string, or None on error.
        """
        try:
            # Get callsign (first available from rig_callsigns)
            callsign = next((cs for cs in self.rig_callsigns.values() if cs), "UNKNOWN")

            # Get db_version from controls table
            db_version = 0
            try:
                conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT db_version FROM controls WHERE id = 1")
                result = cursor.fetchone()
                if result:
                    db_version = result[0]
                conn.close()
            except sqlite3.Error:
                pass  # Use default db_version = 0 if query fails

            # Build heartbeat URL with callsign and db_version parameters
            heartbeat_url = f"{_PING}?cs={callsign}&db={db_version}"

            with urllib.request.urlopen(heartbeat_url, timeout=10) as response:
                content = response.read().decode('utf-8')

            # Extract content between <pre> tags if present
            pre_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
            if pre_match:
                content = pre_match.group(1)

            return content.strip() or None
        except Exception:
            return None

    def _parse_backbone_sections(self, content: str) -> dict:
        """Parse backbone reply content into hierarchical sections.

        Args:
            content: Raw backbone reply (already extracted from <pre> tags).

        Returns:
            Dict with keys: 'global', 'group', 'callsign'
            Each value is the raw text for that section (or None)
        """
        import re
        sections = {'global': None, 'group': None, 'callsign': None}

        # Check if content has section markers
        if '::GLOBAL::' not in content and '::GROUP::' not in content and '::CALLSIGN::' not in content:
            # Legacy format - no sections, return None for all
            return sections

        # Split by section markers and extract content
        # Pattern captures section name and everything until next section or end
        pattern = r'::(GLOBAL|GROUP|CALLSIGN)::\s*(.*?)(?=::(?:GLOBAL|GROUP|CALLSIGN)::|$)'
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)

        for section_name, section_content in matches:
            key = section_name.lower()
            if key in sections:
                sections[key] = section_content.strip()

        return sections

    def _debug(self, message: str) -> None:
        """Print debug message if debug mode is enabled."""
        if self.debug_mode:
            print(f"[Backbone] {message}")

    def _is_backbone_date_valid(self, section_text: str) -> bool:
        """Check if backbone section's date is in the future.

        Args:
            section_text: Raw section content (first line should be Date:)

        Returns:
            True if date is in the future, False otherwise.
        """
        import re
        from datetime import datetime

        lines = section_text.strip().split('\n')
        if not lines:
            return False

        # Look for Date: line (should be first line)
        # Supports: YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS
        date_line = lines[0].strip()
        self._debug(f"First line of section: '{date_line}'")
        match = re.match(
            r'Date:\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2})(?::(\d{2}))?)?',
            date_line, re.IGNORECASE
        )
        if not match:
            self._debug("Date regex did not match")
            return False

        date_str = match.group(1)
        time_str = match.group(2) or "23:59"  # Default to end of day if no time
        seconds_str = match.group(3) or "00"

        try:
            expiry = datetime.strptime(
                f"{date_str} {time_str}:{seconds_str}",
                "%Y-%m-%d %H:%M:%S"
            )
            now = datetime.now()
            is_valid = expiry > now
            self._debug(f"Date check: {expiry} > {now} = {is_valid}")
            return is_valid
        except ValueError as e:
            self._debug(f"Date parse error: {e}")
            return False

    def _matches_user_groups(self, section_text: str) -> bool:
        """Check if user has any matching active groups.

        Args:
            section_text: Raw section content.

        Returns:
            True if user has at least one matching group.
        """
        import re

        # Look for "Group List:" line
        match = re.search(r'Group List:\s*(.+)', section_text, re.IGNORECASE)
        if not match:
            return False

        target_groups = [g.strip().upper() for g in match.group(1).split(',')]
        user_groups = [g.upper() for g in self.db.get_active_groups()]

        return bool(set(target_groups) & set(user_groups))

    def _matches_user_callsign(self, section_text: str) -> bool:
        """Check if user's callsign matches any in list.

        Args:
            section_text: Raw section content.

        Returns:
            True if any connected rig's callsign is in the list.
        """
        import re

        # Look for "Callsign List:" line
        match = re.search(r'Callsign List:\s*(.+)', section_text, re.IGNORECASE)
        if not match:
            return False

        target_calls = [c.strip().upper() for c in match.group(1).split(',')]
        user_calls = [c.upper() for c in self.rig_callsigns.values() if c]

        return bool(set(target_calls) & set(user_calls))

    def _extract_section_message(self, section_text: str) -> Optional[str]:
        """Extract MESSAGE START/END block from section.

        Args:
            section_text: Raw section content.

        Returns:
            Message content or None if no message block found.
        """
        import re
        msg_match = re.search(r'MESSAGE START\s*\n(.*?)\nMESSAGE END', section_text, re.DOTALL)
        return msg_match.group(1) if msg_match else None

    def _extract_section_urls(self, section_text: str) -> List[Tuple[str, Optional[str]]]:
        """Extract and download image URLs from section.

        Args:
            section_text: Raw section content.

        Returns:
            List of (temp_image_path, click_url) tuples.
        """
        import re
        items = []
        lines = section_text.strip().split('\n')

        for line in lines:
            # Skip metadata lines
            line_lower = line.lower().strip()
            if (line_lower.startswith('date:') or
                line_lower.startswith('group list:') or
                line_lower.startswith('callsign list:') or
                line_lower in ('message start', 'message end')):
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
                self._debug(f"Failed to download {image_url}: {e}")

        return items

    def _process_backbone_section(
        self,
        section_text: str,
        section_type: str
    ) -> Optional[Tuple[str, any]]:
        """Process a single backbone reply section.

        Args:
            section_text: Raw text of the section.
            section_type: 'global', 'group', or 'callsign'.

        Returns:
            Tuple of (action, data) where:
            - action is 'message' or 'heartbeat'
            - data is message text or list of image tuples
            Returns None if section doesn't apply.
        """
        if not section_text:
            return None

        # Check date validity
        if not self._is_backbone_date_valid(section_text):
            self._debug(f"{section_type.upper()} section: date expired, skipping")
            return None

        # For group/callsign sections, check targeting
        if section_type == 'group':
            if not self._matches_user_groups(section_text):
                self._debug("GROUP section: no matching groups, skipping")
                return None
            self._debug("GROUP section: user group matched")

        elif section_type == 'callsign':
            if not self._matches_user_callsign(section_text):
                self._debug("CALLSIGN section: no matching callsign, skipping")
                return None
            self._debug("CALLSIGN section: user callsign matched")

        # Look for message block
        message = self._extract_section_message(section_text)
        if message:
            self._debug(f"{section_type.upper()} section: showing message")
            return ('message', message)

        # Look for image URLs
        urls = self._extract_section_urls(section_text)
        if urls:
            self._debug(f"{section_type.upper()} section: loaded {len(urls)} images")
            return ('heartbeat', urls)

        return None

    def _fetch_backbone_reply(self) -> List[Tuple[str, Optional[str]]]:
        """Fetch and process backbone reply with hierarchical sections.

        Backbone reply format supports three sections processed in order:
        - ::GLOBAL:: - Applies to all users
        - ::GROUP:: - Applies to users with matching active groups
        - ::CALLSIGN:: - Applies to users with matching callsign

        Each section has:
        - Date: YYYY-MM-DD [HH:MM] (if in past, skip section)
        - Group List: or Callsign List: (for targeting)
        - MESSAGE START/END block OR image URLs

        Returns empty list if showing a message or no content matched.
        """
        from datetime import datetime
        self.ping_message = None  # Reset message

        try:
            content = self._fetch_backbone_content()
            if not content:
                return []

            # Parse into sections
            sections = self._parse_backbone_sections(content)

            # Check if we have any sections (new format)
            has_sections = any(sections.values())

            if has_sections:
                # Process in priority order: GLOBAL → GROUP → CALLSIGN
                for section_type in ['global', 'group', 'callsign']:
                    section_text = sections.get(section_type)
                    if not section_text:
                        continue

                    result = self._process_backbone_section(section_text, section_type)
                    if result:
                        action, data = result
                        if action == 'message':
                            self.ping_message = data
                            return []  # No images when showing message
                        elif action == 'heartbeat':
                            return data  # List of (image_path, click_url) tuples

                # No sections matched
                self._debug("No sections matched user criteria")
                return []

            else:
                # Legacy format - process as before (single date + content)
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                if not lines:
                    return []

                # Check for expiration date
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    if expiry_date < datetime.now().date():
                        self._debug(f"Legacy format: date {expiry_date} expired")
                        return []
                    lines = lines[1:]

                # Skip Force command (legacy)
                if lines and lines[0].lower().startswith("force"):
                    lines = lines[1:]

                # Check for message
                content = '\n'.join(lines)
                msg_match = re.search(r'MESSAGE START\s*\n(.*?)\nMESSAGE END', content, re.DOTALL)
                if msg_match:
                    self.ping_message = msg_match.group(1)
                    return []

                # Extract URLs
                items = []
                for line in lines:
                    if line in ("MESSAGE START", "MESSAGE END"):
                        continue
                    urls = re.findall(r'https?://[^\s]+', line)
                    if urls:
                        image_url = urls[0]
                        click_url = urls[1] if len(urls) > 1 else None
                        try:
                            temp_path = self._download_image(image_url)
                            if temp_path:
                                items.append((temp_path, click_url))
                        except Exception as e:
                            self._debug(f"Failed to download {image_url}: {e}")

                return items

        except Exception as e:
            self._debug(f"Failed to fetch backbone reply: {e}")

        return []

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
            self._debug(f"Failed to download image {url}: {e}")
            return None

    def _load_slideshow_images(self) -> None:
        """Load images with priority: URL > my_images > images > 00-default.png."""
        self.slideshow_items = []
        self.slideshow_index = 0
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        # Priority 1: Fetch backbone reply
        remote_items = self._fetch_backbone_reply()

        if remote_items:
            # Use backbone images only
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
        """Start the image slideshow or display backbone message."""
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
        """Display the backbone message centered in the label."""
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
        # If showing a message, just keep displaying it (backbone_timer handles updates)
        if self.ping_message:
            return

        # Otherwise advance to next image
        if not self.slideshow_items:
            return

        self.slideshow_index = (self.slideshow_index + 1) % len(self.slideshow_items)
        self._show_current_image()

    def _check_backbone_content_async(self) -> None:
        """Background thread to check backbone reply for message changes.

        Handles both new hierarchical format and legacy format.
        """
        from datetime import datetime
        # Backbone check runs silently
        try:
            content = self._fetch_backbone_content()
            if not content:
                return

            # Reset fail counter on success
            self._backbone_fail_count = 0

            # Parse into sections
            sections = self._parse_backbone_sections(content)
            has_sections = any(sections.values())

            new_message = None

            if has_sections:
                # Process hierarchical format
                for section_type in ['global', 'group', 'callsign']:
                    section_text = sections.get(section_type)
                    if not section_text:
                        continue

                    # Check date validity
                    if not self._is_backbone_date_valid(section_text):
                        continue

                    # Check targeting for group/callsign sections
                    if section_type == 'group' and not self._matches_user_groups(section_text):
                        continue
                    if section_type == 'callsign' and not self._matches_user_callsign(section_text):
                        continue

                    # Extract message from this section
                    new_message = self._extract_section_message(section_text)
                    break  # Stop at first matching section

            else:
                # Legacy format
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                if not lines:
                    return

                # Check for expiration date
                first_line = lines[0]
                date_match = re.match(r'date:\s*(\d{4}-\d{2}-\d{2})', first_line, re.IGNORECASE)
                if date_match:
                    expiry_date = datetime.strptime(date_match.group(1), '%Y-%m-%d').date()
                    if expiry_date < datetime.now().date():
                        # Date has passed - clear any message
                        if self.ping_message:
                            self.ping_message = None
                            QtCore.QMetaObject.invokeMethod(
                                self, "_reload_slideshow",
                                QtCore.Qt.QueuedConnection
                            )
                        return
                    lines = lines[1:]

                # Skip Force command (legacy)
                if lines and lines[0].lower().startswith("force"):
                    lines = lines[1:]

                # Check for message
                content = '\n'.join(lines)
                msg_match = re.search(r'MESSAGE START\s*\n(.*?)\nMESSAGE END', content, re.DOTALL)
                if msg_match:
                    new_message = msg_match.group(1)

            # Update display if message changed
            if new_message != self.ping_message:
                self.ping_message = new_message
                if new_message:
                    QtCore.QMetaObject.invokeMethod(
                        self, "_display_ping_message",
                        QtCore.Qt.QueuedConnection
                    )
                else:
                    QtCore.QMetaObject.invokeMethod(
                        self, "_reload_slideshow",
                        QtCore.Qt.QueuedConnection
                    )

        except Exception as e:
            self._backbone_fail_count += 1
            self._debug(f"Failed ({self._backbone_fail_count}/{self._backbone_max_failures}): {e}")
            if self._backbone_fail_count >= self._backbone_max_failures:
                self.backbone_timer.stop()
                self._debug(f"Stopped after {self._backbone_max_failures} consecutive failures")

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
        self.message_table.setColumnCount(6)
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
            "", "Date Time", "Freq", "From", "To", "Message"
        ])

        # Configure header behavior
        header = self.message_table.horizontalHeader()
        header.setMinimumSectionSize(10)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(0, 10)
        header.setStretchLastSection(True)
        self.message_table.verticalHeader().setVisible(False)
        self.message_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.message_table.setFixedHeight(MAP_HEIGHT)

        # Add to layout (row 4, column 1)
        self.main_layout.addWidget(self.message_table, 4, 1, 1, 1)

    def _load_message_data(self) -> None:
        """Load message data from database into the table."""
        filters = self.config.filter_settings
        groups, show_all = self._get_filtered_groups()
        data = self.db.get_message_data(
            groups=groups,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', ''),
            show_all=show_all
        )

        self._populate_table(self.message_table, data)

    def _load_map(self) -> None:
        """Generate and display the folium map with StatRep pins."""
        filters = self.config.filter_settings
        groups, show_all = self._get_filtered_groups()

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
            max_zoom=8,
            control=False
        ).add_to(m)

        # Add online tile layer (OpenStreetMap) for zoom > 8, only if internet available
        if self._internet_available:
            folium.raster_layers.TileLayer(
                tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                name='OpenStreetMap',
                attr='OpenStreetMap',
                min_zoom=8,
                control=False
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
                callsign = row[4]
                srid = row[3]
                status = str(row[7])
                grid = row[5]

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
        filters = self.config.filter_settings
        groups, show_all = self._get_filtered_groups()

        # Fetch data from database
        data = self.db.get_statrep_data(
            groups=groups,
            start=filters.get('start', DEFAULT_FILTER_START),
            end=filters.get('end', ''),
            show_all=show_all
        )

        # Status color mapping for values 1-4
        status_colors = {
            "1": "condition_green",
            "2": "condition_yellow",
            "3": "condition_red",
            "4": "condition_gray"
        }
        self._populate_table(self.statrep_table, data, status_colors)

    def _on_statrep_click(self, item: QTableWidgetItem) -> None:
        """Handle click on StatRep table row."""
        row = item.row()
        sr_id = self.statrep_table.item(row, 1)  # Column 1 is the ID
        if sr_id:
            print(f"StatRep clicked: ID = {sr_id.text()}")

    def _setup_timers(self) -> None:
        """Setup timers for clock, data refresh, and news feed animation."""
        # Clock timer - updates every second
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_time)
        self.clock_timer.start(1000)
        self._update_time()  # Initial display
        self._update_connected_rigs_display()  # Initial connected rigs display

        # Internet check timer - retries every 30 minutes if offline
        self.internet_timer = QTimer(self)
        self.internet_timer.timeout.connect(self._retry_internet_check)
        if not self._internet_available:
            self.internet_timer.start(INTERNET_CHECK_INTERVAL)

        # Backbone check timer - runs every 60 seconds
        self._backbone_fail_count = 0
        self._backbone_max_failures = 20
        self.backbone_timer = QTimer(self)
        self.backbone_timer.timeout.connect(self._check_backbone)
        if self._internet_available:
            self.backbone_timer.start(60000)

        # News ticker animation timeline
        self.newsfeed_timeline = QtCore.QTimeLine()
        self.newsfeed_timeline.setCurveShape(QtCore.QTimeLine.LinearCurve)
        self.newsfeed_timeline.frameChanged.connect(self._update_newsfeed_text)
        self.newsfeed_timeline.finished.connect(self._next_headline)

        # News ticker state
        self.newsfeed_text = ""
        self.newsfeed_chars = 0
        self.rss_fetcher = RSSFetcher()
        self.headline_index = 0
        self.headlines: List[str] = []

        # RSS refresh timer - refreshes feed every 5 minutes
        self.rss_timer = QTimer(self)
        self.rss_timer.timeout.connect(self._refresh_rss_feed)
        self.rss_timer.start(300000)  # 5 minutes

        # Initial RSS fetch
        if self._internet_available:
            self._start_rss_fetch()

    def _check_backbone(self) -> None:
        """Check backbone server for content updates (runs in background thread)."""
        if not self._internet_available:
            return
        thread = threading.Thread(target=self._check_backbone_content_async, daemon=True)
        thread.start()

    def _update_time(self) -> None:
        """Update the time display with current UTC time."""
        current_time = QDateTime.currentDateTimeUtc()
        self.time_label.setText(current_time.toString("hh:mm:ss"))

    def _update_connected_rigs_display(self) -> None:
        """Update the connected rigs display with currently connected rig names."""
        # Update header label (existing functionality)
        connected = self.tcp_pool.get_connected_rig_names()
        if connected:
            text = "  ".join(f"[{name}]" for name in connected)
        else:
            text = ""
        self.connected_rigs_label.setText(text)

        # Update status bar widgets for each rig
        all_rigs = self.connector_manager.get_all_connectors()

        # Remove widgets for rigs that no longer exist
        all_rig_names = [r['rig_name'] for r in all_rigs]
        for rig_name in list(self.rig_status_widgets.keys()):
            if rig_name not in all_rig_names:
                label_rig, label_status = self.rig_status_widgets[rig_name]
                self.statusbar.removeWidget(label_rig)
                self.statusbar.removeWidget(label_status)
                label_rig.deleteLater()
                label_status.deleteLater()
                del self.rig_status_widgets[rig_name]

        # Create or update widgets for each rig
        for rig in all_rigs:
            rig_name = rig['rig_name']
            is_connected = rig_name in connected

            if rig_name not in self.rig_status_widgets:
                # Create new widgets for this rig
                # Rig name label with sunken effect
                label_rig = QtWidgets.QLabel(f" {rig_name} ")
                label_rig.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
                label_rig.setLineWidth(2)

                # Status label with sunken effect
                label_status = QtWidgets.QLabel()
                label_status.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Sunken)
                label_status.setLineWidth(2)

                # Add to status bar (on left side, not permanent)
                self.statusbar.addWidget(label_rig)
                self.statusbar.addWidget(label_status)

                # Store references
                self.rig_status_widgets[rig_name] = (label_rig, label_status)

            # Update status label
            _, label_status = self.rig_status_widgets[rig_name]
            if is_connected:
                label_status.setText(" Connected ")
                label_status.setStyleSheet("background-color: #00dd00; color: black;")
            else:
                label_status.setText(" Disconnected ")
                label_status.setStyleSheet("background-color: #dd0000; color: white;")

    def _update_newsfeed_text(self, frame: int) -> None:
        """Update news feed display for current animation frame."""
        if frame < self.newsfeed_chars:
            start = 0
        else:
            start = frame - self.newsfeed_chars
        text = self.newsfeed_text[start:frame]
        self.newsfeed_label.setText(text)

    def _next_headline(self) -> None:
        """Called when news ticker animation completes - show next headline."""
        if self.headlines:
            self.headline_index = (self.headline_index + 1) % len(self.headlines)
        self._display_current_headline()

    def _start_rss_fetch(self) -> None:
        """Start fetching RSS feed in background."""
        feed_name = self.config.get_selected_rss_feed()
        feed_url = DEFAULT_RSS_FEEDS.get(feed_name, list(DEFAULT_RSS_FEEDS.values())[0])
        self.newsfeed_label.setText("  Loading news...")
        self.rss_fetcher.fetch_async(feed_url, callback=self._on_rss_fetched)

    def _on_rss_fetched(self) -> None:
        """Called when RSS fetch completes (from background thread)."""
        # Use QTimer to safely update UI from main thread
        QTimer.singleShot(0, self._update_headlines_from_fetch)

    def _update_headlines_from_fetch(self) -> None:
        """Update headlines list and start display (called on main thread)."""
        feed_name = self.config.get_selected_rss_feed()
        feed_url = DEFAULT_RSS_FEEDS.get(feed_name, list(DEFAULT_RSS_FEEDS.values())[0])
        self.headlines = self.rss_fetcher.get_headlines(feed_url)
        self.headline_index = 0
        self._display_current_headline()

    def _refresh_rss_feed(self) -> None:
        """Refresh RSS feed periodically."""
        if self._internet_available:
            feed_name = self.config.get_selected_rss_feed()
            feed_url = DEFAULT_RSS_FEEDS.get(feed_name, list(DEFAULT_RSS_FEEDS.values())[0])
            self.rss_fetcher.fetch_async(feed_url, callback=self._on_rss_fetched)

    def _display_current_headline(self) -> None:
        """Display the current headline with scrolling animation."""
        if not self.headlines:
            self.newsfeed_label.setText("  No news available")
            return

        try:
            headline = self.headlines[self.headline_index]

            # Set green color for news headlines
            self.newsfeed_label.setStyleSheet(
                f"background-color: {self.config.get_color('newsfeed_background')};"
                f"color: {self.config.get_color('newsfeed_foreground')};"
            )

            # Build ticker text with headline
            ticker_text = f" {headline}"

            # Calculate how many characters fit in the ticker width
            fm = self.newsfeed_label.fontMetrics()
            self.newsfeed_chars = int(self.newsfeed_label.width() / fm.averageCharWidth())

            # Add padding spaces
            padding = ' ' * self.newsfeed_chars
            self.newsfeed_text = ticker_text + "      +++      " + padding

            # Setup and start animation
            text_length = len(self.newsfeed_text)
            self.newsfeed_timeline.setDuration(15000)  # 15 seconds per headline
            self.newsfeed_timeline.setFrameRange(0, text_length)
            self.newsfeed_timeline.start()
        except (IndexError, TypeError) as e:
            print(f"Error displaying headline: {e}")
            self.newsfeed_label.setText("  News feed error")

    def _on_feed_changed(self, feed_name: str) -> None:
        """Handle feed selection change."""
        self.config.set_selected_rss_feed(feed_name)
        self.rss_fetcher.clear_cache()
        self.headlines = []
        self.headline_index = 0
        self.newsfeed_timeline.stop()
        if self._internet_available:
            self._start_rss_fetch()
        else:
            self.newsfeed_label.setText("  No internet connection")

    def _on_last20_clicked(self) -> None:
        """Show dialog with last 20 news headlines."""
        headlines = self.headlines if self.headlines else ["No headlines available"]

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Last 20 News Headlines")
        dialog.setMinimumSize(600, 400)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Feed name label
        feed_name = self.feed_combo.currentText()
        feed_label = QtWidgets.QLabel(f"Feed: {feed_name}")
        feed_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
        layout.addWidget(feed_label)

        # Headlines list
        list_widget = QtWidgets.QListWidget()
        list_widget.setFont(QtGui.QFont("Arial", 11))
        list_widget.setAlternatingRowColors(True)
        for i, headline in enumerate(headlines[:20], 1):
            list_widget.addItem(f"{i}. {headline}")
        layout.addWidget(list_widget)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec_()

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

    def _on_send_message(self) -> None:
        """Open Send Message window."""
        dialog = QtWidgets.QDialog(self)
        dialog.ui = Ui_FormMessage(self.tcp_pool, self.connector_manager)
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_group_alert(self) -> None:
        """Open Group Alert window."""
        dialog = QtWidgets.QDialog(self)
        dialog.ui = Ui_FormAlert(self.tcp_pool, self.connector_manager, self._trigger_show_alerts)
        dialog.ui.setupUi(dialog)
        dialog.exec_()

    def _on_filter(self) -> None:
        """Open Display Filter window."""
        dialog = FilterDialog(self.config.filter_settings, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Update filter settings directly
            self.config.filter_settings = dialog.get_filters()
            # Refresh data with new filters
            self._refresh_all_data()

    def _reset_filter_date(self, days_ago: int) -> None:
        """Reset filter start date to specified days ago and apply."""
        from datetime import datetime, timedelta, timezone

        # Calculate new start date using UTC time
        if days_ago == 0:
            # For midnight, use current UTC date at 00:00:00
            utc_now = datetime.now(timezone.utc)
            new_start = utc_now.strftime("%Y-%m-%d") + " 00:00:00"
        else:
            # For days ago, calculate from current UTC time
            new_start = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

        # Update in-memory filter settings
        self.config.filter_settings = {
            'start': new_start,
            'end': ''  # No end date
        }

        # Refresh data with new filters
        self._refresh_all_data()

        print(f"Filter reset (UTC): start={new_start}")

    def _on_toggle_heartbeat(self, checked: bool) -> None:
        """Toggle heartbeat message filtering in live feed."""
        self.config.set_hide_heartbeat(checked)
        self._load_live_feed()

    def _on_toggle_hide_map(self, checked: bool) -> None:
        """Toggle between map and image slideshow."""
        self.config.set_hide_map(checked)
        if checked:
            self.map_widget.hide()
            # If show_alerts is enabled, show alert display instead of slideshow
            if self.config.get_show_alerts():
                self.map_disabled_label.hide()
                self._show_alert_display()
            else:
                self.alert_display.hide()
                self.map_disabled_label.show()
                self._start_slideshow()
        else:
            self._stop_slideshow()
            self.ping_message = None  # Clear any message
            self.map_disabled_label.hide()
            self.alert_display.hide()
            self.map_widget.show()
            # Uncheck show_alerts when showing map
            if self.config.get_show_alerts():
                self.config.set_show_alerts(False)
                self.show_alerts_checkbox.blockSignals(True)
                self.show_alerts_checkbox.setChecked(False)
                self.show_alerts_checkbox.blockSignals(False)

    def _on_toggle_show_alerts(self, checked: bool) -> None:
        """Toggle alert display mode."""
        self.config.set_show_alerts(checked)
        if checked:
            # Reset to show most recent alert
            self.alert_index = 0

            # Also check hide_map if not already checked
            if not self.config.get_hide_map():
                self.config.set_hide_map(True)
                self.hide_map_checkbox.blockSignals(True)
                self.hide_map_checkbox.setChecked(True)
                self.hide_map_checkbox.blockSignals(False)
                self.map_widget.hide()

            # Stop slideshow and hide slideshow label
            self._stop_slideshow()
            self.map_disabled_label.hide()

            # Show alert display
            self._show_alert_display()
        else:
            # Hide alert display
            self.alert_display.hide()
            # If hide_map is still checked, show slideshow
            if self.config.get_hide_map():
                self.map_disabled_label.show()
                self._start_slideshow()

    def _trigger_show_alerts(self) -> None:
        """Trigger Show Alerts mode when a new alert is received."""
        # Reset to show most recent alert
        self.alert_index = 0
        # Check the Show Alerts checkbox (this will trigger the handler)
        if not self.show_alerts_checkbox.isChecked():
            self.show_alerts_checkbox.setChecked(True)
        else:
            # Already checked, just refresh the display
            self._show_alert_display()

    def _get_filtered_groups(self) -> tuple:
        """Get groups list and show_all flag based on current filter settings.

        Returns:
            Tuple of (groups, show_all) where:
            - groups: List of group names to filter by
            - show_all: True if all data should be shown regardless of groups
        """
        if self.config.get_show_every_group():
            return [], True
        elif self.config.get_show_all_groups():
            return self.db.get_all_groups(), False
        else:
            return self.db.get_active_groups(), False

    def _populate_table(self, table, data, status_colors: dict = None) -> None:
        """Populate a table widget with data.

        Args:
            table: QTableWidget to populate
            data: List of row tuples
            status_colors: Optional dict mapping values to config color keys
        """
        table.setRowCount(0)
        is_message_table = (table == self.message_table)
        is_statrep_table = (table == self.statrep_table)

        for row_num, row_data in enumerate(data):
            table.insertRow(row_num)

            # Check if this row should be bold (direct message, no @ symbol)
            bold_row = False
            if is_message_table and len(row_data) > 4:
                to_value = str(row_data[4]) if row_data[4] is not None else ""
                bold_row = to_value and not to_value.startswith("@")

            for col_num, value in enumerate(row_data):
                display_value = str(value) if value is not None else ""

                # Handle SNR (db) column (first column)
                if (is_statrep_table or is_message_table) and col_num == 0:
                    display_value = ""
                    item = QTableWidgetItem(display_value)
                    try:
                        db_value = int(value) if value is not None else 0
                        item.setToolTip(f"{db_value} dB")
                        if db_value >= -5:
                            color = QColor(self.config.get_color('condition_green'))
                        elif db_value >= -16:
                            color = QColor(self.config.get_color('condition_yellow'))
                        else:
                            color = QColor(self.config.get_color('condition_red'))
                        item.setBackground(color)
                    except (ValueError, TypeError):
                        pass
                    table.setItem(row_num, col_num, item)
                    continue

                # Truncate datetime column (remove seconds) - column 1 for both tables
                if (is_message_table or is_statrep_table) and col_num == 1:
                    if len(display_value) >= 16:
                        display_value = display_value[:16]

                # Format frequency column (column 2) - convert Hz to MHz
                if (is_message_table or is_statrep_table) and col_num == 2:
                    try:
                        freq_hz = float(value) if value else 0
                        freq_mhz = freq_hz / 1000000
                        display_value = f"{freq_mhz:.3f}"  # Show as 7.110
                    except (ValueError, TypeError):
                        pass

                item = QTableWidgetItem(display_value)

                # Bold From and To columns (3 and 4) if direct message
                if bold_row and col_num in (3, 4):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

                if status_colors and value in status_colors:
                    color = QColor(self.config.get_color(status_colors[value]))
                    item.setBackground(color)
                    item.setForeground(color)

                table.setItem(row_num, col_num, item)

        # Sort by datetime column (column 1 for both statrep and message tables)
        sort_column = 1 if (is_statrep_table or is_message_table) else 0
        table.sortItems(sort_column, QtCore.Qt.DescendingOrder)

    def _refresh_all_data(self) -> None:
        """Refresh all data views (statrep, messages, and map)."""
        self._load_statrep_data()
        self._load_message_data()
        self._save_map_position(callback=self._load_map)

    def _on_toggle_show_all_groups(self, checked: bool) -> None:
        """Toggle showing all groups data regardless of active groups."""
        self.config.set_show_all_groups(checked)
        self._refresh_all_data()

    def _on_toggle_show_every_group(self, checked: bool) -> None:
        """Toggle showing every group's data (no filtering at all)."""
        self.config.set_show_every_group(checked)

        # When "Show Every Group" is checked, also check "Show All My Groups"
        if checked:
            self.show_all_groups_checkbox.setChecked(True)
            self.config.set_show_all_groups(True)

        self._refresh_all_data()

    def _on_toggle_text_normalization(self, checked: bool) -> None:
        """Toggle text normalization (abbreviation expansion and smart title case)."""
        self.config.set_apply_text_normalization(checked)
        self._refresh_all_data()

    def _on_manage_groups(self) -> None:
        """Open Manage Groups window."""
        dialog = GroupsDialog(self.db, self)
        dialog.exec_()
        self._populate_groups_menu()
        self._refresh_all_data()

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

            # Helper to create URL table item
            def create_url_item(url):
                if url:
                    item = QtWidgets.QTableWidgetItem("Link" if len(url) > 30 else url)
                    item.setToolTip(url)
                    item.setForeground(QtGui.QColor("#0066CC"))
                else:
                    item = QtWidgets.QTableWidgetItem("")
                return item

            table.setItem(row, 2, create_url_item(group["url1"]))
            table.setItem(row, 3, create_url_item(group["url2"]))

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
        # Remove existing group actions (keep Manage Groups, Show Groups, separator, and title)
        actions = self.groups_menu.actions()
        for action in actions[4:]:  # Skip Manage Groups, Show Groups, separator, and title
            self.groups_menu.removeAction(action)

        # Add section title if not already present
        if len(self.groups_menu.actions()) == 3:
            title_action = QtWidgets.QAction("ACTIVE GROUPS", self)
            title_action.setEnabled(False)
            self.groups_menu.addAction(title_action)

        # Add groups alphabetically with checkboxes (menu stays open when clicked)
        menu_bg = self.config.get_color('menu_background')
        menu_fg = self.config.get_color('menu_foreground')
        checkbox_style = f"QCheckBox {{ padding: 4px 8px; background-color: {menu_bg}; color: {menu_fg}; }}"
        groups = self.db.get_all_groups_with_status()
        for name, is_active in groups:  # Already sorted by name from DB
            checkbox = QtWidgets.QCheckBox(name)
            checkbox.setChecked(is_active)
            checkbox.setStyleSheet(checkbox_style)
            checkbox.stateChanged.connect(lambda state, n=name: self._toggle_group(n, state == Qt.Checked))
            widget_action = QtWidgets.QWidgetAction(self)
            widget_action.setDefaultWidget(checkbox)
            self.groups_menu.addAction(widget_action)

    def _toggle_group(self, group_name: str, active: bool) -> None:
        """Toggle a group's active status."""
        self.db.set_group_active(group_name, active)
        self._refresh_all_data()

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
        if not is_connected:
            # For disconnects, add the message here
            from datetime import datetime, timezone
            utc_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d   %H:%M:%S")
            status_line = f"{utc_str}\t[{rig_name}] Disconnected"
            self.feed_messages.insert(0, status_line)
            self._update_feed_display()
            # Clear status logged flag so it will log again on reconnect
            self.rig_status_logged.discard(rig_name)
        self._update_connected_rigs_display()

    def _handle_callsign_received(self, rig_name: str, callsign: str) -> None:
        """
        Handle callsign received from JS8Call.

        Args:
            rig_name: Name of the rig.
            callsign: Callsign configured in JS8Call.
        """
        if callsign:
            self.rig_callsigns[rig_name] = callsign
            # Callsign is printed later after frequency is received

    def get_callsign_for_rig(self, rig_name: str) -> str:
        """
        Get cached callsign for a rig.

        Args:
            rig_name: Name of the rig.

        Returns:
            Callsign string or empty string if not known.
        """
        return self.rig_callsigns.get(rig_name, "")

    def _handle_grid_received(self, rig_name: str, grid: str) -> None:
        """
        Handle grid received from JS8Call.

        Prints combined rig status line with all collected info.

        Args:
            rig_name: Name of the rig.
            grid: Maidenhead grid square from JS8Call.
        """
        from statrep import get_state_from_connector

        if grid:
            self.rig_grids[rig_name] = grid

            # Get state from connector table
            state = get_state_from_connector(self.connector_manager, rig_name)
            if state:
                self.rig_states[rig_name] = state

            # Get cached values from the TCP client
            client = self.tcp_pool.clients.get(rig_name)
            if client:
                # Only log the status message once per connection
                if rig_name not in self.rig_status_logged:
                    speed_name = client.speed_name or "UNKNOWN"
                    callsign = client.callsign or "UNKNOWN"
                    frequency = client.frequency

                    # Format: [IC-7300] Running in TURBO mode, N0DDK, EM83CV, GA on 7.110
                    status_line = f"[{rig_name}] Running in {speed_name} mode, {callsign}, {grid}, {state or 'XX'} on {frequency:.3f}"
                    print(status_line)
                    self._handle_status_message(rig_name, status_line)
                    self.rig_status_logged.add(rig_name)

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

            # Convert UTC milliseconds to datetime strings
            utc_dt = datetime.fromtimestamp(utc_ms / 1000, tz=timezone.utc)
            utc_db = utc_dt.strftime("%Y-%m-%d %H:%M:%S")  # Single space for database
            utc_display = utc_dt.strftime("%Y-%m-%d   %H:%M:%S")  # 3 spaces for feed display

            # Format feed line to match DIRECTED.TXT format:
            # DATETIME    FREQ_MHZ    OFFSET    SNR    CALLSIGN: MESSAGE
            # FREQ from JS8Call is dial + offset, so subtract offset to get dial frequency
            dial_freq_mhz = (freq - offset) / 1000000 if freq else 0
            feed_line = f"{utc_display}\t{dial_freq_mhz:.3f}\t{offset}\t{snr:+03d}\t{from_call}: {value}"

            # Add to feed buffer (newest first)
            self._add_to_feed(feed_line, rig_name)

            print(f"[{rig_name}] RX.DIRECTED: {from_call} -> {to_call}: {value}")

            # Process the message for database insertion
            # Use dial frequency (freq - offset) for database storage
            dial_freq = freq - offset if freq else 0
            data_type = self._process_directed_message(
                rig_name, value, from_call, to_call, grid, dial_freq, snr, utc_db
            )

            # Refresh only the relevant UI component
            if data_type == "statrep":
                self._load_statrep_data()
                self._save_map_position(callback=self._load_map)
            elif data_type == "message":
                self._load_message_data()
            elif data_type == "checkin":
                self._save_map_position(callback=self._load_map)
            elif data_type == "alert":
                self._trigger_show_alerts()

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

        # Handle RX.CALL_SELECTED response (debug feature)
        elif msg_type == "RX.CALL_SELECTED":
            if hasattr(self, 'debug_features'):
                self.debug_features.handle_call_selected_response(rig_name, message)

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

        This method parses incoming JS8Call messages and stores them in the database.
        Messages can be StatReps, bulletins, check-ins, or standard messages.

        Two detection methods are used:
        1. Marker-based: Messages with special markers like {&%}, {^%}, {~%}, {F%}
        2. Pattern-based: Messages matching expected formats without markers

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
            Message type string ("statrep", "message", "checkin") or empty string.
        """
        import re
        import maidenhead as mh

        # CommStat message type markers (legacy format compatibility)
        # These markers appear at the END of the message data
        MSG_BULLETIN = "{^%}"          # Group bulletin/message
        MSG_STATREP = "{&%}"           # Status report
        MSG_FORWARDED_STATREP = "{F%}" # Forwarded status report (relayed)
        MSG_ALERT = "{%%}"             # Group alert

        # Precedence levels indicate the geographic scope of a status report
        PRECEDENCE_MAP = {
            "1": "My Location",
            "2": "My Community",
            "3": "My County",
            "4": "My Region",
            "5": "Other Location"
        }

        # Load abbreviations from database for text expansion
        abbreviations = self.db.get_abbreviations()

        # Extract group from to_call (keep @ symbol, e.g., "@MAGNET")
        group = ""
        if to_call.startswith("@"):
            group = to_call

        # Extract callsign (remove suffix like /P)
        callsign = from_call.split("/")[0] if from_call else ""

        try:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()

            # Determine message type and process
            # Old CommStat format has marker at END: ,DATA,FIELDS,{MARKER}
            # Extract content BEFORE the marker, strip leading comma

            if MSG_ALERT in value:
                # Parse alert: LRT ,COLOR,TITLE,MESSAGE,{%%}
                match = re.search(r'LRT\s*,(.+?)\{\%\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 3:
                        # Only save alerts for active groups
                        active_groups = self.db.get_active_groups()
                        group_name = group.lstrip('@').upper() if group else ""
                        if group_name not in [g.upper() for g in active_groups]:
                            conn.close()
                            return ""

                        try:
                            color = int(fields[0].strip())
                        except ValueError:
                            color = 1  # Default to yellow
                        title = fields[1].strip()
                        # Apply smart title case to message (acronym detection)
                        message_text = smart_title_case(",".join(fields[2:]).strip(), abbreviations, self.config.get_apply_text_normalization())

                        cursor.execute(
                            "INSERT INTO alerts "
                            "(datetime, freq, db, source, from_callsign, groupname, color, title, message) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, freq, snr, 1, callsign, group, color, title, message_text)
                        )
                        conn.commit()
                        print(f"\033[91m[{rig_name}] Added Alert from: {callsign} - {title}\033[0m")
                        conn.close()
                        return "alert"

            elif MSG_BULLETIN in value:
                # Parse message: ,ID,MESSAGE,{^%}
                match = re.search(r',(.+?)\{\^\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 2:
                        id_num = fields[0].strip()
                        # Apply smart title case to message (acronym detection)
                        message_text = smart_title_case(",".join(fields[1:]).strip(), abbreviations, self.config.get_apply_text_normalization())

                        cursor.execute(
                            "INSERT OR REPLACE INTO messages "
                            "(datetime, freq, db, source, SRid, from_callsign, target, message) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, freq, snr, 1, id_num, callsign, group, message_text)
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
                        # Apply smart title case to comments (acronym detection)
                        comments = smart_title_case(fields[4].strip(), abbreviations, self.config.get_apply_text_normalization()) if len(fields) > 4 else ""
                        orig_call = fields[5].strip() if len(fields) > 5 else callsign

                        # Expand compressed "+" to all green (111111111111)
                        if srcode == "+":
                            srcode = "111111111111"

                        prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                        if len(srcode) >= 12:
                            sr_fields = list(srcode)
                            # Extract date from datetime string (format: "YYYY-MM-DD   HH:MM:SS")
                            date_only = utc.split()[0] if utc else ""
                            cursor.execute(
                                "INSERT OR IGNORE INTO statrep "
                                "(datetime, date, freq, db, source, SRid, from_callsign, groupname, grid, prec, status, commpwr, pubwtr, "
                                "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (utc, date_only, freq, snr, 1, srid, orig_call, group, curgrid, prec,
                                 sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                                 sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                                 sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                                 comments)
                            )
                            conn.commit()
                            print(f"\033[92m[{rig_name}] Added Forwarded StatRep from: {orig_call} ID: {srid}\033[0m")
                            conn.close()
                            return "statrep"

            elif MSG_STATREP in value:
                # Parse statrep: ,GRID,PREC,SRID,SRCODE,COMMENTS,{&%}
                # GRID: 4-6 char Maidenhead locator (e.g., EM15 or EM15ab)
                # PREC: Precedence 1-5 (scope of report)
                # SRID: Unique StatRep ID number
                # SRCODE: 12-digit status code or "+" shorthand for all green
                match = re.search(r',(.+?)\{&\%\}', value)
                if match:
                    fields = match.group(1).split(",")
                    if len(fields) >= 4:
                        curgrid = fields[0].strip()
                        prec1 = fields[1].strip()
                        srid = fields[2].strip()
                        srcode = fields[3].strip()
                        # Apply smart title case to comments (acronym detection)
                        comments = smart_title_case(fields[4].strip(), abbreviations, self.config.get_apply_text_normalization()) if len(fields) > 4 else ""

                        # Expand compressed "+" shorthand to all green status
                        # "+" means all 12 indicators are at level 1 (green/good)
                        if srcode == "+":
                            srcode = "111111111111"

                        prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                        # StatRep code is 12 digits, each representing a condition:
                        # [0]=status, [1]=commpwr, [2]=pubwtr, [3]=med, [4]=ota, [5]=trav
                        # [6]=net, [7]=fuel, [8]=food, [9]=crime, [10]=civil, [11]=political
                        # Values: 1=Green, 2=Yellow, 3=Red, 4=Gray/Unknown
                        if len(srcode) >= 12:
                            sr_fields = list(srcode)
                            # Extract date from datetime string (format: "YYYY-MM-DD   HH:MM:SS")
                            date_only = utc.split()[0] if utc else ""
                            cursor.execute(
                                "INSERT OR IGNORE INTO statrep "
                                "(datetime, date, freq, db, source, SRid, from_callsign, groupname, grid, prec, status, commpwr, pubwtr, "
                                "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
                                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (utc, date_only, freq, snr, 1, srid, callsign, group, curgrid, prec,
                                 sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                                 sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                                 sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                                 comments)
                            )
                            conn.commit()
                            print(f"\033[92m[{rig_name}] Added StatRep from: {callsign} ID: {srid}\033[0m")
                            conn.close()
                            return "statrep"

            # =================================================================
            # Pattern-based detection (no markers required)
            # =================================================================

            # StatRep pattern: GRID,PREC,SRID,SRCODE[,COMMENTS]
            # - GRID: 4-6 char maidenhead (AA00 or AA00aa)
            # - PREC: 1-5 (precedence)
            # - SRID: numeric ID
            # - SRCODE: + or 12 digits [1-4]
            # - COMMENTS: optional
            # Only process if sent to a group (@GROUP) or message contains @GROUP
            if to_call.startswith("@") or "@" in value:
                # Use re.search to find pattern anywhere in message (handles various formats)
                statrep_pattern = re.search(
                    r'([A-Z]{2}\d{2}[a-z]{0,2}),([1-5]),(\d+),(\+|[1-4]{12})(?:,(.*))?',
                    value.strip(),
                    re.IGNORECASE
                )
                if statrep_pattern:
                    curgrid = statrep_pattern.group(1).upper()
                    prec1 = statrep_pattern.group(2)
                    srid = statrep_pattern.group(3)
                    srcode = statrep_pattern.group(4)
                    # Apply smart title case to comments (acronym detection)
                    comments = smart_title_case(statrep_pattern.group(5).strip(), abbreviations, self.config.get_apply_text_normalization()) if statrep_pattern.group(5) else ""

                    # Expand compressed "+" to all green (111111111111)
                    if srcode == "+":
                        srcode = "111111111111"

                    prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                    # Extract group from value if not already set (handles embedded @GROUP)
                    pattern_group = group
                    if not pattern_group:
                        group_match = re.search(r'(@[A-Z0-9]+)', value, re.IGNORECASE)
                        if group_match:
                            pattern_group = group_match.group(1).upper()

                    if len(srcode) >= 12:
                        sr_fields = list(srcode)
                        # Extract date from datetime string (format: "YYYY-MM-DD   HH:MM:SS")
                        date_only = utc.split()[0] if utc else ""
                        cursor.execute(
                            "INSERT OR IGNORE INTO statrep "
                            "(datetime, date, freq, db, source, SRid, from_callsign, groupname, grid, prec, status, commpwr, pubwtr, "
                            "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, date_only, freq, snr, 1, srid, callsign, pattern_group, curgrid, prec,
                             sr_fields[0], sr_fields[1], sr_fields[2], sr_fields[3],
                             sr_fields[4], sr_fields[5], sr_fields[6], sr_fields[7],
                             sr_fields[8], sr_fields[9], sr_fields[10], sr_fields[11],
                             comments)
                        )
                        conn.commit()
                        print(f"\033[92m[{rig_name}] Added StatRep (pattern) from: {callsign} ID: {srid}\033[0m")
                        conn.close()
                        return "statrep"

            # Check for F!304 statrep format (BEFORE standard MSG check)
            # Format: [CALLSIGN:] [@GROUP|CALLSIGN] [MSG] F!304 {8 digits} {remainder text}
            # Note: MSG is optional
            # This must be checked before standard " MSG " to avoid false matches
            if "F!304" in value:
                import random

                # Check the pattern before "F!304" to determine if we should process
                # Pattern: look at what comes before F!304
                pre_msg = value.split("F!304")[0]

                # Check for callsign-to-callsign pattern (skip if found)
                # Pattern: CALL1: CALL2 [MSG] (two callsigns before F!304)
                callsign_pattern = re.search(r'([A-Z0-9]+):\s+([A-Z0-9/]+)\s+(?:MSG\s+)?$', pre_msg, re.IGNORECASE)
                if callsign_pattern:
                    # This is a callsign-to-callsign message, skip processing
                    conn.close()
                    return ""

                # Extract pattern: [MSG] F!304 {8 digits} {remainder}
                # MSG is optional
                f304_pattern = re.search(r'(?:MSG\s+)?F!304\s+(\d{8})\s*(.*?)(?:>])?$', value)

                if f304_pattern:
                    digits = f304_pattern.group(1)      # 8-digit code
                    remainder = f304_pattern.group(2)   # Rest of message

                    # Parse the 8 digits
                    # Position 1 (digits[0]): Landline text
                    # Position 2 (digits[1]): ota mapping
                    ota_digit = int(digits[1])
                    if ota_digit == 1:
                        ota = "1"
                    elif ota_digit in [2, 3]:
                        ota = "2"
                    elif ota_digit == 4:
                        ota = "3"
                    else:
                        ota = "4"

                    # Position 4-6 (digits[3-5]): direct mapping
                    net = digits[3]
                    pubwtr = digits[4]
                    commpw = digits[5]

                    # Build comment string
                    # Helper function to map digit to text
                    def map_value(digit):
                        mapping = {1: "Yes", 2: "Limited", 3: "No", 4: "Unknown"}
                        return mapping.get(int(digit), "Unknown")

                    landline = map_value(digits[0])  # Position 1
                    amfmtv = map_value(digits[2])    # Position 3
                    natgas = map_value(digits[6])    # Position 7
                    noaa = map_value(digits[7])      # Position 8

                    # Extract grid square from remainder (pattern: 2 alpha + 2 digits + optional 2 alphanumeric)
                    # Look for grid square like EM48AT, EM48, etc.
                    f304_grid = grid  # Default to sender's grid from parameter
                    f304_grid_found = False  # Track if grid was found in message
                    grid_match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9]{0,2})\b', remainder, re.IGNORECASE)
                    if grid_match:
                        f304_grid = grid_match.group(1).upper()
                        f304_grid_found = True
                        # Remove grid square from remainder
                        remainder = remainder.replace(grid_match.group(0), '').strip()

                    # Build comment
                    comment_parts = [
                        "F!304",
                        f"Landline = {landline}",
                        f"AM/FM/TV = {amfmtv}",
                        f"Nat Gas = {natgas}",
                        f"NOAA = {noaa}"
                    ]

                    if remainder.strip():
                        # Apply text normalization to remainder if enabled
                        formatted_remainder = smart_title_case(
                            remainder.strip(),
                            abbreviations,
                            self.config.get_apply_text_normalization()
                        )
                        comments = ", ".join(comment_parts) + f" - {formatted_remainder}"
                    else:
                        comments = ", ".join(comment_parts)

                    # Extract group: check for @GROUP in value, otherwise use "@ALL"
                    f304_group = group if group else ""
                    if not f304_group and "@" in value:
                        group_match = re.search(r'(@[A-Z0-9]+)', value, re.IGNORECASE)
                        if group_match:
                            f304_group = group_match.group(1).upper()

                    # If still no group found, set to @ALL
                    if not f304_group:
                        f304_group = "@ALL"

                    # Generate random 3-digit SRid
                    srid_f304 = random.randint(100, 999)

                    # Extract date from datetime string (format: "YYYY-MM-DD   HH:MM:SS")
                    date_only = utc.split()[0] if utc else ""

                    # Calculate status based on sum of last 8 digits (all digits for F!304)
                    # Count 4 as 1, all others as face value
                    digit_score = 0
                    for d in digits:
                        digit_val = int(d)
                        digit_score += 1 if digit_val == 4 else digit_val

                    # Determine status based on score
                    if digit_score > 12:
                        f304_status = "3"
                    elif digit_score > 10:
                        f304_status = "2"
                    elif f304_grid_found:
                        f304_status = "1"
                    else:
                        f304_status = "4"

                    # Insert into statrep table
                    cursor.execute(
                        "INSERT OR IGNORE INTO statrep "
                        "(datetime, date, freq, db, source, SRid, from_callsign, groupname, grid, prec, status, commpwr, pubwtr, "
                        "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (utc, date_only, freq, snr, 1,
                         srid_f304,      # SRid: random 3-digit number (100-999)
                         callsign,       # from_callsign
                         f304_group,     # groupname
                         f304_grid,      # grid from message or sender's grid
                         "My Location",  # prec: set to "My Location"
                         f304_status,    # status: "1" if grid found in message, "4" if not
                         commpw,         # commpwr
                         pubwtr,         # pubwtr
                         "4",            # med (hardcoded)
                         ota,            # ota (mapped from digit 2)
                         "4",            # trav (hardcoded)
                         net,            # net
                         "4",            # fuel (hardcoded)
                         "4",            # food (hardcoded)
                         "4",            # crime (hardcoded)
                         "4",            # civil (hardcoded)
                         "4",            # political (hardcoded)
                         comments)       # comments (formatted string)
                    )
                    conn.commit()
                    print(f"\033[92m[{rig_name}] Added F!304 StatRep from: {callsign}\033[0m")
                    conn.close()
                    return "statrep"

            # Check for F!301 statrep format (BEFORE standard MSG check)
            # Format: [CALLSIGN:] [@GROUP|CALLSIGN] [MSG] F!301 {9 digits} {remainder text}
            # Note: MSG is optional
            # First digit = precedence (1-5), remaining 8 digits same as F!304
            if "F!301" in value:
                import random

                # Check the pattern before "F!301" to determine if we should process
                # Pattern: look at what comes before F!301
                pre_msg = value.split("F!301")[0]

                # Check for callsign-to-callsign pattern (skip if found)
                # Pattern: CALL1: CALL2 [MSG] (two callsigns before F!301)
                callsign_pattern = re.search(r'([A-Z0-9]+):\s+([A-Z0-9/]+)\s+(?:MSG\s+)?$', pre_msg, re.IGNORECASE)
                if callsign_pattern:
                    # This is a callsign-to-callsign message, skip processing
                    conn.close()
                    return ""

                # Extract pattern: [MSG] F!301 {9 digits} {remainder}
                # MSG is optional
                f301_pattern = re.search(r'(?:MSG\s+)?F!301\s+(\d{9})\s*(.*?)(?:>])?$', value)

                if f301_pattern:
                    digits = f301_pattern.group(1)      # 9-digit code
                    remainder = f301_pattern.group(2)   # Rest of message

                    # Parse the 9 digits
                    # Position 1 (digits[0]): precedence (1-5, maps to PRECEDENCE_MAP)
                    prec1 = digits[0]
                    prec = PRECEDENCE_MAP.get(prec1, "Unknown")

                    # Remaining 8 digits follow F!304 rules
                    # Position 2 (digits[1]): ignored (same as F!304 position 1)
                    # Position 3 (digits[2]): ota mapping (same as F!304 position 2)
                    ota_digit = int(digits[2])
                    if ota_digit == 1:
                        ota = "1"
                    elif ota_digit in [2, 3]:
                        ota = "2"
                    elif ota_digit == 4:
                        ota = "3"
                    else:
                        ota = "4"

                    # Positions 5-7 (digits[4-6]): direct mapping (same as F!304 positions 4-6)
                    net = digits[4]
                    pubwtr = digits[5]
                    commpw = digits[6]

                    # Build comment string
                    # Helper function to map digit to text
                    def map_value(digit):
                        mapping = {1: "Yes", 2: "Limited", 3: "No", 4: "Unknown"}
                        return mapping.get(int(digit), "Unknown")

                    amfmtv = map_value(digits[3])   # Position 4 (same as F!304 position 3)
                    natgas = map_value(digits[7])   # Position 8 (same as F!304 position 7)
                    noaa = map_value(digits[8])     # Position 9 (same as F!304 position 8)

                    # Extract grid square from remainder (pattern: 2 alpha + 2 digits + optional 2 alphanumeric)
                    # Look for grid square like EM48AT, EM48, etc.
                    f301_grid = grid  # Default to sender's grid from parameter
                    f301_grid_found = False  # Track if grid was found in message
                    grid_match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9]{0,2})\b', remainder, re.IGNORECASE)
                    if grid_match:
                        f301_grid = grid_match.group(1).upper()
                        f301_grid_found = True
                        # Remove grid square from remainder
                        remainder = remainder.replace(grid_match.group(0), '').strip()

                    # Build comment
                    comment_parts = [
                        "F!301",
                        f"AM/FM/TV = {amfmtv}",
                        f"Nat Gas = {natgas}",
                        f"NOAA = {noaa}"
                    ]

                    if remainder.strip():
                        # Apply text normalization to remainder if enabled
                        formatted_remainder = smart_title_case(
                            remainder.strip(),
                            abbreviations,
                            self.config.get_apply_text_normalization()
                        )
                        comments = ", ".join(comment_parts) + f" - {formatted_remainder}"
                    else:
                        comments = ", ".join(comment_parts)

                    # Extract group: check for @GROUP in value, otherwise use "@ALL"
                    f301_group = group if group else ""
                    if not f301_group and "@" in value:
                        group_match = re.search(r'(@[A-Z0-9]+)', value, re.IGNORECASE)
                        if group_match:
                            f301_group = group_match.group(1).upper()

                    # If still no group found, set to @ALL
                    if not f301_group:
                        f301_group = "@ALL"

                    # Generate random 3-digit SRid
                    srid_f301 = random.randint(100, 999)

                    # Extract date from datetime string (format: "YYYY-MM-DD   HH:MM:SS")
                    date_only = utc.split()[0] if utc else ""

                    # Calculate status based on sum of last 8 digits (skip first precedence digit)
                    # Count 4 as 1, all others as face value
                    digit_score = 0
                    for d in digits[1:]:  # Skip first digit (precedence)
                        digit_val = int(d)
                        digit_score += 1 if digit_val == 4 else digit_val

                    # Determine status based on score
                    if digit_score > 12:
                        f301_status = "3"
                    elif digit_score > 10:
                        f301_status = "2"
                    elif f301_grid_found:
                        f301_status = "1"
                    else:
                        f301_status = "4"

                    # Insert into statrep table
                    cursor.execute(
                        "INSERT OR IGNORE INTO statrep "
                        "(datetime, date, freq, db, source, SRid, from_callsign, groupname, grid, prec, status, commpwr, pubwtr, "
                        "med, ota, trav, net, fuel, food, crime, civil, political, comments) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (utc, date_only, freq, snr, 1,
                         srid_f301,      # SRid: random 3-digit number (100-999)
                         callsign,       # from_callsign
                         f301_group,     # groupname
                         f301_grid,      # grid from message or sender's grid
                         prec,           # prec: from first digit (1-5) mapped to PRECEDENCE_MAP
                         f301_status,    # status: "1" if grid found in message, "4" if not
                         commpw,         # commpwr
                         pubwtr,         # pubwtr
                         "4",            # med (hardcoded)
                         ota,            # ota (mapped from digit 3)
                         "4",            # trav (hardcoded)
                         net,            # net
                         "4",            # fuel (hardcoded)
                         "4",            # food (hardcoded)
                         "4",            # crime (hardcoded)
                         "4",            # civil (hardcoded)
                         "4",            # political (hardcoded)
                         comments)       # comments (formatted string)
                    )
                    conn.commit()
                    print(f"\033[92m[{rig_name}] Added F!301 StatRep from: {callsign}\033[0m")
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
                        # Apply smart title case to message (acronym detection)
                        message_text = smart_title_case(msg_match.group(1).strip(), abbreviations, self.config.get_apply_text_normalization())

                        # Use to_call for target (includes @ for groups, callsign for direct)
                        target = to_call

                        cursor.execute(
                            "INSERT INTO messages "
                            "(datetime, freq, db, source, SRid, from_callsign, target, message) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                            (utc, freq, snr, 1, "", callsign, target, message_text)
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

    def _show_image_dialog(
        self,
        title: str,
        image_url: str,
        link_html: str,
        loading_text: str,
        error_prefix: str
    ) -> None:
        """
        Display a dialog that fetches and shows an image from a URL.

        This helper method reduces code duplication for dialogs that display
        remote images (band conditions, solar flux, world map, etc.).

        Args:
            title: Window title for the dialog.
            image_url: URL of the image to fetch.
            link_html: HTML string for the attribution/link label.
            loading_text: Text to show while loading.
            error_prefix: Prefix for error message (e.g., "Failed to load band conditions").
        """
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(480, 200)
        dialog.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image label (shows loading text, then image or error)
        image_label = QtWidgets.QLabel(loading_text)
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

        # Attribution/link label
        link_label = QtWidgets.QLabel(link_html)
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(link_label)

        # Close button
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # Storage for fetched data (shared between threads)
        fetch_result = {'data': None, 'error': None}

        def fetch_image():
            """Background thread: fetch image from URL."""
            try:
                request = urllib.request.Request(
                    image_url,
                    headers={'User-Agent': 'CommStat/2.5'}
                )
                with urllib.request.urlopen(request, timeout=15, context=create_insecure_ssl_context()) as response:
                    fetch_result['data'] = response.read()
            except Exception as e:
                fetch_result['error'] = str(e)

        def update_ui():
            """Poll for fetch completion and update dialog."""
            if fetch_result['data']:
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(fetch_result['data'])
                image_label.setPixmap(pixmap)
                dialog.adjustSize()
            elif fetch_result['error']:
                image_label.setText(f"{error_prefix}: {fetch_result['error']}")
            else:
                # Still loading, check again in 100ms
                QTimer.singleShot(100, update_ui)

        # Start fetch in background thread
        thread = threading.Thread(target=fetch_image, daemon=True)
        thread.start()

        # Start polling for result
        QTimer.singleShot(100, update_ui)

        dialog.exec_()

    def _on_band_conditions(self) -> None:
        """Show Band Conditions dialog with N0NBH solar-terrestrial data."""
        self._show_image_dialog(
            title="Band Conditions",
            image_url="https://www.hamqsl.com/solar101pic.php",
            link_html='<a href="https://www.hamqsl.com/solar.html">Solar-Terrestrial Data provided by N0NBH</a>',
            loading_text="Loading band conditions...",
            error_prefix="Failed to load band conditions"
        )

    def _on_solar_flux(self) -> None:
        """Show Solar Flux dialog with N0NBH solar flux chart."""
        self._show_image_dialog(
            title="Solar Flux",
            image_url="https://www.hamqsl.com/marston.php",
            link_html='<a href="https://www.hamqsl.com/solar.html">Solar-Terrestrial Data provided by N0NBH</a>',
            loading_text="Loading solar flux data...",
            error_prefix="Failed to load solar flux data"
        )

    def _on_world_map(self) -> None:
        """Show World Map dialog with current solar conditions."""
        self._show_image_dialog(
            title="World Map",
            image_url="https://www.hamqsl.com/solarmuf.php",
            link_html='<a href="https://www.hamqsl.com/solar.html">View more at hamqsl.com</a>',
            loading_text="Loading solar conditions...",
            error_prefix="Failed to load solar data"
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
    # Check for debug mode
    debug_mode = "--debug" in sys.argv

    # Check for demo mode with version number and optional duration
    # Usage: --demo-mode [version] [duration_seconds]
    demo_mode = False
    demo_version = 1
    demo_duration = 60  # default 60 seconds
    for i, arg in enumerate(sys.argv):
        if arg == "--demo-mode":
            demo_mode = True
            # Check if next arg is a version number
            if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit():
                demo_version = int(sys.argv[i + 1])
                # Check if there's also a duration
                if i + 2 < len(sys.argv) and sys.argv[i + 2].isdigit():
                    demo_duration = int(sys.argv[i + 2])

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

    # Load configuration
    config = ConfigManager()

    # In demo mode, initialize demo database (but still use traffic.db3 for display)
    if demo_mode:
        from demo_mode import init_demo_database
        init_demo_database()  # Creates demo.db3 if needed

    db = DatabaseManager()

    # Initialize Groups table (creates if needed)
    db.init_groups_table()

    # Initialize QRZ settings table (creates if needed)
    db.init_qrz_table()

    # Initialize alerts table (creates if needed)
    db.init_alerts_table()

    # Initialize statrep table (creates if needed)
    db.init_statrep_table()

    # Initialize messages table (creates if needed)
    db.init_messages_table()

    # Initialize abbreviations table (creates if needed, populates with defaults)
    db.init_abbreviations_table()

    # Create and show main window
    window = MainWindow(config, db, debug_mode=debug_mode, demo_mode=demo_mode, demo_version=demo_version, demo_duration=demo_duration)
    window.show()

    if debug_mode:
        print("Debug mode enabled")
    if demo_mode:
        print(f"Demo mode enabled - Version {demo_version} - {demo_duration} second disaster simulation")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
