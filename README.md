# SpeedFlasher

SpeedFlasher converts raw partition image dumps (`.img` or `.img.zst`) into flashable ROM packages for Android devices. Generated packages can be flashed directly in custom recovery (TWRP, OrangeFox, PBRP, Lineage Recovery) or flashed from a PC/Termux via Fastboot and fastbootd.

Supported host platforms:
- Windows (PowerShell, Command Prompt, batch launcher)
- Linux (x86_64, aarch64)
- Android Termux (arm64)

## Features

- Dynamic partition management: Uses bundled `lptools` in custom recovery to remove, resize, and recreate logical partitions on modern dynamic super devices.
- Streaming Zstandard decompression: Partitions are compressed with Zstandard and decompressed on-the-fly directly into partition block devices in recovery, eliminating memory exhaustion or intermediate cache writes.
- Slot handling: Automatically detects active boot slot (`_a` / `_b`) or single slot devices and flashes firmware and bootchain partitions to both slots on A/B targets.
- AVB 2.0 controls: Can pre-patch `vbmeta.img` flags or configure dm-verity and verification status on-device via `avbctl`.
- Hybrid Fastboot installer: Packages include standalone `flash_windows.bat`, `flash_linux.sh`, and `flash_termux.sh` alongside bundled fastboot binaries, allowing deployment through USB fastboot / fastbootd without custom recovery.
- POSIX permissions: Generated ZIP files retain exact `0755` executable permissions for recovery binaries and flash scripts.

## Directory Structure

```
SpeedFlasher/
├── bin/
│   ├── device/              # ARM64 recovery binaries (lptools, avbctl, zstd-arm64, rapidflasher)
│   ├── fastboot/            # Fastboot binaries and drivers for Windows and Linux
│   └── host/                # Host compression tools (zstd.exe, zstd)
├── core/
│   ├── avb.py               # AVB 2.0 flag manager and header patcher
│   ├── builder.py           # Core packaging and parallel compression pipeline
│   ├── partitions.py        # Partition scanner, classifier, and size inspector
│   └── scripts.py           # Recovery update-binary and fastboot script generators
├── main.py                  # CLI and interactive entry point
├── start.bat                # Windows launcher
├── start.sh                 # Linux launcher
├── start_termux.sh          # Termux launcher
├── requirements.txt         # Python dependencies
└── README.md
```

## Installation

### Windows
Run `start.bat` or install requirements manually:
```powershell
pip install -r requirements.txt
```

### Linux
```bash
chmod +x start.sh bin/host/* bin/device/* bin/fastboot/*
pip install -r requirements.txt
./start.sh
```

### Android Termux
```bash
pkg update && pkg install -y python zstd p7zip tar clang android-tools
pip install -r requirements.txt
chmod +x start_termux.sh
./start_termux.sh
```

## Usage

### Interactive Mode
Run without arguments to start the interactive prompt:
```bash
python main.py
```

### Command Line Mode

```bash
python main.py \
  --imgs-dir "/path/to/extracted/imgs" \
  --device "Infinix GT 20 Pro" \
  --codename "X6871" \
  --version "15.1.2.180" \
  --maintainer "Mehraan" \
  --vbmeta "skip" \
  --zstd-level 1 \
  --zip-level 1 \
  --output "./output/ROM-Flashable.zip"
```

### CLI Arguments

| Argument | Description | Default |
|---|---|---|
| `-i, --imgs-dir` | Directory containing raw `.img` or `.img.zst` files | Required (or interactive) |
| `-o, --output` | Output ZIP file path | `./output/{version}-{codename}-Flashable.zip` |
| `-d, --device` | Device marketing name | `Android Device` |
| `-c, --codename` | Device board codename | Empty |
| `-v, --version` | ROM / firmware version string | `1.0` |
| `-m, --maintainer` | Maintainer name | `Mehraan` |
| `--vbmeta` | AVB 2.0 mode (`disable`, `enable`, `skip`) | `skip` |
| `--zstd-level` | Zstandard compression level (0-22) | `1` |
| `--zip-level` | ZIP deflation level (0=STORE, 1-9=DEFLATE) | `1` |
| `--no-fastboot` | Exclude Fastboot installer scripts and binaries from package | Disabled |

## How Flashing Works

### Recovery Flashing (TWRP / OrangeFox / Lineage)
1. Device checks active slot via `ro.boot.slot_suffix`.
2. Validates board codename (prompts with volume keys if device string does not match).
3. Unmounts existing dynamic partitions.
4. Flashes firmware images (`lk`, `logo`, `scp`, `spmfw`, etc.) to both slots on A/B hardware.
5. Flashes bootchain images (`boot`, `dtbo`, `init_boot`, `vendor_boot`, `vbmeta`) to both slots.
6. Clears and resizes dynamic partitions in `super` using `lptools`.
7. Decompresses `.img.zst` files directly into `/dev/block/mapper/` targets.
8. Syncs caches and remaps logical devices.

### Fastboot Flashing (PC / Termux)
1. Extract the generated flashable ZIP on PC or Termux.
2. Connect phone in fastboot mode.
3. Run `flash_windows.bat` on Windows, `./flash_linux.sh` on Linux, or `./flash_termux.sh` in Termux.
4. The script flashes boot and firmware partitions, transitions to `fastbootd` (`fastboot reboot fastboot`), flashes logical partitions, and reboots.

## License
Apache-2.0 License.
