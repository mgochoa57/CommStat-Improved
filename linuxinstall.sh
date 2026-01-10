#!/bin/bash
# CommStat Linux Installation Script
# For Debian/Ubuntu-based systems (including Linux Mint, Raspberry Pi OS)

set -e  # Exit on error

echo "=============================================="
echo "CommStat Linux Installer"
echo "=============================================="

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "Error: This script is for Linux only."
    echo "For macOS, run: python3 install.py"
    exit 1
fi

# Check for apt (Debian/Ubuntu)
if ! command -v apt &> /dev/null; then
    echo "Error: apt package manager not found."
    echo "This script is for Debian/Ubuntu-based systems."
    echo ""
    echo "For other distros, manually install PyQt5 WebEngine:"
    echo "  Fedora: sudo dnf install python3-qt5-webengine"
    echo "  Arch:   sudo pacman -S python-pyqt5-webengine"
    echo "Then run: python3 install.py"
    exit 1
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 not found. Please install Python 3.8 or newer."
    exit 1
fi

echo ""
echo "Installing PyQt5 WebEngine via apt..."
echo "(You may be prompted for your sudo password)"
echo ""

sudo apt update
sudo apt install -y python3-pyqt5.qtwebengine

echo ""
echo "Running Python installer..."
echo ""

python3 install.py

echo ""
echo "=============================================="
echo "Installation complete!"
echo "Run CommStat with: python3 startup.py"
echo "=============================================="
