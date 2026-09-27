import os
import shutil
import subprocess
import sys


class TermuxPlatform:
    @staticmethod
    def is_termux() -> bool:
        return "TERMUX_VERSION" in os.environ or os.path.isdir("/data/data/com.termux")

    @staticmethod
    def get_bin_dir() -> str:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base, "bin", "termux")

    @classmethod
    def get_zstd_binary(cls) -> str:
        system_bin = shutil.which("zstd")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def get_fastboot_binary(cls) -> str:
        system_bin = shutil.which("fastboot")
        if system_bin:
            return system_bin
        return ""

    @classmethod
    def ensure_dependencies(cls):
        if not cls.is_termux():
            return

        storage_dir = os.path.expanduser("~/storage")
        if not os.path.isdir(storage_dir):
            print("[*] Requesting Termux storage permission...")
            subprocess.run(["termux-setup-storage"], check=False)

        # Check required native packages in Termux
        missing_pkgs = []
        if not shutil.which("zstd"):
            missing_pkgs.append("zstd")
        if not shutil.which("fastboot"):
            missing_pkgs.append("android-tools")
        if not shutil.which("clang"):
            missing_pkgs.append("clang")

        if missing_pkgs:
            print(f"[*] Installing required Termux packages: {', '.join(missing_pkgs)}")
            subprocess.run(["pkg", "install", "-y", *missing_pkgs], check=False)

        missing_py = []
        try:
            import zstandard
        except ImportError:
            missing_py.append("zstandard")

        if missing_py:
            print(f"[*] Installing required Python packages: {', '.join(missing_py)}")
            subprocess.run([sys.executable, "-m", "pip", "install", *missing_py], check=False)
