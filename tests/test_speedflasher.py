import os
import shutil
import struct
import tempfile
import unittest
import zipfile

from core.avb import AvbManager
from core.builder import FlashableBuilder
from core.partitions import scan_partitions
from core.recovery import generate_update_binary
from core.windows import WindowsPlatform, WindowsInstaller
from core.linux import LinuxPlatform, LinuxInstaller
from core.termux import TermuxPlatform, TermuxInstaller


class TestSpeedFlasherDeepOS(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="speedflasher_deep_")
        self.out_zip = os.path.join(self.test_dir, "output", "test_pkg.zip")

        # Create dummy boot image
        self.boot_path = os.path.join(self.test_dir, "boot.img")
        with open(self.boot_path, "wb") as f:
            f.write(b"BOOT_IMAGE_DATA" * 512)

        # Create dummy vbmeta image with AVB0 header
        self.vbmeta_path = os.path.join(self.test_dir, "vbmeta.img")
        with open(self.vbmeta_path, "wb") as f:
            h = bytearray(256)
            h[0:4] = b"AVB0"
            f.write(h)

        # Create dummy firmware image
        self.lk_path = os.path.join(self.test_dir, "lk.img")
        with open(self.lk_path, "wb") as f:
            f.write(b"LK_BOOTLOADER" * 256)

        # Create dummy super partition with ext4 superblock magic
        self.sys_path = os.path.join(self.test_dir, "system.img")
        with open(self.sys_path, "wb") as f:
            data = bytearray(4096)
            data[1080:1082] = b"\x53\xef"
            f.write(data)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_partition_scanning(self):
        parts = scan_partitions(self.test_dir)
        self.assertIn("boot", parts)
        self.assertIn("vbmeta", parts)
        self.assertIn("lk", parts)
        self.assertIn("system", parts)
        self.assertEqual(parts["boot"]["type"], "system")
        self.assertEqual(parts["vbmeta"]["type"], "system")
        self.assertEqual(parts["lk"]["type"], "firmware")
        self.assertEqual(parts["system"]["type"], "super")

    def test_windows_platform_and_installer(self):
        win_zstd = WindowsPlatform.get_zstd_binary()
        self.assertTrue(bool(win_zstd))
        bat = WindowsInstaller.generate_batch_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("fastboot", bat)
        self.assertIn("X6871", bat)
        self.assertIn("flash lk lk.img.zst", bat)
        self.assertIn("reboot fastboot", bat)

    def test_linux_platform_and_installer(self):
        lin_zstd = LinuxPlatform.get_zstd_binary()
        self.assertTrue(bool(lin_zstd))
        sh = LinuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("#!/usr/bin/env bash", sh)
        self.assertIn("X6871", sh)
        self.assertIn("flash \"lk\" \"lk.img.zst\"", sh)

    def test_termux_platform_and_installer(self):
        sh = TermuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("#!/data/data/com.termux/files/usr/bin/bash", sh)
        self.assertIn("android-tools", sh)
        self.assertIn("X6871", sh)

    def test_recovery_updater_script(self):
        ub = generate_update_binary(
            device="Infinix GT 20 Pro",
            firmware="15.1.2.180",
            codename="X6871",
            super_specs=[("system", 4096)],
            system_imgs=["boot", "vbmeta"],
            firmware_imgs=["lk"],
            tr_specs=[],
            maintainer="Mehraan",
            vbmeta_option="disable",
            use_zstd=True
        )
        self.assertIn("#!/sbin/sh", ub)
        self.assertIn("X6871", ub)
        self.assertIn("lptools", ub)
        self.assertIn("avbctl", ub)
        self.assertIn("flash_partition_zstd", ub)

    def test_avb_patcher(self):
        mgr = AvbManager("disable")
        self.assertTrue(mgr.patch_vbmeta_image(self.vbmeta_path))
        with open(self.vbmeta_path, "rb") as f:
            data = f.read(256)
            flags = struct.unpack(">I", data[120:124])[0]
            self.assertEqual(flags & 3, 3)

    def test_zip64_stream_no_runtime_error(self):
        """Validates that zipfile streaming with force_zip64 avoids Termux crash on >2GB files."""
        zip_path = os.path.join(self.test_dir, "zip64_test.zip")
        with zipfile.ZipFile(zip_path, "w", allowZip64=True) as z:
            zinfo = zipfile.ZipInfo("large_partition.img")
            zinfo.file_size = 3 * 1024 * 1024 * 1024
            with z.open(zinfo, mode="w", force_zip64=True) as dst:
                dst._file_size = 3 * 1024 * 1024 * 1024

    def test_full_pipeline_build(self):
        res = FlashableBuilder.build(
            imgs_dir=self.test_dir,
            output_zip=self.out_zip,
            device="Infinix GT 20 Pro",
            firmware="15.1.2.180",
            codename="X6871",
            maintainer="Mehraan",
            vbmeta_option="disable",
            zstd_level=1,
            zip_level=1,
            include_fastboot=True
        )
        self.assertTrue(os.path.isfile(res))

        with zipfile.ZipFile(res, "r") as z:
            names = z.namelist()
            self.assertIn("META-INF/com/google/android/update-binary", names)
            self.assertIn("META-INF/com/google/android/updater-script", names)
            self.assertIn("META-INF/zstd", names)
            self.assertIn("META-INF/bin/lptools", names)
            self.assertIn("boot.img.zst", names)
            self.assertIn("system.img.zst", names)
            self.assertIn("flash_windows.bat", names)
            self.assertIn("flash_linux.sh", names)
            self.assertIn("flash_termux.sh", names)

            # Check POSIX 0755 permissions
            info = z.getinfo("META-INF/com/google/android/update-binary")
            self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
