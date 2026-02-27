"""
Centralized theme manager for CommStat v3.

On Linux: provides system-theme-aware structural colors derived from the
active QPalette so the UI follows the OS dark/light mode automatically.

On macOS and Windows: returns the original hardcoded color values and QSS
strings that were used before the dynamic theme system was introduced.
This preserves the expected look-and-feel on those platforms and avoids
visual bugs caused by platform-specific QPalette quirks.

Usage:
    from theme_manager import theme
    bg = theme.color('window')
    qss = theme.menu_style()
"""

import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor


class ThemeManager:
    """Provides structural UI colors, platform-aware.

    On macOS / Windows (legacy_ui = True):
        All methods return the original hardcoded values from the pre-dynamic-
        theme era.  No QPalette lookups are performed.

    On Linux (legacy_ui = False):
        All methods query the live QPalette so the UI follows the OS/desktop
        theme automatically.

    Structural colors (backgrounds, text, menus, inputs, table chrome) are
    managed here.  Semantic colors (status indicators, alert severity, button
    accents, newsfeed, etc.) are NOT managed here — they stay hardcoded in
    the modules that own them.
    """

    # True on macOS and Windows — use original hardcoded UI
    legacy_ui: bool = sys.platform in ('darwin', 'win32')

    # Default font settings — used as fallback everywhere
    font_family: str = "Arial"
    font_size: int = 12

    # -----------------------------------------------------------------
    # Original hardcoded palette values (macOS / Windows fallback)
    # These mirror what the app used before commit c4f30e7.
    # -----------------------------------------------------------------

    # Structural color mappings derived from the original DEFAULT_COLORS
    # in little_gucci.py plus the hardcoded strings used in all dialogs.
    _LEGACY_COLORS: dict = {
        # program / window chrome
        'window':           '#A52A2A',   # Brown/maroon program background
        'windowtext':       '#FFFFFF',   # White program foreground

        # menu bar
        'menu_background':  '#3050CC',   # Blue menu background
        'menu_foreground':  '#FFFFFF',   # White menu text

        # title / header bar (used for table headers)
        'highlight':        '#F07800',   # Orange title bar background
        'highlightedtext':  '#FFFFFF',   # White title bar text

        # data areas / inputs
        'base':             '#FFF0D4',   # Warm white data background
        'text':             '#000000',   # Black data text

        # misc palette roles (kept close to a typical light palette)
        'alternatebase':    '#EFE0C4',
        'button':           '#D0D0D0',
        'buttontext':       '#000000',
        'tooltipbase':      '#FFFFE1',
        'tooltiptext':      '#000000',
        'mid':              '#A0A0A0',
        'dark':             '#808080',
        'light':            '#FFFFFF',
        'brighttext':       '#FFFFFF',
        'link':             '#0000FF',
        'linkvisited':      '#800080',
        'shadow':           '#000000',
        'midlight':         '#C8C8C8',
        'placeholdertext':  '#808080',

        # Read-only input background (original hardcoded value)
        'readonly_bg':      '#f0f0f0',
    }

    # -----------------------------------------------------------------
    # Palette helpers (Linux / dynamic path only)
    # -----------------------------------------------------------------

    @staticmethod
    def _palette() -> QPalette:
        """Return the application palette (must be called after QApplication exists)."""
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("ThemeManager requires a QApplication instance")
        return app.palette()

    @staticmethod
    def _hex(color: QColor) -> str:
        """Convert a QColor to a hex string like '#rrggbb'."""
        return color.name()

    # -----------------------------------------------------------------
    # Individual palette color accessors
    # -----------------------------------------------------------------

    def color(self, role: str) -> str:
        """Return a hex color string for a named QPalette role.

        On macOS/Windows returns the original hardcoded value.
        On Linux queries the live QPalette.

        Supported role names (case-insensitive):
            window, windowtext, base, alternatebase, text,
            button, buttontext, highlight, highlightedtext,
            tooltipbase, tooltiptext, mid, dark, light,
            brighttext, link, linkvisited, shadow,
            midlight, placeholdertext
        """
        role_lower = role.lower()

        if self.legacy_ui:
            val = self._LEGACY_COLORS.get(role_lower)
            if val is None:
                raise ValueError(f"Unknown palette role: {role!r}")
            return val

        # Linux: live QPalette lookup
        palette = self._palette()
        role_map = {
            'window':           QPalette.Window,
            'windowtext':       QPalette.WindowText,
            'base':             QPalette.Base,
            'alternatebase':    QPalette.AlternateBase,
            'text':             QPalette.Text,
            'button':           QPalette.Button,
            'buttontext':       QPalette.ButtonText,
            'highlight':        QPalette.Highlight,
            'highlightedtext':  QPalette.HighlightedText,
            'tooltipbase':      QPalette.ToolTipBase,
            'tooltiptext':      QPalette.ToolTipText,
            'mid':              QPalette.Mid,
            'dark':             QPalette.Dark,
            'light':            QPalette.Light,
            'brighttext':       QPalette.BrightText,
            'link':             QPalette.Link,
            'linkvisited':      QPalette.LinkVisited,
            'shadow':           QPalette.Shadow,
            'midlight':         QPalette.Midlight,
        }
        # PlaceholderText was added in Qt 5.12
        if hasattr(QPalette, 'PlaceholderText'):
            role_map['placeholdertext'] = QPalette.PlaceholderText

        qt_role = role_map.get(role_lower)
        if qt_role is None:
            raise ValueError(f"Unknown palette role: {role!r}")
        return self._hex(palette.color(qt_role))

    # -----------------------------------------------------------------
    # Structural color dict (replaces DEFAULT_COLORS structural keys)
    # -----------------------------------------------------------------

    def structural_colors(self) -> dict:
        """Return a dict of structural color keys mapped to color values.

        On macOS/Windows: returns the original hardcoded colors.
        On Linux: derives values from the live QPalette.

        Semantic keys (newsfeed_*, condition_*) are NOT included here —
        they stay as-is in DEFAULT_COLORS in little_gucci.py.
        """
        if self.legacy_ui:
            return {
                'program_background':   '#A52A2A',   # Brown/maroon
                'program_foreground':   '#FFFFFF',
                'menu_background':      '#3050CC',   # Blue
                'menu_foreground':      '#FFFFFF',
                'title_bar_background': '#F07800',   # Orange
                'title_bar_foreground': '#FFFFFF',
                'data_background':      '#FFF0D4',   # Warm white
                'data_foreground':      '#000000',
                'feed_background':      '#000000',   # Black
                'feed_foreground':      '#FFFFFF',
                'time_background':      '#282864',   # Navy blue
                'time_foreground':      '#88CCFF',   # Light blue
            }

        # Linux: live QPalette
        return {
            'program_background':    self.color('window'),
            'program_foreground':    self.color('windowtext'),
            'menu_background':       self.color('window'),
            'menu_foreground':       self.color('windowtext'),
            'title_bar_background':  self.color('highlight'),
            'title_bar_foreground':  self.color('highlightedtext'),
            'data_background':       self.color('base'),
            'data_foreground':       self.color('text'),
            'feed_background':       self.color('base'),
            'feed_foreground':       self.color('text'),
            'time_background':       self.color('window'),
            'time_foreground':       self.color('windowtext'),
        }

    # -----------------------------------------------------------------
    # QSS snippet generators
    # -----------------------------------------------------------------

    def menu_style(self) -> str:
        """Return QSS for QMenuBar and QMenu."""
        if self.legacy_ui:
            bg = '#3050CC'   # Original blue menu background
            fg = '#FFFFFF'
            return f"""
            QMenuBar {{
                background-color: {bg};
                color: {fg};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
            }}
            QMenuBar::item:selected {{
                background-color: {bg};
            }}
            QMenu {{
                background-color: {bg};
                color: {fg};
            }}
            QMenu::item:selected {{
                background-color: {bg};
            }}
        """

        # Linux: palette-derived
        bg = self.color('window')
        fg = self.color('windowtext')
        hl = self.color('highlight')
        hl_text = self.color('highlightedtext')
        mid = self.color('mid')
        return f"""
            QMenuBar {{
                background-color: {bg};
                color: {fg};
            }}
            QMenuBar::item {{
                padding: 4px 8px;
                background-color: transparent;
                color: {fg};
            }}
            QMenuBar::item:selected {{
                background-color: {hl};
                color: {hl_text};
            }}
            QMenu {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {mid};
            }}
            QMenu::item {{
                padding: 4px 20px 4px 20px;
                background-color: transparent;
                color: {fg};
            }}
            QMenu::item:selected {{
                background-color: {hl};
                color: {hl_text};
            }}
        """

    def table_style(self) -> str:
        """Return QSS for QTableWidget structural chrome."""
        if self.legacy_ui:
            # Original values: data area uses warm white; header uses orange/white
            data_bg  = '#FFF0D4'
            data_fg  = '#000000'
            title_bg = '#F07800'
            title_fg = '#FFFFFF'
            return f"""
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
            QToolTip {{
                background-color: #FFFFE1;
                color: black;
                border: 1px solid black;
            }}
        """

        # Linux: palette-derived
        base = self.color('base')
        text = self.color('text')
        hl = self.color('highlight')
        hl_text = self.color('highlightedtext')
        return f"""
            QTableWidget {{
                background-color: {base};
                color: {text};
            }}
            QTableWidget QHeaderView::section {{
                background-color: {hl};
                color: {hl_text};
                font-weight: bold;
                padding: 4px;
                border: 1px solid {hl};
            }}
        """

    def header_style(self) -> str:
        """Return QSS for QHeaderView::section."""
        if self.legacy_ui:
            title_bg = '#F07800'
            title_fg = '#FFFFFF'
            return f"""
            QHeaderView::section {{
                background-color: {title_bg};
                color: {title_fg};
                font-weight: bold;
                font-size: 10pt;
                padding: 4px;
            }}
        """

        # Linux: palette-derived
        hl = self.color('highlight')
        hl_text = self.color('highlightedtext')
        return f"""
            QHeaderView::section {{
                background-color: {hl};
                color: {hl_text};
                font-weight: bold;
                font-size: 10pt;
                padding: 4px;
            }}
        """

    def combo_style(self) -> str:
        """Return QSS for QComboBox structural chrome."""
        if self.legacy_ui:
            # Original: menu blue background with white text
            bg = '#3050CC'
            fg = '#FFFFFF'
            return f"""
            QComboBox {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {fg};
                padding: 2px 5px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """

        # Linux: palette-derived
        bg = self.color('window')
        fg = self.color('windowtext')
        border = self.color('mid')
        return f"""
            QComboBox {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                padding: 2px 5px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """

    def combo_list_style(self) -> str:
        """Return QSS for the QListView popup inside a QComboBox."""
        if self.legacy_ui:
            bg = '#3050CC'
            fg = '#FFFFFF'
            return f"""
            QListView {{
                background-color: {bg};
                color: {fg};
                outline: none;
            }}
            QListView::item {{
                background-color: {bg};
                color: {fg};
                padding: 4px;
            }}
        """

        # Linux: palette-derived
        bg = self.color('window')
        fg = self.color('windowtext')
        hl = self.color('highlight')
        hl_text = self.color('highlightedtext')
        return f"""
            QListView {{
                background-color: {bg};
                color: {fg};
                outline: none;
            }}
            QListView::item {{
                background-color: {bg};
                color: {fg};
                padding: 4px;
            }}
            QListView::item:selected {{
                background-color: {hl};
                color: {hl_text};
            }}
        """

    def header_button_style(self) -> str:
        """Return QSS for header-area buttons (e.g. 'Last 20')."""
        if self.legacy_ui:
            # Original: same blue/white as the menu, inverts on hover
            bg = '#3050CC'
            fg = '#FFFFFF'
            return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {fg};
                padding: 2px 5px;
            }}
            QPushButton:hover {{
                background-color: {fg};
                color: {bg};
            }}
        """

        # Linux: palette-derived
        bg = self.color('window')
        fg = self.color('windowtext')
        hl = self.color('highlight')
        hl_text = self.color('highlightedtext')
        border = self.color('mid')
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                padding: 2px 5px;
            }}
            QPushButton:hover {{
                background-color: {hl};
                color: {hl_text};
            }}
        """

    def input_readonly_style(self) -> str:
        """Return QSS for read-only input fields."""
        if self.legacy_ui:
            # Original hardcoded value used in statrep, alert, message, etc.
            return "background-color: #f0f0f0;"

        # Linux: palette-derived
        bg = self.color('base')
        return f"background-color: {bg};"

    def dialog_title_style(self) -> str:
        """Return QSS for dialog title labels (standard margin)."""
        if self.legacy_ui:
            # Original: dark gray text, no dynamic palette needed
            return "color: #333; margin-bottom: 10px;"

        # Linux: palette-derived
        fg = self.color('windowtext')
        return f"color: {fg}; margin-bottom: 10px;"

    def dialog_title_style_compact(self) -> str:
        """Return QSS for dialog title labels (compact margin)."""
        if self.legacy_ui:
            return "color: #333; margin-bottom: 5px;"

        # Linux: palette-derived
        fg = self.color('windowtext')
        return f"color: {fg}; margin-bottom: 5px;"

    @staticmethod
    def button_style(accent_color: str) -> str:
        """Return QSS for an accent-colored button.

        The accent_color is a semantic color passed through unchanged
        (e.g. '#007bff' for primary, '#dc3545' for danger).
        This method is platform-agnostic — accent buttons look the same
        on all platforms.
        """
        return f"""
            QPushButton {{
                background-color: {accent_color};
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """


# Module-level singleton — import as `from theme_manager import theme`
theme = ThemeManager()
