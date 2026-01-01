# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
"""
qrz_client.py - QRZ.com XML API Client for CommStat-Improved

Provides callsign lookups via QRZ.com with local database caching
to minimize API calls.
"""

import configparser
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pathlib import Path


# Constants
QRZ_API_URL = "https://xmldata.qrz.com/xml/current/"
CACHE_DAYS = 30  # How long to cache callsign data
DB_PATH = Path(__file__).parent / "traffic.db3"
CONFIG_PATH = Path(__file__).parent / "config.ini"


def load_qrz_config() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Load QRZ configuration from config.ini.

    Returns:
        Tuple of (active, username, password)
    """
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        active = config.getboolean("QRZ", "active", fallback=False)
        username = config.get("QRZ", "username", fallback="").strip()
        password = config.get("QRZ", "password", fallback="").strip()

        return active, username or None, password or None
    except Exception as e:
        print(f"Error reading QRZ config: {e}")
        return False, None, None


def set_qrz_active(active: bool) -> bool:
    """
    Set the QRZ active flag in config.ini.

    Args:
        active: True to enable, False to disable

    Returns:
        True if successful
    """
    try:
        config = configparser.ConfigParser()
        config.read(CONFIG_PATH)

        if not config.has_section("QRZ"):
            config.add_section("QRZ")

        config.set("QRZ", "active", str(active))

        with open(CONFIG_PATH, "w") as f:
            config.write(f)

        return True
    except Exception as e:
        print(f"Error writing QRZ config: {e}")
        return False


# Legacy function for backwards compatibility
def load_qrz_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Load QRZ credentials from config.ini."""
    active, username, password = load_qrz_config()
    return username, password


