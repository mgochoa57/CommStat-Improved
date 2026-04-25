import sys
import os
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
    QStatusBar, QCompleter, QPushButton, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

from constants import (
    DEFAULT_COLORS, COLOR_INPUT_TEXT, COLOR_INPUT_BORDER,
    COLOR_BTN_RED, COLOR_BTN_CYAN,
)

_PROG_BG  = DEFAULT_COLORS.get("program_background",   "#000000")
_PROG_FG  = DEFAULT_COLORS.get("program_foreground",   "#FFFFFF")
_TITLE_BG = DEFAULT_COLORS.get("title_bar_background", "#F07800")
_TITLE_FG = DEFAULT_COLORS.get("title_bar_foreground", "#FFFFFF")

_COL_CANCEL = "#555555"


def _btn(label: str, color: str, w: int = 120) -> QPushButton:
    b = QPushButton(label)
    b.setFixedWidth(w)
    b.setFocusPolicy(Qt.NoFocus)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; font-weight:bold;"
        f" font-family:Roboto; font-size:15px; padding:4px 8px; border:none; border-radius:4px; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
    )
    return b


def format_grid(grid: str) -> str:
    """Format grid as EM83cv: first 2 uppercase, digits unchanged, last 2 lowercase."""
    g = grid.strip()
    if len(g) >= 6:
        return g[:2].upper() + g[2:4] + g[4:6].lower()
    if len(g) >= 4:
        return g[:2].upper() + g[2:4]
    return g.upper()


