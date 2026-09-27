import os
import shutil
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .avb import AvbManager
from .partitions import scan_partitions, get_zstd_uncompressed_size
from .scripts import (
    generate_update_binary,
    generate_fastboot_windows,
    generate_fastboot_linux,
    generate_fastboot_termux
)


def get_host_zstd() -> str:
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(script_dir, "bin", "host", "zstd.exe"),
        os.path.join(script_dir, "bin", "host", "zstd"),
        shutil.which("zstd.exe"),
        shutil.which("zstd")
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            if sys.platform.startswith("win") or os.access(c, os.X_OK):
                return c
    return ""


def fast_stage_file(src: str, dst: str):
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError:
            pass
    try:
        os.link(src, dst)
    except (OSError, AttributeError):
        shutil.copy2(src, dst)


def compress_single_image_worker(task: Tuple[str, str, str, int, int, int, str]) -> Tuple[str, int]:
    name, in_file, out_file, level, raw_size, threads, z_bin = task

    th_arg = f"-T{threads}"
    if level <= 0:
        cmd_args = ["--fast=10", th_arg, "-f", "-q", in_file, "-o", out_file]
    elif level >= 20:
        cmd_args = [f"-{level}", "--ultra", th_arg, "-f", "-q", in_file, "-o", out_file]
    else:
        cmd_args = [f"-{level}", th_arg, "-f", "-q", in_file, "-o", out_file]

    compressed = False
    if z_bin and os.path.isfile(z_bin):
        try:
            subprocess.run([z_bin] + cmd_args, check=True)
            compressed = True
        except Exception:
            pass

    if not compressed:
        try:
            import zstandard
            c_level = max(1, min(level, 19 if level > 19 else (1 if level <= 0 else level)))
            try:
                cctx = zstandard.ZstdCompressor(level=c_level, threads=threads)
            except TypeError:
                cctx = zstandard.ZstdCompressor(level=c_level)
            with open(in_file, "rb") as ifh, open(out_file, "wb") as ofh:
                cctx.copy_stream(ifh, ofh)
        except Exception as e:
            raise RuntimeError(f"Compression failed for {in_file}: {e}")

    return name, raw_size


