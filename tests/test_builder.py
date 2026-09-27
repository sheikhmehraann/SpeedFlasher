import os
import shutil
import struct
import tempfile
import unittest
import zipfile

from core.builder import FlashableBuilder
from core.partitions import scan_partitions


class TestSpeedFlasher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="speedflasher_test_")
        self.out_zip = os.path.join(self.test_dir, "test_output.zip")

        # Create dummy partitions
        self.boot_path = os.path.join(self.test_dir, "boot.img")
        with open(self.boot_path, "wb") as f:
            f.write(b"BOOT_IMAGE_DATA" * 1024)

        # Create dummy vbmeta with AVB0 magic
        self.vbmeta_path = os.path.join(self.test_dir, "vbmeta.img")
        with open(self.vbmeta_path, "wb") as f:
            header = bytearray(256)
            header[0:4] = b"AVB0"
            f.write(header)

        # Create dummy firmware image
        self.lk_path = os.path.join(self.test_dir, "lk.img")
        with open(self.lk_path, "wb") as f:
            f.write(b"LK_BOOTLOADER" * 512)

        # Create dummy super partition with ext4 superblock magic at offset 1080 (0x53 0xef)
        self.sys_path = os.path.join(self.test_dir, "system.img")
        with open(self.sys_path, "wb") as f:
            data = bytearray(4096)
            data[1080:1082] = b"\x53\xef"
            f.write(data)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scan_partitions(self):
        parts = scan_partitions(self.test_dir)
        self.assertIn("boot", parts)
        self.assertIn("vbmeta", parts)
        self.assertIn("lk", parts)
        self.assertIn("system", parts)
        self.assertEqual(parts["boot"]["type"], "system")
        self.assertEqual(parts["vbmeta"]["type"], "system")
        self.assertEqual(parts["lk"]["type"], "firmware")
        self.assertEqual(parts["system"]["type"], "super")

    def test_full_build(self):
        zip_path = FlashableBuilder.build(
            imgs_dir=self.test_dir,
            output_zip=self.out_zip,
            device="Test Phone",
            firmware="1.0.0",
            codename="testphone",
            maintainer="Mehraan",
            vbmeta_option="disable",
            zstd_level=1,
            zip_level=1,
            include_fastboot=True
        )

        self.assertTrue(os.path.isfile(zip_path))
        with zipfile.ZipFile(zip_path, "r") as z:
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

            # Inspect update-binary content
            ub = z.read("META-INF/com/google/android/update-binary").decode("utf-8")
            self.assertIn("testphone", ub)
            self.assertIn("Mehraan", ub)
            self.assertIn("manage_logical_partition", ub)

            # Check POSIX executable permission on update-binary
            ub_info = z.getinfo("META-INF/com/google/android/update-binary")
            perm = (ub_info.external_attr >> 16) & 0o777
            self.assertEqual(perm, 0o755)


if __name__ == "__main__":
    unittest.main()
