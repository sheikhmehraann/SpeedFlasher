import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

ZSTD_FRAME_MAGIC = b"\x28\xb5\x2f\xfd"
SPARSE_HEADER_MAGIC = b"\x3a\xff\x26\xed"


def find_7z_binary() -> Optional[str]:
    for name in ("7z", "7za", "7z.exe"):
        bin_path = shutil.which(name)
        if bin_path:
            return bin_path
    windows_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for p in windows_paths:
        if os.path.isfile(p):
            return p
    linux_paths = [
        "/usr/bin/7z",
        "/usr/local/bin/7z",
        "/data/data/com.termux/files/usr/bin/7z",
    ]
    for p in linux_paths:
        if os.path.isfile(p):
            return p
    return None


class PartitionExtractor:
    @staticmethod
    def detect_metadata(search_dir: str) -> Dict[str, str]:
        meta = {"device": "", "codename": "", "version": ""}
        prop_files = []
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".prop") or file == "build.prop":
                    prop_files.append(os.path.join(root, file))

        for pf in prop_files:
            try:
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if "=" not in line or line.startswith("#"):
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k in ("ro.product.device", "ro.build.product", "ro.product.board") and not meta["codename"]:
                            meta["codename"] = v
                        elif k in ("ro.product.model", "ro.product.marketname") and not meta["device"]:
                            meta["device"] = v
                        elif k in ("ro.build.display.id", "ro.build.version.incremental") and not meta["version"]:
                            meta["version"] = v
            except OSError:
                pass

        if not meta["device"] and meta["codename"]:
            meta["device"] = meta["codename"]
        return meta

    @classmethod
    def unpack_payload_bin(cls, payload_path: str, output_dir: str):
        print(f"[*] Extracting payload.bin -> {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_candidates = [
            os.path.join(root_dir, "bin", "host", "payload-dumper-go.exe"),
            os.path.join(root_dir, "bin", "host", "payload-extract"),
            shutil.which("payload-dumper-go"),
            shutil.which("payload-extract")
        ]
        payload_bin = next((b for b in bin_candidates if b and os.path.isfile(b) and (sys.platform.startswith("win") or os.access(b, os.X_OK))), None)

        if payload_bin:
            subprocess.run([payload_bin, payload_path, output_dir], check=True)
        else:
            try:
                subprocess.run([sys.executable, "-m", "payload_dumper", "--out", output_dir, payload_path], check=True)
            except Exception as e:
                print(f"[!] Warning: payload_dumper failed ({e}). Install payload_dumper or payload-dumper-go.")

    @classmethod
    def unpack_super_img(cls, super_path: str, output_dir: str):
        print(f"[*] Unpacking super.img -> {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lpunpack_bin = os.path.join(root_dir, "bin", "host", "lpunpack")
        if not (os.path.isfile(lpunpack_bin) and os.access(lpunpack_bin, os.X_OK)):
            lpunpack_bin = shutil.which("lpunpack")

        simg2img_bin = os.path.join(root_dir, "bin", "host", "simg2img")
        if not (os.path.isfile(simg2img_bin) and os.access(simg2img_bin, os.X_OK)):
            simg2img_bin = shutil.which("simg2img")

        target_super = super_path
        is_sparse = False
        try:
            with open(super_path, "rb") as f:
                is_sparse = f.read(4) == SPARSE_HEADER_MAGIC
        except OSError:
            pass

        if is_sparse and simg2img_bin:
            unsparse_file = os.path.join(output_dir, "super.raw.img")
            res = subprocess.run([simg2img_bin, super_path, unsparse_file], capture_output=True)
            if res.returncode == 0:
                target_super = unsparse_file

        if lpunpack_bin:
            subprocess.run([lpunpack_bin, target_super, output_dir], check=True)
            if target_super != super_path and os.path.exists(target_super):
                os.remove(target_super)
        else:
            print("[!] Warning: lpunpack not found, super.img left as-is.")

    @classmethod
    def extract_single(cls, archive_path: str, extract_dir: str):
        os.makedirs(extract_dir, exist_ok=True)
        lower = archive_path.lower()
        magic = b""
        try:
            with open(archive_path, "rb") as f:
                magic = f.read(6)
        except OSError:
            pass

        is_zstd = magic.startswith(ZSTD_FRAME_MAGIC) or lower.endswith((".tar.zst", ".tzst", ".zst"))
        is_zip = magic.startswith(b"PK\x03\x04") or lower.endswith(".zip")
        is_7z = magic.startswith(b"7z\xbc\xaf\x27\x1c") or lower.endswith(".7z")
        is_rar = magic.startswith(b"Rar!\x1a\x07") or lower.endswith(".rar")
        is_tar = lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2"))
        seven_zip = find_7z_binary()

        if is_zstd:
            unpacked = False
            if shutil.which("tar"):
                try:
                    subprocess.run(["tar", "-I", "zstd", "-xf", archive_path, "-C", extract_dir], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    unpacked = True
                except Exception:
                    pass
            if not unpacked and seven_zip:
                try:
                    subprocess.run([seven_zip, "x", "-y", f"-o{extract_dir}", archive_path], check=True, stdout=subprocess.DEVNULL)
                    unpacked = True
                except Exception:
                    pass
            if not unpacked:
                try:
                    import tarfile
                    import zstandard
                    dctx = zstandard.ZstdDecompressor()
                    with open(archive_path, "rb") as ifh, dctx.stream_reader(ifh) as reader:
                        with tarfile.open(fileobj=reader, mode="r|") as tar:
                            tar.extractall(path=extract_dir)
                    unpacked = True
                except Exception:
                    pass

        elif (is_7z or is_rar) and seven_zip:
            subprocess.run([seven_zip, "x", "-y", f"-o{extract_dir}", archive_path], check=True, stdout=subprocess.DEVNULL)

        elif is_zip:
            if seven_zip:
                subprocess.run([seven_zip, "x", "-y", f"-o{extract_dir}", archive_path], check=True, stdout=subprocess.DEVNULL)
            elif shutil.which("unzip"):
                subprocess.run(["unzip", "-q", "-o", archive_path, "-d", extract_dir], check=True)
            else:
                import zipfile
                with zipfile.ZipFile(archive_path, "r") as z:
                    z.extractall(extract_dir)

        elif is_tar:
            if shutil.which("tar"):
                try:
                    subprocess.run(["tar", "-xf", archive_path, "-C", extract_dir], check=True)
                except Exception:
                    import tarfile
                    with tarfile.open(archive_path, "r:*") as t:
                        t.extractall(extract_dir)
            else:
                import tarfile
                with tarfile.open(archive_path, "r:*") as t:
                    t.extractall(extract_dir)

        else:
            if seven_zip:
                subprocess.run([seven_zip, "x", "-y", f"-o{extract_dir}", archive_path], check=True, stdout=subprocess.DEVNULL)

    @classmethod
    def extract_recursive(cls, initial_archive: str, extract_dir: str, max_depth: int = 5):
        print(f"[*] Extracting archive: {initial_archive}")
        cls.extract_single(initial_archive, extract_dir)

        for depth in range(1, max_depth + 1):
            nested_found = False
            for root, _, files in os.walk(extract_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    fl = f.lower()

                    if fl == "payload.bin":
                        cls.unpack_payload_bin(fp, os.path.join(root, "_payload_extracted"))
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
                        nested_found = True
                        continue

                    if fl == "super.img":
                        cls.unpack_super_img(fp, os.path.join(root, "_super_extracted"))
                        try:
                            os.remove(fp)
                        except OSError:
                            pass
                        nested_found = True
                        continue

                    if fl.endswith((".zip", ".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.zst", ".7z", ".rar")) and not fl.endswith(".img"):
                        print(f"[*] Nested archive (depth {depth}): {f}")
                        nested_dir = os.path.join(root, f"_unpacked_{f}")
                        try:
                            cls.extract_single(fp, nested_dir)
                            os.remove(fp)
                            nested_found = True
                        except Exception as e:
                            print(f"[!] Warning: Failed unpacking {f}: {e}")

            if not nested_found:
                break

        print(f"[+] Archive extracted: {extract_dir}")
