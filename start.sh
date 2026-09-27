#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[Error] python3 is not installed."
    echo "Install python3 with your distribution package manager."
    exit 1
fi

chmod +x bin/host/* bin/device/* bin/fastboot/* 2>/dev/null || true

if ! python3 -c "import zstandard" >/dev/null 2>&1; then
    echo "[*] Installing Python dependencies..."
    python3 -m pip install -r requirements.txt || pip3 install -r requirements.txt
fi

python3 main.py "$@"
