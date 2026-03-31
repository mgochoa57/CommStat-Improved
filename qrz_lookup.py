# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
"""
qrz_lookup.py - QRZ Callsign Lookup Dialogs for CommStat

Three modal dialog views:
  - QRZLookupDialog     : standalone search (Tools → QRZ Lookup)
  - StatRepDetailDialog : detail view when clicking a StatRep row
  - MessageDetailDialog : detail view when clicking a Message row
"""

import io
import os
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Dict, Optional

import folium
import maidenhead as mh
from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QDesktopServices, QFont, QPainter, QPixmap
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from qrz_client import QRZClient, get_qrz_cached, load_qrz_config

DB_PATH = "traffic.db3"

# StatRep status field order: (display label, statrep row index)
STATUS_FIELDS = [
    ("Map",    8),
    ("Power",  9),
    ("Water", 10),
    ("Med",   11),
    ("Comms", 12),
    ("Travel",13),
    ("Inet",  14),
    ("Fuel",  15),
    ("Food",  16),
    ("Crime", 17),
    ("Civil", 18),
    ("Pol",   19),
]

# Status value → (CSS color string, tooltip text)
STATUS_COLORS: Dict[str, tuple] = {
    "1": ("rgb(0, 128, 0)",     "Green: Normal"),
    "2": ("rgb(255, 255, 0)",   "Yellow: Warning"),
    "3": ("rgb(255, 0, 0)",     "Red: Critical"),
    "4": ("rgb(128, 128, 128)", "Gray: Unknown"),
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _normalize_qrz(data: dict) -> dict:
    """Normalize QRZ data to consistent display keys.

    Handles both the raw API response (addr1/addr2/call) and the
    cached DB row (address/city/callsign) transparently.
    """
    return {
        "call":     (data.get("call") or data.get("callsign") or "").upper(),
        "name":     " ".join(x for x in (
                        (data.get("fname") or "").strip(),
                        (data.get("name") or "").strip()
                    ) if x).title() or "",
        "born":     str(data.get("born") or ""),
        "expdate":  str(data.get("expdate") or ""),
        "addr1":    data.get("addr1") or data.get("address") or "",
        "addr2":    data.get("addr2") or data.get("city") or "",
        "state":    data.get("state") or "",
        "zip":      str(data.get("zip") or ""),
        "county":   data.get("county") or "",
        "country":  data.get("country") or "",
        "license":  data.get("class") or "",
        "grid":     data.get("grid") or "",
        "lat":      str(data.get("lat") or ""),
        "lon":      str(data.get("lon") or ""),
        "email":    data.get("email") or "",
        "image":    data.get("image") or "",
        "moddate":  data.get("moddate") or "",
    }


def _make_map_html(lat: float, lon: float, internet_available: bool = True,
                   extra_lat: float = None, extra_lon: float = None) -> str:
    """Generate folium map HTML with one or two marker pins.

    The primary pin (lat/lon) is blue. If extra_lat/extra_lon are provided,
    a red secondary pin is added and the map fits both markers.
    """
    if extra_lat is not None and extra_lon is not None:
        center_lat = (lat + extra_lat) / 2
        center_lon = (lon + extra_lon) / 2
        m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
    else:
        m = folium.Map(location=[lat, lon], zoom_start=4)

    folium.raster_layers.TileLayer(
        tiles="http://localhost:8000/{z}/{x}/{y}.png",
        name="Local Tiles", attr="Local Tiles",
        max_zoom=8, control=False,
    ).add_to(m)
    if internet_available:
        folium.raster_layers.TileLayer(
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            name="OpenStreetMap", attr="OpenStreetMap",
            min_zoom=8, control=False,
        ).add_to(m)

    if extra_lat is not None and extra_lon is not None:
        folium.Marker(location=[lat, lon], icon=folium.Icon(color="red")).add_to(m)
        folium.Marker(location=[extra_lat, extra_lon]).add_to(m)
        m.fit_bounds([[min(lat, extra_lat), min(lon, extra_lon)],
                      [max(lat, extra_lat), max(lon, extra_lon)]])
    else:
        folium.Marker(location=[lat, lon]).add_to(m)

    buf = io.BytesIO()
    m.save(buf, close_file=False)
    html = buf.getvalue().decode()
    html = html.replace(
        "<head>",
        '<head><meta name="referrer" content="no-referrer-when-downgrade">',
        1
    )
    return html


def _btn_style(color: str) -> str:
    return (
        f"QPushButton {{ background-color:{color}; color:white; border:none; "
        f"padding:6px 14px; border-radius:4px; font-weight:bold; font-size:11pt; }}"
        f"QPushButton:hover {{ background-color:{color}; }}"
    )


def _hsep() -> QFrame:
    """Return a styled horizontal separator line."""
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet("color:#cccccc;")
    return sep


# ── Background workers ─────────────────────────────────────────────────────

class _ImageLoader(QThread):
    """Downloads and scales a QRZ profile image in the background."""
    image_loaded = pyqtSignal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                data = resp.read()
            px = QPixmap()
            px.loadFromData(data)
            if not px.isNull():
                target_h = 166 if px.width() < px.height() * 1.6 else 126
                self.image_loaded.emit(px.scaledToHeight(target_h, Qt.SmoothTransformation))
        except Exception:
            pass


def _get_local_callsign() -> str:
    """Read the local station callsign from the controls table."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT callsign FROM controls WHERE id = 1")
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


class _ReadCountThread(QThread):
    """Fetches the delivery read-count from the backbone server."""
    count_ready = pyqtSignal(int)

    def __init__(self, backbone_url: str, callsign: str, global_id: int):
        super().__init__()
        self.backbone_url = backbone_url
        self.callsign = callsign
        self.global_id = global_id

    def run(self) -> None:
        try:
            url = (f"{self.backbone_url}/get-read-count-808585.php"
                   f"?cs={urllib.parse.quote(self.callsign)}&id={self.global_id}")
            with urllib.request.urlopen(url, timeout=10) as resp:
                text = resp.read().decode().strip()
            self.count_ready.emit(int(text))
        except Exception:
            pass


class _QRZThread(QThread):
    """Performs a QRZ callsign lookup in the background."""
    result_ready = pyqtSignal(object)  # dict or None

    def __init__(self, callsign: str, username: Optional[str], password: Optional[str]):
        super().__init__()
        self.callsign = callsign
        self.username = username
        self.password = password

    def run(self) -> None:
        client = QRZClient(self.username, self.password)
        self.result_ready.emit(client.lookup(self.callsign))


# ── Clickable image label ──────────────────────────────────────────────────

class _ClickableImageLabel(QLabel):
    """QLabel that opens a URL in the browser when clicked (if one is set)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._url: str = ""

    def set_url(self, url: str) -> None:
        self._url = url
        self.setCursor(QCursor(Qt.PointingHandCursor) if url else QCursor(Qt.ArrowCursor))

    def mousePressEvent(self, event) -> None:
        if self._url and event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl(self._url))
        else:
            super().mousePressEvent(event)


