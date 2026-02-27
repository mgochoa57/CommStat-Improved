# Grid Finder: A cross-platform application for searching city, state, and grid data from a CSV file.
# Requirements: Install dependencies with `pip install pandas PyQt5`.
# On Linux, ensure Qt dependencies: `sudo apt-get install libqt5gui5`.
# CSV file: Place `GridSearchData1_preprocessed.csv` in the same directory as this script.
# Note: File names are case-sensitive on Linux; ensure exact match.

import sys
import os
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem,
    QStatusBar, QCompleter, QMenu, QMessageBox, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QFont, QBrush, QColor, QPalette
from theme_manager import theme

class AppTheme:
    # Semantic/functional colors — these do NOT follow system theme
    COLORS = {
        'primary': '#4CAF50',       # Green for search inputs
        'primary_hover': '#66BB6A', # Lighter green for hover
        'flash_red': '#FF0000',     # Red for validation alerts
        'focus_border': '#388E3C',  # Focus ring on green inputs
        'text_on_primary': '#000000',       # Text on green background
        'placeholder_on_primary': '#E0E0E0', # Placeholder on green bg
    }

    @staticmethod
    def input_style(valid=True):
        """QSS for green search inputs. Border turns red when invalid."""
        border_color = theme.color('mid') if valid else AppTheme.COLORS['flash_red']
        return f"""
            QLineEdit {{
                background-color: {AppTheme.COLORS['primary']};
                color: {AppTheme.COLORS['text_on_primary']};
                font-family: {theme.font_family}, sans-serif;
                font-size: 11pt;
                font-weight: bold;
                border: 3px solid {border_color};
                padding: 2px 8px;
                border-radius: 5px;
            }}
            QLineEdit:hover {{
                background-color: {AppTheme.COLORS['primary_hover']};
            }}
            QLineEdit:focus {{
                border: 3px solid {AppTheme.COLORS['focus_border']};
                background-color: {AppTheme.COLORS['primary']};
            }}
            QLineEdit::placeholder {{
                color: {AppTheme.COLORS['placeholder_on_primary']};
                font-weight: normal;
            }}
        """

class GridFinderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grid Finder V1.0")
        self.setGeometry(200, 200, 500, 400)
        self.setMinimumSize(500, 400)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(theme.color('window')))
        self.setPalette(palette)
        print("Applied application palette")  # Debug
        self.data = self.load_data()
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.filter_data)
        self.debounce_delay = 300  # milliseconds
        self.initUI()

    def load_data(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            file_name = "GridSearchData1_preprocessed.csv"
            file_path = os.path.join(script_dir, file_name)
            # Case-insensitive file search for Linux
            if not os.path.exists(file_path):
                for f in os.listdir(script_dir):
                    if f.lower() == file_name.lower():
                        file_path = os.path.join(script_dir, f)
                        break
                else:
                    raise FileNotFoundError(f"CSV file '{file_name}' not found")
            data = pd.read_csv(file_path, encoding='utf-8')
            data['MGrid'] = data['MGrid'].astype(str).str.strip()
            data['City'] = data['City'].astype(str).str.strip()
            data['State'] = data['State'].astype(str).str.strip()
            print(f"Data loaded successfully: {len(data)} rows")  # Debug
            print(f"Unique MGrid values: {data['MGrid'].unique().tolist()[:10]}")  # Debug
            return data
        except FileNotFoundError:
            print("Error: CSV file not found")  # Debug
            self._show_error_dialog("Error", f"CSV file '{file_name}' not found. Ensure it is in the same directory as the script.")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error loading data: {str(e)}")  # Debug
            self._show_error_dialog("Error", f"Error loading data: {str(e)}")
            return pd.DataFrame()

    def _show_error_dialog(self, title, message):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    def initUI(self):
        # Set up central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setStyleSheet(f"""
            border: 1px solid {theme.color('mid')};
            border-radius: 4px;
            background-color: {theme.color('window')};
        """)
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        self.central_widget.setLayout(layout)
        print("Applied central widget stylesheet with border: #666666")  # Debug

        # Input grid
        input_grid = QGridLayout()
        input_grid.setSpacing(10)
        input_grid.setColumnStretch(0, 3)
        input_grid.setColumnStretch(1, 1)
        input_grid.setColumnStretch(2, 1)
        print("Created QGridLayout for inputs")  # Debug

        # Inputs
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("Enter City")
        self.city_input.setReadOnly(False)
        self.city_input.setEnabled(True)
        self.city_input.setStyleSheet(AppTheme.input_style(valid=True))
        self.city_input.setToolTip("Enter city name (partial, case-insensitive)")
        self.city_input.textChanged.connect(self.on_text_changed)
        self.city_input.textChanged.connect(self.validate_inputs)
        if not self.data.empty:
            self.city_completer = QCompleter(self.data['City'].unique(), self)
            self.city_completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.city_input.setCompleter(self.city_completer)
        input_grid.addWidget(self.city_input, 0, 0)
        print("Applied city input stylesheet with border: #666666, text: #000000, font-size: 11pt")  # Debug

        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("State")
        self.state_input.setReadOnly(False)
        self.state_input.setEnabled(True)
        self.state_input.setStyleSheet(AppTheme.input_style(valid=True))
        self.state_input.setToolTip("Enter 2-letter state code (case-insensitive)")
        self.state_input.textChanged.connect(self.on_text_changed)
        self.state_input.textChanged.connect(self.validate_inputs)
        input_grid.addWidget(self.state_input, 0, 1)
        print("Applied state input stylesheet with border: #666666, text: #000000, font-size: 11pt")  # Debug

        self.grid_input = QLineEdit()
        self.grid_input.setPlaceholderText("Grid")
        self.grid_input.setReadOnly(False)
        self.grid_input.setEnabled(True)
        self.grid_input.setStyleSheet(AppTheme.input_style(valid=True))
        self.grid_input.setToolTip("Enter grid code (partial or full, up to 6 characters, case-insensitive)")
        self.grid_input.textChanged.connect(self.on_text_changed)
        self.grid_input.textChanged.connect(self.validate_inputs)
        input_grid.addWidget(self.grid_input, 0, 2)
        print("Applied grid input stylesheet with border: #666666, text: #000000, font-size: 11pt")  # Debug

        layout.addLayout(input_grid)

        # Results table
        self.results = QTableWidget()
        self.results.setColumnCount(3)
        self.results.setHorizontalHeaderLabels(["City", "State", "Grid"])
        self.results.setSelectionMode(QTableWidget.SingleSelection)
        self.results.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results.setSortingEnabled(True)
        self.results.setStyleSheet(f"""
            QTableWidget {{
                font-family: {theme.font_family}, sans-serif;
                font-size: 11pt;
                background-color: {theme.color('base')};
                color: {theme.color('text')};
                border: 1px solid {theme.color('mid')};
                border-radius: 5px;
            }}
            QTableWidget::item {{
                padding: 2px;
            }}
            QHeaderView::section {{
                background-color: {theme.color('window')};
                color: {theme.color('windowtext')};
                border: 1px solid {theme.color('mid')};
                padding: 4px;
            }}
        """)
        self.results.setColumnWidth(0, 200)
        self.results.setColumnWidth(1, 60)
        self.results.setColumnWidth(2, 100)
        layout.addWidget(self.results)
        print("Applied results table stylesheet with border: #666666")  # Debug

        # Status bar
        self.statusBar = QStatusBar()
        self.statusBar.setStyleSheet(f"""
            QStatusBar {{
                background: {theme.color('window')};
                border: 1px solid {theme.color('mid')};
                font-family: {theme.font_family}, sans-serif;
                font-size: 11pt;
                font-weight: bold;
                color: {theme.color('windowtext')};
            }}
        """)
        self.statusBar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.statusBar.customContextMenuRequested.connect(self._create_status_context_menu)
        self.setStatusBar(self.statusBar)
        if self.data.empty:
            self.show_styled_message("Error: Failed to load data. Check CSV file.", 15000, "#CC0000")
        print("Applied status bar stylesheet with border: #666666")  # Debug

        # Install event filter for focus debugging
        self.state_input.installEventFilter(self)
        self.grid_input.installEventFilter(self)

        # Initial validation
        self.validate_inputs()

    def show_styled_message(self, text, timeout, color):
        self.statusBar.setStyleSheet(f"""
            QStatusBar {{
                background: {theme.color('window')};
                border: 1px solid {theme.color('mid')};
                font-family: {theme.font_family}, sans-serif;
                font-size: 11pt;
                font-weight: bold;
                color: {color};
            }}
        """)
        self.statusBar.setToolTip(text)
        self.statusBar.showMessage(text, timeout)
        print(f"Status message: {text}, color: {color}")  # Debug

    def _create_status_context_menu(self, position):
        menu = QMenu()
        copy_action = menu.addAction("Copy Status Message")
        copy_action.triggered.connect(self._copy_status_message)
        menu.exec_(self.statusBar.mapToGlobal(position))

    def _copy_status_message(self):
        clipboard = QApplication.clipboard()
        message = self.statusBar.currentMessage()
        if message:
            clipboard.setText(message)
            self.show_styled_message("Status message copied to clipboard", 8000, "#000000")
        else:
            self.show_styled_message("No status message to copy", 8000, "#CC0000")

    def eventFilter(self, source, event):
        if event.type() == QEvent.FocusIn:
            if source == self.state_input:
                print("State input gained focus")  # Debug
            elif source == self.grid_input:
                print("Grid input gained focus")  # Debug
        return super().eventFilter(source, event)

    def on_text_changed(self, text):
        print(f"Text changed: City={self.city_input.text()}, State={self.state_input.text()}, Grid={self.grid_input.text()}")  # Debug
        self.debounce_timer.start(self.debounce_delay)

    def validate_inputs(self):
        def set_input_style(input_widget, valid, tooltip=""):
            input_widget.setStyleSheet(AppTheme.input_style(valid=valid))
            input_widget.setToolTip(tooltip)

        state_text = self.state_input.text()
        if state_text and len(state_text) != 2:
            set_input_style(self.state_input, False, "State must be 2 letters (case-insensitive).")
        else:
            set_input_style(self.state_input, True, "Enter 2-letter state code (case-insensitive)")

        grid_text = self.grid_input.text()
        if grid_text and len(grid_text) > 6:
            set_input_style(self.grid_input, False, "Grid must be 6 or fewer characters (case-insensitive, partial matches allowed).")
        else:
            set_input_style(self.grid_input, True, "Enter grid code (partial or full, up to 6 characters, case-insensitive)")

    def filter_data(self):
        self.show_styled_message("Filtering...", 8000, "#000000")
        city_query = self.city_input.text().strip()
        state_query = self.state_input.text().strip().upper()
        grid_query = self.grid_input.text().strip().upper()
        print(f"Filtering with: City={city_query}, State={state_query}, Grid={grid_query}")  # Debug

        # Validate State before filtering
        if state_query and len(state_query) != 2:
            self.show_styled_message("Invalid State: Must be exactly 2 letters", 10000, "#CC0000")
            self.display_results(pd.DataFrame())
            return
        # Validate Grid length
        if grid_query and len(grid_query) > 6:
            self.show_styled_message("Invalid Grid: Must be 6 or fewer characters", 10000, "#CC0000")
            self.display_results(pd.DataFrame())
            return

        if not any([city_query, state_query, grid_query]):
            self.display_results(pd.DataFrame())
            return

        if self.data.empty:
            self.show_styled_message("No data available. Check CSV file.", 15000, "#CC0000")
            self.display_results(pd.DataFrame())
            return

        filtered = self.data
        print(f"Initial data rows: {len(filtered)}")  # Debug
        if city_query:
            filtered = filtered[filtered['City'].str.contains(city_query, case=False, na=False, regex=False)]
            print(f"After City filter: {len(filtered)} rows")  # Debug
        if state_query:
            filtered = filtered[filtered['State'].str.upper() == state_query]
            print(f"After State filter: {len(filtered)} rows")  # Debug
        if grid_query:
            filtered = filtered[filtered['MGrid'].str.contains(grid_query, case=False, na=False, regex=False)]
            print(f"After Grid filter: {len(filtered)} rows")  # Debug

        print(f"Filtered results: {len(filtered)} rows")  # Debug
        if len(filtered) > 0:
            print(f"Sample filtered data: {filtered[['City', 'State', 'MGrid']].head().to_dict('records')}")  # Debug
            if grid_query:
                print(f"Matched MGrid values: {filtered['MGrid'].unique().tolist()}")  # Debug
        self.display_results(filtered)

    def display_results(self, filtered):
        self.results.clearContents()
        self.results.setRowCount(0)

        if filtered.empty:
            self.results.setRowCount(1)
            self.results.setItem(0, 0, QTableWidgetItem("No matches found"))
            self.show_styled_message("No results found", 8000, "#CC0000")
            return

        self.results.setRowCount(len(filtered))
        for i, (_, row) in enumerate(filtered.iterrows()):
            self.results.setItem(i, 0, QTableWidgetItem(row['City']))
            self.results.setItem(i, 1, QTableWidgetItem(row['State']))
            self.results.setItem(i, 2, QTableWidgetItem(row['MGrid']))

        self.results.resizeColumnsToContents()
        self.show_styled_message(f"Found {len(filtered)} results", 8000, "#000000")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont(theme.font_family, theme.font_size))
    window = GridFinderApp()
    window.show()
    sys.exit(app.exec_())