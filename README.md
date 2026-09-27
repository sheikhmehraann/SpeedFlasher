# SpeedFlasher

SpeedFlasher is a high-speed flashable ROM package maker for Android devices. It packages raw partition image dumps (.img or .img.zst) into flashable ZIP packages supporting both custom recovery installation (TWRP, OrangeFox, PBRP, Lineage Recovery) and PC/Termux Fastboot installation.

Supported host platforms:
- Windows
- Linux
- Android Termux

## Architecture

The project organizes platform-specific logic and binaries cleanly by operating system:

```
SpeedFlasher/
├── bin/
│   ├── device/              # ARM64 recovery binaries (lptools, avbctl, zstd-arm64, rapidflasher-arm64, lpdump, lpmake)
│   ├── windows/             # Windows host binaries (zstd.exe, fastboot.exe, AdbWinApi.dll, AdbWinUsbApi.dll)
│   ├── linux/               # Linux host binaries (zstd, fastboot, lpunpack, simg2img)
│   └── termux/              # Termux environment handlers
├── core/
│   ├── avb.py               # AVB 2.0 vbmeta header patcher
│   ├── builder.py           # Multi-threaded package synthesis engine (with zip64 support)
│   ├── partitions.py        # Partition scanner, classifier, and size inspector
│   ├── recovery/            # Recovery update-binary generator
│   ├── windows/             # Windows binary resolver and flash_windows.bat generator
│   ├── linux/               # Linux binary resolver and flash_linux.sh generator
│   └── termux/              # Termux package resolver, storage checker, and flash_termux.sh generator
├── main.py                  # CLI and interactive console entry point
├── start.bat                # Windows launcher
├── start.sh                 # Linux launcher
├── start_termux.sh          # Termux launcher
├── requirements.txt         # Minimal Python dependencies
└── tests/
    └── test_speedflasher.py # Deep multi-OS test suite
```

## Features

- Dynamic partition support: Bundles static ARM64 `lptools` to resize, unmap, and recreate logical partitions on modern dynamic super devices.
- In-memory streaming decompression: Compresses partitions with Zstandard and decompresses them on the fly directly to `/dev/block/mapper/` nodes, avoiding recovery RAM exhaustion.
- Both-slots patching: Automatically flashes firmware and bootchain partitions to both slots (`_a` and `_b`) on A/B targets.
- AVB 2.0 control: Direct binary patching of `vbmeta.img` header flags (disable verity/verification) or on-device configuration via `avbctl`.
- Hybrid Fastboot flasher: Packages include `flash_windows.bat`, `flash_linux.sh`, and `flash_termux.sh` along with fastboot binaries, allowing deployment via fastboot and fastbootd without custom recovery.
- Zip64 enabled: Uses explicit zip64 streams to prevent `RuntimeError: File size too large, try using force_zip64` when packaging large partition dumps.
- Automatic dependency setup: Detects and installs missing packages automatically on startup across Windows, Linux, and Termux.

## Installation

### Windows
Run `start.bat` or install requirements:
```powershell
pip install -r requirements.txt
```

### Linux
```bash
chmod +x start.sh bin/linux/* bin/device/*
pip install -r requirements.txt
./start.sh
```

### Android Termux
```bash
pkg update && pkg install -y python zstd p7zip clang android-tools
pip install -r requirements.txt
chmod +x start_termux.sh
./start_termux.sh
```

## Usage

### Interactive Mode
Run `python main.py` or double-click the launcher for your OS:
```text
Enter IMGS Path : C:\Path\To\ROM_DUMP
Devicename [Infinix GT 20 Pro] : 
Codename [X6871] : 
Version [15.1.2.180] : 
AVB 2.0 (vbmeta) [skip/disable/enable] : disable
Maintainer [Mehraan] : 
Ztsd Compression (0-22) [1] : 1
Zip Compression (0-9) [1] : 1
```

The tool automatically generates the output package inside the `output/` directory:
`output/<version>-<codename>-Flashable.zip`

### Command Line Mode
```bash
python main.py \
  --imgs-path "C:\Path\To\ROM_DUMP" \
  --device "Infinix GT 20 Pro" \
  --codename "X6871" \
  --version "15.1.2.180" \
  --maintainer "Mehraan" \
  --vbmeta "disable" \
  --zstd-level 1 \
  --zip-level 1
```

## Running Tests
Run the test suite across all platform modules:
```bash
python -m unittest tests/test_speedflasher.py
```

## License
Apache-2.0 License.