class _MemoTextEdit(QTextEdit):
    """QTextEdit that emits focus_lost when it loses keyboard focus."""
    focus_lost = pyqtSignal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class _ToggleSwitch(QWidget):
    """iOS-style toggle switch that emits toggled(bool) on state change."""
    toggled = pyqtSignal(bool)

    _W, _H = 50, 26        # track dimensions
    _KNOB   = 22           # knob diameter
    _MARGIN = 2            # gap between knob and track edge

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(self._W, self._H)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        self._checked = checked
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track_color = QColor("#28a745") if self._checked else QColor("#aaaaaa")
        p.setBrush(track_color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, (self._H - 20) // 2, self._W, 20, 10, 10)
        knob_x = self._W - self._KNOB - self._MARGIN if self._checked else self._MARGIN
        knob_y = (self._H - self._KNOB) // 2
        p.setBrush(QColor("white"))
        p.drawEllipse(knob_x, knob_y, self._KNOB, self._KNOB)
        p.end()


# ── Shared QRZ info panel ──────────────────────────────────────────────────

class _QRZInfoSection(QWidget):
    """Three-column QRZ info display used by all three dialogs.

    Left  : section header, callsign, name, address
    Center: license, born, grid, lat/lon, email
    Right : profile image, last modified date
    """

    image_width_ready = pyqtSignal(int)

    def __init__(self, hdr_bg: str = "", hdr_fg: str = "", parent=None):
        super().__init__(parent)
        self._img_loader: Optional[_ImageLoader] = None
        self._hdr_bg = hdr_bg
        self._hdr_fg = hdr_fg
        self._build()

    def _build(self) -> None:
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(10, 8, 10, 8)
        self._main_layout.setSpacing(0)

        outer = QHBoxLayout()
        outer.setSpacing(24)
        self._main_layout.addLayout(outer)

        # ── Columns 1 & 2 (2/3 total) via QGridLayout for row alignment ─
        self._grid = QGridLayout()
        grid = self._grid
        grid.setSpacing(2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        hdr = QLabel("QRZ API Results")
        hdr.setFont(QFont("Arial", 16, QFont.Bold))
        hdr.setStyleSheet(
            f"QLabel {{ background-color: {self._hdr_bg}; color: {self._hdr_fg}; padding-top: 9px; padding-bottom: 9px; }}"
            if self._hdr_bg else ""
        )
        hdr.setAlignment(Qt.AlignCenter)
        self.lbl_call    = QLabel(); self.lbl_call.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_name    = QLabel(); self.lbl_name.setFont(QFont("Arial", 12, QFont.Bold))
        self.lbl_addr1   = QLabel(); self.lbl_addr1.setFont(QFont("Arial", 11))
        self.lbl_addr2   = QLabel(); self.lbl_addr2.setFont(QFont("Arial", 11))
        self.lbl_county  = QLabel(); self.lbl_county.setFont(QFont("Arial", 11))
        self.lbl_country = QLabel(); self.lbl_country.setFont(QFont("Arial", 11))
        self.lbl_license = QLabel(); self.lbl_license.setFont(QFont("Arial", 11))
        self.lbl_born    = QLabel(); self.lbl_born.setFont(QFont("Arial", 11))
        self.lbl_grid    = QLabel(); self.lbl_grid.setFont(QFont("Arial", 11))
        self.lbl_lat     = QLabel(); self.lbl_lat.setFont(QFont("Arial", 11))
        self.lbl_lon     = QLabel(); self.lbl_lon.setFont(QFont("Arial", 11))
        self.lbl_email   = QLabel(); self.lbl_email.setFont(QFont("Arial", 11))
        self.lbl_email.setOpenExternalLinks(True)
        self.lbl_qrz_profile = QLabel(); self.lbl_qrz_profile.setFont(QFont("Arial", 11))
        self.lbl_qrz_profile.setOpenExternalLinks(True)

        grid.addWidget(hdr,                   0, 0, 1, 2)  # header spans both columns
        grid.addWidget(self.lbl_call,         1, 0)
        grid.addWidget(self.lbl_name,         2, 0)
        grid.addWidget(self.lbl_license,      2, 1)
        grid.addWidget(self.lbl_addr1,        3, 0)
        grid.addWidget(self.lbl_born,         3, 1)
        grid.addWidget(self.lbl_addr2,        4, 0)
        grid.addWidget(self.lbl_grid,         4, 1)
        grid.addWidget(self.lbl_county,       5, 0)
        grid.addWidget(self.lbl_lat,          5, 1)
        grid.addWidget(self.lbl_country,      6, 0)
        grid.addWidget(self.lbl_lon,          6, 1)
        grid.addWidget(self.lbl_qrz_profile,  7, 0)
        grid.addWidget(self.lbl_email,        7, 1)
        grid.setRowStretch(8, 1)
        outer.addLayout(grid, 2)

        # ── Column 3 (1/3): image + photo status + moddate ───────────────
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop | Qt.AlignRight)
        right.setSpacing(4)
        self.lbl_image = _ClickableImageLabel()
        self.lbl_image.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.lbl_image.setStyleSheet("border:none; padding:0px;")
        self.lbl_moddate = QLabel()
        self.lbl_moddate.setFont(QFont("Arial", 10))
        self.lbl_moddate.setAlignment(Qt.AlignRight)
        moddate_row = QHBoxLayout()
        moddate_row.addStretch()
        moddate_row.addWidget(self.lbl_moddate)
        right.addWidget(self.lbl_image)
        right.addLayout(moddate_row)
        right.addStretch()
        outer.addLayout(right, 1)

    def add_statrep_rows(self, memo_widget=None) -> None:
        """Add separator + StatRep fields below the QRZ section, spanning all three columns."""
        # Empty spacer row at the bottom of the QRZ grid (below URL row)
        self._grid.setRowStretch(8, 0)
        spacer = QLabel("")
        self._grid.addWidget(spacer, 8, 0)

        # Full-width separator spanning all three visual columns
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        self._main_layout.addWidget(sep)
        self._main_layout.addSpacing(8)

        # StatRep rows in same 2/3 + 1/3 proportions as the QRZ section above
        sr_row = QHBoxLayout()
        sr_row.setSpacing(24)

        sr_grid = QGridLayout()
        sr_grid.setSpacing(2)
        sr_grid.setColumnStretch(0, 1)
        sr_grid.setColumnStretch(1, 1)

        sr_hdr = QLabel("Status Report Details")
        sr_hdr.setFont(QFont("Arial", 13, QFont.Bold))
        sr_grid.addWidget(sr_hdr, 0, 0)

        self.lbl_sr_source    = QLabel(); self.lbl_sr_source.setFont(QFont("Arial", 11))
        self.lbl_sr_posted    = QLabel(); self.lbl_sr_posted.setFont(QFont("Arial", 11))
        self.lbl_sr_global_id = QLabel(); self.lbl_sr_global_id.setFont(QFont("Arial", 11))
        self.lbl_sr_group     = QLabel(); self.lbl_sr_group.setFont(QFont("Arial", 11))
        self.lbl_sr_grid      = QLabel(); self.lbl_sr_grid.setFont(QFont("Arial", 11))
        self.lbl_sr_freqid    = QLabel(); self.lbl_sr_freqid.setFont(QFont("Arial", 11))
        self.lbl_sr_delivered = QLabel(); self.lbl_sr_delivered.setFont(QFont("Arial", 11))

        sr_grid.addWidget(self.lbl_sr_source,    0, 1)
        sr_grid.addWidget(self.lbl_sr_posted,    1, 0)
        sr_grid.addWidget(self.lbl_sr_global_id, 1, 1)
        sr_grid.addWidget(self.lbl_sr_group,     2, 0)
        sr_grid.addWidget(self.lbl_sr_grid,      2, 1)
        sr_grid.addWidget(self.lbl_sr_freqid,    3, 0)
        sr_grid.addWidget(self.lbl_sr_delivered, 3, 1)
        sr_grid.setRowStretch(4, 1)

        sr_row.addLayout(sr_grid, 2)   # cols 1 & 2 — matches QRZ grid proportion

        # col 3: memo widget if provided, otherwise empty space
        if memo_widget is not None:
            sr_right = QVBoxLayout()
            sr_right.setSpacing(2)
            memo_lbl = QLabel("Status Report Notes / Memo")
            memo_lbl.setFont(QFont("Arial", 11, QFont.Bold))
            sr_right.addWidget(memo_lbl)
            sr_right.addWidget(memo_widget)
            sr_row.addLayout(sr_right, 1)
        else:
            sr_row.addStretch(1)
        self._main_layout.addLayout(sr_row)
        self._main_layout.addStretch()

    def update_data(self, data: dict) -> None:
        """Populate all labels from raw QRZ data (API or cached format)."""
        d = _normalize_qrz(data)

        self.lbl_call.setText(d["call"])
        self.lbl_name.setText(d["name"])

        self.lbl_addr1.setText(d["addr1"])
        city_state = ", ".join(x for x in (d["addr2"], d["state"]) if x)
        if d["zip"]:
            city_state = (city_state + " " + d["zip"]).strip()
        self.lbl_addr2.setText(city_state)

        self.lbl_county.setText(f"<b>County:</b> {d['county']}" if d["county"] else "")
        self.lbl_country.setText(f"<b>Country:</b> {d['country']}" if d["country"] else "")

        if d["license"] and d["expdate"]:
            self.lbl_license.setText(f"<b>License:</b> {d['license']} (exp: {d['expdate']})")
        elif d["expdate"]:
            self.lbl_license.setText(f"(exp: {d['expdate']})")
        else:
            self.lbl_license.setText("")

        self.lbl_born.setText(f"<b>Born:</b> {d['born']}" if d["born"] else "")
        self.lbl_grid.setText(f"<b>Grid:</b> {d['grid']}" if d["grid"] else "")
        self.lbl_lat.setText(f"<b>Lat:</b> {d['lat']}" if d["lat"] else "")
        self.lbl_lon.setText(f"<b>Lon:</b> {d['lon']}" if d["lon"] else "")

        if d["email"]:
            self.lbl_email.setText(
                f'<b>Email:</b> <a href="mailto:{d["email"]}">{d["email"]}</a>'
            )
        else:
            self.lbl_email.setText("")

        if d["call"]:
            url = f"https://www.qrz.com/db/{d['call']}"
            self.lbl_qrz_profile.setText(
                f'<a href="{url}">{url}</a>'
            )
        else:
            self.lbl_qrz_profile.setText("")

        self.lbl_moddate.setText(
            f"QRZ profile last modified: {d['moddate']}" if d["moddate"] else ""
        )

        self.lbl_image.clear()
        self.lbl_image.set_url("")
        if d["image"]:
            self.lbl_image.set_url(d["image"])
            self._img_loader = _ImageLoader(d["image"])
            self._img_loader.image_loaded.connect(self._on_image_loaded)
            self._img_loader.start()
        else:
            px = QPixmap("little-duck.png")
            if not px.isNull():
                self.lbl_image.setPixmap(px.scaledToHeight(126, Qt.SmoothTransformation))

    def _on_image_loaded(self, px: QPixmap) -> None:
        self.lbl_image.setPixmap(px)
        self.image_width_ready.emit(px.width())

    def clear(self) -> None:
        for w in (self.lbl_call, self.lbl_name, self.lbl_addr1, self.lbl_addr2,
                  self.lbl_county, self.lbl_country, self.lbl_license, self.lbl_born,
                  self.lbl_grid, self.lbl_lat, self.lbl_lon, self.lbl_email,
                  self.lbl_qrz_profile, self.lbl_image, self.lbl_moddate):
            w.clear()


# ── Dialog 1: Standalone QRZ Lookup ───────────────────────────────────────

class QRZLookupDialog(QDialog):
    """Standalone QRZ callsign lookup (Tools → QRZ Lookup)."""

    def __init__(self, panel_background: str = "#f5f5f5",
                 panel_foreground: str = "#333333",
                 program_background: str = "",
                 program_foreground: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._panel_bg = panel_background
        self._panel_fg = panel_foreground
        self._program_bg = program_background
        self._program_fg = program_foreground
        self.setWindowTitle("QRZ Lookup")
        self.setModal(True)
        self.setMinimumSize(750, 320)
        self.resize(820, 380)
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))
        self._thread: Optional[_QRZThread] = None
        self._setup_ui()
        self._check_subscription()

    def _check_subscription(self) -> None:
        is_active, _, _ = load_qrz_config()
        if not is_active:
            QMessageBox.warning(
                self, "QRZ Lookup",
                "QRZ Lookup requires a paid QRZ subscription.\n"
                "Please configure your QRZ credentials in Settings."
            )

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"QDialog {{ background-color:{self._panel_bg}; }}"
            f"QLabel {{ color:{self._panel_fg}; }}"
            "QLineEdit { background-color:white; color:#333; border:1px solid #ccc;"
            " border-radius:4px; padding:4px 8px; font-size:13px; }"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(15, 12, 15, 12)
        main.setSpacing(8)

        row = QHBoxLayout()
        self.cs_edit = QLineEdit()
        self.cs_edit.setPlaceholderText("Enter callsign…")
        self.cs_edit.setMaxLength(12)
        self.cs_edit.returnPressed.connect(self._search)
        self.cs_edit.textChanged.connect(self._force_upper)
        row.addWidget(self.cs_edit)

        self.btn_search = QPushButton("Search")
        self.btn_search.setStyleSheet(_btn_style("#0078d7"))
        self.btn_search.setFixedWidth(90)
        self.btn_search.clicked.connect(self._search)
        row.addWidget(self.btn_search)
        main.addLayout(row)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color:#888; font-size:11px;")
        main.addWidget(self.lbl_status)

        self.qrz_info = _QRZInfoSection(hdr_bg=self._program_bg, hdr_fg=self._program_fg, parent=self)
        self.qrz_info.image_width_ready.connect(self._adjust_for_image_width)
        main.addWidget(self.qrz_info)
        main.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_message_lookup = QPushButton("Message")
        self.btn_message_lookup.setStyleSheet(_btn_style("#0078d7"))
        self.btn_message_lookup.setVisible(False)
        self.btn_message_lookup.clicked.connect(self._on_message_clicked)
        btn_row.addWidget(self.btn_message_lookup)
        main.addLayout(btn_row)

    def _adjust_for_image_width(self, img_width: int) -> None:
        if img_width > 275:
            self.resize(self.width() + (img_width - 275), self.height())

    def _force_upper(self, text: str) -> None:
        if text != text.upper():
            self.cs_edit.blockSignals(True)
            pos = self.cs_edit.cursorPosition()
            self.cs_edit.setText(text.upper())
            self.cs_edit.setCursorPosition(pos)
            self.cs_edit.blockSignals(False)

    def _search(self) -> None:
        cs = self.cs_edit.text().strip().upper()
        if not cs:
            return
        self.lbl_status.setText(f"Looking up {cs}…")
        self.btn_search.setEnabled(False)
        self.qrz_info.clear()
        _, username, password = load_qrz_config()
        self._thread = _QRZThread(cs, username, password)
        self._thread.result_ready.connect(self._on_result)
        self._thread.start()

    def _on_result(self, result) -> None:
        self.btn_search.setEnabled(True)
        if result:
            self.lbl_status.setText("")
            self.qrz_info.update_data(result)
            self.btn_message_lookup.setVisible(True)
        else:
            self.lbl_status.setText("No results found.")

    def _on_message_clicked(self) -> None:
        from direct_message import DirectMessageDialog
        cs = self.cs_edit.text().strip().upper()
        dlg = DirectMessageDialog(target_callsign=cs, parent=self)
        dlg.exec_()


