#!/bin/bash
# CommStat macOS Launcher
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/commstat.py" "$@"
