# SpeedFlasher

Universal Android Flashable Package Maker for Windows, Linux, and Android Termux.

SpeedFlasher converts partition image dumps (`.img` or `.img.zst`) into flashable recovery ZIPs (compatible with TWRP, OrangeFox, PBRP, and Lineage Recovery) and multi-platform Fastboot flasher scripts (`flash_windows.bat`, `flash_linux.sh`, `flash_termux.sh`).

## Features

- Multi-Platform Support: Windows (x86_64), Linux (x86_64), and Android Termux (ARM64).
- Recovery Installer: Self-contained POSIX `update-binary` supporting dynamic partitions (via `lptools`), dual-slot detection (A/B and A-only), and in-memory streaming Zstandard decompression directly to block devices.
- Fastboot Installers: Generates ready-to-run Fastboot flasher scripts for Windows, Linux, and Termux with bundled tools and on-the-fly partition decompression.
- AVB 2.0 (Vbmeta) Control: Directly inspects and patches AVB0 header flags (`disable`, `enable`, or `skip`) across `vbmeta`, `vbmeta_system`, and `vbmeta_vendor`.
- Partition Classification: Automatically identifies dynamic partitions (`system`, `vendor`, `product`, `system_ext`, etc.), direct bootchain images (`boot`, `dtbo`, `init_boot`, `vendor_boot`, `vbmeta`), and firmware images (`lk`, `logo`, `md1img`, `tee`, etc.).
- Multi-Threaded Compression: Parallel Zstandard compression (levels 0-22) with configurable ZIP compression (levels 0-9) and standard Zip64 support.
- Dependency Auto-Resolution: Automatically verifies and installs missing platform dependencies on startup.
- Clean Output Summary: Displays a full breakdown of packaged partitions, output path, and file size, with terminal window retention.

## Project Structure

```text
SpeedFlasher/
├── bin/
│   ├── device/                  # ARM64 recovery binaries (lptools, avbctl, zstd-arm64, etc.)
│   ├── linux/                   # Linux host tools (fastboot, zstd)
│   └── windows/                 # Windows host tools (fastboot.exe, zstd.exe, DLLs)
├── core/
│   ├── avb.py                   # AVB 2.0 vbmeta header parser and flag patcher
│   ├── builder.py               # Package staging, multi-threaded compression, and ZIP packaging
│   ├── partitions.py            # Partition image scanning and filesystem detection
│   ├── linux/
│   │   ├── installer.py         # Linux Fastboot shell script generator
│   │   └── platform.py          # Linux dependency checker and tool resolver
│   ├── recovery/
│   │   └── updater.py           # Recovery POSIX update-binary shell generator
│   ├── termux/
│   │   ├── installer.py         # Termux Fastboot shell script generator
│   │   └── platform.py          # Termux environment setup and package manager installer
│   └── windows/
│       ├── installer.py         # Windows Fastboot batch script generator
│       └── platform.py          # Windows dependency checker and tool resolver
├── output/                      # Default build target directory
├── tests/
│   └── test_speedflasher.py     # Multi-OS unit and integration test suite
├── gui.py                       # Windows 11 Fluent Dark Mica GUI
├── main.py                      # Interactive CLI and headless entrypoint
├── requirements.txt             # Python requirements (optional fallback)
├── start_gui.bat                # Windows 11 GUI launcher
├── start.bat                    # Windows CLI launcher
├── start.sh                     # Linux launcher
└── start_termux.sh              # Termux launcher
```

## OS Usage Guides

### 1. Windows Guide

#### Requirements
- Windows 10 / 11 (64-bit)
- Python 3.8 or newer (ensure "Add Python to PATH" is checked during installation)

#### Building a Flashable Package (GUI Mode)
1. Double-click `start_gui.bat` or run:
   ```cmd
   python gui.py
   ```
   *(Or run `python main.py --gui`)*
2. The native Windows 11 Fluent Dark Mica interface will launch.
3. Click **Browse...** to select your dumped partition images directory. The tool automatically detects partitions and parses `build.prop` for device metadata.
4. Adjust AVB 2.0 flags, Zstandard compression, and ZIP levels as needed.
5. Click **Build Flashable Package**. Progress and live logs will stream in the embedded console.
6. Once complete, click **Open Output Folder** to reveal the compiled ZIP package.

#### Building a Flashable Package (CLI Mode)
1. Double-click `start.bat` or run:
   ```cmd
   python main.py
   ```
2. Follow the interactive prompts (enter the folder path containing your `.img` files).
3. The output package is automatically saved to `output/<version>-<codename>-Flashable.zip`.
4. The terminal window stays open after completion so you can review the build summary.

#### Flashing the Generated Package on Windows
- **Via Custom Recovery**:
  Copy the generated `.zip` to your device (internal storage, SD card, or USB OTG) and flash it in TWRP, OrangeFox, or PBRP.
- **Via Fastboot**:
  1. Extract the generated `.zip` file on your PC.
  2. Put your device into Fastboot mode (`adb reboot bootloader` or hold Volume Down + Power).
  3. Connect the device via USB and double-click `flash_windows.bat`.
  4. The script uses bundled `fastboot.exe` and `zstd.exe`, decompresses partitions on-the-fly, flashes firmware, reboots to fastbootd for dynamic partitions, and prompts whether to format userdata.

