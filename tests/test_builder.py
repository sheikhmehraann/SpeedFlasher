import os
import shutil
import struct
import tempfile
import unittest
import zipfile

from core.avb import AvbManager
from core.builder import FlashableBuilder
from core.extractor import PartitionExtractor
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

        # Create dummy build.prop for metadata detection test
        self.prop_path = os.path.join(self.test_dir, "build.prop")
        with open(self.prop_path, "w", encoding="utf-8") as f:
            f.write("ro.product.device=X6871\nro.product.model=Infinix GT 20 Pro\nro.build.display.id=15.1.2.180\n")

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

    def test_metadata_detection(self):
        meta = PartitionExtractor.detect_metadata(self.test_dir)
        self.assertEqual(meta["codename"], "X6871")
        self.assertEqual(meta["device"], "Infinix GT 20 Pro")
        self.assertEqual(meta["version"], "15.1.2.180")

    def test_avb_patching(self):
        mgr = AvbManager("disable")
        self.assertTrue(mgr.patch_vbmeta_image(self.vbmeta_path))
        with open(self.vbmeta_path, "rb") as f:
            data = f.read(256)
            flags = struct.unpack(">I", data[120:124])[0]
            self.assertEqual(flags & 3, 3)

    def test_zip64_stream_write_no_crash(self):
        """Validates that writing large entries with force_zip64 does not trigger Termux crash."""
        test_zip_path = os.path.join(self.test_dir, "test_zip64.zip")
        with zipfile.ZipFile(test_zip_path, "w", allowZip64=True) as z:
            zinfo = zipfile.ZipInfo("large_partition.img")
            zinfo.file_size = 3 * 1024 * 1024 * 1024  # 3GB
            # Must not raise RuntimeError: File size too large, try using force_zip64
            with z.open(zinfo, mode="w", force_zip64=True) as dst:
                dst._file_size = 3 * 1024 * 1024 * 1024

    def test_full_build(self):
        zip_path = FlashableBuilder.build(
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

            ub = z.read("META-INF/com/google/android/update-binary").decode("utf-8")
            self.assertIn("X6871", ub)
            self.assertIn("Mehraan", ub)
            self.assertIn("manage_logical_partition", ub)

            ub_info = z.getinfo("META-INF/com/google/android/update-binary")
            perm = (ub_info.external_attr >> 16) & 0o777
            self.assertEqual(perm, 0o755)

    def test_archive_input_flow(self):
        """Validates building from an input archive (.zip containing partitions)."""
        archive_path = os.path.join(self.test_dir, "rom_archive.zip")
        with zipfile.ZipFile(archive_path, "w") as z:
            z.write(self.boot_path, "boot.img")
            z.write(self.sys_path, "system.img")
            z.write(self.prop_path, "build.prop")

        from main import resolve_source
        extracted = resolve_source(archive_path, os.path.join(self.test_dir, "ws"))
        self.assertTrue(os.path.isdir(extracted))
        parts = scan_partitions(extracted)
        self.assertIn("boot", parts)
        self.assertIn("system", parts)

        meta = PartitionExtractor.detect_metadata(extracted)
        self.assertEqual(meta["codename"], "X6871")


if __name__ == "__main__":
    unittest.main()
