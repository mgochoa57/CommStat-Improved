# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat.
# Licensed under the GNU General Public License v3.0.

#!/usr/bin/env python3
import subprocess
import sys
import os
import platform
import shutil

DATABASE_FILE = "traffic.db3"
DATABASE_TEMPLATE = "traffic.db3.template"

pyver = ""
osver = ""


def oscheck():
    global osver

    if sys.platform == 'win32':
        print("Detected: Windows")
        osver = "Windows"
        test_python()
    elif sys.platform == 'darwin':
        print("Detected: macOS")
        osver = "macOS"
        test_python()
    elif sys.platform.startswith('linux'):
        # Check for Raspberry Pi
        if "aarch64" in platform.platform():
            print("Detected: Raspberry Pi 64-bit")
        else:
            print("Detected: Linux")
        osver = "Linux"
        test_python()
    else:
        print("CommStat does not recognize this operating system and cannot proceed.")
        print(f"Platform detected: {sys.platform}")
        return


def create_from_template(target: str, template: str) -> None:
    """Create a file from template if it doesn't exist."""
    if not os.path.exists(target):
        if os.path.exists(template):
            shutil.copy(template, target)
            print(f"Created {target} from template")
        else:
            print(f"Warning: {template} not found, cannot create {target}")


def setup_files():
    """Create database from template if missing."""
    create_from_template(DATABASE_FILE, DATABASE_TEMPLATE)


def runsettings():
    setup_files()
    print("\nInstallation complete. Run 'python commstat.py' to start the program.")


def install(package):
    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if sys.platform == 'darwin' or sys.platform.startswith('linux'):
            cmd.extend(["--break-system-packages", "--user"])
        cmd.append(package)
        subprocess.check_call(cmd)

    except subprocess.CalledProcessError as e:
        # print("this is the except install error: "+str(e.returncode))
        if e.returncode > 0:
            print(
                " Installation failed, copy and paste this screen \n into https://groups.io/g/CommStat for support exiting now")
            sys.exit()
            # Exception("failed installation, cannot conntinue")


def test_python():
    global osver
    print("HERE is the version "+osver)
    try:
        if int(sys.version_info[0]) < 3:
            print("You are using Python " + str(sys.version_info[0]))
            print("Commstatx requires Python 3.9 or newer, install cannot continue")
            # raise Exception("Wrong Python version, cannot continue installation, please upgrade Python")
            sys.exit()

        if int(sys.version_info[1]) < 8:
            print("You are using Python 3." + str(sys.version_info[1]))
            print("Commstatx requires Python 3.8 or newer")
            # raise Exception("Wrong Python cannot continue")
            sys.exit()
        else:
            print("Appropriate version of Python found : Python 3." + str(
                sys.version_info[1]) + ", continuing installation")

    except:
        print("Exception while testing Python version, cannot continue installation")
        sys.exit()
    if osver == "Windows":
        print("Installing for Windows 10 or 11")
        wininstall()
    elif osver == "macOS":
        print("Installing for macOS")
        macinstall()
    elif osver == "Linux":
        print("Installing for Linux")
        lininstall()
    else:
        print("System not recognized")


def lininstall():
    """Install dependencies for Linux/Pi systems."""
    packages = [
        "feedparser",
        "file-read-backwards",
        "folium",
        "pandas",
        "maidenhead",
        "psutil",
        "pyenchant",
    ]
    for package in packages:
        install(package)
    runsettings()


def macinstall():
    """Install dependencies for macOS systems."""
    packages = [
        "PyQt5",
        "PyQt5-Qt5",
        "PyQtWebEngine",
        "PyQtWebEngine-Qt5",
        "feedparser",
        "file-read-backwards",
        "folium",
        "pandas",
        "maidenhead",
        "psutil",
        "pyenchant",
    ]
    for package in packages:
        install(package)
    runsettings()


def wininstall():
    """Install dependencies for Windows systems."""
    packages = [
        "pyqt5",
        "PyQtWebEngine",
        "feedparser",
        "file-read-backwards",
        "folium",
        "pandas",
        "maidenhead",
        "psutil",
        "pyenchant",
    ]
    for package in packages:
        install(package)
    runsettings()


oscheck()

# test_python()


# os.chdir(os.path.dirname(__file__))
# print(os.getcwd())

# runsettings()
