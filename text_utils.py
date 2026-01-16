# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.

"""
Text normalization utilities for CommStat.
Provides abbreviation expansion and smart title case for messages.
"""

import re
import sqlite3
from typing import Dict, Optional

# Optional: PyEnchant for smart title case (acronym detection)
try:
    import enchant
    ENCHANT_AVAILABLE = True
except ImportError:
    ENCHANT_AVAILABLE = False

DATABASE_FILE = "traffic.db3"


def get_abbreviations() -> Dict[str, str]:
    """Load abbreviations from the database.

    Returns:
        Dictionary mapping abbreviations to their expansions.
    """
    try:
        with sqlite3.connect(DATABASE_FILE, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT abbrev, expansion FROM abbreviations")
            return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.Error:
        return {}


def expand_abbreviations(text: str, abbreviations: Optional[Dict[str, str]] = None) -> str:
    """Expand common JS8Call abbreviations in text.

    Args:
        text: The text to process.
        abbreviations: Optional dictionary of abbreviations. If None, loads from database.

    Returns:
        Text with abbreviations expanded.
    """
    if not text:
        return text

    if abbreviations is None:
        abbreviations = get_abbreviations()

    if not abbreviations:
        return text

    words = text.split()
    result = []

    for word in words:
        # Strip punctuation for matching
        stripped = word.strip(".,!?;:")
        suffix = word[len(stripped):] if len(word) > len(stripped) else ""

        # Check if word (case-insensitive) is an abbreviation
        upper_word = stripped.upper()
        if upper_word in abbreviations:
            result.append(abbreviations[upper_word] + suffix)
        else:
            result.append(word)

    return " ".join(result)


def smart_title_case(text: str, abbreviations: Optional[Dict[str, str]] = None) -> str:
    """Apply smart title case that preserves callsigns and known acronyms.

    Args:
        text: The text to process.
        abbreviations: Optional dictionary of abbreviations. If None, loads from database.

    Returns:
        Text with smart title case applied.
    """
    if not text:
        return text

    if abbreviations is None:
        abbreviations = get_abbreviations()

    # First expand abbreviations
    text = expand_abbreviations(text, abbreviations)

    # Callsign pattern - matches US amateur radio callsigns
    callsign_pattern = re.compile(r'\b[AKNW][A-Z]?[0-9][A-Z]{1,3}\b', re.IGNORECASE)

    # Common acronyms to keep uppercase
    acronyms = {
        'HF', 'VHF', 'UHF', 'FM', 'AM', 'SSB', 'CW', 'FT8', 'FT4',
        'JS8', 'PSK', 'RTTY', 'SSTV', 'ATV', 'APRS', 'DMR', 'DStar',
        'EME', 'QRP', 'QRO', 'QSO', 'QSL', 'QTH', 'QRZ', 'RST',
        'SWR', 'RF', 'DC', 'AC', 'LED', 'LCD', 'USB', 'LSB',
        'ANT', 'RX', 'TX', 'PTT', 'VOX', 'AGC', 'NB', 'NR',
        'ARRL', 'AMRRON', 'ARES', 'RACES', 'MARS', 'CAP', 'CERT',
        'FEMA', 'NWS', 'NOAA', 'NASA', 'FAA', 'FCC', 'ITU',
        'GPS', 'UTC', 'GMT', 'PDT', 'PST', 'EDT', 'EST', 'CDT', 'CST', 'MDT', 'MST',
        'USA', 'UK', 'EU', 'NATO', 'UN',
        'ID', 'OK', 'SOS', 'CQ', 'DX', 'FB', 'OM', 'XYL', 'YL',
        'SOTA', 'POTA', 'IOTA', 'WWV', 'WWVH', 'CHU',
        'NVIS', 'EMCOMM', 'AUXCOMM', 'SATERN', 'SKYWARN',
        'MHZ', 'KHZ', 'GHZ', 'DB', 'DBM',
        'II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'XI', 'XII',
        'SR', 'SRID', 'STATREP',
        # US State abbreviations (DC, ID, OK already listed above)
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    }

    # Find all callsigns in the text and preserve them
    callsigns = set()
    for match in callsign_pattern.finditer(text):
        callsigns.add(match.group().upper())

    # Split into words and process
    words = text.split()
    result = []

    for word in words:
        # Strip punctuation for checking
        stripped = word.strip(".,!?;:'\"")
        suffix = word[len(stripped):] if len(word) > len(stripped) else ""
        prefix = word[:len(word) - len(stripped) - len(suffix)] if word.startswith(("'", '"')) else ""
        if prefix:
            stripped = word[len(prefix):len(word) - len(suffix)] if suffix else word[len(prefix):]

        upper_stripped = stripped.upper()

        # Check if it's a callsign
        if upper_stripped in callsigns:
            result.append(prefix + upper_stripped + suffix)
        # Check if it's a known acronym
        elif upper_stripped in acronyms:
            result.append(prefix + upper_stripped + suffix)
        # Check if all caps and might be an acronym (2-5 chars, all letters)
        elif len(stripped) >= 2 and len(stripped) <= 5 and stripped.isalpha() and stripped.isupper():
            # Use enchant to check if it's a real word
            if ENCHANT_AVAILABLE:
                try:
                    d = enchant.Dict("en_US")
                    if not d.check(stripped.lower()):
                        # Not a real word, keep as acronym
                        result.append(prefix + upper_stripped + suffix)
                    else:
                        # Real word, title case it
                        result.append(prefix + stripped.capitalize() + suffix)
                except Exception:
                    result.append(prefix + stripped.capitalize() + suffix)
            else:
                # Without enchant, keep short all-caps as acronyms
                result.append(prefix + upper_stripped + suffix)
        else:
            # Regular word - title case
            result.append(prefix + stripped.capitalize() + suffix)

    return " ".join(result)


def normalize_text(text: str) -> str:
    """Apply full text normalization: expand abbreviations and smart title case.

    Args:
        text: The text to normalize.

    Returns:
        Normalized text.
    """
    abbreviations = get_abbreviations()
    return smart_title_case(text, abbreviations)
