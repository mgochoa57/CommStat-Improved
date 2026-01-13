# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.
"""
connector_manager.py - JS8Call TCP Connector Database Manager

Manages database operations for JS8Call TCP connectors.
Supports up to 3 connectors with one designated as default.
"""

import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

# Constants
DATABASE_FILE = "traffic.db3"
MAX_CONNECTORS = 3
DEFAULT_TCP_PORT = 2442


class ConnectorManager:
    """Manages JS8Call TCP connector configuration in database."""

    def __init__(self, db_path: str = DATABASE_FILE):
        """
        Initialize ConnectorManager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path

    def init_connectors_table(self) -> None:
        """Create js8_connectors table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS js8_connectors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rig_name TEXT UNIQUE NOT NULL,
                        tcp_port INTEGER NOT NULL DEFAULT 2442,
                        comment TEXT,
                        date_added TEXT NOT NULL,
                        is_default INTEGER DEFAULT 0,
                        enabled INTEGER DEFAULT 1
                    )
                """)
                conn.commit()
                # Add enabled column if missing (for existing databases)
                self._add_enabled_column()
        except sqlite3.Error as e:
            print(f"Error initializing js8_connectors table: {e}")

    def _add_enabled_column(self) -> None:
        """Add enabled column to existing js8_connectors table if missing."""
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(js8_connectors)")
                columns = [col[1] for col in cursor.fetchall()]
                if "enabled" not in columns:
                    cursor.execute(
                        "ALTER TABLE js8_connectors ADD COLUMN enabled INTEGER DEFAULT 1"
                    )
                    conn.commit()
                    print("Added enabled column to js8_connectors")
        except sqlite3.Error as e:
            print(f"Error adding enabled column: {e}")

    def add_frequency_columns(self) -> None:
        """Add frequency column to StatRep_Data and messages_Data."""
        tables = ["StatRep_Data", "messages_Data"]
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                for table in tables:
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [col[1] for col in cursor.fetchall()]
                    if "frequency" not in columns:
                        cursor.execute(
                            f"ALTER TABLE {table} ADD COLUMN frequency INTEGER DEFAULT 0"
                        )
                        print(f"Added frequency column to {table}")
                conn.commit()
        except sqlite3.Error as e:
            print(f"Error adding frequency columns: {e}")

    def get_all_connectors(self, enabled_only: bool = False) -> List[Dict]:
        """
        Get all configured connectors.

        Args:
            enabled_only: If True, only return enabled connectors.

        Returns:
            List of connector dictionaries with keys:
            id, rig_name, tcp_port, comment, date_added, is_default, enabled
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if enabled_only:
                    cursor.execute("""
                        SELECT id, rig_name, tcp_port, comment, date_added, is_default, enabled
                        FROM js8_connectors
                        WHERE enabled = 1
                        ORDER BY is_default DESC, rig_name ASC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, rig_name, tcp_port, comment, date_added, is_default, enabled
                        FROM js8_connectors
                        ORDER BY is_default DESC, rig_name ASC
                    """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            print(f"Error getting connectors: {e}")
            return []

    def get_connector_by_id(self, connector_id: int) -> Optional[Dict]:
        """
        Get a connector by its ID.

        Args:
            connector_id: The connector's database ID.

        Returns:
            Connector dictionary or None if not found.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, rig_name, tcp_port, comment, date_added, is_default, enabled
                    FROM js8_connectors
                    WHERE id = ?
                """, (connector_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error getting connector by ID: {e}")
            return None

    def get_connector_by_name(self, rig_name: str) -> Optional[Dict]:
        """
        Get a connector by its rig name.

        Args:
            rig_name: The rig name to look up.

        Returns:
            Connector dictionary or None if not found.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, rig_name, tcp_port, comment, date_added, is_default, enabled
                    FROM js8_connectors
                    WHERE rig_name = ?
                """, (rig_name,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error getting connector by name: {e}")
            return None

    def get_default_connector(self) -> Optional[Dict]:
        """
        Get the default connector.

        Returns:
            Default connector dictionary or None if no default set.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, rig_name, tcp_port, comment, date_added, is_default, enabled
                    FROM js8_connectors
                    WHERE is_default = 1
                """)
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            print(f"Error getting default connector: {e}")
            return None

    def add_connector(
        self,
        rig_name: str,
        tcp_port: int = DEFAULT_TCP_PORT,
        comment: str = "",
        set_as_default: bool = False
    ) -> bool:
        """
        Add a new connector.

        Args:
            rig_name: Name for the rig (must be unique).
            tcp_port: TCP port for JS8Call (default 2442).
            comment: Optional description.
            set_as_default: If True, set this as the default connector.

        Returns:
            True if successful, False otherwise.
        """
        # Check max connectors limit
        if self.get_connector_count() >= MAX_CONNECTORS:
            print(f"Cannot add connector: maximum of {MAX_CONNECTORS} reached")
            return False

        # Validate rig_name
        rig_name = rig_name.strip()
        if not rig_name:
            print("Cannot add connector: rig name is required")
            return False

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()

                # If setting as default, clear existing default first
                if set_as_default:
                    cursor.execute("UPDATE js8_connectors SET is_default = 0")

                # If this is the first connector, make it default
                cursor.execute("SELECT COUNT(*) FROM js8_connectors")
                count = cursor.fetchone()[0]
                is_default = 1 if (set_as_default or count == 0) else 0

                date_added = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("""
                    INSERT INTO js8_connectors
                    (rig_name, tcp_port, comment, date_added, is_default)
                    VALUES (?, ?, ?, ?, ?)
                """, (rig_name, tcp_port, comment, date_added, is_default))

                conn.commit()
                print(f"Added connector: {rig_name} on port {tcp_port}")
                return True

        except sqlite3.IntegrityError:
            print(f"Cannot add connector: rig name '{rig_name}' already exists")
            return False
        except sqlite3.Error as e:
            print(f"Error adding connector: {e}")
            return False

    def update_connector(
        self,
        connector_id: int,
        rig_name: str,
        tcp_port: int,
        comment: str = ""
    ) -> bool:
        """
        Update an existing connector.

        Args:
            connector_id: The connector's database ID.
            rig_name: New rig name.
            tcp_port: New TCP port.
            comment: New comment.

        Returns:
            True if successful, False otherwise.
        """
        rig_name = rig_name.strip()
        if not rig_name:
            print("Cannot update connector: rig name is required")
            return False

        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE js8_connectors
                    SET rig_name = ?, tcp_port = ?, comment = ?
                    WHERE id = ?
                """, (rig_name, tcp_port, comment, connector_id))
                conn.commit()

                if cursor.rowcount > 0:
                    print(f"Updated connector ID {connector_id}")
                    return True
                else:
                    print(f"Connector ID {connector_id} not found")
                    return False

        except sqlite3.IntegrityError:
            print(f"Cannot update: rig name '{rig_name}' already exists")
            return False
        except sqlite3.Error as e:
            print(f"Error updating connector: {e}")
            return False

    def remove_connector(self, connector_id: int) -> bool:
        """
        Remove a connector by ID.

        Cannot remove the default connector or the last connector.

        Args:
            connector_id: The connector's database ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()

                # Check if this is the default connector
                cursor.execute(
                    "SELECT is_default FROM js8_connectors WHERE id = ?",
                    (connector_id,)
                )
                row = cursor.fetchone()
                if not row:
                    print(f"Connector ID {connector_id} not found")
                    return False

                if row[0] == 1:
                    print("Cannot remove the default connector")
                    return False

                # Check if this is the last connector
                cursor.execute("SELECT COUNT(*) FROM js8_connectors")
                count = cursor.fetchone()[0]
                if count <= 1:
                    print("Cannot remove the last connector")
                    return False

                # Remove the connector
                cursor.execute(
                    "DELETE FROM js8_connectors WHERE id = ?",
                    (connector_id,)
                )
                conn.commit()

                print(f"Removed connector ID {connector_id}")
                return True

        except sqlite3.Error as e:
            print(f"Error removing connector: {e}")
            return False

    def set_default(self, connector_id: int) -> bool:
        """
        Set a connector as the default.

        Args:
            connector_id: The connector's database ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()

                # Clear existing default
                cursor.execute("UPDATE js8_connectors SET is_default = 0")

                # Set new default
                cursor.execute(
                    "UPDATE js8_connectors SET is_default = 1 WHERE id = ?",
                    (connector_id,)
                )
                conn.commit()

                if cursor.rowcount > 0:
                    print(f"Set connector ID {connector_id} as default")
                    return True
                else:
                    print(f"Connector ID {connector_id} not found")
                    return False

        except sqlite3.Error as e:
            print(f"Error setting default connector: {e}")
            return False

    def get_connector_count(self) -> int:
        """
        Get the total number of configured connectors.

        Returns:
            Number of connectors.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM js8_connectors")
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"Error getting connector count: {e}")
            return 0

    def has_connectors(self) -> bool:
        """
        Check if any connectors are configured.

        Returns:
            True if at least one connector exists.
        """
        return self.get_connector_count() > 0

    def set_enabled(self, connector_id: int, enabled: bool) -> bool:
        """
        Enable or disable a connector.

        Args:
            connector_id: The connector's database ID.
            enabled: True to enable, False to disable.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE js8_connectors SET enabled = ? WHERE id = ?",
                    (1 if enabled else 0, connector_id)
                )
                conn.commit()

                if cursor.rowcount > 0:
                    status = "enabled" if enabled else "disabled"
                    print(f"Connector ID {connector_id} {status}")
                    return True
                else:
                    print(f"Connector ID {connector_id} not found")
                    return False

        except sqlite3.Error as e:
            print(f"Error setting connector enabled state: {e}")
            return False

    def is_enabled(self, connector_id: int) -> bool:
        """
        Check if a connector is enabled.

        Args:
            connector_id: The connector's database ID.

        Returns:
            True if enabled, False if disabled or not found.
        """
        connector = self.get_connector_by_id(connector_id)
        if connector:
            return connector.get("enabled", 1) == 1
        return False
