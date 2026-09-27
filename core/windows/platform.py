import os
import shutil
import subprocess
import sys


class WindowsPlatform:
    @staticmethod
    def get_bin_dir() -> str:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base, "bin", "windows")

    @classmethod
    def get_zstd_binary(cls) -> str:
        bundled = os.path.join(cls.get_bin_dir(), "zstd.exe")
        if os.path.isfile(bundled):
            return bundled
        system_bin = shutil.which("zstd.exe") or shutil.which("zstd")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def get_fastboot_binary(cls) -> str:
        bundled = os.path.join(cls.get_bin_dir(), "fastboot.exe")
        if os.path.isfile(bundled):
            return bundled
        system_bin = shutil.which("fastboot.exe") or shutil.which("fastboot")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def get_fastboot_assets(cls) -> list:
        bin_dir = cls.get_bin_dir()
        assets = []
        for name in ("fastboot.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"):
            p = os.path.join(bin_dir, name)
            if os.path.isfile(p):
                assets.append(p)
        return assets

    @staticmethod
    def ensure_dependencies():
        missing = []
        try:
            import zstandard
        except ImportError:
            missing.append("zstandard")

        if missing:
            print(f"[*] Installing missing Python packages: {', '.join(missing)}")
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)
