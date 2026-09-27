import json
import os
import shutil
import subprocess
from typing import Any, Dict, Tuple

ZSTD_FRAME_MAGIC = b"\x28\xb5\x2f\xfd"
SPARSE_HEADER_MAGIC = b"\x3a\xff\x26\xed"

SUPER_PARTITIONS = {
    "system", "vendor", "product", "system_dlkm", "system_ext",
    "vendor_dlkm", "odm_dlkm", "odm", "mi_ext", "cust",
    "prism", "optics", "my_product", "my_stock", "my_heytap",
    "my_carrier", "my_region", "my_manifest", "my_preload",
    "my_company", "my_engineering", "my_bigball"
}

SUPER_TR_PARTITIONS = {
    "tr_carrier", "tr_company", "tr_mi", "tr_overlayfs", "tr_preload",
    "tr_product", "tr_region", "tr_theme", "tr_manifest", "tr_misc",
    "tr_vintf", "tr_vendor"
}

SYSTEM_PARTITIONS = {
    "boot", "dtbo", "init_boot", "vendor_boot", "recovery",
    "vbmeta", "vbmeta_system", "vbmeta_vendor", "pvmfw"
}

FIRMWARE_PARTITIONS = {
    "apusys", "cam_vpu1", "cam_vpu2", "cam_vpu3", "ccu", "connsys_bt",
    "dpm", "gpueb", "gz", "lk", "logo", "mcf_ota", "mcupm", "md1img",
    "mvpu_algo", "pi_img", "preloader_raw", "preloader", "scp", "spmfw", "sspm",
    "tee", "tkv", "vcp", "modem", "bluetooth", "dsp", "hyp", "tz", "uefi",
    "xbl", "xbl_config", "abl"
}


def is_zstd_file(file_path: str) -> bool:
    if not os.path.isfile(file_path) or os.path.getsize(file_path) < 4:
        return False
    try:
        with open(file_path, "rb") as f:
            return f.read(4) == ZSTD_FRAME_MAGIC
    except OSError:
        return False


def is_sparse_file(file_path: str) -> bool:
    if not os.path.isfile(file_path) or os.path.getsize(file_path) < 4:
        return False
    try:
        with open(file_path, "rb") as f:
            return f.read(4) == SPARSE_HEADER_MAGIC
    except OSError:
        return False


def is_filesystem_image(file_path: str) -> bool:
    if not os.path.isfile(file_path) or os.path.getsize(file_path) < 2048:
        return False
    try:
        with open(file_path, "rb") as f:
            f.seek(1024)
            buf = f.read(16)
            # ext4 or erofs magic
            if buf.startswith(b"\xe2\xe1\xf5\xe0") or buf.startswith(b"\x10\x20\xf5\xf2"):
                return True
            f.seek(1080)
            # f2fs magic
            if f.read(2) == b"\x53\xef":
                return True
    except OSError:
        pass
    return False


def get_zstd_uncompressed_size(file_path: str, zstd_bin: str = None) -> int:
    z_bin = zstd_bin or shutil.which("zstd") or shutil.which("zstd.exe")
    if z_bin:
        try:
            res = subprocess.run([z_bin, "-l", "--format=json", file_path], capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            if isinstance(data, list) and data:
                decomp_sz = data[0].get("decompSize") or data[0].get("uncompressedSize")
                if decomp_sz and int(decomp_sz) > 0:
                    return int(decomp_sz)
        except Exception:
            try:
                res = subprocess.run([z_bin, "-l", "-q", file_path], capture_output=True, text=True, check=True)
                for line in res.stdout.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 4 and parts[3].isdigit():
                        return int(parts[3])
            except Exception:
                pass

    try:
        import zstandard
        dctx = zstandard.ZstdDecompressor()
        total = 0
        with open(file_path, "rb") as f:
            with dctx.stream_reader(f) as reader:
                while True:
                    chunk = reader.read(4 * 1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
        if total > 0:
            return total
    except Exception:
        pass

    try:
        import zstandard
        with open(file_path, "rb") as f:
            header = f.read(1024)
            params = zstandard.get_frame_parameters(header)
            if params.content_size is not None and params.content_size > 0:
                return params.content_size
    except Exception:
        pass

    return os.path.getsize(file_path)


def classify_partition(name: str, file_path: str, is_zst: bool) -> str:
    name_lower = name.lower()
    if name_lower in SUPER_TR_PARTITIONS:
        return "super_tr"
    if name_lower in SUPER_PARTITIONS:
        return "super"
    if not is_zst and is_filesystem_image(file_path):
        return "super"
    if name_lower in SYSTEM_PARTITIONS:
        return "system"
    if name_lower in FIRMWARE_PARTITIONS:
        return "firmware"
    return "firmware"


def scan_partitions(directory: str, zstd_bin: str = None) -> Dict[str, Dict[str, Any]]:
    partitions = {}
    if not os.path.isdir(directory):
        return partitions

    for root, _, files in os.walk(directory):
        for file in files:
            file_lower = file.lower()
            file_path = os.path.join(root, file)

            if file_lower.endswith(".img.zst") or file_lower.endswith(".zst"):
                base_name = file_lower.replace(".img.zst", "").replace(".zst", "")
                is_zst = True
                raw_size = get_zstd_uncompressed_size(file_path, zstd_bin=zstd_bin)
            elif file_lower.endswith(".img"):
                base_name = file_lower[:-4]
                is_zst = is_zstd_file(file_path)
                if is_zst:
                    raw_size = get_zstd_uncompressed_size(file_path, zstd_bin=zstd_bin)
                else:
                    raw_size = os.path.getsize(file_path)
            else:
                continue

            ptype = classify_partition(base_name, file_path, is_zst)
            partitions[base_name] = {
                "name": base_name,
                "path": file_path,
                "filename": file,
                "is_zstd": is_zst,
                "raw_size": raw_size,
                "type": ptype
            }

    return partitions
