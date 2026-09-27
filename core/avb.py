import struct
from pathlib import Path

AVB_MAGIC = b"AVB0"
AVB_FLAGS_OFFSET = 120
AVB_FLAG_DISABLE_VERITY = 1
AVB_FLAG_DISABLE_VERIFICATION = 2


class AvbManager:
    def __init__(self, mode: str = "skip"):
        self.mode = mode.lower().strip()
        if self.mode not in ["disable", "enable", "skip"]:
            raise ValueError(f"Invalid AVB mode: '{mode}'. Must be 'disable', 'enable', or 'skip'.")

    def patch_vbmeta_image(self, vbmeta_path) -> bool:
        path = Path(vbmeta_path)
        if self.mode == "skip" or not path.exists():
            return False

        try:
            with open(path, "r+b") as f:
                data = f.read(256)
                if not data.startswith(AVB_MAGIC):
                    return False

                flags = struct.unpack(">I", data[120:124])[0]
                if self.mode == "disable":
                    new_flags = flags | AVB_FLAG_DISABLE_VERITY | AVB_FLAG_DISABLE_VERIFICATION
                    f.seek(120)
                    f.write(struct.pack(">I", new_flags))
                    return True
                elif self.mode == "enable":
                    new_flags = flags & ~(AVB_FLAG_DISABLE_VERITY | AVB_FLAG_DISABLE_VERIFICATION)
                    f.seek(120)
                    f.write(struct.pack(">I", new_flags))
                    return True
        except Exception:
            return False
        return False