# ── Dialog 2: StatRep Detail ───────────────────────────────────────────────

class StatRepDetailDialog(QDialog):
    """Detail view for a StatRep row: QRZ info + 12 status indicators + map + comments."""

    pin_changed = pyqtSignal(bool)   # emitted when pinned state is saved

    def __init__(self, record_id: str, callsign: str,
                 internet_available: bool = True,
                 backbone_url: str = "",
                 panel_background: str = "#f5f5f5",
                 panel_foreground: str = "#333333",
                 title_bar_background: str = "#555555",
                 title_bar_foreground: str = "#D2D0CF",
                 data_background: str = "#D2D0CF",
                 program_background: str = "",
                 program_foreground: str = "",
                 condition_green: str = "",
                 condition_yellow: str = "",
                 condition_red: str = "",
                 condition_gray: str = "",
                 tcp_pool=None,
                 connector_manager=None,
                 backbone_debug: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._record_id = record_id
        self.callsign = callsign
        self.internet_available = internet_available
        self._backbone_url = backbone_url
        self._panel_bg = panel_background
        self._panel_fg = panel_foreground
        self._title_bg = title_bar_background
        self._title_fg = title_bar_foreground
        self._data_bg = data_background
        self._program_bg = program_background
        self._program_fg = program_foreground
        self._status_colors = {
            "1": (condition_green  or STATUS_COLORS["1"][0], STATUS_COLORS["1"][1]),
            "2": (condition_yellow or STATUS_COLORS["2"][0], STATUS_COLORS["2"][1]),
            "3": (condition_red    or STATUS_COLORS["3"][0], STATUS_COLORS["3"][1]),
            "4": (condition_gray   or STATUS_COLORS["4"][0], STATUS_COLORS["4"][1]),
        }
        self._tcp_pool = tcp_pool
        self._connector_manager = connector_manager
        self._backbone_debug = backbone_debug
        self._thread: Optional[_QRZThread] = None
        self._rc_thread: Optional[_ReadCountThread] = None
        self._map_loaded = False
        self._global_id = 0
        self._row_data: dict = {}
        self._statrep_lat: Optional[float] = None
        self._statrep_lon: Optional[float] = None
        self._statrep_grid: str = ""
        self.setWindowTitle(f"StatRep — {callsign}")
        self.setModal(True)
        self.setMinimumSize(996, 670)
        self.resize(996, 730)
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))
        self._setup_ui()
        self._load_statrep()
        self._start_qrz()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"QDialog {{ background-color:{self._panel_bg}; }}"
            f"QLabel {{ color:{self._panel_fg}; }}"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # QRZ info (top section) — lbl_moddate embedded below image in right column
        self.memo_edit = _MemoTextEdit()
        self.memo_edit.setPlaceholderText("Add notes…")
        self.memo_edit.setFont(QFont("Arial", 11))
        self.memo_edit.setStyleSheet(
            f"background-color:{self._data_bg}; border:1px solid #ccc; border-radius:4px;"
        )
        self.qrz_info = _QRZInfoSection(hdr_bg=self._program_bg, hdr_fg=self._program_fg, parent=self)
        self.qrz_info.add_statrep_rows(memo_widget=self.memo_edit)
        self.qrz_info.image_width_ready.connect(self._adjust_for_image_width)
        main.addWidget(self.qrz_info)

        # Status grid (table style: header row + color row)
        # Outer widget provides top+left border; cells use right+bottom only → 1px lines everywhere
        sg_widget = QWidget()
        sg_widget.setStyleSheet(f"border-top:1px solid #D2D0CF; border-left:1px solid #D2D0CF;")
        sg_grid = QGridLayout(sg_widget)
        sg_grid.setContentsMargins(0, 0, 0, 0)
        sg_grid.setSpacing(0)
        self._squares: Dict[str, QLabel] = {}
        for col_idx, (label_text, _) in enumerate(STATUS_FIELDS):
            hdr = QLabel(label_text)
            hdr.setAlignment(Qt.AlignCenter)
            hdr.setFont(QFont("Arial", 11, QFont.Bold))
            hdr.setStyleSheet(
                f"background-color:{self._title_bg}; color:{self._title_fg};"
                "border-right:1px solid #D2D0CF; border-bottom:1px solid #D2D0CF; padding: 5px 2px;"
            )
            sg_grid.addWidget(hdr, 0, col_idx)
            sq = QLabel()
            sq.setFixedHeight(24)
            sq.setStyleSheet("background-color:rgb(255,255,255); border-right:1px solid #D2D0CF; border-bottom:1px solid #D2D0CF;")
            sq.setToolTip("No status")
            sg_grid.addWidget(sq, 1, col_idx)
            sg_grid.setColumnStretch(col_idx, 1)
            self._squares[label_text] = sq
        main.addWidget(sg_widget)
        main.addWidget(_hsep())

        # Map (512x288) + comments, side by side
        lower = QHBoxLayout()
        lower.setSpacing(10)
        self.map_view = QWebEngineView()
        self.map_view.setFixedSize(480, 270)
        lower.addWidget(self.map_view, alignment=Qt.AlignTop)

        self.comments = QTextEdit()
        self.comments.setReadOnly(True)
        self.comments.setFont(QFont("Arial", 11))
        self.comments.setFixedSize(480, 270)
        self.comments.setStyleSheet(
            f"background-color:{self._data_bg}; border:1px solid #ccc; border-radius:4px;"
        )
        lower.addWidget(self.comments)
        main.addLayout(lower)

        # Action buttons
        btn_row = QHBoxLayout()
        brevity_note = QLabel("<b>Brevity Note:</b> Highlight brevity code, then click Brevity button to decode")
        brevity_note.setFont(QFont("Arial", 10))
        btn_row.addWidget(brevity_note)
        btn_row.addStretch()
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet(_btn_style("#dc3545"))
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)
        self.btn_message_sr = QPushButton("Message")
        self.btn_message_sr.setStyleSheet(_btn_style("#0078d7"))
        self.btn_message_sr.clicked.connect(self._on_message_clicked)
        btn_row.addWidget(self.btn_message_sr)
        for label, color in [
            ("Brevity", "#6f42c1"),
            ("Forward", "#17a2b8"),
        ]:
            b = QPushButton(label)
            b.setStyleSheet(_btn_style(color))
            if label == "Forward":
                b.clicked.connect(self._on_forward)
            elif label == "Brevity":
                b.clicked.connect(self._on_brevity)
            btn_row.addWidget(b)

        # Pin toggle
        self.pin_toggle = _ToggleSwitch()
        self.pin_toggle.toggled.connect(self._save_pinned)
        self.lbl_pin = QLabel("Pinned")
        self.lbl_pin.setFont(QFont("Arial", 11))
        btn_row.addWidget(self.pin_toggle)
        btn_row.addWidget(self.lbl_pin)
        main.addLayout(btn_row)

    def _adjust_for_image_width(self, img_width: int) -> None:
        if img_width > 400:
            self.resize(self.width() + (img_width - 400), self.height())

    def _load_statrep(self) -> None:
        """Load status fields, comments, and map from the database."""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT datetime, global_id, map, power, water, med, telecom, travel,
                           internet, fuel, food, crime, civil, political, comments, grid, sr_id,
                           freq, target, memo, pinned, source
                    FROM statrep WHERE id = ?
                """, (self._record_id,))
                row = cursor.fetchone()
        except sqlite3.Error as e:
            print(f"[StatRepDetailDialog] DB error: {e}")
            return
        if not row:
            return

        # Store row data for forwarding (indices 2–16)
        self._row_data = {
            "map": row[2], "power": row[3], "water": row[4],
            "med": row[5], "telecom": row[6], "travel": row[7],
            "internet": row[8], "fuel": row[9], "food": row[10],
            "crime": row[11], "civil": row[12], "political": row[13],
            "comments": row[14], "grid": row[15],
            "sr_id": row[16],
            "origin_callsign": self.callsign,
        }

        # StatRep details (row indices: 0=datetime, 1=global_id, 16=sr_id, 17=freq, 18=target, 21=source)
        global_id = row[1] or 0
        self._global_id = global_id
        freq_mhz = (float(row[17]) / 1_000_000) if row[17] else 0.0
        sr_id    = row[16] or ""
        group    = ("@" + (row[18] or "").lstrip("@")) if (row[18] or "").strip("@") else ""
        sr_grid  = row[15] or ""
        source   = row[21] if row[21] is not None else 0
        _source_map = {1: "RF via JS8Call", 2: "Internet", 3: "Internet Only"}
        source_text  = _source_map.get(int(source), "Unknown")

        self.qrz_info.lbl_sr_posted.setText(
            f"<b>Posted:</b>  {row[0]}" if row[0] else "<b>Posted:</b>"
        )
        self.qrz_info.lbl_sr_source.setText(f"<b>Received via:</b>  {source_text}")
        self.qrz_info.lbl_sr_global_id.setText(
            f"<b>Global ID:</b>  {global_id}" if global_id else "<b>Global ID:</b>"
        )
        self.qrz_info.lbl_sr_group.setText(
            f"<b>Group:</b>  {group}" if group else "<b>Group:</b>"
        )
        self.qrz_info.lbl_sr_grid.setText(
            f"<b>Grid:</b>  {sr_grid}" if sr_grid else "<b>Grid:</b>"
        )
        self.qrz_info.lbl_sr_freqid.setText(
            f"<b>Freq/ID:</b>  {freq_mhz:.3f}/{sr_id}" if freq_mhz or sr_id else "<b>Freq/ID:</b>"
        )
        self.qrz_info.lbl_sr_delivered.setText("<b>Delivered To:</b>")

        # Fetch delivery count from backbone if available
        if global_id and self._backbone_url and self.internet_available:
            local_cs = _get_local_callsign()
            if local_cs:
                self._rc_thread = _ReadCountThread(self._backbone_url, local_cs, global_id)
                self._rc_thread.count_ready.connect(self._on_read_count)
                self._rc_thread.start()

        # Status squares (indices 2–13)
        for i, (label_text, _) in enumerate(STATUS_FIELDS):
            val = str(row[i + 2]) if row[i + 2] is not None else ""
            sq = self._squares[label_text]
            color_str, tip = self._status_colors.get(val, ("rgb(255,255,255)", "No status"))
            sq.setStyleSheet(
                f"background-color:{color_str}; border:1px solid #D2D0CF;"
            )
            sq.setToolTip(tip)

        # Comments (index 14) — decode || newline placeholders
        self.comments.setPlainText((row[14] or "").replace("||", "\n"))

        # Memo (index 19) — user notes, auto-saved on focus-out
        self.memo_edit.blockSignals(True)
        self.memo_edit.setPlainText(row[19] or "")
        self.memo_edit.blockSignals(False)
        self.memo_edit.focus_lost.connect(self._save_memo)

        # Pinned (index 20)
        self.pin_toggle.blockSignals(True)
        self.pin_toggle.setChecked(bool(row[20]))
        self.pin_toggle.blockSignals(False)

        # Map from grid square (index 15)
        grid = row[15]
        if grid:
            try:
                coords = mh.to_location(grid, center=True)
                lat, lon = float(coords[0]), float(coords[1])
                self._statrep_lat = lat
                self._statrep_lon = lon
                self._statrep_grid = grid[:4].upper()
                self.map_view.setHtml(
                    _make_map_html(lat, lon, self.internet_available)
                )
                self._map_loaded = True
            except Exception as e:
                print(f"[StatRepDetailDialog] Map error for grid {grid}: {e}")

    def _on_read_count(self, count: int) -> None:
        self.qrz_info.lbl_sr_delivered.setText(f"<b>Delivered To:</b>  {count} CommStat users")

    def _save_memo(self) -> None:
        """Save memo text to the database on focus-out."""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute(
                    "UPDATE statrep SET memo = ? WHERE id = ?",
                    (self.memo_edit.toPlainText(), self._record_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"[StatRepDetailDialog] Memo save error: {e}")

    def _save_pinned(self, checked: bool) -> None:
        """Save pinned state to the database and notify the main window."""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute(
                    "UPDATE statrep SET pinned = ? WHERE id = ?",
                    (1 if checked else 0, self._record_id)
                )
                conn.commit()
            self.pin_changed.emit(checked)
        except sqlite3.Error as e:
            print(f"[StatRepDetailDialog] Pinned save error: {e}")

    def _on_brevity(self) -> None:
        selected = self.comments.textCursor().selectedText().strip()
        brevity_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brevity.py")
        if os.path.exists(brevity_path):
            args = [sys.executable, brevity_path, self._panel_bg, self._panel_fg]
            if selected:
                args.append(selected)
            subprocess.Popen(args)

    def _on_forward(self) -> None:
        if not self._tcp_pool or not self._connector_manager or not self._row_data:
            return
        from statrep import StatRepDialog
        dlg = StatRepDialog(
            self._tcp_pool, self._connector_manager, self,
            backbone_debug=self._backbone_debug,
            panel_background=self._panel_bg,
        )
        dlg.prefill(self._row_data)
        dlg.exec_()

    def _on_message_clicked(self) -> None:
        from direct_message import DirectMessageDialog
        dlg = DirectMessageDialog(target_callsign=self.callsign, parent=self)
        dlg.exec_()

    def _on_delete(self) -> None:
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Delete")
        msg_box.setText(
            "Status Report records will be deleted from all CommStat users if you are "
            "the creator of the record. If you are not the creator, the record will only "
            "be deleted locally."
        )
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        if msg_box.exec_() != QMessageBox.Yes:
            return
        if self._global_id and self._backbone_url:
            try:
                local_cs = _get_local_callsign()
                url = (f"{self._backbone_url}/statrep-delete-808585.php"
                       f"?cs={urllib.parse.quote(local_cs)}&id={self._global_id}")
                urllib.request.urlopen(url, timeout=10).close()
            except Exception:
                pass
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute("DELETE FROM statrep WHERE id = ?", (self._record_id,))
                conn.commit()
        except sqlite3.Error:
            pass
        self.accept()

    def _start_qrz(self) -> None:
        cached = get_qrz_cached(self.callsign)
        if cached:
            self._on_qrz_result(cached)
            return
        is_active, username, password = load_qrz_config()
        if not is_active:
            return
        self._thread = _QRZThread(self.callsign, username, password)
        self._thread.result_ready.connect(self._on_qrz_result)
        self._thread.start()

    def _on_qrz_result(self, result) -> None:
        if not result:
            return
        self.qrz_info.update_data(result)
        d = _normalize_qrz(result)

        if not self._map_loaded:
            # Fall back to QRZ lat/lon if grid-based map didn't load
            if d["lat"] and d["lon"]:
                try:
                    lat, lon = float(d["lat"]), float(d["lon"])
                    self.map_view.setHtml(
                        _make_map_html(lat, lon, self.internet_available)
                    )
                    self._map_loaded = True
                except (ValueError, TypeError):
                    pass
        else:
            # Map already shows statrep grid — add QRZ home pin if grid differs
            qrz_grid = (d.get("grid") or "")[:4].upper()
            if qrz_grid and qrz_grid != self._statrep_grid and d["lat"] and d["lon"]:
                try:
                    qrz_lat, qrz_lon = float(d["lat"]), float(d["lon"])
                    self.map_view.setHtml(
                        _make_map_html(
                            self._statrep_lat, self._statrep_lon,
                            self.internet_available,
                            extra_lat=qrz_lat, extra_lon=qrz_lon,
                        )
                    )
                except (ValueError, TypeError):
                    pass


# ── Dialog 3: Message Detail ───────────────────────────────────────────────

class MessageDetailDialog(QDialog):
    """Detail view for a Message row: QRZ info + map + message text."""

    def __init__(self, callsign: str, message_text: str,
                 internet_available: bool = True,
                 panel_background: str = "#f5f5f5",
                 panel_foreground: str = "#333333",
                 data_background: str = "#D2D0CF",
                 program_background: str = "",
                 program_foreground: str = "",
                 msg_id: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.callsign = callsign
        self.message_text = message_text
        self.internet_available = internet_available
        self._panel_bg = panel_background
        self._panel_fg = panel_foreground
        self._data_bg = data_background
        self._program_bg = program_background
        self._program_fg = program_foreground
        self._msg_id = msg_id
        self._thread: Optional[_QRZThread] = None
        self._map_loaded = False
        self.setWindowTitle(f"Message — {callsign}")
        self.setModal(True)
        self.setMinimumSize(996, 460)
        self.resize(996, 520)
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))
        self._setup_ui()
        self._start_qrz()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"QDialog {{ background-color:{self._panel_bg}; }}"
            f"QLabel {{ color:{self._panel_fg}; }}"
        )
        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # QRZ info (top section)
        self.qrz_info = _QRZInfoSection(hdr_bg=self._program_bg, hdr_fg=self._program_fg, parent=self)
        main.addWidget(self.qrz_info)
        main.addWidget(_hsep())

        # Map (480x230) + message text, side by side
        lower = QHBoxLayout()
        lower.setSpacing(10)
        self.map_view = QWebEngineView()
        self.map_view.setFixedSize(480, 230)
        lower.addWidget(self.map_view, alignment=Qt.AlignTop)

        self.msg_text = QTextEdit()
        self.msg_text.setReadOnly(True)
        self.msg_text.setFont(QFont("Arial", 11))
        self.msg_text.setFixedSize(480, 230)
        self.msg_text.setStyleSheet(
            f"background-color:{self._data_bg}; border:1px solid #ccc; border-radius:4px;"
        )
        self.msg_text.setPlainText(self.message_text.replace("||", "\n"))
        lower.addWidget(self.msg_text)
        main.addLayout(lower)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setStyleSheet(_btn_style("#dc3545"))
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)
        self.btn_message_msg = QPushButton("Message")
        self.btn_message_msg.setStyleSheet(_btn_style("#0078d7"))
        self.btn_message_msg.clicked.connect(self._on_message_clicked)
        btn_row.addWidget(self.btn_message_msg)
        main.addLayout(btn_row)

    def _on_message_clicked(self) -> None:
        from direct_message import DirectMessageDialog
        dlg = DirectMessageDialog(target_callsign=self.callsign, parent=self)
        dlg.exec_()

    def _on_delete(self) -> None:
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute("DELETE FROM messages WHERE msg_id = ?", (self._msg_id,))
                conn.commit()
        except sqlite3.Error:
            pass
        self.accept()

    def _start_qrz(self) -> None:
        cached = get_qrz_cached(self.callsign)
        if cached:
            self._on_qrz_result(cached)
            return
        is_active, username, password = load_qrz_config()
        if not is_active:
            return
        self._thread = _QRZThread(self.callsign, username, password)
        self._thread.result_ready.connect(self._on_qrz_result)
        self._thread.start()

    def _on_qrz_result(self, result) -> None:
        if not result:
            return
        self.qrz_info.update_data(result)
        d = _normalize_qrz(result)
        if not self._map_loaded:
            lat, lon = None, None
            if d["lat"] and d["lon"]:
                try:
                    lat, lon = float(d["lat"]), float(d["lon"])
                except (ValueError, TypeError):
                    pass
            if lat is None and d["grid"]:
                try:
                    coords = mh.to_location(d["grid"], center=True)
                    lat, lon = float(coords[0]), float(coords[1])
                except Exception:
                    pass
            if lat is not None and lon is not None:
                self._map_loaded = True
                self.map_view.setHtml(
                    _make_map_html(lat, lon, self.internet_available)
                )
        else:
            # Map already shows statrep grid — add QRZ home pin if grid differs
            qrz_grid = (d.get("grid") or "")[:4].upper()
            if qrz_grid and qrz_grid != self._statrep_grid and d["lat"] and d["lon"]:
                try:
                    qrz_lat, qrz_lon = float(d["lat"]), float(d["lon"])
                    self.map_view.setHtml(
                        _make_map_html(
                            self._statrep_lat, self._statrep_lon,
                            self.internet_available,
                            extra_lat=qrz_lat, extra_lon=qrz_lon,
                        )
                    )
                except (ValueError, TypeError):
                    pass
