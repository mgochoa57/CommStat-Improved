# CommStat / CommStatOne / CommStat-Improved  
Situational Awareness Companion Software for JS8Call

---

## Project Context and Intended Use

CommStat and its related projects were created to support **organized HF digital communications** using **JS8Call**, with a focus on situational awareness, structured reporting, and group coordination.

Over time, these tools have been used by members and participants associated with organizations and communities such as **AmRRON**, **MPURN**, **PREPPERNET**, and other independent emergency communications and preparedness groups.

- AmRRON: https://amrron.com/  
- MPURN: https://mpurn.wordpress.com/  
- PREPPERNET: https://preppernet.com/

> **Important Notice**  
> References to AmRRON, MPURN, PREPPERNET, or any other organization are **historical and descriptive only** and do **not** imply endorsement, sponsorship, or official affiliation unless explicitly stated by those organizations.

---

## Project Lineage Overview

The CommStat ecosystem consists of multiple related projects developed independently over time:

- **CommStat** – Original application concept and implementation  
- **CommStatOne** – Python-based, cross-platform rewrite  
- **CommStat-Improved** – Community-driven rebuild and modernization effort  

Each project builds upon earlier ideas while maintaining compatibility with **JS8Call** and its API.

---

# CommStatOne Version 1.0.5  
**Released:** 10/15/2023

CommStatOne Version 1.0.5 is add-on software for JS8Call groups.  
CommStatOne is a Python version of the CommStat software **designed to run on Windows 10 and Linux**.

- **Author:** Daniel M. Hurd ~W5DMH  
- **Credit:** Special credit to **L. Hutchinson (M0IAX), England**, for the *JS8CallAPISupport* script, which enables message transmission.  
  Additional JS8Call tools: https://github.com/m0iax  
- **Repository:** https://github.com/W5DMH/commstatone

---

# CommStat Version 2.0.0  
**Released:** 6/05/2025

- **Author:** Rich W. Whittington ~KD9DSS  
- **ZIP Update Package (applies to CommStat 1.0.5 only):**  
  https://amrron.com/wp-content/uploads/2025/07/Download-2025-07-18T18_31_39.zip 

- **Highlight:** Added the AmRRON StatRep 5.1 form

---

# CommStat Version 2.3.0  
**Released:** 11/17/2025

- **Author:** Rich W. Whittington ~KD9DSS  
- **ZIP Update Package (must be applied after CommStat 2.2.0):**  
  https://amrron.com/2025/11/17/commstat-v2-3-offline-mapping/
 
- **Highlight:** Introduced Offline Maps

---

# CommStat-Improved Version 2.5.0  
**Released:** 12/25/2025

- **Author:** Manuel G. Ochoa ~N0DDK  
- **AI Code Assistant:** Claude (Anthropic), ChatGPT (OpenAI)

---

## Project rebuild and modernization effort – December 2025  
### Summary of Changes and Improvements

1. NEW MAIN APPLICATION
--------------------------------------
- Complete rebuild of commstat.py using Python best practices
- Clean class-based architecture:
  - ConfigManager: Handles config.ini loading with validation
  - DatabaseManager: Centralized SQLite operations
  - MainWindow: PyQt5 GUI with organized component setup
- Type hints and docstrings throughout
- Constants defined at top of file (no magic numbers/strings)
- Color validation with fallback to defaults for invalid config values
- Menu bar styling with configurable colors and centered text
- Filter labels use size policy to allow window resizing
- 20-second auto-refresh for StatRep, messages, live feed, and map

2. DATAREADER REFACTORING (datareader.py)
-----------------------------------------
- Reduced from 675 to ~620 lines while adding features
- Replaced 7 global variables with Config class
- Consolidated 4+ database connections into single connection
- Created helper methods to eliminate code duplication:
  - extract_callsign(): Replaces 6 duplicated blocks
  - parse_statrep_fields(): Parses 12-character status code
  - validate_statrep_fields(): Validates all fields in one call
- Added constants for message type markers:
  - MSG_BULLETIN = "{^%}"
  - MSG_STATREP = "{&%}"
  - MSG_FORWARDED_STATREP = "{F%}"
  - MSG_MARQUEE = "{*%}"
  - MSG_CHECKIN = "{~%}"
- Removed unused imports (numpy, re)
- Removed 100+ lines of commented/dead code
- Added type hints and docstrings

3. MODULE INTEGRATION (datareader + commstat2)
----------------------------------------------
- datareader imported as module instead of subprocess call
- Parser instance persists in memory between refresh cycles
- Added timestamp tracking to skip already-processed lines:
  - First run: processes last 50 lines (sets baseline)
  - Subsequent runs: only processes NEW lines
- Much cleaner terminal output - only shows genuinely new messages
- No subprocess overhead every 20 seconds

4. CROSS-PLATFORM PATH HANDLING
-------------------------------
- Replaced OS-specific path separators with os.path.join()
- Works on Windows, Linux, and macOS without code changes
- Simplified _detect_os() to _log_os_info() (just logs OS name)

5. CONFIGURATION IMPROVEMENTS
-----------------------------
- Created config.ini.template with default settings
- Created traffic.db3.template with test data
- install.py creates files from templates if missing
- User configs preserved during updates
- .gitignore updated to track templates but ignore user files
- Renamed 'port' to 'UDP_port' for clarity (15 Python files updated)

6. INSTALL.PY UPDATES
---------------------
- Added psutil to package list
- Refactored to use list iteration instead of individual variables
- Added create_from_template() function
- Added setup_files() to create config and database from templates

