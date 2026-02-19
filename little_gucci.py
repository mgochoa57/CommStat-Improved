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
import re
import base64
import socket
import sqlite3
import threading
import subprocess
import http.server
import socketserver
import urllib.request
import ssl
import time
import tempfile
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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
from id_utils import generate_time_based_id


# =============================================================================
# Constants
# =============================================================================

VERSION = "3.0.4"
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
SLIDESHOW_INTERVAL = 5  # Minutes between image changes

# Backbone server for remote announcements and slideshow images
# This allows the developer to push messages/images to all CommStat users
_BACKBONE = base64.b64decode("aHR0cHM6Ly9jb21tc3RhdC1pbXByb3ZlZC5jb20=").decode()
_PING = _BACKBONE + "/heartbeat-808585.php"

# Internet connectivity check interval (30 minutes in ms)
INTERNET_CHECK_INTERVAL = 30 * 60 * 1000

# News feed animation timing
NEWSFEED_TYPE_INTERVAL_MS = 60    # ms per character during type-on
NEWSFEED_PAUSE_MS = 20000         # ms to hold when window is full
NEWSFEED_SCROLL_DURATION_MS = 1000  # total ms for the scroll-off phase


class ConsoleColors:
    """ANSI color codes for console output."""
    SUCCESS = "\033[92m"  # Green
    WARNING = "\033[93m"  # Yellow
    ERROR = "\033[91m"    # Red
    RESET = "\033[0m"


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

    # Identify words that should be preserved as all-caps
    # These are words that:
    # 1. Are in the abbreviations dictionary
    # 2. Expand to an all-caps form (e.g., state codes: TX, NY, SC)
    preserved_caps = set()
    if abbreviations:
        for word in text.split():
            clean = ''.join(c for c in word if c.isalnum())
            upper_clean = clean.upper()
            # Check if this word is in abbreviations and expands to all-caps
            if upper_clean in abbreviations:
                expansion = abbreviations[upper_clean]
                # If expansion is all uppercase, preserve it
                if expansion.isupper():
                    preserved_caps.add(expansion.upper())

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

        # Skip empty words (punctuation only)
        if not clean_word:
            result.append(word)
            continue

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


# =============================================================================
# STATREP Parsing Helper Functions
# =============================================================================

def strip_duplicate_callsign(value: str, from_call: str) -> str:
    """
    Remove duplicate callsign from message value if present.

    JS8Call bug causes: "W8APP: W8APP: @GROUP ..." instead of "W8APP: @GROUP ..."
    Must handle both formats since most users still have the buggy version.

    Args:
        value: Message text from JS8Call TCP stream
        from_call: Sender callsign from JSON params (may include /P suffix)

    Returns:
        Cleaned message text with duplicate removed
    """
    # Extract base callsign (remove /P, /M suffixes)
    base_call = from_call.split("/")[0] if from_call else ""
    if not base_call:
        return value

    # Pattern: "CALLSIGN: CALLSIGN: remainder"
    # Use word boundary to avoid partial matches
    pattern = rf'\b{re.escape(base_call)}\s*:\s*{re.escape(base_call)}\s*:\s*'
    if re.match(pattern, value, re.IGNORECASE):
        # Remove first occurrence, keep second
        value = re.sub(pattern, f'{base_call}: ', value, count=1, flags=re.IGNORECASE)

    return value


def sanitize_ascii(text: str) -> str:
    """
    Remove non-ASCII characters (keep only printable ASCII 32-126).

    Args:
        text: Input text

    Returns:
        Sanitized text with only printable ASCII characters
    """
    return re.sub(r'[^ -~]+', '', text).strip()


def parse_message_datetime(utc: str) -> tuple:
    """
    Parse UTC timestamp and generate time-based ID.

    Args:
        utc: UTC timestamp string (format: "YYYY-MM-DD   HH:MM:SS" or "YYYY-MM-DD HH:MM:SS")

    Returns:
        (date_only_str, time_based_id)
    """
    dt_str = utc.replace("   ", " ").strip()
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    date_only = utc.split()[0] if utc else ""
    msg_id = generate_time_based_id(dt)

    return (date_only, msg_id)


def expand_plus_shorthand(srcode: str) -> str:
    """Expand '+' shorthand to '111111111111' (all green status)."""
    return "111111111111" if srcode == "+" else srcode


def extract_grid_from_text(text: str, default_grid: str) -> tuple:
    """
    Extract Maidenhead grid square from text.

    Returns:
        (grid_square, found_in_message)
    """
    # Pattern: 2 letters + 2 digits + optional 2 alphanumeric (e.g., EM15, EM15at)
    match = re.search(r'\b([A-Z]{2}\d{2}[A-Z0-9]{0,2})\b', text, re.IGNORECASE)
    if match:
        return (match.group(1).upper(), True)
    return (default_grid, False)


def format_statrep_comments(raw_comments: str, abbreviations: dict, apply_norm: bool) -> str:
    """
    Format STATREP comments: apply smart title case and filter non-ASCII.

    Args:
        raw_comments: Raw comment text
        abbreviations: Dictionary of known abbreviations for smart_title_case
        apply_norm: Whether to apply text normalization

    Returns:
        Formatted comments string
    """
    if not raw_comments:
        return ""

    # Apply smart title case (preserves acronyms)
    formatted = smart_title_case(raw_comments, abbreviations, apply_norm) if raw_comments else ""

    # Remove non-ASCII characters (keep only space through tilde: ASCII 32-126)
    formatted = re.sub(r'[^ -~]+', '', formatted).strip()

    return formatted


# REMOVED: extract_group_from_message() - Function was never called in codebase
# Group extraction is now handled directly in message processing handlers


def calculate_f304_status(digits: str, grid_found: bool) -> str:
    """
    Calculate map status for F!304/F!301 based on digit score.

    Rules:
    - Count 4 as 1, all others as face value
    - Score > 12: Red (3)
    - Score > 10: Yellow (2)
    - Grid found: Green (1)
    - Else: Unknown (4)
    """
    digit_score = sum(1 if int(d) == 4 else int(d) for d in digits)

    if digit_score > 12:
        return "3"
    elif digit_score > 10:
        return "2"
    elif grid_found:
        return "1"
    else:
        return "4"


def map_f304_digits_to_fields(digits: str) -> dict:
    """
    Map 8-digit F!304 format to database fields.

    Digit positions:
    [0]=Landline, [1]=Telecom, [2]=AM/FM/TV, [3]=Internet,
    [4]=Water, [5]=Power, [6]=Nat Gas, [7]=NOAA

    Returns dict with: power, water, telecom, internet, and comment parts
    """
    # Direct mappings
    commpw = digits[5]  # Commercial power
    pubwtr = digits[4]  # Public water
    net = digits[3]     # Internet

    # Telecom mapping (position 1)
    ota_digit = int(digits[1])
    if ota_digit == 1:
        ota = "1"
    elif ota_digit in [2, 3]:
        ota = "2"
    elif ota_digit == 4:
        ota = "3"
    else:
        ota = "4"

    # Comment additions (fields not in 12-digit format)
    YESNO_MAP = {1: "Yes", 2: "Limited", 3: "No", 4: "Unknown"}
    landline = YESNO_MAP.get(int(digits[0]), "Unknown")
    amfmtv = YESNO_MAP.get(int(digits[2]), "Unknown")
    natgas = YESNO_MAP.get(int(digits[6]), "Unknown")
    noaa = YESNO_MAP.get(int(digits[7]), "Unknown")

    return {
        'power': commpw,
        'water': pubwtr,
        'telecom': ota,
        'internet': net,
        'comment_parts': [
            f"Landline = {landline}",
            f"AM/FM/TV = {amfmtv}",
            f"Nat Gas = {natgas}",
            f"NOAA = {noaa}"
        ]
    }


def map_f301_digits_to_fields(digits: str) -> dict:
    """
    Map 9-digit F!301 format to database fields.

    First digit = scope (1-5), remaining 8 follow F!304 rules.

    Returns dict with: scope, power, water, telecom, internet, and comment parts
    """
    # Scope mapping
    SCOPE_MAP = {
        "1": "My Location",
        "2": "My Community",
        "3": "My County",
        "4": "My Region",
        "5": "Other Location"
    }
    scope = SCOPE_MAP.get(digits[0], "Unknown")

    # Remaining 8 digits follow F!304 format
    f304_fields = map_f304_digits_to_fields(digits[1:])

    # F!301 doesn't include Landline in comments
    f304_fields['comment_parts'] = f304_fields['comment_parts'][1:]  # Skip Landline
    f304_fields['scope'] = scope

    return f304_fields


