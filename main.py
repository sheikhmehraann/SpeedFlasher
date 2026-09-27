#!/usr/bin/env python3
import argparse
import os
import sys

# Add bin subdirectories to PATH based on platform
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.platform.startswith("win"):
    _OS_BIN = os.path.join(_ROOT_DIR, "bin", "windows")
else:
    _OS_BIN = os.path.join(_ROOT_DIR, "bin", "linux")

if os.path.isdir(_OS_BIN) and _OS_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_OS_BIN}{os.pathsep}{os.environ.get('PATH', '')}"

from core.builder import FlashableBuilder, get_current_platform
from core.partitions import scan_partitions


def clean_path(raw: str) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return ""
    return os.path.abspath(os.path.expanduser(cleaned))


def print_summary(res):
    print("\n========================================================================")
    print("                      SpeedFlasher Build Summary")
    print("========================================================================")
    print(f"Device Name        : {res.device}")
    if getattr(res, "codename", ""):
        print(f"Codename           : {res.codename}")
    print(f"ROM Version        : {res.firmware}")
    print(f"Maintainer         : {res.maintainer}")
    print(f"AVB 2.0 (vbmeta)   : {res.vbmeta_option.upper()}")
    print(f"ZSTD Compression   : Level {res.zstd_level}")
    print(f"ZIP Compression    : Level {res.zip_level}")
    print("-" * 72)

    super_pts = getattr(res, "super_partitions", [])
    sys_pts = getattr(res, "system_partitions", [])
    fw_pts = getattr(res, "firmware_partitions", [])
    total_pts = len(super_pts) + len(sys_pts) + len(fw_pts)

    print(f"Partitions Packaged: Total {total_pts}")
    if super_pts:
        print(f"  - Dynamic (Super): {len(super_pts)} ({', '.join(super_pts)})")
    if sys_pts:
        print(f"  - Direct (System): {len(sys_pts)} ({', '.join(sys_pts)})")
    if fw_pts:
        print(f"  - Firmware/Boot  : {len(fw_pts)} ({', '.join(fw_pts)})")

    print("-" * 72)
    print("Installers Generated:")
    print("  - Recovery ZIP    : META-INF/com/google/android/update-binary")
    print("  - Windows Fastboot: flash_windows.bat (with bundled tools)")
    print("  - Linux Fastboot  : flash_linux.sh")
    print("  - Termux Fastboot : flash_termux.sh")
    print("-" * 72)
    print(f"Output File        : {res.output_zip}")
    print(f"Package Size       : {res.size_mb:.2f} MB")
    print("Status             : SUCCESS")
    print("========================================================================")


