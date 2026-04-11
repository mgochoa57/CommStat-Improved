# Copyright (c) 2025 Manuel Ochoa

import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget, 
    QTableWidgetItem, QLineEdit, QPushButton, QLabel, QHeaderView,
    QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal

# CommStat Imports
from constants import DEFAULT_COLORS
from qrz_client import load_qrz_config, CACHE_DAYS
from qrz_lookup import _QRZInfoSection, _normalize_qrz, _QRZThread, _btn_style, _hsep, fs

DB_PATH = Path(__file__).parent / "traffic.db3"

class QRZDetailDialog(QDialog):
    """Popup dialog showing full QRZ cache details with re-fetch and delete actions."""
    
    data_refetched = pyqtSignal(dict) # Signal to notify parent of updated data
    
    def __init__(self, row_data, panel_bg="#f5f5f5", panel_fg="#333333", data_bg="#FFF5E1", data_fg="#000000", parent=None):
        super().__init__(parent)
        self.row_data = dict(row_data) # Convert sqlite3.Row to dict
        self.callsign = self.row_data['callsign']
        self.panel_bg = panel_bg
        self.panel_fg = panel_fg
        self.data_bg = data_bg
        self.data_fg = data_fg
        
        self.setWindowTitle(f"QRZ Cache Detail - {self.callsign}")
        self.setMinimumSize(fs(900), fs(600))
        
        self.setStyleSheet(f"background-color: {self.panel_bg}; color: {self.data_fg};")
        
        # Persistent references for metadata labels
        self.meta_vals = {} # keys: cached_on, age, status
        
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(fs(20), fs(20), fs(20), fs(20))
        layout.setSpacing(fs(15))
        
        # 1. Metadata Section (above _QRZInfoSection)
        meta_frame = QFrame()
        meta_frame.setStyleSheet(f"background-color: {self.data_bg}; border: 1px solid #cccccc; border-radius: {fs(5)}px;")
        meta_layout = QGridLayout(meta_frame)
        
        # Fonts
        lbl_font = QtGui.QFont("Arial", fs(11), QtGui.QFont.Bold)
        self.val_font = QtGui.QFont("Arial", fs(11))
        
        # Helper to add rows and store value label references
        def _add_meta_row(row, label, key):
            l = QLabel(label)
            l.setFont(lbl_font)
            l.setStyleSheet(f"color: {self.data_fg}; border: none; background: transparent;")
            
            v = QLabel("")
            v.setFont(self.val_font)
            v.setStyleSheet(f"color: {self.data_fg}; border: none; background: transparent;")
            
            meta_layout.addWidget(l, row, 0)
            meta_layout.addWidget(v, row, 1)
            self.meta_vals[key] = v

        _add_meta_row(0, "Callsign:", 'callsign')
        _add_meta_row(1, "Cached On:", 'cached_on')
        _add_meta_row(2, "Cache Age:", 'age')
        _add_meta_row(3, "Status:", 'status')
        
        layout.addWidget(meta_frame)
        
        # 2. QRZ Info Section (The 3-column panel from qrz_lookup)
        self.info_section = _QRZInfoSection(
            hdr_bg=self.panel_bg,
            hdr_fg=self.panel_fg,
            parent=self
        )
        self.info_section.setStyleSheet(f"QLabel {{ color: {self.data_fg}; }}")
        layout.addWidget(self.info_section)
        
        # Error Label (hidden by default)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #dc3545; font-weight: bold; border: none; background: transparent;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # 3. Action Buttons
        btn_layout = QHBoxLayout()
        
        # Re-fetch Button
        self.refetch_btn = QPushButton("Re-fetch from QRZ")
        self.refetch_btn.setMinimumHeight(fs(40))
        
        # Check credentials
        is_active, user, pwd = load_qrz_config()
        if not is_active or not user or not pwd:
            self.refetch_btn.setEnabled(False)
            self.refetch_btn.setToolTip("QRZ credentials not configured in CommStat settings.")
            self.refetch_btn.setStyleSheet(_btn_style("#6c757d")) # Greyed out
        else:
            self.refetch_btn.setStyleSheet(_btn_style("#0078d7")) # Blue
            self.refetch_btn.clicked.connect(self._on_refetch)
            
        # Delete Button
        self.delete_btn = QPushButton("Delete Cache Entry")
        self.delete_btn.setStyleSheet(_btn_style("#dc3545")) # Red
        self.delete_btn.setMinimumHeight(fs(40))
        self.delete_btn.clicked.connect(self._on_delete)
        
        # Close Button
        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet(_btn_style("#6c757d"))
        self.close_btn.setMinimumHeight(fs(40))
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.refetch_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)

    def _load_data(self):
        """Populate the info section and metadata labels with current data."""
        # 1. Update QRZ Panel
        norm_data = _normalize_qrz(self.row_data)
        self.info_section.update_data(norm_data)
        
        # 2. Update Metadata Labels
        self.meta_vals['callsign'].setText(self.callsign)
        self.meta_vals['cached_on'].setText(self.row_data['insert_date'])
        
        insert_dt = datetime.fromisoformat(self.row_data['insert_date'])
        age_days = (datetime.now(timezone.utc) - insert_dt).days
        
        status = "Good"
        status_bg = None
        status_fg = self.data_fg
        
        if self.row_data['active'] == 0:
            status = "Expired"
            status_bg = "#dc3545" # Red
            status_fg = "#ffffff" # White
        elif age_days >= CACHE_DAYS:
            status = "Expired/Unknown"
            status_bg = "#6c757d" # Grey
            status_fg = "#000000" # Black
            
        def _style_val(key, text, bg, fg):
            lbl = self.meta_vals[key]
            lbl.setText(text)
            text_color = fg if fg else self.data_fg
            style = f"color: {text_color}; border: none;"
            if bg:
                style += f" background-color: {bg}; padding: 2px 5px; border-radius: 3px;"
            else:
                style += " background: transparent;"
            lbl.setStyleSheet(style)

        _style_val('age', f"{age_days} days", status_bg, status_fg)
        _style_val('status', status, status_bg, status_fg)

    def _on_refetch(self):
        """Trigger a background lookup to refresh the cache."""
        self.refetch_btn.setEnabled(False)
        self.error_label.setVisible(False)
        self.refetch_btn.setText("Fetching...")
        
        is_active, user, pwd = load_qrz_config()
        from qrz_client import QRZClient
        
        class CustomFetchThread(QtCore.QThread):
            result_ready = pyqtSignal(object)
            def run(self):
                try:
                    client = QRZClient(user, pwd)
                    res = client.lookup(self.parent().callsign, use_cache=False)
                    self.result_ready.emit(res)
                except Exception as e:
                    self.result_ready.emit(str(e))
                    
        self.fetch_thread = CustomFetchThread(self)
        self.fetch_thread.result_ready.connect(self._on_refetch_finished)
        self.fetch_thread.start()

    def _on_refetch_finished(self, result):
        self.refetch_btn.setEnabled(True)
        self.refetch_btn.setText("Re-fetch from QRZ")
        
        if isinstance(result, str): # Error message
            self.error_label.setText(f"Fetch failed: {result}")
            self.error_label.setVisible(True)
        elif result:
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM qrz WHERE callsign = ?", (self.callsign,)).fetchone()
                conn.close()
                if row:
                    self.row_data = dict(row)
                    self._load_data()
                    self.data_refetched.emit(self.row_data) # Notify parent
                    # User feedback
                    self.error_label.setText("Successfully refreshed!")
                    self.error_label.setStyleSheet("color: #28a745; font-weight: bold; border: none; background: transparent;")
                    self.error_label.setVisible(True)
            except Exception as e:
                self.error_label.setText(f"DB Error after fetch: {e}")
                self.error_label.setVisible(True)
        else:
            self.error_label.setText("Callsign not found or lookup failed.")
            self.error_label.setVisible(True)

    def _on_delete(self):
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete the cached data for {self.callsign}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM qrz WHERE callsign = ?", (self.callsign,))
                conn.commit()
                conn.close()
                self.done(2)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete entry: {e}")

