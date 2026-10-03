import io
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from core.avb import AvbManager
from core.builder import FlashableBuilder, BuildResult
from core.partitions import scan_partitions, classify_partition, is_filesystem_image, is_zstd_file
from core.recovery import generate_update_binary
from core.windows import WindowsPlatform, WindowsInstaller
from core.linux import LinuxPlatform, LinuxInstaller
from core.termux import TermuxPlatform, TermuxInstaller
from main import clean_path, print_summary


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

    def test_partition_scanning_and_classification(self):
        parts = scan_partitions(self.test_dir)
        self.assertIn("boot", parts)
        self.assertIn("vbmeta", parts)
        self.assertIn("lk", parts)
        self.assertIn("system", parts)
        self.assertEqual(parts["boot"]["type"], "system")
        self.assertEqual(parts["vbmeta"]["type"], "system")
        self.assertEqual(parts["lk"]["type"], "firmware")
        self.assertEqual(parts["system"]["type"], "super")

        # Test classify helper directly
        self.assertEqual(classify_partition("tr_carrier", "", False), "super_tr")
        self.assertEqual(classify_partition("vendor", "", False), "super")
        self.assertEqual(classify_partition("dtbo", "", False), "system")
        self.assertEqual(classify_partition("abl", "", False), "firmware")
        self.assertTrue(is_filesystem_image(self.sys_path))
        self.assertFalse(is_filesystem_image(self.boot_path))

    def test_clean_path(self):
        self.assertEqual(clean_path(""), "")
        self.assertEqual(clean_path('  "C:\\test\\dir"  '), os.path.abspath("C:\\test\\dir"))
        self.assertEqual(clean_path("  'C:\\test\\dir'  "), os.path.abspath("C:\\test\\dir"))
        self.assertTrue(os.path.isabs(clean_path(".")))

    def test_windows_platform_and_installer(self):
        win_zstd = WindowsPlatform.get_zstd_binary()
        self.assertTrue(bool(win_zstd))
        assets = WindowsPlatform.get_fastboot_assets()
        self.assertTrue(any("fastboot.exe" in a for a in assets))
        self.assertTrue(any("zstd.exe" in a for a in assets))

        # Test with use_zstd=True
        bat_zstd = WindowsInstaller.generate_batch_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("fastboot", bat_zstd)
        self.assertIn("X6871", bat_zstd)
        self.assertIn("lk.img.zst", bat_zstd)
        self.assertIn("%zstd% -d -q -f", bat_zstd)
        self.assertIn("%fastboot% flash lk lk.img", bat_zstd)
        self.assertIn("reboot fastboot", bat_zstd)

        # Test with use_zstd=False
        bat_raw = WindowsInstaller.generate_batch_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot"],
            super_imgs=["system"],
            use_zstd=False
        )
        self.assertIn("%fastboot% flash lk lk.img", bat_raw)
        self.assertNotIn("lk.img.zst", bat_raw)

    def test_linux_platform_and_installer(self):
        lin_zstd = LinuxPlatform.get_zstd_binary()
        self.assertTrue(bool(lin_zstd))
        assets = LinuxPlatform.get_fastboot_assets()
        self.assertTrue(any("fastboot" in a for a in assets))
        self.assertTrue(any("zstd" in a for a in assets))

        sh_zstd = LinuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("#!/usr/bin/env bash", sh_zstd)
        self.assertIn("X6871", sh_zstd)
        self.assertIn("$ZSTD -d -q -f -T0 --no-check \"lk.img.zst\" -o \"lk.img\"", sh_zstd)
        self.assertIn("$FASTBOOT flash \"lk\" \"lk.img\"", sh_zstd)

        sh_raw = LinuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot"],
            super_imgs=["system"],
            use_zstd=False
        )
        self.assertIn("$FASTBOOT flash \"lk\" \"lk.img\"", sh_raw)
        self.assertNotIn("lk.img.zst", sh_raw)

    def test_termux_platform_and_installer(self):
        sh_zstd = TermuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot", "vbmeta"],
            super_imgs=["system"],
            use_zstd=True
        )
        self.assertIn("#!/data/data/com.termux/files/usr/bin/bash", sh_zstd)
        self.assertIn("android-tools", sh_zstd)
        self.assertIn("pkg install -y zstd", sh_zstd)
        self.assertIn("zstd -d -q -f -T0 --no-check \"lk.img.zst\" -o \"lk.img\"", sh_zstd)
        self.assertIn("$FASTBOOT flash \"lk\" \"lk.img\"", sh_zstd)

        sh_raw = TermuxInstaller.generate_shell_script(
            device="Infinix GT 20 Pro",
            codename="X6871",
            firmware_imgs=["lk"],
            system_imgs=["boot"],
            super_imgs=["system"],
            use_zstd=False
        )
        self.assertIn("$FASTBOOT flash \"lk\" \"lk.img\"", sh_raw)
        self.assertNotIn("lk.img.zst", sh_raw)

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
        self.assertIn("disable-verity", ub)

    def test_avb_patcher_all_modes(self):
        # Disable mode
        mgr_dis = AvbManager("disable")
        self.assertTrue(mgr_dis.patch_vbmeta_image(self.vbmeta_path))
        with open(self.vbmeta_path, "rb") as f:
            data = f.read(256)
            flags = struct.unpack(">I", data[120:124])[0]
            self.assertEqual(flags & 3, 3)

        # Enable mode
        mgr_en = AvbManager("enable")
        self.assertTrue(mgr_en.patch_vbmeta_image(self.vbmeta_path))
        with open(self.vbmeta_path, "rb") as f:
            data = f.read(256)
            flags = struct.unpack(">I", data[120:124])[0]
            self.assertEqual(flags & 3, 0)

        # Skip mode (no patching applied)
        mgr_sk = AvbManager("skip")
        self.assertFalse(mgr_sk.patch_vbmeta_image(self.vbmeta_path))

        # Invalid file
        non_avb = os.path.join(self.test_dir, "non_avb.img")
        with open(non_avb, "wb") as f:
            f.write(b"NOT_AVB_HEADER" * 10)
        self.assertFalse(mgr_dis.patch_vbmeta_image(non_avb))

    def test_zip64_stream_no_runtime_error(self):
        zip_path = os.path.join(self.test_dir, "zip64_test.zip")
        with zipfile.ZipFile(zip_path, "w", allowZip64=True) as z:
            zinfo = zipfile.ZipInfo("large_partition.img")
            zinfo.file_size = 3 * 1024 * 1024 * 1024
            with z.open(zinfo, mode="w", force_zip64=True) as dst:
                dst._file_size = 3 * 1024 * 1024 * 1024

    def test_full_pipeline_build_and_summary(self):
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
        self.assertIsInstance(res, BuildResult)
        self.assertEqual(res.device, "Infinix GT 20 Pro")
        self.assertEqual(res.codename, "X6871")
        self.assertEqual(res.firmware, "15.1.2.180")
        self.assertEqual(res.maintainer, "Mehraan")
        self.assertEqual(res.vbmeta_option, "disable")
        self.assertEqual(res.zstd_level, 1)
        self.assertEqual(res.zip_level, 1)
        self.assertIn("system", res.super_partitions)
        self.assertIn("boot", res.system_partitions)
        self.assertIn("lk", res.firmware_partitions)

        # Test summary output
        captured = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured
            print_summary(res)
        finally:
            sys.stdout = old_stdout

        summary_text = captured.getvalue()
        self.assertIn("SpeedFlasher Build Summary", summary_text)
        self.assertIn("Infinix GT 20 Pro", summary_text)
        self.assertIn("X6871", summary_text)
        self.assertIn("15.1.2.180", summary_text)
        self.assertIn("DISABLE", summary_text)
        self.assertIn("SUCCESS", summary_text)
        self.assertIn("Dynamic (Super)", summary_text)

        # Inspect ZIP structure
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
            self.assertIn("bin/windows/fastboot.exe", names)
            self.assertIn("bin/windows/zstd.exe", names)
            self.assertIn("bin/linux/fastboot", names)
            self.assertIn("bin/linux/zstd", names)

            # Check POSIX 0755 permissions
            info = z.getinfo("META-INF/com/google/android/update-binary")
            self.assertEqual((info.external_attr >> 16) & 0o777, 0o755)

    def test_interactive_flow_execution(self):
        from main import interactive_flow

        user_inputs = [
            self.test_dir,  # Enter IMGS Path :
            "Infinix GT 20 Pro",  # Devicename :
            "X6871",  # Codename :
            "15.0",  # Version :
            "disable",  # AVB 2.0 (vbmeta) :
            "Mehraan",  # Maintainer :
            "1",  # Ztsd Compression (0-22) :
            "1",  # Zip Compression (0-9) :
            "y",  # Proceed with build? [Y] :
            ""  # Press Enter to exit...
        ]

        with patch("builtins.input", side_effect=user_inputs):
            with patch("core.builder.get_current_platform") as mock_plat:
                mock_plat.return_value.ensure_dependencies.return_value = None
                captured = io.StringIO()
                old_stdout = sys.stdout
                try:
                    sys.stdout = captured
                    interactive_flow()
                finally:
                    sys.stdout = old_stdout

                out = captured.getvalue()
                self.assertIn("Build Configuration Review:", out)
                self.assertIn("SpeedFlasher Build Summary", out)
                self.assertIn("Infinix GT 20 Pro", out)
                self.assertIn("X6871", out)
                self.assertIn("15.0", out)
                self.assertIn("DISABLE", out)
                self.assertIn("SUCCESS", out)

    def test_interactive_flow_back_navigation(self):
        from main import interactive_flow

        user_inputs = [
            self.test_dir,        # 1. IMGS Path
            "Wrong Device",       # 2. Devicename
            "WrongCodename",      # 3. Codename
            "b",                  # 4. At Version -> 'b' goes back to 3 (Codename)
            "X6871",              # 3. Codename corrected
            "15.1",               # 4. Version
            "disable",            # 5. AVB 2.0
            "Mehraan",            # 6. Maintainer
            "1",                  # 7. Zstd
            "1",                  # 8. Zip
            "2",                  # 9. Review screen -> type '2' to edit Devicename
            "Infinix GT 20 Pro",  # 2. Devicename corrected
            "y",                  # 9. Review screen -> 'y' to proceed
            ""                    # Press Enter to exit...
        ]

        with patch("builtins.input", side_effect=user_inputs):
            with patch("core.builder.get_current_platform") as mock_plat:
                mock_plat.return_value.ensure_dependencies.return_value = None
                captured = io.StringIO()
                old_stdout = sys.stdout
                try:
                    sys.stdout = captured
                    interactive_flow()
                finally:
                    sys.stdout = old_stdout

                out = captured.getvalue()
                self.assertIn("Build Configuration Review:", out)
                self.assertIn("SpeedFlasher Build Summary", out)
                self.assertIn("Infinix GT 20 Pro", out)
                self.assertIn("X6871", out)
                self.assertIn("15.1", out)

    def test_interactive_prompts_have_no_bracket_defaults(self):
        from main import interactive_flow

        prompts_received = []
        user_inputs = [
            self.test_dir,
            "Infinix GT 20 Pro",
            "X6871",
            "15.0",
            "disable",
            "Mehraan",
            "1",
            "1",
            "y",
            ""
        ]

        def mock_input(prompt=""):
            prompts_received.append(prompt)
            return user_inputs.pop(0)

        with patch("builtins.input", side_effect=mock_input):
            with patch("core.builder.get_current_platform") as mock_plat:
                mock_plat.return_value.ensure_dependencies.return_value = None
                with patch("sys.stdout", new_callable=io.StringIO):
                    interactive_flow()

        self.assertEqual(prompts_received[0], "Enter IMGS Path : ")
        self.assertEqual(prompts_received[1], "Devicename : ")
        self.assertEqual(prompts_received[2], "Codename : ")
        self.assertEqual(prompts_received[3], "Version : ")
        self.assertEqual(prompts_received[4], "AVB 2.0 (vbmeta) : ")
        self.assertEqual(prompts_received[5], "Maintainer : ")
        self.assertEqual(prompts_received[6], "Ztsd Compression (0-22) : ")
        self.assertEqual(prompts_received[7], "Zip Compression (0-9) : ")
        for p in prompts_received[:8]:
            self.assertNotIn("[Android Device]", p)
            self.assertNotIn("[skip]", p)
            self.assertNotIn("[1.0]", p)
            self.assertNotIn("[1]", p)
            self.assertNotIn("[Mehraan]", p)

    def test_gui_initialization_and_scan(self):
        import tkinter as tk
        from gui import SpeedFlasherGUI, apply_windows_11_mica_theme

        root = tk.Tk()
        root.withdraw()
        try:
            app = SpeedFlasherGUI(root)
            self.assertIsNotNone(app)
            self.assertEqual(app.dev_var.get(), "Android Device")
            self.assertEqual(app.ver_var.get(), "1.0")
            self.assertEqual(app.avb_var.get(), "skip")

            # Test scanning test_dir
            app.path_var.set(self.test_dir)
            app._scan_folder(self.test_dir)
            self.assertEqual(len(app.partitions_dict), 4)
            self.assertIn("Dynamic: 1", app.chip_super.cget("text"))
            self.assertIn("Bootchain: 2", app.chip_boot.cget("text"))
            self.assertIn("Firmware: 1", app.chip_firmware.cget("text"))

            # Test slider callbacks
            app._on_zstd_slider("3")
            self.assertEqual(app.zstd_var.get(), 3)
            app._on_zip_slider("0")
            self.assertEqual(app.zip_var.get(), 0)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
