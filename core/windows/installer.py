from typing import List


class WindowsInstaller:
    @staticmethod
    def generate_batch_script(
        device: str,
        codename: str,
        firmware_imgs: List[str],
        system_imgs: List[str],
        super_imgs: List[str],
        use_zstd: bool = False
    ) -> str:
        lines = [
            "@echo off",
            "setlocal enabledelayedexpansion",
            "cd /d \"%~dp0\"",
            "title SpeedFlasher Fastboot Installer (Windows)",
            "set fastboot=bin\\windows\\fastboot.exe",
            "if not exist %fastboot% (",
            "    set fastboot=fastboot.exe",
            "    where fastboot.exe >nul 2>nul || (",
            "        echo [Error] fastboot.exe not found.",
            "        pause",
            "        exit /b 1",
            "    )",
            ")",
            "echo ==============================================",
            "echo          SpeedFlasher Fastboot Installer",
            "echo ==============================================",
            f"echo Target Device: {device} ({codename})",
            "echo.",
            "echo Checking connected device...",
            "%fastboot% devices",
            "echo.",
        ]

        if codename:
            lines.extend([
                f'%fastboot% getvar product 2>&1 | findstr /i "{codename}" >nul',
                "if %errorlevel% neq 0 (",
                f'    echo [Warning] Connected device does not match expected codename ({codename}).',
                '    set /p CONT="Do you want to continue anyway? (y/n): "',
                '    if /i "!CONT!" neq "y" exit /b 1',
                ")",
                "echo.",
            ])

        lines.extend([
            'set /p WIPE="Format userdata after flashing? (y/n): "',
            "echo.",
            "echo Flashing firmware partitions...",
        ])

        ext = ".img.zst" if use_zstd else ".img"
        for fw in firmware_imgs:
            lines.append(f"if exist {fw}{ext} %fastboot% flash {fw} {fw}{ext}")

        lines.append("echo.")
        lines.append("echo Flashing system bootchain partitions...")
        for sys_part in system_imgs:
            lines.append(f"if exist {sys_part}{ext} %fastboot% flash {sys_part} {sys_part}{ext}")

        if super_imgs:
            lines.extend([
                "echo.",
                "echo Rebooting to fastbootd for dynamic partitions...",
                "%fastboot% reboot fastboot",
                "echo Waiting for fastbootd...",
                "timeout /t 5 >nul",
                "echo Flashing dynamic partitions in fastbootd...",
            ])
            for sp in super_imgs:
                lines.append(f"if exist {sp}{ext} %fastboot% flash {sp} {sp}{ext}")

        lines.extend([
            "echo.",
            'if /i "%WIPE%" == "y" (',
            "    echo Wiping userdata...",
            "    %fastboot% -w",
            ")",
            "echo.",
            "echo Rebooting to system...",
            "%fastboot% reboot",
            "echo ==============================================",
            "echo            Flashing Complete",
            "echo ==============================================",
            "pause"
        ])
        return "\r\n".join(lines)
