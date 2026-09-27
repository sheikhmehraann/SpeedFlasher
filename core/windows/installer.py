from typing import List


class WindowsInstaller:
    @classmethod
    def _flash_block(cls, part: str, use_zstd: bool) -> List[str]:
        if use_zstd:
            return [
                f"if exist {part}.img.zst (",
                f"    echo Flashing {part}...",
                f"    %zstd% -d -q -f {part}.img.zst -o {part}.img",
                f"    if exist {part}.img (",
                f"        %fastboot% flash {part} {part}.img",
                f"        del /f /q {part}.img >nul 2>&1",
                f"    )",
                f") else if exist {part}.img (",
                f"    echo Flashing {part}...",
                f"    %fastboot% flash {part} {part}.img",
                f")",
            ]
        return [
            f"if exist {part}.img (",
            f"    echo Flashing {part}...",
            f"    %fastboot% flash {part} {part}.img",
            f")",
        ]

    @classmethod
    def generate_batch_script(
        cls,
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
            "set zstd=bin\\windows\\zstd.exe",
            "if not exist %zstd% (",
            "    set zstd=zstd.exe",
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

        for fw in firmware_imgs:
            lines.extend(cls._flash_block(fw, use_zstd))

        lines.append("echo.")
        lines.append("echo Flashing system bootchain partitions...")
        for sys_part in system_imgs:
            lines.extend(cls._flash_block(sys_part, use_zstd))

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
                lines.extend(cls._flash_block(sp, use_zstd))

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
