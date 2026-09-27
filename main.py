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
from core.downloader import FastDownloader
from core.extractor import PartitionExtractor
from core.partitions import scan_partitions


def clean_input_path(raw: str) -> str:
    cleaned = raw.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def resolve_source(source: str, workspace_dir: str) -> str:
    source = clean_input_path(source)
    if not source:
        raise ValueError("Source path or URL cannot be empty.")

    if source.startswith(("http://", "https://")):
        archive_path = os.path.join(workspace_dir, "downloaded_rom")
        downloaded = FastDownloader.download(source, archive_path)
        extracted_dir = os.path.join(workspace_dir, "extracted")
        PartitionExtractor.extract_recursive(downloaded, extracted_dir)
        if os.path.exists(downloaded):
            try:
                os.remove(downloaded)
            except OSError:
                pass
        return extracted_dir

    if os.path.isfile(source):
        extracted_dir = os.path.join(workspace_dir, "extracted")
        PartitionExtractor.extract_recursive(source, extracted_dir)
        return extracted_dir

    if os.path.isdir(source):
        return source

    raise FileNotFoundError(f"Source not found: {source}")


def interactive_mode():
    print("========================================================================")
    print("                              SpeedFlasher")
    print("========================================================================\n")

    raw_src = input("ROM Images Directory, Archive, or URL: ").strip()
    workspace_dir = os.path.abspath("build_workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    imgs_dir = resolve_source(raw_src, workspace_dir)
    partitions = scan_partitions(imgs_dir)
    if not partitions:
        print(f"Error: No partition images found in '{imgs_dir}'")
        sys.exit(1)

    # Auto-detect device metadata from extracted files
    meta = PartitionExtractor.detect_metadata(imgs_dir)
    def_device = meta.get("device") or "Android Device"
    def_codename = meta.get("codename") or ""
    def_version = meta.get("version") or "1.0"

    print(f"\n[+] Found {len(partitions)} partition(s)")
    if def_codename:
        print(f"[+] Detected Device: {def_device} ({def_codename}), Version: {def_version}")

    device = input(f"Device Name [{def_device}]: ").strip() or def_device
    codename = input(f"Device Codename [{def_codename}]: ").strip() or def_codename
    version = input(f"ROM Version [{def_version}]: ").strip() or def_version
    maintainer = input("Maintainer [Mehraan]: ").strip() or "Mehraan"
    vbmeta = input("AVB 2.0 Vbmeta (disable/enable/skip) [skip]: ").strip().lower() or "skip"

    zstd_raw = input("ZSTD Compression Level (0-22) [1]: ").strip()
    zstd_level = int(zstd_raw) if zstd_raw.isdigit() else 1

    zip_raw = input("ZIP Level (0=Store, 1-9=Deflate) [1]: ").strip()
    zip_level = int(zip_raw) if zip_raw.isdigit() else 1

    out_name = f"{version}-{codename}-Flashable.zip" if codename else f"{version}-Flashable.zip"
    default_out = os.path.join(_ROOT_DIR, "output", out_name)
    raw_out = input(f"Output ZIP [{default_out}]: ").strip()
    output_zip = clean_input_path(raw_out) if raw_out else default_out

    print("\n[*] Starting build process...")
    FlashableBuilder.build(
        imgs_dir=imgs_dir,
        partitions=partitions,
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
    parser.add_argument("-i", "--rom-dir", "--imgs-dir", dest="rom_dir", help="Directory containing partition images")
    parser.add_argument("-f", "--file", help="Path to local archive (.zip, .tar.zst, payload.bin, super.img)")
    parser.add_argument("-u", "--url", help="Direct URL to ROM archive")
    parser.add_argument("-o", "--output", help="Output .zip package path")
    parser.add_argument("-d", "--device", default="", help="Device marketing name")
    parser.add_argument("-c", "--codename", default="", help="Device board codename")
    parser.add_argument("-v", "--version", default="", help="Firmware / ROM version")
    parser.add_argument("-m", "--maintainer", default="Mehraan", help="Maintainer name")
    parser.add_argument("--vbmeta", choices=["disable", "enable", "skip"], default="skip", help="AVB 2.0 action")
    parser.add_argument("--zstd-level", type=int, default=1, help="ZSTD compression level (0-22)")
    parser.add_argument("--zip-level", type=int, default=1, help="ZIP compression level (0-9)")
    parser.add_argument("--no-fastboot", action="store_true", help="Exclude Fastboot installer scripts and binaries")

    args = parser.parse_args()

    if not args.rom_dir and not args.file and not args.url:
        interactive_mode()
        return

    workspace_dir = os.path.abspath("build_workspace")
    os.makedirs(workspace_dir, exist_ok=True)

    src = args.url or args.file or args.rom_dir
    imgs_dir = resolve_source(src, workspace_dir)
    partitions = scan_partitions(imgs_dir)
    if not partitions:
        print(f"Error: No partition images found in '{imgs_dir}'")
        sys.exit(1)

    meta = PartitionExtractor.detect_metadata(imgs_dir)
    device = args.device or meta.get("device") or "Android Device"
    codename = args.codename or meta.get("codename") or ""
    version = args.version or meta.get("version") or "1.0"

    out_name = f"{version}-{codename}-Flashable.zip" if codename else f"{version}-Flashable.zip"
    default_out = os.path.join(_ROOT_DIR, "output", out_name)
    output_zip = clean_input_path(args.output) if args.output else default_out

    FlashableBuilder.build(
        imgs_dir=imgs_dir,
        partitions=partitions,
        output_zip=output_zip,
        device=device,
        firmware=version,
        codename=codename,
        maintainer=args.maintainer,
        vbmeta_option=args.vbmeta,
        zstd_level=args.zstd_level,
        zip_level=args.zip_level,
        include_fastboot=not args.no_fastboot
    )


if __name__ == "__main__":
    main()
