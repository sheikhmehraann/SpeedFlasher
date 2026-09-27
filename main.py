#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path

# Add bin/host to PATH
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_HOST_BIN = os.path.join(_ROOT_DIR, "bin", "host")
if os.path.isdir(_HOST_BIN) and _HOST_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_HOST_BIN}{os.pathsep}{os.environ.get('PATH', '')}"

from core.builder import FlashableBuilder


def clean_input_path(raw: str) -> str:
    cleaned = raw.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def interactive_mode():
    print("========================================================================")
    print("                              SpeedFlasher")
    print("========================================================================\n")

    raw_dir = input("Partition IMGS Directory: ").strip()
    imgs_dir = clean_input_path(raw_dir)
    if not imgs_dir or not os.path.isdir(imgs_dir):
        print(f"Error: Invalid directory '{imgs_dir}'")
        sys.exit(1)

    device = input("Device Name (e.g. Infinix GT 20 Pro): ").strip() or "Android Device"
    codename = input("Device Codename (e.g. X6871): ").strip()
    version = input("ROM Version (e.g. 15.1.2.180): ").strip() or "1.0"
    maintainer = input("Maintainer [default: Mehraan]: ").strip() or "Mehraan"
    vbmeta = input("AVB 2.0 Vbmeta (disable/enable/skip) [default: skip]: ").strip().lower() or "skip"
    
    zstd_raw = input("ZSTD Compression Level (0-22) [default: 1]: ").strip()
    zstd_level = int(zstd_raw) if zstd_raw.isdigit() else 1

    zip_raw = input("ZIP Level (0=Store, 1-9=Deflate) [default: 1]: ").strip()
    zip_level = int(zip_raw) if zip_raw.isdigit() else 1

    out_name = f"{version}-{codename}-Flashable.zip" if codename else f"{version}-Flashable.zip"
    out_dir = os.path.join(_ROOT_DIR, "output")
    default_out = os.path.join(out_dir, out_name)
    raw_out = input(f"Output ZIP Path [default: {default_out}]: ").strip()
    output_zip = clean_input_path(raw_out) if raw_out else default_out

    print("\n[*] Starting build process...")
    FlashableBuilder.build(
        imgs_dir=imgs_dir,
        output_zip=output_zip,
        device=device,
        firmware=version,
        codename=codename,
        maintainer=maintainer,
        vbmeta_option=vbmeta,
        zstd_level=zstd_level,
        zip_level=zip_level,
        include_fastboot=True
    )


def main():
    parser = argparse.ArgumentParser(description="SpeedFlasher - Universal Flashable Package Maker")
    parser.add_argument("-i", "--imgs-dir", help="Directory containing partition images (.img, .img.zst)")
    parser.add_argument("-o", "--output", help="Output .zip package path")
    parser.add_argument("-d", "--device", default="Android Device", help="Device marketing name")
    parser.add_argument("-c", "--codename", default="", help="Device board codename")
    parser.add_argument("-v", "--version", default="1.0", help="Firmware / ROM version")
    parser.add_argument("-m", "--maintainer", default="Mehraan", help="Maintainer name")
    parser.add_argument("--vbmeta", choices=["disable", "enable", "skip"], default="skip", help="AVB 2.0 action")
    parser.add_argument("--zstd-level", type=int, default=1, help="ZSTD compression level (0-22)")
    parser.add_argument("--zip-level", type=int, default=1, help="ZIP compression level (0-9)")
    parser.add_argument("--no-fastboot", action="store_true", help="Exclude Fastboot installer scripts and binaries")

    args = parser.parse_args()

    if not args.imgs_dir and len(sys.argv) == 1:
        interactive_mode()
        return

    if not args.imgs_dir:
        interactive_mode()
        return

    imgs_dir = clean_input_path(args.imgs_dir)
    if not os.path.isdir(imgs_dir):
        print(f"Error: Directory '{imgs_dir}' does not exist.")
        sys.exit(1)

    out_name = f"{args.version}-{args.codename}-Flashable.zip" if args.codename else f"{args.version}-Flashable.zip"
    default_out = os.path.join(_ROOT_DIR, "output", out_name)
    output_zip = clean_input_path(args.output) if args.output else default_out

    FlashableBuilder.build(
        imgs_dir=imgs_dir,
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


if __name__ == "__main__":
    main()
