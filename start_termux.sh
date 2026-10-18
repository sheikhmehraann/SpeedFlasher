#!/data/data/com.termux/files/usr/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo "                     SpeedFlasher (Termux Setup)"
echo "========================================================================"

if [ ! -d "$HOME/storage" ]; then
    echo "[*] Requesting storage access..."
    termux-setup-storage || true
fi

echo "[*] Ensuring Termux packages (python, zstd, android-tools)..."
pkg update -y || true
pkg install -y python zstd android-tools || true

if [ -f "requirements.txt" ]; then
    if ! python -c "import zstandard" >/dev/null 2>&1; then
        echo "[*] Installing Python dependencies from requirements.txt..."
        pip install -r requirements.txt || true
    else
        echo "[*] All requirements already satisfied."
    fi
fi

chmod +x bin/device/* 2>/dev/null || true

echo "[*] Starting SpeedFlasher..."
echo "========================================================================"
echo ""

python main.py "$@"