#### Windows Troubleshooting
- If device is not detected in fastboot, install the Google USB Driver or OEM Fastboot Driver.
- If Python is not recognized, re-run Python installer and select "Add python.exe to PATH".

---

### 2. Linux Guide

#### Requirements
- Ubuntu, Debian, Fedora, Arch Linux, or any standard Linux distribution (x86_64)
- Python 3.8+ (no extra pip packages required; bundled tools run out-of-the-box)

#### Installation
Install Python using your distribution package manager:

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3

# Fedora
sudo dnf install -y python3

# Arch Linux
sudo pacman -S --needed python
```

#### Building a Flashable Package
1. Grant execute permissions and run the launcher:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```
   Or run directly:
   ```bash
   python3 main.py
   ```
2. Enter the path to your extracted partition images when prompted.
3. The resulting ZIP file is generated in the `output/` directory.

#### Flashing the Generated Package on Linux
- **Via Custom Recovery**:
  Transfer the `.zip` to your device and flash it through recovery.
- **Via Fastboot**:
  1. Extract the `.zip` package:
     ```bash
     unzip <package-name>.zip -d rom_extracted
     cd rom_extracted
     ```
  2. Boot device into Fastboot mode (`adb reboot bootloader`).
  3. Grant execute permission and run the installer:
     ```bash
     chmod +x flash_linux.sh
     ./flash_linux.sh
     ```

#### Linux Troubleshooting
- If fastboot requires root permissions or fails with `no permissions`, install android udev rules:
  ```bash
  sudo apt install -y android-sdk-platform-tools-common
  # Or create /etc/udev/rules.d/51-android.rules
  ```

---

### 3. Android Termux Guide

#### Requirements
- Android device running Termux (from F-Droid or GitHub release)
- At least 4GB of free internal storage for building ROM packages

#### Installation
Run `start_termux.sh` to automatically install all dependencies:
```bash
chmod +x start_termux.sh
./start_termux.sh
```

Or install dependencies manually:
```bash
pkg update -y
pkg install -y python zstd android-tools
termux-setup-storage
```

#### Building a Flashable Package in Termux
1. Run the interactive tool:
   ```bash
   python main.py
   ```
2. When prompted for `Enter IMGS Path :`, enter the path where your dump is stored, for example:
   ```text
   /sdcard/Download/rom_dump
   ```
3. Complete the interactive prompts. The package will be compiled into `output/`.

#### Flashing the Generated Package in Termux (Device-to-Device via USB OTG)
1. Extract the `.zip` file in Termux:
   ```bash
   unzip output/<package-name>.zip -d /sdcard/Download/flasher
   cd /sdcard/Download/flasher
   ```
2. Connect the target device in Fastboot mode to your phone using a USB OTG cable.
3. Run the Termux installer:
   ```bash
   chmod +x flash_termux.sh
   ./flash_termux.sh
   ```

#### Termux Troubleshooting
- If storage access is denied, run `termux-setup-storage` and grant permission.
- If Termux process gets killed during compression, acquire wake lock by running `termux-wake-lock`.

---

## Interactive Prompts

When running without arguments, the tool interactively prompts for configuration:

```text
========================================================================
                              SpeedFlasher
========================================================================

Enter IMGS Path : C:\path\to\dumped_images
Devicename : Infinix GT 20 Pro
Codename : X6871
Version : 15.1.2.180
AVB 2.0 (vbmeta) : disable
Maintainer : Mehraan
Ztsd Compression (0-22) : 1
Zip Compression (0-9) : 1
```

Once the build finishes, the tool prints a structured summary and waits for Enter before closing:

```text
========================================================================
                      SpeedFlasher Build Summary
========================================================================
Device Name        : Infinix GT 20 Pro
Codename           : X6871
ROM Version        : 15.1.2.180
Maintainer         : Mehraan
AVB 2.0 (vbmeta)   : DISABLE
ZSTD Compression   : Level 1
ZIP Compression    : Level 1
------------------------------------------------------------------------
Partitions Packaged: Total 12
  - Dynamic (Super): 4 (system, vendor, product, system_ext)
  - Direct (System): 5 (boot, dtbo, init_boot, vendor_boot, vbmeta)
  - Firmware/Boot  : 3 (lk, logo, md1img)
------------------------------------------------------------------------
Output File        : output/15.1.2.180-X6871-Flashable.zip
Package Size       : 1845.20 MB
Status             : SUCCESS
========================================================================

Press Enter to exit...
```

## Command Line Usage

For automated environments, pass arguments directly:

```bash
python main.py \
  --imgs-path /path/to/images \
  --device "Infinix GT 20 Pro" \
  --codename "X6871" \
  --version "15.1.2.180" \
  --maintainer "Mehraan" \
  --vbmeta disable \
  --zstd-level 1 \
  --zip-level 1
```

## Running Tests

Execute the test suite across all OS modules:

```bash
python -m unittest discover tests
```

## License

MIT License. See [LICENSE](file:///C:/Users/Admin/Videos/Github/SpeedFlasher/LICENSE) for details.
