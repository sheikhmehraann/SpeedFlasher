from typing import List


class TermuxInstaller:
    @classmethod
    def _flash_block(cls, part: str, use_zstd: bool) -> List[str]:
        if use_zstd:
            return [
                f'if [ -f "{part}.img.zst" ]; then',
                f'    echo "Flashing {part}..."',
                f'    zstd -d -q -f -T0 --no-check "{part}.img.zst" -o "{part}.img"',
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
            "#!/data/data/com.termux/files/usr/bin/bash",
            "set -e",
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
            'cd "$SCRIPT_DIR"',
            "",
            'if ! command -v fastboot >/dev/null 2>&1; then',
            '    echo "[*] Installing android-tools in Termux..."',
            "    pkg update -y && pkg install -y android-tools",
            "fi",
            'if ! command -v zstd >/dev/null 2>&1; then',
            '    echo "[*] Installing zstd in Termux..."',
            "    pkg install -y zstd",
            "fi",
            'FASTBOOT="fastboot"',
            "",
            'echo "=============================================="',
            'echo "      SpeedFlasher Fastboot Installer (Termux)"',
            'echo "=============================================="',
            f'echo "Target Device: {device} ({codename})"',
            'echo ""',
            '$FASTBOOT devices',
            'echo ""',
            'read -r -p "Format userdata after flashing? (y/n): " WIPE',
            'echo ""',
            'echo "Flashing firmware partitions..."',
        ]

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
