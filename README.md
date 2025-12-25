# CommStatOne Ver 1.0.5 Released 10/15/2023
CommStat One Ver 1.0.5 add on software for JS8Call groups
Commstat One is a Python version of the CommStat software <b>designed to run on on Win10 AND Linux</b><br>
- Author: Daniel M Hurd ~W5DMH
- Repository: https://github.com/W5DMH/commstatone
<br><br>

# CommStat Ver 2.0.0
- Author: uknown
- Repository: unkown
- Release Date: uknown
<br><br>

# CommStat Ver 2.3.0 Released 11/17/2025
- Author: Rick W Whittington ~KD9DSS
- Repository: https://amrron.com/2025/11/17/commstat-v2-3-offline-mapping/
- Highlight: Introduced Offline Maps
<br><br>

# CommStat-Improved Ver 2.5.0 Released 12/25/2025
- Author: Manuel G Ochoa ~N0DDK
<br>

<h3>CommStat-Improved - Summary of Changes and Improvements</h3>
<h3>Project rebuild and modernization effort - December 2025</h3>
<br>

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
- 20-second auto-refresh for StatRep, bulletins, live feed, and map


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
- commstatpy (main application rebuild)
- datareader.py (refactored)
- install.py (updated)
- config.ini.template (NEW)
- traffic.db3.template (NEW)
- .gitignore (updated)
- bulletin.py, checkin.py, csresponder.py, filter.py, heardlist.py,
  js8mail.py, js8sms.py, marquee.py, members.py, netmanager.py,
  settings.py, statack.py, statrep.py (UDP_port rename)


10. GIT COMMITS
---------------
- Add commstat.py - rebuilt application with best practices
- Refactor datareader.py with Python best practices
- Use os.path.join for cross-platform path handling
- Add psutil to install.py and clean up package installation
- Add color validation and menu bar styling improvements
- Add template files and rename port to UDP_port
- Fix filter labels blocking resize and add datareader call
- Import datareader as module with timestamp tracking







<b>NOTE: ALL USERS MUST RUN INSTALL ON THIS VERSION!<br></b>
<br>

<b>Commstat One WINDOWS INSTALL PROCEDURE</B>
<br>
NOTE : Saavy users can "git clone t"
<br>
 To install, simply unzip the zipped folder below then: <br>
 <b>Type : cd commstatone <br>
  Type : python install.py </b> (or use : python3 install.py  if necessary) <br>
 You should get your settings popup, complete the settings then :<br>
 <b>Type : python commstat.py    or    python3 commstat.py (if your system requires python3) <b> NOT commstatx.py this has changed to commstat.py</b> 

<br>
 <br>
 
<b>Commstat One LINUX INSTALL PROCEDURE (Mint 20.03 & 21.1 Supported, Pi4 64bit may work)</B><br>
NOTE : Saavy users can "git clone https://github.com/W5DMH/commstatone.git"<br>
 <b>Type : cd commstatone <br>
 type : chmod +x linuxinstall.sh <br>
 type : ./linuxinstall.sh <br>
 enter your sudo password <br>
 After some installation you should get your settings popup, complete the settings then :<br>
 <b>Type : python commstat.py    or    python3 commstat.py (if your system requires python3) <b> NOT commstatx.py this has changed to commstat.py</b> 

<br><br><br>
=======
 
<h3>Here is a link to the archive file:&nbsp;<a href="https://github.com/W5DMH/commstatone/raw/main/commstatone.zip" target="_blank" rel="noopener">CommStat One 1.0.5 for Win10 & Win11 & Linux </a></h3>




I must give credit to m0iax for his JS8CallAPISupport Script as that is what makes the transmitting possible.See the rest of his JS8Call Tools here : https://github.com/m0iax
<br>
