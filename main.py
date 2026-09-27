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
    print(f"Output File        : {res.output_zip}")
    print(f"Package Size       : {res.size_mb:.2f} MB")
    print("Status             : SUCCESS")
    print("========================================================================")


def interactive_flow():
    try:
        # Ensure all platform requirements are present
        plat = get_current_platform()
        plat.ensure_dependencies()

        print("========================================================================")
        print("                              SpeedFlasher")
        print("========================================================================")
        print("(Type 'b' or 'back' at any prompt to go back to the previous step)\n")

        cfg = {
            "imgs_path": "",
            "partitions": {},
            "device": "",
            "codename": "",
            "version": "1.0",
            "vbmeta": "skip",
            "maintainer": "Mehraan",
            "zstd_level": 1,
            "zip_level": 1,
        }

        def_device = ""
        def_codename = ""
        def_version = "1.0"

        step = 1
        return_to_review = False

        while True:
            if step == 1:
                prompt = f"Enter IMGS Path [{cfg['imgs_path']}] : " if cfg['imgs_path'] else "Enter IMGS Path : "
                raw = input(prompt).strip()
                if raw.lower() in ("b", "back"):
                    continue
                if raw:
                    path_cand = clean_path(raw)
                else:
                    path_cand = cfg['imgs_path']

                if not path_cand or not os.path.isdir(path_cand):
                    print(f"Error: Directory does not exist: {path_cand or raw}\n")
                    continue

                parts = scan_partitions(path_cand)
                if not parts:
                    print(f"Error: No partition images (.img or .img.zst) found in: {path_cand}\n")
                    continue

                cfg["imgs_path"] = path_cand
                cfg["partitions"] = parts

                # Inspect build.prop for defaults if not already set
                for root, _, files in os.walk(path_cand):
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

                if not cfg["device"]:
                    cfg["device"] = def_device or "Android Device"
                if not cfg["codename"]:
                    cfg["codename"] = def_codename or ""
                if cfg["version"] == "1.0" and def_version != "1.0":
                    cfg["version"] = def_version

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 2

            elif step == 2:
                prompt = f"Devicename [{cfg['device']}] : " if cfg['device'] else "Devicename : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 1
                    return_to_review = False
                    continue
                if val:
                    cfg["device"] = val
                elif not cfg["device"]:
                    cfg["device"] = "Android Device"

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 3

            elif step == 3:
                prompt = f"Codename [{cfg['codename']}] : " if cfg['codename'] else "Codename : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 2
                    return_to_review = False
                    continue
                if val:
                    cfg["codename"] = val

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 4

            elif step == 4:
                prompt = f"Version [{cfg['version']}] : " if cfg['version'] else "Version : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 3
                    return_to_review = False
                    continue
                if val:
                    cfg["version"] = val

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 5

            elif step == 5:
                prompt = f"AVB 2.0 (vbmeta) [{cfg['vbmeta']}] : "
                val = input(prompt).strip().lower()
                if val in ("b", "back"):
                    step = 9 if return_to_review else 4
                    return_to_review = False
                    continue
                if val:
                    if val in ("1", "skip", "s"):
                        cfg["vbmeta"] = "skip"
                    elif val in ("2", "disable", "d"):
                        cfg["vbmeta"] = "disable"
                    elif val in ("3", "enable", "e"):
                        cfg["vbmeta"] = "enable"
                    else:
                        cfg["vbmeta"] = "skip"

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 6

            elif step == 6:
                prompt = f"Maintainer [{cfg['maintainer']}] : " if cfg['maintainer'] else "Maintainer : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 5
                    return_to_review = False
                    continue
                if val:
                    cfg["maintainer"] = val

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 7

            elif step == 7:
                prompt = f"Ztsd Compression (0-22) [{cfg['zstd_level']}] : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 6
                    return_to_review = False
                    continue
                if val:
                    try:
                        lvl = int(val)
                        if 0 <= lvl <= 22:
                            cfg["zstd_level"] = lvl
                        else:
                            print("Notice: Level must be between 0 and 22. Keeping current value.")
                    except ValueError:
                        print("Notice: Invalid number. Keeping current value.")

                if return_to_review:
                    step = 9
                    return_to_review = False
                else:
                    step = 8

            elif step == 8:
                prompt = f"Zip Compression (0-9) [{cfg['zip_level']}] : "
                val = input(prompt).strip()
                if val.lower() in ("b", "back"):
                    step = 9 if return_to_review else 7
                    return_to_review = False
                    continue
                if val:
                    try:
                        lvl = int(val)
                        if 0 <= lvl <= 9:
                            cfg["zip_level"] = lvl
                        else:
                            print("Notice: Level must be between 0 and 9. Keeping current value.")
                    except ValueError:
                        print("Notice: Invalid number. Keeping current value.")

                step = 9

            elif step == 9:
                print("\n------------------------------------------------------------------------")
                print("Build Configuration Review:")
                print(f"  1. IMGS Path       : {cfg['imgs_path']}")
                print(f"  2. Devicename      : {cfg['device']}")
                print(f"  3. Codename        : {cfg['codename']}")
                print(f"  4. Version         : {cfg['version']}")
                print(f"  5. AVB 2.0         : {cfg['vbmeta']}")
                print(f"  6. Maintainer      : {cfg['maintainer']}")
                print(f"  7. ZSTD Level      : {cfg['zstd_level']}")
                print(f"  8. ZIP Level       : {cfg['zip_level']}")
                print("------------------------------------------------------------------------")
                ans = input("Proceed with build? (Y/n, 1-8 to edit, 'b' to go back) [Y] : ").strip().lower()
                if ans in ("", "y", "yes"):
                    break
                elif ans in ("b", "back"):
                    step = 8
                    continue
                elif ans in ("n", "no", "q", "quit", "exit"):
                    print("\n[!] Build cancelled by user.")
                    input("\nPress Enter to exit...")
                    sys.exit(0)
                elif ans in ("1", "2", "3", "4", "5", "6", "7", "8"):
                    step = int(ans)
                    return_to_review = True
                    continue
                else:
                    print("Invalid choice. Enter 'Y' to build, 'n' to cancel, 1-8 to edit a field, or 'b' to go back.")
                    continue

        # Automatically generate output destination into output folder
        out_dir = os.path.join(_ROOT_DIR, "output")
        os.makedirs(out_dir, exist_ok=True)
        out_name = f"{cfg['version']}-{cfg['codename']}-Flashable.zip" if cfg['codename'] else f"{cfg['version']}-Flashable.zip"
        output_zip = os.path.join(out_dir, out_name)

        print(f"\n[*] Output target: {output_zip}")
        print("[*] Starting package build...")

        res = FlashableBuilder.build(
            imgs_dir=cfg["imgs_path"],
            partitions=cfg["partitions"],
            output_zip=output_zip,
            device=cfg["device"],
            firmware=cfg["version"],
            codename=cfg["codename"],
            maintainer=cfg["maintainer"],
            vbmeta_option=cfg["vbmeta"],
            zstd_level=cfg["zstd_level"],
            zip_level=cfg["zip_level"],
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