class QRZCacheViewer(QtWidgets.QMainWindow):
    """Main window for the QRZ Cache Viewer."""
    
    def __init__(self, panel_bg="#f5f5f5", panel_fg="#333333", data_bg="#FFF5E1", data_fg="#000000"):
        super().__init__()
        self.panel_bg = panel_bg
        self.panel_fg = panel_fg
        self.data_bg = data_bg
        self.data_fg = data_fg
        
        self.setWindowTitle("CommStat - QRZ Cache Viewer")
        self.setMinimumSize(fs(1000), fs(700))
        
        self._apply_main_style()
        self._init_ui()
        self.refresh_data()

    def _apply_main_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {self.panel_bg};
                color: {self.panel_fg};
            }}
            QWidget {{
                background-color: {self.panel_bg};
                color: {self.panel_fg};
            }}
            QLabel {{
                background-color: transparent;
                color: {self.panel_fg};
            }}
            QLineEdit {{
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 5px;
            }}
            QTableWidget {{
                background-color: {self.data_bg};
                color: {self.data_fg};
                gridline-color: #cccccc;
                border: 1px solid #cccccc;
            }}
            QTableWidget::item {{
                color: {self.data_fg};
            }}
            QTableWidget::item:selected {{
                background-color: #0078d7;
                color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: {self.panel_bg};
                color: {self.panel_fg};
                font-weight: bold;
                border: 1px solid #cccccc;
                padding: 4px;
            }}
        """)

    def _init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 1. Toolbar area
        toolbar = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh Table")
        self.refresh_btn.setStyleSheet(_btn_style("#0078d7"))
        self.refresh_btn.clicked.connect(self.refresh_data)
        toolbar.addWidget(self.refresh_btn)
        
        toolbar.addSpacing(fs(20))
        
        lbl_filter = QLabel("Filter by Callsign:")
        lbl_filter.setFont(QtGui.QFont("Arial", fs(11), QtGui.QFont.Bold))
        toolbar.addWidget(lbl_filter)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter callsign...")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_input)
        
        toolbar.addStretch()
        
        self.count_label = QLabel("Entries: 0")
        self.count_label.setFont(QtGui.QFont("Arial", fs(12), QtGui.QFont.Bold))
        toolbar.addWidget(self.count_label)
        
        main_layout.addLayout(toolbar)
        
        # 2. Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Callsign", "Name", "Location", "Cached On", "Age (Days)", "Status"
        ])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        
        header = self.table.horizontalHeader()
        # Optimized Sizing: Compact metadata, Stretched info
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # Callsign
        header.setSectionResizeMode(1, QHeaderView.Stretch)          # Name
        header.setSectionResizeMode(2, QHeaderView.Stretch)          # Location
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents) # Cached On
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents) # Age
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents) # Status
        
        main_layout.addWidget(self.table)

    def refresh_data(self):
        """Reload all data from the database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            self.full_data = conn.execute("SELECT * FROM qrz ORDER BY insert_date DESC").fetchall()
            conn.close()
            self._populate_table(self.full_data)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not load QRZ cache: {e}")

    def _populate_table(self, rows):
        self.table.setRowCount(0)
        self.count_label.setText(f"Entries: {len(rows)}")
        for i, row in enumerate(rows):
            self.table.insertRow(i)
            self._update_row_items(i, dict(row))

    def _update_row_items(self, i, row_dict):
        """Helper to populate or update items in a specific row."""
        # 0. Callsign
        item0 = QTableWidgetItem(row_dict['callsign'])
        item0.setData(Qt.UserRole, row_dict) 
        self.table.setItem(i, 0, item0)
        
        # 1. Name
        name = row_dict['name'] or ""
        self.table.setItem(i, 1, QTableWidgetItem(name))
        
        # 2. Location
        loc = f"{row_dict['city'] or ''}, {row_dict['state'] or ''} {row_dict['country'] or ''}".strip(", ")
        self.table.setItem(i, 2, QTableWidgetItem(loc))
        
        # 3. Cached On
        self.table.setItem(i, 3, QTableWidgetItem(row_dict['insert_date']))
        
        # 4. Age
        insert_dt = datetime.fromisoformat(row_dict['insert_date'])
        age_days = (datetime.now(timezone.utc) - insert_dt).days
        age_item = QTableWidgetItem(str(age_days))
        
        # 5. Status
        status = "Good"
        status_item = QTableWidgetItem(status)
        status_item.setForeground(QtGui.QColor(self.data_fg))
        
        if row_dict['active'] == 0:
            status = "Expired"
            status_item.setText(status)
            status_item.setBackground(QtGui.QColor("#dc3545")) # Red
            status_item.setForeground(QtGui.QColor("#ffffff")) # White
            age_item.setBackground(QtGui.QColor("#dc3545"))
            age_item.setForeground(QtGui.QColor("#ffffff"))
        elif age_days >= CACHE_DAYS:
            status = "Expired/Unknown"
            status_item.setText(status)
            status_item.setBackground(QtGui.QColor("#6c757d")) # Grey
            status_item.setForeground(QtGui.QColor("#000000")) # Black
            age_item.setBackground(QtGui.QColor("#6c757d"))
            age_item.setForeground(QtGui.QColor("#000000"))
        else:
            age_item.setForeground(QtGui.QColor(self.data_fg))
            
        self.table.setItem(i, 4, age_item)
        self.table.setItem(i, 5, status_item)

    def _on_filter_changed(self, text):
        text = text.upper()
        for i in range(self.table.rowCount()):
            callsign = self.table.item(i, 0).text().upper()
            self.table.setRowHidden(i, text not in callsign)

    def _on_row_double_clicked(self, item):
        row_idx = item.row()
        row_data = self.table.item(row_idx, 0).data(Qt.UserRole)
        
        dlg = QRZDetailDialog(
            row_data, 
            panel_bg=self.panel_bg, 
            panel_fg=self.panel_fg,
            data_bg=self.data_bg,
            data_fg=self.data_fg,
            parent=self
        )
        # Connect signal for live updates
        dlg.data_refetched.connect(lambda updated_data: self._update_row_items(row_idx, updated_data))
        
        result = dlg.exec_()
        if result == 2: # Deleted
            self.table.removeRow(row_idx)
            count = int(self.count_label.text().split(": ")[1])
            self.count_label.setText(f"Entries: {max(0, count-1)}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    viewer = QRZCacheViewer()
    viewer.show()
    sys.exit(app.exec_())