# StatRep table column headers
STATREP_HEADERS = [
    "", "Date Time", "Freq", "From", "To", "ID", "Grid", "Scope", "Map",
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
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': True, 'show_every_group': True, 'hide_map': False, 'show_alerts': False, 'selected_rss_feed': default_feed, 'apply_text_normalization': False}
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
                'apply_text_normalization': config.getboolean("DIRECTEDCONFIG", "apply_text_normalization", fallback=True),
            }
        else:
            self.directed_config = {'hide_heartbeat': False, 'show_all_groups': True, 'show_every_group': True, 'hide_map': False, 'show_alerts': False, 'selected_rss_feed': default_feed, 'apply_text_normalization': False}

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
            articles = []  # List of (title, pubdate_datetime) tuples
            now = datetime.now(timezone.utc)
            cutoff_time = now - timedelta(hours=6)

            # Try RSS 2.0 format first (most common)
            for item in root.findall('.//item'):
                title_elem = item.find('title')
                pubdate_elem = item.find('pubDate')

                if title_elem is not None and title_elem.text:
                    title = title_elem.text.strip()
                    pub_date = None

                    # Parse publication date
                    if pubdate_elem is not None and pubdate_elem.text:
                        try:
                            pub_date = parsedate_to_datetime(pubdate_elem.text)
                            # Filter out articles older than 6 hours
                            if pub_date < cutoff_time:
                                continue
                        except Exception:
                            # If date parsing fails, include the article anyway
                            pub_date = None

                    articles.append((title, pub_date))

            # Try Atom format if no RSS items found
            if not articles:
                # Atom uses namespace
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                for entry in root.findall('.//atom:entry', ns):
                    title_elem = entry.find('atom:title', ns)
                    published_elem = entry.find('atom:published', ns) or entry.find('atom:updated', ns)

                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()
                        pub_date = None

                        # Parse publication date
                        if published_elem is not None and published_elem.text:
                            try:
                                # Atom uses ISO 8601 format
                                pub_date = datetime.fromisoformat(published_elem.text.replace('Z', '+00:00'))
                                # Filter out articles older than 6 hours
                                if pub_date < cutoff_time:
                                    continue
                            except Exception:
                                pub_date = None

                        articles.append((title, pub_date))

                # Also try without namespace
                if not articles:
                    for entry in root.findall('.//entry'):
                        title_elem = entry.find('title')
                        published_elem = entry.find('published') or entry.find('updated')

                        if title_elem is not None and title_elem.text:
                            title = title_elem.text.strip()
                            pub_date = None

                            if published_elem is not None and published_elem.text:
                                try:
                                    pub_date = datetime.fromisoformat(published_elem.text.replace('Z', '+00:00'))
                                    if pub_date < cutoff_time:
                                        continue
                                except Exception:
                                    pub_date = None

                            articles.append((title, pub_date))

            # Sort by date (newest first), articles without dates go to end
            articles.sort(key=lambda x: x[1] if x[1] else datetime.min.replace(tzinfo=timezone.utc), reverse=True)

            # Format headlines with timestamps
            headlines = []
            for title, pub_date in articles[:20]:  # Limit to 20 headlines
                if pub_date:
                    # Convert to UTC for display
                    utc_time = pub_date.astimezone(timezone.utc)
                    time_str = utc_time.strftime('%H:%M UTC')
                    headlines.append(f"{title} - {time_str}")
                else:
                    headlines.append(title)

            self._headlines = headlines
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
                        SELECT db, datetime, freq, from_callsign, target, sr_id, grid, scope, map,
                               power, water, med, telecom, travel, internet,
                               fuel, food, crime, civil, political, comments, source
                        FROM statrep
                        WHERE {date_condition}
                    """
                    params = date_params
                else:
                    # Build group filter for multiple groups (add @ prefix for matching)
                    groups_with_at = ["@" + g for g in groups]
                    placeholders = ",".join("?" * len(groups_with_at))
                    query = f"""
                        SELECT db, datetime, freq, from_callsign, target, sr_id, grid, scope, map,
                               power, water, med, telecom, travel, internet,
                               fuel, food, crime, civil, political, comments, source
                        FROM statrep
                        WHERE target IN ({placeholders}) AND {date_condition}
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
                    query = f"""SELECT db, datetime, freq, from_callsign, target, msg_id, message, source
                               FROM messages
                               WHERE {date_condition}"""
                    params = date_params
                elif groups:
                    # Filter by active groups (add @ prefix for matching)
                    groups_with_at = ["@" + g for g in groups]
                    placeholders = ",".join("?" * len(groups_with_at))
                    query = f"""SELECT db, datetime, freq, from_callsign, target, msg_id, message, source
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

    def get_user_settings(self) -> Tuple[str, str, str]:
        """Get user callsign, grid square, and state from controls table."""
        def op(cursor, conn):
            cursor.execute("SELECT callsign, gridsquare, state FROM controls WHERE id = 1")
            row = cursor.fetchone()
            return (row[0] or "", row[1] or "", row[2] or "") if row else ("", "", "")
        return self._execute(op, ("", "", ""))

    def set_user_settings(self, callsign: str, grid: str, state: str) -> bool:
        """Save user callsign, grid square, and state to controls table."""
        def op(cursor, conn):
            cursor.execute(
                "UPDATE controls SET callsign = ?, gridsquare = ?, state = ? WHERE id = 1",
                (callsign, grid, state)
            )
            conn.commit()
            return cursor.rowcount > 0
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

    def __init__(self, config: ConfigManager, db: DatabaseManager, debug_mode: bool = False, backbone_debug: bool = False, demo_mode: bool = False, demo_version: int = 1, demo_duration: int = 60):
        """
        Initialize the main window.

        Args:
            config: ConfigManager instance with loaded settings
            db: DatabaseManager instance for database operations
            debug_mode: Enable debug features when True
            backbone_debug: Enable backbone StatRep submission debug logging
            demo_mode: Enable demo mode with simulated disaster data
            demo_version: Demo scenario version (1, 2, 3, etc.)
            demo_duration: Demo playback duration in seconds (default 60)
        """
        super().__init__()
        self.config = config
        self.db = db
        self.debug_mode = debug_mode
        self.backbone_debug = backbone_debug
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

        # Backbone check will start automatically after 30 seconds via timer

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
            # Send first heartbeat after 30 second delay, then start timer
            def start_backbone_heartbeat():
                self._check_backbone()  # Send first heartbeat immediately
                self.backbone_timer.start(180000)  # Then start 3 minute interval timer
            QTimer.singleShot(30000, start_backbone_heartbeat)
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
        self.menu = QtWidgets.QMenu("Config", self.menubar)
        self.menubar.addMenu(self.menu)

        # Define menu actions: (name, text, handler)
        menu_items = [
            ("js8_connectors", "JS8 Connectors", self._on_js8_connectors),
            ("qrz_enable", "QRZ Settings", self._on_qrz_enable),
            ("user_settings", "User Settings", self._on_user_settings),
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

        # Create the Transmit menu
        self.transmit_menu = QtWidgets.QMenu("Transmit", self.menubar)
        self.menubar.addMenu(self.transmit_menu)

        transmit_items = [
            ("statrep", "Status Report", self._on_statrep),
            ("group_alert", "Group Alert", self._on_group_alert),
            ("send_message", "Group Message", self._on_send_message),
            ("js8email", "JS8 Email", self._on_js8email),
            ("js8sms", "JS8 SMS", self._on_js8sms),
        ]
        for name, text, handler in transmit_items:
            action = QtWidgets.QAction(text, self)
            action.triggered.connect(handler)
            self.transmit_menu.addAction(action)
            self.actions[name] = action

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
        font = QtGui.QFont("Arial", 13, QtGui.QFont.Bold)

        # News label
        self.label_newsfeed = QtWidgets.QLabel(self.header_widget)
        self.label_newsfeed.setStyleSheet(f"color: {fg_color};")
        self.label_newsfeed.setText("News:")
        self.label_newsfeed.setFont(font)
        self.header_layout.addWidget(self.label_newsfeed)

        # RSS Feed selector dropdown
        self.feed_combo = QtWidgets.QComboBox(self.header_widget)
        self.feed_combo.setFixedSize(120, 28)
        self.feed_combo.setFont(QtGui.QFont("Arial", 13))
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
        combo_view.setFont(QtGui.QFont("Arial", 13))
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
        self.feed_combo.addItem("Disable")
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
        self.newsfeed_label.setFixedSize(740, 32)
        self.newsfeed_label.setFont(QtGui.QFont("Arial", 13))
        self.newsfeed_label.setStyleSheet(
            f"background-color: {self.config.get_color('newsfeed_background')};"
            f"color: {self.config.get_color('newsfeed_foreground')};"
        )
        self.header_layout.addWidget(self.newsfeed_label)

        # Last 20 button - shows last 20 news headlines
        self.last20_button = QtWidgets.QPushButton("Last 20", self.header_widget)
        self.last20_button.setFixedSize(80, 28)
        self.last20_button.setFont(QtGui.QFont("Arial", 13))
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
        self.time_label.setFont(QtGui.QFont("Arial", 13))
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
        self.statrep_table.setColumnCount(21)
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
                font-size: 10pt;
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

        # Use feed colors for background
        bg_color = self.config.get_color('feed_background')
        fg_color = self.config.get_color('feed_foreground')
        self.map_disabled_label.setStyleSheet(
            f"background-color: {bg_color}; color: {fg_color}; font-size: 18px; font-weight: bold;"
        )

        # Add to same layout position as map
        self.main_layout.addWidget(self.map_disabled_label, 4, 0, 2, 1, Qt.AlignLeft | Qt.AlignTop)

        # Image slideshow state
        self.slideshow_items: List[str] = []
        self.slideshow_index: int = 0

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

        # Use vertical layout
        alert_layout = QtWidgets.QVBoxLayout(self.alert_display)
        alert_layout.setAlignment(Qt.AlignTop)

        # Add small spacing at top
        alert_layout.addSpacing(20)

        # Title label (first line)
        self.alert_title_label = QtWidgets.QLabel()
        self.alert_title_label.setAlignment(Qt.AlignCenter)
        self.alert_title_label.setTextFormat(Qt.RichText)  # Enable HTML formatting
        # Title uses Roboto Slab with Black weight (heaviest/900)
        title_font = QtGui.QFont("Roboto Slab", 24, QtGui.QFont.Black)
        self.alert_title_label.setFont(title_font)
        alert_layout.addWidget(self.alert_title_label)

        # Message label (second line)
        self.alert_message_label = QtWidgets.QLabel()
        self.alert_message_label.setAlignment(Qt.AlignCenter)
        self.alert_message_label.setWordWrap(True)
        # Message uses Roboto (clean sans-serif for readability)
        message_font = QtGui.QFont("Roboto", 18)
        self.alert_message_label.setFont(message_font)
        alert_layout.addWidget(self.alert_message_label)

        # Spacer between message and date
        alert_layout.addStretch(1)

        # Date received label (at bottom)
        self.alert_date_label = QtWidgets.QLabel()
        self.alert_date_label.setAlignment(Qt.AlignCenter)
        self.alert_date_label.setTextFormat(Qt.RichText)  # Enable HTML formatting
        # Date uses Roboto (clean sans-serif for readability)
        date_font = QtGui.QFont("Roboto", 12)
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
        self.alert_message_label.setStyleSheet("color: #ffffff; font-family: Roboto;")
        self.alert_date_label.setStyleSheet("color: #ffffff; font-family: Roboto;")

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
            title, message, color, date_received, from_callsign, group = alert

            # Apply text normalization to message field only if enabled
            apply_normalization = self.config.get_apply_text_normalization()
            if apply_normalization:
                abbreviations = self.db.get_abbreviations()
                message = smart_title_case(message, abbreviations, apply_normalization)

            # Set colors based on alert color - all alerts use red
            color_map = {
                1: ("#dc3545", "#ffffff"),  # Red (formerly Yellow)
                2: ("#dc3545", "#ffffff"),  # Red (formerly Orange)
                3: ("#dc3545", "#ffffff"),  # Red
                4: ("#dc3545", "#ffffff"),  # Red (formerly Black)
            }
            bg_color, text_color = color_map.get(color, ("#dc3545", "#ffffff"))

            # Format date to remove seconds (e.g., "2026-01-15 11:00:00" -> "2026-01-15 11:00")
            date_formatted = date_received[:16] if len(date_received) > 16 else date_received

            # Build date/callsign line with bold labels (use Roboto font)
            date_line = f'<span style="font-family: Roboto;"><b>Date Received:</b> {date_formatted}'
            if from_callsign:
                date_line += f"&nbsp;&nbsp;&nbsp;<b>Sent By:</b> {from_callsign}"
            date_line += "</span>"

            # Format alert display:
            # Top: group - ALERT (smaller font)
            # Middle: title (bold, bigger than message)
            # Bottom: message (normal)
            if group:
                # Show group + ALERT at top, then title in bold below (strip @ symbol)
                group_display = group.lstrip('@')
                formatted_title = f'<div style="font-family: \'Roboto Slab\'; font-size: 16pt; font-weight: normal; margin-top: -10px;">{group_display} - ALERT</div>'
                if title:
                    formatted_title += f'<div style="font-family: \'Roboto Slab\'; font-size: 22pt; font-weight: 900; margin-top: 44px;">{title}</div>'
            else:
                # No group, just show title in bold
                formatted_title = f'<div style="font-family: \'Roboto Slab\'; font-size: 22pt; font-weight: 900;">{title if title else ""}</div>'

            self.alert_display.setStyleSheet(f"background-color: {bg_color};")
            self.alert_title_label.setStyleSheet(f"color: {text_color};")
            self.alert_message_label.setStyleSheet(f"color: {text_color}; font-family: Roboto;")
            self.alert_date_label.setStyleSheet(f"color: {text_color}; font-family: Roboto;")
            self.alert_title_label.setText(formatted_title)
            self.alert_message_label.setText(message)
            self.alert_date_label.setText(date_line)
        else:
            # No alerts - show placeholder
            self.alert_display.setStyleSheet("background-color: #333333;")
            self.alert_title_label.setStyleSheet("color: #ffffff;")
            self.alert_message_label.setStyleSheet("color: #ffffff; font-family: Roboto;")
            self.alert_date_label.setStyleSheet("color: #ffffff; font-family: Roboto;")
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

    def _get_alert_at_offset(self, offset: int) -> Optional[Tuple[str, str, int, str, str, str]]:
        """Get an alert at the specified offset from most recent.

        Args:
            offset: 0 for most recent, 1 for second most recent, etc.

        Returns:
            Tuple of (title, message, color, datetime, from_callsign, group) or None if not found.
        """
        try:
            with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, message, color, datetime, from_callsign, target FROM alerts ORDER BY datetime DESC LIMIT 1 OFFSET ?",
                    (offset,)
                )
                result = cursor.fetchone()
                if result:
                    return (result[0], result[1], result[2], result[3], result[4] or "", result[5] or "")
        except sqlite3.Error as e:
            print(f"Error fetching alert at offset {offset}: {e}")
        return None

    def _fetch_backbone_content(self) -> Optional[str]:
        """Fetch and extract content from backbone server.

        Returns:
            Extracted content string, or None on error.
        """
        try:
            # Get callsign: prefer first active JS8 connector callsign, fall back to user settings
            callsign = next((cs for cs in self.rig_callsigns.values() if cs), None)
            if not callsign:
                callsign, _, __ = self.db.get_user_settings()
            if not callsign:
                callsign = "UNKNOWN"

            # Get db_version, build_number, and data_id from controls table
            db_version = 0
            build_number = 500  # Default fallback
            data_id = 0  # Default fallback
            try:
                conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT db_version, build_number, data_id FROM controls WHERE id = 1")
                result = cursor.fetchone()
                if result:
                    db_version = result[0]
                    build_number = result[1] if len(result) > 1 else 500
                    data_id = result[2] if len(result) > 2 else 0
                conn.close()
            except sqlite3.Error:
                pass  # Use default values if query fails

            # Build heartbeat URL with callsign, data_id, db_version, and build_number parameters
            heartbeat_url = f"{_PING}?cs={callsign}&id={data_id}&db={db_version}&build={build_number}"

            with urllib.request.urlopen(heartbeat_url, timeout=10) as response:
                content = response.read().decode('utf-8')

            return content.strip() or None
        except Exception:
            return None

    def _handle_db_update(self, content: str) -> bool:
        """Handle database update from backbone server.

        Expected format:
        db_update
        db: 3
        sql:
        CREATE TABLE ... );
        INSERT INTO ... );

        Each SQL statement ends with };

        Args:
            content: The db_update response content

        Returns:
            True if update was successful, False otherwise
        """
        try:
            lines = content.split('\n')

            if not lines or lines[0].strip() != 'db_update':
                return False

            new_db_version = None
            sql_section = None

            # Find db version and sql section
            for i, line in enumerate(lines):
                if line.strip().startswith('db:'):
                    try:
                        new_db_version = int(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        return False
                elif line.strip().startswith('sql:'):
                    # SQL may start on this line or the next
                    sql_start = line.split(':', 1)[1].strip()
                    if sql_start:
                        # SQL starts on same line
                        sql_section = sql_start + '\n' + '\n'.join(lines[i+1:])
                    else:
                        # SQL starts on next line
                        sql_section = '\n'.join(lines[i+1:])
                    break

            if new_db_version is None or sql_section is None:
                return False

            # Split SQL statements by semicolon
            sql_statements = []
            raw_statements = sql_section.split(';')

            for stmt in raw_statements:
                stmt = stmt.strip()
                if stmt:  # Skip empty statements
                    sql_statements.append(stmt)

            if not sql_statements:
                return False

            # Execute SQL statements
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()

            try:
                for sql in sql_statements:
                    cursor.execute(sql)

                # Update db_version in controls table
                cursor.execute("UPDATE controls SET db_version = ? WHERE id = 1", (new_db_version,))
                conn.commit()
                print(f"Database updated successfully to version {new_db_version}")

                return True

            except sqlite3.Error as e:
                conn.rollback()
                print(f"Database update failed: {e}")
                return False
            finally:
                conn.close()

        except Exception as e:
            print(f"Error handling db_update: {e}")
            return False

    def _handle_program_update(self, content: str) -> bool:
        """Handle program update from backbone server.

        Expected format:
        program_update
        build: 501
        url: https://commstat.com/downloads/update.zip

        Args:
            content: The program_update response content

        Returns:
            True if download was successful, False otherwise
        """
        try:
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            if not lines or lines[0] != 'program_update':
                return False

            new_build = None
            download_url = None

            # Parse the update content
            for line in lines[1:]:
                if line.startswith('build:'):
                    try:
                        new_build = int(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        print(f"Invalid build number format: {line}")
                        return False
                elif line.startswith('url:') or line.startswith('URL:'):
                    download_url = line.split(':', 1)[1].strip()
                    # Handle URLs that might have multiple colons (https://)
                    if '://' in line:
                        download_url = line.split(None, 1)[1].strip()

            if new_build is None or not download_url:
                print("Missing build number or URL in program_update")
                return False

            # Create updates directory if it doesn't exist
            import os
            updates_dir = os.path.join(os.path.dirname(__file__), 'updates')
            os.makedirs(updates_dir, exist_ok=True)

            update_file = os.path.join(updates_dir, 'update.zip')

            # Download the update
            print(f"Downloading update build {new_build} from {download_url}")

            try:
                with urllib.request.urlopen(download_url, timeout=30) as response:
                    with open(update_file, 'wb') as f:
                        f.write(response.read())

                print(f"Update downloaded successfully to {update_file}")

                # Update build_number in database
                try:
                    conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE controls SET build_number = ? WHERE id = 1", (new_build,))
                    conn.commit()
                    conn.close()
                    print(f"Build number updated to {new_build} in database")
                except sqlite3.Error as e:
                    print(f"Warning: Failed to update build number in database: {e}")
                    # Continue anyway - the update file is downloaded

                # Show restart prompt to user
                QtCore.QMetaObject.invokeMethod(
                    self, "_show_program_update_notification",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(int, new_build)
                )

                return True

            except Exception as e:
                print(f"Failed to download update: {e}")
                # Clean up partial download
                if os.path.exists(update_file):
                    os.remove(update_file)
                return False

        except Exception as e:
            print(f"Error handling program_update: {e}")
            return False

    def _is_valid_grid(self, grid: str) -> bool:
        """Check if a string looks like a valid Maidenhead grid square.

        Args:
            grid: String to validate

        Returns:
            True if it looks like a valid grid square (e.g., EM83CV, FN20, etc.)
        """
        if not grid:
            return False
        grid = grid.strip().upper()
        # Grid squares are 2 letters + 2 digits + optional 2 letters/digits
        # Examples: EM83, EM83CV, FN20XS
        if len(grid) < 4 or len(grid) > 8:
            return False
        # First 2 chars must be letters A-R
        if not (grid[0].isalpha() and grid[1].isalpha()):
            return False
        if not (grid[0] in 'ABCDEFGHIJKLMNOPQR' and grid[1] in 'ABCDEFGHIJKLMNOPQR'):
            return False
        # Next 2 must be digits
        if not (grid[2].isdigit() and grid[3].isdigit()):
            return False
        return True

    def _lookup_grid_for_callsign(self, callsign: str) -> Optional[str]:
        """Look up grid square for a callsign using QRZ cache/API.

        Args:
            callsign: Callsign to lookup

        Returns:
            Grid square or None if not found
        """
        try:
            from qrz_client import QRZClient, load_qrz_config

            # Check if QRZ is active
            active, username, password = load_qrz_config()
            if not active:
                return None

            # Create client and do lookup (uses cache first)
            client = QRZClient(username, password)
            result = client.lookup(callsign, use_cache=True)

            if result and result.get('grid'):
                grid = result['grid']
                print(f"[QRZ] Found grid {grid} for {callsign}")
                return grid

            return None
        except Exception as e:
            print(f"[QRZ] Error looking up {callsign}: {e}")
            return None

    def _resolve_grid(
        self,
        rig_name: str,
        grid: str,
        callsign: str,
        fallback_grid: str = "",
        msg_format: str = ""
    ) -> str:
        """
        Resolve grid square with QRZ fallback if needed.

        Args:
            rig_name: Rig identifier for logging
            grid: Primary grid square (may be empty/invalid)
            callsign: Callsign to lookup if grid is missing
            fallback_grid: Grid to use if QRZ lookup fails
            msg_format: Message format for logging (e.g., "STATREP", "F!304")

        Returns:
            Valid grid square or fallback
        """
        prefix = f"[{rig_name}] {msg_format}: " if msg_format else f"[{rig_name}] "

        # Case 1: Already have a precise grid (5+ chars) - use directly
        if grid and len(grid) > 4:
            return grid

        # Case 2: Have a 4-char grid - try to upgrade via QRZ
        if grid and len(grid) == 4:
            qrz_grid = self._lookup_grid_for_callsign(callsign)
            if qrz_grid and len(qrz_grid) > 4 and qrz_grid[:4].upper() == grid.upper():
                # Format as mixed case: first 4 upper + rest lower (e.g., EM83cv)
                # This makes QRZ-upgraded grids visually distinguishable
                qrz_grid = qrz_grid[:4].upper() + qrz_grid[4:].lower()
                print(f"{prefix}Upgraded grid {grid} -> {qrz_grid} via QRZ for {callsign}")
                return qrz_grid
            return grid

        # Try QRZ lookup for missing/invalid grid
        print(f"{prefix}Missing/invalid grid, attempting QRZ lookup for {callsign}")

        qrz_grid = self._lookup_grid_for_callsign(callsign)
        if qrz_grid:
            print(f"{prefix}Found grid {qrz_grid} via QRZ for {callsign}")
            return qrz_grid

        print(f"{prefix}QRZ lookup failed, using fallback grid")
        return fallback_grid if fallback_grid else ""

    def _insert_message_data(
        self,
        rig_name: str,
        table: str,
        data: dict,
        id_field: str,
        msg_type: str,
        from_callsign: str,
        extra_info: str = ""
    ) -> str:
        """
        Generic database insert with standardized error handling.

        Args:
            rig_name: Rig identifier for logging
            table: Database table name
            data: Dict of column_name: value pairs
            id_field: Name of the ID field for duplicate detection
            msg_type: Return value on success (e.g., "statrep", "message")
            from_callsign: Sender callsign for logging
            extra_info: Optional extra info for success message (e.g., " (FORWARDED)")

        Returns:
            msg_type on success, empty string on failure
        """
        try:
            conn = sqlite3.connect(DATABASE_FILE, timeout=10)
            cursor = conn.cursor()

            # Build INSERT statement
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?" for _ in data])
            query = f"INSERT INTO {table} ({columns}) VALUES({placeholders})"

            cursor.execute(query, tuple(data.values()))
            conn.commit()

            print(f"{ConsoleColors.SUCCESS}[{rig_name}] Added {msg_type.upper()}{extra_info} from: {from_callsign}{ConsoleColors.RESET}")
            conn.close()
            return msg_type

        except sqlite3.IntegrityError as e:
            if id_field in str(e) or "UNIQUE" in str(e):
                id_val = data.get(id_field, "unknown")
                print(f"{ConsoleColors.SUCCESS}[{rig_name}] Skipping {msg_type} from {from_callsign} — already received (ID: {id_val}){ConsoleColors.RESET}")
            else:
                print(f"{ConsoleColors.WARNING}[{rig_name}] WARNING: Database constraint violation: {e}{ConsoleColors.RESET}")
        except sqlite3.Error as e:
            print(f"{ConsoleColors.ERROR}[{rig_name}] ERROR: {msg_type.capitalize()} database insert failed for {from_callsign}: {e}{ConsoleColors.RESET}")
        finally:
            if 'conn' in locals():
                conn.close()

        return ""

    def _process_fcode_statrep(
        self,
        rig_name: str,
        value: str,
        from_callsign: str,
        target: str,
        grid: str,
        freq: int,
        snr: int,
        utc: str,
        format_code: str,  # "F!304" or "F!301"
        source: int = 1  # 1=Radio (TCP), 2=Internet (backbone)
    ) -> str:
        """
        Process F!304 or F!301 STATREP format messages.

        Args:
            format_code: "F!304" (8 digits) or "F!301" (9 digits)

        Returns:
            "statrep" on success, empty string on failure
        """
        # Determine pattern based on format
        digit_count = 8 if format_code == "F!304" else 9
        pattern = rf'{format_code}\s+(\d{{{digit_count}}})\s*(.*?)(?:>])?$'

        match = re.search(pattern, value, re.IGNORECASE)
        if not match:
            return ""

        digits = match.group(1)
        remainder = match.group(2)

        # Map digits to fields
        if format_code == "F!304":
            field_map = map_f304_digits_to_fields(digits)
            scope = "My Location"
            status_digits = digits
        else:  # F!301
            field_map = map_f301_digits_to_fields(digits)
            scope = field_map['scope']
            status_digits = digits[1:]  # Skip scope digit

        # F!304/F!301 messages don't contain grid data — resolve via callsign lookup
        # _lookup_grid_for_callsign checks qrz_cache first, then QRZ API (caches result)
        fcode_grid = self._lookup_grid_for_callsign(from_callsign) or ""
        grid_found = bool(fcode_grid and len(fcode_grid) >= 4)

        # Build comments
        comment_parts = [format_code] + field_map['comment_parts']
        comments = ", ".join(comment_parts)
        if remainder.strip():
            comments += f" - {remainder.strip()}"
        comments = sanitize_ascii(comments)

        # Calculate status
        fcode_status = calculate_f304_status(status_digits, grid_found)

        # Generate ID and extract date
        date_only, srid = parse_message_datetime(utc)

        # Default group
        fcode_group = target if target else "@ALL"

        # Build data dict for insertion
        data = {
            'datetime': utc,
            'date': date_only,
            'freq': freq,
            'db': snr,
            'source': source,
            'sr_id': srid,
            'from_callsign': from_callsign,
            'target': fcode_group,
            'grid': fcode_grid,
            'scope': scope,
            'map': fcode_status,
            'power': field_map['power'],
            'water': field_map['water'],
            'med': "4",
            'telecom': field_map['telecom'],
            'travel': "4",
            'internet': field_map['internet'],
            'fuel': "4",
            'food': "4",
            'crime': "4",
            'civil': "4",
            'political': "4",
            'comments': comments
        }

        return self._insert_message_data(
            rig_name, "statrep", data, "sr_id", "statrep", from_callsign
        )

    def _handle_backbone_data_messages(self, content: str) -> bool:
        """Handle backbone server data messages with ID prefixes.

        Expected format (one or more lines):
        113:  2026-02-06 18:32:32    14118000    0    30    N0DDK: @MAGNET ,EM83CV,3,T31,321311111331,GA,{&%}
        114:  2026-02-06 18:35:10    14118000    0    30    W1ABC: @ALL LRT ,1,Test Alert,This is a test,{%%}

        Format per line:
        ID: date time freq_hz unused(0) snr callsign: message_data

        Args:
            content: The backbone response content with ID-prefixed messages

        Returns:
            True if at least one message was processed, False otherwise
        """
        import re
        from datetime import datetime, timezone
        from id_utils import generate_time_based_id
        from typing import Optional

        try:
            lines = content.split('\n')
            processed_count = 0
            last_data_id = 0
            data_types_processed = set()  # Track which data types were added

            # Process each line that starts with an ID
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Check if line starts with a number followed by colon
                id_match = re.match(r'^(\d+):\s*(.+)$', line)
                if not id_match:
                    continue

                data_id = int(id_match.group(1))
                data = id_match.group(2).strip()

                # Track the highest ID we've seen
                if data_id > last_data_id:
                    last_data_id = data_id

                # Parse the data line: date time freq_hz unused snr callsign: message
                # Example: 2026-02-06 18:32:32    14118000    0    30    N0DDK: @MAGNET ,EM83CV,3,T31,321311111331,GA,{&%}
                # Fields: date(0) time(1) freq_hz(2) unused/0(3) snr/db(4) callsign:message(5)
                parts = data.split(None, 5)  # Split on whitespace, max 6 parts
                if len(parts) < 6:
                    print(f"Skipping malformed data line (ID {data_id}): insufficient fields")
                    continue

                try:
                    utc_date = parts[0]  # YYYY-MM-DD
                    utc_time = parts[1]  # HH:MM:SS
                    utc = f"{utc_date} {utc_time}"
                    freq = int(parts[2])  # Frequency in Hz
                    # parts[3] is unknown/unused (always 0)
                    db = int(parts[4])  # SNR in dB
                    message_part = parts[5]  # callsign: message_data

                    # Split callsign from message
                    if ':' not in message_part:
                        print(f"Skipping malformed message (ID {data_id}): no callsign separator")
                        continue

                    callsign_and_msg = message_part.split(':', 1)
                    from_callsign = callsign_and_msg[0].strip()
                    message_value = message_part  # Keep full message with sender prefix for consistent parsing

                    # Extract target group from message if present
                    target = ""
                    target_match = re.search(r'(@[A-Z0-9]+)', message_value, re.IGNORECASE)
                    if target_match:
                        target = target_match.group(1).upper()

                    # Preprocess message value
                    message_value = self._preprocess_message_value(message_value, from_callsign)

                    # Parse using unified parser (source=2 for Internet)
                    msg_type, _ = self._parse_commstat_message(
                        "BACKBONE", from_callsign, message_value, target, "", freq, db, utc, source=2
                    )

                    if msg_type:
                        processed_count += 1
                        data_types_processed.add(msg_type)

                except Exception as e:
                    print(f"Error parsing data line (ID {data_id}): {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            # Update data_id in controls table if we processed any messages
            if last_data_id > 0:
                try:
                    conn = sqlite3.connect(DATABASE_FILE, timeout=10)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE controls SET data_id = ? WHERE id = 1", (last_data_id,))
                    conn.commit()
                    conn.close()
                    print(f"Updated data_id to {last_data_id} in controls table")
                except sqlite3.Error as e:
                    print(f"Warning: Failed to update data_id in controls table: {e}")

            # Trigger UI refresh for processed data types (on main thread)
            if data_types_processed:
                QtCore.QMetaObject.invokeMethod(
                    self, "_refresh_backbone_data",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(set, data_types_processed)
                )

            return processed_count > 0

        except Exception as e:
            print(f"Error handling backbone data messages: {e}")
            import traceback
            traceback.print_exc()
            return False

    @QtCore.pyqtSlot(set)
    def _refresh_backbone_data(self, data_types: set) -> None:
        """Refresh UI for data received from backbone server (called from main thread).

        Args:
            data_types: Set of data types to refresh ('statrep', 'alert', 'message')
        """
        if 'statrep' in data_types:
            self._load_statrep_data()
            self._save_map_position(callback=self._load_map)

        if 'message' in data_types:
            self._load_message_data()

        if 'alert' in data_types:
            # Alerts are shown in the live feed, so refresh it
            self._load_live_feed()

    @QtCore.pyqtSlot(int)
    @QtCore.pyqtSlot(int)
    def _show_program_update_notification(self, new_build: int) -> None:
        """Show notification prompting user to restart (called from main thread)."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Update Available",
            f"CommStat build {new_build} has been downloaded.\n\n"
            f"Please close the application to install the update.\n\n"
            f"Close CommStat now?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes
        )

        if reply == QtWidgets.QMessageBox.Yes:
            # Close the application gracefully - this triggers closeEvent() which
            # disconnects TCP connections and saves state
            # commstat.py will apply the update on next launch
            self.close()

    def _debug(self, message: str) -> None:
        """Print debug message if debug mode is enabled."""
        if self.debug_mode:
            print(f"[Backbone] {message}")

    def _load_slideshow_images(self) -> None:
        """Load images with priority: my_images > images > 00-default.png."""
        self.slideshow_items = []
        self.slideshow_index = 0
        valid_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')

        # Priority 1: Check my_images folder
        my_images_folder = os.path.join(os.getcwd(), "my_images")
        if os.path.isdir(my_images_folder):
            files = sorted(os.listdir(my_images_folder))
            for filename in files:
                if filename.lower().endswith(valid_extensions):
                    image_path = os.path.join(my_images_folder, filename)
                    self.slideshow_items.append(image_path)

        if self.slideshow_items:
            return

        # Priority 2: Check images folder
        images_folder = os.path.join(os.getcwd(), "images")
        if os.path.isdir(images_folder):
            files = sorted(os.listdir(images_folder))
            for filename in files:
                if filename.lower().endswith(valid_extensions):
                    image_path = os.path.join(images_folder, filename)
                    self.slideshow_items.append(image_path)

        if self.slideshow_items:
            return

        # Priority 3: Use default image
        default_image = os.path.join(os.getcwd(), "00-default.png")
        if os.path.isfile(default_image):
            self.slideshow_items.append(default_image)

    def _start_slideshow(self) -> None:
        """Start the image slideshow."""
        self._load_slideshow_images()
        if self.slideshow_items:
            self._show_current_image()
            self.slideshow_timer.start()
        else:
            self.map_disabled_label.setPixmap(QtGui.QPixmap())
            self.map_disabled_label.setText("Map Disabled")

    def _stop_slideshow(self) -> None:
        """Stop the image slideshow."""
        self.slideshow_timer.stop()

    def _show_current_image(self) -> None:
        """Display the current slideshow image."""
        if not self.slideshow_items:
            return

        image_path = self.slideshow_items[self.slideshow_index]
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
        """Advance to the next image in the slideshow."""
        if not self.slideshow_items:
            return

        self.slideshow_index = (self.slideshow_index + 1) % len(self.slideshow_items)
        self._show_current_image()

    def _check_backbone_content_async(self) -> None:
        """Background thread to check backbone for updates."""
        try:
            content = self._fetch_backbone_content()
            if not content:
                return

            self._backbone_fail_count = 0

            if content.strip() == '1':
                return

            # Check if server returns "0"
            if content.strip() == '0':
                print("Backbone server reply = 0")
                return
            content_stripped = content.strip()

            if content_stripped.startswith('db_update'):
                self._handle_db_update(content_stripped)
                return
            elif content_stripped.startswith('program_update'):
                self._handle_program_update(content_stripped)
                return

            if re.search(r'^\d+:\s+\d{4}-\d{2}-\d{2}', content_stripped, re.MULTILINE):
                self._handle_backbone_data_messages(content_stripped)

        except Exception as e:
            self._backbone_fail_count += 1
            self._debug(f"Failed ({self._backbone_fail_count}/{self._backbone_max_failures}): {e}")
            if self._backbone_fail_count >= self._backbone_max_failures:
                self.backbone_timer.stop()
                self._debug(f"Stopped after {self._backbone_max_failures} consecutive failures")

    @QtCore.pyqtSlot()
    def _reload_slideshow(self) -> None:
        """Reload the slideshow."""
        self._load_slideshow_images()
        if self.slideshow_items:
            self.slideshow_index = 0
            self._show_current_image()
        else:
            self.map_disabled_label.setPixmap(QtGui.QPixmap())
            self.map_disabled_label.setText("Map Disabled")

    def _setup_live_feed(self) -> None:
        """Create the live feed text area."""
        # Feed text area
        self.feed_text = QtWidgets.QPlainTextEdit(self.central_widget)
        self.feed_text.setObjectName("feedText")
        mono_font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        mono_font.setPointSize(10)
        self.feed_text.setFont(mono_font)
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
            # Build startup messages for missing configuration
            messages = []
            messages.append("No JS8Call connectors configured.\n")
            messages.append("Use Menu > JS8 CONNECTORS to add a connection.")

            # Check for groups
            if not self.db.get_all_groups():
                messages.append("\n\nNo groups configured.\n")
                messages.append("Use Menu > Groups > Manage Groups to add a group.")

            self.feed_text.setPlainText(''.join(messages))
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
        self.message_table.setColumnCount(7)
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
                font-size: 10pt;
                padding: 4px;
            }}
        """)

        # Set headers
        self.message_table.setHorizontalHeaderLabels([
            "", "Date Time", "Freq", "From", "To", "ID", "Message"
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
                callsign = row[3]  # from_callsign
                srid = row[5]      # sr_id
                grid = row[6]      # grid
                status = str(row[8])  # map (status)

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
        sr_id = self.statrep_table.item(row, 5)  # Column 5 is the ID
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

        # Backbone check timer - runs every 3 minutes, starts 30 seconds after launch
        self._backbone_fail_count = 0
        self._backbone_max_failures = 20
        self.backbone_timer = QTimer(self)
        self.backbone_timer.timeout.connect(self._check_backbone)
        if self._internet_available:
            # Delay first heartbeat by 30 seconds, then start timer for subsequent heartbeats
            def start_backbone_heartbeat():
                self._check_backbone()  # Send first heartbeat immediately
                self.backbone_timer.start(180000)  # Then start 3 minute interval timer
            QTimer.singleShot(30000, start_backbone_heartbeat)

        # News ticker animation timer
        self.newsfeed_timer = QTimer(self)
        self.newsfeed_timer.timeout.connect(self._tick_newsfeed)
        self._newsfeed_frame = 0
        self._newsfeed_phase = 0  # 0 = type-on, 1 = scroll-off
        self._scroll_start = 0.0

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
        if self.config.get_selected_rss_feed() == "Disable":
            self.newsfeed_label.setText("      +++  News Feed Disabled  +++")
        elif self._internet_available:
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
        connected = self.tcp_pool.get_connected_rig_names()

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

    def _tick_newsfeed(self) -> None:
        """Timer-driven tick for news feed animation."""
        text = self.newsfeed_text
        visible = self.newsfeed_chars

        if self._newsfeed_phase == 0:
            # Type-on: reveal characters one at a time
            frame = self._newsfeed_frame
            self.newsfeed_label.setText(text[0:frame])
            self._newsfeed_frame += 1
            if self._newsfeed_frame >= visible:
                # Window is full — pause before scrolling
                self.newsfeed_timer.stop()
                QTimer.singleShot(NEWSFEED_PAUSE_MS, self._start_scroll_phase)
        else:
            # Scroll-off: wall-clock-based so duration is accurate on Windows
            elapsed = time.monotonic() - self._scroll_start
            progress = min(1.0, elapsed / (NEWSFEED_SCROLL_DURATION_MS / 1000.0))
            scroll_steps = len(text) - visible
            offset = int(progress * scroll_steps)
            frame = visible + offset
            self.newsfeed_label.setText(text[frame - visible:frame])
            if progress >= 1.0:
                self.newsfeed_timer.stop()
                self._next_headline()

    def _start_scroll_phase(self) -> None:
        """Begin the scroll-off phase after the pause."""
        self._newsfeed_phase = 1
        self._scroll_start = time.monotonic()
        self.newsfeed_timer.start(16)  # ~60 fps; position derived from wall-clock time

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
        feed_name = self.config.get_selected_rss_feed()
        if self._internet_available and feed_name != "Disable":
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

            # Calculate how many characters fit in the ticker width.
            # averageCharWidth() overestimates for typical ASCII news text because
            # it averages across all Unicode glyphs. Measure a representative
            # lowercase+space sample instead for a more accurate fit.
            fm = self.newsfeed_label.fontMetrics()
            sample = 'abcdefghijklmnopqrstuvwxyz '
            avg_char_px = fm.horizontalAdvance(sample) / len(sample)
            self.newsfeed_chars = int(self.newsfeed_label.width() / avg_char_px)

            # Add padding spaces
            padding = ' ' * self.newsfeed_chars
            self.newsfeed_text = ticker_text + "      +++" + padding

            # Setup and start animation
            self._newsfeed_frame = 0
            self._newsfeed_phase = 0
            self.newsfeed_timer.start(NEWSFEED_TYPE_INTERVAL_MS)
        except (IndexError, TypeError) as e:
            print(f"Error displaying headline: {e}")
            self.newsfeed_label.setText("  News feed error")

    def _on_feed_changed(self, feed_name: str) -> None:
        """Handle feed selection change."""
        self.config.set_selected_rss_feed(feed_name)
        self.rss_fetcher.clear_cache()
        self.headlines = []
        self.headline_index = 0
        self.newsfeed_timer.stop()
        if feed_name == "Disable":
            self.newsfeed_label.setText("      +++  News Feed Disabled  +++")
        elif self._internet_available:
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
        dialog = StatRepDialog(self.tcp_pool, self.connector_manager, self, backbone_debug=self.backbone_debug)
        dialog.exec_()

    def _on_send_message(self) -> None:
        """Open Send Message window."""
        dialog = QtWidgets.QDialog(self)
        dialog.ui = Ui_FormMessage(self.tcp_pool, self.connector_manager, self._load_message_data)
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

        # Get abbreviations and normalization setting for text processing
        apply_normalization = self.config.get_apply_text_normalization()
        abbreviations = self.db.get_abbreviations() if apply_normalization else None

        for row_num, row_data in enumerate(data):
            table.insertRow(row_num)

            # Check if this row should be bold (direct message, no @ symbol)
            bold_row = False
            if is_message_table and len(row_data) > 4:
                to_value = str(row_data[4]) if row_data[4] is not None else ""
                bold_row = to_value and not to_value.startswith("@")

            for col_num, value in enumerate(row_data):
                display_value = str(value) if value is not None else ""

                # Apply text normalization to message/comment fields only if enabled
                if apply_normalization and display_value:
                    # For statrep table: col 19=comments only
                    # For message table: col 5=message only
                    if is_statrep_table and col_num == 20:
                        display_value = smart_title_case(display_value, abbreviations, apply_normalization)
                    elif is_message_table and col_num == 6:
                        display_value = smart_title_case(display_value, abbreviations, apply_normalization)

                # Handle SNR (db) column (first column)
                if (is_statrep_table or is_message_table) and col_num == 0:
                    display_value = ""
                    item = QTableWidgetItem(display_value)
                    try:
                        # Check if source = 2 (Internet source)
                        source_value = None
                        if is_statrep_table and len(row_data) > 21:
                            source_value = int(row_data[21]) if row_data[21] is not None else 0
                        elif is_message_table and len(row_data) > 7:
                            source_value = int(row_data[7]) if row_data[7] is not None else 0

                        if source_value == 2:
                            item.setToolTip("   Internet")
                            color = QColor("#9400ff")
                            item.setBackground(color)
                            table.setItem(row_num, col_num, item)
                            continue

                        # Default SNR-based coloring
                        db_value = int(value) if value is not None else 0
                        item.setToolTip(f"   RF SNR {db_value}")
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
                utc_dt = datetime.fromtimestamp(utc_ms / 1000, tz=timezone.utc)
                utc_str = utc_dt.strftime("%Y-%m-%d   %H:%M:%S")
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

    def _generate_time_based_srid(self, utc_datetime: Optional[str] = None) -> str:
        """
        Generate a time-based SRid from UTC datetime string.

        Args:
            utc_datetime: Optional UTC datetime string in format "YYYY-MM-DD   HH:MM:SS"
                         If None, uses current UTC time.

        Returns:
            3-character time-based ID (e.g., "A12", "Q47")
        """
        from id_utils import generate_time_based_id
        from datetime import datetime, timezone

        if utc_datetime:
            # Parse datetime string (format: "YYYY-MM-DD   HH:MM:SS")
            dt_str = utc_datetime.replace("   ", " ").strip()
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return generate_time_based_id(dt)
        else:
            return generate_time_based_id()

    def _preprocess_message_value(self, value: str, from_call: str) -> str:
        """
        Preprocess message value before parsing.

        Applies:
        1. Duplicate callsign removal (JS8Call bug fix)
        2. Slash suffix stripping from message callsign

        Args:
            value: Raw message text
            from_call: Sender callsign (may include suffix)

        Returns:
            Cleaned message value
        """
        import re

        # Strip duplicate callsign (JS8Call bug: "W8APP: W8APP: @GROUP" → "W8APP: @GROUP")
        value = strip_duplicate_callsign(value, from_call)

        # Strip slash suffix from callsign in message (W3BFO/P: → W3BFO:)
        value = re.sub(r'^(\w+)/\w+:', r'\1:', value)

        # Strip non-ASCII characters (e.g., JS8Call EOL diamond ♦) so the
        # backbone regex can correctly match and discard the {^%} terminator
        value = re.sub(r'[^ -~]', '', value).strip()

        return value

    def _parse_standard_statrep(
        self,
        rig_name: str,
        message_value: str,
        from_callsign: str,
        target: str,
        grid: str,
        freq: int,
        snr: int,
        utc: str,
        source: int
    ) -> tuple:
        """
        Parse standard STATREP message format.

        Format: ,GRID,PREC,SRID,SRCODE,COMMENTS,{&%}
        Forwarded: ,GRID,PREC,SRID,SRCODE,COMMENTS,ORIG_CALL,{F%}

        Args:
            rig_name: Name of the rig/source
            message_value: Message text
            from_callsign: Sender callsign (base callsign without suffix)
            target: Target @GROUP or callsign
            grid: Grid square from TCP params or empty for backbone
            freq: Frequency in Hz
            snr: Signal-to-noise ratio in dB
            utc: UTC timestamp string "YYYY-MM-DD HH:MM:SS"
            source: 1=Radio (TCP), 2=Internet (backbone)

        Returns:
            (message_type, None) where message_type is "statrep" or ""
        """
        import re

        is_forwarded = "{F%}" in message_value
        marker = "{F%}" if is_forwarded else "{&%}"

        # Extract statrep data before marker
        match = re.search(r',(.+?)' + re.escape(marker), message_value)
        if not match:
            return ("", None)

        fields = match.group(1).split(",")

        # Need at least 4 fields: GRID, PREC, SRID, SRCODE
        if len(fields) < 4:
            return ("", None)

        statrep_grid = fields[0].strip()
        prec_num = fields[1].strip()
        sr_id = fields[2].strip()
        srcode = fields[3].strip()

        # Expand "+" shorthand
        srcode = expand_plus_shorthand(srcode)

        # Validate SRCODE: must be at least 12 numeric digits
        if len(srcode) < 12 or not srcode[:12].isdigit():
            print(f"{ConsoleColors.WARNING}[{rig_name}] WARNING: Invalid STATREP SRCODE from {from_callsign} - must be 12 numeric digits, got: {srcode}{ConsoleColors.RESET}")
            return ("", None)

        # Validate and get grid (use QRZ if invalid/missing)
        statrep_grid = self._resolve_grid(rig_name, statrep_grid, from_callsign, grid, "STATREP")

        # Handle forwarded statrep
        if is_forwarded and len(fields) > 4:
            # Remove empty trailing fields
            while fields and not fields[-1].strip():
                fields.pop()
            # Last field is origin callsign
            origin_call = fields[-1].strip() if len(fields) > 4 else ""
            # Comments are between SRCODE and origin
            comments_raw = ",".join(fields[4:-1]).strip() if len(fields) > 5 else ""
            comments = format_statrep_comments(comments_raw, self.db.get_abbreviations(), self.config.get_apply_text_normalization())
            # Append forwarded info
            if origin_call:
                fwd_suffix = f" FORWARDED BY: {from_callsign}"
                comments = (comments + fwd_suffix) if comments else fwd_suffix.lstrip()
                # Use origin callsign as sender
                from_callsign = origin_call
        else:
            # Standard statrep comments
            comments_raw = ",".join([f for f in fields[4:] if f.strip()]).strip() if len(fields) > 4 else ""
            comments = format_statrep_comments(comments_raw, self.db.get_abbreviations(), self.config.get_apply_text_normalization())

        # Map scope
        SCOPE_MAP = {
            "1": "My Location",
            "2": "My Community",
            "3": "My County",
            "4": "My Region",
            "5": "Other Location"
        }
        scope = SCOPE_MAP.get(prec_num, "Unknown")

        # Insert statrep
        sr_fields = list(srcode[:12])  # Use only first 12 digits
        date_only, _ = parse_message_datetime(utc)

        # Build data dict for insertion
        data = {
            'datetime': utc,
            'date': date_only,
            'freq': freq,
            'db': snr,
            'source': source,
            'sr_id': sr_id,
            'from_callsign': from_callsign,
            'target': target,
            'grid': statrep_grid,
            'scope': scope,
            'map': sr_fields[0],
            'power': sr_fields[1],
            'water': sr_fields[2],
            'med': sr_fields[3],
            'telecom': sr_fields[4],
            'travel': sr_fields[5],
            'internet': sr_fields[6],
            'fuel': sr_fields[7],
            'food': sr_fields[8],
            'crime': sr_fields[9],
            'civil': sr_fields[10],
            'political': sr_fields[11],
            'comments': comments
        }

        fwd_marker = " (FORWARDED)" if is_forwarded else ""
        result = self._insert_message_data(
            rig_name, "statrep", data, "sr_id", "statrep", from_callsign, fwd_marker
        )
        if result:
            return (result, None)

        return ("", None)

    def _parse_alert(
        self,
        rig_name: str,
        message_value: str,
        from_callsign: str,
        target: str,
        freq: int,
        snr: int,
        utc: str,
        source: int
    ) -> tuple:
        """
        Parse ALERT message format.

        New format: @GROUP ,ALERT_ID,COLOR,TITLE,MESSAGE,{%%}
        Old format: @GROUP ,COLOR,TITLE,MESSAGE,{%%}
        Legacy backbone format: LRT ,COLOR,TITLE,MESSAGE,{%%}

        Args:
            rig_name: Name of the rig/source
            message_value: Message text
            from_callsign: Sender callsign (base callsign without suffix)
            target: Target @GROUP or callsign
            freq: Frequency in Hz
            snr: Signal-to-noise ratio in dB
            utc: UTC timestamp string "YYYY-MM-DD HH:MM:SS"
            source: 1=Radio (TCP), 2=Internet (backbone)

        Returns:
            (message_type, None) where message_type is "alert" or ""
        """
        import re

        # Try standard @GROUP pattern first
        match = re.search(r'(@\w+)\s*,(.+?)\{\%\%\}', message_value)
        if match:
            alert_target = match.group(1).strip()
            fields_str = match.group(2).strip()
        else:
            # Try LRT pattern (legacy backbone format)
            match = re.search(r'LRT\s*,(.+?)\{\%\%\}', message_value)
            if match:
                alert_target = target if target else "@ALL"
                fields_str = match.group(1).strip()
            else:
                return ("", None)

        # Split fields (max 3 splits to preserve commas in message)
        fields = fields_str.split(",", 3)

        # Determine if we have the new format (with alert_id) or old format
        if len(fields) >= 4:
            # New format: ALERT_ID, COLOR, TITLE, MESSAGE
            alert_id = fields[0].strip()
            try:
                alert_color = int(fields[1].strip())
            except ValueError:
                print(f"{ConsoleColors.WARNING}[{rig_name}] WARNING: Invalid alert color in message from {from_callsign}{ConsoleColors.RESET}")
                return ("", None)
            alert_title = sanitize_ascii(fields[2].strip())
            alert_message = sanitize_ascii(fields[3].strip())
            # Extract date for new format
            date_only, _ = parse_message_datetime(utc)
        elif len(fields) >= 3:
            # Old format: COLOR, TITLE, MESSAGE (no alert_id, generate one)
            try:
                alert_color = int(fields[0].strip())
            except ValueError:
                print(f"{ConsoleColors.WARNING}[{rig_name}] WARNING: Invalid alert color in message from {from_callsign}{ConsoleColors.RESET}")
                return ("", None)
            alert_title = sanitize_ascii(fields[1].strip())
            alert_message = sanitize_ascii(fields[2].strip())
            # Generate time-based alert ID for old format
            date_only, alert_id = parse_message_datetime(utc)
        else:
            return ("", None)

        # Filter alerts: only save if directed to one of our active groups
        if alert_target.startswith("@"):
            group_name = alert_target[1:].upper()  # Remove @ and normalize
            active_groups = self.db.get_active_groups()
            if group_name not in active_groups:
                # Skip alerts to inactive or non-member groups
                return ("", None)

        # Build data dict for insertion
        data = {
            'datetime': utc,
            'date': date_only,
            'freq': freq,
            'db': snr,
            'source': source,
            'alert_id': alert_id,
            'from_callsign': from_callsign,
            'target': alert_target,
            'color': alert_color,
            'title': alert_title,
            'message': alert_message
        }

        result = self._insert_message_data(
            rig_name, "alerts", data, "alert_id", "alert", from_callsign
        )
        if result:
            return (result, None)

        return ("", None)

    def _parse_message(
        self,
        rig_name: str,
        message_value: str,
        from_callsign: str,
        target: str,
        freq: int,
        snr: int,
        utc: str,
        source: int
    ) -> tuple:
        """
        Parse MESSAGE format.

        TCP format: CALLSIGN: TARGET MSG message_text
        Backbone format: @GROUP MSG ,MSG_ID,MESSAGE_TEXT,{^%}

        Args:
            rig_name: Name of the rig/source
            message_value: Message text
            from_callsign: Sender callsign (base callsign without suffix)
            target: Target @GROUP or callsign
            freq: Frequency in Hz
            snr: Signal-to-noise ratio in dB
            utc: UTC timestamp string "YYYY-MM-DD HH:MM:SS"
            source: 1=Radio (TCP), 2=Internet (backbone)

        Returns:
            (message_type, None) where message_type is "message" or ""
        """
        import re

        msg_id = None
        msg_target = target
        message_text = None

        # Try to parse backbone format with msg_id: SENDER: @GROUP MSG ,MSG_ID,MESSAGE,{^%}
        backbone_pattern = re.match(r'^(\w+):\s+(@?\w+)\s+MSG\s+,([^,]+),(.+?)(?:\s*,\{[^\}]+\})?$', message_value, re.IGNORECASE)
        if backbone_pattern:
            # Group 1 is sender (already have from from_callsign parameter)
            msg_target = backbone_pattern.group(2).strip()
            msg_id = backbone_pattern.group(3).strip()
            message_text = backbone_pattern.group(4).strip()
        else:
            # Try strict TCP MSG pattern: CALLSIGN: TARGET MSG message_text
            tcp_pattern = re.match(r'^(\w+):\s+(@?\w+)\s+MSG\s+(.+)$', message_value, re.IGNORECASE)
            if tcp_pattern:
                msg_target = tcp_pattern.group(2).strip()
                message_text = tcp_pattern.group(3).strip()
            elif source == 2:
                # Backbone fallback: accept raw message (for older formats)
                message_text = message_value
                msg_target = target if target else ""
            else:
                # TCP: require MSG keyword
                return ("", None)

        # Skip if message is empty
        if not message_text:
            return ("", None)

        # Clean up message text
        message_text = message_text.strip()

        # Extract date and generate msg_id if not extracted from message
        date_only, generated_msg_id = parse_message_datetime(utc)
        if not msg_id:
            msg_id = generated_msg_id

        # Check if message is to a group we're in or to one of our callsigns
        if msg_target.startswith("@"):
            # Group message - check if we're in this group (entire group list, not just active)
            group_name = msg_target[1:].upper()  # Remove @ and normalize
            all_groups = self.db.get_all_groups()
            if group_name not in all_groups:
                # Skip messages to groups we're not in
                return ("", None)
        else:
            # Direct message - check if target is one of our callsigns
            target_call = msg_target.upper()
            user_callsigns = [c.upper() for c in self.rig_callsigns.values() if c]
            if target_call not in user_callsigns:
                # Skip messages not to our callsigns
                return ("", None)

        # Build data dict for insertion
        data = {
            'datetime': utc,
            'date': date_only,
            'freq': freq,
            'db': snr,
            'source': source,
            'msg_id': msg_id,
            'from_callsign': from_callsign,
            'target': msg_target,
            'message': message_text
        }

        result = self._insert_message_data(
            rig_name, "messages", data, "msg_id", "message", from_callsign
        )
        if result:
            return (result, None)

        return ("", None)

    def _parse_commstat_message(
        self,
        rig_name: str,
        from_callsign: str,
        message_value: str,
        target: str,
        grid: str,
        freq: int,
        snr: int,
        utc: str,
        source: int  # 1=Radio, 2=Internet
    ) -> tuple:
        """
        Parse and validate CommStat message in any format.

        Processes messages in priority order:
        1. Standard STATREP ({&%} or {F%})
        2. F!304 STATREP (8-digit format)
        3. F!301 STATREP (9-digit format)
        4. ALERT ({%%})
        5. MESSAGE (contains "MSG" keyword)

        Args:
            rig_name: Name of the rig/source
            from_callsign: Sender callsign (base callsign without suffix)
            message_value: Message text (already preprocessed)
            target: Target @GROUP or callsign
            grid: Grid square from TCP params or empty for backbone
            freq: Frequency in Hz
            snr: Signal-to-noise ratio in dB
            utc: UTC timestamp string "YYYY-MM-DD HH:MM:SS"
            source: 1=Radio (TCP), 2=Internet (backbone)

        Returns:
            (message_type, data_dict) where:
            - message_type: "statrep", "alert", "message", or "" (invalid/skip)
            - data_dict: None (already inserted by sub-parsers)
        """
        # Validate inputs
        if not from_callsign or not message_value:
            return ("", None)

        # Extract base callsign (remove /P, /M suffixes)
        from_callsign = from_callsign.split("/")[0]

        # PRIORITY 1: Standard STATREP ({&%} or {F%})
        if "{&%}" in message_value or "{F%}" in message_value:
            return self._parse_standard_statrep(
                rig_name, message_value, from_callsign, target, grid, freq, snr, utc, source
            )

        # PRIORITY 2: F!304 STATREP
        if "F!304" in message_value:
            result = self._process_fcode_statrep(
                rig_name, message_value, from_callsign, target, grid, freq, snr, utc, "F!304", source
            )
            if result:
                return (result, None)

        # PRIORITY 3: F!301 STATREP
        if "F!301" in message_value:
            result = self._process_fcode_statrep(
                rig_name, message_value, from_callsign, target, grid, freq, snr, utc, "F!301", source
            )
            if result:
                return (result, None)

        # PRIORITY 4: ALERT ({%%})
        if "{%%}" in message_value:
            return self._parse_alert(
                rig_name, message_value, from_callsign, target, freq, snr, utc, source
            )

        # PRIORITY 5: MESSAGE
        return self._parse_message(
            rig_name, message_value, from_callsign, target, freq, snr, utc, source
        )

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
        Process a directed message received via TCP from JS8Call.

        SIMPLIFIED: Only processes messages containing " MSG "
        - Process ALL messages to groups (to_call starts with @)
        - Process messages to user's callsign only

        Args:
            rig_name: Name of the rig that received the message.
            value: The message text content.
            from_call: Sender callsign (from TCP connection).
            to_call: Recipient callsign or @GROUP (from TCP connection).
            grid: Sender's grid square.
            freq: Frequency in Hz.
            snr: Signal-to-noise ratio.
            utc: UTC timestamp string.

        Returns:
            "statrep", "message", "alert", "checkin", or empty string
        """
        # Preprocess message value
        value = self._preprocess_message_value(value, from_call)

        # Extract base callsign
        from_callsign = from_call.split("/")[0] if from_call else ""

        # Extract target group
        target = ""
        if to_call.startswith("@"):
            target = to_call

        # Determine if message is relevant (to group or to our callsign)
        is_to_group = to_call.startswith("@")
        user_callsign = self.get_callsign_for_rig(rig_name)
        is_to_user = to_call == user_callsign if user_callsign else False

        # Only process if to group OR to our callsign
        if not (is_to_group or is_to_user):
            return ""

        # Parse using unified parser (source=1 for Radio)
        msg_type, _ = self._parse_commstat_message(
            rig_name, from_callsign, value, target, grid, freq, snr, utc, source=1
        )

        return msg_type

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

    def _on_user_settings(self) -> None:
        """Open User Settings dialog for editing default callsign, grid, and state."""
        callsign, grid, state = self.db.get_user_settings()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("User Settings")
        dialog.setFixedWidth(400)
        layout = QtWidgets.QVBoxLayout(dialog)

        # Info message
        info_label = QtWidgets.QLabel(
            "These settings are used when CommStat is not connected to JS8Call "
            "or when 'Internet' is selected as the transmit method."
        )
        info_label.setStyleSheet("color: #FF6600; font-weight: bold;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Form fields
        form_layout = QtWidgets.QFormLayout()

        callsign_input = QtWidgets.QLineEdit()
        callsign_input.setText(callsign)
        callsign_input.setMaxLength(12)
        callsign_input.setPlaceholderText("Your callsign")
        callsign_input.textChanged.connect(lambda t: callsign_input.setText(t.upper()) or callsign_input.setCursorPosition(len(t)))
        form_layout.addRow("Callsign:", callsign_input)

        grid_input = QtWidgets.QLineEdit()
        grid_input.setText(grid)
        grid_input.setMaxLength(6)
        grid_input.setPlaceholderText("Grid square (e.g. EM83cv)")
        form_layout.addRow("Grid Square:", grid_input)

        state_input = QtWidgets.QLineEdit()
        state_input.setText(state)
        state_input.setMaxLength(6)
        state_input.setPlaceholderText("State/region code")
        state_input.textChanged.connect(lambda t: state_input.setText(t.upper()) or state_input.setCursorPosition(len(t)))
        form_layout.addRow("State:", state_input)

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
            new_callsign = callsign_input.text().strip().upper()
            raw_grid = grid_input.text().strip()
            if len(raw_grid) == 6:
                new_grid = raw_grid[:2].upper() + raw_grid[2:4] + raw_grid[4:].lower()
            else:
                new_grid = raw_grid.upper()
            new_state = state_input.text().strip().upper()
            if self.db.set_user_settings(new_callsign, new_grid, new_state):
                QtWidgets.QMessageBox.information(
                    self, "User Settings", "Settings saved."
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Failed to save settings."
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

    # Check for backbone debug mode
    backbone_debug = "--debug-mode" in sys.argv

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
            "Please run commstat.py to apply the update and launch the application."
        )
        sys.exit(1)

    app = QtWidgets.QApplication(sys.argv)

    # Set tooltip colors to match Windows (tan background, black text)
    app.setStyleSheet("QToolTip { background-color: #FFFFE1; color: black; border: 1px solid black; }")

    # Load bundled fonts
    from PyQt5.QtGui import QFontDatabase
    import os

    font_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    fonts_to_load = [
        'Roboto-Regular.ttf',
        'Roboto-Bold.ttf',
        'RobotoSlab-Regular.ttf',
        'RobotoSlab-Bold.ttf',
        'RobotoSlab-Black.ttf'
    ]

    for font_file in fonts_to_load:
        font_path = os.path.join(font_dir, font_file)
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                print(f"Warning: Failed to load font {font_file}")
            else:
                families = QFontDatabase.applicationFontFamilies(font_id)
                print(f"Loaded font: {font_file} -> {families}")
        else:
            print(f"Warning: Font file not found: {font_path}")

    # Load configuration
    config = ConfigManager()

    # In demo mode, initialize demo database (but still use traffic.db3 for display)
    if demo_mode:
        from demo_mode import init_demo_database
        init_demo_database()  # Creates demo.db3 if needed

    db = DatabaseManager()

    # Create and show main window
    window = MainWindow(config, db, debug_mode=debug_mode, backbone_debug=backbone_debug, demo_mode=demo_mode, demo_version=demo_version, demo_duration=demo_duration)
    window.show()

    if debug_mode:
        print("Debug mode enabled")
    if backbone_debug:
        print("Backbone debug mode enabled")
    if demo_mode:
        print(f"Demo mode enabled - Version {demo_version} - {demo_duration} second disaster simulation")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
