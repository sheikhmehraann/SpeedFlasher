from typing import List


class LinuxInstaller:
    @staticmethod
    def generate_shell_script(
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

        ext = ".img.zst" if use_zstd else ".img"
        for fw in firmware_imgs:
            lines.append(f'[ -f "{fw}{ext}" ] && $FASTBOOT flash "{fw}" "{fw}{ext}" || true')

        lines.append('echo ""')
        lines.append('echo "Flashing system bootchain partitions..."')
        for sys_part in system_imgs:
            lines.append(f'[ -f "{sys_part}{ext}" ] && $FASTBOOT flash "{sys_part}" "{sys_part}{ext}" || true')

        if super_imgs:
            lines.extend([
                'echo ""',
                'echo "Rebooting to fastbootd for dynamic partitions..."',
                '$FASTBOOT reboot fastboot || true',
                'sleep 5',
                'echo "Flashing dynamic partitions in fastbootd..."',
            ])
            for sp in super_imgs:
                lines.append(f'[ -f "{sp}{ext}" ] && $FASTBOOT flash "{sp}" "{sp}{ext}" || true')

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