def interactive_flow():
    try:
        # 1. Ensure all platform requirements are present
        plat = get_current_platform()
        plat.ensure_dependencies()

        print("========================================================================")
        print("                              SpeedFlasher")
        print("========================================================================\n")

        raw_path = input("Enter IMGS Path : ").strip()
        imgs_path = clean_path(raw_path)
        if not imgs_path or not os.path.isdir(imgs_path):
            print(f"\nError: Directory does not exist: {imgs_path or raw_path}")
            input("\nPress Enter to exit...")
            sys.exit(1)

        partitions = scan_partitions(imgs_path)
        if not partitions:
            print(f"\nError: No partition images (.img or .img.zst) found in: {imgs_path}")
            input("\nPress Enter to exit...")
            sys.exit(1)

        # Inspect build.prop for defaults if present
        def_device = ""
        def_codename = ""
        def_version = "1.0"
        for root, _, files in os.walk(imgs_path):
            for f in files:
                if f.endswith(".prop") or f == "build.prop":
                    try:
                        with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as pf:
                            for line in pf:
                                line = line.strip()
                                if "=" not in line or line.startswith("#"):
                                    continue
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k in ("ro.product.device", "ro.build.product", "ro.product.board") and not def_codename:
                                    def_codename = v
                                elif k in ("ro.product.model", "ro.product.marketname") and not def_device:
                                    def_device = v
                                elif k in ("ro.build.display.id", "ro.build.version.incremental") and def_version == "1.0":
                                    def_version = v
                    except OSError:
                        pass

        devicename_prompt = f"Devicename [{def_device}] : " if def_device else "Devicename : "
        codename_prompt = f"Codename [{def_codename}] : " if def_codename else "Codename : "
        version_prompt = f"Version [{def_version}] : " if def_version != "1.0" else "Version : "

        devicename_input = input(devicename_prompt).strip()
        devicename = devicename_input or def_device or "Android Device"

        codename_input = input(codename_prompt).strip()
        codename = codename_input or def_codename or ""

        version_input = input(version_prompt).strip()
        version = version_input or def_version

        avb_raw = input("AVB 2.0 (vbmeta) : ").strip().lower()
        if avb_raw in ("1", "skip", "s", ""):
            avb_mode = "skip"
        elif avb_raw in ("2", "disable", "d"):
            avb_mode = "disable"
        elif avb_raw in ("3", "enable", "e"):
            avb_mode = "enable"
        else:
            avb_mode = "skip"

        maintainer_input = input("Maintainer : ").strip()
        maintainer = maintainer_input or "Mehraan"

        zstd_raw = input("Ztsd Compression (0-22) : ").strip()
        try:
            zstd_level = int(zstd_raw) if zstd_raw else 1
        except ValueError:
            zstd_level = 1

        zip_raw = input("Zip Compression (0-9) : ").strip()
        try:
            zip_level = int(zip_raw) if zip_raw else 1
        except ValueError:
            zip_level = 1

        # Automatically generate output destination into output folder
        out_dir = os.path.join(_ROOT_DIR, "output")
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{version}-{codename}-Flashable.zip" if codename else f"{version}-Flashable.zip"
        output_zip = os.path.join(out_dir, out_name)

        print(f"\n[*] Output target: {output_zip}")
        print("[*] Starting package build...")

        res = FlashableBuilder.build(
            imgs_dir=imgs_path,
            partitions=partitions,
            output_zip=output_zip,
            device=devicename,
            firmware=version,
            codename=codename,
            maintainer=maintainer,
            vbmeta_option=avb_mode,
            zstd_level=zstd_level,
            zip_level=zip_level,
            include_fastboot=True
        )

        print_summary(res)
        input("\nPress Enter to exit...")

    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user.")
        input("\nPress Enter to exit...")
        sys.exit(130)
    except Exception as e:
        print(f"\n[Error] Build failed: {e}")
        input("\nPress Enter to exit...")
        sys.exit(1)


def cli_flow():
    plat = get_current_platform()
    plat.ensure_dependencies()

    parser = argparse.ArgumentParser(description="SpeedFlasher - Universal Flashable Package Maker")
    parser.add_argument("-i", "--imgs-path", "--rom-dir", dest="imgs_path", help="Directory containing partition images")
    parser.add_argument("-d", "--device", default="Android Device", help="Device marketing name")
    parser.add_argument("-c", "--codename", default="", help="Device board codename")
    parser.add_argument("-v", "--version", default="1.0", help="Firmware / ROM version")
    parser.add_argument("-m", "--maintainer", default="Mehraan", help="Maintainer name")
    parser.add_argument("--vbmeta", choices=["skip", "disable", "enable"], default="skip", help="AVB 2.0 vbmeta mode")
    parser.add_argument("--zstd-level", type=int, default=1, help="ZSTD compression level (0-22)")
    parser.add_argument("--zip-level", type=int, default=1, help="ZIP compression level (0-9)")
    parser.add_argument("-o", "--output", help="Optional custom output ZIP path")
    parser.add_argument("--no-fastboot", action="store_true", help="Exclude Fastboot installer scripts and binaries")

    args = parser.parse_args()

    imgs_path = clean_path(args.imgs_path)
    if not imgs_path or not os.path.isdir(imgs_path):
        print(f"Error: Directory does not exist: {imgs_path or args.imgs_path}")
        sys.exit(1)

    partitions = scan_partitions(imgs_path)
    if not partitions:
        print(f"Error: No partition images found in: {imgs_path}")
        sys.exit(1)

    out_dir = os.path.join(_ROOT_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_name = f"{args.version}-{args.codename}-Flashable.zip" if args.codename else f"{args.version}-Flashable.zip"
    output_zip = clean_path(args.output) if args.output else os.path.join(out_dir, out_name)

    res = FlashableBuilder.build(
        imgs_dir=imgs_path,
        partitions=partitions,
        output_zip=output_zip,
        device=args.device,
        firmware=args.version,
        codename=args.codename,
        maintainer=args.maintainer,
        vbmeta_option=args.vbmeta,
        zstd_level=args.zstd_level,
        zip_level=args.zip_level,
        include_fastboot=not args.no_fastboot
    )

    print_summary(res)


def main():
    if len(sys.argv) == 1:
        interactive_flow()
    else:
        cli_flow()


if __name__ == "__main__":
    main()
