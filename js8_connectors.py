# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
"""
js8_connectors2.py - JS8 Connectors Management Dialog

Modern rewrite of the JS8 Connectors dialog. Displays a table of configured
JS8Call TCP connectors with Add, Edit, Delete, and Reconnect actions.
Supports connections to JS8Call instances on remote computers via the Server field.
"""

import os
from typing import Optional

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QAbstractItemView,
)

from connector_manager import ConnectorManager, DEFAULT_SERVER, DEFAULT_TCP_PORT
from constants import DEFAULT_COLORS

# ── Constants ──────────────────────────────────────────────────────────────────

_PROG_BG   = DEFAULT_COLORS.get("program_background",   "#A52A2A")
_PROG_FG   = DEFAULT_COLORS.get("program_foreground",   "#FFFFFF")
_PANEL_BG  = DEFAULT_COLORS.get("panel_background",     "#DDDDDD")
_TITLE_BG  = DEFAULT_COLORS.get("title_bar_background", "#F07800")
_TITLE_FG  = DEFAULT_COLORS.get("title_bar_foreground", "#FFFFFF")
_DATA_BG   = DEFAULT_COLORS.get("data_background",      "#F8F6F4")
_DATA_FG   = DEFAULT_COLORS.get("data_foreground",      "#000000")

_COL_ADD        = "#28a745"
_COL_EDIT       = "#007bff"
_COL_DELETE     = "#dc3545"
_COL_RECONNECT  = "#17a2b8"
_COL_CLOSE      = "#555555"
_COL_SAVE       = "#28a745"
_COL_CANCEL     = "#555555"

_COL_CONNECTED    = "#1a7f37"   # dark green text
_COL_DISCONNECTED = "#cc0000"   # red text
_COL_DISABLED     = "#888888"   # gray text

_WIN_W          = 620
_WIN_H_LIST     = 400           # height when form is hidden
_WIN_H_FORM     = 660           # height when form is visible

