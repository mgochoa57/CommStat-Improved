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
echo "Installing Enchant via Homebrew..."
echo ""

brew install enchant

echo ""
echo "Running Python installer..."
echo ""

python3 install.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Build a CommStat.app bundle in /Applications so it appears in Finder, Launchpad, and Spotlight.
# Writing to /Applications requires admin rights, so prompt for sudo once up front and keep the
# timestamp alive while the script runs. brew and pip stay under the regular user.
echo ""
echo "CommStat.app will be installed to /Applications (admin password required)."
sudo -v
( while true; do sudo -n true; sleep 50; kill -0 "$$" || exit; done 2>/dev/null ) &
SUDO_KEEPALIVE=$!
trap 'kill $SUDO_KEEPALIVE 2>/dev/null' EXIT

echo ""
echo "Creating CommStat.app in /Applications..."

FINAL_APP_DIR="/Applications/CommStat.app"
STAGE_DIR="$(mktemp -d)"
APP_DIR="$STAGE_DIR/CommStat.app"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

# Launcher inside the app bundle — cd into the real CommStat source dir and run it.
# Finder/Launchpad launches use a minimal PATH, so resolve python3 to an absolute
# path and prepend Homebrew locations so user-installed packages are importable.
PYTHON3_BIN="$(command -v python3 || echo /usr/bin/python3)"
cat > "$APP_DIR/Contents/MacOS/CommStat" << EOF
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH"
cd "$SCRIPT_DIR" || exit 1
LOG="\$HOME/Library/Logs/CommStat.log"
mkdir -p "\$(dirname "\$LOG")"
exec "$PYTHON3_BIN" "$SCRIPT_DIR/commstat.py" "\$@" >>"\$LOG" 2>&1
EOF
chmod +x "$APP_DIR/Contents/MacOS/CommStat"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>CommStat</string>
    <key>CFBundleDisplayName</key>
    <string>CommStat</string>
    <key>CFBundleIdentifier</key>
    <string>com.commstat.app</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>CommStat</string>
    <key>CFBundleIconFile</key>
    <string>CommStat.icns</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Build an .icns from the best radiation image we can find
ICON_SRC=""
for candidate in "$SCRIPT_DIR/radiation.png" "$SCRIPT_DIR/radiation-32.png" "$SCRIPT_DIR/images/044-radiation.png"; do
    if [ -f "$candidate" ]; then
        ICON_SRC="$candidate"
        break
    fi
done

if [ -n "$ICON_SRC" ]; then
    ICONSET="$(mktemp -d)/CommStat.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 64 128 256 512 1024; do
        sips -z $size $size "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null 2>&1
    done
    # Retina @2x variants (macOS expects these names)
    cp "$ICONSET/icon_32x32.png"   "$ICONSET/icon_16x16@2x.png"   2>/dev/null || true
    cp "$ICONSET/icon_64x64.png"   "$ICONSET/icon_32x32@2x.png"   2>/dev/null || true
    cp "$ICONSET/icon_256x256.png" "$ICONSET/icon_128x128@2x.png" 2>/dev/null || true
    cp "$ICONSET/icon_512x512.png" "$ICONSET/icon_256x256@2x.png" 2>/dev/null || true
    cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png" 2>/dev/null || true
    iconutil -c icns "$ICONSET" -o "$APP_DIR/Contents/Resources/CommStat.icns" 2>/dev/null \
        || cp "$ICON_SRC" "$APP_DIR/Contents/Resources/CommStat.icns"
    rm -rf "$(dirname "$ICONSET")"
    echo "Icon installed from: $ICON_SRC"
else
    echo "No radiation icon found — app will use default icon."
fi

# Move the staged bundle into /Applications, replacing any prior install.
sudo rm -rf "$FINAL_APP_DIR"
sudo mv "$APP_DIR" "$FINAL_APP_DIR"
rm -rf "$STAGE_DIR"

# Nudge the Finder/Launch Services to pick up the new icon
sudo touch "$FINAL_APP_DIR"
sudo /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$FINAL_APP_DIR" >/dev/null 2>&1 || true

echo "CommStat.app installed at: $FINAL_APP_DIR"

echo ""
echo "=============================================="
echo "Installation complete!"
echo "https://commstat-improved.com/"
echo "=============================================="