class FlashableBuilder:
    @classmethod
    def package_zip(cls, work_dir: str, output_zip: str, zip_level: int = 1):
        abs_output = os.path.abspath(output_zip)
        out_dir = os.path.dirname(abs_output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        if os.path.exists(abs_output):
            try:
                os.remove(abs_output)
            except OSError:
                pass

        print(f"[*] Packaging ZIP (Level {zip_level}): {os.path.basename(output_zip)}")

        executable_names = {
            "update-binary", "zstd", "lptools", "avbctl",
            "rapidflasher-arm64", "lpdump", "lpmake", "fastboot",
            "flash_linux.sh", "flash_termux.sh"
        }

        compression = zipfile.ZIP_STORED if zip_level == 0 else zipfile.ZIP_DEFLATED
        kwargs = {"compresslevel": zip_level} if zip_level > 0 else {}

        with zipfile.ZipFile(abs_output, "w", compression=compression, **kwargs) as z:
            for root, dirs, files in os.walk(work_dir):
                for d in dirs:
                    dp = os.path.join(root, d)
                    rp = os.path.relpath(dp, work_dir).replace("\\", "/") + "/"
                    zinfo = zipfile.ZipInfo(filename=rp)
                    zinfo.date_time = time.localtime(os.stat(dp).st_mtime)[:6]
                    zinfo.create_system = 3
                    zinfo.external_attr = (0o040755) << 16
                    z.writestr(zinfo, b"")

                for f in files:
                    fp = os.path.join(root, f)
                    rp = os.path.relpath(fp, work_dir).replace("\\", "/")
                    is_exec = (
                        f in executable_names or
                        rp.startswith("META-INF/bin/") or
                        rp.endswith("update-binary") or
                        rp == "META-INF/zstd" or
                        rp.endswith(".sh")
                    )

                    zinfo = zipfile.ZipInfo(filename=rp)
                    st = os.stat(fp)
                    zinfo.date_time = time.localtime(st.st_mtime)[:6]
                    zinfo.compress_type = compression
                    zinfo.create_system = 3

                    if is_exec:
                        zinfo.external_attr = (0o100755) << 16
                    else:
                        zinfo.external_attr = (0o100644) << 16

                    with open(fp, "rb") as src_f, z.open(zinfo, mode="w") as dst_f:
                        shutil.copyfileobj(src_f, dst_f, length=8 * 1024 * 1024)

    @classmethod
    def build(
        cls,
        imgs_dir: str,
        output_zip: str,
        device: str,
        firmware: str,
        codename: str,
        maintainer: str = "Mehraan",
        vbmeta_option: str = "skip",
        zstd_level: int = 1,
        zip_level: int = 1,
        include_fastboot: bool = True
    ) -> str:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        host_zstd = get_host_zstd()

        print(f"[*] Scanning partitions in {imgs_dir}...")
        partitions = scan_partitions(imgs_dir, zstd_bin=host_zstd)
        if not partitions:
            raise ValueError(f"No valid partition images (.img or .img.zst) found in {imgs_dir}")

        print(f"[+] Found {len(partitions)} partition(s): {', '.join(sorted(partitions.keys()))}")

        work_dir = os.path.abspath("zip_workspace")
        staging_dir = os.path.abspath("temp_staging")
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)
        meta_dir = os.path.join(work_dir, "META-INF", "com", "google", "android")
        os.makedirs(meta_dir, exist_ok=True)

        if vbmeta_option in ("disable", "enable") and "vbmeta" in partitions:
            try:
                avb_mgr = AvbManager(vbmeta_option)
                vb_info = partitions["vbmeta"]
                if not vb_info["is_zstd"] and os.path.isfile(vb_info["path"]):
                    staged_vbmeta = os.path.join(staging_dir, "vbmeta_staged.img")
                    shutil.copy2(vb_info["path"], staged_vbmeta)
                    if avb_mgr.patch_vbmeta_image(Path(staged_vbmeta)):
                        print(f"[*] Pre-patched vbmeta header flags -> {vbmeta_option.upper()}")
                        partitions["vbmeta"]["path"] = staged_vbmeta
            except Exception as e:
                print(f"[!] Notice: vbmeta header patch skipped: {e}")

        compress_tasks = []
        super_specs = []
        tr_specs = []
        system_imgs = []
        firmware_imgs = []
        super_imgs = []

        use_zstd = zstd_level > 0
        for name, info in partitions.items():
            src_path = info["path"]
            is_zst = info["is_zstd"]
            raw_size = info["raw_size"]
            ptype = info["type"]

            if ptype == "super_tr":
                tr_specs.append((name, raw_size))
                super_imgs.append(name)
            elif ptype == "super":
                super_specs.append((name, raw_size))
                super_imgs.append(name)
            elif ptype == "system":
                system_imgs.append(name)
            else:
                firmware_imgs.append(name)

            if use_zstd:
                target_file = os.path.join(work_dir, f"{name}.img.zst")
                if is_zst:
                    fast_stage_file(src_path, target_file)
                else:
                    compress_tasks.append((name, src_path, target_file, zstd_level, raw_size))
            else:
                target_file = os.path.join(work_dir, f"{name}.img")
                fast_stage_file(src_path, target_file)

        if compress_tasks:
            compress_tasks.sort(key=lambda t: t[4], reverse=True)
            total_cpus = os.cpu_count() or 4
            workers = min(len(compress_tasks), total_cpus)
            threads_per_worker = max(1, total_cpus // workers)
            tasks_with_threads = [
                (t[0], t[1], t[2], t[3], t[4], threads_per_worker, host_zstd) for t in compress_tasks
            ]
            print(f"[*] Compressing {len(tasks_with_threads)} partition image(s) to .zst (level {zstd_level}, {workers} workers x {threads_per_worker}T)...")
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(compress_single_image_worker, t) for t in tasks_with_threads]
                for f in as_completed(futures):
                    name, raw_size = f.result()
                    print(f"    [+] Compressed {name}.img -> {name}.img.zst")
                    if any(n == name for n, _ in tr_specs):
                        tr_specs = [(n, raw_size if n == name else s) for n, s in tr_specs]
                    elif any(n == name for n, _ in super_specs):
                        super_specs = [(n, raw_size if n == name else s) for n, s in super_specs]

        # Stage recovery binaries
        print("[*] Staging recovery binaries...")
        if use_zstd:
            zstd_rec_path = os.path.join(work_dir, "META-INF", "zstd")
            zstd_src = os.path.join(root_dir, "bin", "device", "zstd-arm64")
            if os.path.exists(zstd_src):
                fast_stage_file(zstd_src, zstd_rec_path)

        bin_dir_target = os.path.join(work_dir, "META-INF", "bin")
        bin_dir_src = os.path.join(root_dir, "bin", "device")
        if os.path.exists(bin_dir_src):
            os.makedirs(bin_dir_target, exist_ok=True)
            for b in ["lptools", "avbctl", "rapidflasher-arm64", "lpdump", "lpmake"]:
                b_src = os.path.join(bin_dir_src, b)
                if os.path.exists(b_src):
                    fast_stage_file(b_src, os.path.join(bin_dir_target, b))

        # Write recovery update-binary and updater-script
        print("[*] Generating recovery update-binary...")
        update_binary_content = generate_update_binary(
            device, firmware, codename, super_specs, system_imgs, firmware_imgs, tr_specs,
            maintainer=maintainer, vbmeta_option=vbmeta_option, use_zstd=use_zstd
        )
        update_binary_path = os.path.join(meta_dir, "update-binary")
        with open(update_binary_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(update_binary_content)
        try:
            os.chmod(update_binary_path, 0o755)
        except OSError:
            pass

        with open(os.path.join(meta_dir, "updater-script"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# SpeedFlasher installer\n")

        # Stage Fastboot installer scripts and binaries if enabled
        if include_fastboot:
            print("[*] Staging fastboot installer scripts and binaries...")
            fastboot_dir = os.path.join(work_dir, "bin", "fastboot")
            src_fastboot_dir = os.path.join(root_dir, "bin", "fastboot")
            if os.path.exists(src_fastboot_dir):
                os.makedirs(fastboot_dir, exist_ok=True)
                for item in os.listdir(src_fastboot_dir):
                    s = os.path.join(src_fastboot_dir, item)
                    d = os.path.join(fastboot_dir, item)
                    fast_stage_file(s, d)

            fb_win = generate_fastboot_windows(device, codename, firmware_imgs, system_imgs, super_imgs, use_zstd=use_zstd)
            fb_lin = generate_fastboot_linux(device, codename, firmware_imgs, system_imgs, super_imgs, use_zstd=use_zstd)
            fb_tmx = generate_fastboot_termux(device, codename, firmware_imgs, system_imgs, super_imgs, use_zstd=use_zstd)

            with open(os.path.join(work_dir, "flash_windows.bat"), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(fb_win)
            with open(os.path.join(work_dir, "flash_linux.sh"), "w", encoding="utf-8", newline="\n") as f:
                f.write(fb_lin)
            try:
                os.chmod(os.path.join(work_dir, "flash_linux.sh"), 0o755)
            except OSError:
                pass
            with open(os.path.join(work_dir, "flash_termux.sh"), "w", encoding="utf-8", newline="\n") as f:
                f.write(fb_tmx)
            try:
                os.chmod(os.path.join(work_dir, "flash_termux.sh"), 0o755)
            except OSError:
                pass

        # Build final ZIP
        cls.package_zip(work_dir, output_zip, zip_level=zip_level)
        shutil.rmtree(work_dir, ignore_errors=True)
        shutil.rmtree(staging_dir, ignore_errors=True)

        size_mb = os.path.getsize(output_zip) / (1024 * 1024)
        print(f"[+] Package created: {output_zip} ({size_mb:.2f} MB)")
        return output_zip
