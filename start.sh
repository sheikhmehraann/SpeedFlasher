#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo "                         SpeedFlasher Launcher"
echo "========================================================================"

# Detect Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[*] python3 was not found. Attempting package installation..."
    if command -v apt-get >/dev/null 2>&1; then
        echo "[*] Running apt-get install python3 python3-pip python3-tk..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-tk
    elif command -v dnf >/dev/null 2>&1; then
        echo "[*] Running dnf install python3 python3-pip python3-tkinter..."
        sudo dnf install -y python3 python3-pip python3-tkinter
    elif command -v pacman >/dev/null 2>&1; then
        echo "[*] Running pacman install python python-pip tk..."
        sudo pacman -S --noconfirm python python-pip tk
    else
        echo "[Error] python3 is not installed."
        echo "Please install python3, python3-pip, and python3-tk using your system package manager."
        exit 1
    fi
fi

# Verify dependencies
echo "[*] Checking Python dependencies..."
if [ -f "requirements.txt" ]; then
    if ! python3 -c "import zstandard" >/dev/null 2>&1; then
        echo "[*] Installing required packages from requirements.txt..."
        python3 -m pip install -r requirements.txt 2>/dev/null || \
        python3 -m pip install --user -r requirements.txt 2>/dev/null || \
        python3 -m pip install --break-system-packages -r requirements.txt 2>/dev/null || true
    else
        echo "[*] All requirements already satisfied."
    fi
fi

chmod +x bin/linux/* bin/device/* 2>/dev/null || true

echo "[*] Launching SpeedFlasher..."
echo "========================================================================"
echo ""

python3 main.py "$@"
