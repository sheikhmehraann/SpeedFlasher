import os
import shutil
import subprocess
import sys


class LinuxPlatform:
    @staticmethod
    def get_bin_dir() -> str:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base, "bin", "linux")

    @classmethod
    def get_zstd_binary(cls) -> str:
        bundled = os.path.join(cls.get_bin_dir(), "zstd")
        if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
            return bundled
        system_bin = shutil.which("zstd")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def get_fastboot_binary(cls) -> str:
        bundled = os.path.join(cls.get_bin_dir(), "fastboot")
        if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
            return bundled
        system_bin = shutil.which("fastboot")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def get_fastboot_assets(cls) -> list:
        bin_dir = cls.get_bin_dir()
        assets = []
        for name in ("fastboot", "zstd"):
            p = os.path.join(bin_dir, name)
            if os.path.isfile(p):
                assets.append(p)
        return assets

    @classmethod
    def ensure_dependencies(cls):
        bin_dir = cls.get_bin_dir()
        if os.path.isdir(bin_dir):
            for item in os.listdir(bin_dir):
                fp = os.path.join(bin_dir, item)
                if os.path.isfile(fp):
                    try:
                        os.chmod(fp, 0o755)
                    except OSError:
                        pass

        if cls.get_zstd_binary():
            return

        missing = []
        try:
            import zstandard
        except ImportError:
            missing.append("zstandard")

        if missing:
            print(f"[*] Installing fallback Python package: {', '.join(missing)}")
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)
