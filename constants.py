# Copyright (c) 2025, 2026 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.

"""
CommStat UI and application constants.
Import with: from constants import *
"""

from typing import Dict

# =============================================================================
# Application Identity
# =============================================================================

VERSION = "4.1.1"

# When True, dialog handlers reload their module before opening so source
# edits take effect without restarting CommStat. Leave False for releases.
DEV_RELOAD_DIALOGS = True

WINDOW_TITLE = f"CommStat (v{VERSION}) by N0DDK"
WINDOW_SIZE = (1360, 768)
CONFIG_FILE = "config.ini"
ICON_FILE = "radiation-32.png"
DATABASE_FILE = "traffic.db3"

# =============================================================================
# Fonts
# =============================================================================

FONT_ROBOTO   = "Roboto"
FONT_SLAB     = "Roboto Slab"
FONT_MONO     = "Kode Mono"
FONT_SIZE     = 13   # body / inputs
FONT_SIZE_SM  = 13   # hints & tips
FONT_SIZE_LG  = 16   # section / dialog headers

# =============================================================================
# UI Colors
# =============================================================================

# Input / form fields
COLOR_INPUT_BG      = "#FFF5E1"
COLOR_INPUT_TEXT    = "#333333"
COLOR_INPUT_BORDER  = "#cccccc"
COLOR_DISABLED_BG   = "#e9ecef"
COLOR_DISABLED_TEXT = "#999999"

# Semantic button colors
COLOR_BTN_RED   = "#dc3545"
COLOR_BTN_GREEN = "#28a745"
COLOR_BTN_BLUE  = "#007bff"
COLOR_BTN_CYAN  = "#17a2b8"

# Labels
COLOR_ERROR         = "#AA0000"
COLOR_WARNING_LABEL = "#FF6600"

# Misc
COLOR_TOOLTIP_BG = "#FFFFE1"
COLOR_ALERT_BG   = "#333333"
COLOR_ALERT_TEXT = "#ffffff"

# =============================================================================
# Default Color Scheme (used by ConfigManager / config.ini)
# =============================================================================

DEFAULT_COLORS: Dict[str, str] = {
    # Main window
    'program_background': '#A52A2A',       # Maroon
    #'program_background': '#DDDDDD',       # testing black
    'program_foreground': '#FFFFFF',
    'menu_background': '#3050CC',          # Blue
    'menu_foreground': '#FFFFFF',
    'title_bar_background': '#F07800',     # Orange
    'title_bar_foreground': '#FFFFFF',
    #'title_bar_background': '#FFFF00',     # Testing
    #'title_bar_foreground': '#000000',
    # News feed marquee
    'newsfeed_background': '#242424',      # Dark gray
    'newsfeed_foreground': '#00FF00',      # Green text
    # Clock display
    'time_background': '#282864',          # Navy blue
    'time_foreground': '#FFFF00',
    # StatRep condition indicators (traffic light)
    'condition_green': '#28A745',          # Good / normal
    'condition_yellow': '#FFFF77',         # Caution / degraded
    'condition_red': '#DC3534',            # Critical / emergency
    'condition_gray': '#6C757D',           # Unknown / no data
    # Data tables
    'data_background': '#F5EDD7',          # Cream was F8F6F4
    'data_foreground': '#000000',
    # Live feed display
    'feed_background': '#000000',
    'feed_foreground': '#FFFFFF',
    # Module / dialog background
    'module_background': '#E4E4E4',
    'module_foreground': '#242424',
}

# =============================================================================
# Filter / Map / Slideshow
# =============================================================================

DEFAULT_FILTER_START  = "2023-01-01"
MAX_GROUP_NAME_LENGTH = 8
MAP_WIDTH             = 604
MAP_HEIGHT            = 340
SLIDESHOW_INTERVAL    = 5   # minutes between image changes

# =============================================================================
# Timing
# =============================================================================

INTERNET_CHECK_INTERVAL    = 30 * 60 * 1000   # 30 minutes in ms
NEWSFEED_TYPE_INTERVAL_MS  = 60               # ms per character during type-on
NEWSFEED_PAUSE_MS          = 20000            # ms to hold when window is full
NEWSFEED_SCROLL_DURATION_MS = 1000            # total ms for scroll-off phase

# =============================================================================
# StatRep Table Headers
# =============================================================================

STATREP_HEADERS = [
    "", "Date Time", "Freq", "From", "To", "ID", "Grid", "Scope", "Map",
    "Powr", "H2O", "Med", "Comm", "Trvl", "Inet", "Fuel", "Food",
    "Crime", "Civil", "Pol", "Remarks"
]

# =============================================================================
# Console Colors (ANSI)
# =============================================================================

class ConsoleColors:
    """ANSI color codes for console output."""
    SUCCESS = "\033[92m"   # Green
    WARNING = "\033[93m"   # Yellow
    ERROR   = "\033[91m"   # Red
    RESET   = "\033[0m"

# =============================================================================
# Default RSS News Feeds
# =============================================================================

DEFAULT_RSS_FEEDS: Dict[str, str] = {
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "AP News":    "https://feedx.net/rss/ap.xml",
    "BBC World":  "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Fox News":   "https://moxie.foxnews.com/google-publisher/latest.xml",
    "NPR News":   "https://feeds.npr.org/1001/rss.xml",
}
