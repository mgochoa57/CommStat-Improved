#!/bin/bash
# CommStat macOS Installation Script

set -e  # Exit on error

echo "=============================================="
echo "CommStat macOS Installer"
echo "=============================================="

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script is for macOS only."
    echo "For Linux, run: ./linuxinstall.sh"
    exit 1
fi

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Error: Homebrew not found."
    echo ""
    echo "Install Homebrew first:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    echo "Then run this script again."
    exit 1
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Installing via Homebrew..."
    brew install python3
fi

echo ""
echo "Installing PyQt5 via Homebrew..."
echo ""

brew install pyqt5

echo ""
echo "Running Python installer..."
echo ""

python3 install.py

echo ""
echo "=============================================="
echo "Installation complete!"
echo "Run CommStat with: python3 startup.py"
echo "=============================================="
