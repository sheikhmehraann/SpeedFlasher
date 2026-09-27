from typing import List


class LinuxInstaller:
    @classmethod
    def _flash_block(cls, part: str, use_zstd: bool) -> List[str]:
        if use_zstd:
            return [
                f'if [ -f "{part}.img.zst" ]; then',
                f'    echo "Flashing {part}..."',
                f'    $ZSTD -d -q -f "{part}.img.zst" -o "{part}.img"',
                f'    if [ -f "{part}.img" ]; then',
                f'        $FASTBOOT flash "{part}" "{part}.img"',
                f'        rm -f "{part}.img"',
                '    fi',
                f'elif [ -f "{part}.img" ]; then',
                f'    echo "Flashing {part}..."',
                f'    $FASTBOOT flash "{part}" "{part}.img"',
                'fi',
            ]
        return [
            f'if [ -f "{part}.img" ]; then',
            f'    echo "Flashing {part}..."',
            f'    $FASTBOOT flash "{part}" "{part}.img"',
            'fi',
        ]

    @classmethod
    def generate_shell_script(
        cls,
        device: str,
        codename: str,
        firmware_imgs: List[str],
        system_imgs: List[str],
        super_imgs: List[str],
        use_zstd: bool = False
    ) -> str:
        lines = [
            "#!/usr/bin/env bash",
            "set -e",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'cd "$SCRIPT_DIR"',
            "",
            'FASTBOOT="bin/linux/fastboot"',
            'if [ ! -x "$FASTBOOT" ]; then',
            '    FASTBOOT="fastboot"',
            '    if ! command -v fastboot >/dev/null 2>&1; then',
            '        echo "[Error] fastboot not found in PATH or bin/linux/fastboot"',
            "        exit 1",
            "    fi",
            "fi",
            "",
            'ZSTD="bin/linux/zstd"',
            'if [ ! -x "$ZSTD" ]; then',
            '    ZSTD="zstd"',
            'fi',
            "",
            'chmod +x "$FASTBOOT" "$ZSTD" 2>/dev/null || true',
            "",
            'echo "=============================================="',
            'echo "          SpeedFlasher Fastboot Installer"',
            'echo "=============================================="',
            f'echo "Target Device: {device} ({codename})"',
            'echo ""',
            '$FASTBOOT devices',
            'echo ""',
        ]

        if codename:
            lines.extend([
                f'PRODUCT=$($FASTBOOT getvar product 2>&1 | grep "product:" | awk \'{{print $2}}\' || true)',
                f'if [ -n "$PRODUCT" ] && ! echo "$PRODUCT" | grep -qi "{codename}"; then',
                f'    echo "[Warning] Device mismatch (found: $PRODUCT, expected: {codename})"',
                '    read -r -p "Do you want to continue anyway? (y/n) " CONT',
                '    if [ "$CONT" != "y" ] && [ "$CONT" != "Y" ]; then exit 1; fi',
                "fi",
                'echo ""',
            ])

        lines.extend([
            'read -r -p "Format userdata after flashing? (y/n): " WIPE',
            'echo ""',
            'echo "Flashing firmware partitions..."',
        ])

        for fw in firmware_imgs:
            lines.extend(cls._flash_block(fw, use_zstd))

        lines.append('echo ""')
        lines.append('echo "Flashing system bootchain partitions..."')
        for sys_part in system_imgs:
            lines.extend(cls._flash_block(sys_part, use_zstd))

        if super_imgs:
            lines.extend([
                'echo ""',
                'echo "Rebooting to fastbootd for dynamic partitions..."',
                '$FASTBOOT reboot fastboot || true',
                'sleep 5',
                'echo "Flashing dynamic partitions in fastbootd..."',
            ])
            for sp in super_imgs:
                lines.extend(cls._flash_block(sp, use_zstd))

        lines.extend([
            'echo ""',
            'if [ "$WIPE" = "y" ] || [ "$WIPE" = "Y" ]; then',
            '    echo "Wiping userdata..."',
            '    $FASTBOOT -w || true',
            "fi",
            'echo ""',
            'echo "Rebooting to system..."',
            '$FASTBOOT reboot',
            'echo "=============================================="',
            'echo "           Flashing Complete"',
            'echo "=============================================="',
        ])
        return "\n".join(lines)