class QRZClient:
    """
    QRZ.com XML API client with local caching.

    Caches callsign lookups in SQLite to reduce API calls.
    Session keys are reused until they expire.
    """

    def __init__(self, username: str = None, password: str = None):
        """
        Initialize QRZ client.

        Args:
            username: QRZ.com username
            password: QRZ.com password
        """
        self.username = username
        self.password = password
        self.session_key: Optional[str] = None
        self._init_cache_table()

    @staticmethod
    def is_active() -> bool:
        """Check if QRZ lookups are enabled in config."""
        active, _, _ = load_qrz_config()
        return active

    def _init_cache_table(self) -> None:
        """Create the QRZ cache table if it doesn't exist."""
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS qrz_cache (
                        callsign TEXT PRIMARY KEY,
                        fname TEXT,
                        name TEXT,
                        addr1 TEXT,
                        addr2 TEXT,
                        city TEXT,
                        state TEXT,
                        zip TEXT,
                        country TEXT,
                        lat REAL,
                        lon REAL,
                        grid TEXT,
                        county TEXT,
                        license_class TEXT,
                        email TEXT,
                        qsl_mgr TEXT,
                        eqsl TEXT,
                        lotw TEXT,
                        image_url TEXT,
                        bio_url TEXT,
                        cached_date TEXT
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            print(f"Error creating QRZ cache table: {e}")

    def _get_cached(self, callsign: str) -> Optional[Dict]:
        """
        Check cache for callsign data.

        Args:
            callsign: Callsign to look up

        Returns:
            Cached data dict or None if not found/expired
        """
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM qrz_cache WHERE callsign = ?",
                    (callsign.upper(),)
                )
                row = cursor.fetchone()

                if row:
                    # Check if cache is still valid
                    cached_date = datetime.fromisoformat(row["cached_date"])
                    age_days = (datetime.now(timezone.utc) - cached_date).days

                    if age_days < CACHE_DAYS:
                        return dict(row)
                    else:
                        # Cache expired, delete it
                        cursor.execute(
                            "DELETE FROM qrz_cache WHERE callsign = ?",
                            (callsign.upper(),)
                        )
                        conn.commit()

                return None
        except sqlite3.Error as e:
            print(f"Error reading QRZ cache: {e}")
            return None

    def _save_to_cache(self, data: Dict) -> None:
        """
        Save callsign data to cache.

        Args:
            data: Callsign data dict from QRZ
        """
        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO qrz_cache (
                        callsign, fname, name, addr1, addr2, city, state, zip,
                        country, lat, lon, grid, county, license_class, email,
                        qsl_mgr, eqsl, lotw, image_url, bio_url, cached_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data.get("call", "").upper(),
                    data.get("fname"),
                    data.get("name"),
                    data.get("addr1"),
                    data.get("addr2"),
                    data.get("addr2"),  # QRZ uses addr2 for city sometimes
                    data.get("state"),
                    data.get("zip"),
                    data.get("country"),
                    data.get("lat"),
                    data.get("lon"),
                    data.get("grid"),
                    data.get("county"),
                    data.get("class"),
                    data.get("email"),
                    data.get("qslmgr"),
                    data.get("eqsl"),
                    data.get("lotw"),
                    data.get("image"),
                    data.get("bio"),
                    datetime.now(timezone.utc).isoformat()
                ))
                conn.commit()
        except sqlite3.Error as e:
            print(f"Error saving to QRZ cache: {e}")

    def _api_request(self, params: Dict) -> Optional[ET.Element]:
        """
        Make API request to QRZ.

        Args:
            params: Query parameters

        Returns:
            XML root element or None on error
        """
        try:
            url = QRZ_API_URL + "?" + urllib.parse.urlencode(params, safe="")

            with urllib.request.urlopen(url, timeout=10) as response:
                xml_data = response.read().decode("utf-8")
                return ET.fromstring(xml_data)

        except urllib.error.URLError as e:
            print(f"QRZ API error: {e}")
            return None
        except ET.ParseError as e:
            print(f"QRZ XML parse error: {e}")
            return None

    def login(self, username: str = None, password: str = None) -> bool:
        """
        Authenticate with QRZ and get session key.

        Args:
            username: QRZ username (uses stored if not provided)
            password: QRZ password (uses stored if not provided)

        Returns:
            True if login successful
        """
        username = username or self.username
        password = password or self.password

        if not username or not password:
            print("QRZ: Username and password required")
            return False

        self.username = username
        self.password = password

        params = {
            "username": username,
            "password": password,
            "agent": "CommStat-Improved/2.5"
        }

        root = self._api_request(params)
        if root is None:
            print("QRZ: No response from API")
            return False

        # Debug: print raw XML response
        import xml.etree.ElementTree as ET
        print(f"QRZ Response: {ET.tostring(root, encoding='unicode')[:500]}")

        # Check for session key
        session = root.find(".//Session")
        if session is None:
            print("QRZ: No Session element in response")
            return False

        if session is not None:
            key_elem = session.find("Key")
            if key_elem is not None and key_elem.text:
                self.session_key = key_elem.text
                print(f"QRZ: Login successful")

                # Check subscription status
                sub_exp = session.find("SubExp")
                if sub_exp is not None and sub_exp.text:
                    print(f"QRZ: Subscription expires {sub_exp.text}")

                return True

            # Check for error - disable QRZ on auth failure
            error = session.find("Error")
            if error is not None and error.text:
                print(f"QRZ: {error.text}")
                # Disable QRZ on authentication errors
                if "invalid" in error.text.lower() or "password" in error.text.lower():
                    print("QRZ: Disabling QRZ lookups due to auth failure")
                    set_qrz_active(False)

        return False

    def lookup(self, callsign: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Look up a callsign.

        Args:
            callsign: Callsign to look up
            use_cache: Check cache first (default True)

        Returns:
            Dict with callsign data or None if not found
        """
        callsign = callsign.upper().strip()

        # Check cache first (works even if QRZ is disabled)
        if use_cache:
            cached = self._get_cached(callsign)
            if cached:
                print(f"QRZ: {callsign} found in cache")
                return cached

        # Check if QRZ is active before making API calls
        if not self.is_active():
            print("QRZ: Lookups disabled (active = False in config.ini)")
            return None

        # Need session key
        if not self.session_key:
            if not self.login():
                return None

        # Make API call
        params = {
            "s": self.session_key,
            "callsign": callsign
        }

        root = self._api_request(params)
        if root is None:
            return None

        # Check for errors (session expired, not found, etc.)
        session = root.find(".//Session")
        if session is not None:
            error = session.find("Error")
            if error is not None and error.text:
                if "Session Timeout" in error.text or "Invalid session" in error.text:
                    # Session expired, re-login and retry
                    self.session_key = None
                    if self.login():
                        return self.lookup(callsign, use_cache=False)
                print(f"QRZ: {error.text}")
                return None

        # Parse callsign data
        callsign_elem = root.find(".//Callsign")
        if callsign_elem is None:
            print(f"QRZ: {callsign} not found")
            return None

        # Extract all fields
        data = {}
        for child in callsign_elem:
            data[child.tag] = child.text

        # Save to cache
        self._save_to_cache(data)

        print(f"QRZ: {callsign} fetched from API")
        return data


# Command-line test
if __name__ == "__main__":
    import sys

    print("QRZ.com API Test")
    print("-" * 40)

    # Get config - try config.ini first
    active, username, password = load_qrz_config()

    print(f"QRZ Active: {active}")

    if username and password:
        print(f"Using credentials from config.ini (user: {username})")
    elif len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        active = True  # Override for command-line testing
    else:
        print("No credentials in config.ini")
        username = input("QRZ Username: ")
        password = input("QRZ Password: ")
        active = True  # Override for manual testing

    if not active:
        print("\nQRZ is disabled. Set active = True in config.ini to enable.")
        sys.exit(0)

    # Get callsign to lookup
    if len(sys.argv) > 3:
        callsign = sys.argv[3]
    elif len(sys.argv) == 2:
        callsign = sys.argv[1]
    else:
        callsign = input("Callsign to lookup (default AA7BQ): ") or "AA7BQ"

    # Test
    print(f"\nLooking up: {callsign}")
    client = QRZClient(username, password)

    print("Attempting login...")
    if client.login():
        print()
        result = client.lookup(callsign)

        if result:
            print()
            print(f"Results for {callsign}:")
            print("-" * 40)

            # Display key fields
            fields = [
                ("call", "Callsign"),
                ("fname", "First Name"),
                ("name", "Last Name"),
                ("addr1", "Address"),
                ("addr2", "City"),
                ("state", "State"),
                ("country", "Country"),
                ("grid", "Grid"),
                ("lat", "Latitude"),
                ("lon", "Longitude"),
                ("class", "License Class"),
                ("email", "Email"),
                ("eqsl", "eQSL"),
                ("lotw", "LoTW"),
            ]

            for key, label in fields:
                value = result.get(key)
                if value:
                    print(f"{label:15}: {value}")
        else:
            print(f"No results for {callsign}")
    else:
        print("Login failed - check credentials")