_TABLE_COLS = ["Rig Name", "Server", "Port", "State", "Status", "Comment"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _btn(label: str, color: str, min_w: int = 90) -> QPushButton:
    b = QPushButton(label)
    b.setMinimumWidth(min_w)
    b.setStyleSheet(
        f"QPushButton {{ background-color:{color}; color:#ffffff; border:none;"
        f" padding:6px 14px; border-radius:4px; font-family:Roboto; font-size:15px;"
        f" font-weight:bold; }}"
        f"QPushButton:hover {{ background-color:{color}; opacity:0.9; }}"
        f"QPushButton:pressed {{ background-color:{color}; }}"
        f"QPushButton:disabled {{ background-color:#cccccc; color:#888888; }}"
    )
    return b


def _lbl_font(px: int = 15, bold: bool = True) -> QtGui.QFont:
    f = QtGui.QFont("Roboto", -1, QtGui.QFont.Bold if bold else QtGui.QFont.Normal)
    f.setPixelSize(px)
    return f


def _mono_font(px: int = 15) -> QtGui.QFont:
    f = QtGui.QFont("Kode Mono")
    f.setPixelSize(px)
    return f


def _input(placeholder: str = "", default: str = "", max_len: int = 0) -> QLineEdit:
    e = QLineEdit()
    if placeholder:
        e.setPlaceholderText(placeholder)
    if default:
        e.setText(default)
    if max_len:
        e.setMaxLength(max_len)
    e.setFont(_mono_font(15))
    e.setMinimumHeight(30)
    e.setStyleSheet(
        "QLineEdit { background-color:white; color:#333333; border:1px solid #cccccc;"
        " border-radius:4px; padding:2px 6px; }"
        "QLineEdit:focus { border:1px solid #007bff; }"
    )
    return e


# ── Dialog ─────────────────────────────────────────────────────────────────────

class JS8ConnectorsDialog(QDialog):
    """JS8 Connectors management dialog — list, add, edit, delete, reconnect."""

    def __init__(
        self,
        connector_manager: ConnectorManager,
        tcp_pool,
        parent=None
    ):
        super().__init__(parent)
        self.connector_manager = connector_manager
        self.tcp_pool = tcp_pool
        self._edit_id: Optional[int] = None   # None = adding, int = editing

        self.setWindowTitle("JS8 Connectors")
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )
        self.setFixedSize(_WIN_W, _WIN_H_LIST)
        if os.path.exists("radiation-32.png"):
            self.setWindowIcon(QtGui.QIcon("radiation-32.png"))

        self._setup_ui()
        self._load_connectors()

        # Refresh table whenever any connection state changes (async connect/disconnect)
        if self.tcp_pool and hasattr(self.tcp_pool, "any_connection_changed"):
            self.tcp_pool.any_connection_changed.connect(self._on_connection_changed)

    # ── UI construction ────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QDialog {{ background-color:{_PANEL_BG}; }}")

        body = QVBoxLayout(self)
        body.setContentsMargins(15, 15, 15, 15)
        body.setSpacing(10)

        # ── Title ─────────────────────────────────────────────────────────────
        title_lbl = QLabel("JS8 Connectors")
        title_lbl.setAlignment(Qt.AlignCenter)
        tf = QtGui.QFont("Roboto Slab", -1, QtGui.QFont.Black)
        tf.setPixelSize(20)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet(
            f"QLabel {{ background-color:{_PROG_BG}; color:{_PROG_FG};"
            " padding-top:9px; padding-bottom:9px; }}"
        )
        body.addWidget(title_lbl)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget(0, len(_TABLE_COLS))
        self.table.setHorizontalHeaderLabels(_TABLE_COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(160)

        # Header style
        hh = self.table.horizontalHeader()
        hf = QtGui.QFont("Roboto", -1, QtGui.QFont.Bold)
        hf.setPixelSize(15)
        hh.setFont(hf)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Rig Name
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Server
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Port
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # State
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Status
        hh.setSectionResizeMode(5, QHeaderView.Stretch)           # Comment

        self.table.setStyleSheet(
            f"QTableWidget {{ background-color:{_DATA_BG}; alternate-background-color:{_DATA_BG};"
            f" gridline-color:#cccccc; color:{_DATA_FG}; }}"
            f"QTableWidget::item {{ padding:4px 6px; }}"
            f"QHeaderView::section {{ background-color:{_TITLE_BG}; color:{_TITLE_FG};"
            f" padding:5px 6px; border:none; font-family:Roboto; font-size:15px;"
            f" font-weight:bold; }}"
            f"QTableWidget::item:selected {{ background-color:#cce5ff; color:#000000; }}"
        )
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_edit)
        body.addWidget(self.table)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_add       = _btn("Add",       _COL_ADD,       80)
        self.btn_edit      = _btn("Edit",      _COL_EDIT,      80)
        self.btn_delete    = _btn("Delete",    _COL_DELETE,    80)
        self.btn_reconnect = _btn("Reconnect", _COL_RECONNECT, 100)
        self.btn_close     = _btn("Close",     _COL_CLOSE,     80)

        self.btn_edit.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.btn_reconnect.setEnabled(False)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_reconnect.clicked.connect(self._on_reconnect)
        self.btn_close.clicked.connect(self.accept)

        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_reconnect)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_close)
        body.addLayout(btn_row)

        # ── Add/Edit form (hidden by default) ─────────────────────────────────
        self.form_frame = QFrame()
        self.form_frame.setFrameShape(QFrame.StyledPanel)
        self.form_frame.setStyleSheet(
            f"QFrame {{ background-color:#f9f9f9; border:1px solid #cccccc;"
            f" border-radius:6px; }}"
        )
        form_layout = QVBoxLayout(self.form_frame)
        form_layout.setContentsMargins(14, 10, 14, 10)
        form_layout.setSpacing(8)

        self.form_title_lbl = QLabel("Add Connector")
        self.form_title_lbl.setFont(_lbl_font(15, bold=True))
        self.form_title_lbl.setStyleSheet(f"color:{_PROG_BG}; border:none;")
        form_layout.addWidget(self.form_title_lbl)

        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setColumnStretch(1, 1)

        def _row_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFont(_lbl_font(15, bold=True))
            lbl.setStyleSheet("color:#333333; border:none;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return lbl

        self.f_rig     = _input("e.g. IC-7300, FTDX10", max_len=20)
        self.f_server  = _input(default=DEFAULT_SERVER)
        self.f_port    = _input(default=str(DEFAULT_TCP_PORT), max_len=5)
        self.f_state   = _input("e.g. TX", max_len=2)
        self.f_comment = _input("Optional Description", max_len=60)

        self.f_state.textChanged.connect(
            lambda t: self.f_state.setText(t.upper()) if t != t.upper() else None
        )

        grid.addWidget(_row_label("Rig Name:"), 0, 0)
        grid.addWidget(self.f_rig,              0, 1)
        grid.addWidget(_row_label("Server:"),   1, 0)
        grid.addWidget(self.f_server,           1, 1)
        grid.addWidget(_row_label("Port:"),     2, 0)
        grid.addWidget(self.f_port,             2, 1)
        grid.addWidget(_row_label("State:"),    3, 0)
        grid.addWidget(self.f_state,            3, 1)
        grid.addWidget(_row_label("Comment:"),  4, 0)
        grid.addWidget(self.f_comment,          4, 1)

        form_layout.addLayout(grid)

        # Form action buttons
        form_btn_row = QHBoxLayout()
        form_btn_row.setSpacing(8)
        self.btn_save   = _btn("Save Connector", _COL_SAVE,   130)
        self.btn_cancel = _btn("Cancel",         _COL_CANCEL,  80)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_cancel.clicked.connect(self._on_cancel)
        form_btn_row.addStretch()
        form_btn_row.addWidget(self.btn_save)
        form_btn_row.addWidget(self.btn_cancel)
        form_layout.addLayout(form_btn_row)

        self.form_frame.setVisible(False)
        body.addWidget(self.form_frame)

        # ── Tip / Note ────────────────────────────────────────────────────────
        tip_lbl = QLabel(
            "<i><b><span style='color:#AA0000'>Tip:</span></b> Enable both TCP settings"
            " in JS8Call under File &gt; Settings &gt; Reporting</i><br>"
            "<i><b><span style='color:#AA0000'>Note:</span></b> Each connector requires"
            " a unique port</i>"
        )
        tip_lbl.setFont(_lbl_font(15, bold=False))
        tip_lbl.setWordWrap(True)
        tip_lbl.setStyleSheet("color:#333333;")
        body.addWidget(tip_lbl)

        # Wire up save-button enable/disable
        self.f_rig.textChanged.connect(self._on_form_changed)
        self.f_port.textChanged.connect(self._on_form_changed)

    # ── Data loading ───────────────────────────────────────────────────────────

    def _load_connectors(self) -> None:
        """Reload the connector table from the database."""
        connectors = self.connector_manager.get_all_connectors()
        status_map: dict = {}
        if self.tcp_pool and hasattr(self.tcp_pool, "get_connection_status"):
            status_map = self.tcp_pool.get_connection_status()

        self.table.setRowCount(0)
        mono = _mono_font(15)
        bold_mono = _mono_font(15)
        bold_mono.setBold(True)

        for row_idx, conn in enumerate(connectors):
            self.table.insertRow(row_idx)

            is_default = bool(conn.get("is_default", 0))
            is_enabled = bool(conn.get("enabled", 1))
            rig        = conn.get("rig_name", "")
            server     = conn.get("server",   DEFAULT_SERVER)
            port       = str(conn.get("tcp_port", DEFAULT_TCP_PORT))
            state      = conn.get("state",    "") or ""
            comment    = conn.get("comment",  "") or ""

            if not is_enabled:
                status_text  = "Disabled"
                status_color = _COL_DISABLED
            elif status_map.get(rig, False):
                status_text  = "Connected"
                status_color = _COL_CONNECTED
            else:
                status_text  = "Disconnected"
                status_color = _COL_DISCONNECTED

            cell_font = bold_mono if is_default else mono
            values = [rig, server, port, state, status_text, comment]

            for col_idx, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFont(cell_font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                if col_idx == 4:   # Status column — colored text
                    item.setForeground(QtGui.QColor(status_color))

                self.table.setItem(row_idx, col_idx, item)

            # Store connector id in row's first item UserRole
            self.table.item(row_idx, 0).setData(Qt.UserRole, conn["id"])

        self._on_selection_changed()

    # ── Selection ──────────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        has_sel = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_reconnect.setEnabled(has_sel)

    def _selected_connector_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    # ── Form helpers ───────────────────────────────────────────────────────────

    def _show_form(self, title: str) -> None:
        self.form_title_lbl.setText(title)
        self.form_frame.setVisible(True)
        self.setFixedSize(_WIN_W, _WIN_H_FORM)
        self.f_rig.setFocus()

    def _hide_form(self) -> None:
        self.form_frame.setVisible(False)
        self.setFixedSize(_WIN_W, _WIN_H_LIST)
        self._edit_id = None

    def _clear_form(self) -> None:
        self.f_rig.clear()
        self.f_server.setText(DEFAULT_SERVER)
        self.f_port.setText(str(DEFAULT_TCP_PORT))
        self.f_state.clear()
        self.f_comment.clear()

    def _on_form_changed(self) -> None:
        rig_ok  = bool(self.f_rig.text().strip())
        port_ok = self.f_port.text().strip().isdigit()
        self.btn_save.setEnabled(rig_ok and port_ok)

    # ── Actions ────────────────────────────────────────────────────────────────

    def _on_add(self) -> None:
        self._edit_id = None
        self._clear_form()
        self._show_form("Add Connector")

    def _on_edit(self) -> None:
        cid = self._selected_connector_id()
        if cid is None:
            return
        conn = self.connector_manager.get_connector_by_id(cid)
        if not conn:
            return
        self._edit_id = cid
        self.f_rig.setText(conn.get("rig_name", ""))
        self.f_server.setText(conn.get("server", DEFAULT_SERVER) or DEFAULT_SERVER)
        self.f_port.setText(str(conn.get("tcp_port", DEFAULT_TCP_PORT)))
        self.f_state.setText(conn.get("state", "") or "")
        self.f_comment.setText(conn.get("comment", "") or "")
        self._show_form("Edit Connector")

    def _on_cancel(self) -> None:
        self._hide_form()

    def _on_save(self) -> None:
        rig     = self.f_rig.text().strip()
        server  = self.f_server.text().strip() or DEFAULT_SERVER
        port    = int(self.f_port.text().strip())
        state   = self.f_state.text().strip().upper()[:2]
        comment = self.f_comment.text().strip()

        if self._edit_id is None:
            ok = self.connector_manager.add_connector(
                rig_name=rig, tcp_port=port, state=state,
                comment=comment, server=server
            )
            action = "add"
        else:
            ok = self.connector_manager.update_connector(
                connector_id=self._edit_id, rig_name=rig,
                tcp_port=port, state=state, comment=comment, server=server
            )
            action = "update"

        if ok:
            if self.tcp_pool and hasattr(self.tcp_pool, "refresh_connections"):
                self.tcp_pool.refresh_connections()
            self._hide_form()
            self._load_connectors()
        else:
            QMessageBox.critical(
                self, "Error",
                f"Could not {action} connector.\n"
                "Rig name may already be in use."
            )

    def _on_delete(self) -> None:
        cid = self._selected_connector_id()
        if cid is None:
            return

        row  = self.table.currentRow()
        name = self.table.item(row, 0).text() if self.table.item(row, 0) else "this connector"

        reply = QMessageBox.question(
            self, "Delete Connector",
            f"Delete connector '{name}'?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if reply != QMessageBox.Yes:
            return

        ok = self.connector_manager.remove_connector(cid)
        if ok:
            if self.tcp_pool and hasattr(self.tcp_pool, "refresh_connections"):
                self.tcp_pool.refresh_connections()
            self._load_connectors()
        else:
            QMessageBox.critical(
                self, "Cannot Delete",
                "Cannot delete this connector.\n\n"
                "You cannot delete the default connector or the last connector."
            )

    def _on_connection_changed(self, _rig_name: str, _connected: bool) -> None:
        """Refresh table when any TCP connection state changes."""
        self._load_connectors()

    def closeEvent(self, event) -> None:
        if self.tcp_pool and hasattr(self.tcp_pool, "any_connection_changed"):
            try:
                self.tcp_pool.any_connection_changed.disconnect(self._on_connection_changed)
            except RuntimeError:
                pass
        super().closeEvent(event)

    def _on_reconnect(self) -> None:
        cid = self._selected_connector_id()
        if cid is None:
            return
        # Re-enable the connector in case it was auto-disabled
        self.connector_manager.set_enabled(cid, True)
        if self.tcp_pool and hasattr(self.tcp_pool, "refresh_connections"):
            self.tcp_pool.refresh_connections()
        self._load_connectors()
