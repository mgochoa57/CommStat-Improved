# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
"""
Debug Features for CommStat-Improved

This module contains all debug-related functionality.
To remove debug features, simply delete this file and remove its import.

Features:
- Get Call Activity: Requests call activity from all connected JS8Call instances
  and writes the results to {rig_name}-data-dump.txt files.

Usage:
1. Run CommStat with --debug flag: python little_gucci.py --debug
2. Debug menu appears in menu bar
3. Click "Get Call Activity" to dump call activity from all rigs
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt5 import QtWidgets

if TYPE_CHECKING:
    from little_gucci import MainWindow


class DebugFeatures:
    """
    Manages all debug features for CommStat-Improved.

    This class encapsulates debug functionality so it can be easily
    added or removed from the application.
    """

    def __init__(self, main_window: "MainWindow"):
        """
        Initialize debug features.

        Args:
            main_window: Reference to the main application window.
        """
        self.main_window = main_window
        self._pending_call_activity = set()

    def setup_debug_menu(self) -> None:
        """
        Create the Debug menu and add all debug options.

        Call this from MainWindow._setup_menu() when debug_mode is True.
        """
        # Create Debug dropdown menu
        self.debug_menu = QtWidgets.QMenu("Debug", self.main_window.menubar)
        self.main_window.menubar.addMenu(self.debug_menu)

        # Get Call Activity option
        get_call_activity_action = QtWidgets.QAction("Get Call Activity", self.main_window)
        get_call_activity_action.triggered.connect(self.on_get_call_activity)
        self.debug_menu.addAction(get_call_activity_action)

    def on_get_call_activity(self) -> None:
        """
        Request call activity from all connected JS8Call instances.

        Sends RX.GET_CALL_ACTIVITY to each connected rig. The response
        (RX.CALL_ACTIVITY) is handled by handle_call_activity_response().
        """
        connected_count = 0

        for rig_name, client in self.main_window.tcp_pool.clients.items():
            if client.is_connected():
                print(f"[{rig_name}] Requesting call activity...")
                client.send_message("RX.GET_CALL_ACTIVITY")
                self._pending_call_activity.add(rig_name)
                connected_count += 1

        if connected_count == 0:
            QtWidgets.QMessageBox.information(
                self.main_window, "No Connections",
                "No JS8Call instances are connected."
            )
        else:
            QtWidgets.QMessageBox.information(
                self.main_window, "Request Sent",
                f"Requested call activity from {connected_count} rig(s).\n"
                "Data will be written to {rig}-data-dump.txt files."
            )

    def handle_call_activity_response(self, rig_name: str, message: dict) -> None:
        """
        Handle RX.CALL_ACTIVITY response from JS8Call.

        Writes the call activity data to a text file.

        Args:
            rig_name: Name of the rig that sent the response.
            message: Full message containing call activity data.
        """
        # Remove from pending set
        self._pending_call_activity.discard(rig_name)

        # Create filename in the app directory
        filename = f"{rig_name}-data-dump.txt"
        filepath = Path(__file__).parent / filename

        try:
            with open(filepath, 'w') as f:
                f.write(f"Call Activity Dump for {rig_name}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")

                # Get the value which contains the call activity list
                value = message.get("value", [])

                if isinstance(value, list):
                    f.write(f"Total stations: {len(value)}\n\n")
                    for entry in value:
                        if isinstance(entry, dict):
                            callsign = entry.get("CALL", "Unknown")
                            grid = entry.get("GRID", "")
                            snr = entry.get("SNR", "")
                            utc = entry.get("UTC", 0)
                            f.write(f"Callsign: {callsign}\n")
                            if grid:
                                f.write(f"  Grid: {grid}\n")
                            if snr:
                                f.write(f"  SNR: {snr}\n")
                            if utc:
                                utc_str = datetime.utcfromtimestamp(utc / 1000).strftime('%Y-%m-%d %H:%M:%S')
                                f.write(f"  Last heard: {utc_str}\n")
                            f.write("\n")
                        else:
                            f.write(f"{entry}\n")
                else:
                    # Write raw JSON if not a list
                    f.write(json.dumps(message, indent=2))

            print(f"[{rig_name}] Call activity written to {filename}")

        except Exception as e:
            print(f"[{rig_name}] Error writing call activity dump: {e}")


def is_call_activity_message(msg_type: str) -> bool:
    """
    Check if a message type is a call activity response.

    Use this in js8_tcp_client.py to determine if a message
    should be forwarded to the main app.

    Args:
        msg_type: The message type string.

    Returns:
        True if this is a call activity message.
    """
    return msg_type == "RX.CALL_ACTIVITY"