class GridFinderApp(QMainWindow):
    grid_selected = pyqtSignal(str)

    def __init__(self, panel_bg: str = "#F8F6F4", panel_fg: str = "#333333",
                 data_bg: str = "#F8F6F4", data_fg: str = "#333333", parent=None):
        super().__init__(parent)
        self.panel_bg = panel_bg
        self.panel_fg = panel_fg
        self.data_bg  = data_bg
        self.data_fg  = data_fg

        self.setWindowTitle("Grid Finder")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.resize(620, 520)
        self.setMinimumSize(500, 440)

        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QIcon("radiation-32.png"))

        self.data = self._load_data()
        if not self.data.empty:
            self.data['City_lower']  = self.data['City'].str.lower().str.strip()
            self.data['State_lower'] = self.data['State'].str.lower().str.strip()
            self.data['MGrid_lower'] = self.data['MGrid'].str.lower().str.strip()

        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._filter_data)

        self._setup_ui()
        self._apply_stylesheet()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self) -> pd.DataFrame:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(script_dir, "gridsearchdata.csv")
        if not os.path.exists(csv_path):
            QMessageBox.critical(None, "Grid Finder Error",
                                 f"gridsearchdata.csv not found in:\n{script_dir}")
            return pd.DataFrame()
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
            df['MGrid'] = df['MGrid'].astype(str).str.strip().str.upper()
            df['City']  = df['City'].astype(str).str.strip()
            df['State'] = df['State'].astype(str).str.strip()
            return df
        except Exception as e:
            QMessageBox.critical(None, "Grid Finder Error", f"Failed to load data:\n{e}")
            return pd.DataFrame()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 10)

        # Title
        title = QLabel("GRID FINDER")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Roboto Slab", -1, QFont.Black))
        title.setFixedHeight(36)
        title.setStyleSheet(
            f"QLabel {{ background-color: {_PROG_BG}; color: {_PROG_FG}; "
            "font-size: 16px; padding-top: 9px; padding-bottom: 9px; }}"
        )
        layout.addWidget(title)

        # City field
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("City")
        if not self.data.empty:
            completer = QCompleter(self.data['City'].unique())
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.city_input.setCompleter(completer)
        layout.addWidget(self.city_input)

        # State + Grid row
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("State (US) or Country")
        row2.addWidget(self.state_input, stretch=2)

        self.grid_input = QLineEdit()
        self.grid_input.setPlaceholderText("Grid")
        self.grid_input.setMaxLength(6)
        row2.addWidget(self.grid_input, stretch=1)

        layout.addLayout(row2)

        # Tab order: city → state → grid → city
        self.setTabOrder(self.city_input, self.state_input)
        self.setTabOrder(self.state_input, self.grid_input)
        self.setTabOrder(self.grid_input, self.city_input)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["City", "State / Country", "Grid"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 90)
        layout.addWidget(self.table)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.clear_btn = _btn("Clear", COLOR_BTN_RED)
        btn_row.addWidget(self.clear_btn)

        self.copy_btn = _btn("Copy", COLOR_BTN_CYAN)
        btn_row.addWidget(self.copy_btn)

        self.cancel_btn = _btn("Cancel", _COL_CANCEL)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Signals
        self.city_input.textChanged.connect(self._on_text_changed)
        self.state_input.textChanged.connect(self._on_text_changed)
        self.grid_input.textChanged.connect(self._on_text_changed)
        self.table.clicked.connect(self._on_row_clicked)
        self.clear_btn.clicked.connect(self._on_clear)
        self.copy_btn.clicked.connect(self._on_copy)
        self.cancel_btn.clicked.connect(self.close)

        self.city_input.setFocus()

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {self.data_bg}; }}
            QWidget {{ background-color: {self.data_bg}; color: {COLOR_INPUT_TEXT}; }}
            QLabel {{ background-color: transparent; color: {COLOR_INPUT_TEXT}; font-size: 13px; }}
            QLineEdit {{
                background-color: white; color: {COLOR_INPUT_TEXT};
                border: 1px solid {COLOR_INPUT_BORDER}; border-radius: 4px;
                padding: 4px; font-family: 'Kode Mono'; font-size: 13px;
            }}
            QTableWidget {{
                background-color: {self.data_bg}; color: {self.data_fg};
                border: 1px solid {COLOR_INPUT_BORDER};
                font-family: 'Kode Mono'; font-size: 13px;
                gridline-color: #cccccc;
            }}
            QTableWidget::item {{
                background-color: {self.data_bg}; color: {self.data_fg}; padding: 2px;
            }}
            QTableWidget::item:selected {{
                background-color: #cce5ff; color: #000000;
            }}
            QHeaderView::section {{
                background-color: {_TITLE_BG}; color: {_TITLE_FG};
                border: 1px solid {COLOR_INPUT_BORDER};
                padding: 4px; font-family: Roboto; font-size: 13px; font-weight: bold;
            }}
            QStatusBar {{
                background-color: {self.data_bg}; color: {COLOR_INPUT_TEXT};
                font-family: Roboto; font-size: 13px;
            }}
        """)

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_text_changed(self):
        self.debounce_timer.start(400)

    def _filter_data(self):
        city_q  = self.city_input.text().strip().lower()
        state_q = self.state_input.text().strip().lower()
        grid_q  = self.grid_input.text().strip().lower()

        if not any([city_q, state_q, grid_q]):
            self._populate_table(pd.DataFrame())
            self.status_bar.showMessage("Enter city, state/country, or grid to search.")
            return

        filtered = self.data
        if city_q:
            filtered = filtered[filtered['City_lower'].str.contains(city_q, na=False)]
        if state_q:
            filtered = filtered[filtered['State_lower'].str.contains(state_q, na=False)]
        if grid_q:
            filtered = filtered[filtered['MGrid_lower'].str.contains(grid_q, na=False)]

        self._populate_table(filtered)

    def _populate_table(self, df: pd.DataFrame):
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(0)

        if df.empty:
            if any([self.city_input.text(), self.state_input.text(), self.grid_input.text()]):
                self.status_bar.showMessage("No results found.", 5000)
            return

        self.table.setRowCount(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            self.table.setItem(i, 0, QTableWidgetItem(row['City']))
            self.table.setItem(i, 1, QTableWidgetItem(row['State']))
            self.table.setItem(i, 2, QTableWidgetItem(format_grid(row['MGrid'])))

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.status_bar.showMessage(f"{len(df)} result(s) found.", 5000)

    def _on_row_clicked(self, index):
        row = index.row()
        grid_item = self.table.item(row, 2)
        if not grid_item:
            return
        formatted = format_grid(grid_item.text())
        self.grid_input.blockSignals(True)
        self.grid_input.setText(formatted)
        self.grid_input.blockSignals(False)
        self.status_bar.showMessage(
            f"Grid: {formatted}  — press Copy to copy to clipboard.", 8000
        )

    def _on_clear(self):
        self.city_input.clear()
        self.state_input.clear()
        self.grid_input.clear()
        self.table.clearContents()
        self.table.setRowCount(0)
        self.status_bar.showMessage("Cleared.", 3000)
        self.city_input.setFocus()

    def _on_copy(self):
        grid = self.grid_input.text().strip()
        if grid:
            QApplication.clipboard().setText(grid)
            self.grid_selected.emit(grid)
            self.status_bar.showMessage(f"Copied: {grid}", 5000)
        else:
            self.status_bar.showMessage("No grid to copy.", 5000)


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    panel_bg = sys.argv[1] if len(sys.argv) > 1 else "#F8F6F4"
    panel_fg = sys.argv[2] if len(sys.argv) > 2 else "#333333"
    data_bg  = sys.argv[3] if len(sys.argv) > 3 else "#F8F6F4"
    data_fg  = sys.argv[4] if len(sys.argv) > 4 else "#333333"

    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    if os.path.exists("radiation-32.png"):
        app.setWindowIcon(QIcon("radiation-32.png"))

    window = GridFinderApp(panel_bg, panel_fg, data_bg, data_fg)
    window.show()

    if len(sys.argv) >= 9:
        try:
            px, py, pw, ph = int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
            ww, wh = window.width(), window.height()
            window.move(px + (pw - ww) // 2, py + (ph - wh) // 2)
        except ValueError:
            pass

    sys.exit(app.exec_())
