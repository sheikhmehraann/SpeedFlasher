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
    cleaned = raw.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def interactive_flow():
    # 1. Ensure all platform requirements are present
    plat = get_current_platform()
    plat.ensure_dependencies()

    print("========================================================================")
    print("                              SpeedFlasher")
    print("========================================================================\n")

    raw_path = input("Enter IMGS Path : ").strip()
    imgs_path = clean_path(raw_path)
    if not imgs_path or not os.path.isdir(imgs_path):
        print(f"\nError: Directory does not exist: {imgs_path}")
        sys.exit(1)

    partitions = scan_partitions(imgs_path)
    if not partitions:
        print(f"\nError: No partition images (.img or .img.zst) found in: {imgs_path}")
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

    avb_raw = input("AVB 2.0 (vbmeta) [skip/disable/enable] : ").strip().lower()
    avb_mode = avb_raw if avb_raw in ("disable", "enable") else "skip"

    maintainer_input = input("Maintainer [Mehraan] : ").strip()
    maintainer = maintainer_input or "Mehraan"

    zstd_raw = input("Ztsd Compression (0-22) [1] : ").strip()
    try:
        zstd_level = int(zstd_raw) if zstd_raw else 1
    except ValueError:
        zstd_level = 1

    zip_raw = input("Zip Compression (0-9) [1] : ").strip()
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

    FlashableBuilder.build(
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
    if not os.path.isdir(imgs_path):
        print(f"Error: Directory does not exist: {imgs_path}")
        sys.exit(1)

    partitions = scan_partitions(imgs_path)
    if not partitions:
        print(f"Error: No partition images found in: {imgs_path}")
        sys.exit(1)

    out_dir = os.path.join(_ROOT_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_name = f"{args.version}-{args.codename}-Flashable.zip" if args.codename else f"{args.version}-Flashable.zip"
    output_zip = clean_path(args.output) if args.output else os.path.join(out_dir, out_name)

    FlashableBuilder.build(
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


def main():
    if len(sys.argv) == 1:
        interactive_flow()
    else:
        cli_flow()


if __name__ == "__main__":
    main()