7. UI IMPROVEMENTS
------------------
- Menu bar: 24px height with 4px padding for centered text
- Menu colors configurable via config.ini (menu_background, menu_foreground)
- Filter labels allow window to be narrowed (QSizePolicy.Ignored)
- Color validation: invalid colors fall back to defaults with warning

8. CODE QUALITY
---------------
- Type hints on all function parameters and returns
- Docstrings on all classes and key methods
- Constants replace magic numbers and strings
- Single responsibility principle applied
- Dependency injection (config/db managers passed to components)
- Error handling with graceful failures
- f-strings for consistent string formatting
- Private methods use _ prefix

9. FILES MODIFIED
-----------------
- commstat.py (main application rebuild)
- datareader.py (refactored)
- install.py (updated)
- config.ini.template (NEW)
- traffic.db3.template (NEW)
- .gitignore (updated)
- message.py, checkin.py, csresponder.py, filter.py,
  js8mail.py, js8sms.py, marquee.py, members.py, netmanager.py,
  settings.py, statack.py, statrep.py (modernized dialogs)

10. MENU ACTIVATION (December 2025)
-----------------------------------
- JS8EMAIL: Send emails via APRS gateway
- JS8SMS: Send SMS via APRS gateway
- DISPLAY FILTER: Simplified filter dialog
- Removed unused DATA MANAGER menu option

11. MAP IMPROVEMENTS
--------------------
- Map preserves position and zoom during 20-second auto-refresh
- Removed grid-based filtering from SQL queries

12. GROUP MANAGEMENT
--------------------
- Groups now stored in database (Groups table) instead of config.ini
- Unlimited groups supported
- Group names: max 15 characters, stored in UPPERCASE
- Default groups seeded on first run: MAGNET, AMRRON, PREPPERNET
- New "MANAGE GROUPS" menu option
- All data refreshes when active group changes

13. FILE CLEANUP AND REORGANIZATION (December 2025)
----------------------------------------------------
- Renamed modernized files
- Replaced images and icons
- Moved obsolete files to trash/
- Cleaned up UI labels and spacing

14. MODERNIZED DIALOGS
----------------------
- StatRep
- JS8 EMAIL
- JS8 SMS
- Filter
- Settings

15. GIT COMMITS
---------------
- Application rebuild
- Refactoring and cleanup
- Feature activation
- Group management overhaul
- File reorganization

16. JS8 TCP CONNECTOR SUPPORT (December 2025)
---------------------------------------------
- Replaced file-based DIRECTED.TXT polling with persistent TCP connections
- Replaced UDP transmission with TCP API (TX.SEND_MESSAGE)
- Support for up to 3 simultaneous JS8Call instances
- New "JS8 CONNECTORS" menu for managing connections
- Connector configuration stored in database (js8_connectors table)
- Server IP hardcoded to 127.0.0.1 (localhost)
- Callsign and grid fetched automatically from JS8Call via API
- Frequency stored in database when sending StatRep, Message, or Marquee
- Rig dropdown added to all transmit dialogs:
  - StatRep
  - Message
  - Marquee
  - JS8 Email
  - JS8 SMS
- New files:
  - connector_manager.py: Database operations for connectors
  - js8_tcp_client.py: TCP client with Qt signals
  - js8_connectors.py: Connector management dialog
- Removed from config.ini: callsign, grid, server, UDP_port

17. EVENT-DRIVEN UI UPDATES (January 2026)
------------------------------------------
- Replaced 20-second polling with event-driven updates
- UI refreshes immediately when data is received via TCP:
  - StatRep received → StatRep table + map refresh
  - Message received → Message table refresh
  - Marquee received → Marquee banner refresh
  - Check-in received → Map refresh
- Playlist check moved to 60-second interval
- More responsive UI with reduced unnecessary database queries

18. DATE FILTERING (January 2026)
---------------------------------
- Start date automatically set to today when program launches
- No end date by default (shows all data from today forward)
- Display Filter dialog (Menu > DISPLAY FILTER) allows viewing historical data:
  - Set custom start date to view older StatReps
  - Set end date to limit the date range
- Filter settings stored in memory (not saved to config.ini)
- Each program restart resets to today's date
- Removed [FILTER] section from config.ini

19. STATREP COMPRESSION (January 2026)
--------------------------------------
- All-green StatReps (111111111111) are compressed to "+" when transmitted
- Saves 11 characters over the air for faster transmission
- Receiving stations automatically expand "+" back to 12 ones
- Works for both regular and forwarded StatReps

20. TOOLS MENU (January 2026)
-----------------------------
- Band Conditions: Solar-terrestrial data from N0NBH (https://www.hamqsl.com/solar.html)
- World Map: HF propagation world map

---

## License & Copyright

Copyright © 2025 Manuel Ochoa

This project is licensed under the **GNU General Public License v3.0**.

CommStat-Improved is derived from earlier CommStat projects originally created by **Daniel M. Hurd (W5DMH)** and later expanded by **Rich W. Whittington (KD9DSS)**.  
The original CommStat design incorporated concepts and workflows developed in collaboration with:

- **AmRRON** — https://amrron.com/  
- **MPURN** — https://mpurn.wordpress.com/  
- **PREPPERNET** — https://preppernet.com/

References to organizations are **historical and descriptive only**.

AI assistance provided by **Claude (Anthropic)** and **ChatGPT (OpenAI)**.

---

## Contact

For questions, comments, or suggestions:  
**mochoa@protonmail.com**
