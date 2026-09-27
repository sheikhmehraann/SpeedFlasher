#!/data/data/com.termux/files/usr/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "$HOME/storage" ]; then
    echo "[*] Setting up Termux storage access..."
    termux-setup-storage || true
fi

pkg update -y || true
pkg install -y python zstd android-tools || true

python main.py "$@"
